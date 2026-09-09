import type { Hit } from "../lib/types";
import { PROVENANCE_LABELS, PROVENANCE_COLORS } from "../lib/types";
import { tokens } from "../lib/tokens";

interface ResultCardProps {
  hit: Hit;
  selected?: boolean;
  onSelect?: (id: string) => void;
}

const IMAGE_SIZE = 64;

export default function ResultCard({ hit, selected, onSelect }: ResultCardProps) {
  return (
    <button
      onClick={() => onSelect?.(hit.id)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        width: "100%",
        textAlign: "left",
        background: tokens.surface,
        border: `1px solid ${selected ? tokens.accent : tokens.outline}`,
        borderRadius: 16,
        padding: "8px 12px",
        cursor: "pointer",
        fontFamily: tokens.font,
      }}
    >
      {/* image placeholder: straight edge on the left, filled semicircle bulge on
          the right, inset within the card's border on all sides — real thumbnail
          wiring is a later phase */}
      <div
        aria-hidden
        style={{
          width: IMAGE_SIZE,
          height: IMAGE_SIZE,
          flexShrink: 0,
          borderTopRightRadius: IMAGE_SIZE / 2,
          borderBottomRightRadius: IMAGE_SIZE / 2,
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
