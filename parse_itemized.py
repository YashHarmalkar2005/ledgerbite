"""Supplier bill (image) -> raw_material_purchases + purchase_line_items.
Usage: python parse_itemized.py path/to/bill.png
"""
from _cli import run

if __name__ == "__main__":
    run("Restaurant-Receipt.png", "Raw Material (Expense)")
