"""Goal → precomputed ranking axis. Data, not control flow — new goals are new
entries here, never new if/elif branches in query code."""

# goal -> (sort field, direction)
GOAL_AXES: dict[str, tuple[str, str]] = {
    "high_protein": ("protein_density", "desc"),
    "sustained_energy": ("glycemic_proxy", "asc"),  # low crash risk first
    "light": ("calories", "asc"),
    "none": ("_text_match", "desc"),
}


def goal_sort(goal: str) -> str:
    field, direction = GOAL_AXES.get(goal, GOAL_AXES["none"])
    return f"{field}:{direction}"
