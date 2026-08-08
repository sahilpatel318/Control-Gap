"""Step 1 of the pipeline: parse requirements and controls into structured
records with stable IDs.

The bundled data is already atomic (one object per requirement / control), so
"parsing" here means validating each record against the schema and guaranteeing
a stable, unique ID. If a future data source were free-form text, this is the
module that would split it into records — the rest of the pipeline depends only
on the typed records produced here, not on the source format.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from .models import Control, Requirement

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

STANDARD_FILES = {
    "wcag22": "wcag22.json",
    "gdpr_subset": "gdpr_subset.json",
}


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def available_standards() -> List[dict]:
    out = []
    for sid, fname in STANDARD_FILES.items():
        raw = _load_json(DATA_DIR / fname)
        out.append(
            {
                "standard_id": sid,
                "standard_name": raw.get("standard_name", sid),
                "count": len(raw.get("requirements", [])),
                "source_url": raw.get("source_url"),
                "source_note": raw.get("source_note"),
            }
        )
    return out


def load_requirements(standard_id: str) -> Tuple[List[Requirement], dict]:
    if standard_id not in STANDARD_FILES:
        raise ValueError(f"Unknown standard '{standard_id}'")
    raw = _load_json(DATA_DIR / STANDARD_FILES[standard_id])
    reqs: List[Requirement] = []
    seen = set()
    for item in raw.get("requirements", []):
        req = Requirement(**item)
        if req.requirement_id in seen:
            raise ValueError(f"Duplicate requirement_id: {req.requirement_id}")
        seen.add(req.requirement_id)
        reqs.append(req)
    meta = {
        "standard_id": standard_id,
        "standard_name": raw.get("standard_name"),
        "source_url": raw.get("source_url"),
        "source_note": raw.get("source_note"),
    }
    return reqs, meta


def load_controls() -> Tuple[List[Control], dict]:
    raw = _load_json(DATA_DIR / "controls.json")
    controls: List[Control] = []
    seen = set()
    for item in raw.get("controls", []):
        ctrl = Control(**item)
        if ctrl.control_id in seen:
            raise ValueError(f"Duplicate control_id: {ctrl.control_id}")
        seen.add(ctrl.control_id)
        controls.append(ctrl)
    meta = {
        "org_name": raw.get("org_name"),
        "source_note": raw.get("source_note"),
        "count": len(controls),
    }
    return controls, meta
