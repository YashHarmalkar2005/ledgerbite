"""Shared command-line runner for the small one-file scripts."""
import json
import sys


def run(default_file: str, category: str, is_audio: bool = False) -> None:
    from parse_receipts import process_receipt
    path = sys.argv[1] if len(sys.argv) > 1 else default_file
    try:
        data = process_receipt(path, category, is_audio=is_audio)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    for w in data.get("warnings", []):
        print(f"⚠️  {w}")
    if data.get("saved"):
        print(f"\n✅ Saved as {data['receipt_type']} ({len(data['items'])} items, total ₹{data['grand_total']:,.2f})")
    else:
        print("\n⏭️  Not saved: this looks like a duplicate of an existing entry.")
    print(json.dumps({k: v for k, v in data.items() if k != "warnings"}, indent=2, default=str))
