"""FastAPI app for ControlGap.

Endpoints:
  GET  /api/health
  GET  /api/standards                      list bundled standards
  GET  /api/controls                       list synthetic controls
  POST /api/analyze                        run pipeline -> gap register (persisted)
  GET  /api/runs/{run_id}                  fetch a run's rows + info
  GET  /api/runs/latest?standard_id=       latest run for a standard
  POST /api/runs/{run_id}/rows/{req_id}/review   accept/edit/reject a row
  GET  /api/runs/{run_id}/export.csv
  GET  /api/runs/{run_id}/export.xlsx
  GET  /api/eval                           run the hand-labeled eval (real numbers)
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from . import db
from .eval import run_eval
from .export import to_csv, to_xlsx
from .models import GapRow, ReviewStatus, ReviewUpdate
from .parsing import available_standards, load_controls
from .pipeline import run_analysis

app = FastAPI(title="ControlGap", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # single-user local PoC
    allow_methods=["*"],
    allow_headers=["*"],
)

DISCLAIMER = (
    "Decision-support only — not legal or compliance advice. Control data is SYNTHETIC. "
    "AI/stub outputs require human validation before any reliance."
)


@app.on_event("startup")
def _startup():
    db.init_db()


@app.get("/api/health")
def health():
    return {"status": "ok", "disclaimer": DISCLAIMER}


@app.get("/api/standards")
def standards():
    return {"standards": available_standards(), "disclaimer": DISCLAIMER}


@app.get("/api/controls")
def controls():
    ctrls, meta = load_controls()
    return {"controls": [c.model_dump() for c in ctrls], "meta": meta}


class AnalyzeRequest(BaseModel):
    standard_id: str = "wcag22"
    top_k: int = 4
    prefer_model: bool = True


def _run_payload(run_id: str) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, f"run '{run_id}' not found")
    rows = db.get_rows(run_id)
    info = json.loads(run["meta_json"])
    summary = _summarize(rows)
    return {
        "run_id": run_id,
        "standard_id": run["standard_id"],
        "info": info,
        "summary": summary,
        "rows": [r.model_dump() for r in rows],
        "disclaimer": DISCLAIMER,
    }


def _summarize(rows) -> dict:
    counts = {"Met": 0, "Partial": 0, "Gap": 0, "N/A": 0}
    reviewed = 0
    for r in rows:
        counts[r.coverage_status.value] = counts.get(r.coverage_status.value, 0) + 1
        if r.review_status != ReviewStatus.AI_PROPOSED:
            reviewed += 1
    return {
        "total": len(rows),
        "coverage_counts": counts,
        "reviewed": reviewed,
        "unreviewed": len(rows) - reviewed,
    }


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    try:
        run_id, _info = run_analysis(req.standard_id, top_k=req.top_k, prefer_model=req.prefer_model)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _run_payload(run_id)


@app.get("/api/runs/latest")
def latest(standard_id: Optional[str] = Query(default=None)):
    run_id = db.latest_run_id(standard_id)
    if not run_id:
        raise HTTPException(404, "no runs yet")
    return _run_payload(run_id)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return _run_payload(run_id)


@app.post("/api/runs/{run_id}/rows/{req_id}/review")
def review(run_id: str, req_id: str, update: ReviewUpdate):
    row = db.get_row(run_id, req_id)
    if not row:
        raise HTTPException(404, "row not found")
    row.review_status = update.review_status
    if update.reviewer_note is not None:
        row.reviewer_note = update.reviewer_note
    if update.coverage_status is not None:
        row.coverage_status = update.coverage_status
    if update.mapped_control_ids is not None:
        row.mapped_control_ids = update.mapped_control_ids
    if update.severity is not None:
        row.severity = update.severity
    if update.recommended_remediation is not None:
        row.recommended_remediation = update.recommended_remediation
    db.update_row(run_id, row)
    return row.model_dump()


@app.get("/api/runs/{run_id}/export.csv")
def export_csv(run_id: str):
    rows = db.get_rows(run_id)
    if not rows:
        raise HTTPException(404, "run not found or empty")
    data = to_csv(rows)
    return Response(
        content=data, media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="controlgap_{run_id}.csv"'},
    )


@app.get("/api/runs/{run_id}/export.xlsx")
def export_xlsx(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    rows = db.get_rows(run_id)
    info = json.loads(run["meta_json"])
    data = to_xlsx(rows, info)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="controlgap_{run_id}.xlsx"'},
    )


@app.get("/api/eval")
def eval_endpoint(top_k: int = 4, prefer_model: bool = True):
    return run_eval(top_k=top_k, prefer_model=prefer_model)
