import React, { useMemo, useState } from "react";
import { StatusBadge, ConfidenceCell } from "./Primitives.jsx";

const STATUS_ORDER = { Gap: 0, Partial: 1, "N/A": 2, Met: 3 };
const SEV_ORDER = { High: 0, Medium: 1, Low: 2, None: 3 };

export default function RegisterTable({ rows, selectedId, onSelect }) {
  const [statusFilter, setStatusFilter] = useState("All");
  const [unreviewedOnly, setUnreviewedOnly] = useState(false);
  const [sort, setSort] = useState({ key: "requirement_ref", dir: 1 });

  const filtered = useMemo(() => {
    let r = rows;
    if (statusFilter !== "All") r = r.filter((x) => x.coverage_status === statusFilter);
    if (unreviewedOnly) r = r.filter((x) => x.review_status === "AI-proposed");
    const { key, dir } = sort;
    const sorted = [...r].sort((a, b) => {
      let av, bv;
      if (key === "coverage_status") { av = STATUS_ORDER[a.coverage_status]; bv = STATUS_ORDER[b.coverage_status]; }
      else if (key === "severity") { av = SEV_ORDER[a.severity]; bv = SEV_ORDER[b.severity]; }
      else if (key === "confidence") { av = a.confidence; bv = b.confidence; }
      else { av = a[key]; bv = b[key]; }
      if (av < bv) return -1 * dir;
      if (av > bv) return 1 * dir;
      return 0;
    });
    return sorted;
  }, [rows, statusFilter, unreviewedOnly, sort]);

  const toggleSort = (key) =>
    setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: 1 }));

  const arrow = (key) => (sort.key === key ? (sort.dir === 1 ? " ↑" : " ↓") : "");

  return (
    <div className="panel">
      <div className="panel-head">
        <span>Gap Register</span>
        <span className="mono" style={{ color: "var(--ink-3)" }}>
          {filtered.length}/{rows.length} rows
        </span>
        <span className="spacer" />
        <div className="filters">
          <div className="seg" role="group" aria-label="Filter by coverage status">
            {["All", "Gap", "Partial", "Met", "N/A"].map((s) => (
              <button key={s} className={statusFilter === s ? "on" : ""} onClick={() => setStatusFilter(s)}>
                {s}
              </button>
            ))}
          </div>
          <label className="check">
            <input type="checkbox" checked={unreviewedOnly} onChange={(e) => setUnreviewedOnly(e.target.checked)} />
            Unreviewed only
          </label>
        </div>
      </div>

      <div className="table-wrap">
        <table className="register">
          <thead>
            <tr>
              <th onClick={() => toggleSort("requirement_ref")}>Req{arrow("requirement_ref")}</th>
              <th onClick={() => toggleSort("requirement_title")}>Requirement{arrow("requirement_title")}</th>
              <th onClick={() => toggleSort("coverage_status")}>Coverage{arrow("coverage_status")}</th>
              <th className="nosort">Mapped control(s)</th>
              <th onClick={() => toggleSort("confidence")}>Confidence{arrow("confidence")}</th>
              <th onClick={() => toggleSort("severity")}>Severity{arrow("severity")}</th>
              <th className="nosort">Review</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => {
              const isSel = row.requirement_id === selectedId;
              const unrev = row.review_status === "AI-proposed";
              return (
                <tr
                  key={row.requirement_id}
                  className={`${isSel ? "selected" : ""} ${unrev ? "unreviewed" : ""}`}
                  onClick={() => onSelect(row.requirement_id)}
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(row.requirement_id); } }}
                >
                  <td><span className="req-ref">{row.requirement_ref}</span></td>
                  <td className="req-title-cell" title={row.requirement_title}>{row.requirement_title}</td>
                  <td><StatusBadge status={row.coverage_status} /></td>
                  <td className={`map-cell ${row.mapped_control_ids.length ? "" : "none"}`}>
                    {row.mapped_control_ids.length ? row.mapped_control_ids.join(", ") : "— none —"}
                  </td>
                  <td><ConfidenceCell confidence={row.confidence} band={row.confidence_band} /></td>
                  <td><span className={`sev ${row.severity}`}>{row.severity}</span></td>
                  <td>
                    {unrev ? (
                      <span className="review-tag unrev">UNREVIEWED</span>
                    ) : (
                      <span className={`review-tag ${row.review_status}`}>{row.review_status}</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr><td colSpan={7} style={{ color: "var(--ink-3)", padding: "16px 10px" }}>No rows match the current filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
