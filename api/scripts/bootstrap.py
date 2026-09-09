"""Create the food_items collection (blue/green) and seed it.

Usage: python scripts/bootstrap.py   (from api/, with .env present and Typesense up)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.pipeline import rebuild  # noqa: E402
from app.typesense.client import admin_client  # noqa: E402
from app.typesense.nl_model import ensure_model  # noqa: E402
from app.typesense.synonyms import register_synonyms  # noqa: E402

SEED = Path(__file__).resolve().parents[1] / "data" / "seed" / "items.json"

if __name__ == "__main__":
    report = rebuild(SEED)
    print(f"food_items_v{report['version']}: {report['imported']} docs imported")
    if report["failed"]:
        print("FAILURES:")
        for f in report["failed"]:
            print(" ", f)
        sys.exit(1)

    n = register_synonyms(admin_client())
    print(f"synonyms registered: {n}")

    # Non-fatal: without a key the search path degrades to keyword, which is a
    # worse demo but a working one. Failing the whole seed here would be worse.
    try:
        print(f"NL search model registered: {ensure_model(admin_client())}")
    except Exception as exc:
        print(f"NL search model NOT registered ({exc}) - search will degrade to keyword")
