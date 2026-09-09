import { useEffect, useState } from "react";
import type { Hit } from "../lib/types";
import { tokens } from "../lib/tokens";

interface NutritionFactsProps {
  hit: Hit;
  onClose: () => void;
  onLogFood: () => void;
}

// Standard FDA reference daily values — used only because this app doesn't yet
// have personalized targets wired to the UI. Swap for real personalized values
// once the API contract exposes them.
const DAILY_VALUE = { fat_g: 78, carbs_g: 275, protein_g: 50 };

function pct(value: number, ref: number): string {
  return `${Math.round((value / ref) * 100)}%`;
}

interface RowProps {
  label: string;
  value: string;
  percent?: string;
  indent?: number;
  bold?: boolean;
}

function Row({ label, value, percent, indent = 0, bold = false }: RowProps) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        padding: "8px 0",
        borderBottom: `1px solid ${tokens.outline}`,
        paddingLeft: indent * 16,
      }}
    >
      <span style={{ fontSize: 14, fontWeight: bold ? 700 : 400, color: tokens.textPrimary }}>
        {bold ? <strong>{label}</strong> : label} {value}
      </span>
      {percent && (
        <strong style={{ fontSize: 14, color: tokens.textPrimary, flexShrink: 0 }}>
          {percent}
        </strong>
      )}
    </div>
  );
}

export default function NutritionFacts({ hit, onClose, onLogFood }: NutritionFactsProps) {
  // Slides up on mount rather than snapping into place. Starts off-screen,
  // flips to entered on the next frame so the browser animates the transition.
  const [entered, setEntered] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setEntered(true));
    return () => cancelAnimationFrame(id);
  }, []);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 20,
        display: "flex",
        flexDirection: "column",
        background: tokens.background,
        fontFamily: tokens.font,
        color: tokens.textPrimary,
        transform: `translateY(${entered ? 0 : "100%"})`,
        transition: "transform 320ms cubic-bezier(.22,1,.36,1)",
      }}
    >
      <div style={{ flexShrink: 0, padding: "16px 16px 0" }}>
        <button
          onClick={onClose}
          aria-label="Close nutrition facts"
          style={{
            border: "none",
            background: "transparent",
            color: tokens.textSecondary,
            fontSize: 15,
            padding: 0,
            cursor: "pointer",
          }}
        >
          ‹ Back
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "8px 20px 96px" }}>
        <h1 style={{ textAlign: "center", fontSize: 26, margin: "8px 0 16px" }}>{hit.name}</h1>

        {/* decorative — no rating data in the API contract yet */}
        <div style={{ display: "flex", justifyContent: "center", gap: 4, marginBottom: 16 }}>
          {Array.from({ length: 5 }).map((_, i) => (
            <span key={i} style={{ color: tokens.outline, fontSize: 20 }} aria-hidden>
              ☆
            </span>
          ))}
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "center",
            gap: 8,
            marginBottom: 24,
          }}
        >
          {hit.cleared.map((c) => (
            <span
              key={c.label}
              style={{
                fontSize: 13,
                fontWeight: 600,
                padding: "6px 14px",
                borderRadius: 999,
                border: `1px solid ${c.passed ? tokens.outline : tokens.danger}`,
                color: c.passed ? tokens.textSecondary : tokens.danger,
              }}
            >
              {c.passed ? c.label : `Restricted: ${c.label}`}
            </span>
          ))}
        </div>

        <h2 style={{ fontSize: 28, margin: "0 0 4px" }}>Nutrition Facts</h2>
        <p style={{ fontSize: 13, fontWeight: 700, margin: "0 0 2px" }}>
          With Personalized Targets for You
        </p>

        <div style={{ height: 6, background: tokens.textPrimary, margin: "12px 0 8px" }} />

        <p style={{ fontSize: 13, margin: "0 0 4px" }}>Amount Per Serving</p>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <strong style={{ fontSize: 26 }}>Calories</strong>
          <strong style={{ fontSize: 34 }}>{hit.calories}</strong>
        </div>

        <div style={{ height: 6, background: tokens.textPrimary, margin: "8px 0 4px" }} />

        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 4 }}>
          <span style={{ fontSize: 12, fontWeight: 700 }}>% Personal Goal*</span>
        </div>

        <Row
          label="Total Fat"
          value={`${hit.fat_g}g`}
          percent={pct(hit.fat_g, DAILY_VALUE.fat_g)}
          bold
        />
        <Row label="Saturated Fat" value="—" indent={1} />
        <Row label="Cholesterol" value="—" />
        <Row label="Sodium" value="—" />
        <Row
          label="Total Carbohydrate"
          value={`${hit.carbs_g}g`}
          percent={pct(hit.carbs_g, DAILY_VALUE.carbs_g)}
          bold
        />
        <Row label="Total Sugars" value="—" indent={1} />
        <Row label="Added Sugars" value="—" indent={2} />
        <Row label="Dietary Fiber" value="—" indent={1} />
        <Row
          label="Protein"
          value={`${hit.protein_g}g`}
          percent={pct(hit.protein_g, DAILY_VALUE.protein_g)}
          bold
        />
        <Row label="Iron" value="—" />

        <div style={{ height: 6, background: tokens.textPrimary, margin: "8px 0 12px" }} />

        <p style={{ fontSize: 11, color: tokens.textSecondary, lineHeight: 1.5 }}>
          * % Personal Goal is shown only for values this app currently tracks (fat, carbs,
          protein), against standard reference daily values — not yet your personalized
          targets. Fields marked "—" aren't in the data yet.
        </p>
      </div>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: 16,
          background: `linear-gradient(to top, ${tokens.background} 60%, transparent)`,
        }}
      >
        <button
          aria-label="Report an issue with this item"
          style={{
            width: 48,
            height: 48,
            flexShrink: 0,
            borderRadius: "50%",
            border: "none",
            background: tokens.accent,
            color: tokens.accentText,
            fontSize: 18,
            cursor: "pointer",
          }}
        >
          ⚑
        </button>
        <button
          onClick={onLogFood}
          style={{
            flex: 1,
            padding: "14px 0",
            borderRadius: 999,
            border: "none",
            background: tokens.accent,
            color: tokens.accentText,
            fontSize: 16,
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Log Food
        </button>
      </div>
    </div>
  );
}
