import React, { useEffect, useState } from "react";
import { StatusBadge, ConfidenceCell, Highlight } from "./Primitives.jsx";

const STATUSES = ["Met", "Partial", "Gap", "N/A"];
const SEVERITIES = ["None", "Low", "Medium", "High"];

export default function DetailPane({ row, onReview, busy }) {
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);

  useEffect(() => {
    setNote(row?.reviewer_note || "");
    setEditing(false);
    setDraft(null);
  }, [row?.requirement_id]);

  if (!row) {
    return (
      <div className="workpane">
        <div className="empty">Select a requirement from the register to inspect its clause, retrieved candidate controls, and the assessment.</div>
      </div>
    );
  }

  // requirement-side highlight = the requirement_quote in any citation
  const reqQuote = (row.citations.find((c) => c.requirement_quote) || {}).requirement_quote;
  // control-side highlights keyed by control_id
  const ctrlQuote = {};
  row.citations.forEach((c) => { if (c.control_id && c.control_quote) ctrlQuote[c.control_id] = c.control_quote; });

  const isStub = row.assessor === "stub" || row.assessor.endsWith("->stub");

  const startEdit = () => {
    setDraft({
      coverage_status: row.coverage_status,
      mapped_control_ids: [...row.mapped_control_ids],
      severity: row.severity,
      recommended_remediation: row.recommended_remediation,
    });
    setEditing(true);
  };

  const submit = (review_status, payload = {}) =>
    onReview(row.requirement_id, { review_status, reviewer_note: note, ...payload });

  const toggleMapped = (cid) => {
    setDraft((d) => {
      const has = d.mapped_control_ids.includes(cid);
      return { ...d, mapped_control_ids: has ? d.mapped_control_ids.filter((x) => x !== cid) : [...d.mapped_control_ids, cid] };
    });
  };

  return (
    <div className="workpane">
      {/* LEFT: requirement clause */}
      <div className="workcol">
        <div className="panel-head">
          <span>Requirement clause</span>
          <span className="spacer" />
          <span className="mono" style={{ color: "var(--ink-3)" }}>{row.requirement_id}</span>
        </div>
        <div className="workbody">
          <div className="clause-meta">
            <span className="pill">{row.requirement_ref}</span>
            <span className="clause-title" style={{ margin: 0 }}>{row.requirement_title}</span>
          </div>
          <div className="clause-text">
            <Highlight text={row.requirement_text} quote={reqQuote} />
          </div>
          <div className="kw">Cited clause span is highlighted. The assessment on the right may only rely on retrieved controls.</div>
        </div>
      </div>

      {/* RIGHT: assessment + candidates + review */}
      <div className="workcol">
        <div className="panel-head">
          <span>Assessment &amp; retrieved candidates</span>
          <span className="spacer" />
          <span className="mono" style={{ color: "var(--ink-3)" }}>assessor: {row.assessor}</span>
        </div>
        <div className="workbody">
          <div className={`assessor-note ${isStub ? "stub" : ""}`}>
            {isStub
              ? "STUB assessment — deterministic keyword heuristic, not model reasoning. Verify before relying on this row."
              : "Model assessment reasoned only over the retrieved candidates below. Cited control text is verified to appear verbatim in a candidate."}
          </div>

          <div className="assess-head">
            <StatusBadge status={row.coverage_status} />
            <ConfidenceCell confidence={row.confidence} band={row.confidence_band} />
            <span className={`sev ${row.severity}`} title="Severity">Severity: {row.severity}</span>
          </div>

          <div className="sub">Rationale</div>
          <div className="rationale">{row.rationale}</div>

          <div className="sub">Recommended remediation</div>
          <div className="remediation">{row.recommended_remediation}</div>

          <div className="sub">Retrieved candidate controls (top-{row.candidates.length})</div>
          {row.candidates.length === 0 && <div style={{ color: "var(--ink-3)" }}>No candidates retrieved.</div>}
          {row.candidates.map((c) => {
            const mapped = row.mapped_control_ids.includes(c.control_id);
            return (
              <div key={c.control_id} className={`cand ${mapped ? "mapped" : ""}`}>
                <div className="cand-head">
                  <span className="cand-id">{c.control_id}</span>
                  <span className="cand-title">{c.title}</span>
                  <span className="spacer" />
                  {mapped && <span className="mapped-flag">MAPPED</span>}
                  <span className="cand-score" title="Retrieval similarity">sim {c.score.toFixed(3)}</span>
                </div>
                <div className="cand-text">
                  <Highlight text={c.text} quote={ctrlQuote[c.control_id]} />
                </div>
              </div>
            );
          })}
        </div>

        {/* review controls */}
        <div className="review">
          {!editing && (
            <div className="review-row">
              <button className="btn-accept" disabled={busy} onClick={() => submit("Accepted")}>Accept proposal</button>
              <button className="btn-edit" disabled={busy} onClick={startEdit}>Edit…</button>
              <button className="btn-reject" disabled={busy} onClick={() => submit("Rejected")}>Reject</button>
              <span className="spacer" />
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                current: {row.review_status}
              </span>
            </div>
          )}

          {editing && draft && (
            <div>
              <div className="edit-grid">
                <div className="field-col">
                  <label>Coverage status</label>
                  <select className="mono" value={draft.coverage_status}
                    onChange={(e) => setDraft({ ...draft, coverage_status: e.target.value })}>
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div className="field-col">
                  <label>Severity</label>
                  <select className="mono" value={draft.severity}
                    onChange={(e) => setDraft({ ...draft, severity: e.target.value })}>
                    {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              </div>
              <div className="field-col" style={{ marginBottom: 8 }}>
                <label>Mapped controls (pick from retrieved candidates)</label>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 3 }}>
                  {row.candidates.map((c) => (
                    <label key={c.control_id} className="check mono" style={{ border: "1px solid var(--line-2)", borderRadius: 3, padding: "2px 6px" }}>
                      <input type="checkbox" checked={draft.mapped_control_ids.includes(c.control_id)} onChange={() => toggleMapped(c.control_id)} />
                      {c.control_id}
                    </label>
                  ))}
                </div>
              </div>
              <div className="field-col" style={{ marginBottom: 8 }}>
                <label>Recommended remediation</label>
                <textarea value={draft.recommended_remediation}
                  onChange={(e) => setDraft({ ...draft, recommended_remediation: e.target.value })} />
              </div>
            </div>
          )}

          <div className="field-col">
            <label style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--ink-3)" }}>Reviewer note</label>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Record your judgement, evidence checked, or reason for rejection…" />
          </div>

          {editing && (
            <div className="review-row" style={{ marginTop: 8 }}>
              <button className="primary" disabled={busy}
                onClick={() => submit("Edited", {
                  coverage_status: draft.coverage_status,
                  mapped_control_ids: draft.mapped_control_ids,
                  severity: draft.severity,
                  recommended_remediation: draft.recommended_remediation,
                })}>Save edits</button>
              <button disabled={busy} onClick={() => { setEditing(false); setDraft(null); }}>Cancel</button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
