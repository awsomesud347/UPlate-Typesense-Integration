"""THE core module. The only place Typesense search params are assembled.

Layering (see BUILD_PLAN.md §4):
  - hard exclusions + provenance gate -> explicit filter_by (ours, ANDed, un-loosenable)
  - soft preferences / LLM interpretation -> q, soft_filter_by, sort selection
  - hybrid search: query_by MUST include `embedding` alongside text fields
  - multi_search: search 1 = gated query, search 2 = same minus the provenance
    gate, per_page 0 — its found-count diff is the withheld count
"""
from app.constraints.exclusions import exclusion_fragments, has_hard_exclusions
from app.constraints.goals import goal_sort
from app.constraints.provenance import VERIFICATION_GATE
from app.schemas.search import UserContext
from app.typesense.synonyms import SET_NAME as SYNONYM_SET

QUERY_BY = "name,description,tags,venue_name,embedding"


def build_filter_by(
    ctx: UserContext,
    gated: bool = True,
    soft_filter_by: str | None = None,
    radius_override: float | None = None,
    with_availability: bool = True,
) -> str:
    radius = radius_override or ctx.radius_mi
    frags = [
        f"campus_id:={ctx.campus_id}",
        f"location:({ctx.lat}, {ctx.lng}, {radius} mi)",
    ]
    if with_availability:
        frags.append(f"available_from:<={ctx.now_minutes}")
        frags.append(f"available_to:>={ctx.now_minutes}")
    frags += exclusion_fragments(ctx.exclude_allergens, ctx.diet_flags)
    if gated and has_hard_exclusions(ctx.exclude_allergens, ctx.diet_flags):
        frags.append(VERIFICATION_GATE)
    if soft_filter_by:
        # Soft prefs are ANDed into BOTH gated and ungated queries so the
        # withheld diff isolates the provenance gate specifically.
        frags.append(soft_filter_by)
    return " && ".join(frags)


def sort_for(ctx: UserContext, goal: str | None = None) -> str:
    return (
        f"location({ctx.lat}, {ctx.lng}, precision: 1 mi):asc, "
        f"{goal_sort(goal or ctx.goal)}"
    )


def base_search(q: str, ctx: UserContext, goal: str | None, alpha: float) -> dict:
    params = {
        "collection": "food_items",
        "q": q or "*",
        "query_by": QUERY_BY,
        "sort_by": sort_for(ctx, goal),
        "exclude_fields": "embedding",  # always — vectors bloat every response
        "synonym_sets": SYNONYM_SET,  # campus slang -> menu vocabulary
        "per_page": 20,
    }
    if q and q != "*":
        params["vector_query"] = f"embedding:([], alpha: {alpha})"
    return params


def build_search_request(
    q: str,
    ctx: UserContext,
    goal: str | None = None,
    soft_filter_by: str | None = None,
    alpha: float = 0.3,
) -> dict:
    """Returns a Typesense multi_search body: [gated query, ungated count query]."""
    base = base_search(q, ctx, goal, alpha)
    gated = {
        **base,
        "filter_by": build_filter_by(ctx, gated=True, soft_filter_by=soft_filter_by),
    }
    ungated_count = {
        **base,
        "filter_by": build_filter_by(ctx, gated=False, soft_filter_by=soft_filter_by),
        "per_page": 0,
    }
    return {"searches": [gated, ungated_count]}


def build_relaxed_request(q: str, ctx: UserContext, goal: str | None = None) -> dict:
    """Empty-state fallback: exclusions KEPT (safety never relaxes), radius x3,
    availability dropped, soft prefs dropped."""
    base = base_search(q, ctx, goal, alpha=0.3)
    return {
        "searches": [
            {
                **base,
                "filter_by": build_filter_by(
                    ctx,
                    gated=True,
                    radius_override=ctx.radius_mi * 3,
                    with_availability=False,
                ),
                "per_page": 5,
            }
        ]
    }
