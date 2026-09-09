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
from app.typesense import nl_model
from app.typesense.client import admin_client

# Shared with the Typesense NL model's system_prompt so the two cannot drift.
SITUATIONAL_HINTS = nl_model.SITUATIONAL_HINTS

CACHE_TTL_SECONDS = 10 * 60
_ALLOWED_GOALS = {"none", "high_protein", "sustained_energy", "light"}
_FORBIDDEN_FILTER_FIELDS = re.compile(
    r"\b(allergens?|allergen_verified|diet_flags?)\b", re.IGNORECASE
)
# Typesense ANDs a generated filter onto ours WITHOUT parentheses, and && binds
# tighter than ||. So `exclusion && a:1 || b:2` lets the right branch escape the
# exclusion entirely. Any disjunction in model output is therefore discarded
# outright rather than parenthesised — we cannot know what the model meant, and
# guessing on the allergen path is not a risk worth taking.
_DISJUNCTION = re.compile(r"\|\|")

# Generated sort_by -> our goal axis. Anything unrecognised falls back to "none".
_SORT_TO_GOAL: dict[str, str] = {
    "glycemic_proxy:asc": "sustained_energy",
    "protein_density:desc": "high_protein",
    "calories:asc": "light",
}

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


def _safe_soft_filter(value: Any) -> str | None:
    """Reduce a model-generated filter to something safe, or drop it entirely.

    Fails closed on every branch. A discarded soft preference costs the user a
    slightly worse ranking; a mishandled one costs the safety invariant.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if _FORBIDDEN_FILTER_FIELDS.search(candidate):
        return None  # the model has no business filtering on safety fields
    if _DISJUNCTION.search(candidate):
        return None  # see _DISJUNCTION — precedence hole, not a formatting nit
    if candidate.count("(") != candidate.count(")"):
        return None
    return candidate


def _interpret_via_typesense(query: str) -> Interpretation:
    """Primary path: Typesense NL Search Models, used as a parser only."""
    params = nl_model.parse(admin_client(), _without_hard_constraints(query.strip()))

    sort_by = params.get("sort_by")
    goal = _SORT_TO_GOAL.get(sort_by.strip(), "none") if isinstance(sort_by, str) else "none"

    # GOTCHA: the model emits q:"*" when it reads a query as purely filter-shaped.
    # A wildcard has no text to embed, so hybrid ranking silently collapses on
    # exactly the queries worth demoing. Fall back to the user's own words.
    generated_q = params.get("q")
    if not isinstance(generated_q, str) or not generated_q.strip() or generated_q.strip() == "*":
        generated_q = query.strip()

    soft_filter = _safe_soft_filter(params.get("filter_by"))
    intent = ", ".join(
        part for part in [
            {"sustained_energy": "steady energy, low crash risk",
             "high_protein": "protein-forward",
             "light": "lighter options"}.get(goal),
            f"filtered on {soft_filter}" if soft_filter else None,
        ] if part
    )

    return Interpretation(
        intent=intent or "Food search",
        soft_filter_by=soft_filter,
        goal=goal,
        search_terms=generated_q.strip(),
        raw={"source": "typesense_nl", "generated_params": params},
    )


def _validate(data: dict[str, Any], raw: dict[str, Any], query: str) -> Interpretation:
    goal = data.get("goal", "none")
    if goal not in _ALLOWED_GOALS:
        goal = "none"

    soft_filter = _safe_soft_filter(data.get("soft_filter_by"))

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


def _interpret_via_claude(query: str) -> Interpretation:
    """Fallback path. Typesense NL models do not accept Anthropic as a provider,
    so this talks to the API directly rather than through the engine."""
    settings = get_settings()
    response = _get_client().messages.create(
        model=settings.anthropic_model,
        max_tokens=500,
        temperature=0,
        system=_SYSTEM_PROMPT,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[{"role": "user", "content": _without_hard_constraints(query.strip())}],
    )
    data, raw = _tool_input(response)
    raw["source"] = "claude_fallback"
    return _validate(data, raw, query)


def interpret(query: str) -> Interpretation:
    """Interpret a natural-language query. Never raises.

    Typesense NL Search Models first (it is a Typesense feature and the primary
    path), Claude second, plain keyword search last. Each step down is a
    degradation in ranking quality only — hard exclusions are assembled in
    query_builder from UserContext and are unaffected by any of this.
    """
    if not isinstance(query, str) or not _normalize_query(query):
        return _degraded(query if isinstance(query, str) else "", "query must be a non-empty string")

    normalized = _normalize_query(query)
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(normalized)
        if cached and cached.expires_at > now:
            return copy.deepcopy(cached.value)
        if cached:
            _cache.pop(normalized, None)

    errors: list[str] = []
    for name, path in (("typesense_nl", _interpret_via_typesense), ("claude", _interpret_via_claude)):
        try:
            result = path(query)
        except Exception as exc:
            errors.append(f"{name}: {str(exc).strip() or type(exc).__name__}")
            continue

        with _cache_lock:
            _cache[normalized] = _CacheEntry(
                expires_at=time.monotonic() + CACHE_TTL_SECONDS,
                value=copy.deepcopy(result),
            )
        return result

    # This boundary is intentional: search availability must not depend on any LLM.
    return _degraded(query, "; ".join(errors))
