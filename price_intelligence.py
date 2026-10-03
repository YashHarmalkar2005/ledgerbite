"""Flag raw materials whose latest purchase price jumped above their historical average."""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
SUPABASE_KEY = (os.getenv("SUPABASE_KEY") or "").strip()
if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("SUPABASE_URL or SUPABASE_KEY missing from .env")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def analyze_price_trends_and_margins(threshold_pct=10.0):
    print("🔍 Analyzing commodity price trends across past purchases...\n")

    # purchase_line_items is the table the app writes to. Oldest first, so the last record is the latest price.
    items = supabase.table("purchase_line_items").select("*").order("created_at").execute().data or []
    if not items:
        print("ℹ️ No purchases found to analyse.")
        return []

    history = {}
    for item in items:
        name = str(item.get("item_name") or "").strip()
        rate, qty = _f(item.get("rate_per_unit")), _f(item.get("quantity"))
        if not name or rate <= 0 or qty <= 0:   # qty 0 = a starting price, not a real purchase
            continue
        entry = history.setdefault(name.lower(), {"name": name.title(), "unit": item.get("unit") or "unit", "rates": []})
        entry["rates"].append(rate)

    alerts = []
    print("📊 COMMODITY PRICE ANALYSIS:")
    print("-" * 55)
    for data in sorted(history.values(), key=lambda d: d["name"]):
        name, unit, rates = data["name"], data["unit"], data["rates"]
        if len(rates) < 2:
            print(f"• {name}: Latest rate ₹{rates[-1]:.2f}/{unit} (baseline established)")
            continue
        latest, avg = rates[-1], sum(rates[:-1]) / len(rates[:-1])
        diff_pct = (latest - avg) / avg * 100
        print(f"• {name}: Latest ₹{latest:.2f}/{unit} | Avg ₹{avg:.2f}/{unit} | Var: {diff_pct:+.1f}%")
        if diff_pct >= threshold_pct:
            alerts.append({
                "item": name, "latest_rate": latest, "avg_rate": round(avg, 2), "diff_pct": round(diff_pct, 1),
                "alert": f"🚨 PRICE SPIKE: {name} is up {diff_pct:.1f}% (₹{latest:.2f}/{unit} vs average ₹{avg:.2f}/{unit}).",
            })
    print("-" * 55)

    if alerts:
        print("\n📲 ALERTS:")
        for a in alerts:
            print(f"  - {a['alert']}")
    else:
        print("\n✅ All commodity prices are within the safe range.")
    return alerts


if __name__ == "__main__":
    analyze_price_trends_and_margins()
