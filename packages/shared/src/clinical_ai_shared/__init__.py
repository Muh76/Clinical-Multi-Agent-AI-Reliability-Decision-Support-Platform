"""Shared contracts and domain primitives."""

from clinical_ai_shared.explainability import (
    CitationFormat,
    ConfidenceBand,
    ConfidenceRepresentation,
    ContributionDirection,
    EvidenceAttribution,
    ExplainableOutput,
    ModalityContribution,
    OutputAudience,
    ReasoningMetadata,
    RiskContributionSummary,
    WorkflowTraceLink,
    attach_formatted_citations,
    format_citation,
    redacted_observability_payload,
    serialize_explainable_output,
    serialize_explainable_output_json,
)

__all__ = [
    "CitationFormat",
    "ConfidenceBand",
    "ConfidenceRepresentation",
    "ContributionDirection",
    "EvidenceAttribution",
    "ExplainableOutput",
    "ModalityContribution",
    "OutputAudience",
    "ReasoningMetadata",
    "RiskContributionSummary",
    "WorkflowTraceLink",
    "attach_formatted_citations",
    "format_citation",
    "redacted_observability_payload",
    "serialize_explainable_output",
    "serialize_explainable_output_json",
]

