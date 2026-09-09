"""Retrieval behavior against the real seeded index.

The hybrid test is the load-bearing one: if `embedding` drops out of query_by,
search silently degrades to keyword-only, which looks fine on easy queries and
fails every semantic one. Do not weaken it.
"""
import pytest

from app.schemas.search import UserContext
from app.typesense.client import admin_client
from app.typesense.query_builder import QUERY_BY, build_search_request


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


def result(query: str, c: UserContext, **kw) -> dict:
    body = build_search_request(query, c, **kw)
    res = admin_client().multi_search.perform(body, {})["results"][0]
    assert "error" not in res, res.get("error")
    return res


def hits(query: str, c: UserContext, **kw) -> list[dict]:
    return result(query, c, **kw).get("hits", [])


def found(query: str, c: UserContext, **kw) -> int:
    return result(query, c, **kw).get("found", 0)


def names(query: str, c: UserContext, **kw) -> list[str]:
    return [h["document"]["name"] for h in hits(query, c, **kw)]


def test_keyword_match():
    assert any("Chicken" in n for n in names("chicken", ctx()))


def test_hybrid_semantic_match():
    """THE HYBRID PROOF. 'warm and comforting' must surface soups/stews even
    though neither word appears in those documents. Fails if query_by omits
    the embedding field."""
    assert "embedding" in QUERY_BY
    result = names("something warm and comforting", ctx())
    comfort = {"Creamy Tomato Basil Soup", "Hearty Lentil Stew", "Cheesestix"}
    assert comfort & set(result[:5]), (
        f"No comfort food in top 5 — hybrid search may be keyword-only. Got: {result[:5]}"
    )


def test_embedding_never_returned():
    """Vectors bloat every response; exclude_fields must always strip them."""
    for h in hits("chicken", ctx()):
        assert "embedding" not in h["document"]


def test_geo_radius_excludes_distant_items():
    """Compare found-counts, not page lengths — both pages cap at per_page."""
    near = found("*", ctx(radius_mi=0.35))
    far = found("*", ctx(radius_mi=5.0))
    assert 0 < near < far, f"radius had no effect: {near} vs {far}"


def test_geo_bucketing_lets_goal_break_the_tie():
    """With precision:1mi everything inside a mile ties on distance, so the goal
    axis breaks it. Assert the ordering property directly: within that bucket,
    protein_density must be non-increasing — meaning a farther-but-higher-protein
    item legitimately outranks a nearer, lower-protein one."""
    within_mile = [
        h for h in hits("*", ctx(goal="high_protein"))
        if h.get("geo_distance_meters", {}).get("location", 0) <= 1609
    ]
    assert len(within_mile) >= 3, "not enough nearby items to test bucketing"

    densities = [h["document"]["protein_density"] for h in within_mile]
    assert densities == sorted(densities, reverse=True), (
        f"Distance bucket is not ordered by protein_density: {densities}"
    )

    # And prove the tie is real: the bucket spans a range of actual distances.
    dists = [h["geo_distance_meters"]["location"] for h in within_mile]
    assert max(dists) > min(dists), "all items equidistant; bucketing untested"


def test_availability_window():
    """Breakfast-only oatmeal is served 06:30-10:30; invisible at noon."""
    assert "Steel-Cut Oatmeal with Berries" in names("oatmeal", ctx(now_minutes=480))
    assert "Steel-Cut Oatmeal with Berries" not in names("oatmeal", ctx(now_minutes=720))


def test_light_goal_sorts_by_calories():
    """Within the nearby distance bucket, calories must be non-decreasing."""
    within_mile = [
        h for h in hits("*", ctx(goal="light"))
        if h.get("geo_distance_meters", {}).get("location", 0) <= 1609
    ]
    cals = [h["document"]["calories"] for h in within_mile]
    assert cals == sorted(cals), f"'light' goal did not sort by calories: {cals}"


def test_campus_scoping():
    for h in hits("*", ctx()):
        assert h["document"]["campus_id"] == "purdue"
