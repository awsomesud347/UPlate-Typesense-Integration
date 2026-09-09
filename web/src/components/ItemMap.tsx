import { useEffect, useRef } from "react";
import { Map as MapLibreMap, Marker, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Hit } from "../lib/types";
import { tokens } from "../lib/tokens";

interface ItemMapProps {
  hits: Hit[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

// Free, keyless OSM raster tiles — no API key, no billing surprise (BUILD_PLAN §2).
const OSM_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: [
        "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://b.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://c.tile.openstreetmap.org/{z}/{x}/{y}.png",
      ],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

// Real map, but per user's call — NOT real per-item geo. Pins keep the same
// hashed, deterministic "simplified" positions as before, just expressed as a
// small lng/lat offset around campus instead of a screen percentage, so they
// behave correctly as the real map pans/zooms underneath them.
//
// Hashed by venue_name (not item id) so every item from the same restaurant
// lands on the same point instead of scattering across the map. Frontend-only
// grouping — the API contract doesn't expose a venue_id to hash on instead.
const CENTER: [number, number] = [-86.9111, 40.4249]; // matches api.ts demoContext()
const BASE_ZOOM = 14.5;
const FOCUS_ZOOM = 16.5;

function venueLngLat(venueName: string): [number, number] {
  let hash = 0;
  for (const ch of venueName) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff;
  const leftPct = 15 + (hash % 70); // 15–85, same distribution as before
  const topPct = 15 + ((hash >> 4) % 65);
  const lng = CENTER[0] + ((leftPct - 50) / 50) * 0.012;
  const lat = CENTER[1] - ((topPct - 50) / 50) * 0.009;
  return [lng, lat];
}

// Marker writes its own `translate(...)` position directly onto the element's
// style.transform on every map move/zoom — it OWNS that property. Our teardrop
// shape needs `rotate(-45deg)` too, so it lives on a nested child instead of
// the marker's root element; otherwise whichever of us wrote `transform` last
// wins, and the loser's translate gets wiped, snapping the pin back to (0,0).
function applyPinStyle(inner: HTMLDivElement, isSelected: boolean): void {
  const size = isSelected ? 32 : 26;
  Object.assign(inner.style, {
    width: `${size}px`,
    height: `${size}px`,
    borderRadius: "50% 50% 50% 0",
    transform: "rotate(-45deg)",
    background: isSelected ? tokens.accent : tokens.surface,
    border: `2px solid ${tokens.accent}`,
    cursor: "pointer",
  });
}

function pinElement(isSelected: boolean): HTMLDivElement {
  const wrapper = document.createElement("div");
  const inner = document.createElement("div");
  applyPinStyle(inner, isSelected);
  wrapper.appendChild(inner);
  return wrapper;
}

function youElement(): HTMLDivElement {
  const el = document.createElement("div");
  Object.assign(el.style, {
    width: "14px",
    height: "14px",
    borderRadius: "50%",
    background: "#4A9DFF",
    border: "2px solid white",
    boxShadow: "0 0 0 6px rgba(74,157,255,0.25)",
  });
  return el;
}

export default function ItemMap({ hits, selectedId, onSelect }: ItemMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<globalThis.Map<string, Marker>>(new globalThis.Map());

  // Create the map once.
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new MapLibreMap({
      container: containerRef.current,
      style: OSM_STYLE,
      center: CENTER,
      zoom: BASE_ZOOM,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    new Marker({ element: youElement() }).setLngLat(CENTER).addTo(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Keep one marker per hit in sync with the current result set.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    const seen = new Set<string>();
    for (const hit of hits) {
      seen.add(hit.id);
      const isSelected = hit.id === selectedId;
      const existing = markersRef.current.get(hit.id);
      if (existing) {
        const inner = existing.getElement().firstElementChild as HTMLDivElement | null;
        if (inner) applyPinStyle(inner, isSelected);
      } else {
        const marker = new Marker({ element: pinElement(isSelected) })
          .setLngLat(venueLngLat(hit.venue_name))
          .addTo(map);
        marker.getElement().addEventListener("click", () => onSelect?.(hit.id));
        markersRef.current.set(hit.id, marker);
      }
    }
    for (const [id, marker] of markersRef.current) {
      if (!seen.has(id)) {
        marker.remove();
        markersRef.current.delete(id);
      }
    }
  }, [hits, selectedId, onSelect]);

  // Pan/zoom to the selected point, biased toward the top of the visible area
  // (bottom padding reserves room for the results sheet below).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const selected = selectedId ? hits.find((h) => h.id === selectedId) : null;
    const containerHeight = containerRef.current?.clientHeight ?? 0;

    if (!selected) {
      map.flyTo({ center: CENTER, zoom: BASE_ZOOM, duration: 550 });
      return;
    }
    map.flyTo({
      center: venueLngLat(selected.venue_name),
      zoom: FOCUS_ZOOM,
      padding: { top: 20, bottom: containerHeight * 0.72, left: 20, right: 20 },
      duration: 550,
    });
  }, [selectedId, hits]);

  return <div ref={containerRef} style={{ position: "relative", width: "100%", height: "100%" }} />;
}
