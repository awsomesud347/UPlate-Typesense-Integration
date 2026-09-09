import { useLayoutEffect, useRef, useState } from "react";
import type { Hit } from "../lib/types";
import { tokens } from "../lib/tokens";

interface ItemMapProps {
  hits: Hit[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
}

// SKELETON — Phase 6 replaces this with real MapLibre GL + clustering.
// Pins are placed by hashing hit.id to a stable position so the layout doesn't
// jump between renders; this is NOT a real geo projection.
function pinPosition(id: string): { leftPct: number; topPct: number } {
  let hash = 0;
  for (const ch of id) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff;
  return { leftPct: 15 + (hash % 70), topPct: 15 + ((hash >> 4) % 65) }; // 15–85 / 15–80
}

const ZOOM = 2.2;
// Where the selected point should land: horizontally centered, near the TOP of
// the map area so it stays visible above the results sheet once it opens.
const TARGET = { leftPct: 54, topPct: 12 };

export default function ItemMap({ hits, selectedId, onSelect }: ItemMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [transform, setTransform] = useState<{ x: number; y: number; originX: number; originY: number; scale: number }>({
    x: 0,
    y: 0,
    originX: 0,
    originY: 0,
    scale: 1,
  });

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const selected = selectedId ? hits.find((h) => h.id === selectedId) : null;
    if (!selected) {
      setTransform({ x: 0, y: 0, originX: 0, originY: 0, scale: 1 });
      return;
    }
    const { width, height } = el.getBoundingClientRect();
    const pos = pinPosition(selected.id);
    const originX = (pos.leftPct / 100) * width;
    const originY = (pos.topPct / 100) * height;
    const targetX = (TARGET.leftPct / 100) * width;
    const targetY = (TARGET.topPct / 100) * height;
    // Scale is anchored at the point itself (transform-origin), so the point
    // doesn't move under the scale — only the translate below moves it, to TARGET.
    setTransform({ x: targetX - originX, y: targetY - originY, originX, originY, scale: ZOOM });
  }, [selectedId, hits]);

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%", height: "100%" }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
          transformOrigin: `${transform.originX}px ${transform.originY}px`,
          transition: "transform 550ms cubic-bezier(.22,1,.36,1)",
          background: `repeating-linear-gradient(45deg, ${tokens.surfaceMuted}, ${tokens.surfaceMuted} 12px, ${tokens.background} 12px, ${tokens.background} 24px)`,
        }}
      >
        {hits.map((hit) => {
          const pos = pinPosition(hit.id);
          const isSelected = hit.id === selectedId;
          return (
            <button
              key={hit.id}
              aria-label={`${hit.name} at ${hit.venue_name}`}
              onClick={() => onSelect?.(hit.id)}
              style={{
                position: "absolute",
                left: `${pos.leftPct}%`,
                top: `${pos.topPct}%`,
                transform: "translate(-50%, -100%)",
                width: isSelected ? 32 / transform.scale : 26 / transform.scale,
                height: isSelected ? 32 / transform.scale : 26 / transform.scale,
                borderRadius: "50% 50% 50% 0",
                rotate: "-45deg",
                background: isSelected ? tokens.accent : tokens.surface,
                border: `${2 / transform.scale}px solid ${tokens.accent}`,
                cursor: "pointer",
                padding: 0,
              }}
            />
          );
        })}
      </div>

      <span
        style={{
          position: "absolute",
          top: 8,
          left: 8,
          fontSize: 10,
          color: tokens.textSecondary,
          background: tokens.surface,
          border: `1px solid ${tokens.outline}`,
          padding: "2px 6px",
          borderRadius: 4,
        }}
      >
        map placeholder — Phase 6 wires MapLibre
      </span>
    </div>
  );
}
