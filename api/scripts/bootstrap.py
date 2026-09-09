"""Create the food_items collection (blue/green) and seed it.

Usage: python scripts/bootstrap.py   (from api/, with .env present and Typesense up)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.pipeline import rebuild  # noqa: E402

SEED = Path(__file__).resolve().parents[1] / "data" / "seed" / "items.json"

if __name__ == "__main__":
    report = rebuild(SEED)
    print(f"food_items_v{report['version']}: {report['imported']} docs imported")
    if report["failed"]:
        print("FAILURES:")
        for f in report["failed"]:
            print(" ", f)
        sys.exit(1)
