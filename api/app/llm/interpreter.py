"""Claude query-understanding layer. [BACKEND DEV OWNS THIS — Phase 4]

Contract: interpret(query) -> Interpretation. It NEVER sees or emits allergen /
diet exclusions — those come from UserContext and are applied as the explicit
filter_by in query_builder. The LLM interprets vibes; it does not enforce safety.

Must: cache by normalized query (TTL ~10 min, demo insurance), and degrade
gracefully — on any API failure return Interpretation(degraded=True) so search
falls back to plain keyword. Never raise out of interpret().
"""
from dataclasses import dataclass, field

# Situational mappings live HERE, in one editable place, not inside prompts
# scattered through query code.
SITUATIONAL_HINTS = {
    "exam / focus / don't crash": "sort glycemic_proxy:asc, prefer moderate protein",
    "post-workout / gains": "sort protein_density:desc",
    "light / small / snack": "sort calories:asc",
    "warm / comfort": "boost is_warm via _eval",
}


@dataclass
class Interpretation:
    intent: str = ""  # human-readable, e.g. "low-glycemic, moderate protein"
    soft_filter_by: str | None = None  # e.g. "calories:<600" — soft prefs ONLY
    goal: str = "none"  # maps into constraints/goals.py axes
    search_terms: str = ""  # cleaned q for Typesense
    degraded: bool = False
    error: str | None = None
    raw: dict = field(default_factory=dict)


def interpret(query: str) -> Interpretation:
    # TODO(Phase 4): anthropic tool-use call producing the fields above; cache; degrade.
    return Interpretation(
        intent="(LLM layer not wired yet — keyword search)",
        search_terms=query,
        degraded=True,
    )
