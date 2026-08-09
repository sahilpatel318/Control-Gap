import React from "react";

// Status conveyed by GLYPH + LABEL + color (never color alone).
const GLYPHS = {
  Met: "●",       // filled circle
  Partial: "◗",   // half circle
  Gap: "▲",       // triangle
  "N/A": "○",     // empty circle
};

export function StatusBadge({ status }) {
  const cls = status === "N/A" ? "NA" : status;
  return (
    <span className={`status ${cls}`} title={status}>
      <span className="glyph" aria-hidden="true">{GLYPHS[status] || "?"}</span>
      <span>{status}</span>
    </span>
  );
}

export function ConfidenceCell({ confidence, band }) {
  const pct = Math.round((confidence || 0) * 100);
  return (
    <span>
      <span className="conf-bar" aria-hidden="true">
        <span style={{ width: `${pct}%` }} />
      </span>
      <span className={`band ${band}`}>{band}</span>{" "}
      <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11 }}>{confidence?.toFixed(2)}</span>
    </span>
  );
}

// Highlight the exact matched substring inside a longer text.
// `quote` must be an exact substring; if it isn't found, the text renders plain.
export function Highlight({ text, quote }) {
  if (!quote) return <>{text}</>;
  const idx = text.indexOf(quote);
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="hl">{text.slice(idx, idx + quote.length)}</mark>
      {text.slice(idx + quote.length)}
    </>
  );
}
