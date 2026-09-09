"""THE API CONTRACT. Mirrored field-for-field in web/src/lib/types.ts.

Change both together or not at all.
"""
from typing import Literal

from pydantic import BaseModel

Provenance = Literal["OFFICIAL_FEED", "CHAIN_PUBLISHED", "CROWD_VERIFIED", "ESTIMATED"]
Goal = Literal["high_protein", "sustained_energy", "light", "none"]


class UserContext(BaseModel):
    lat: float
    lng: float
    campus_id: str = "purdue"
    now_minutes: int  # minutes since local midnight
    exclude_allergens: list[str] = []  # HARD
    diet_flags: list[str] = []  # HARD
    goal: Goal = "none"
    radius_mi: float = 3.0


class SearchRequest(BaseModel):
    query: str  # natural language
    context: UserContext


class ClearedConstraint(BaseModel):
    label: str  # "dairy-free"
    passed: bool


class Hit(BaseModel):
    id: str
    name: str
    venue_name: str
    source_type: Literal["dining_hall", "off_campus"]
    distance_mi: float
    calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    provenance: Provenance
    allergen_verified: bool
    cleared: list[ClearedConstraint]
    lat: float
    lng: float


class ReasoningTrace(BaseModel):
    interpreted_intent: str  # "low-glycemic, moderate protein"
    generated_filters: str | None  # from the LLM
    explicit_filters: str  # from US — the safety layer
    chosen_sort: str
    llm_error: str | None = None
    degraded: bool = False  # true if we fell back to keyword search


class PartialMatch(BaseModel):
    hit: Hit
    fails: list[str]  # ["40g over your carb target"]


class SearchResponse(BaseModel):
    hits: list[Hit]
    withheld_count: int
    reasoning: ReasoningTrace
    partial_matches: list[PartialMatch] = []  # populated when hits is empty
    took_ms: int
