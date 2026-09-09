"""Campus slang -> menu vocabulary, via Typesense synonym sets.

Students don't search the words on a menu board. They search "gains," "brain
food," "the peanut butter burger." Synonyms are applied by Typesense at query
time, so they cost nothing at index time and need no reindex to change.

GOTCHA: the per-collection synonyms API (collections/{c}/synonyms) is REMOVED
in Typesense v30+ — it 404s. v30 uses top-level SYNONYM SETS, created once and
referenced from a search via the `synonym_sets` query parameter. Most tutorials
and LLM training data still show the old API.

Multi-way (`synonyms` only): any term matches all the others.
One-way (`root` + `synonyms`): searching the root also matches the synonyms,
not the reverse.
"""

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


def register_synonyms(client) -> int:
    """Idempotent — upsert replaces the whole set by name. Returns item count."""
    client.synonym_sets[SET_NAME].upsert({"items": SYNONYM_ITEMS})
    return len(SYNONYM_ITEMS)
