"""Dev-only fixture response, served when USE_FIXTURES=true.

Exists so frontend work doesn't require a running Typesense. It is opt-in and
off by default on purpose: fixture data does not honor allergen exclusions, so
a silent fallback would show unfiltered results while claiming they were
filtered. The reasoning trace stamps every fixture response so it is impossible
to mistake one for a real search.
"""
import time

from app.schemas.search import (
    ClearedConstraint,
    Hit,
    ReasoningTrace,
    SearchResponse,
)

FIXTURE_HITS = [
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


def fixture_response(start: float) -> SearchResponse:
    return SearchResponse(
        hits=FIXTURE_HITS,
        withheld_count=2,
        reasoning=ReasoningTrace(
            interpreted_intent="FIXTURE MODE — not a real search",
            generated_filters=None,
            explicit_filters="(none — USE_FIXTURES=true bypasses the safety layer)",
            chosen_sort="(none)",
            llm_error=None,
            degraded=True,
        ),
        took_ms=int((time.perf_counter() - start) * 1000),
    )
