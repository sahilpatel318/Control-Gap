"""Step 5 of the pipeline: assess coverage for one requirement given ONLY its
retrieved candidate controls.

Two assessors:
  * LLMAssessor   - calls Anthropic or OpenAI (key via env var). Reasons only
                    over the retrieved candidates that are passed in.
  * StubAssessor  - deterministic, no network, no key. Announces itself as a
                    stub. Uses lexical keyword overlap + partial-language cues.

Both go through verify_grounding(): every citation's control_quote MUST be an
exact substring of a retrieved candidate's text, or it is dropped and the
confidence is reduced. This enforces "no claim without a citation" even when the
underlying model tries to paraphrase or invent evidence.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional, Tuple

from .chunking import Chunk
from .models import (
    Assessment,
    Candidate,
    Citation,
    ConfidenceBand,
    CoverageStatus,
    Severity,
    band_for,
)

STOPWORDS = set(
    "a an and are as at be by for from has have in into is it its of on or that the to "
    "with which when where this these those must may can not no does are all each any "
    "such other using use used via provide provided their they user users content".split()
)

PARTIAL_CUES = [
    "best-effort", "best effort", "not yet", "not mandatory", "not currently",
    "recommends but does not require", "recommend but does not require",
    "encouraged but", "not consistently", "case-by-case", "case by case",
    "partial", "does not address", "out of scope", "not fully", "does not by itself",
    "only", "not require", "is not enforced", "not enforced", "backlog",
]

# Cues that a control explicitly disclaims the topic (pushes toward Gap, not Partial).
DISCLAIM_CUES = [
    "does not address", "out of scope", "not currently specify", "not yet defined",
    "unrelated to", "does not by itself",
]


def _tokens(text: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if t and t not in STOPWORDS}


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.;])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _best_evidence_sentence(req_tokens: set, control_text: str) -> Tuple[str, float]:
    """Return the sentence of the control most lexically related to the requirement,
    plus an overlap ratio. The returned string is an exact substring of control_text.
    """
    best, best_overlap = control_text.strip(), 0.0
    for sent in _split_sentences(control_text):
        st = _tokens(sent)
        if not st:
            continue
        overlap = len(req_tokens & st) / max(1, len(req_tokens))
        if overlap > best_overlap:
            best, best_overlap = sent, overlap
    return best, best_overlap


def _requirement_quote(req_text: str) -> str:
    """First sentence of the requirement, guaranteed to be an exact substring."""
    sents = _split_sentences(req_text)
    return sents[0] if sents else req_text.strip()


def _severity_for(level: str, status: CoverageStatus) -> Severity:
    if status == CoverageStatus.MET:
        return Severity.NONE
    lvl = (level or "").lower()
    high = lvl in ("a", "principle", "obligation", "right")
    med = lvl in ("aa",)
    if status == CoverageStatus.GAP:
        return Severity.HIGH if high else (Severity.MEDIUM if med else Severity.LOW)
    # Partial
    return Severity.MEDIUM if high else Severity.LOW


# --------------------------------------------------------------------------- #
# Grounding verification (applies to every assessor)
# --------------------------------------------------------------------------- #

def verify_grounding(
    assessment: Assessment, candidates: List[Candidate]
) -> Assessment:
    cand_text = {c.control_id: c.text for c in candidates}
    verified: List[Citation] = []
    dropped = 0
    for cit in assessment.citations:
        if cit.control_id is None and cit.control_quote is None:
            verified.append(cit)  # requirement-only citation
            continue
        text = cand_text.get(cit.control_id or "")
        if text and cit.control_quote and cit.control_quote.strip() in text:
            verified.append(cit)
        else:
            dropped += 1
    assessment.citations = verified
    if dropped:
        # Penalize unverifiable evidence and flag it in the rationale.
        assessment.confidence = round(max(0.0, assessment.confidence - 0.25 * dropped), 3)
        assessment.confidence_band = band_for(assessment.confidence)
        assessment.rationale += (
            f" [grounding: {dropped} cited quote(s) could not be verified against the "
            "retrieved control text and were removed; confidence reduced.]"
        )
        # If a positive coverage claim lost all its control evidence, demote to Gap.
        has_control_evidence = any(c.control_id for c in verified)
        if assessment.coverage_status in (CoverageStatus.MET, CoverageStatus.PARTIAL) and not has_control_evidence:
            assessment.coverage_status = CoverageStatus.GAP
            assessment.rationale += " Coverage demoted to Gap: no verifiable control evidence remained."
    return assessment


# --------------------------------------------------------------------------- #
# Deterministic stub assessor
# --------------------------------------------------------------------------- #

class StubAssessor:
    name = "stub"

    # Tuned to be conservative: it would rather flag Partial/Gap for review than
    # over-claim Met. These thresholds operate on lexical overlap, not on the
    # embedder's absolute score, so they behave the same under either backend.
    MET_OVERLAP = 0.34
    PARTIAL_OVERLAP = 0.18

    def assess(self, req: Chunk, req_meta: dict, candidates: List[Candidate]) -> Assessment:
        req_tokens = _tokens(req.embed_text)
        level = req_meta.get("level", "")

        scored = []
        for c in candidates:
            ev_sent, overlap = _best_evidence_sentence(req_tokens, c.text)
            # blend lexical overlap with retrieval score (retrieval is a weak prior)
            strength = 0.75 * overlap + 0.25 * c.score
            scored.append((strength, overlap, c, ev_sent))
        scored.sort(key=lambda x: -x[0])

        if not scored or scored[0][0] < self.PARTIAL_OVERLAP:
            status = CoverageStatus.GAP
            conf = round(min(0.5, 0.3 + 0.2 * (scored[0][0] if scored else 0)), 3)
            rationale = (
                "No retrieved control is lexically close enough to this requirement to "
                "support a mapping. Treated as 'No adequate control found'. "
                "(Stub assessor — deterministic keyword heuristic, not model reasoning.)"
            )
            citations = [Citation(requirement_quote=_requirement_quote(req.text))]
            return Assessment(
                coverage_status=status, confidence=conf, confidence_band=band_for(conf),
                rationale=rationale, citations=citations,
                severity=_severity_for(level, status),
                recommended_remediation=(
                    "No control currently addresses this requirement. Draft and assign "
                    "ownership for a new control, or extend an adjacent control to cover it."
                ),
                assessor=self.name,
            )

        strength, overlap, best, ev_sent = scored[0]
        best_text_lower = best.text.lower()
        disclaims = any(cue in best_text_lower for cue in DISCLAIM_CUES)
        partial_signal = any(cue in best_text_lower for cue in PARTIAL_CUES)

        if disclaims and overlap < self.MET_OVERLAP:
            status = CoverageStatus.GAP
        elif overlap >= self.MET_OVERLAP and not partial_signal:
            status = CoverageStatus.MET
        else:
            status = CoverageStatus.PARTIAL

        # confidence: driven by how strong and how separated the top match is
        second = scored[1][0] if len(scored) > 1 else 0.0
        separation = max(0.0, strength - second)
        conf = 0.35 + 0.55 * min(1.0, strength) + 0.10 * min(1.0, separation * 2)
        if status == CoverageStatus.PARTIAL:
            conf *= 0.8
        conf = round(min(0.95, conf), 3)

        mapped = [best.control_id]
        citations = [
            Citation(requirement_quote=_requirement_quote(req.text)),
            Citation(
                requirement_quote=_requirement_quote(req.text),
                control_id=best.control_id,
                control_quote=ev_sent,
            ),
        ]
        verb = {
            CoverageStatus.MET: "appears to fully address",
            CoverageStatus.PARTIAL: "partially addresses",
            CoverageStatus.GAP: "does not adequately address",
        }[status]
        rationale = (
            f"Control {best.control_id} ({best.title}) {verb} this requirement based on "
            f"lexical overlap ({overlap:.0%}) with the quoted control text"
            + (". A partial-coverage cue was detected in the control text." if partial_signal and status == CoverageStatus.PARTIAL else ".")
            + " (Stub assessor — deterministic keyword heuristic, not model reasoning.)"
        )
        remediation = {
            CoverageStatus.MET: "No remediation required; confirm the control is operating effectively during the next review.",
            CoverageStatus.PARTIAL: f"Strengthen {best.control_id} to close the residual gap (e.g. make the practice mandatory, extend scope, or add enforcement).",
            CoverageStatus.GAP: "Introduce a dedicated control; the closest existing control does not cover this requirement.",
        }[status]

        return Assessment(
            coverage_status=status, confidence=conf, confidence_band=band_for(conf),
            rationale=rationale, citations=citations if status != CoverageStatus.GAP else citations[:1],
            severity=_severity_for(level, status),
            recommended_remediation=remediation,
            assessor=self.name,
        )


# --------------------------------------------------------------------------- #
# LLM assessor (Anthropic / OpenAI)
# --------------------------------------------------------------------------- #

SYSTEM_PROMPT = (
    "You are a meticulous GRC (governance, risk & compliance) analyst mapping a single "
    "regulatory requirement to a company's internal controls. You are given the requirement "
    "and a SHORT LIST of candidate controls retrieved for it. Reason ONLY over the candidates "
    "provided. Never invent a control or cite text that is not present verbatim in a candidate. "
    "If no candidate adequately covers the requirement, return coverage_status 'Gap' with an "
    "empty mapped_control_ids list — 'no adequate control found' is a valid, expected answer. "
    "Quote the EXACT control sentence you relied on. Respond with ONLY a JSON object, no prose, "
    "no markdown fences."
)

JSON_SHAPE = (
    '{"coverage_status": "Met|Partial|Gap|N/A", "confidence": 0.0-1.0, '
    '"mapped_control_ids": ["..."], "rationale": "grounded explanation", '
    '"evidence": [{"control_id": "...", "control_quote": "exact sentence copied from that control"}], '
    '"severity": "None|Low|Medium|High", "recommended_remediation": "..."}'
)


class LLMAssessor:
    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.name = f"{provider}:{model}"
        self._stub = StubAssessor()

    def _build_user_prompt(self, req: Chunk, req_meta: dict, candidates: List[Candidate]) -> str:
        cand_block = "\n\n".join(
            f"[{c.control_id}] {c.title}\n\"{c.text}\"" for c in candidates
        ) or "(no candidates retrieved)"
        return (
            f"REQUIREMENT {req_meta.get('ref','')} — {req.title} "
            f"(level {req_meta.get('level','')}):\n\"{req.text}\"\n\n"
            f"CANDIDATE CONTROLS (the only controls you may cite):\n{cand_block}\n\n"
            f"Return JSON exactly of this shape:\n{JSON_SHAPE}"
        )

    def _call_anthropic(self, user_prompt: str) -> str:
        import httpx

        model = self.model
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 700,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

    def _call_openai(self, user_prompt: str) -> str:
        import httpx

        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _parse(raw: str) -> dict:
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
        # Grab the outermost JSON object if the model added stray text.
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            cleaned = m.group(0)
        return json.loads(cleaned)

    def assess(self, req: Chunk, req_meta: dict, candidates: List[Candidate]) -> Assessment:
        user_prompt = self._build_user_prompt(req, req_meta, candidates)
        try:
            raw = self._call_anthropic(user_prompt) if self.provider == "anthropic" else self._call_openai(user_prompt)
            obj = self._parse(raw)
        except Exception as exc:  # network / parse / auth failure -> stub, flagged
            fallback = self._stub.assess(req, req_meta, candidates)
            fallback.rationale += (
                f" [LLM assessor unavailable ({type(exc).__name__}); fell back to the "
                "deterministic stub for this row.]"
            )
            fallback.assessor = f"{self.name}->stub"
            return fallback

        try:
            status = CoverageStatus(obj.get("coverage_status", "Gap"))
        except ValueError:
            status = CoverageStatus.GAP
        try:
            severity = Severity(obj.get("severity", "Medium"))
        except ValueError:
            severity = Severity.MEDIUM
        conf = float(obj.get("confidence", 0.5))
        conf = max(0.0, min(1.0, conf))

        citations = [Citation(requirement_quote=_requirement_quote(req.text))]
        for ev in obj.get("evidence", []) or []:
            citations.append(
                Citation(
                    requirement_quote=_requirement_quote(req.text),
                    control_id=ev.get("control_id"),
                    control_quote=ev.get("control_quote"),
                )
            )
        assessment = Assessment(
            coverage_status=status,
            confidence=round(conf, 3),
            confidence_band=band_for(conf),
            rationale=str(obj.get("rationale", "")).strip(),
            citations=citations,
            severity=severity,
            recommended_remediation=str(obj.get("recommended_remediation", "")).strip(),
            assessor=self.name,
        )
        return assessment


def build_assessor() -> Tuple[object, dict]:
    """Choose an assessor from environment configuration.

    Precedence: ANTHROPIC_API_KEY -> OpenAI (OPENAI_API_KEY) -> stub.
    Returns (assessor, info) where info describes what is active for the UI.
    """
    provider = (os.getenv("LLM_PROVIDER") or "").lower().strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    def _anthropic():
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        return LLMAssessor("anthropic", model, anthropic_key), {
            "assessor": f"anthropic:{model}", "is_stub": False,
            "detail": "Anthropic model assessing coverage over retrieved candidates.",
        }

    def _openai():
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        return LLMAssessor("openai", model, openai_key), {
            "assessor": f"openai:{model}", "is_stub": False,
            "detail": "OpenAI model assessing coverage over retrieved candidates.",
        }

    if provider == "anthropic" and anthropic_key:
        return _anthropic()
    if provider == "openai" and openai_key:
        return _openai()
    if anthropic_key:
        return _anthropic()
    if openai_key:
        return _openai()

    return StubAssessor(), {
        "assessor": "stub", "is_stub": True,
        "detail": (
            "STUB assessor active: no LLM API key found. Coverage is decided by a "
            "deterministic keyword heuristic, not model reasoning. Results are weaker and "
            "every row should be human-reviewed."
        ),
    }
