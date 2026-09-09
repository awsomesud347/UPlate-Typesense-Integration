import { useEffect, useState } from "react";
import { api, demoContext } from "./lib/api";
import type { SearchResponse } from "./lib/types";
import { PROVENANCE_COLORS, PROVENANCE_LABELS } from "./lib/types";

// Minimal wiring proof for Phase 0. UI dev: replace with real components
// (SearchBar, ResultCard, ReasoningPanel, WithheldNotice, EmptyState, PhoneFrame)
// per BUILD_PLAN.md §7 tokens. Data flow below is the pattern to keep.
export default function App() {
  const [health, setHealth] = useState<string>("checking…");
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h.status))
      .catch((e) => setHealth(`backend unreachable: ${e.message}`));
  }, []);

  async function runSearch() {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.search({ query, context: demoContext() }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        maxWidth: 390,
        margin: "0 auto",
        padding: 16,
        fontFamily: "Inter, system-ui, sans-serif",
        background: "#FBFAF8",
        minHeight: "100vh",
        color: "#1C1B19",
      }}
    >
      <h1 style={{ fontSize: 20 }}>UPlate Search</h1>
      <p style={{ fontSize: 12, color: "#6E6A63" }}>backend: {health}</p>

      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && runSearch()}
          placeholder="exam in an hour, don't want to crash"
          aria-label="Search food"
          style={{ flex: 1, padding: 10, borderRadius: 8, border: "1px solid #E4E0D9" }}
        />
        <button
          onClick={runSearch}
          disabled={loading}
          style={{
            padding: "10px 16px",
            borderRadius: 8,
            border: "none",
            background: "#3F6B4A",
            color: "white",
          }}
        >
          {loading ? "…" : "Search"}
        </button>
      </div>

      {error && <p style={{ color: "#8A4A4A" }}>{error}</p>}

      {result && (
        <>
          <p style={{ fontSize: 13, color: "#6E6A63" }}>
            {result.reasoning.interpreted_intent}
          </p>
          {result.withheld_count > 0 && (
            <p style={{ fontSize: 12, color: "#8A6A6A" }}>
              {result.withheld_count} items hidden — allergen data unverified
            </p>
          )}
          {result.hits.map((hit) => (
            <div
              key={hit.id}
              style={{
                background: "#FFFFFF",
                border: "1px solid #E4E0D9",
                borderRadius: 12,
                padding: 12,
                marginTop: 8,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <strong>{hit.name}</strong>
                <span
                  style={{
                    fontSize: 11,
                    color: "white",
                    background: PROVENANCE_COLORS[hit.provenance],
                    borderRadius: 6,
                    padding: "2px 6px",
                  }}
                >
                  {PROVENANCE_LABELS[hit.provenance]}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "#6E6A63" }}>
                {hit.venue_name} · {hit.distance_mi} mi ·{" "}
                {hit.source_type === "dining_hall" ? "on campus" : "off campus"}
              </div>
              <div style={{ fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                {hit.calories} cal · {hit.protein_g}g P · {hit.carbs_g}g C ·{" "}
                {hit.fat_g}g F
              </div>
              <div style={{ fontSize: 12, color: "#3F6B4A" }}>
                {hit.cleared.map((c) => `${c.label} ✓`).join(" · ")}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
