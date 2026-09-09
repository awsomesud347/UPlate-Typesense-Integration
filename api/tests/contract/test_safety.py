"""The most important suite in the repo.

Hard exclusions ride the explicit filter_by, which Typesense ANDs on top of
anything the interpretation layer contributes. These tests assert that property
against a REAL seeded index, because mocking Typesense would test nothing.

Run: python scripts/bootstrap.py first.
"""
import pytest

from app.schemas.search import UserContext
from app.typesense.client import admin_client
from app.typesense.query_builder import build_filter_by, build_search_request


def _seeded() -> bool:
    try:
        c = admin_client()
        return c.operations.is_healthy() and c.collections["food_items"].retrieve()[
            "num_documents"
        ] > 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _seeded(), reason="Typesense not running or not seeded (run bootstrap.py)"
)


def ctx(**kw) -> UserContext:
    base = dict(
        lat=40.4249,
        lng=-86.9111,
        campus_id="purdue",
        now_minutes=720,
        exclude_allergens=[],
        diet_flags=[],
        goal="none",
        radius_mi=5.0,
    )
    base.update(kw)
    return UserContext(**base)


def run(query: str, c: UserContext) -> tuple[list[dict], int]:
    """Returns (documents, withheld_count)."""
    res = admin_client().multi_search.perform(build_search_request(query, c), {})
    gated, ungated = res["results"][0], res["results"][1]
    assert "error" not in gated, gated.get("error")
    docs = [h["document"] for h in gated.get("hits", [])]
    return docs, max(ungated.get("found", 0) - gated.get("found", 0), 0)


PHRASINGS = [
    "food", "something to eat", "lunch", "dinner", "protein", "warm food",
    "snack", "cheap eats", "healthy", "dessert", "cookie", "peanut butter",
    "nuts", "burger", "sandwich", "bowl", "soup", "chicken", "anything", "*",
]


@pytest.mark.parametrize("query", PHRASINGS)
def test_peanut_never_leaks(query):
    """No phrasing of any query surfaces a peanut item when peanuts are excluded."""
    docs, _ = run(query, ctx(exclude_allergens=["peanut"]))
    for d in docs:
        assert "peanut" not in d["allergens"], f"PEANUT LEAKED via '{query}': {d['name']}"


def test_unverified_withheld_even_when_allergens_look_clean():
    """'No verified data' and 'verifiably contains none' are different claims.

    Avocado Toast has allergens=['gluten'] (no peanut) but allergen_verified=false.
    It must NOT appear under a peanut exclusion, despite its list looking clean.
    """
    docs, _ = run("*", ctx(exclude_allergens=["peanut"]))
    for d in docs:
        assert d["allergen_verified"] is True, (
            f"Unverified item surfaced under an active exclusion: {d['name']}"
        )


def test_gate_is_conditional_not_global():
    """With no exclusions active, unverified items ARE visible."""
    docs, _ = run("*", ctx())
    assert any(d["allergen_verified"] is False for d in docs), (
        "Provenance gate applied with no exclusions active — it should be conditional"
    )


def test_withheld_count_isolates_the_provenance_gate():
    """The diff must count only docs removed by the gate, not by other filters.

    Gated and ungated queries differ solely by the verification gate, so the
    difference is exactly the set of unverified docs that cleared everything else.
    """
    c = ctx(exclude_allergens=["peanut"])
    docs, withheld = run("*", c)

    ungated_filter = build_filter_by(c, gated=False)
    res = admin_client().multi_search.perform(
        {
            "searches": [
                {
                    "collection": "food_items",
                    "q": "*",
                    "query_by": "name",
                    "filter_by": f"{ungated_filter} && allergen_verified:false",
                    "exclude_fields": "embedding",
                    "per_page": 0,
                }
            ]
        },
        {},
    )
    expected = res["results"][0]["found"]
    assert withheld == expected, (
        f"withheld={withheld} but {expected} unverified docs cleared the other filters"
    )


def test_single_multi_search_request():
    """Gated query and withheld count arrive in ONE round trip, not two."""
    body = build_search_request("chicken", ctx(exclude_allergens=["dairy"]))
    assert len(body["searches"]) == 2
    res = admin_client().multi_search.perform(body, {})
    assert len(res["results"]) == 2


def test_explicit_filter_never_empty_under_exclusions():
    """A bug here would silently disable the entire safety layer."""
    f = build_filter_by(ctx(exclude_allergens=["peanut"], diet_flags=["vegan"]))
    assert "allergens:!=peanut" in f
    assert "diet_flags:=vegan" in f
    assert "allergen_verified:true" in f


def test_soft_filter_cannot_remove_the_gate():
    """Even a hostile soft filter is ANDed, never substituted."""
    f = build_filter_by(
        ctx(exclude_allergens=["peanut"]),
        soft_filter_by="calories:<9999 || allergen_verified:false",
    )
    assert "allergens:!=peanut" in f
    assert "allergen_verified:true" in f
    assert f.count("&&") >= 2


def test_diet_flag_enforced():
    docs, _ = run("*", ctx(diet_flags=["vegan"]))
    for d in docs:
        assert "vegan" in d["diet_flags"], f"Non-vegan item surfaced: {d['name']}"
