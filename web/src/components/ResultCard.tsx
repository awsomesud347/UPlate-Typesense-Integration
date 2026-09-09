import type { Hit } from "../lib/types";
import { PROVENANCE_LABELS, PROVENANCE_COLORS } from "../lib/types";
import { tokens } from "../lib/tokens";

interface ResultCardProps {
  hit: Hit;
  selected?: boolean;
  onSelect?: (id: string) => void;
  onOpenDetail?: (hit: Hit) => void;
}

const CIRCLE_DIAMETER = 72;
const VISIBLE_FRACTION = 0.68; // how much of the circle's width shows past the card edge
const CIRCLE_CENTER_OFFSET = CIRCLE_DIAMETER * (VISIBLE_FRACTION - 0.5); // shift center rightward
const VISIBLE_WIDTH = CIRCLE_DIAMETER * VISIBLE_FRACTION;
const CONTENT_LEFT_INSET = VISIBLE_WIDTH + 12; // visible portion + gap before text

export default function ResultCard({ hit, selected, onSelect, onOpenDetail }: ResultCardProps) {
  return (
    <button
      onClick={() => {
        onSelect?.(hit.id);
        onOpenDetail?.(hit);
      }}
      style={{
        position: "relative",
        display: "flex",
        alignItems: "center",
        gap: 12,
        width: "100%",
        textAlign: "left",
        background: tokens.surface,
        border: `1px solid ${selected ? tokens.accent : tokens.outline}`,
        borderRadius: 16,
        padding: `10px 12px 10px ${CONTENT_LEFT_INSET}px`,
        cursor: "pointer",
        fontFamily: tokens.font,
        overflow: "hidden", // crops the circle at the card's left edge
      }}
    >
      {/* a full circle shifted so most of its width shows past the card's left
          edge — the card's own overflow:hidden clips the rest away. Real
          thumbnail wiring is a later phase. */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          left: CIRCLE_CENTER_OFFSET,
          top: "50%",
          width: CIRCLE_DIAMETER,
          height: CIRCLE_DIAMETER,
          transform: "translate(-50%, -50%)",
          borderRadius: "50%",
          flexShrink: 0,
          background: PROVENANCE_COLORS[hit.provenance],
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "white",
          fontSize: 20,
          fontWeight: 700,
        }}
      >
        {hit.venue_name.charAt(0)}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <strong style={{ fontSize: 14, color: tokens.textPrimary }}>{hit.name}</strong>
          <span
            style={{
              fontSize: 10,
              color: "white",
              background: PROVENANCE_COLORS[hit.provenance],
              borderRadius: 6,
              padding: "1px 6px",
              flexShrink: 0,
            }}
          >
            {PROVENANCE_LABELS[hit.provenance]}
          </span>
        </div>
        <div style={{ fontSize: 12, color: tokens.textSecondary }}>
          {hit.venue_name} · {hit.distance_mi} mi
        </div>
        <div
          style={{
            fontSize: 12,
            color: tokens.textPrimary,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {hit.calories} cal · {hit.protein_g}g P · {hit.carbs_g}g C · {hit.fat_g}g F
        </div>
      </div>

      <span aria-hidden style={{ color: tokens.accent, fontSize: 18, paddingRight: 4 }}>
        ›
      </span>
    </button>
  );
}
