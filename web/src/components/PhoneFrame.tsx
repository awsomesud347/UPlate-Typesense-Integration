import type { ReactNode } from "react";
import { tokens } from "../lib/tokens";

// Demo presentation wrapper only — the app underneath stays responsive.
// Width bumped to 430px per request (was 390px).
const FRAME_WIDTH = 430;

export default function PhoneFrame({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        width: FRAME_WIDTH,
        maxWidth: "100%",
        margin: "0 auto",
        height: "100dvh",
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        background: tokens.background,
        fontFamily: tokens.font,
        color: tokens.textPrimary,
      }}
    >
      {children}
    </div>
  );
}
