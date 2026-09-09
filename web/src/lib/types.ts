// MIRRORS api/app/schemas/search.py FIELD-FOR-FIELD.
// Change both together or not at all.

export type Provenance =
  | "OFFICIAL_FEED"
  | "CHAIN_PUBLISHED"
  | "CROWD_VERIFIED"
  | "ESTIMATED";

export type Goal = "high_protein" | "sustained_energy" | "light" | "none";

export interface UserContext {
  lat: number;
  lng: number;
  campus_id: string;
  now_minutes: number; // minutes since local midnight
  exclude_allergens: string[]; // HARD
  diet_flags: string[]; // HARD
  goal: Goal;
  radius_mi: number;
}

export interface SearchRequest {
  query: string;
  context: UserContext;
}

export interface ClearedConstraint {
  label: string; // "dairy-free"
  passed: boolean;
}

export interface Hit {
  id: string;
  name: string;
  venue_name: string;
  source_type: "dining_hall" | "off_campus";
  distance_mi: number;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  provenance: Provenance;
  allergen_verified: boolean;
  cleared: ClearedConstraint[];
  lat: number;
  lng: number;
}

export interface ReasoningTrace {
  interpreted_intent: string;
  generated_filters: string | null; // from the LLM
  explicit_filters: string; // from US — the safety layer
  chosen_sort: string;
  llm_error?: string | null;
  degraded: boolean;
}

export interface PartialMatch {
  hit: Hit;
  fails: string[]; // ["40g over your carb target"]
}

export interface SearchResponse {
  hits: Hit[];
  withheld_count: number;
  reasoning: ReasoningTrace;
  partial_matches: PartialMatch[];
  took_ms: number;
}

export const PROVENANCE_LABELS: Record<Provenance, string> = {
  OFFICIAL_FEED: "Verified",
  CHAIN_PUBLISHED: "Published",
  CROWD_VERIFIED: "Community",
  ESTIMATED: "Estimated",
};

export const PROVENANCE_COLORS: Record<Provenance, string> = {
  OFFICIAL_FEED: "#3F6B4A",
  CHAIN_PUBLISHED: "#4A6B7C",
  CROWD_VERIFIED: "#8A7040",
  ESTIMATED: "#8A6A6A",
};
