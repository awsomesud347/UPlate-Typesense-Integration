"""THE core module. The only place Typesense search params are assembled.

Layering (see BUILD_PLAN.md section 4):
  - hard exclusions + provenance gate -> explicit filter_by (ours, ANDed, un-loosenable)
  - soft preferences / LLM interpretation -> q, sort selection
  - hybrid search: query_by MUST include `embedding` alongside text fields
  - multi_search: search 1 = gated query, search 2 = ungated count (withheld diff)
"""
from app.constraints.exclusions import exclusion_fragments, has_hard_exclusions
from app.constraints.goals import goal_sort
from app.constraints.provenance import VERIFICATION_GATE
from app.schemas.search import UserContext

QUERY_BY = "name,description,tags,venue_name,embedding"


def build_filter_by(ctx: UserContext, gated: bool = True) -> str:
    frags = [
        f"campus_id:={ctx.campus_id}",
        f"location:({ctx.lat}, {ctx.lng}, {ctx.radius_mi} mi)",
        f"available_from:<={ctx.now_minutes}",
        f"available_to:>={ctx.now_minutes}",
    ]
    frags += exclusion_fragments(ctx.exclude_allergens, ctx.diet_flags)
    if gated and has_hard_exclusions(ctx.exclude_allergens, ctx.diet_flags):
        frags.append(VERIFICATION_GATE)
    return " && ".join(frags)


def build_search_request(q: str, ctx: UserContext, alpha: float = 0.3) -> dict:
    """Returns a Typesense multi_search body: [gated query, ungated count query]."""
    base = {
        "collection": "food_items",
        "q": q or "*",
        "query_by": QUERY_BY,
        "vector_query": f"embedding:([], alpha: {alpha})",
        "sort_by": (
            f"location({ctx.lat}, {ctx.lng}, precision: 1 mi):asc, {goal_sort(ctx.goal)}"
        ),
        "exclude_fields": "embedding",  # always — vectors bloat every response
        "per_page": 20,
    }
    gated = {**base, "filter_by": build_filter_by(ctx, gated=True)}
    ungated_count = {
        **base,
        "filter_by": build_filter_by(ctx, gated=False),
        "per_page": 0,  # only want found-count for the withheld diff
    }
    return {"searches": [gated, ungated_count]}
