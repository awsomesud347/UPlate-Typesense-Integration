"""Campus slang -> menu vocabulary, via Typesense synonym sets.

Students don't search the words on a menu board. They search "gains," "brain
food," "the peanut butter burger." Synonyms are applied by Typesense at query
time, so they cost nothing at index time and need no reindex to change.

GOTCHA: the synonyms API changed between major versions, in both directions.
v30+ REMOVED per-collection synonyms (collections/{c}/synonyms) in favour of
top-level synonym sets. v29 is the opposite: per-collection works, and
/synonym_sets does not exist and 404s.

We are pinned to 29.1 on purpose — v30.0-30.2 have an open NL-search regression
that returns 0 hits (Backend_Architecture.MD §10.1) — so this module uses the
per-collection API. The python client exposes both surfaces regardless of what
the server supports, so a wrong call fails at runtime, not at import.

Synonyms live on a concrete collection, not on an alias, so they must be
re-registered after every blue/green swap. bootstrap.py and reindex.py both do.

Multi-way (`synonyms` only): any term matches all the others.
One-way (`root` + `synonyms`): searching the root also matches the synonyms,
not the reverse.
"""

from app.typesense.schema import COLLECTION_ALIAS

SET_NAME = "uplate_slang"

SYNONYM_ITEMS: list[dict] = [
    # --- multi-way: any term finds the others ---
    {"id": "protein-slang", "synonyms": ["gains", "protein", "swole", "bulking"]},
    {"id": "warm-slang", "synonyms": ["warm", "hot", "cozy", "comforting"]},
    {"id": "light-slang", "synonyms": ["light", "small", "snack", "lite"]},
    {"id": "sick-slang", "synonyms": ["sick", "under the weather", "soup", "broth"]},
    {"id": "veg-slang", "synonyms": ["veggie", "vegetarian", "plant based", "meatless"]},
    # --- one-way: root also matches these, not vice versa ---
    {
        "id": "brain-food",
        "root": "brain food",
        "synonyms": ["oatmeal", "salmon", "lentil", "whole grain"],
    },
    {
        "id": "pb-burger",
        "root": "peanut butter burger",
        "synonyms": ["duane purvis", "triple xxx", "all-american"],
    },
    {
        "id": "post-gym",
        "root": "post workout",
        "synonyms": ["chicken", "salmon", "protein bowl", "eggs"],
    },
    {
        "id": "hangover",
        "root": "hungover",
        "synonyms": ["breakfast", "eggs", "greasy", "toast"],
    },
]


def register_synonyms(client, collection: str | None = None) -> int:
    """Idempotent — each upsert replaces that synonym by id. Returns item count.

    Defaults to whatever the `food_items` alias currently points at, so it lands
    on the live collection after a blue/green swap.
    """
    if collection is None:
        collection = client.aliases[COLLECTION_ALIAS].retrieve()["collection_name"]

    for item in SYNONYM_ITEMS:
        body = {k: v for k, v in item.items() if k != "id"}
        client.collections[collection].synonyms.upsert(item["id"], body)
    return len(SYNONYM_ITEMS)
