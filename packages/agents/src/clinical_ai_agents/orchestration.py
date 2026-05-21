from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any
from uuid import uuid4

from clinical_ai_agents.contracts import (
    AgentInput,
    AgentOutput,
    AgentRole,
    AgentRunStatus,
    AgentTraceContext,
    ClinicalAgent,
    ConfidenceScore,
)
from clinical_ai_agents.evidence_retrieval import EvidenceRetrievalAgent
from clinical_ai_agents.patient_context import PatientContextAgent
from clinical_ai_agents.risk_analysis import RiskAnalysisAgent
from clinical_ai_platform.observability import bind_execution_context, get_logger
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(__name__)


class WorkflowStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    REQUIRES_REVIEW = "requires_review"


class WorkflowNodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WorkflowExecutionContext(WorkflowModel):
    workflow_id: str
    trace_id: str
    case_id: str
    request_id: str | None = None
    correlation_id: str | None = None
    workflow_name: str = "patient_evidence_risk_workflow"
    workflow_version: str = "v1"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class WorkflowNode(WorkflowModel):
    node_id: str
    role: AgentRole
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True
    human_checkpoint_after: bool = False


class WorkflowEdge(WorkflowModel):
    source_node_id: str
    target_node_id: str
    condition: str = "success"


class WorkflowGraph(WorkflowModel):
    graph_id: str
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge] = Field(default_factory=list)


class WorkflowNodeResult(WorkflowModel):
    node_id: str
    role: AgentRole
    status: WorkflowNodeStatus
    agent_run_id: str
    started_at: datetime
    completed_at: datetime
    latency_ms: float = Field(ge=0.0)
    output: AgentOutput | None = None
    error: str | None = None


class WorkflowExecutionOutput(WorkflowModel):
    workflow_id: str
    trace_id: str
    case_id: str
    status: WorkflowStatus
    graph: WorkflowGraph
    node_results: list[WorkflowNodeResult]
    shared_state: dict[str, Any] = Field(default_factory=dict)
    confidence: ConfidenceScore
    started_at: datetime
    completed_at: datetime
    latency_ms: float = Field(ge=0.0)
    human_review_required: bool = False
    future_integration_points: list[str] = Field(default_factory=list)


class AgentWorkflowOrchestrator:
    def __init__(
        self,
        *,
        patient_context_agent: ClinicalAgent | None = None,
        evidence_retrieval_agent: ClinicalAgent | None = None,
        risk_analysis_agent: ClinicalAgent | None = None,
    ) -> None:
        self._agents: dict[AgentRole, ClinicalAgent] = {
            AgentRole.PATIENT_CONTEXT: patient_context_agent or PatientContextAgent(),
            AgentRole.EVIDENCE_RETRIEVAL: evidence_retrieval_agent or EvidenceRetrievalAgent(),
            AgentRole.RISK_ANALYSIS: risk_analysis_agent or RiskAnalysisAgent(),
        }

    async def run_patient_evidence_risk_workflow(
        self,
        *,
        case_id: str,
        payload: dict[str, Any],
        request_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> WorkflowExecutionOutput:
        context = WorkflowExecutionContext(
            workflow_id=f"workflow-{uuid4()}",
            trace_id=f"trace-{uuid4()}",
            case_id=case_id,
            request_id=request_id,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )
        graph = patient_evidence_risk_graph()
        bind_execution_context(
            workflow_id=context.workflow_id,
            workflow_trace_id=context.trace_id,
            case_id=case_id,
        )
        logger.info(
            "workflow_started",
            workflow_id=context.workflow_id,
            trace_id=context.trace_id,
            case_id=case_id,
            workflow_name=context.workflow_name,
            workflow_version=context.workflow_version,
        )
        started = perf_counter()
        shared_state: dict[str, Any] = {"input": payload}
        node_results: list[WorkflowNodeResult] = []

        for node in graph.nodes:
            if not dependencies_completed(node, node_results):
                node_results.append(skipped_node_result(node))
                if node.required:
                    break
                continue

            result = await self._run_node(
                node=node,
                context=context,
                shared_state=shared_state,
                parent_agent_run_id=last_agent_run_id(node_results),
            )
            node_results.append(result)
            if result.output is not None:
                update_shared_state(node.node_id, result.output, shared_state)
            if result.status == WorkflowNodeStatus.FAILED and node.required:
                break

        completed_at = datetime.now(UTC)
        status = workflow_status(node_results)
        confidence = aggregate_confidence(node_results)
        human_review_required = any(
            result.output is not None
            and (
                result.output.status == AgentRunStatus.REQUIRES_REVIEW
                or bool(result.output.safety_hooks.get("requires_human_review"))
            )
            for result in node_results
        )
        output = WorkflowExecutionOutput(
            workflow_id=context.workflow_id,
            trace_id=context.trace_id,
            case_id=case_id,
            status=status,
            graph=graph,
            node_results=node_results,
            shared_state=summarize_shared_state(shared_state),
            confidence=confidence,
            started_at=context.started_at,
            completed_at=completed_at,
            latency_ms=max(0.0, (perf_counter() - started) * 1000),
            human_review_required=human_review_required,
            future_integration_points=[
                "safety_critic_agent",
                "explainability_agent",
                "audit_agent",
                "human_approval_checkpoint",
                "branching_workflow_router",
            ],
        )
        logger.info(
            "workflow_completed",
            workflow_id=context.workflow_id,
            trace_id=context.trace_id,
            case_id=case_id,
            status=output.status.value,
            confidence_score=output.confidence.score,
            human_review_required=output.human_review_required,
            node_count=len(node_results),
            latency_ms=round(output.latency_ms, 2),
        )
        return output

    async def _run_node(
        self,
        *,
        node: WorkflowNode,
        context: WorkflowExecutionContext,
        shared_state: dict[str, Any],
        parent_agent_run_id: str | None,
    ) -> WorkflowNodeResult:
        agent = self._agents[node.role]
        agent_run_id = f"agent-run-{uuid4()}"
        started_at = datetime.now(UTC)
        started = perf_counter()
        logger.info(
            "workflow_node_started",
            workflow_id=context.workflow_id,
            trace_id=context.trace_id,
            case_id=context.case_id,
            node_id=node.node_id,
            agent_role=node.role.value,
            agent_run_id=agent_run_id,
        )
        try:
            agent_input = AgentInput(
                case_id=context.case_id,
                role=node.role,
                trace=AgentTraceContext(
                    workflow_id=context.workflow_id,
                    trace_id=context.trace_id,
                    agent_run_id=agent_run_id,
                    request_id=context.request_id,
                    correlation_id=context.correlation_id,
                    parent_agent_run_id=parent_agent_run_id,
                ),
                payload=node_payload(node, shared_state),
                metadata={
                    "workflow_name": context.workflow_name,
                    "workflow_version": context.workflow_version,
                    "node_id": node.node_id,
                },
            )
            output = await agent.run(agent_input)
            result = WorkflowNodeResult(
                node_id=node.node_id,
                role=node.role,
                status=WorkflowNodeStatus.COMPLETED,
                agent_run_id=agent_run_id,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                latency_ms=max(0.0, (perf_counter() - started) * 1000),
                output=output,
            )
        except Exception as exc:
            result = WorkflowNodeResult(
                node_id=node.node_id,
                role=node.role,
                status=WorkflowNodeStatus.FAILED,
                agent_run_id=agent_run_id,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                latency_ms=max(0.0, (perf_counter() - started) * 1000),
                error=f"{type(exc).__name__}: {exc}",
            )
            logger.exception(
                "workflow_node_failed",
                workflow_id=context.workflow_id,
                trace_id=context.trace_id,
                case_id=context.case_id,
                node_id=node.node_id,
                agent_role=node.role.value,
                agent_run_id=agent_run_id,
                error_type=type(exc).__name__,
            )
            return result

        logger.info(
            "workflow_node_completed",
            workflow_id=context.workflow_id,
            trace_id=context.trace_id,
            case_id=context.case_id,
            node_id=node.node_id,
            agent_role=node.role.value,
            agent_run_id=agent_run_id,
            status=result.status.value,
            latency_ms=round(result.latency_ms, 2),
        )
        return result


def patient_evidence_risk_graph() -> WorkflowGraph:
    return WorkflowGraph(
        graph_id="patient_context_to_evidence_to_risk_v1",
        nodes=[
            WorkflowNode(node_id="patient_context", role=AgentRole.PATIENT_CONTEXT),
            WorkflowNode(
                node_id="evidence_retrieval",
                role=AgentRole.EVIDENCE_RETRIEVAL,
                depends_on=["patient_context"],
            ),
            WorkflowNode(
                node_id="risk_analysis",
                role=AgentRole.RISK_ANALYSIS,
                depends_on=["evidence_retrieval"],
                human_checkpoint_after=True,
            ),
        ],
        edges=[
            WorkflowEdge(source_node_id="patient_context", target_node_id="evidence_retrieval"),
            WorkflowEdge(source_node_id="evidence_retrieval", target_node_id="risk_analysis"),
        ],
    )


def node_payload(node: WorkflowNode, shared_state: dict[str, Any]) -> dict[str, Any]:
    root_input = shared_state["input"]
    if node.role == AgentRole.PATIENT_CONTEXT:
        return {
            "patient_context": root_input.get("patient_context", root_input),
        }
    if node.role == AgentRole.EVIDENCE_RETRIEVAL:
        patient_output = shared_state.get("patient_context", {})
        patient_representation = patient_output.get("patient_representation", {})
        return {
            "query": root_input.get("query") or root_input.get("evidence_query"),
            "filters": root_input.get("filters", {}),
            "limit": root_input.get("limit", root_input.get("top_k", 10)),
            "candidate_limit": root_input.get("candidate_limit", 50),
            "mode": root_input.get("mode", "hybrid"),
            "fusion_strategy": root_input.get("fusion_strategy", "weighted_sum"),
            "rerank": root_input.get("rerank", True),
            "evidence_corpus": root_input.get("evidence_corpus", []),
            "retrieval_profile": patient_representation.get("retrieval_profile", {}),
            "patient_context": patient_representation,
        }
    if node.role == AgentRole.RISK_ANALYSIS:
        patient_output = shared_state.get("patient_context", {})
        evidence_output = shared_state.get("evidence_retrieval", {})
        return {
            "patient_context": root_input.get("patient_context", root_input),
            "patient_representation": patient_output.get("patient_representation", {}),
            "evidence_package": evidence_output.get("evidence_package", {}),
        }
    return root_input


def update_shared_state(
    node_id: str,
    output: AgentOutput,
    shared_state: dict[str, Any],
) -> None:
    if node_id == "patient_context":
        shared_state[node_id] = output.structured_payload
    elif node_id == "evidence_retrieval":
        shared_state[node_id] = output.structured_payload
    elif node_id == "risk_analysis":
        shared_state[node_id] = output.structured_payload
    else:
        shared_state[node_id] = output.model_dump(mode="json")


def dependencies_completed(
    node: WorkflowNode,
    results: list[WorkflowNodeResult],
) -> bool:
    completed = {
        result.node_id
        for result in results
        if result.status == WorkflowNodeStatus.COMPLETED
    }
    return all(dependency in completed for dependency in node.depends_on)


def skipped_node_result(node: WorkflowNode) -> WorkflowNodeResult:
    now = datetime.now(UTC)
    return WorkflowNodeResult(
        node_id=node.node_id,
        role=node.role,
        status=WorkflowNodeStatus.SKIPPED,
        agent_run_id=f"agent-run-{uuid4()}",
        started_at=now,
        completed_at=now,
        latency_ms=0.0,
        error="Dependency did not complete.",
    )


def workflow_status(results: list[WorkflowNodeResult]) -> WorkflowStatus:
    if any(result.status == WorkflowNodeStatus.FAILED for result in results):
        return WorkflowStatus.FAILED
    if any(result.status == WorkflowNodeStatus.SKIPPED for result in results):
        return WorkflowStatus.PARTIAL
    if any(
        result.output is not None and result.output.status == AgentRunStatus.REQUIRES_REVIEW
        for result in results
    ):
        return WorkflowStatus.REQUIRES_REVIEW
    return WorkflowStatus.COMPLETED


def aggregate_confidence(results: list[WorkflowNodeResult]) -> ConfidenceScore:
    confidence_scores = [
        result.output.confidence.score
        for result in results
        if result.output is not None
    ]
    if not confidence_scores:
        return ConfidenceScore(score=0.0)
    score = sum(confidence_scores) / len(confidence_scores)
    return ConfidenceScore(
        score=score,
        band=confidence_band(score),
        components={
            "agent_count": float(len(confidence_scores)),
            "minimum_agent_confidence": min(confidence_scores),
            "maximum_agent_confidence": max(confidence_scores),
        },
        rationale="Aggregate confidence across completed agent workflow steps.",
    )


def summarize_shared_state(shared_state: dict[str, Any]) -> dict[str, Any]:
    patient_state = shared_state.get("patient_context", {})
    evidence_state = shared_state.get("evidence_retrieval", {})
    risk_state = shared_state.get("risk_analysis", {})
    return {
        "has_patient_context": bool(patient_state),
        "has_evidence_package": bool(evidence_state),
        "has_risk_analysis": bool(risk_state),
        "patient_context_id": patient_state.get("patient_representation", {}).get("context_id"),
        "retrieved_evidence_count": len(
            evidence_state.get("evidence_package", {}).get("evidence", [])
        ),
        "risk_level": risk_state.get("risk_analysis", {}).get("risk_level"),
    }


def last_agent_run_id(results: list[WorkflowNodeResult]) -> str | None:
    for result in reversed(results):
        if result.status == WorkflowNodeStatus.COMPLETED:
            return result.agent_run_id
    return None


def confidence_band(score: float):
    from clinical_ai_agents.contracts import ConfidenceBand

    if score >= 0.85:
        return ConfidenceBand.HIGH
    if score >= 0.65:
        return ConfidenceBand.MODERATE
    if score > 0:
        return ConfidenceBand.LOW
    return ConfidenceBand.UNKNOWN
