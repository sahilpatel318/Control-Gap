"""Data models and controlled vocabularies for ControlGap.

These types define the shape of every record that flows through the pipeline
and out to the gap register. Keeping them in one place makes the traceability
guarantees easy to audit: a register row cannot exist without the fields below.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class CoverageStatus(str, Enum):
    MET = "Met"
    PARTIAL = "Partial"
    GAP = "Gap"
    NA = "N/A"


class ConfidenceBand(str, Enum):
    LOW = "Low"
    MED = "Med"
    HIGH = "High"


class ReviewStatus(str, Enum):
    AI_PROPOSED = "AI-proposed"
    ACCEPTED = "Accepted"
    EDITED = "Edited"
    REJECTED = "Rejected"


class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    NONE = "None"


class Requirement(BaseModel):
    requirement_id: str
    ref: str
    title: str
    level: str
    principle: str
    text: str
    keywords: List[str] = Field(default_factory=list)


class Control(BaseModel):
    control_id: str
    title: str
    owner: str
    category: str
    text: str
    tags: List[str] = Field(default_factory=list)


class Candidate(BaseModel):
    """A control retrieved as a candidate match for a requirement."""
    control_id: str
    title: str
    text: str
    score: float  # retrieval similarity in [0, 1]


class Citation(BaseModel):
    """Exact text spans the assessment relied on. No claim without a citation."""
    requirement_quote: str
    control_id: Optional[str] = None
    control_quote: Optional[str] = None


class Assessment(BaseModel):
    coverage_status: CoverageStatus
    confidence: float  # 0..1
    confidence_band: ConfidenceBand
    rationale: str
    citations: List[Citation] = Field(default_factory=list)
    severity: Severity
    recommended_remediation: str
    assessor: str  # "stub" | "anthropic:<model>" | "openai:<model>"


class GapRow(BaseModel):
    """One row of the gap register — the product."""
    requirement_id: str
    requirement_ref: str
    requirement_title: str
    requirement_summary: str
    requirement_text: str
    mapped_control_ids: List[str] = Field(default_factory=list)
    candidates: List[Candidate] = Field(default_factory=list)
    coverage_status: CoverageStatus
    confidence: float
    confidence_band: ConfidenceBand
    rationale: str
    citations: List[Citation] = Field(default_factory=list)
    severity: Severity
    recommended_remediation: str
    review_status: ReviewStatus = ReviewStatus.AI_PROPOSED
    reviewer_note: str = ""
    assessor: str = "stub"


class ReviewUpdate(BaseModel):
    """Payload the analyst sends when accepting / editing / rejecting a row."""
    review_status: ReviewStatus
    reviewer_note: Optional[str] = None
    coverage_status: Optional[CoverageStatus] = None
    mapped_control_ids: Optional[List[str]] = None
    severity: Optional[Severity] = None
    recommended_remediation: Optional[str] = None


def band_for(confidence: float) -> ConfidenceBand:
    if confidence >= 0.75:
        return ConfidenceBand.HIGH
    if confidence >= 0.45:
        return ConfidenceBand.MED
    return ConfidenceBand.LOW
