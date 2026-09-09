"""Sortable nutrient axes, mirroring the live UPlate app's Filter & Sort panel.

Single source of truth: the API validates against these keys and /api/facets
serves the same list to the UI, so the filter chips can never drift from what
the backend actually accepts.
"""

# public key -> (indexed field, display label, unit)
NUTRIENT_FIELDS: dict[str, tuple[str, str, str]] = {
    "calories": ("calories", "Calories", "cal"),
    "protein": ("protein_g", "Protein", "g"),
    "carbs": ("carbs_g", "Carbs", "g"),
    "fat": ("fat_g", "Fat", "g"),
    "sugar": ("sugar_g", "Sugar", "g"),
    "saturated_fat": ("saturated_fat_g", "Saturated Fat", "g"),
    "added_sugars": ("added_sugars_g", "Added Sugars", "g"),
    "sodium": ("sodium_mg", "Sodium", "mg"),
    "fiber": ("fiber_g", "Fiber", "g"),
    "cholesterol": ("cholesterol_mg", "Cholesterol", "mg"),
    "calcium": ("calcium_mg", "Calcium", "mg"),
    "iron": ("iron_mg", "Iron", "mg"),
}


def nutrient_sort(key: str, direction: str = "desc") -> str:
    """'iron', 'desc' -> 'iron_mg:desc'. Raises KeyError on an unknown key."""
    field = NUTRIENT_FIELDS[key][0]
    return f"{field}:{'asc' if direction == 'asc' else 'desc'}"


def catalog() -> list[dict]:
    return [
        {"key": k, "field": f, "label": label, "unit": unit}
        for k, (f, label, unit) in NUTRIENT_FIELDS.items()
    ]
