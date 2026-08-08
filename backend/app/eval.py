"""Small hand-labeled evaluation.

Runs the CURRENTLY-CONFIGURED assessor (stub unless an API key is set) plus the
retriever against the hand-labeled ground truth in data/eval_labels.json, then
reports the REAL numbers. Nothing here is hard-coded — the figures printed are
whatever the pipeline actually produces on this machine, with the sample size
stated. If you configure an LLM key, re-run to measure that configuration.

Metrics:
  * status_accuracy      - exact match of coverage_status (3-way Met/Partial/Gap).
  * gap_detection        - treat {Gap} as the positive class: precision/recall/F1
                           for correctly identifying missing coverage.
  * retrieval_recall@k   - for labeled rows that expect a control, did the expected
                           control appear among the retrieved candidates.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .assessor import build_assessor, verify_grounding
from .chunking import control_chunks, requirement_chunks
from .parsing import load_controls, load_requirements
from .retrieval import Retriever

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_labels() -> Dict[str, dict]:
    raw = json.loads((DATA_DIR / "eval_labels.json").read_text(encoding="utf-8"))
    return {l["requirement_id"]: l for l in raw["labels"]}, raw.get("standard_id", "wcag22"), raw.get("labeler_note", "")


def run_eval(top_k: int = 4, prefer_model: bool = True) -> dict:
    labels, standard_id, note = _load_labels()
    reqs, _ = load_requirements(standard_id)
    controls, _ = load_controls()
    r_chunks = requirement_chunks(reqs)
    c_chunks = control_chunks(controls)
    retriever = Retriever.build(r_chunks, c_chunks, prefer_model=prefer_model)
    assessor, assessor_info = build_assessor()
    req_lookup = {r.requirement_id: r for r in reqs}

    n = 0
    status_correct = 0
    # gap = positive class
    tp = fp = fn = tn = 0
    retr_expected = 0
    retr_hits = 0
    per_row = []

    for chunk in r_chunks:
        label = labels.get(chunk.ref_id)
        if not label:
            continue
        n += 1
        req = req_lookup[chunk.ref_id]
        cands = retriever.top_k(chunk, k=top_k)
        a = verify_grounding(
            assessor.assess(chunk, {"ref": req.ref, "title": req.title, "level": req.level}, cands),
            cands,
        )
        pred = a.coverage_status.value
        exp = label["expected_status"]
        if pred == exp:
            status_correct += 1

        exp_is_gap = exp == "Gap"
        pred_is_gap = pred == "Gap"
        if exp_is_gap and pred_is_gap:
            tp += 1
        elif not exp_is_gap and pred_is_gap:
            fp += 1
        elif exp_is_gap and not pred_is_gap:
            fn += 1
        else:
            tn += 1

        exp_controls = label.get("expected_controls", [])
        if exp_controls:
            retr_expected += 1
            retrieved_ids = {c.control_id for c in cands}
            if any(ec in retrieved_ids for ec in exp_controls):
                retr_hits += 1

        per_row.append({"requirement_id": chunk.ref_id, "expected": exp, "predicted": pred})

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    return {
        "sample_size": n,
        "assessor": assessor_info["assessor"],
        "assessor_is_stub": assessor_info["is_stub"],
        "embedder_backend": retriever.embedder.info.backend,
        "embedder_is_fallback": retriever.embedder.info.is_fallback,
        "top_k": top_k,
        "status_accuracy": round(status_correct / n, 3) if n else None,
        "status_correct": status_correct,
        "gap_detection": {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        },
        "retrieval_recall_at_k": round(retr_hits / retr_expected, 3) if retr_expected else None,
        "retrieval_expected_rows": retr_expected,
        "retrieval_hits": retr_hits,
        "labeler_note": note,
        "per_row": per_row,
    }


def main():
    import sys

    res = run_eval()
    print(json.dumps(res, indent=2))
    print("\n--- SUMMARY ---")
    print(f"Sample size (hand-labeled): {res['sample_size']}")
    print(f"Assessor: {res['assessor']} (stub={res['assessor_is_stub']})")
    print(f"Embedder: {res['embedder_backend']} (fallback={res['embedder_is_fallback']})")
    print(f"3-way status accuracy: {res['status_accuracy']}  ({res['status_correct']}/{res['sample_size']})")
    gd = res["gap_detection"]
    print(f"Gap detection  P={gd['precision']} R={gd['recall']} F1={gd['f1']}  (tp={gd['tp']} fp={gd['fp']} fn={gd['fn']} tn={gd['tn']})")
    print(f"Retrieval recall@{res['top_k']}: {res['retrieval_recall_at_k']}  ({res['retrieval_hits']}/{res['retrieval_expected_rows']})")


if __name__ == "__main__":
    main()
