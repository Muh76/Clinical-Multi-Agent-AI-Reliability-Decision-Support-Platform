from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from clinical_ai_agents.observability import (
    MetricsSink,
    WorkflowTraceGraph,
    record_workflow_observability,
)
from clinical_ai_agents.orchestration import AgentWorkflowOrchestrator, WorkflowExecutionOutput
from clinical_ai_shared.explainability import (
    ConfidenceBand as SharedConfidenceBand,
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
    redacted_observability_payload,
)
from clinical_ai_platform.observability import get_logger
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(__name__)


class EndToEndWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str
    patient_context: dict[str, Any]
    evidence_query: str | None = None
    evidence_corpus: list[dict[str, Any]] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    top_k: int = Field(default=10, ge=1, le=100)
    candidate_limit: int = Field(default=50, ge=1, le=500)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class EndToEndWorkflowOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    output_id: str
    workflow_id: str
    trace_id: str
    case_id: str
    status: str
    structured_patient_context: dict[str, Any] = Field(default_factory=dict)
    retrieved_evidence: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence_scores: dict[str, Any] = Field(default_factory=dict)
    risk_analysis: dict[str, Any] = Field(default_factory=dict)
    escalation_indicators: list[dict[str, Any]] = Field(default_factory=list)
    explainability: dict[str, Any] = Field(default_factory=dict)
    workflow_trace: dict[str, Any] = Field(default_factory=dict)
    observability: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EndToEndClinicalReliabilityWorkflowRunner:
    def __init__(
        self,
        *,
        orchestrator: AgentWorkflowOrchestrator | None = None,
        metrics_sink: MetricsSink | None = None,
    ) -> None:
        self._orchestrator = orchestrator or AgentWorkflowOrchestrator()
        self._metrics_sink = metrics_sink

    async def run(
        self,
        request: EndToEndWorkflowRequest,
        *,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EndToEndWorkflowOutput:
        logger.info(
            "end_to_end_workflow_started",
            case_id=request.case_id,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        payload = workflow_payload(request)
        workflow_output = await self._orchestrator.run_patient_evidence_risk_workflow(
            case_id=request.case_id,
            payload=payload,
            request_id=request_id,
            correlation_id=correlation_id,
            metadata=request.metadata,
        )
        trace_graph = await record_workflow_observability(
            workflow_output,
            metrics_sink=self._metrics_sink,
        )
        explainable_output = build_explainable_output(
            workflow_output=workflow_output,
            trace_graph=trace_graph,
        )
        final_output = build_final_output(
            workflow_output=workflow_output,
            trace_graph=trace_graph,
            explainable_output=explainable_output,
        )
        logger.info(
            "end_to_end_workflow_completed",
            output_id=final_output.output_id,
            workflow_id=final_output.workflow_id,
            trace_id=final_output.trace_id,
            case_id=final_output.case_id,
            status=final_output.status,
            confidence_score=final_output.confidence_scores.get("workflow"),
            evidence_count=len(final_output.retrieved_evidence),
            escalation_indicator_count=len(final_output.escalation_indicators),
        )
        return final_output


def workflow_payload(request: EndToEndWorkflowRequest) -> dict[str, Any]:
    return {
        "patient_context": request.patient_context,
        "evidence_query": request.evidence_query,
        "evidence_corpus": request.evidence_corpus,
        "filters": request.filters,
        "top_k": request.top_k,
        "candidate_limit": request.candidate_limit,
    }


def build_final_output(
    *,
    workflow_output: WorkflowExecutionOutput,
    trace_graph: WorkflowTraceGraph,
    explainable_output: ExplainableOutput,
) -> EndToEndWorkflowOutput:
    patient_payload = node_structured_payload(workflow_output, "patient_context")
    evidence_payload = node_structured_payload(workflow_output, "evidence_retrieval")
    risk_payload = node_structured_payload(workflow_output, "risk_analysis")
    evidence_package = evidence_payload.get("evidence_package", {})
    risk_analysis = risk_payload.get("risk_analysis", {})
    formatted_explainability = attach_formatted_citations(explainable_output)
    return EndToEndWorkflowOutput(
        output_id=explainable_output.output_id,
        workflow_id=workflow_output.workflow_id,
        trace_id=workflow_output.trace_id,
        case_id=workflow_output.case_id,
        status=workflow_output.status.value,
        structured_patient_context=patient_payload.get("structured_patient_context", {}),
        retrieved_evidence=evidence_package.get("evidence", []),
        citations=[
            citation.model_dump(mode="json")
            for citation in formatted_explainability.citations
        ],
        confidence_scores=confidence_scores(workflow_output),
        risk_analysis=risk_analysis,
        escalation_indicators=risk_analysis.get("escalation_indicators", []),
        explainability=formatted_explainability.model_dump(mode="json"),
        workflow_trace=trace_graph.model_dump(mode="json"),
        observability=redacted_observability_payload(formatted_explainability),
    )


def build_explainable_output(
    *,
    workflow_output: WorkflowExecutionOutput,
    trace_graph: WorkflowTraceGraph,
) -> ExplainableOutput:
    patient_payload = node_structured_payload(workflow_output, "patient_context")
    evidence_payload = node_structured_payload(workflow_output, "evidence_retrieval")
    risk_payload = node_structured_payload(workflow_output, "risk_analysis")
    patient_representation = patient_payload.get("patient_representation", {})
    evidence_package = evidence_payload.get("evidence_package", {})
    risk_analysis = risk_payload.get("risk_analysis", {})
    return ExplainableOutput(
        output_id=f"explainable-output-{uuid4()}",
        output_type="clinical_reliability_workflow",
        audience=[
            OutputAudience.CLINICIAN_DASHBOARD,
            OutputAudience.SAFETY_CRITIC,
            OutputAudience.AUDIT,
            OutputAudience.EVALUATION,
            OutputAudience.OBSERVABILITY,
        ],
        trace=WorkflowTraceLink(
            workflow_id=workflow_output.workflow_id,
            trace_id=workflow_output.trace_id,
            case_id=workflow_output.case_id,
            agent_run_ids=[result.agent_run_id for result in workflow_output.node_results],
            node_ids=[result.node_id for result in workflow_output.node_results],
        ),
        summary=workflow_summary(workflow_output, evidence_package, risk_analysis),
        evidence_attributions=evidence_attributions(evidence_package),
        confidence=ConfidenceRepresentation(
            score=workflow_output.confidence.score,
            band=shared_confidence_band(workflow_output.confidence.band.value),
            components=workflow_output.confidence.components,
            rationale=workflow_output.confidence.rationale,
        ),
        reasoning_metadata=reasoning_metadata(workflow_output, evidence_package, risk_analysis),
        modality_contributions=modality_contributions(patient_representation),
        risk_contributions=risk_contributions(risk_analysis),
        structured_payload={
            "patient_context_id": patient_representation.get("context_id"),
            "retrieved_evidence_count": len(evidence_package.get("evidence", [])),
            "risk_level": risk_analysis.get("risk_level"),
            "workflow_status": workflow_output.status.value,
            "trace_graph": trace_graph.model_dump(mode="json"),
        },
    )


def node_structured_payload(
    workflow_output: WorkflowExecutionOutput,
    node_id: str,
) -> dict[str, Any]:
    for result in workflow_output.node_results:
        if result.node_id == node_id and result.output is not None:
            return result.output.structured_payload
    return {}


def confidence_scores(workflow_output: WorkflowExecutionOutput) -> dict[str, Any]:
    scores: dict[str, Any] = {
        "workflow": workflow_output.confidence.score,
        "workflow_band": workflow_output.confidence.band.value,
        "agents": {},
    }
    for result in workflow_output.node_results:
        if result.output is not None:
            scores["agents"][result.node_id] = {
                "score": result.output.confidence.score,
                "band": result.output.confidence.band.value,
                "components": result.output.confidence.components,
                "rationale": result.output.confidence.rationale,
            }
    return scores


def evidence_attributions(evidence_package: dict[str, Any]) -> list[EvidenceAttribution]:
    citations = {
        citation.get("citation_id"): citation
        for citation in evidence_package.get("citations", [])
        if isinstance(citation, dict)
    }
    attributions: list[EvidenceAttribution] = []
    for item in evidence_package.get("evidence", []):
        if not isinstance(item, dict):
            continue
        citation_id = str(item.get("citation_id") or item.get("source_id") or item.get("chunk_id"))
        citation = citations.get(citation_id, {})
        attributions.append(
            EvidenceAttribution(
                evidence_id=str(item.get("chunk_id") or item.get("source_id") or citation_id),
                citation_id=citation_id,
                source_id=str(item.get("source_id") or citation.get("source_id") or citation_id),
                source_type=str(
                    item.get("source_type") or citation.get("source_type") or "unknown"
                ),
                title=item.get("title") or citation.get("title"),
                url=citation.get("url"),
                publication_year=citation.get("publication_year"),
                section_path=list(citation.get("section_path", [])),
                quote=citation.get("quote") or item.get("text", "")[:500],
                relevance_score=item.get("score"),
                source_reliability_score=item.get("source_reliability_score"),
                attribution_text=str(
                    citation.get("attribution_text")
                    or item.get("citation_id")
                    or citation_id
                ),
            )
        )
    return attributions


def modality_contributions(patient_representation: dict[str, Any]) -> list[ModalityContribution]:
    contributions: list[ModalityContribution] = []
    for summary in patient_representation.get("modality_summaries", []):
        if not isinstance(summary, dict):
            continue
        contributions.append(
            ModalityContribution(
                modality=str(summary.get("modality", "unknown")),
                present=bool(summary.get("present", False)),
                record_count=int(summary.get("record_count", 0)),
                contribution_direction=ContributionDirection.CONTEXTUAL,
                contribution_score=1.0 if summary.get("present") else 0.0,
                summary=(
                    f"{summary.get('modality', 'unknown')} contributed "
                    f"{summary.get('record_count', 0)} records."
                ),
                missingness_notes=(
                    [f"{summary.get('missing_field_count', 0)} missing fields"]
                    if summary.get("missing_field_count", 0)
                    else []
                ),
            )
        )
    return contributions


def risk_contributions(risk_analysis: dict[str, Any]) -> list[RiskContributionSummary]:
    contributions: list[RiskContributionSummary] = []
    for factor in risk_analysis.get("contributing_factors", []):
        if not isinstance(factor, dict):
            continue
        contributions.append(
            RiskContributionSummary(
                factor_id=str(factor.get("code", "risk.factor")),
                severity=str(factor.get("severity", "unknown")),
                summary=str(factor.get("message", "Risk contribution.")),
                contribution_score=risk_contribution_score(str(factor.get("severity", ""))),
                source_refs=[str(ref) for ref in factor.get("source_refs", [])],
                evidence_refs=[str(ref) for ref in factor.get("evidence_refs", [])],
                uncertainty=factor.get("uncertainty"),
            )
        )
    return contributions


def reasoning_metadata(
    workflow_output: WorkflowExecutionOutput,
    evidence_package: dict[str, Any],
    risk_analysis: dict[str, Any],
) -> list[ReasoningMetadata]:
    return [
        ReasoningMetadata(
            reasoning_id="workflow.execution",
            summary="Executed patient context, evidence retrieval, and risk analysis agents.",
            method="structured_agent_orchestration",
            input_refs=[workflow_output.case_id],
            limitations=(
                []
                if workflow_output.status.value == "completed"
                else ["Workflow incomplete."]
            ),
        ),
        ReasoningMetadata(
            reasoning_id="evidence.retrieval",
            summary=(
                f"Retrieved {len(evidence_package.get('evidence', []))} evidence items with "
                f"{len(evidence_package.get('citations', []))} citations."
            ),
            method="metadata_aware_evidence_retrieval",
            evidence_refs=[
                str(item.get("citation_id") or item.get("source_id"))
                for item in evidence_package.get("evidence", [])
                if isinstance(item, dict)
            ],
            limitations=evidence_package.get("retrieval_metadata", {}).get(
                "reliability_notes",
                [],
            ),
        ),
        ReasoningMetadata(
            reasoning_id="risk.analysis",
            summary=(
                f"Risk level: {risk_analysis.get('risk_level', 'unknown')}; "
                f"escalation indicators: {len(risk_analysis.get('escalation_indicators', []))}."
            ),
            method="risk_oriented_reliability_analysis",
            risk_factor_refs=[
                str(factor.get("code"))
                for factor in risk_analysis.get("contributing_factors", [])
                if isinstance(factor, dict) and factor.get("code")
            ],
            limitations=risk_analysis.get("uncertainty_metadata", {}).get("limitations", []),
        ),
    ]


def workflow_summary(
    workflow_output: WorkflowExecutionOutput,
    evidence_package: dict[str, Any],
    risk_analysis: dict[str, Any],
) -> str:
    return (
        "Fully orchestrated clinical reliability workflow completed with status "
        f"{workflow_output.status.value}. Retrieved {len(evidence_package.get('evidence', []))} "
        f"evidence items. Risk level: {risk_analysis.get('risk_level', 'unknown')}. "
        "No chatbot response or diagnosis was generated."
    )


def risk_contribution_score(severity: str) -> float:
    return {
        "critical": 1.0,
        "high": 0.8,
        "moderate": 0.5,
        "low": 0.25,
    }.get(severity, 0.1)


def shared_confidence_band(value: str) -> SharedConfidenceBand:
    try:
        return SharedConfidenceBand(value)
    except ValueError:
        return SharedConfidenceBand.UNKNOWN
