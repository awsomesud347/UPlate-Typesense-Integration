"""POST /api/search.

Currently serves FIXTURE data matching the real contract so the UI can integrate
from minute one. Phase 2 wires build_search_request + Typesense multi_search here;
Phase 4 adds the Claude interpreter. The response shape does not change.
"""
import time

from fastapi import APIRouter

from app.schemas.search import (
    ClearedConstraint,
    Hit,
    ReasoningTrace,
    SearchRequest,
    SearchResponse,
)

router = APIRouter()

_FIXTURE_HITS = [
    Hit(
        id="wiley-grilled-chicken",
        name="Grilled Chicken Breast",
        venue_name="Wiley Dining Court",
        source_type="dining_hall",
        distance_mi=0.3,
        calories=280,
        protein_g=42.0,
        carbs_g=2.0,
        fat_g=8.0,
        provenance="OFFICIAL_FEED",
        allergen_verified=True,
        cleared=[
            ClearedConstraint(label="dairy-free", passed=True),
            ClearedConstraint(label="42g protein", passed=True),
        ],
        lat=40.4286,
        lng=-86.9207,
    ),
    Hit(
        id="chipotle-chicken-bowl",
        name="Chicken Burrito Bowl (no cheese)",
        venue_name="Chipotle - Chauncey Hill",
        source_type="off_campus",
        distance_mi=0.6,
        calories=510,
        protein_g=51.0,
        carbs_g=41.0,
        fat_g=16.5,
        provenance="CHAIN_PUBLISHED",
        allergen_verified=True,
        cleared=[
            ClearedConstraint(label="dairy-free", passed=True),
            ClearedConstraint(label="51g protein", passed=True),
        ],
        lat=40.4241,
        lng=-86.9081,
    ),
]


@router.post("/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    start = time.perf_counter()
    # TODO(Phase 2): interpret -> build_search_request -> multi_search -> map hits
    return SearchResponse(
        hits=_FIXTURE_HITS,
        withheld_count=2,
        reasoning=ReasoningTrace(
            interpreted_intent="high protein, dairy excluded (FIXTURE DATA)",
            generated_filters=None,
            explicit_filters="campus_id:=purdue && allergens:!=dairy && allergen_verified:true",
            chosen_sort="location(...):asc, protein_density:desc",
            degraded=False,
        ),
        took_ms=int((time.perf_counter() - start) * 1000),
    )
