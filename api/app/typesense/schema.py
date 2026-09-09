"""Collection definitions, versioned. The live collection is always reached via
the alias COLLECTION_ALIAS; concrete versions are food_items_v1, v2, ..."""

COLLECTION_ALIAS = "food_items"


def food_items_schema(version: int) -> dict:
    return {
        "name": f"food_items_v{version}",
        "fields": [
            {"name": "name", "type": "string"},
            {"name": "description", "type": "string"},
            {"name": "venue_name", "type": "string", "facet": True},
            {"name": "venue_id", "type": "string", "facet": True},
            {"name": "source_type", "type": "string", "facet": True},  # dining_hall | off_campus
            {"name": "campus_id", "type": "string", "facet": True},
            {"name": "location", "type": "geopoint"},
            # --- soft: ranking inputs ---
            {"name": "tags", "type": "string[]", "facet": True},
            {"name": "calories", "type": "int32", "facet": True},
            {"name": "protein_g", "type": "float"},
            {"name": "carbs_g", "type": "float"},
            {"name": "fat_g", "type": "float"},
            {"name": "fiber_g", "type": "float"},
            {"name": "sodium_mg", "type": "int32"},
            # --- hard: exclusion inputs ---
            {"name": "allergens", "type": "string[]", "facet": True},
            {"name": "diet_flags", "type": "string[]", "facet": True},
            {"name": "provenance", "type": "string", "facet": True},
            {"name": "allergen_verified", "type": "bool", "facet": True},
            # --- precomputed ranking axes (derive.py; sort_by can't do arithmetic) ---
            {"name": "protein_density", "type": "float"},
            {"name": "satiety_score", "type": "float"},
            {"name": "glycemic_proxy", "type": "float"},
            {"name": "is_warm", "type": "bool"},
            # --- availability (minutes since midnight) ---
            {"name": "available_from", "type": "int32"},
            {"name": "available_to", "type": "int32"},
            {
                "name": "embedding",
                "type": "float[]",
                "embed": {
                    "from": ["name", "description", "tags", "venue_name"],
                    "model_config": {"model_name": "ts/all-MiniLM-L12-v2"},
                },
            },
        ],
        "default_sorting_field": "calories",
    }
