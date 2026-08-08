"""Orchestrates the full RAG pipeline into a gap register.

parse -> chunk(by boundary) -> embed(local) -> retrieve(top-k) -> assess(LLM|stub)
     -> verify grounding -> GapRow -> persist.
"""
from __future__ import annotations

import time
import uuid
from typing import List, Tuple

from . import db
from .assessor import build_assessor, verify_grounding
from .chunking import control_chunks, requirement_chunks
from .models import GapRow, ReviewStatus
from .parsing import load_controls, load_requirements
from .retrieval import Retriever


def run_analysis(standard_id: str, top_k: int = 4, prefer_model: bool = True) -> Tuple[str, dict]:
    reqs, req_meta = load_requirements(standard_id)
    controls, ctrl_meta = load_controls()

    r_chunks = requirement_chunks(reqs)
    c_chunks = control_chunks(controls)

    retriever = Retriever.build(r_chunks, c_chunks, prefer_model=prefer_model)
    assessor, assessor_info = build_assessor()

    req_lookup = {r.requirement_id: r for r in reqs}

    rows: List[GapRow] = []
    for chunk in r_chunks:
        req = req_lookup[chunk.ref_id]
        candidates = retriever.top_k(chunk, k=top_k)
        assessment = assessor.assess(
            chunk, {"ref": req.ref, "title": req.title, "level": req.level}, candidates
        )
        assessment = verify_grounding(assessment, candidates)

        mapped = sorted({c.control_id for c in assessment.citations if c.control_id})
        rows.append(
            GapRow(
                requirement_id=req.requirement_id,
                requirement_ref=req.ref,
                requirement_title=req.title,
                requirement_summary=(req.text[:140] + "…") if len(req.text) > 141 else req.text,
                requirement_text=req.text,
                mapped_control_ids=mapped,
                candidates=candidates,
                coverage_status=assessment.coverage_status,
                confidence=assessment.confidence,
                confidence_band=assessment.confidence_band,
                rationale=assessment.rationale,
                citations=assessment.citations,
                severity=assessment.severity,
                recommended_remediation=assessment.recommended_remediation,
                review_status=ReviewStatus.AI_PROPOSED,
                reviewer_note="",
                assessor=assessment.assessor,
            )
        )

    info = {
        "assessor": assessor_info,
        "embedder": {
            "backend": retriever.embedder.info.backend,
            "is_fallback": retriever.embedder.info.is_fallback,
            "detail": retriever.embedder.info.detail,
        },
        "standard": req_meta,
        "controls": ctrl_meta,
        "top_k": top_k,
        "generated_at": time.time(),
    }

    run_id = f"{standard_id}-{uuid.uuid4().hex[:8]}"
    db.init_db()
    db.save_run(run_id, standard_id, info, top_k, rows)
    return run_id, info
