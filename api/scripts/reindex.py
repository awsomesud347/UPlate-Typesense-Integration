"""Blue/green rebuild + alias swap. Safe to run while the API serves traffic:
the new version is built on the side and the alias flips atomically.

Usage: python scripts/reindex.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingest.pipeline import rebuild  # noqa: E402
from app.typesense.client import admin_client  # noqa: E402
from app.typesense.synonyms import register_synonyms  # noqa: E402

SEED = Path(__file__).resolve().parents[1] / "data" / "seed" / "items.json"

if __name__ == "__main__":
    report = rebuild(SEED)
    print(
        f"swapped alias -> food_items_v{report['version']} "
        f"({report['imported']} docs)"
    )
    if report["failed"]:
        print(f"REJECTED {len(report['failed'])} docs:")
        for f in report["failed"]:
            print(" ", f)
        sys.exit(1)

    # Synonyms live on the collection, so they must be re-registered after a swap.
    print(f"synonyms registered: {register_synonyms(admin_client())}")
