"""Data endpoints: browse the index without a natural-language query.

These back the venue/station views in the live UPlate app (see the Earhart
"Filter & Sort" screen). Deliberately thin — they expose Typesense facets and
sorts directly. Architecture/wiring lives elsewhere; this is the data surface.
"""
from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.constraints.exclusions import exclusion_fragments
from app.constraints.nutrients import NUTRIENT_FIELDS, catalog, nutrient_sort
from app.constraints.provenance import PROVENANCE_TIERS, VERIFICATION_GATE
from app.typesense.client import admin_client

router = APIRouter()

COLLECTION = "food_items"


def _scope(campus_id: str | None) -> str:
    """Campus + the retail-only scope, so browse endpoints show the same universe
    that search does."""
    cid = campus_id or get_settings().campus_id
    f = f"campus_id:={cid}"
    if get_settings().retail_only:
        f += " && source_type:=off_campus"
    return f


def _search(params: dict) -> dict:
    try:
        res = admin_client().multi_search.perform(
            {"searches": [{"collection": COLLECTION, **params}]}, {}
        )["results"][0]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Typesense error: {e}") from e
    if "error" in res:
        raise HTTPException(status_code=502, detail=res["error"])
    return res


def _facet_counts(res: dict, field: str) -> list[dict]:
    for f in res.get("facet_counts", []):
        if f["field_name"] == field:
            return [{"value": c["value"], "count": c["count"]} for c in f["counts"]]
    return []


@router.get("/facets")
def facets(campus_id: str | None = None) -> dict:
    """Everything the UI needs to build filter chips, sourced from live data so
    the options can never drift from what is actually in the index."""
    res = _search(
        {
            "q": "*",
            "query_by": "name",
            "filter_by": _scope(campus_id),
            "facet_by": "tags,allergens,diet_flags,station,venue_name,source_type,provenance",
            "max_facet_values": 100,
            "per_page": 0,
        }
    )
    return {
        "total_items": res.get("found", 0),
        "tags": _facet_counts(res, "tags"),
        "allergens": _facet_counts(res, "allergens"),
        "diet_flags": _facet_counts(res, "diet_flags"),
        "stations": _facet_counts(res, "station"),
        "venues": _facet_counts(res, "venue_name"),
        "source_types": _facet_counts(res, "source_type"),
        "provenance": _facet_counts(res, "provenance"),
        "nutrients": catalog(),
        "provenance_tiers": PROVENANCE_TIERS,
    }


@router.get("/venues")
def venues(campus_id: str | None = None) -> dict:
    """Venue list with item counts. One doc per venue is fetched to recover the
    venue's coordinates and type, which facets alone don't carry."""
    res = _search(
        {
            "q": "*",
            "query_by": "name",
            "filter_by": _scope(campus_id),
            "facet_by": "venue_id",
            "max_facet_values": 200,
            "per_page": 250,
            "include_fields": "venue_id,venue_name,source_type,location",
        }
    )
    counts = {c["value"]: c["count"] for c in _facet_counts(res, "venue_id") for _ in [0]}
    seen: dict[str, dict] = {}
    for hit in res.get("hits", []):
        d = hit["document"]
        if d["venue_id"] not in seen:
            seen[d["venue_id"]] = {
                "venue_id": d["venue_id"],
                "venue_name": d["venue_name"],
                "source_type": d["source_type"],
                "lat": d["location"][0],
                "lng": d["location"][1],
                "item_count": counts.get(d["venue_id"], 0),
            }
    return {"venues": sorted(seen.values(), key=lambda v: -v["item_count"])}


@router.get("/venues/{venue_id}/items")
def venue_items(
    venue_id: str,
    sort_nutrient: str | None = Query(None, description="e.g. iron, protein, calories"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    station: str | None = None,
    exclude_allergens: list[str] = Query(default=[]),
    diet_flags: list[str] = Query(default=[]),
    restricted: str = Query("hide", pattern="^(hide|highlight)$"),
    per_page: int = Query(100, le=250),
) -> dict:
    """Items at one venue — backs the venue detail screen.

    `restricted` mirrors the live app's Highlight/Hide toggle:
      hide      — exclusions filtered out, unverified items withheld and counted
      highlight — clashing items returned but flagged `restricted: true`, so the
                  UI can mark them. The user asked to see them; nothing is
                  presented as safe that wasn't verified.
    """
    if sort_nutrient and sort_nutrient not in NUTRIENT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown nutrient '{sort_nutrient}'. Valid: {sorted(NUTRIENT_FIELDS)}",
        )

    base_filter = [f"venue_id:={venue_id}"]
    if station:
        base_filter.append(f"station:={station}")

    hard = exclusion_fragments(exclude_allergens, diet_flags)
    gated_filter = list(base_filter)
    if hard and restricted == "hide":
        gated_filter += hard + [VERIFICATION_GATE]

    sort_by = nutrient_sort(sort_nutrient, sort_dir) if sort_nutrient else "calories:asc"

    res = _search(
        {
            "q": "*",
            "query_by": "name",
            "filter_by": " && ".join(gated_filter),
            "sort_by": sort_by,
            "facet_by": "station",
            "exclude_fields": "embedding",
            "per_page": per_page,
        }
    )

    withheld = 0
    if hard and restricted == "hide":
        ungated = _search(
            {
                "q": "*",
                "query_by": "name",
                "filter_by": " && ".join(base_filter + hard),
                "per_page": 0,
            }
        )
        withheld = max(ungated.get("found", 0) - res.get("found", 0), 0)

    items = []
    for hit in res.get("hits", []):
        d = hit["document"]
        clashes = [a for a in exclude_allergens if a.lower() in d.get("allergens", [])]
        clashes += [f for f in diet_flags if f.lower() not in d.get("diet_flags", [])]
        items.append(
            {
                **d,
                "restricted": bool(clashes) or (bool(hard) and not d["allergen_verified"]),
                "restricted_reasons": clashes
                or (["allergen data unverified"] if hard and not d["allergen_verified"] else []),
            }
        )

    return {
        "venue_id": venue_id,
        "items": items,
        "found": res.get("found", 0),
        "withheld_count": withheld,
        "stations": _facet_counts(res, "station"),
        "sorted_by": sort_by,
        "restricted_mode": restricted,
    }


@router.get("/items/{item_id}")
def item(item_id: str) -> dict:
    try:
        return admin_client().collections[COLLECTION].documents[item_id].retrieve()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Item '{item_id}' not found: {e}") from e
