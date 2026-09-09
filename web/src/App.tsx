import { useState } from "react";
import { api, demoContext } from "./lib/api";
import type { SearchResponse } from "./lib/types";
import { tokens } from "./lib/tokens";
import PhoneFrame from "./components/PhoneFrame";
import SearchBar from "./components/SearchBar";
import ItemMap from "./components/ItemMap";
import ResultsSheet from "./components/ResultsSheet";

export default function App() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  async function runSearch() {
    setLoading(true);
    setError(null);
    try {
      const response = await api.search({ query, context: demoContext() });
      setResult(response);
      setSelectedId(response.hits[0]?.id ?? null); // auto-center map on top result
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  function handleImageUpload(_file: File) {
    // SKELETON — Phase 8 wires this to POST /api/photo (CLIP recognition).
    setError("Photo search isn't wired up yet.");
  }

  const hits = result?.hits ?? [];

  return (
    <PhoneFrame>
      {/* static header, per the reference app */}
      <div style={{ flexShrink: 0, padding: "16px 16px 12px" }}>
        <h1 style={{ margin: "0 0 12px", fontSize: 24, fontWeight: 800 }}>UPlate</h1>
        <SearchBar
          value={query}
          onChange={setQuery}
          onSubmit={runSearch}
          onImageUpload={handleImageUpload}
          loading={loading}
        />
        {error && (
          <p style={{ margin: "8px 0 0", fontSize: 12, color: tokens.danger }}>{error}</p>
        )}
      </div>

      {/* map fills the remaining space below the header, rounded */}
      <div style={{ flex: 1, position: "relative", margin: "0 16px 16px", overflow: "hidden", borderRadius: 20 }}>
        <ItemMap hits={hits} selectedId={selectedId} onSelect={setSelectedId} />
      </div>

      <ResultsSheet
        hits={hits}
        withheldCount={result?.withheld_count ?? 0}
        interpretedIntent={result?.reasoning.interpreted_intent}
        selectedId={selectedId}
        onSelect={setSelectedId}
        visible={result !== null}
      />
    </PhoneFrame>
  );
}
