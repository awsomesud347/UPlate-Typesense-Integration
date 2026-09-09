"""Raw seed row → indexed document.

RAISES on a missing allergens key. An empty allergen list means "verified none";
absence means "unknown" and must never silently become safety-clearing. Rows with
unknown allergens must carry allergens=[] explicitly AND allergen_verified=false
AND provenance=ESTIMATED, set by the data author, on purpose.
"""
from app.ingest import derive

EXTENDED_NUTRIENTS = (
    "sugar_g",
    "saturated_fat_g",
    "added_sugars_g",
    "cholesterol_mg",
    "calcium_mg",
    "iron_mg",
)


class MissingAllergenData(ValueError):
    pass


def normalize(raw: dict) -> dict:
    if "allergens" not in raw:
        raise MissingAllergenData(
            f"Item '{raw.get('name', '?')}' has no allergens key. Refusing to default "
            "to [] — set allergens=[] with allergen_verified=false explicitly if unknown."
        )
    doc = dict(raw)
    doc["id"] = raw["id"]
    doc["location"] = [raw["lat"], raw["lng"]]
    doc.pop("lat", None)
    doc.pop("lng", None)
    doc["protein_density"] = derive.protein_density(raw["protein_g"], raw["calories"])
    doc["satiety_score"] = derive.satiety_score(raw["protein_g"], raw["fiber_g"])
    doc["glycemic_proxy"] = derive.glycemic_proxy(raw["carbs_g"], raw["fiber_g"])
    doc["is_warm"] = derive.is_warm(raw["tags"])
    doc.setdefault("available_from", 0)
    doc.setdefault("available_to", 1439)
    doc.setdefault("station", "")
    # Extended nutrients (see NUTRIENT_FIELDS) are sparse in seed data. Defaulting
    # to 0 keeps every document sortable on every axis. Unlike allergens, a missing
    # micronutrient is not a safety claim, so a default is safe here.
    for field in EXTENDED_NUTRIENTS:
        doc.setdefault(field, 0.0)
    return doc
