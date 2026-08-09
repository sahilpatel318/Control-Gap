import React from "react";

export default function EvalDialog({ data, onClose }) {
  if (!data) return null;
  const gd = data.gap_detection || {};
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Evaluation — real numbers on the hand-labeled set</h2>
          <span className="spacer" style={{ flex: 1 }} />
          <button onClick={onClose}>Close</button>
        </div>
        <div className="modal-body">
          <p style={{ marginTop: 0, color: "var(--ink-2)" }}>
            Measured against a hand-labeled ground-truth set of{" "}
            <strong className="mono">{data.sample_size}</strong> requirements. Assessor{" "}
            <strong className="mono">{data.assessor}</strong>{data.assessor_is_stub ? " (stub)" : ""}, embedder{" "}
            <strong className="mono">{data.embedder_backend}</strong>
            {data.embedder_is_fallback ? " (fallback)" : ""}. These are not target or claimed figures — they are what the pipeline produced on this run.
          </p>

          <div className="metric-grid">
            <div className="metric">
              <div className="v">{data.status_accuracy ?? "—"}</div>
              <div className="k">3-way status accuracy ({data.status_correct}/{data.sample_size})</div>
            </div>
            <div className="metric">
              <div className="v">{gd.f1 ?? "—"}</div>
              <div className="k">Gap-detection F1 (P {gd.precision} / R {gd.recall})</div>
            </div>
            <div className="metric">
              <div className="v">{data.retrieval_recall_at_k ?? "—"}</div>
              <div className="k">Retrieval recall@{data.top_k} ({data.retrieval_hits}/{data.retrieval_expected_rows})</div>
            </div>
          </div>

          <p style={{ fontSize: 12, color: "var(--ink-2)" }}>
            Gap-detection confusion (Gap = positive): tp {gd.tp}, fp {gd.fp}, fn {gd.fn}, tn {gd.tn}.
            Small sample — treat as indicative, not a guarantee.
          </p>

          <table className="evaltable">
            <thead>
              <tr><th>Requirement</th><th>Expected</th><th>Predicted</th><th></th></tr>
            </thead>
            <tbody>
              {(data.per_row || []).map((r) => {
                const miss = r.expected !== r.predicted;
                return (
                  <tr key={r.requirement_id} className={miss ? "miss" : ""}>
                    <td className="mono">{r.requirement_id}</td>
                    <td className="mono">{r.expected}</td>
                    <td className="mono">{r.predicted}</td>
                    <td>{miss ? "mismatch" : "✓"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
