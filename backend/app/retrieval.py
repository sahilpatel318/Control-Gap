"""Step 4 of the pipeline: for each requirement, retrieve the top-k candidate
controls by embedding similarity.

The retriever holds the control index. For a requirement it returns the k most
similar controls with a cosine-similarity score in [0, 1]. These candidates —
and ONLY these — are what the assessor is later allowed to reason over.
"""
from __future__ import annotations

from typing import List

import numpy as np

from .chunking import Chunk
from .embeddings import BaseEmbedder, get_embedder
from .models import Candidate


class Retriever:
    def __init__(self, control_chunks: List[Chunk], embedder: BaseEmbedder):
        self.control_chunks = control_chunks
        self.embedder = embedder
        self.control_matrix = embedder.encode([c.embed_text for c in control_chunks])

    @classmethod
    def build(
        cls,
        requirement_chunks: List[Chunk],
        control_chunks: List[Chunk],
        prefer_model: bool = True,
    ) -> "Retriever":
        embedder = get_embedder(prefer_model=prefer_model)
        # Fit vectorizers (TF-IDF) on the combined corpus so vocabulary aligns.
        embedder.fit([c.embed_text for c in requirement_chunks + control_chunks])
        return cls(control_chunks, embedder)

    def top_k(self, requirement_chunk: Chunk, k: int = 4) -> List[Candidate]:
        qvec = self.embedder.encode([requirement_chunk.embed_text])[0]
        sims = self.control_matrix @ qvec  # both L2-normalized -> cosine
        order = np.argsort(-sims)[:k]
        out: List[Candidate] = []
        for idx in order:
            chunk = self.control_chunks[int(idx)]
            score = float(np.clip(sims[int(idx)], 0.0, 1.0))
            out.append(
                Candidate(
                    control_id=chunk.ref_id,
                    title=chunk.title,
                    text=chunk.text,
                    score=round(score, 4),
                )
            )
        return out
