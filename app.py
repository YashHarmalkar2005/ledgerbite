import os
import re
import io
import html
import json
import tempfile
import pandas as pd
import streamlit as st

_import_error = None
try:
    from common import supabase, now_local, gemini, MODELS, USE_VERTEX, GEMINI_API_KEY
    from parse_receipts import extract_receipt, save_receipt
except Exception as _e:  # missing .env values etc. Shown nicely below, once Streamlit is configured.
    _import_error = _e

# ==========================================
# BRAND TOKENS (from LedgerBite Brand Identity)
# ==========================================
ESPRESSO = "#2D231E"   # Primary
TERRACOTTA = "#D65A31"  # Accent
SAGE = "#839788"        # Secondary
LINEN = "#FBF8F3"       # Background
LINEN_DEEP = "#F2EBE0"  # Tint of linen for panels
LINE = "#E6DDD0"        # Hairlines
MUTED = "#7A6B61"       # Muted espresso for secondary text


# ==========================================
# INVENTORY CONFIG
# ==========================================
# Tables/columns the app looks for when working out what has been used up.
# Dish sales are read from the first of these tables that exists.
SALE_ITEM_TABLES = ["sales_line_items", "sale_line_items", "customer_sale_items"]
DISH_COLS = ["dish_name", "item_name", "name"]
QTY_COLS = ["quantity", "qty"]
LOW_STOCK_RATIO = 0.10  # "Low" when stock is at or below 10% of everything bought

TAGLINE = "Know your daily profit before you wipe the counters."

st.set_page_config(
    page_title="LedgerBite",
    page_icon="logo.png" if os.path.exists("logo.png") else "🍳",
    layout="wide",
)

if _import_error:
    st.error(f"LedgerBite couldn't start: {_import_error}")
    st.stop()

# ==========================================
# GLOBAL STYLES
# ==========================================
st.markdown(f"""
<style>
    :root {{
        --espresso: {ESPRESSO};
        --terracotta: {TERRACOTTA};
        --sage: {SAGE};
        --linen: {LINEN};
        --linen-deep: {LINEN_DEEP};
        --line: {LINE};
        --muted: {MUTED};
    }}

    /* Base */
    .stApp {{ background-color: var(--linen); color: var(--espresso); }}
    html, body, [class*="css"] {{
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        color: var(--espresso);
    }}
    .block-container {{ padding-top: 2rem; padding-bottom: 4rem; max-width: 1180px; }}
    header[data-testid="stHeader"] {{ background: transparent; }}
    #MainMenu, footer {{ visibility: hidden; }}

    /* Headings: Georgia serif */
    h1, h2, h3, h4 {{
        font-family: Georgia, "Times New Roman", serif !important;
        color: var(--espresso) !important;
        letter-spacing: -0.01em;
        font-weight: 700 !important;
    }}
    h2 {{ font-size: 1.7rem !important; margin-bottom: 0.25rem !important; }}
    h3 {{ font-size: 1.2rem !important; }}
    hr {{ border: none; border-top: 1px solid var(--line); margin: 1.5rem 0; }}

    /* Brand header */
    .lb-brand {{
        display: flex; align-items: baseline; gap: 18px; flex-wrap: wrap;
        padding-bottom: 14px;
    }}
    .lb-wordmark {{
        font-family: Georgia, "Times New Roman", serif;
        font-size: 2.2rem; font-weight: 700; color: var(--espresso);
        letter-spacing: -0.02em; line-height: 1;
    }}
    .lb-wordmark span {{ color: var(--terracotta); }}
    .lb-tagline {{ color: var(--muted); font-size: 0.95rem; font-style: italic; font-family: Georgia, serif; }}

    /* Page intro line under each heading */
    .lb-sub {{ color: var(--muted); font-size: 0.95rem; margin: 0 0 1.25rem 0; }}

    /* Top navigation: segmented tabs */
    .stRadio [role="radiogroup"] {{
        display: flex; flex-direction: row; flex-wrap: wrap; gap: 4px;
        border-bottom: 1px solid var(--line);
        padding-bottom: 0; margin-bottom: 1.5rem;
    }}
    .stRadio label {{
        padding: 10px 18px !important; margin: 0 !important;
        border-bottom: 3px solid transparent;
        border-radius: 0 !important; background: transparent !important;
        cursor: pointer; transition: color .15s ease, border-color .15s ease;
    }}
    .stRadio label > div:first-child {{ display: none !important; }}
    .stRadio label p {{ color: var(--muted); font-weight: 500; font-size: 0.95rem; margin: 0; }}
    .stRadio label:hover p {{ color: var(--espresso); }}
    .stRadio label:has(input:checked) {{ border-bottom-color: var(--terracotta); }}
    .stRadio label:has(input:checked) p {{ color: var(--espresso); font-weight: 700; }}

    /* Summary cards */
    .lb-card {{
        background: #FFFFFF; border: 1px solid var(--line); border-radius: 12px;
        padding: 20px 22px; height: 100%;
    }}
    .lb-card .label {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 6px; }}
    .lb-card .value {{
        font-family: Georgia, serif; font-size: 2rem; font-weight: 700;
        color: var(--espresso); line-height: 1.1;
    }}
    .lb-card.profit .value {{ color: var(--sage); }}
    .lb-card.loss .value {{ color: var(--terracotta); }}
    .lb-card .note {{ color: var(--muted); font-size: 0.8rem; margin-top: 6px; }}

    /* Buttons */
    .stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {{
        background-color: var(--terracotta); color: #fff; border: 1px solid var(--terracotta);
        border-radius: 8px; padding: 0.55rem 1.2rem; font-weight: 600;
        transition: background-color .15s ease;
    }}
    .stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover {{
        background-color: #B94A25; border-color: #B94A25; color: #fff;
    }}
    .stButton > button:focus-visible, .stFormSubmitButton > button:focus-visible {{
        outline: 3px solid var(--sage); outline-offset: 2px;
    }}

    /* Inner tabs (Dish ops, material ops) */
    .stTabs [data-baseweb="tab-list"] {{ gap: 6px; border-bottom: 1px solid var(--line); }}
    .stTabs [data-baseweb="tab"] {{ color: var(--muted); font-weight: 500; padding: 8px 14px; }}
    .stTabs [aria-selected="true"] {{ color: var(--espresso) !important; font-weight: 700; }}
    .stTabs [data-baseweb="tab-highlight"] {{ background-color: var(--terracotta) !important; }}

    /* Forms and inputs */
    [data-testid="stForm"] {{
        background: #FFFFFF; border: 1px solid var(--line); border-radius: 12px; padding: 1.25rem;
    }}
    .stTextInput input, .stNumberInput input, .stSelectbox > div > div {{
        background-color: #FFFFFF; border-radius: 8px;
    }}
    label p {{ font-size: 0.9rem; }}

    /* Tables */
    [data-testid="stDataFrame"] {{
        border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: #fff;
    }}

    /* Alerts */
    [data-testid="stAlert"] {{ border-radius: 10px; border: 1px solid var(--line); }}

    /* File uploader */
    [data-testid="stFileUploaderDropzone"] {{
        background: #FFFFFF; border: 1.5px dashed var(--sage); border-radius: 12px;
    }}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<style>
    /* ---- Force light look regardless of browser/OS dark mode ---- */
    :root, .stApp {{ color-scheme: light; }}
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background-color: var(--linen) !important; }}
    .stApp p, .stApp li, .stApp label,
    .stApp [data-testid="stWidgetLabel"] *, .stApp [data-testid="stMarkdownContainer"] {{ color: var(--espresso) !important; }}
    .stApp .lb-sub, .stApp .lb-tagline {{ color: var(--muted) !important; }}
    .stApp .stRadio label p {{ color: var(--muted) !important; }}
    .stApp .stRadio label:has(input:checked) p {{ color: var(--espresso) !important; }}
    .stApp .stTabs [data-baseweb="tab"] p {{ color: var(--muted) !important; }}
    .stApp .stTabs [aria-selected="true"] p {{ color: var(--espresso) !important; }}

    /* Buttons: always white text on terracotta */
    .stApp .stButton > button, .stApp .stFormSubmitButton > button, .stApp .stDownloadButton > button {{
        background-color: var(--terracotta) !important; border-color: var(--terracotta) !important;
    }}
    .stApp .stButton > button *, .stApp .stFormSubmitButton > button *, .stApp .stDownloadButton > button * {{
        color: #FFFFFF !important;
    }}
    .stApp .stButton > button:hover, .stApp .stFormSubmitButton > button:hover, .stApp .stDownloadButton > button:hover {{
        background-color: #B94A25 !important; border-color: #B94A25 !important;
    }}

    /* Inputs, selects, number steppers: white with dark text */
    .stApp input, .stApp textarea {{
        background-color: #FFFFFF !important; color: var(--espresso) !important;
        -webkit-text-fill-color: var(--espresso) !important;
    }}
    .stApp [data-baseweb="input"], .stApp [data-baseweb="base-input"],
    .stApp [data-baseweb="select"] > div {{
        background-color: #FFFFFF !important; border-color: var(--line) !important; color: var(--espresso) !important;
    }}
    .stApp [data-baseweb="select"] *, .stApp [data-testid="stNumberInput"] button {{ color: var(--espresso) !important; }}
    .stApp [data-testid="stNumberInput"] button {{ background-color: var(--linen-deep) !important; }}
    .stApp svg {{ fill: currentColor; }}

    /* Dropdown menus render in a portal outside .stApp */
    [data-baseweb="popover"], [data-baseweb="popover"] > div, [data-baseweb="menu"],
    [data-baseweb="popover"] ul {{ background-color: #FFFFFF !important; }}
    [data-baseweb="popover"] li, [data-baseweb="popover"] [role="option"] {{
        background-color: #FFFFFF !important; color: var(--espresso) !important;
    }}
    [data-baseweb="popover"] li:hover, [data-baseweb="popover"] [role="option"]:hover,
    [data-baseweb="popover"] [aria-selected="true"] {{ background-color: var(--linen-deep) !important; }}

    /* File uploader contents */
    .stApp [data-testid="stFileUploaderDropzone"] * {{ color: var(--espresso) !important; }}
    .stApp [data-testid="stFileUploaderDropzone"] button {{ background-color: var(--linen-deep) !important; }}
    .stApp [data-testid="stFileUploaderDropzone"] button * {{ color: var(--espresso) !important; }}

    /* White tables */
    .lb-table-wrap {{
        background: #FFFFFF; border: 1px solid var(--line); border-radius: 12px;
        overflow: auto; max-height: 420px;
    }}
    table.lb-table {{ width: 100%; border-collapse: collapse; background: #FFFFFF; font-size: 0.92rem; }}
    table.lb-table thead th {{
        position: sticky; top: 0; background: var(--linen-deep) !important; color: var(--espresso) !important;
        text-align: left; font-weight: 700; padding: 10px 14px; border-bottom: 1px solid var(--line); white-space: nowrap;
    }}
    table.lb-table tbody td {{
        background: #FFFFFF !important; color: var(--espresso) !important;
        padding: 10px 14px; border-bottom: 1px solid var(--line); text-align: left;
    }}
    table.lb-table tbody tr:last-child td {{ border-bottom: none; }}
    table.lb-table tbody tr:hover td {{ background: var(--linen) !important; }}
    .pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-weight: 700; font-size: 0.8rem; }}
    .pill.ok {{ background: #E3EBE5; color: #4F6656; }}
    .pill.bad {{ background: #F8DDD2; color: #A8431F; }}
    .pill.warn {{ background: #F3E6C9; color: #7A5A12; }}
</style>
""", unsafe_allow_html=True)


# ==========================================
# HELPERS
# ==========================================
def page_header(title: str, subtitle: str):
    st.header(title)
    st.markdown(f'<p class="lb-sub">{subtitle}</p>', unsafe_allow_html=True)


def summary_card(label: str, value: str, tone: str = "", note: str = ""):
    note_html = f'<div class="note">{note}</div>' if note else ""
    return f'<div class="lb-card {tone}"><div class="label">{label}</div><div class="value">{value}</div>{note_html}</div>'


PILL_CLASS = {"Profitable": "ok", "OK": "ok", "Low": "warn", "Out": "bad", "Loss": "bad"}


def show_table(df: pd.DataFrame, status_col: str = None):
    """Render a white, theme-proof HTML table (st.dataframe follows the browser's dark mode)."""
    df = df.copy().fillna("")
    for col in df.columns:
        if col != status_col:
            df[col] = df[col].astype(str).map(html.escape)
    if status_col:
        df[status_col] = df[status_col].map(
            lambda v: f'<span class="pill {PILL_CLASS.get(v, "bad")}">{html.escape(str(v))}</span>'
        )
    df.columns = [html.escape(str(c)) for c in df.columns]
    table = df.to_html(index=False, escape=False, border=0, classes="lb-table")
    st.markdown(f'<div class="lb-table-wrap">{table}</div>', unsafe_allow_html=True)


def _key(name):
    """Normalise names so 'Tomato ' and 'tomato' count as the same material."""
    return str(name if name is not None else "").strip().lower()


def _to_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _recent(rows, date_col, cols):
    """Newest first, and only columns that exist."""
    df = pd.DataFrame(rows)
    sort_cols = [c for c in (date_col, "created_at") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=False)
    return df[[c for c in cols if c in df.columns]]


def log_purchase(item_name, qty, unit, rate, vendor="Manual entry"):
    """Record a purchase AND its expense header, so the Dashboard's expenses stay in step with stock."""
    total = round(qty * rate, 2)
    purchase_id = None
    if total > 0:
        now = now_local()
        head = supabase.table("raw_material_purchases").insert({
            "vendor_name": vendor,
            "purchase_date": now.strftime("%Y-%m-%d"),
            "purchase_time": now.strftime("%H:%M:%S"),
            "total_amount": total,
            "payment_method": "Cash",
        }).execute()
        purchase_id = head.data[0]["id"] if head.data else None
    row = {"item_name": item_name, "quantity": qty, "unit": unit,
           "rate_per_unit": rate, "total_item_price": total}
    if purchase_id is not None:
        row["purchase_id"] = purchase_id
    supabase.table("purchase_line_items").insert(row).execute()


def _excel_safe(df):
    """openpyxl can't write dict/list cells (the raw_json columns), so store them as text."""
    df = df.copy()
    for c in df.columns:
        df[c] = df[c].map(lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
    return df


def _num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0.0)


def fetch_table(name):
    """Rows of a table, or None if it doesn't exist / can't be read."""
    try:
        return supabase.table(name).select("*").execute().data or []
    except Exception:
        return None


def compute_material_stats(df_raw: pd.DataFrame) -> pd.DataFrame:
    """One row per material: total bought, total spend and weighted-average cost per unit."""
    cols = ["key", "item_name", "unit", "purchased", "spend", "latest_rate", "avg_rate"]
    if df_raw is None or df_raw.empty or "item_name" not in df_raw.columns:
        return pd.DataFrame(columns=cols)

    d = df_raw.copy()
    if "created_at" in d.columns:
        d = d.sort_values("created_at", ascending=False)  # newest first
    d["key"] = d["item_name"].map(_key)
    d["qty"] = _num(d["quantity"]) if "quantity" in d.columns else 0.0
    d["rate"] = _num(d["rate_per_unit"]) if "rate_per_unit" in d.columns else 0.0
    total = _num(d["total_item_price"]) if "total_item_price" in d.columns else pd.Series(0.0, index=d.index)
    d["cost"] = total.where(total > 0, d["qty"] * d["rate"])
    if "unit" not in d.columns:
        d["unit"] = ""

    g = d.groupby("key", sort=False).agg(
        item_name=("item_name", "first"),
        unit=("unit", "first"),
        purchased=("qty", "sum"),
        spend=("cost", "sum"),
        latest_rate=("rate", "first"),
    ).reset_index()
    g["avg_rate"] = (g["spend"] / g["purchased"]).where(g["purchased"] > 0, g["latest_rate"])
    return g.sort_values("item_name").reset_index(drop=True)


def compute_inventory():
    """Stock on hand = everything bought - ingredients used by dish sales - manual usage."""
    info = {"sales_source": None, "unmatched": [], "adjustments_ok": True}
    stats = compute_material_stats(pd.DataFrame(fetch_table("purchase_line_items") or []))
    if stats.empty:
        return stats, info

    # Recipes: dish -> [(ingredient, qty per dish)]
    recipe_map = {}
    for r in fetch_table("dish_recipes") or []:
        recipe_map.setdefault(_key(r.get("dish_name")), []).append(
            (_key(r.get("ingredient_name")), float(r.get("quantity_required") or 0))
        )

    # Dish sales -> ingredient usage
    used_sales, unmatched = {}, set()
    for tbl in SALE_ITEM_TABLES:
        rows = fetch_table(tbl)
        if rows is None:
            continue
        info["sales_source"] = tbl
        for row in rows:
            dish = next((row[c] for c in DISH_COLS if row.get(c)), None)
            if not dish:
                continue
            qty = next((float(row[c]) for c in QTY_COLS if row.get(c) is not None), 1.0)
            recipe = recipe_map.get(_key(dish))
            if not recipe:
                unmatched.add(str(dish))
                continue
            for ing, per_dish in recipe:
                used_sales[ing] = used_sales.get(ing, 0.0) + per_dish * qty
        break
    info["unmatched"] = sorted(unmatched)

    # Manual usage (spoilage, staff meals, ...)
    used_manual = {}
    adjustments = fetch_table("inventory_adjustments")
    if adjustments is None:
        info["adjustments_ok"] = False
    else:
        for a in adjustments:
            k = _key(a.get("item_name"))
            used_manual[k] = used_manual.get(k, 0.0) + float(a.get("quantity_used") or 0)

    stats["used_sales"] = stats["key"].map(used_sales).fillna(0.0)
    stats["used_manual"] = stats["key"].map(used_manual).fillna(0.0)
    stats["in_stock"] = stats["purchased"] - stats["used_sales"] - stats["used_manual"]
    stats["stock_value"] = stats["in_stock"].clip(lower=0) * stats["avg_rate"]
    stats["status"] = stats.apply(
        lambda r: "Out" if r["in_stock"] <= 0
        else ("Low" if r["in_stock"] <= LOW_STOCK_RATIO * r["purchased"] else "OK"),
        axis=1,
    )
    return stats, info


# ==========================================
# BRAND HEADER + NAVIGATION
# ==========================================
if os.path.exists("logo.png"):
    col_logo, _ = st.columns([1, 3])
    col_logo.image("logo.png", width=220)
    st.markdown(f'<p class="lb-tagline">{TAGLINE}</p>', unsafe_allow_html=True)
else:
    st.markdown(
        f'<div class="lb-brand"><div class="lb-wordmark">Ledger<span>Bite</span></div>'
        f'<div class="lb-tagline">{TAGLINE}</div></div>',
        unsafe_allow_html=True,
    )

NAV_DASH = "Dashboard"
NAV_DISH = "Dishes & Recipes"
NAV_INV = "Inventory"
NAV_RAW = "Raw Materials"
NAV_UPLOAD = "Upload Receipt"
NAV_EXPORT = "Export"

menu = st.radio(
    "Navigation",
    [NAV_DASH, NAV_DISH, NAV_INV, NAV_RAW, NAV_UPLOAD, NAV_EXPORT],
    horizontal=True,
    label_visibility="collapsed",
)

# ==========================================
# 1. DASHBOARD
# ==========================================
if menu == NAV_DASH:
    page_header("Profit & loss", "Sales against raw material spend, all in one view.")

    try:
        raw_purchases = supabase.table("raw_material_purchases").select("*").execute().data or []
        customer_sales = supabase.table("customer_sales").select("*").execute().data or []

        total_expenses = sum(_to_float(x.get("total_amount")) for x in raw_purchases)
        # Revenue is the pre-GST subtotal: GST collected isn't yours to keep.
        total_revenue = sum(
            _to_float(x["subtotal"] if x.get("subtotal") is not None else x.get("total_amount"))
            for x in customer_sales
        )
        net_pl = total_revenue - total_expenses

        c1, c2, c3 = st.columns(3)
        c1.markdown(summary_card("Sales revenue", f"₹{total_revenue:,.2f}", note="Excluding GST"), unsafe_allow_html=True)
        c2.markdown(summary_card("Raw material expense", f"₹{total_expenses:,.2f}"), unsafe_allow_html=True)
        c3.markdown(
            summary_card(
                "Net profit",
                f"{'-' if net_pl < 0 else ''}₹{abs(net_pl):,.2f}",
                tone="profit" if net_pl >= 0 else "loss",
                note="You're in the green." if net_pl >= 0 else "Spending is ahead of sales.",
            ),
            unsafe_allow_html=True,
        )

        st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
        col_a, col_b = st.columns(2, gap="large")

        with col_a:
            st.subheader("Raw material purchases")
            if raw_purchases:
                show_table(_recent(raw_purchases, "purchase_date", ["purchase_date", "vendor_name", "total_amount", "payment_method"]))
            else:
                st.info("No purchases yet. Upload a supplier bill to log your first one.")

        with col_b:
            st.subheader("Customer sales")
            if customer_sales:
                show_table(_recent(customer_sales, "sale_date", ["sale_date", "table_or_order_no", "total_amount", "payment_method"]))
            else:
                st.info("No sales yet. Upload a sales order or voice note to log your first one.")

    except Exception as e:
        st.error(f"Couldn't load dashboard data: {e}")

# ==========================================
# 2. DISHES & RECIPES
# ==========================================
elif menu == NAV_DISH:
    page_header("Dishes & recipes", "See what each dish costs to make and what it earns you.")

    try:
        recipes = supabase.table("dish_recipes").select("*").execute().data or []
        raw_items = supabase.table("purchase_line_items").select("*").execute().data or []

        df_recipes = pd.DataFrame(recipes) if recipes else pd.DataFrame()
        df_raw = pd.DataFrame(raw_items) if raw_items else pd.DataFrame()

        mat_stats = compute_material_stats(df_raw)
        rate_map = dict(zip(mat_stats["key"], mat_stats["avg_rate"])) if not mat_stats.empty else {}
        available_materials = mat_stats["item_name"].tolist() if not mat_stats.empty else ["Tomato", "Cheese", "Flour"]

        if not df_recipes.empty:
            # --- OVERVIEW ---
            st.subheader("Profitability by dish")
            dish_summaries = []
            for dish, group in df_recipes.groupby("dish_name"):
                selling_p = _to_float(group.iloc[0]["selling_price"])
                cost_price = sum(
                    _to_float(r["quantity_required"]) * rate_map.get(_key(r["ingredient_name"]), 0.0)
                    for _, r in group.iterrows()
                )
                margin = selling_p - cost_price
                dish_summaries.append({
                    "Dish": dish,
                    "Selling price": f"₹{selling_p:.2f}",
                    "Ingredient cost": f"₹{cost_price:.2f}",
                    "Profit per dish": f"₹{margin:.2f}",
                    "Status": "Profitable" if margin >= 0 else "Loss",
                })

            show_table(pd.DataFrame(dish_summaries), status_col="Status")

            # --- BREAKDOWN ---
            st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
            st.subheader("Ingredient breakdown")
            dishes_list = df_recipes["dish_name"].unique().tolist()
            selected_dish_inspect = st.selectbox("Choose a dish", dishes_list, key="inspect_dish_select")

            dish_recipe_df = df_recipes[df_recipes["dish_name"] == selected_dish_inspect].copy()
            dish_recipe_df["Avg rate per unit (₹)"] = dish_recipe_df["ingredient_name"].map(lambda x: rate_map.get(_key(x), 0.0))
            dish_recipe_df["Cost (₹)"] = _num(dish_recipe_df["quantity_required"]) * dish_recipe_df["Avg rate per unit (₹)"]

            display_cols = dish_recipe_df[
                ["ingredient_name", "quantity_required", "unit", "Avg rate per unit (₹)", "Cost (₹)"]
            ].rename(columns={"ingredient_name": "Ingredient", "quantity_required": "Quantity", "unit": "Unit"})
            show_table(display_cols)
            st.info(f"Total ingredient cost for {selected_dish_inspect}: ₹{dish_recipe_df['Cost (₹)'].sum():.2f}")
            st.markdown("---")
        else:
            dishes_list = []
            st.info("No dishes yet. Add your first dish below.")

        # --- OPERATIONS ---
        st.subheader("Manage dishes")
        tab_add, tab_add_ing, tab_edit, tab_delete = st.tabs(
            ["Add dish", "Add ingredient", "Edit price", "Delete dish"]
        )

        with tab_add:
            with st.form("add_dish_form"):
                new_dish_name = st.text_input("Dish name")
                new_selling_price = st.number_input("Selling price (₹)", min_value=0.0, step=10.0)
                ing_name = st.selectbox("First ingredient", available_materials)
                ing_qty = st.number_input("Quantity required", min_value=0.01, step=0.05, value=0.1)
                ing_unit = st.text_input("Unit", value="kg")
                submit_add = st.form_submit_button("Create dish")

                if submit_add and not new_dish_name.strip():
                    st.warning("Enter a dish name.")
                elif submit_add and _key(new_dish_name) in {_key(d) for d in dishes_list}:
                    st.warning(f"'{new_dish_name.strip()}' already exists. Use Add ingredient or Edit price.")
                elif submit_add:
                    new_dish_name = new_dish_name.strip()
                    supabase.table("dish_recipes").insert({
                        "dish_name": new_dish_name,
                        "selling_price": new_selling_price,
                        "ingredient_name": ing_name,
                        "quantity_required": ing_qty,
                        "unit": ing_unit,
                    }).execute()
                    st.toast(f"Created '{new_dish_name}'. Add more ingredients in the Add ingredient tab.")
                    st.rerun()

        with tab_add_ing:
            if dishes_list:
                with st.form("add_more_ingredients_form"):
                    target_dish = st.selectbox("Dish", dishes_list, key="target_dish_add_ing")
                    target_selling_price = _to_float(
                        df_recipes[df_recipes["dish_name"] == target_dish].iloc[0]["selling_price"]
                    )
                    new_ing_name = st.selectbox("Ingredient", available_materials, key="new_ing_select")
                    new_ing_qty = st.number_input("Quantity required", min_value=0.01, step=0.05, value=0.1, key="new_ing_qty")
                    new_ing_unit = st.text_input("Unit", value="kg", key="new_ing_unit")
                    submit_ing_add = st.form_submit_button("Add ingredient")

                    already = set(df_recipes.loc[df_recipes["dish_name"] == target_dish, "ingredient_name"].map(_key))
                    if submit_ing_add and _key(new_ing_name) in already:
                        st.warning(f"{new_ing_name} is already in {target_dish}.")
                    elif submit_ing_add:
                        supabase.table("dish_recipes").insert({
                            "dish_name": target_dish,
                            "selling_price": target_selling_price,
                            "ingredient_name": new_ing_name,
                            "quantity_required": new_ing_qty,
                            "unit": new_ing_unit,
                        }).execute()
                        st.toast(f"Added {new_ing_qty} {new_ing_unit} of {new_ing_name} to {target_dish}.")
                        st.rerun()
            else:
                st.info("Create a dish first in the Add dish tab.")

        with tab_edit:
            if dishes_list:
                selected_edit_dish = st.selectbox("Dish", dishes_list, key="edit_dish_sel")
                current_price = _to_float(
                    df_recipes.loc[df_recipes["dish_name"] == selected_edit_dish, "selling_price"].iloc[0]
                )
                updated_price = st.number_input(
                    "New selling price (₹)", min_value=0.0, step=10.0, value=current_price,
                    key=f"edit_dish_price_{selected_edit_dish}",
                )
                if st.button("Save price"):
                    supabase.table("dish_recipes").update({"selling_price": updated_price}).eq("dish_name", selected_edit_dish).execute()
                    st.toast(f"Selling price for {selected_edit_dish} is now ₹{updated_price:.2f}.")
                    st.rerun()
            else:
                st.info("No dishes to edit yet.")

        with tab_delete:
            if dishes_list:
                selected_del_dish = st.selectbox("Dish", dishes_list, key="del_dish_sel")
                confirm_dish = st.checkbox(f"Yes, delete {selected_del_dish} and its whole recipe", key=f"confirm_del_{selected_del_dish}")
                if st.button("Delete dish", disabled=not confirm_dish):
                    supabase.table("dish_recipes").delete().eq("dish_name", selected_del_dish).execute()
                    st.toast(f"Deleted {selected_del_dish}.")
                    st.rerun()
            else:
                st.info("No dishes to delete yet.")

    except Exception as e:
        st.error(f"Couldn't load dishes: {e}")

# ==========================================
# 3. INVENTORY
# ==========================================
elif menu == NAV_INV:
    page_header("Inventory", "Stock on hand for every raw material: what you bought, minus what you've used.")

    try:
        inv, info = compute_inventory()

        if inv.empty:
            st.info("No raw materials yet. Upload a supplier bill or add a material in Raw Materials.")
        else:
            attention = int((inv["status"] != "OK").sum())
            c1, c2, c3 = st.columns(3)
            c1.markdown(summary_card("Materials tracked", f"{len(inv)}"), unsafe_allow_html=True)
            c2.markdown(summary_card("Stock value", f"₹{inv['stock_value'].sum():,.2f}", note="At average purchase cost"), unsafe_allow_html=True)
            c3.markdown(
                summary_card(
                    "Needs attention", f"{attention}",
                    tone="loss" if attention else "profit",
                    note="Low or out of stock" if attention else "Everything is stocked",
                ),
                unsafe_allow_html=True,
            )

            st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
            st.subheader("Stock on hand")
            view = pd.DataFrame({
                "Material": inv["item_name"],
                "Unit": inv["unit"],
                "In stock": inv["in_stock"].map(lambda x: f"{x:,.2f}"),
                "Total bought": inv["purchased"].map(lambda x: f"{x:,.2f}"),
                "Used in sales": inv["used_sales"].map(lambda x: f"{x:,.2f}"),
                "Other usage": inv["used_manual"].map(lambda x: f"{x:,.2f}"),
                "Avg cost per unit (₹)": inv["avg_rate"].map(lambda x: f"₹{x:,.2f}"),
                "Stock value (₹)": inv["stock_value"].map(lambda x: f"₹{x:,.2f}"),
                "Status": inv["status"],
            })
            show_table(view, status_col="Status")

            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
            if info["sales_source"]:
                st.info(f"Each dish sale in `{info['sales_source']}` removes its recipe ingredients from stock automatically.")
            else:
                st.warning(
                    "Automatic deduction from sales is off because no sold-dish table was found. "
                    "Stock currently only drops when you record usage below."
                )
            if info["unmatched"]:
                st.warning("Sold dishes with no recipe (their ingredients aren't deducted): " + ", ".join(info["unmatched"]))

            st.markdown("---")
            st.subheader("Record other usage")
            tab_use, tab_log = st.tabs(["Record usage", "Usage log"])

            with tab_use:
                if not info["adjustments_ok"]:
                    st.warning("Run `inventory_setup.sql` in the Supabase SQL editor once to turn on manual usage tracking.")
                else:
                    with st.form("inv_usage_form"):
                        use_item = st.selectbox("Material", inv["item_name"].tolist())
                        use_qty = st.number_input("Quantity used", min_value=0.01, step=0.1, value=1.0)
                        use_reason = st.selectbox("Reason", ["Spoilage or waste", "Staff meal", "Sampling or testing", "Stock count correction"])
                        submit_use = st.form_submit_button("Deduct from stock")
                        if submit_use:
                            supabase.table("inventory_adjustments").insert({
                                "item_name": use_item, "quantity_used": use_qty, "reason": use_reason,
                            }).execute()
                            st.toast(f"Deducted {use_qty:g} of {use_item}.")
                            st.rerun()

            with tab_log:
                log = fetch_table("inventory_adjustments")
                if log:
                    df_log = pd.DataFrame(log)
                    if "created_at" in df_log.columns:
                        df_log = df_log.sort_values("created_at", ascending=False)
                        df_log["created_at"] = df_log["created_at"].astype(str).str[:16].str.replace("T", " ")
                    cols = [c for c in ["created_at", "item_name", "quantity_used", "reason"] if c in df_log.columns]
                    show_table(df_log[cols].head(50).rename(columns={
                        "created_at": "When", "item_name": "Material", "quantity_used": "Quantity", "reason": "Reason"}))
                else:
                    st.info("Nothing recorded yet.")

    except Exception as e:
        st.error(f"Couldn't load inventory: {e}")

# ==========================================
# 4. RAW MATERIALS
# ==========================================
elif menu == NAV_RAW:
    page_header("Raw materials", "Average cost per unit across everything you've bought. Dish costs use these rates.")

    try:
        raw_items = supabase.table("purchase_line_items").select("*").order("created_at", desc=True).execute().data or []
        stats = compute_material_stats(pd.DataFrame(raw_items))

        if not stats.empty:
            st.subheader("Average rates")
            df_display = pd.DataFrame({
                "Material": stats["item_name"],
                "Unit": stats["unit"],
                "Total bought": stats["purchased"].map(lambda x: f"{x:,.2f}"),
                "Avg rate per unit (₹)": stats["avg_rate"].map(lambda x: f"₹{x:,.2f}"),
                "Latest price (₹)": stats["latest_rate"].map(lambda x: f"₹{x:,.2f}"),
            })
            show_table(df_display)
            st.caption("Average rate = total spent on a material divided by total quantity bought. Every new bill or purchase updates it.")

            st.markdown("---")
            st.subheader("Manage materials")
            tab_rm_edit, tab_rm_buy, tab_rm_add, tab_rm_del = st.tabs(["Update rate", "Log purchase", "Add material", "Delete material"])

            with tab_rm_edit:
                item_to_edit = st.selectbox("Material", stats["item_name"].tolist(), key="edit_rm_select")
                sel = stats[stats["item_name"] == item_to_edit].iloc[0]
                new_rate = st.number_input(
                    f"New rate per {sel['unit']} (₹)", min_value=0.0, value=float(sel["avg_rate"]),
                    step=1.0, key=f"edit_rm_rate_{item_to_edit}",
                )
                st.caption(
                    "Sets this rate on every past purchase of the material, so the average becomes this price. "
                    "To keep your purchase history and average, use Log purchase instead."
                )
                if st.button("Save rate"):
                    for r in raw_items:
                        if _key(r.get("item_name")) != _key(item_to_edit):
                            continue
                        upd = {"rate_per_unit": new_rate}
                        if r.get("quantity") is not None:
                            upd["total_item_price"] = round(float(r["quantity"] or 0) * new_rate, 2)
                        q = supabase.table("purchase_line_items").update(upd)
                        if r.get("id") is not None:
                            q = q.eq("id", r["id"])
                        else:
                            q = q.eq("item_name", r["item_name"])
                            if r.get("created_at"):
                                q = q.eq("created_at", r["created_at"])
                        q.execute()
                    st.toast(f"{item_to_edit} is now ₹{new_rate:,.2f} per {sel['unit']}.")
                    st.rerun()

            with tab_rm_buy:
                with st.form("log_purchase_form"):
                    buy_item = st.selectbox("Material", stats["item_name"].tolist(), key="buy_rm_select")
                    buy_qty = st.number_input("Quantity bought", min_value=0.01, step=0.5, value=1.0)
                    buy_rate = st.number_input("Price per unit (₹)", min_value=0.0, step=1.0, value=0.0)
                    submit_buy = st.form_submit_button("Log purchase")
                    if submit_buy and buy_rate <= 0:
                        st.warning("Enter the price you paid per unit. A ₹0 purchase would drag the average down.")
                    elif submit_buy:
                        unit = stats.loc[stats["item_name"] == buy_item, "unit"].iloc[0]
                        log_purchase(buy_item, buy_qty, unit, buy_rate)
                        st.toast(f"Logged {buy_qty:g} {unit} of {buy_item}. Average rate and stock updated.")
                        st.rerun()

            with tab_rm_add:
                with st.form("add_rm_form"):
                    rm_name = st.text_input("Material name")
                    rm_unit = st.text_input("Unit (kg, packet, litre)", value="kg")
                    rm_qty = st.number_input("Quantity in stock now", min_value=0.0, step=0.5, value=0.0,
                                             help="Leave at 0 to just set a starting price.")
                    rm_rate = st.number_input("Price per unit (₹)", min_value=0.0, value=50.0)
                    submit_rm = st.form_submit_button("Add material")

                    if submit_rm and not rm_name.strip():
                        st.warning("Enter a material name.")
                    elif submit_rm and _key(rm_name) in set(stats["key"]):
                        st.warning(f"{rm_name.strip()} already exists. Use Log purchase to add stock.")
                    elif submit_rm:
                        rm_name = rm_name.strip()
                        log_purchase(rm_name, rm_qty, rm_unit.strip() or "kg", rm_rate)
                        st.toast(f"Added {rm_name}.")
                        st.rerun()

            with tab_rm_del:
                item_to_del = st.selectbox("Material", stats["item_name"].tolist(), key="del_rm_select")
                confirm_rm = st.checkbox(f"Yes, delete {item_to_del} and its purchase history", key=f"confirm_rm_{item_to_del}")
                if st.button("Delete material", disabled=not confirm_rm):
                    # match on the normalised name so 'Tomato ' and 'tomato' rows go too
                    for r in raw_items:
                        if _key(r.get("item_name")) != _key(item_to_del):
                            continue
                        q = supabase.table("purchase_line_items").delete()
                        q = q.eq("id", r["id"]) if r.get("id") is not None else q.eq("item_name", r["item_name"])
                        q.execute()
                    st.toast(f"Deleted {item_to_del}.")
                    st.rerun()
        else:
            st.warning("No raw materials yet. Run `python seed_raw_materials.py` to load your starting list.")

    except Exception as e:
        st.error(f"Couldn't load raw materials: {e}")

# ==========================================
# 5. UPLOAD RECEIPT
# ==========================================
elif menu == NAV_UPLOAD:
    page_header("Upload receipt", "Snap a bill or record a voice note. LedgerBite reads it, you check it, then it's logged.")

    saved_msg = st.session_state.pop("last_saved", None)
    if saved_msg:
        st.success(saved_msg)

    with st.expander("Connection check (use this if reading a receipt fails)"):
        import importlib.metadata as _md
        try:
            _sdk = _md.version("google-genai")
        except Exception:
            _sdk = "unknown"
        st.caption(
            f"google-genai {_sdk} · key starts with `{GEMINI_API_KEY[:3]}` and is {len(GEMINI_API_KEY)} characters long · "
            f"route: {'Vertex AI' if USE_VERTEX else 'Gemini API'} · model: {MODELS[0]}"
        )
        if st.button("Test Gemini connection"):
            results = []
            for _m in MODELS:
                try:
                    gemini.models.generate_content(model=_m, contents="Reply with the single word OK")
                    results.append((_m, None))
                except Exception as e:
                    results.append((_m, str(e)[:300]))
            for _m, _err in results:
                if _err is None:
                    st.success(f"{_m}: works.")
                elif "503" in _err or "UNAVAILABLE" in _err:
                    st.warning(f"{_m}: Google is busy right now (temporary). Your key is fine. Try again in a minute.")
                else:
                    st.error(f"{_m}: {_err}")

    recipe_type = st.selectbox(
        "What are you logging?",
        ["Raw Materials (Expense / Supplier Bill)", "Dishes Served (Revenue / Sales Order)"],
    )
    category = "Raw Material (Expense)" if "Raw Materials" in recipe_type else "Customer Sale (Revenue)"

    uploaded_file = st.file_uploader("Receipt image or voice note", type=["png", "jpg", "jpeg", "webp", "mp3", "wav", "m4a", "aac", "ogg", "flac"])

    if uploaded_file is None:
        st.session_state.pop("pending_entry", None)
    else:
        file_ext = os.path.splitext(uploaded_file.name)[1].lower().lstrip(".")
        is_audio = file_ext in ("mp3", "wav", "m4a", "aac", "ogg", "flac")
        file_sig = f"{uploaded_file.name}:{uploaded_file.size}:{category}"

        if st.button("Read entry"):
            with st.spinner("Reading your entry..."):
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(suffix=f".{file_ext}", delete=False) as tmp:
                        tmp.write(uploaded_file.getbuffer())
                        tmp_path = tmp.name
                    data, warnings = extract_receipt(tmp_path, category, is_audio)
                    st.session_state["pending_entry"] = {"sig": file_sig, "data": data, "warnings": warnings}
                except Exception as e:
                    st.session_state.pop("pending_entry", None)
                    st.error(f"Couldn't read this entry: {e}")
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.remove(tmp_path)

        pending = st.session_state.get("pending_entry")
        if pending and pending["sig"] == file_sig:
            data, warnings = pending["data"], pending["warnings"]
            is_sale = data["receipt_type"] == "CUSTOMER_SALE"

            st.subheader("Check before saving")
            c1, c2, c3 = st.columns(3)
            c1.markdown(summary_card("Type", "Sale" if is_sale else "Purchase", note=f"{data['vendor_or_order']} · {data['date']}"), unsafe_allow_html=True)
            c2.markdown(summary_card("Subtotal", f"₹{data['subtotal']:,.2f}", note=f"GST ₹{data['tax_amount']:,.2f}"), unsafe_allow_html=True)
            c3.markdown(summary_card("Total", f"₹{data['grand_total']:,.2f}", note=data["payment_method"]), unsafe_allow_html=True)

            st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
            if data["items"]:
                show_table(pd.DataFrame([{
                    "Item": i["name"], "Qty": f"{i['quantity']:g}", "Unit": i["unit"],
                    "Price each (₹)": f"{i['rate_or_price']:,.2f}", "Line total (₹)": f"{i['line_total']:,.2f}",
                } for i in data["items"]]))

            for w in warnings:
                (st.error if "duplicate" in w else st.warning)(w)

            duplicate = bool(data.get("duplicate"))
            label = "Save anyway" if warnings else "Save entry"
            if st.button(label, disabled=duplicate or data["grand_total"] <= 0):
                try:
                    save_receipt(data)
                    st.session_state.pop("pending_entry", None)
                    st.session_state["last_saved"] = f"Saved {data['vendor_or_order']} (₹{data['grand_total']:,.2f}) as {'a sale' if is_sale else 'a purchase'}."
                    st.rerun()
                except Exception as e:
                    st.error(f"Couldn't save: {e}")

# ==========================================
# 6. EXPORT
# ==========================================
elif menu == NAV_EXPORT:
    page_header("Export", "Download your full ledger as an Excel file.")

    try:
        raw_p = supabase.table("raw_material_purchases").select("*").execute().data or []
        sales_p = supabase.table("customer_sales").select("*").execute().data or []
        items_p = supabase.table("purchase_line_items").select("*").execute().data or []
        sale_items = []
        for tbl in SALE_ITEM_TABLES:
            rows = fetch_table(tbl)
            if rows is not None:
                sale_items = rows
                break

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            _excel_safe(pd.DataFrame(raw_p)).to_excel(writer, sheet_name="Raw_Material_Purchases", index=False)
            _excel_safe(pd.DataFrame(sales_p)).to_excel(writer, sheet_name="Customer_Sales", index=False)
            _excel_safe(pd.DataFrame(items_p)).to_excel(writer, sheet_name="Raw_Material_Line_Items", index=False)
            _excel_safe(pd.DataFrame(sale_items)).to_excel(writer, sheet_name="Sales_Line_Items", index=False)
            inv_x, _ = compute_inventory()
            if not inv_x.empty:
                inv_x.drop(columns=["key"]).rename(columns={
                    "item_name": "Material", "unit": "Unit", "purchased": "Total bought", "spend": "Total spend",
                    "latest_rate": "Latest price", "avg_rate": "Avg cost per unit", "used_sales": "Used in sales",
                    "used_manual": "Other usage", "in_stock": "In stock", "stock_value": "Stock value", "status": "Status",
                }).to_excel(writer, sheet_name="Inventory", index=False)

        st.download_button(
            label="Download ledger (Excel)",
            data=buffer.getvalue(),
            file_name="ledgerbite_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.error(f"Couldn't create the export: {e}")