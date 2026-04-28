export type ExtractorErrorCode = "INSUFFICIENT_TEXT";
export type VerifierVerdict = "supported" | "contested" | "unsupported";
export type GraphVerdict =
  | "supported"
  | "contested"
  | "unsupported"
  | "unknown";
export type GraphEdgeType = "depends_on" | "shares_source" | "same_topic";
export type CredibilityLabel = "high" | "mixed" | "low";
export type PatternType =
  | "source_clustering"
  | "topic_skew"
  | "consistency_break";

export interface ClaimExtractorInput {
  article_id: string;
  text: string;
  source_url: string | null;
}

export interface ExtractedClaim {
  claim_id: string;
  text: string;
  original_quote: string;
  importance: number;
  controversy: number;
  topic_tags: string[];
}

export interface ClaimExtractorData {
  claims: ExtractedClaim[];
}

export interface ClaimExtractorSuccess {
  status: "ok";
  data: ClaimExtractorData;
}

export interface ClaimExtractorError {
  status: "error";
  error_code: ExtractorErrorCode;
  message?: string;
}

export interface VerifierInput {
  claim_id: string;
  claim_text: string;
  topic_tags: string[];
}

export interface VerificationSource {
  url: string;
  title: string;
  evidence_quote: string;
  supports: boolean;
}

export interface VerifierData {
  claim_id: string;
  verdict: VerifierVerdict;
  confidence: number;
  sources: VerificationSource[];
  reasoning: string;
}

export interface VerifierSuccess {
  status: "ok";
  data: VerifierData;
}

export interface VerifierError {
  status: "error";
  error_code: "UPSTREAM" | "TIMEOUT";
  message?: string;
}

export interface ClaimWithVerdict {
  claim_id: string;
  text: string;
  original_quote: string;
  importance: number;
  controversy: number;
  topic_tags: string[];
  verdict: GraphVerdict;
  confidence: number;
  sources: VerificationSource[];
  reasoning: string;
}

export interface DecisionGraphBuilderInput {
  extractor_output: ClaimExtractorSuccess;
  verifier_outputs: Array<VerifierSuccess | VerifierError>;
}

export interface DecisionGraphNode {
  claim_id: string;
  verdict: GraphVerdict;
  confidence: number;
  importance: number;
  weight: number;
}

export interface DecisionGraphEdge {
  from: string;
  to: string;
  type: GraphEdgeType;
}

export interface DecisionGraph {
  nodes: DecisionGraphNode[];
  edges: DecisionGraphEdge[];
  credibility_score: number;
  top_findings_input: string[];
}

export interface MetaReviewerInput {
  article_id: string;
  claims: ClaimWithVerdict[];
  graph: DecisionGraph;
  credibility_score: number;
}

export interface TopFinding {
  claim_id: string;
  headline: string;
  explanation: string;
}

export interface PatternObservation {
  type: PatternType;
  description: string;
}

export interface MetaReviewerData {
  credibility_score: number;
  credibility_label: CredibilityLabel;
  top_findings: TopFinding[];
  patterns: PatternObservation[];
  summary: string;
}

export interface MetaReviewerOutput {
  status: "ok";
  data: MetaReviewerData;
}
