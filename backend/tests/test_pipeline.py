"""Tests for the ControlGap pipeline. Run with:  pytest -q

These exercise the deterministic (stub + TF-IDF) path, so they need no API key
and no model download. They assert the traceability invariants the product
depends on rather than specific accuracy numbers.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.assessor import StubAssessor, verify_grounding
from app.chunking import control_chunks, requirement_chunks
from app.models import Assessment, Candidate, Citation, ConfidenceBand, CoverageStatus, Severity
from app.parsing import load_controls, load_requirements
from app.retrieval import Retriever
from app.export import to_csv, to_xlsx
from app.pipeline import run_analysis
from app import db


def _build_tfidf_retriever():
    reqs, _ = load_requirements("wcag22")
    controls, _ = load_controls()
    rc = requirement_chunks(reqs)
    cc = control_chunks(controls)
    return Retriever.build(rc, cc, prefer_model=False), rc, {r.requirement_id: r for r in reqs}


def test_parsing_ids_unique():
    reqs, _ = load_requirements("wcag22")
    controls, _ = load_controls()
    assert len({r.requirement_id for r in reqs}) == len(reqs)
    assert len({c.control_id for c in controls}) == len(controls)
    assert len(reqs) >= 20 and len(controls) >= 15


def test_retrieval_returns_topk_with_scores():
    retriever, rc, _ = _build_tfidf_retriever()
    cands = retriever.top_k(rc[0], k=4)
    assert len(cands) == 4
    for c in cands:
        assert 0.0 <= c.score <= 1.0
        assert c.text  # candidate carries its exact control text


def test_stub_citations_are_exact_substrings():
    """Every control_quote must appear verbatim in a retrieved candidate."""
    retriever, rc, lookup = _build_tfidf_retriever()
    stub = StubAssessor()
    for chunk in rc:
        req = lookup[chunk.ref_id]
        cands = retriever.top_k(chunk, k=4)
        a = stub.assess(chunk, {"ref": req.ref, "title": req.title, "level": req.level}, cands)
        cand_text = {c.control_id: c.text for c in cands}
        for cit in a.citations:
            if cit.control_id and cit.control_quote:
                assert cit.control_quote in cand_text[cit.control_id]


def test_gap_rows_have_no_mapped_control():
    """'No adequate control' is first-class: Gap rows cite no control."""
    retriever, rc, lookup = _build_tfidf_retriever()
    stub = StubAssessor()
    saw_gap = False
    for chunk in rc:
        req = lookup[chunk.ref_id]
        cands = retriever.top_k(chunk, k=4)
        a = stub.assess(chunk, {"ref": req.ref, "title": req.title, "level": req.level}, cands)
        if a.coverage_status == CoverageStatus.GAP:
            saw_gap = True
            assert not any(c.control_id for c in a.citations)
    assert saw_gap  # the synthetic set is designed to contain real gaps


def test_grounding_drops_unverifiable_quote_and_demotes():
    cands = [Candidate(control_id="ACC-01", title="t", text="This exact sentence exists.", score=0.9)]
    bogus = Assessment(
        coverage_status=CoverageStatus.MET, confidence=0.9, confidence_band=ConfidenceBand.HIGH,
        rationale="claim", citations=[Citation(requirement_quote="q", control_id="ACC-01",
                                               control_quote="a hallucinated sentence not present")],
        severity=Severity.NONE, recommended_remediation="none", assessor="test",
    )
    out = verify_grounding(bogus, cands)
    assert all(c.control_quote != "a hallucinated sentence not present" for c in out.citations)
    assert out.coverage_status == CoverageStatus.GAP  # demoted: lost all control evidence
    assert out.confidence < 0.9


def test_full_run_and_exports(tmp_path):
    run_id, info = run_analysis("wcag22", top_k=4, prefer_model=False)
    rows = db.get_rows(run_id)
    assert len(rows) >= 20
    # exports
    csv_bytes = to_csv(rows)
    assert b"requirement_id" in csv_bytes
    assert b"UNREVIEWED" in csv_bytes  # fresh rows are flagged unreviewed
    xlsx_bytes = to_xlsx(rows, info)
    assert xlsx_bytes[:2] == b"PK"  # xlsx is a zip
