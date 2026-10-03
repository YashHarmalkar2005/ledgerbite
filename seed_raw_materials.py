import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing from .env file.")
    exit()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Raw materials extracted from your list with default units & estimated baseline market rates (INR)
RAW_MATERIALS_LIST = [
    {"item_name": "Flour (white)", "quantity": 10.0, "unit": "kg", "rate_per_unit": 40.00},
    {"item_name": "Yeast", "quantity": 1.0, "unit": "packet", "rate_per_unit": 120.00},
    {"item_name": "Salt", "quantity": 2.0, "unit": "kg", "rate_per_unit": 25.00},
    {"item_name": "Sugar", "quantity": 5.0, "unit": "kg", "rate_per_unit": 45.00},
    {"item_name": "Tomato", "quantity": 10.0, "unit": "kg", "rate_per_unit": 35.00},
    {"item_name": "Potato", "quantity": 15.0, "unit": "kg", "rate_per_unit": 30.00},
    {"item_name": "Cheese", "quantity": 2.0, "unit": "kg", "rate_per_unit": 450.00},
    {"item_name": "Spices", "quantity": 1.0, "unit": "kg", "rate_per_unit": 350.00},
    {"item_name": "Lettuce", "quantity": 3.0, "unit": "kg", "rate_per_unit": 80.00},
    {"item_name": "Paneer", "quantity": 5.0, "unit": "kg", "rate_per_unit": 360.00},
    {"item_name": "Chicken", "quantity": 10.0, "unit": "kg", "rate_per_unit": 220.00}
]

SEED_VENDOR = "Wholesale Mandi (Initial Baseline)"


def seed_baseline_inventory():
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M:%S")

    # Don't seed twice: it would double your stock and your expenses
    existing = supabase.table("raw_material_purchases").select("id").eq("vendor_name", SEED_VENDOR).limit(1).execute()
    if existing.data:
        print("ℹ️ Baseline already seeded. Nothing to do.")
        return

    # 1. Calculate overall bill total
    total_bill_amount = sum(item["quantity"] * item["rate_per_unit"] for item in RAW_MATERIALS_LIST)

    print(f"🌱 Seeding baseline raw materials purchase (Total: ₹{total_bill_amount:,.2f})...")

    # 2. Insert master invoice header into raw_material_purchases
    header_res = supabase.table("raw_material_purchases").insert({
        "vendor_name": SEED_VENDOR,
        "purchase_date": current_date,
        "purchase_time": current_time,
        "total_amount": total_bill_amount,
        "payment_method": "Cash",
        "notes": "Initial raw materials list seed"
    }).execute()

    if not header_res.data:
        print("❌ Failed to create raw material purchase header.")
        return

    purchase_id = header_res.data[0]["id"]

    # 3. Insert all itemized raw materials into purchase_line_items
    line_items_payload = [
        {
            "purchase_id": purchase_id,
            "item_name": item["item_name"],
            "quantity": item["quantity"],
            "unit": item["unit"],
            "rate_per_unit": item["rate_per_unit"],
            "total_item_price": round(item["quantity"] * item["rate_per_unit"], 2)
        }
        for item in RAW_MATERIALS_LIST
    ]

    supabase.table("purchase_line_items").insert(line_items_payload).execute()

    print("✅ Successfully seeded 11 raw material line items into Supabase!")

if __name__ == "__main__":
    seed_baseline_inventory()