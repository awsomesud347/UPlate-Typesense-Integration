// Fixture SearchResponse for building UI without a running backend.
// Matches api/app/routers/search.py stub output.
import type { SearchResponse } from "./types";

export const FIXTURE_SEARCH_RESPONSE: SearchResponse = {
  hits: [
    {
      id: "wiley-grilled-chicken",
      name: "Grilled Chicken Breast",
      venue_name: "Wiley Dining Court",
      source_type: "dining_hall",
      distance_mi: 0.3,
      calories: 280,
      protein_g: 42.0,
      carbs_g: 2.0,
      fat_g: 8.0,
      provenance: "OFFICIAL_FEED",
      allergen_verified: true,
      cleared: [
        { label: "dairy-free", passed: true },
        { label: "42g protein", passed: true },
      ],
      lat: 40.4286,
      lng: -86.9207,
    },
    {
      id: "chipotle-chicken-bowl",
      name: "Chicken Burrito Bowl (no cheese)",
      venue_name: "Chipotle - Chauncey Hill",
      source_type: "off_campus",
      distance_mi: 0.6,
      calories: 510,
      protein_g: 51.0,
      carbs_g: 41.0,
      fat_g: 16.5,
      provenance: "CHAIN_PUBLISHED",
      allergen_verified: true,
      cleared: [
        { label: "dairy-free", passed: true },
        { label: "51g protein", passed: true },
      ],
      lat: 40.4241,
      lng: -86.9081,
    },
  ],
  withheld_count: 2,
  reasoning: {
    interpreted_intent: "high protein, dairy excluded (FIXTURE DATA)",
    generated_filters: null,
    explicit_filters:
      "campus_id:=purdue && allergens:!=dairy && allergen_verified:true",
    chosen_sort: "location(...):asc, protein_density:desc",
    degraded: false,
  },
  partial_matches: [],
  took_ms: 42,
};
