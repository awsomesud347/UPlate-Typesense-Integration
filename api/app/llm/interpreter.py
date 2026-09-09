"""Claude query-understanding layer. [BACKEND DEV OWNS THIS — Phase 4]

Contract: interpret(query) -> Interpretation. It NEVER sees or emits allergen /
diet exclusions — those come from UserContext and are applied as the explicit
filter_by in query_builder. The LLM interprets vibes; it does not enforce safety.

Must: cache by normalized query (TTL ~10 min, demo insurance), and degrade
gracefully — on any API failure return Interpretation(degraded=True) so search
falls back to plain keyword. Never raise out of interpret().
"""
from __future__ import annotations

import copy
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.config import get_settings

# Situational mappings live HERE, in one editable place, not inside prompts
# scattered through query code.
SITUATIONAL_HINTS: dict[str, str] = {
    "exam / studying / focus / tired / don't crash": (
        "sustained_energy: rank glycemic_proxy ascending and prefer moderate protein"
    ),
    "post-workout / recovery / gains": (
        "high_protein: rank protein_density descending"
    ),
    "light / small / snack / not too heavy": "light: rank calories ascending",
    "warm / hot / comfort / cold day": (
        "prefer warm food using tags or is_warm; keep the user's other goal"
    ),
}

CACHE_TTL_SECONDS = 10 * 60
_ALLOWED_GOALS = {"none", "high_protein", "sustained_energy", "light"}
_FORBIDDEN_FILTER_FIELDS = re.compile(
    r"\b(allergens?|allergen_verified|diet_flags?)\b", re.IGNORECASE
)
_HARD_CONSTRAINT_TERMS = re.compile(
    r"\b(?:"
    r"peanuts?|tree[\s-]?nuts?|nuts?|dairy|milk|eggs?|wheat|gluten|soy|"
    r"sesame|fish|shellfish|crustaceans?|pork|halal|kosher|vegan|vegetarian"
    r")\b",
    re.IGNORECASE,
)

_TOOL_NAME = "interpret_food_query"
_TOOL = {
    "name": _TOOL_NAME,
    "description": (
        "Interpret only soft food preferences and situational nutrition intent. "
        "Never produce allergen, medical, religious, or dietary exclusions."
    ),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {
                "type": "string",
                "description": "Short, user-facing description of the strategy.",
            },
            "soft_filter_by": {
                "type": ["string", "null"],
                "description": (
                    "Optional Typesense filter using only soft numeric or food-style "
                    "fields. Never use allergens, allergen_verified, or diet_flags."
                ),
            },
            "goal": {
                "type": "string",
                "enum": sorted(_ALLOWED_GOALS),
            },
            "search_terms": {
                "type": "string",
                "description": (
                    "Concise dish/style terms for retrieval; preserve the original "
                    "words when no useful rewrite exists."
                ),
            },
        },
        "required": ["intent", "soft_filter_by", "goal", "search_terms"],
    },
}

_SYSTEM_PROMPT = """You interpret food-search requests into SOFT retrieval preferences.
You do not enforce safety. All allergen, medical, religious, and dietary exclusions are
handled deterministically elsewhere; never include them in soft_filter_by or search_terms.

Available soft fields for soft_filter_by:
- calories, protein_g, carbs_g, fat_g, fiber_g, sodium_mg
- tags, is_warm, source_type, venue_name

Choose exactly one goal:
- sustained_energy: lower glycemic_proxy first
- high_protein: higher protein_density first
- light: lower calories first
- none: relevance first

Situational mappings:
{hints}

Use the interpretation tool exactly once. Keep intent short and human-readable. Do not
invent precise numeric limits unless the user supplied one. Preferences such as "high
protein" should normally select a goal rather than exclude otherwise relevant food.
""".format(
    hints="\n".join(f"- {situation} -> {strategy}" for situation, strategy in SITUATIONAL_HINTS.items())
)


@dataclass
class Interpretation:
    intent: str = ""  # human-readable, e.g. "low-glycemic, moderate protein"
    soft_filter_by: str | None = None  # e.g. "calories:<600" — soft prefs ONLY
    goal: str = "none"  # maps into constraints/goals.py axes
    search_terms: str = ""  # cleaned q for Typesense
    degraded: bool = False
    error: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class _CacheEntry:
    expires_at: float
    value: Interpretation


_cache: dict[str, _CacheEntry] = {}
_cache_lock = threading.Lock()
_client: Any | None = None
_client_lock = threading.Lock()


def _normalize_query(query: str) -> str:
    return " ".join(query.casefold().split())


def _without_hard_constraints(query: str) -> str:
    """Keep safety terms out of the model; UserContext owns their meaning."""
    redacted = _HARD_CONSTRAINT_TERMS.sub("[constraint handled separately]", query)
    return " ".join(redacted.split())


def _get_client() -> Any:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                api_key = get_settings().anthropic_api_key
                if not api_key:
                    raise RuntimeError("ANTHROPIC_API_KEY is not configured")
                _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _block_value(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _tool_input(response: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    content = response.get("content", []) if isinstance(response, dict) else response.content
    for block in content:
        if (
            _block_value(block, "type") == "tool_use"
            and _block_value(block, "name") == _TOOL_NAME
        ):
            value = _block_value(block, "input")
            if not isinstance(value, dict):
                raise ValueError("Claude returned non-object tool input")
            raw = (
                response
                if isinstance(response, dict)
                else {
                    "id": getattr(response, "id", None),
                    "model": getattr(response, "model", None),
                    "stop_reason": getattr(response, "stop_reason", None),
                    "tool_input": copy.deepcopy(value),
                }
            )
            return value, raw
    raise ValueError("Claude did not return the interpretation tool")


def _validate(data: dict[str, Any], raw: dict[str, Any], query: str) -> Interpretation:
    goal = data.get("goal", "none")
    if goal not in _ALLOWED_GOALS:
        goal = "none"

    soft_filter = data.get("soft_filter_by")
    if not isinstance(soft_filter, str) or not soft_filter.strip():
        soft_filter = None
    elif _FORBIDDEN_FILTER_FIELDS.search(soft_filter):
        # Fail closed for this model-owned field. Hard constraints are assembled elsewhere.
        soft_filter = None
    else:
        soft_filter = soft_filter.strip()

    intent = data.get("intent")
    search_terms = data.get("search_terms")
    return Interpretation(
        intent=intent.strip() if isinstance(intent, str) and intent.strip() else "Food search",
        soft_filter_by=soft_filter,
        goal=goal,
        search_terms=(
            search_terms.strip()
            if isinstance(search_terms, str) and search_terms.strip()
            else query.strip()
        ),
        raw=raw,
    )


def _degraded(query: str, error: Exception | str) -> Interpretation:
    message = str(error).strip() or type(error).__name__
    return Interpretation(
        intent="Keyword search (query interpretation unavailable)",
        search_terms=query.strip(),
        degraded=True,
        error=message,
    )


def clear_cache() -> None:
    """Clear interpreter state; useful for tests and explicit pre-warming."""
    with _cache_lock:
        _cache.clear()


def interpret(query: str) -> Interpretation:
    """Interpret a natural-language query, returning a keyword fallback on failure."""
    try:
        if not isinstance(query, str):
            raise TypeError("query must be a string")
        normalized = _normalize_query(query)
        if not normalized:
            raise ValueError("query must not be empty")

        now = time.monotonic()
        with _cache_lock:
            cached = _cache.get(normalized)
            if cached and cached.expires_at > now:
                return copy.deepcopy(cached.value)
            if cached:
                _cache.pop(normalized, None)

        settings = get_settings()
        model_query = _without_hard_constraints(query.strip())
        response = _get_client().messages.create(
            model=settings.anthropic_model,
            max_tokens=500,
            temperature=0,
            system=_SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": model_query}],
        )
        data, raw = _tool_input(response)
        result = _validate(data, raw, query)

        with _cache_lock:
            _cache[normalized] = _CacheEntry(
                expires_at=time.monotonic() + CACHE_TTL_SECONDS,
                value=copy.deepcopy(result),
            )
        return result
    except Exception as exc:
        # This boundary is intentional: search availability must not depend on Claude.
        return _degraded(query if isinstance(query, str) else "", exc)
