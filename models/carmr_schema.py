"""
Pydantic models matching the exact schema expected by the Effectus FE (data.js).
"""
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ── Commitment (C) ──────────────────────────────────────────────────────────

class RecordData(BaseModel):
    title: str = ""
    date: str = ""
    sponsor: str = ""
    owner: str = ""
    statementWhat: str = ""
    statementWhyNow: str = ""
    statementScope: str = ""
    statementOutcomes: str = ""
    reversibility: Literal["full", "partial", "irreversible", ""] = ""
    exitCostMin: str = ""
    exitCostMax: str = ""
    portfolio: str = ""
    status: Literal["draft", "active", "under-review", "closed"] = "draft"
    irreversibleAcknowledged: bool = False
    scrId: str = ""


# ── Assumptions (A) ──────────────────────────────────────────────────────────

class Assumption(BaseModel):
    id: str
    parentId: Optional[str] = None   # None = parent; set to parent id = child
    statement: str = ""
    owner: str = ""
    status: Literal["active", "at-risk", "failed", "superseded"] = "active"
    confidence: Literal["high", "medium", "low", "unknown"] = "unknown"
    falsification: str = ""
    dissentingView: str = ""
    isImplicit: bool = False          # True if never stated explicitly in the document
    sourceFallacy: str = ""          # e.g. "ad populum" - one of the 16 fallacy names
    sourceQuote: str = ""            # verbatim text from the source document (code-verified)
    excavationNote: str = ""         # 1-2 plain sentences: what the document did and what is recorded here


# ── Reasoning (R) ────────────────────────────────────────────────────────────

class ReasoningBlock(BaseModel):
    id: str
    linkedAssumptions: List[str] = Field(default_factory=list)
    assumptionWeights: dict = Field(default_factory=dict)
    # {assumptionId: 'critical' | 'supporting' | 'contextual'}
    # 'critical' = necessary premise; block suffers undercutting defeat if this assumption fails (Pollock 1987)
    # 'supporting' = strengthens warrant but block survives falsification with revision
    # 'contextual' = background condition; not a direct premise in the inference rule
    gapJustification: str = ""
    # Populated ONLY when linkedAssumptions is empty.
    # The implicit premise the author is relying on - excavated from the document.
    # A governance gap: this reasoning step is undefended (Dung 1995 grounded extension).
    # Should be surfaced to the user as a candidate for promotion to a governed assumption.
    then: str = ""
    because: str = ""
    elaboration: str = ""


# ── Meaning (M) ──────────────────────────────────────────────────────────────

class MeaningTerm(BaseModel):
    id: str
    term: str = ""
    autoDetected: bool = True
    contextQuote: str = ""
    definition: str = ""
    driftRisk: str = ""


# ── Review Triggers (R) ──────────────────────────────────────────────────────

class ReviewTrigger(BaseModel):
    id: str
    type: Literal["time", "event"] = "time"
    description: str = ""
    nextReviewDue: str = ""
    overdue: bool = False


# ── Review Events ─────────────────────────────────────────────────────────────

class ReviewEvent(BaseModel):
    date: str = ""
    triggerType: str = ""
    outcome: str = ""
    reviewerName: str = ""


# ── Field-level confidence ───────────────────────────────────────────────────

class FieldConfidence(BaseModel):
    field: str
    score: float  # 0.0 - 1.0
    note: Optional[str] = None


# ── Stage quality report ─────────────────────────────────────────────────────

class StageQualityReport(BaseModel):
    stage: str
    quality_score: float       # 0.0 - 1.0
    issues: List[str] = Field(default_factory=list)
    research_used: List[str] = Field(default_factory=list)
    attempts: int = 1
    warnings: List[str] = Field(default_factory=list)


# ── Full CARMR record ────────────────────────────────────────────────────────

class CARMRRecord(BaseModel):
    scrId: str = ""
    recordData: RecordData = Field(default_factory=RecordData)
    assumptions: List[Assumption] = Field(default_factory=list)
    reasoningBlocks: List[ReasoningBlock] = Field(default_factory=list)
    meaningTerms: List[MeaningTerm] = Field(default_factory=list)
    reviewTriggers: List[ReviewTrigger] = Field(default_factory=list)
    reviewEvents: List[ReviewEvent] = Field(default_factory=list)


# ── Full pipeline output ──────────────────────────────────────────────────────

class ExtractionResult(BaseModel):
    job_id: str
    carmr: CARMRRecord
    cis: float = 0.0
    cis_breakdown: dict = Field(default_factory=dict)
    overall_confidence: float = 0.0
    field_confidence: List[FieldConfidence] = Field(default_factory=list)
    stage_reports: List[StageQualityReport] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    research_citations: List[str] = Field(default_factory=list)
    extracted_from: List[str] = Field(default_factory=list)
    processing_time_seconds: float = 0.0
