from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol

from clinical_ai_agents.contracts import AgentInput, AgentOutput, AgentRole, ClinicalAgent
from clinical_ai_platform.observability import bind_execution_context, get_logger
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(__name__)


class ObservabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TokenUsage(ObservabilityModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    provider: str | None = None
    model: str | None = None
    estimation_method: str = "not_measured"


class LatencyBreakdown(ObservabilityModel):
    total_ms: float = Field(ge=0.0)
    retrieval_ms: float | None = Field(default=None, ge=0.0)
    reranking_ms: float | None = Field(default=None, ge=0.0)
    risk_scoring_ms: float | None = Field(default=None, ge=0.0)
    serialization_ms: float | None = Field(default=None, ge=0.0)


class AgentExecutionTrace(ObservabilityModel):
    workflow_id: str
    trace_id: str
    agent_run_id: str
    parent_agent_run_id: str | None = None
    case_id: str
    agent_name: str
    agent_role: AgentRole
    sequence_index: int = Field(ge=0)
    status: str
    started_at: datetime
    completed_at: datetime
    latency: LatencyBreakdown
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_band: str | None = None
    evidence_sources: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    escalation_indicators: list[str] = Field(default_factory=list)
    risk_events: list[str] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class WorkflowTraceNode(ObservabilityModel):
    node_id: str
    agent_role: AgentRole
    agent_run_id: str
    status: str
    latency_ms: float = Field(ge=0.0)
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)


class WorkflowTraceEdge(ObservabilityModel):
    source_node_id: str
    target_node_id: str
    condition: str = "success"


class WorkflowTraceGraph(ObservabilityModel):
    workflow_id: str
    trace_id: str
    case_id: str
    graph_id: str
    status: str
    duration_ms: float = Field(ge=0.0)
    nodes: list[WorkflowTraceNode]
    edges: list[WorkflowTraceEdge]
    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    human_review_required: bool = False
    evidence_sources: list[str] = Field(default_factory=list)
    escalation_indicators: list[str] = Field(default_factory=list)


class MetricsSink(Protocol):
    async def record_agent_execution(self, trace: AgentExecutionTrace) -> None:
        """Record one agent execution metric event."""

    async def record_workflow_trace(self, trace: WorkflowTraceGraph) -> None:
        """Record one workflow-level trace metric event."""


class NoopMetricsSink:
    async def record_agent_execution(self, trace: AgentExecutionTrace) -> None:
        return None

    async def record_workflow_trace(self, trace: WorkflowTraceGraph) -> None:
        return None


class AgentExecutionLogger:
    def __init__(self, metrics_sink: MetricsSink | None = None) -> None:
        self._metrics_sink = metrics_sink or NoopMetricsSink()

    async def record_success(
        self,
        *,
        agent_input: AgentInput,
        agent_name: str,
        output: AgentOutput,
        started_at: datetime,
        latency_ms: float,
        sequence_index: int = 0,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> AgentExecutionTrace:
        trace = AgentExecutionTrace(
            workflow_id=agent_input.trace.workflow_id,
            trace_id=agent_input.trace.trace_id,
            agent_run_id=agent_input.trace.agent_run_id,
            parent_agent_run_id=agent_input.trace.parent_agent_run_id,
            case_id=agent_input.case_id,
            agent_name=agent_name,
            agent_role=agent_input.role,
            sequence_index=sequence_index,
            status=output.status.value,
            started_at=started_at,
            completed_at=output.completed_at,
            latency=latency_breakdown(agent_input.role, latency_ms, output),
            confidence_score=output.confidence.score,
            confidence_band=output.confidence.band.value,
            evidence_sources=evidence_sources(output),
            citation_ids=output.citations,
            escalation_indicators=escalation_indicators(output),
            risk_events=risk_events(output),
            token_usage=token_usage(output),
            metadata=metadata or {},
        )
        logger.info("agent_execution_trace", **redacted_agent_trace(trace))
        await self._metrics_sink.record_agent_execution(trace)
        return trace

    async def record_failure(
        self,
        *,
        agent_input: AgentInput,
        agent_name: str,
        started_at: datetime,
        latency_ms: float,
        exc: Exception,
        sequence_index: int = 0,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> AgentExecutionTrace:
        completed_at = datetime.now(UTC)
        trace = AgentExecutionTrace(
            workflow_id=agent_input.trace.workflow_id,
            trace_id=agent_input.trace.trace_id,
            agent_run_id=agent_input.trace.agent_run_id,
            parent_agent_run_id=agent_input.trace.parent_agent_run_id,
            case_id=agent_input.case_id,
            agent_name=agent_name,
            agent_role=agent_input.role,
            sequence_index=sequence_index,
            status="failed",
            started_at=started_at,
            completed_at=completed_at,
            latency=LatencyBreakdown(total_ms=latency_ms),
            error_type=type(exc).__name__,
            error_message=str(exc),
            metadata=metadata or {},
        )
        logger.exception("agent_execution_failed", **redacted_agent_trace(trace))
        await self._metrics_sink.record_agent_execution(trace)
        return trace


class AgentObservabilityMiddleware:
    def __init__(
        self,
        agent: ClinicalAgent,
        *,
        execution_logger: AgentExecutionLogger | None = None,
        sequence_index: int = 0,
    ) -> None:
        self.name = agent.name
        self.role = agent.role
        self._agent = agent
        self._execution_logger = execution_logger or AgentExecutionLogger()
        self._sequence_index = sequence_index

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        started_at = datetime.now(UTC)
        start = perf_counter()
        bind_execution_context(
            workflow_id=agent_input.trace.workflow_id,
            workflow_trace_id=agent_input.trace.trace_id,
            agent_run_id=agent_input.trace.agent_run_id,
            agent_role=agent_input.role.value,
            case_id=agent_input.case_id,
        )
        try:
            output = await self._agent.run(agent_input)
        except Exception as exc:
            await self._execution_logger.record_failure(
                agent_input=agent_input,
                agent_name=self.name,
                started_at=started_at,
                latency_ms=elapsed_ms(start),
                exc=exc,
                sequence_index=self._sequence_index,
            )
            raise
        await self._execution_logger.record_success(
            agent_input=agent_input,
            agent_name=self.name,
            output=output,
            started_at=started_at,
            latency_ms=elapsed_ms(start),
            sequence_index=self._sequence_index,
        )
        return output


def latency_breakdown(
    role: AgentRole,
    total_ms: float,
    output: AgentOutput,
) -> LatencyBreakdown:
    retrieval_ms = None
    reranking_ms = None
    risk_scoring_ms = None
    if role == AgentRole.EVIDENCE_RETRIEVAL:
        metadata = output.structured_payload.get("evidence_package", {}).get(
            "retrieval_metadata",
            {},
        )
        retrieval_ms = optional_float(metadata.get("retrieval_latency_ms"))
        reranking_ms = optional_float(metadata.get("reranking_latency_ms"))
    if role == AgentRole.RISK_ANALYSIS:
        risk_scoring_ms = total_ms
    return LatencyBreakdown(
        total_ms=total_ms,
        retrieval_ms=retrieval_ms,
        reranking_ms=reranking_ms,
        risk_scoring_ms=risk_scoring_ms,
    )


def workflow_trace_from_output(workflow_output: Any) -> WorkflowTraceGraph:
    nodes = [
        WorkflowTraceNode(
            node_id=result.node_id,
            agent_role=result.role,
            agent_run_id=result.agent_run_id,
            status=result.status.value,
            latency_ms=result.latency_ms,
            confidence_score=(
                result.output.confidence.score if result.output is not None else None
            ),
        )
        for result in workflow_output.node_results
    ]
    edges = [
        WorkflowTraceEdge(
            source_node_id=edge.source_node_id,
            target_node_id=edge.target_node_id,
            condition=edge.condition,
        )
        for edge in workflow_output.graph.edges
    ]
    return WorkflowTraceGraph(
        workflow_id=workflow_output.workflow_id,
        trace_id=workflow_output.trace_id,
        case_id=workflow_output.case_id,
        graph_id=workflow_output.graph.graph_id,
        status=workflow_output.status.value,
        duration_ms=workflow_output.latency_ms,
        nodes=nodes,
        edges=edges,
        confidence_score=workflow_output.confidence.score,
        human_review_required=workflow_output.human_review_required,
        evidence_sources=workflow_evidence_sources(workflow_output),
        escalation_indicators=workflow_escalation_indicators(workflow_output),
    )


async def record_workflow_observability(
    workflow_output: Any,
    metrics_sink: MetricsSink | None = None,
) -> WorkflowTraceGraph:
    sink = metrics_sink or NoopMetricsSink()
    trace = workflow_trace_from_output(workflow_output)
    logger.info("workflow_trace_graph", **trace.model_dump(mode="json"))
    await sink.record_workflow_trace(trace)
    return trace


def langfuse_trace_payload(trace: WorkflowTraceGraph) -> dict[str, Any]:
    return {
        "id": trace.trace_id,
        "name": "clinical_ai_agent_workflow",
        "userId": trace.case_id,
        "metadata": {
            "workflow_id": trace.workflow_id,
            "graph_id": trace.graph_id,
            "status": trace.status,
            "duration_ms": trace.duration_ms,
            "confidence_score": trace.confidence_score,
            "human_review_required": trace.human_review_required,
            "evidence_sources": trace.evidence_sources,
            "escalation_indicators": trace.escalation_indicators,
        },
        "spans": [
            {
                "id": node.agent_run_id,
                "name": node.node_id,
                "metadata": {
                    "agent_role": node.agent_role.value,
                    "status": node.status,
                    "latency_ms": node.latency_ms,
                    "confidence_score": node.confidence_score,
                },
            }
            for node in trace.nodes
        ],
    }


def evidence_sources(output: AgentOutput) -> list[str]:
    evidence_package = output.structured_payload.get("evidence_package", {})
    evidence = evidence_package.get("evidence", [])
    return sorted(
        {
            str(item.get("source_type"))
            for item in evidence
            if isinstance(item, dict) and item.get("source_type")
        }
    )


def escalation_indicators(output: AgentOutput) -> list[str]:
    risk = output.structured_payload.get("risk_analysis", {})
    indicators = risk.get("escalation_indicators", [])
    return [
        str(indicator.get("code"))
        for indicator in indicators
        if isinstance(indicator, dict) and indicator.get("code")
    ]


def risk_events(output: AgentOutput) -> list[str]:
    risk = output.structured_payload.get("risk_analysis", {})
    factors = risk.get("contributing_factors", [])
    return [
        str(factor.get("code"))
        for factor in factors
        if isinstance(factor, dict) and factor.get("code")
    ]


def token_usage(output: AgentOutput) -> TokenUsage:
    payload = output.structured_payload.get("token_usage", {})
    if isinstance(payload, dict):
        return TokenUsage.model_validate(payload)
    return TokenUsage()


def workflow_evidence_sources(workflow_output: Any) -> list[str]:
    sources: set[str] = set()
    for result in workflow_output.node_results:
        if result.output is not None:
            sources.update(evidence_sources(result.output))
    return sorted(sources)


def workflow_escalation_indicators(workflow_output: Any) -> list[str]:
    indicators: set[str] = set()
    for result in workflow_output.node_results:
        if result.output is not None:
            indicators.update(escalation_indicators(result.output))
    return sorted(indicators)


def redacted_agent_trace(trace: AgentExecutionTrace) -> dict[str, Any]:
    return {
        "workflow_id": trace.workflow_id,
        "trace_id": trace.trace_id,
        "agent_run_id": trace.agent_run_id,
        "parent_agent_run_id": trace.parent_agent_run_id,
        "case_id": trace.case_id,
        "agent_name": trace.agent_name,
        "agent_role": trace.agent_role.value,
        "sequence_index": trace.sequence_index,
        "status": trace.status,
        "latency_ms": trace.latency.total_ms,
        "retrieval_ms": trace.latency.retrieval_ms,
        "reranking_ms": trace.latency.reranking_ms,
        "risk_scoring_ms": trace.latency.risk_scoring_ms,
        "confidence_score": trace.confidence_score,
        "confidence_band": trace.confidence_band,
        "evidence_sources": trace.evidence_sources,
        "citation_count": len(trace.citation_ids),
        "escalation_indicators": trace.escalation_indicators,
        "risk_events": trace.risk_events,
        "total_tokens": trace.token_usage.total_tokens,
        "error_type": trace.error_type,
        "metadata": trace.metadata,
    }


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def elapsed_ms(start: float) -> float:
    return max(0.0, (perf_counter() - start) * 1000)
