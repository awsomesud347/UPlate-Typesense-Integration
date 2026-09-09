"""POST /api/search — live Typesense hybrid search.

Flow: interpret (Claude, degrades to keyword) -> build_search_request ->
multi_search -> map hits. Hard exclusions + provenance gate ride the explicit
filter_by and are structurally outside the LLM's reach.
"""
import time

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.fixtures import fixture_response
from app.llm.interpreter import interpret
from app.schemas.search import (
    ClearedConstraint,
    Hit,
    PartialMatch,
    ReasoningTrace,
    SearchRequest,
    SearchResponse,
    UserContext,
)
from app.typesense.client import admin_client
from app.typesense.query_builder import build_relaxed_request, build_search_request

router = APIRouter()

METERS_PER_MILE = 1609.34


def _cleared_for(doc: dict, ctx: UserContext) -> list[ClearedConstraint]:
    cleared = []
    for allergen in ctx.exclude_allergens:
        cleared.append(ClearedConstraint(label=f"{allergen}-free", passed=True))
    for flag in ctx.diet_flags:
        cleared.append(ClearedConstraint(label=flag.replace("_", "-"), passed=True))
    if ctx.goal == "high_protein":
        cleared.append(
            ClearedConstraint(label=f"{doc['protein_g']:.0f}g protein", passed=True)
        )
    if ctx.goal == "light":
        cleared.append(ClearedConstraint(label=f"{doc['calories']} cal", passed=True))
    return cleared


def _to_hit(ts_hit: dict, ctx: UserContext) -> Hit:
    doc = ts_hit["document"]
    meters = ts_hit.get("geo_distance_meters", {}).get("location", 0)
    return Hit(
        id=doc["id"],
        name=doc["name"],
        venue_name=doc["venue_name"],
        source_type=doc["source_type"],
        distance_mi=round(meters / METERS_PER_MILE, 2),
        calories=doc["calories"],
        protein_g=doc["protein_g"],
        carbs_g=doc["carbs_g"],
        fat_g=doc["fat_g"],
        provenance=doc["provenance"],
        allergen_verified=doc["allergen_verified"],
        cleared=_cleared_for(doc, ctx),
        lat=doc["location"][0],
        lng=doc["location"][1],
    )


def _fails_for(doc: dict, ctx: UserContext) -> list[str]:
    fails = []
    if doc.get("available_to", 1439) < ctx.now_minutes:
        fails.append("closed by now")
    elif doc.get("available_from", 0) > ctx.now_minutes:
        fails.append("not serving yet")
    meters = doc.get("_geo_distance", None)
    if meters is None:
        fails.append(f"outside your {ctx.radius_mi:g} mi radius")
    return fails or ["outside your current filters"]


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    start = time.perf_counter()
    ctx = req.context

    if get_settings().use_fixtures:
        return fixture_response(start)

    interp = interpret(req.query)
    goal = interp.goal if ctx.goal == "none" and interp.goal != "none" else ctx.goal

    body = build_search_request(
        interp.search_terms or req.query,
        ctx,
        goal=goal,
        soft_filter_by=interp.soft_filter_by,
    )

    try:
        results = admin_client().multi_search.perform(body, {})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Typesense error: {e}") from e

    gated_res, ungated_res = results["results"][0], results["results"][1]
    if "error" in gated_res:
        raise HTTPException(status_code=502, detail=f"Search error: {gated_res['error']}")

    hits = [_to_hit(h, ctx) for h in gated_res.get("hits", [])]
    withheld = max(ungated_res.get("found", 0) - gated_res.get("found", 0), 0)

    partial_matches: list[PartialMatch] = []
    if not hits:
        relaxed = build_relaxed_request(interp.search_terms or req.query, ctx, goal=goal)
        try:
            relaxed_res = admin_client().multi_search.perform(relaxed, {})["results"][0]
            for h in relaxed_res.get("hits", []):
                partial_matches.append(
                    PartialMatch(hit=_to_hit(h, ctx), fails=_fails_for(h["document"], ctx))
                )
        except Exception:
            pass  # empty state stays empty; never fail the whole response for it

    gated_query = body["searches"][0]
    return SearchResponse(
        hits=hits,
        withheld_count=withheld,
        reasoning=ReasoningTrace(
            interpreted_intent=interp.intent,
            generated_filters=interp.soft_filter_by,
            explicit_filters=gated_query["filter_by"],
            chosen_sort=gated_query["sort_by"],
            llm_error=interp.error,
            degraded=interp.degraded,
        ),
        partial_matches=partial_matches,
        took_ms=int((time.perf_counter() - start) * 1000),
    )
