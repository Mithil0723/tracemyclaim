from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ExtractorErrorCode = Literal["INSUFFICIENT_TEXT", "UPSTREAM"]
VerifierVerdict = Literal["supported", "contested", "unsupported"]
GraphVerdict = Literal["supported", "contested", "unsupported", "unknown"]
GraphEdgeType = Literal["depends_on", "shares_source", "same_topic"]
CredibilityLabel = Literal["high", "mixed", "low"]
PatternType = Literal["source_clustering", "topic_skew", "consistency_break"]


class ClaimExtractorInput(BaseModel):
    article_id: str
    text: str
    source_url: str | None


class ExtractedClaim(BaseModel):
    claim_id: str
    text: str
    original_quote: str
    importance: float
    controversy: float
    topic_tags: list[str]


class ClaimExtractorData(BaseModel):
    claims: list[ExtractedClaim]


class ClaimExtractorSuccess(BaseModel):
    status: Literal["ok"]
    data: ClaimExtractorData


class ClaimExtractorError(BaseModel):
    status: Literal["error"]
    error_code: ExtractorErrorCode
    message: str | None = None


class VerifierInput(BaseModel):
    claim_id: str
    claim_text: str
    topic_tags: list[str]


class VerificationSource(BaseModel):
    url: str
    title: str
    evidence_quote: str
    supports: bool


class VerifierData(BaseModel):
    claim_id: str
    verdict: VerifierVerdict
    confidence: float
    sources: list[VerificationSource]
    reasoning: str


class VerifierSuccess(BaseModel):
    status: Literal["ok"]
    data: VerifierData


class VerifierError(BaseModel):
    status: Literal["error"]
    error_code: Literal["UPSTREAM", "TIMEOUT"]
    message: str | None = None


class ClaimWithVerdict(BaseModel):
    claim_id: str
    text: str
    original_quote: str
    importance: float
    controversy: float
    topic_tags: list[str]
    verdict: GraphVerdict
    confidence: float
    sources: list[VerificationSource]
    reasoning: str


class DecisionGraphBuilderInput(BaseModel):
    extractor_output: ClaimExtractorSuccess
    verifier_outputs: list[VerifierSuccess | VerifierError]


class DecisionGraphNode(BaseModel):
    claim_id: str
    verdict: GraphVerdict
    confidence: float
    importance: float
    weight: float


class DecisionGraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    type: GraphEdgeType


class DecisionGraph(BaseModel):
    nodes: list[DecisionGraphNode]
    edges: list[DecisionGraphEdge]
    credibility_score: float
    top_findings_input: list[str]


class MetaReviewerInput(BaseModel):
    article_id: str
    claims: list[ClaimWithVerdict]
    graph: DecisionGraph
    credibility_score: float


class TopFinding(BaseModel):
    claim_id: str
    headline: str
    explanation: str


class PatternObservation(BaseModel):
    type: PatternType
    description: str


class MetaReviewerData(BaseModel):
    credibility_score: float
    credibility_label: CredibilityLabel
    top_findings: list[TopFinding]
    patterns: list[PatternObservation]
    summary: str


class MetaReviewerOutput(BaseModel):
    status: Literal["ok"]
    data: MetaReviewerData
