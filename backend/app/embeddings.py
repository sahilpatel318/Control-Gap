"""Step 3 of the pipeline: embed chunks locally (no API key required).

Primary path: a local sentence-transformers model (default all-MiniLM-L6-v2).
Fallback path: scikit-learn TF-IDF vectors.

Why a fallback exists (documented honesty):
The sentence-transformers model weights are downloaded from the Hugging Face
hub on first use. In a fully offline environment, or one without network access
to that host, the model cannot load. Rather than crash, ControlGap falls back to
a deterministic TF-IDF vectorizer so the whole pipeline still runs end-to-end.
TF-IDF is lexical only — it matches shared vocabulary, not meaning — so retrieval
quality is lower than the neural model. The active backend is reported through the
API and shown in the UI so a reviewer always knows which one produced a result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np


@dataclass
class EmbedderInfo:
    backend: str          # "sentence-transformers:<model>" | "tfidf"
    is_fallback: bool
    detail: str


class BaseEmbedder:
    info: EmbedderInfo

    def fit(self, corpus: List[str]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def encode(self, texts: List[str]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


class SentenceTransformerEmbedder(BaseEmbedder):
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # lazy import

        self.model = SentenceTransformer(model_name)
        self.info = EmbedderInfo(
            backend=f"sentence-transformers:{model_name}",
            is_fallback=False,
            detail="Local neural sentence embeddings (semantic retrieval).",
        )

    def fit(self, corpus: List[str]) -> None:
        # No fitting needed for a pretrained model.
        return None

    def encode(self, texts: List[str]) -> np.ndarray:
        vecs = self.model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32)


class TfidfEmbedder(BaseEmbedder):
    def __init__(self, detail: str):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vectorizer = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2), min_df=1
        )
        self._fitted = False
        self.info = EmbedderInfo(
            backend="tfidf",
            is_fallback=True,
            detail=detail,
        )

    def fit(self, corpus: List[str]) -> None:
        self.vectorizer.fit(corpus)
        self._fitted = True

    def encode(self, texts: List[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("TfidfEmbedder.encode called before fit().")
        mat = self.vectorizer.transform(texts).toarray().astype(np.float32)
        # L2-normalize so dot product == cosine similarity.
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return mat / norms


def get_embedder(
    model_name: str = "all-MiniLM-L6-v2",
    prefer_model: bool = True,
) -> BaseEmbedder:
    """Return the best available embedder.

    Tries the neural model first (unless prefer_model is False); on any failure
    (package missing, no network to download weights, etc.) returns a labeled
    TF-IDF fallback. Never raises for the ordinary "no model available" case.
    """
    if prefer_model:
        try:
            return SentenceTransformerEmbedder(model_name)
        except Exception as exc:  # broad on purpose: any load failure -> fallback
            reason = str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__
            return TfidfEmbedder(
                detail=(
                    "Lexical TF-IDF fallback in use because the sentence-transformers "
                    f"model could not be loaded ({reason}). Retrieval is keyword-based, "
                    "not semantic; treat borderline matches with extra caution."
                )
            )
    return TfidfEmbedder(
        detail="Lexical TF-IDF fallback selected explicitly (prefer_model=False)."
    )
