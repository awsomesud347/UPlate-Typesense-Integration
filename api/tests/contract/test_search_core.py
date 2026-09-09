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


def _by_bucket(hit_list: list[dict]) -> dict[int, list[tuple[dict, float]]]:
    """Group hits by their 1-mile distance bucket, matching the precision used in
    sort_by. Ordering guarantees hold within a bucket, not across buckets."""
    out: dict[int, list[tuple[dict, float]]] = {}
    for h in hit_list:
        meters = h.get("geo_distance_meters", {}).get("location", 0)
        out.setdefault(int(meters / 1609.34), []).append((h["document"], meters))
    return out


def names(query: str, c: UserContext, **kw) -> list[str]:
    return [h["document"]["name"] for h in hits(query, c, **kw)]


def test_keyword_match():
    assert any("Chicken" in n for n in names("chicken", ctx()))


def test_hybrid_semantic_match():
    """THE HYBRID PROOF. 'warm and comforting' must surface soups/stews even
    though neither word appears in those documents. Fails if query_by omits
    the embedding field.

    Sorted by relevance only: with a geo sort in front, this would be testing
    the distance bucket rather than retrieval quality."""
    assert "embedding" in QUERY_BY
    res = admin_client().multi_search.perform(
        {
            "searches": [
                {
                    "collection": "food_items",
                    "q": "something warm and comforting",
                    "query_by": QUERY_BY,
                    "vector_query": "embedding:([], alpha: 0.3)",
                    "exclude_fields": "embedding",
                    "per_page": 10,
                }
            ]
        },
        {},
    )["results"][0]
    result = [h["document"]["name"] for h in res.get("hits", [])]
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
    buckets = _by_bucket(hits("*", ctx(goal="high_protein")))
    biggest = max(buckets.values(), key=len)
    assert len(biggest) >= 3, "not enough items in one bucket to test ordering"

    densities = [d["protein_density"] for d, _ in biggest]
    assert densities == sorted(densities, reverse=True), (
        f"Distance bucket is not ordered by protein_density: {densities}"
    )

    # Prove the tie is real: the bucket spans a range of actual distances, so a
    # farther-but-higher-protein item genuinely outranks a nearer, weaker one.
    dists = [m for _, m in biggest]
    assert max(dists) > min(dists), "all items equidistant; bucketing untested"


def test_availability_window():
    """Famous Frank's is a late-night cart (22:00 onward): visible at 23:00,
    invisible at noon. Uses a retail venue so the test holds under RETAIL_ONLY."""
    assert "Cheese Fries" in names("cheese fries", ctx(now_minutes=1380))
    assert "Cheese Fries" not in names("cheese fries", ctx(now_minutes=720))


def test_light_goal_sorts_by_calories():
    """Within the nearby distance bucket, calories must be non-decreasing."""
    buckets = _by_bucket(hits("*", ctx(goal="light")))
    biggest = max(buckets.values(), key=len)
    cals = [d["calories"] for d, _ in biggest]
    assert cals == sorted(cals), f"'light' goal did not sort by calories: {cals}"


def test_campus_scoping():
    for h in hits("*", ctx()):
        assert h["document"]["campus_id"] == "purdue"


def test_retail_only_scope():
    """UPlate covers dining courts natively; this product is the retail half.
    Applied as a query-time filter so it flips via config without a reindex —
    the dining-hall documents stay in the index either way."""
    from app.config import get_settings

    if not get_settings().retail_only:
        pytest.skip("RETAIL_ONLY disabled")

    for h in hits("*", ctx()):
        assert h["document"]["source_type"] == "off_campus", (
            f"dining-hall item leaked into retail-only search: {h['document']['name']}"
        )

    # The data is still there — this is scoping, not deletion.
    total = admin_client().collections["food_items"].retrieve()["num_documents"]
    assert total > found("*", ctx()), "retail filter removed nothing; is it applied?"
