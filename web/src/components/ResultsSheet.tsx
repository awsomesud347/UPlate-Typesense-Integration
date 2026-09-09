import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { Hit } from "../lib/types";
import { tokens } from "../lib/tokens";
import ResultCard from "./ResultCard";

interface ResultsSheetProps {
  hits: Hit[];
  withheldCount: number;
  interpretedIntent?: string;
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  onOpenDetail?: (hit: Hit) => void;
  visible: boolean; // false before the first search — sheet is fully hidden, not peeking
}

const PEEK_HEIGHT = 96; // px visible when collapsed — handle + one-line summary
const EXPANDED_HEIGHT = "68%"; // max height of the sheet when fully open

// Draggable bottom sheet. Hidden entirely until `visible`, then opens (animates
// to expanded). Once open, snaps to collapsed (peek) or expanded on release;
// animates via CSS transition, follows the finger 1:1 while dragging.
export default function ResultsSheet({
  hits,
  withheldCount,
  interpretedIntent,
  selectedId,
  onSelect,
  onOpenDetail,
  visible,
}: ResultsSheetProps) {
  const sheetRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [dragPx, setDragPx] = useState<number | null>(null); // null = not dragging
  const dragState = useRef<{ startY: number; maxTranslate: number } | null>(null);

  // Every fresh search re-opens the sheet fully, even if the user had
  // previously collapsed it.
  useEffect(() => {
    if (visible) setExpanded(true);
  }, [visible]);

  function collapsedTranslate() {
    const el = sheetRef.current;
    if (!el) return 0;
    return Math.max(el.getBoundingClientRect().height - PEEK_HEIGHT, 0);
  }

  function handlePointerDown(e: ReactPointerEvent<HTMLDivElement>) {
    const maxTranslate = collapsedTranslate();
    dragState.current = { startY: e.clientY, maxTranslate };
    setDragPx(expanded ? 0 : maxTranslate);
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  }

  function handlePointerMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (!dragState.current || dragPx === null) return;
    const { startY, maxTranslate } = dragState.current;
    const base = expanded ? 0 : maxTranslate;
    const next = Math.min(Math.max(base + (e.clientY - startY), 0), maxTranslate);
    setDragPx(next);
  }

  function handlePointerUp() {
    if (!dragState.current || dragPx === null) return;
    const { maxTranslate } = dragState.current;
    setExpanded(dragPx < maxTranslate / 2);
    setDragPx(null);
    dragState.current = null;
  }

  const translateY = !visible
    ? "100%"
    : dragPx !== null
      ? dragPx
      : expanded
        ? 0
        : `calc(100% - ${PEEK_HEIGHT}px)`;

  return (
    <div
      ref={sheetRef}
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height: EXPANDED_HEIGHT,
        display: "flex",
        flexDirection: "column",
        background: tokens.surface,
        border: `1px solid ${tokens.outline}`,
        borderBottom: "none",
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        boxShadow: "0 -8px 24px rgba(0,0,0,0.4)",
        transform: `translateY(${typeof translateY === "number" ? `${translateY}px` : translateY})`,
        transition: dragPx === null ? "transform 280ms cubic-bezier(.22,1,.36,1)" : "none",
      }}
    >
      {/* drag handle — the whole header strip is grabbable, not just the bar.
          touchAction:none lives ONLY here, not on the sheet, so touch scrolling
          still works inside the list below. */}
      <div
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onClick={() => dragPx === null && setExpanded((v) => !v)}
        style={{ cursor: "grab", paddingTop: 8, paddingBottom: 4, flexShrink: 0, touchAction: "none" }}
      >
        <div style={{ display: "flex", justifyContent: "center" }}>
          <div
            aria-hidden
            style={{ width: 36, height: 4, borderRadius: 2, background: tokens.outline }}
          />
        </div>

        <p
          style={{
            margin: "8px 16px 0",
            fontSize: 13,
            fontWeight: 600,
            color: tokens.textPrimary,
          }}
        >
          {hits.length > 0
            ? `${hits.length} result${hits.length === 1 ? "" : "s"}`
            : "Search to see results"}
        </p>

        {interpretedIntent && (
          <p style={{ margin: "2px 16px 0", fontSize: 12, color: tokens.textSecondary }}>
            {interpretedIntent}
          </p>
        )}

        {withheldCount > 0 && (
          <p style={{ margin: "4px 16px 0", fontSize: 12, color: tokens.danger }}>
            {withheldCount} item{withheldCount === 1 ? "" : "s"} hidden — allergen data
            unverified
          </p>
        )}
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0, // lets this pane actually shrink and scroll instead of growing the sheet
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          padding: "8px 16px 16px",
        }}
      >
        {hits.map((hit) => (
          <ResultCard
            key={hit.id}
            hit={hit}
            selected={hit.id === selectedId}
            onSelect={onSelect}
            onOpenDetail={onOpenDetail}
          />
        ))}
      </div>
    </div>
  );
}
