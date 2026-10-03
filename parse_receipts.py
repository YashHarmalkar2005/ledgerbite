"""Read a receipt image or voice note with Gemini, sanity-check it, then save it to Supabase.

Two steps so the app can show a preview first:
    extract_receipt()  -> (data, warnings)   nothing is saved
    save_receipt(data) -> saves header + line items
process_receipt() does both for command-line use.
"""
import os
import re
from datetime import datetime

from PIL import Image

from common import (
    delete_media, generate_json, now_local, supabase, upload_media,
)

PRICE_TOLERANCE = 0.25                                   # warn if billed price is >25% off the menu price
LARGE_AMOUNT = float(os.getenv("LARGE_AMOUNT", "50000"))  # warn on any single amount above this (₹)


# ---------- small parsing helpers ----------
def _f(value, default=0.0) -> float:
    """Tolerant float: handles None, '₹1,999.50', 'N/A'."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return default


def _key(name) -> str:
    return str(name or "").strip().lower()


def parse_date(value, fallback: str) -> str:
    """Receipts use DD/MM/YYYY in India, so try that before anything American."""
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return fallback


def parse_time(value, fallback: str) -> str:
    text = str(value or "").strip().upper()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    return fallback


def load_menu() -> dict:
    """{dish key: (display name, selling price)} from dish_recipes."""
    try:
        rows = supabase.table("dish_recipes").select("dish_name,selling_price").execute().data or []
    except Exception:
        return {}
    return {_key(r["dish_name"]): (r["dish_name"], _f(r.get("selling_price"))) for r in rows if r.get("dish_name")}


# ---------- extraction ----------
def build_prompt(today: str, menu: dict) -> str:
    menu_line = ", ".join(name for name, _ in menu.values()) or "(none)"
    return f"""
Analyze this receipt image or voice note and extract structured JSON.
Today's date is {today}. Indian receipts write dates as DD/MM/YYYY.

receipt_type rules:
- Raw commodities/ingredients (flour, sugar, tomato, cheese, chicken, LPG cylinder, oil...) from a supplier -> "RAW_MATERIAL".
- Restaurant menu dishes (pizza, burger, biryani, salad, drinks...) or a table/order/receipt number -> "CUSTOMER_SALE".

For CUSTOMER_SALE the menu is: {menu_line}.
If a printed dish is clearly one of these (only spelling or capitalisation differs) use the menu name exactly.
Otherwise keep the dish name as printed. Do not guess.

Copy values exactly as printed. Never invent or "fix" numbers.
Use the date and time printed on the receipt, converted to YYYY-MM-DD and HH:MM:SS.
If the receipt shows no date or time, use null.

Schema:
{{
  "receipt_type": "RAW_MATERIAL" or "CUSTOMER_SALE",
  "vendor_or_order": "supplier name, or the receipt/order/table number for sales",
  "date": "YYYY-MM-DD or null",
  "time": "HH:MM:SS or null",
  "subtotal": 0.0,
  "tax_amount": 0.0,
  "grand_total": 0.0,
  "payment_method": "Cash / UPI / Card / Vendor Bill",
  "items": [
    {{"name": "string", "quantity": 0.0, "unit": "kg / liters / units / pcs / packet",
      "rate_or_price": 0.0, "line_total": 0.0}}
  ]
}}
rate_or_price is the price of ONE unit. line_total is the amount printed for that line (null if not printed).
Return ONLY valid JSON.
"""


def normalise(raw: dict, category: str, today: str, now_time: str) -> dict:
    rtype = str(raw.get("receipt_type") or "").upper()
    if category == "Raw Material (Expense)":
        rtype = "RAW_MATERIAL"
    elif category == "Customer Sale (Revenue)":
        rtype = "CUSTOMER_SALE"
    elif rtype not in ("RAW_MATERIAL", "CUSTOMER_SALE"):
        rtype = "CUSTOMER_SALE"

    items = []
    for it in raw.get("items") or []:
        if not isinstance(it, dict) or not str(it.get("name") or "").strip():
            continue
        qty = _f(it.get("quantity"), 1.0) or 1.0
        rate = _f(it.get("rate_or_price"))
        printed = it.get("line_total")
        line_total = _f(printed) if printed is not None else 0.0
        if rate <= 0 and line_total > 0:
            rate = round(line_total / qty, 2)
        items.append({
            "name": str(it["name"]).strip(),
            "quantity": qty,
            "unit": str(it.get("unit") or ("pcs" if rtype == "CUSTOMER_SALE" else "kg")).strip(),
            "rate_or_price": rate,
            "line_total": line_total if printed is not None else round(qty * rate, 2),
            "_printed_total": printed is not None,
        })

    items_sum = round(sum(i["line_total"] for i in items), 2)
    subtotal = _f(raw.get("subtotal")) or items_sum
    tax = _f(raw.get("tax_amount"))
    grand = _f(raw.get("grand_total")) or round(subtotal + tax, 2)

    default_vendor = "Local Vendor" if rtype == "RAW_MATERIAL" else "Counter Takeaway"
    default_pay = "Cash" if rtype == "RAW_MATERIAL" else "UPI"
    return {
        "receipt_type": rtype,
        "vendor_or_order": str(raw.get("vendor_or_order") or default_vendor).strip(),
        "date": parse_date(raw.get("date"), today),
        "time": parse_time(raw.get("time"), now_time),
        "subtotal": subtotal,
        "tax_amount": tax,
        "grand_total": grand,
        "payment_method": str(raw.get("payment_method") or default_pay).strip(),
        "items": items,
    }


def find_duplicate(data: dict) -> bool:
    """Same order/vendor + date + total already saved?"""
    try:
        if data["receipt_type"] == "RAW_MATERIAL":
            q = (supabase.table("raw_material_purchases").select("id")
                 .eq("vendor_name", data["vendor_or_order"]).eq("purchase_date", data["date"])
                 .eq("total_amount", data["grand_total"]))
        else:
            q = (supabase.table("customer_sales").select("id")
                 .eq("table_or_order_no", data["vendor_or_order"]).eq("sale_date", data["date"])
                 .eq("total_amount", data["grand_total"]))
        return bool(q.limit(1).execute().data)
    except Exception:
        return False


def check_receipt(data: dict, menu: dict) -> list:
    """Plain-English warnings. A warning never blocks saving, but the app makes the user confirm."""
    w = []
    items = data["items"]
    if not items:
        w.append("No line items were found on this entry.")
    if data["grand_total"] <= 0:
        w.append("The total is ₹0. Nothing useful would be recorded.")

    for it in items:
        expected = round(it["quantity"] * it["rate_or_price"], 2)
        if it["_printed_total"] and it["quantity"] > 0 and it["rate_or_price"] > 0 and abs(it["line_total"] - expected) > 0.5:
            w.append(f"Line maths is off for {it['name']}: {it['quantity']:g} × ₹{it['rate_or_price']:,.2f} "
                     f"should be ₹{expected:,.2f} but the bill says ₹{it['line_total']:,.2f}.")
        if max(it["line_total"], it["rate_or_price"]) > LARGE_AMOUNT:
            w.append(f"{it['name']} is billed at ₹{max(it['line_total'], it['rate_or_price']):,.2f}. "
                     "That is unusually large. Check for a misplaced decimal or extra digits.")

    if items:
        items_sum = round(sum(i["line_total"] for i in items), 2)
        if abs(items_sum - data["subtotal"]) > 1:
            w.append(f"Line items add up to ₹{items_sum:,.2f} but the subtotal says ₹{data['subtotal']:,.2f}.")
    if abs(data["subtotal"] + data["tax_amount"] - data["grand_total"]) > 1:
        w.append(f"Subtotal ₹{data['subtotal']:,.2f} + GST ₹{data['tax_amount']:,.2f} "
                 f"is not the total of ₹{data['grand_total']:,.2f}.")

    if data["receipt_type"] == "CUSTOMER_SALE":
        for it in items:
            entry = menu.get(_key(it["name"]))
            if not entry:
                w.append(f"'{it['name']}' isn't on your menu, so its ingredients won't be deducted from stock. "
                         "Add it under Dishes & Recipes.")
            elif entry[1] > 0 and it["rate_or_price"] > 0 and abs(it["rate_or_price"] - entry[1]) / entry[1] > PRICE_TOLERANCE:
                w.append(f"{entry[0]} is billed at ₹{it['rate_or_price']:,.2f} but your menu price is ₹{entry[1]:,.2f}.")

    if find_duplicate(data):
        data["duplicate"] = True
        w.append("An entry with the same number, date and total is already saved. This looks like a duplicate.")
    return w


def extract_receipt(file_path, receipt_category="Auto-Detect", is_audio=False):
    """Read the file and return (data, warnings). Nothing is written to the database."""
    now = now_local()
    today, now_time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
    menu = load_menu()

    media = upload_media(file_path) if is_audio else Image.open(file_path)
    try:
        raw = generate_json([media], build_prompt(today, menu))
    finally:
        if is_audio:
            delete_media(media)

    data = normalise(raw, receipt_category, today, now_time)
    return data, check_receipt(data, menu)


# ---------- saving ----------
def save_receipt(data: dict) -> None:
    clean_json = {**{k: v for k, v in data.items() if k not in ("duplicate",)},
                  "items": [{k: v for k, v in i.items() if not k.startswith("_")} for i in data["items"]]}

    if data["receipt_type"] == "RAW_MATERIAL":
        res = supabase.table("raw_material_purchases").insert({
            "vendor_name": data["vendor_or_order"],
            "purchase_date": data["date"],
            "purchase_time": data["time"],
            "total_amount": data["grand_total"],
            "payment_method": data["payment_method"],
            "raw_json": clean_json,
        }).execute()
        header_id = res.data[0]["id"]
        rows = [{
            "purchase_id": header_id,
            "item_name": i["name"],
            "quantity": i["quantity"],
            "unit": i["unit"],
            "rate_per_unit": i["rate_or_price"],
            "total_item_price": round(i["quantity"] * i["rate_or_price"], 2),
        } for i in data["items"]]
        table, parent = "purchase_line_items", "raw_material_purchases"
    else:
        res = supabase.table("customer_sales").insert({
            "table_or_order_no": data["vendor_or_order"],
            "sale_date": data["date"],
            "sale_time": data["time"],
            "subtotal": data["subtotal"],          # before GST
            "total_amount": data["grand_total"],   # what the customer paid, GST included
            "payment_method": data["payment_method"],
            "raw_json": clean_json,
        }).execute()
        header_id = res.data[0]["id"]
        rows = [{
            "sale_id": header_id,
            "dish_name": i["name"],
            "quantity": max(1, int(round(i["quantity"]))),
            "unit_price": i["rate_or_price"],
        } for i in data["items"]]
        table, parent = "sales_line_items", "customer_sales"

    if rows:
        try:
            supabase.table(table).insert(rows).execute()
        except Exception:
            supabase.table(parent).delete().eq("id", header_id).execute()  # don't leave a header with no items
            raise


def process_receipt(file_path, receipt_category="Auto-Detect", is_audio=False, allow_duplicate=False):
    """Extract and save in one go (command-line use). Returns the data with a 'warnings' list."""
    data, warnings = extract_receipt(file_path, receipt_category, is_audio)
    data["warnings"] = warnings
    if data.get("duplicate") and not allow_duplicate:
        data["saved"] = False
        return data
    save_receipt(data)
    data["saved"] = True
    return data
