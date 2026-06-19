from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog
from clinical_ai_agents import (
    AgentWorkflowOrchestrator,
    EndToEndClinicalReliabilityWorkflowRunner,
    EvidenceRetrievalAgent,
    NoopMetricsSink,
    PatientContextAgent,
    RiskAnalysisAgent,
    SafetyAwareClinicalWorkflowRunner,
)
from clinical_ai_multimodal.patient_context import PatientContextProcessor
from clinical_ai_platform.core.config import Settings
from clinical_ai_platform.core.settings import VectorProvider
from clinical_ai_retrieval.factory import build_retrieval_service
from clinical_ai_retrieval.service import VectorRetrievalService
from clinical_ai_safety import HumanApprovalWorkflowEngine

logger = structlog.get_logger(__name__)

RetrievalMode = Literal["local", "qdrant"]


ORCHESTRATED_AGENT_EXECUTION_ORDER = (
    "patient_context",
    "evidence_retrieval",
    "risk_analysis",
)

SAFETY_AWARE_WORKFLOW_EXECUTION_ORDER = (
    *ORCHESTRATED_AGENT_EXECUTION_ORDER,
    "hallucination_detection",
    "evidence_verification",
    "uncertainty_scoring",
    "escalation_logic",
    "human_approval_evaluation",
)


@dataclass(frozen=True, slots=True)
class AgentContainer:
    agents_enabled: bool
    retrieval_mode: RetrievalMode
    orchestrator: AgentWorkflowOrchestrator
    safety_aware_runner: SafetyAwareClinicalWorkflowRunner
    vector_retrieval_service: VectorRetrievalService | None
    _qdrant_close: object | None = None

    async def close(self) -> None:
        if self._qdrant_close is not None and hasattr(self._qdrant_close, "close"):
            await self._qdrant_close.close()


def build_agent_container(settings: Settings) -> AgentContainer:
    if not settings.agents.enabled:
        logger.warning("agents_disabled", message="Agent workflow runners are disabled by configuration.")
        return _build_disabled_container()

    vector_retrieval_service: VectorRetrievalService | None = None
    qdrant_store = None
    retrieval_mode: RetrievalMode = "local"

    vector_settings = settings.vector_database
    if vector_settings.provider == VectorProvider.QDRANT:
        if vector_settings.url is None:
            raise ValueError("VECTOR_DATABASE_URL is required when VECTOR_PROVIDER=qdrant")
        vector_retrieval_service = build_retrieval_service(
            url=vector_settings.url,
            collection_prefix=vector_settings.collection_prefix,
            model_name=vector_settings.embedding_model,
            api_key=vector_settings.api_key,
            enable_reranker=True,
        )
        qdrant_store = vector_retrieval_service.vector_store
        retrieval_mode = "qdrant"

    processor = PatientContextProcessor()
    patient_context_agent = PatientContextAgent(processor=processor)
    evidence_retrieval_agent = EvidenceRetrievalAgent(retriever=vector_retrieval_service)
    risk_analysis_agent = RiskAnalysisAgent()
    orchestrator = AgentWorkflowOrchestrator(
        patient_context_agent=patient_context_agent,
        evidence_retrieval_agent=evidence_retrieval_agent,
        risk_analysis_agent=risk_analysis_agent,
    )
    e2e_runner = EndToEndClinicalReliabilityWorkflowRunner(
        orchestrator=orchestrator,
        metrics_sink=NoopMetricsSink(),
    )
    safety_aware_runner = SafetyAwareClinicalWorkflowRunner(
        base_runner=e2e_runner,
        approval_engine=HumanApprovalWorkflowEngine(),
    )

    logger.info(
        "agent_container_built",
        retrieval_mode=retrieval_mode,
        agents_enabled=True,
    )
    return AgentContainer(
        agents_enabled=True,
        retrieval_mode=retrieval_mode,
        orchestrator=orchestrator,
        safety_aware_runner=safety_aware_runner,
        vector_retrieval_service=vector_retrieval_service,
        _qdrant_close=qdrant_store,
    )


async def warmup_agent_container(container: AgentContainer) -> None:
    if not container.agents_enabled:
        return
    if container.vector_retrieval_service is not None:
        await container.vector_retrieval_service.vector_store.ensure_collection()
        logger.info("agent_container_qdrant_warmup_complete")


async def close_agent_container(container: AgentContainer | None) -> None:
    if container is None:
        return
    await container.close()


def _build_disabled_container() -> AgentContainer:
    orchestrator = AgentWorkflowOrchestrator()
    runner = SafetyAwareClinicalWorkflowRunner(
        base_runner=EndToEndClinicalReliabilityWorkflowRunner(orchestrator=orchestrator),
    )
    return AgentContainer(
        agents_enabled=False,
        retrieval_mode="local",
        orchestrator=orchestrator,
        safety_aware_runner=runner,
        vector_retrieval_service=None,
    )
