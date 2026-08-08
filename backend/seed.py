"""Seed / setup script.

Initializes the SQLite database and runs one analysis for each bundled standard
so the app has data the moment the UI opens. Safe to re-run (it overwrites the
per-standard run). Prints which assessor and embedder backend were used so you
can see immediately whether you're on the stub or a real model.

Usage:
    python seed.py                # default: WCAG + GDPR, prefer neural embedder
    python seed.py --tfidf        # force the TF-IDF fallback embedder
"""
from __future__ import annotations

import argparse

from app import db
from app.pipeline import run_analysis


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tfidf", action="store_true", help="force TF-IDF fallback embedder")
    ap.add_argument("--top-k", type=int, default=4)
    args = ap.parse_args()
    prefer_model = not args.tfidf

    db.init_db()
    for standard_id in ("wcag22", "gdpr_subset"):
        run_id, info = run_analysis(standard_id, top_k=args.top_k, prefer_model=prefer_model)
        a = info["assessor"]
        e = info["embedder"]
        print(f"[seed] standard={standard_id} run_id={run_id}")
        print(f"       assessor = {a['assessor']} (stub={a['is_stub']})")
        print(f"       embedder = {e['backend']} (fallback={e['is_fallback']})")
    print("\n[seed] done. Start the API with:  uvicorn app.main:app --reload --port 8000")


if __name__ == "__main__":
    main()
