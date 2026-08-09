// Thin API client. All calls hit the FastAPI backend via the Vite proxy (/api).

const BASE = "/api";

async function j(path, opts) {
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} — ${text}`);
  }
  return res.json();
}

export const api = {
  health: () => j("/health"),
  standards: () => j("/standards"),
  controls: () => j("/controls"),
  analyze: (standard_id, top_k = 4, prefer_model = true) =>
    j("/analyze", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ standard_id, top_k, prefer_model }),
    }),
  latest: (standard_id) =>
    j(`/runs/latest?standard_id=${encodeURIComponent(standard_id)}`),
  review: (run_id, req_id, payload) =>
    j(`/runs/${run_id}/rows/${encodeURIComponent(req_id)}/review`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    }),
  eval: () => j("/eval"),
  csvUrl: (run_id) => `${BASE}/runs/${run_id}/export.csv`,
  xlsxUrl: (run_id) => `${BASE}/runs/${run_id}/export.xlsx`,
};
