import pytest

from app.ingest import derive
from app.ingest.normalize import MissingAllergenData, normalize


def test_protein_density():
    assert derive.protein_density(30.0, 500) == 6.0


def test_protein_density_zero_calories():
    assert derive.protein_density(10.0, 0) == 0.0  # no ZeroDivisionError


def test_glycemic_proxy_ordering():
    high_carb_low_fiber = derive.glycemic_proxy(60.0, 1.0)
    low_carb_high_fiber = derive.glycemic_proxy(20.0, 10.0)
    assert high_carb_low_fiber > low_carb_high_fiber


def test_satiety_monotonic():
    base = derive.satiety_score(10.0, 5.0)
    assert derive.satiety_score(20.0, 5.0) > base
    assert derive.satiety_score(10.0, 10.0) > base


def test_is_warm():
    assert derive.is_warm(["soup", "vegan"]) is True
    assert derive.is_warm(["cold", "salad"]) is False


def test_normalize_raises_on_missing_allergens():
    raw = {
        "id": "x", "name": "Mystery Dish", "description": "?", "venue_name": "?",
        "venue_id": "v", "source_type": "off_campus", "campus_id": "purdue",
        "lat": 40.0, "lng": -86.0, "tags": [], "calories": 100, "protein_g": 1.0,
        "carbs_g": 1.0, "fat_g": 1.0, "fiber_g": 1.0, "sodium_mg": 10,
        "diet_flags": [], "provenance": "ESTIMATED", "allergen_verified": False,
    }
    with pytest.raises(MissingAllergenData):
        normalize(raw)  # absence must never silently become safety-clearing
