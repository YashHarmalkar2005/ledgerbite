"""Any receipt image -> saved entry (type is auto-detected).
Usage: python save_to_ledger.py path/to/receipt.png
"""
from _cli import run

if __name__ == "__main__":
    run("Restaurant-Receipt.png", "Auto-Detect")
