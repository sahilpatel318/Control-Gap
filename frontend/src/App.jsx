import React, { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import RegisterTable from "./components/RegisterTable.jsx";
import DetailPane from "./components/DetailPane.jsx";
import EvalDialog from "./components/EvalDialog.jsx";

const DISCLAIMER =
  "Decision-support only — not legal or compliance advice. Control data is SYNTHETIC. Every AI/stub proposal requires human validation before reliance.";

export default function App() {
  const [standards, setStandards] = useState([]);
  const [standardId, setStandardId] = useState("wcag22");
  const [topK, setTopK] = useState(4);
  const [preferModel, setPreferModel] = useState(true);

  const [run, setRun] = useState(null); // {run_id, info, summary, rows}
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [evalData, setEvalData] = useState(null);

  useEffect(() => {
    api.standards().then((d) => setStandards(d.standards)).catch(() => {});
  }, []);

  // Load the latest existing run for the selected standard, if any.
  useEffect(() => {
    let alive = true;
    setSelectedId(null);
    api.latest(standardId)
      .then((d) => { if (alive) { setRun(d); setError(null); } })
      .catch(() => { if (alive) setRun(null); });
    return () => { alive = false; };
  }, [standardId]);

  const analyze = useCallback(async () => {
    setLoading(true); setError(null); setSelectedId(null);
    try {
      const d = await api.analyze(standardId, topK, preferModel);
      setRun(d);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }, [standardId, topK, preferModel]);

  const doReview = useCallback(async (reqId, payload) => {
    if (!run) return;
    setBusy(true);
    try {
      await api.review(run.run_id, reqId, payload);
      // refresh run to recompute summary + reflect persisted state
      const fresh = await api.latest(standardId);
      setRun(fresh);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  }, [run, standardId]);

  const openEval = useCallback(async () => {
    try { setEvalData(await api.eval()); }
    catch (e) { setError(String(e.message || e)); }
  }, []);

  const selectedRow = useMemo(
    () => run?.rows.find((r) => r.requirement_id === selectedId) || null,
    [run, selectedId]
  );

  const info = run?.info;
  const assessorInfo = info?.assessor;
  const embedderInfo = info?.embedder;
  const summary = run?.summary;

  return (
    <div className="app">
      <div className="toolbar">
        <span className="brand">
          ControlGap
          <span className="tag">Regulatory-change → control-gap mapper</span>
        </span>

        <div className="field">
          <label htmlFor="std">Standard</label>
          <select id="std" className="mono" value={standardId} onChange={(e) => setStandardId(e.target.value)}>
            {standards.map((s) => (
              <option key={s.standard_id} value={s.standard_id}>{s.standard_id}</option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="topk">top-k</label>
          <input id="topk" type="number" min={1} max={8} value={topK} style={{ width: 48 }}
            onChange={(e) => setTopK(Math.max(1, Math.min(8, Number(e.target.value) || 4)))} />
        </div>

        <label className="check" title="Use the neural embedder if available; otherwise TF-IDF fallback">
          <input type="checkbox" checked={preferModel} onChange={(e) => setPreferModel(e.target.checked)} />
          prefer neural embedder
        </label>

        <button className="primary" onClick={analyze} disabled={loading}>
          {loading ? "Running…" : run ? "Re-run analysis" : "Run analysis"}
        </button>

        <span className="spacer" />

        {/* provenance badges — always tell the user what produced the result */}
        {assessorInfo && (
          <span className={`provbadge ${assessorInfo.is_stub ? "warn" : ""}`} title={assessorInfo.detail}>
            <span className="dot" /> assessor: {assessorInfo.assessor}{assessorInfo.is_stub ? " · STUB" : ""}
          </span>
        )}
        {embedderInfo && (
          <span className={`provbadge ${embedderInfo.is_fallback ? "warn" : ""}`} title={embedderInfo.detail}>
            <span className="dot" /> embed: {embedderInfo.backend}{embedderInfo.is_fallback ? " · FALLBACK" : ""}
          </span>
        )}

        <button onClick={openEval} title="Run the hand-labeled evaluation">Eval</button>
        <button onClick={() => run && window.open(api.csvUrl(run.run_id), "_blank")} disabled={!run}>CSV</button>
        <button onClick={() => run && window.open(api.xlsxUrl(run.run_id), "_blank")} disabled={!run}>XLSX</button>
      </div>

      <div className="disclaimer">
        <strong>Disclaimer:</strong> {DISCLAIMER}
      </div>

      {error && <div className="notice error">Error: {error}</div>}

      {summary && (
        <div className="summary">
          <span className="chip"><span className="n">{summary.total}</span><span className="lbl">requirements</span></span>
          <span className="chip"><span className="n" style={{ color: "var(--met)" }}>{summary.coverage_counts.Met}</span><span className="lbl">Met</span></span>
          <span className="chip"><span className="n" style={{ color: "var(--partial)" }}>{summary.coverage_counts.Partial}</span><span className="lbl">Partial</span></span>
          <span className="chip"><span className="n" style={{ color: "var(--gap)" }}>{summary.coverage_counts.Gap}</span><span className="lbl">Gap</span></span>
          {summary.coverage_counts["N/A"] > 0 && (
            <span className="chip"><span className="n">{summary.coverage_counts["N/A"]}</span><span className="lbl">N/A</span></span>
          )}
          <span className="chip"><span className="n" style={{ color: summary.unreviewed ? "var(--warn)" : "var(--met)" }}>{summary.unreviewed}</span><span className="lbl">unreviewed</span></span>
          {info?.standard?.standard_name && (
            <span className="chip" style={{ marginLeft: "auto" }}><span className="lbl">{info.standard.standard_name}</span></span>
          )}
        </div>
      )}

      {!run && !loading && (
        <div className="notice">
          No analysis yet for <span className="mono">{standardId}</span>. Click <strong>Run analysis</strong> to build the gap register.
        </div>
      )}

      {run && (
        <div className="main">
          <RegisterTable rows={run.rows} selectedId={selectedId} onSelect={setSelectedId} />
          <DetailPane row={selectedRow} onReview={doReview} busy={busy} />
        </div>
      )}

      {evalData && <EvalDialog data={evalData} onClose={() => setEvalData(null)} />}
    </div>
  );
}
