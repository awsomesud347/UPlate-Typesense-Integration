"""Raw seed row → indexed document.

RAISES on a missing allergens key. An empty allergen list means "verified none";
absence means "unknown" and must never silently become safety-clearing. Rows with
unknown allergens must carry allergens=[] explicitly AND allergen_verified=false
AND provenance=ESTIMATED, set by the data author, on purpose.
"""
from app.ingest import derive


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
    return doc
