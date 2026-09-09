import { useRef } from "react";
import { tokens } from "../lib/tokens";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onImageUpload: (file: File) => void;
  loading?: boolean;
}

// Sits in the static header, per the reference app. The "+" is the photo-search
// entry point (skeleton only for now — Phase 8 wires actual recognition).
export default function SearchBar({
  value,
  onChange,
  onSubmit,
  onImageUpload,
  loading,
}: SearchBarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: tokens.surface,
        border: `1px solid ${tokens.outline}`,
        borderRadius: 999,
        padding: "10px 8px 10px 16px",
      }}
    >
      <span aria-hidden style={{ color: tokens.textSecondary }}>
        ⌕
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && onSubmit()}
        placeholder="exam in an hour, don't want to crash"
        aria-label="Search food"
        style={{
          flex: 1,
          border: "none",
          outline: "none",
          background: "transparent",
          fontSize: 14,
          fontFamily: tokens.font,
          color: tokens.textPrimary,
        }}
      />
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onImageUpload(file);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        aria-label="Search by photo"
        onClick={() => fileInputRef.current?.click()}
        disabled={loading}
        style={{
          width: 32,
          height: 32,
          flexShrink: 0,
          borderRadius: "50%",
          border: "none",
          background: tokens.accent,
          color: tokens.accentText,
          fontSize: 18,
          lineHeight: 1,
          cursor: "pointer",
        }}
      >
        {loading ? "…" : "+"}
      </button>
    </div>
  );
}
