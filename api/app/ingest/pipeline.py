"""Blue/green index pipeline. Never mutate a live collection in place:
1. create food_items_v{N+1}
2. bulk import
3. upsert alias 'food_items' -> v{N+1}
4. drop older versions, keeping one for rollback
"""
import json
from pathlib import Path

from app.ingest.normalize import normalize
from app.typesense.client import admin_client
from app.typesense.schema import COLLECTION_ALIAS, food_items_schema


def _live_version(ts) -> int:
    try:
        alias = ts.aliases[COLLECTION_ALIAS].retrieve()
        return int(alias["collection_name"].rsplit("_v", 1)[1])
    except Exception:
        return 0


def rebuild(seed_path: Path) -> dict:
    ts = admin_client()
    current = _live_version(ts)
    next_v = current + 1
    schema = food_items_schema(next_v)

    raw_items = json.loads(seed_path.read_text(encoding="utf-8"))
    docs = [normalize(r) for r in raw_items]  # raises before touching Typesense

    ts.collections.create(schema)
    results = ts.collections[schema["name"]].documents.import_(docs, {"action": "upsert"})
    failures = [r for r in results if not r.get("success")]

    ts.aliases.upsert(COLLECTION_ALIAS, {"collection_name": schema["name"]})

    # keep one previous version for rollback, drop anything older
    for v in range(1, current):
        try:
            ts.collections[f"food_items_v{v}"].delete()
        except Exception:
            pass

    return {"version": next_v, "imported": len(docs) - len(failures), "failed": failures}
