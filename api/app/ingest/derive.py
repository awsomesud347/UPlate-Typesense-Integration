"""Precomputed ranking axes. Pure functions, no I/O, no Typesense imports.

Typesense sort_by cannot do arithmetic, so every ratio/composite lives here and is
stored as a plain numeric field at index time.
"""

WARM_TAGS = {"warm", "hot", "soup", "stew", "grilled", "roasted", "baked", "fried"}


def protein_density(protein_g: float, calories: float) -> float:
    """Grams of protein per 100 kcal. 0 for zero-calorie items (no div-by-zero)."""
    if calories <= 0:
        return 0.0
    return round(protein_g / calories * 100, 2)


def satiety_score(protein_g: float, fiber_g: float) -> float:
    """Higher = more filling. Monotonic in both protein and fiber."""
    return round(protein_g * 1.0 + fiber_g * 2.0, 2)


def glycemic_proxy(carbs_g: float, fiber_g: float) -> float:
    """Crash risk. High net carbs with little fiber scores high (bad before an exam)."""
    return round(max(carbs_g - fiber_g, 0.0) / (fiber_g + 1.0), 2)


def is_warm(tags: list[str]) -> bool:
    return any(t.lower() in WARM_TAGS for t in tags)
