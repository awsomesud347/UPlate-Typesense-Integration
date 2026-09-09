"""Typesense NL Search Models — registration and parse-only querying.

Typesense does not host its own LLM for query understanding. It orchestrates a
third-party one (OpenAI, Google Gemini, GCP Vertex, Cloudflare Workers AI, or a
self-hosted vLLM) and turns a sentence into structured search params. Anthropic
is not a supported provider, which is why the Claude path in app/llm/ exists as a
fallback rather than the primary.

PARSE ONLY. We set per_page=0 and read parsed_nl_query.generated_params, then
discard the hits and re-issue the search ourselves through query_builder. Two
reasons, both load-bearing:

  1. Typesense concatenates the model's filter onto ours with && and no
     parentheses. A generated `a:1 || b:2` becomes `exclusion && a:1 || b:2`,
     and since && binds tighter than ||, the right branch escapes the exclusion
     entirely. Letting Typesense execute the model's query would put an allergen
     gate one disjunction away from being bypassed.
  2. When the model decides a query is filter-shaped it emits q:"*", which has
     no text to embed, so hybrid ranking silently collapses on exactly the
     queries worth demoing.

Validation of what comes back lives in app/llm/interpreter.py, which is the only
consumer. Model output is untrusted input.
"""
from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.typesense.schema import COLLECTION_ALIAS

# Situational mappings live HERE, in one editable place, and are shared by both
# the Typesense system_prompt and the Claude fallback prompt so the two cannot
# drift apart.
SITUATIONAL_HINTS: dict[str, str] = {
    "exam / studying / focus / tired / don't crash": (
        "sustained_energy: rank glycemic_proxy ascending and prefer moderate protein"
    ),
    "post-workout / recovery / gains": "high_protein: rank protein_density descending",
    "light / small / snack / not too heavy": "light: rank calories ascending",
    "warm / hot / comfort / cold day": (
        "prefer warm food using tags or is_warm; keep the user's other goal"
    ),
}

SYSTEM_PROMPT = """You convert campus food searches into Typesense search parameters.

Filterable fields, and the ONLY ones you may use in filter_by:
  calories (int), protein_g, carbs_g, fat_g, fiber_g (float), sodium_mg (int),
  protein_density, satiety_score, glycemic_proxy (float), is_warm (bool),
  tags (string[]), source_type (string), venue_name (string)

NEVER write a filter on allergens, allergen_verified, diet_flags, or provenance.
Those are dietary safety constraints, they are applied deterministically outside
your output, and anything you emit touching them is discarded.

NEVER use the || operator. Express alternatives as a tags match instead.

Sort using at most one of:
  glycemic_proxy:asc   (sustained energy, avoiding a crash)
  protein_density:desc (post-workout, high protein)
  calories:asc         (light, small, a snack)
  _text_match:desc     (no clear nutritional strategy)

Situational mappings:
{hints}

Keep q as real dish words the user might see on a menu. Do not set q to "*".
Do not invent numeric limits the user did not state.
""".format(
    hints="\n".join(f"  {situation} -> {strategy}" for situation, strategy in SITUATIONAL_HINTS.items())
)

QUERY_BY = "name,description,tags,venue_name,embedding"


def ensure_model(client: Any) -> str:
    """Register the NL search model if absent. Idempotent. Returns the model id.

    Raises if NL_LLM_API_KEY is unset — callers decide whether that is fatal.
    """
    settings = get_settings()
    if not settings.nl_llm_api_key:
        raise RuntimeError("NL_LLM_API_KEY is not configured")

    model_id = settings.nl_model_id
    existing = client.nl_search_models.retrieve()
    if any(m.get("id") == model_id for m in existing):
        return model_id

    client.nl_search_models.create(
        {
            "id": model_id,
            "model_name": settings.nl_llm_model_name,
            "api_key": settings.nl_llm_api_key,
            "max_bytes": 16000,
            "temperature": 0.0,
            "system_prompt": SYSTEM_PROMPT,
        }
    )
    return model_id


def parse(client: Any, query: str) -> dict[str, Any]:
    """Ask Typesense to parse a sentence into search params. Returns generated_params.

    per_page=0 because the hits are deliberately thrown away; only the parse is
    wanted. Raises on transport failure or a missing parse — the caller degrades.
    """
    settings = get_settings()
    response = client.multi_search.perform(
        {
            "searches": [
                {
                    "collection": COLLECTION_ALIAS,
                    "q": query,
                    "query_by": QUERY_BY,
                    "nl_query": True,
                    "nl_model_id": settings.nl_model_id,
                    "nl_query_debug": True,
                    "per_page": 0,
                    "exclude_fields": "embedding",
                }
            ]
        },
        {},
    )
    result = response["results"][0]
    parsed = result.get("parsed_nl_query")
    if not parsed:
        raise ValueError(f"no parsed_nl_query in response: {result.get('error', result)}")
    return parsed.get("generated_params") or {}
