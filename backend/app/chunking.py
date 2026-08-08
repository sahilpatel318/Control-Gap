"""Step 2 of the pipeline: chunk by requirement / control boundary.

We deliberately do NOT use fixed-size sliding windows. In a compliance mapping
task, the natural unit of meaning is a single requirement clause or a single
control statement. Splitting mid-clause would let a match cite half a sentence
and lose the traceability the whole product depends on.

Each chunk therefore corresponds to exactly one requirement or one control, and
carries the ID and a compact, human-readable "embedding text" that concatenates
the fields a reviewer would read to judge relevance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .models import Control, Requirement


@dataclass
class Chunk:
    kind: str            # "requirement" | "control"
    ref_id: str          # requirement_id or control_id
    title: str
    text: str            # the exact clause/control text (what gets cited)
    embed_text: str      # enriched text used for embedding / retrieval only


def requirement_chunks(reqs: List[Requirement]) -> List[Chunk]:
    chunks = []
    for r in reqs:
        embed = f"{r.ref} {r.title}. {r.text} Keywords: {', '.join(r.keywords)}"
        chunks.append(
            Chunk(kind="requirement", ref_id=r.requirement_id, title=r.title,
                  text=r.text, embed_text=embed)
        )
    return chunks


def control_chunks(controls: List[Control]) -> List[Chunk]:
    chunks = []
    for c in controls:
        embed = f"{c.title} ({c.category}, owner {c.owner}). {c.text} Tags: {', '.join(c.tags)}"
        chunks.append(
            Chunk(kind="control", ref_id=c.control_id, title=c.title,
                  text=c.text, embed_text=embed)
        )
    return chunks
