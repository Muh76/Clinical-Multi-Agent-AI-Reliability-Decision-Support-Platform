from __future__ import annotations

from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from clinical_ai_agents import (
    AgentWorkflowOrchestrator,
    EndToEndClinicalReliabilityWorkflowRunner,
    EvidenceRetrievalAgent,
    NoopMetricsSink,
    PatientContextAgent,
    RiskAnalysisAgent,
    SafetyAwareClinicalWorkflowRunner,
)
from clinical_ai_api.api.dependencies import get_agent_container
from clinical_ai_api.core.agent_container import AgentContainer
from clinical_ai_api.main import create_app
from clinical_ai_multimodal.patient_context import PatientContextProcessor
from clinical_ai_retrieval.context import RetrievalContext
from clinical_ai_retrieval.retrieval_service import RetrievalService
from clinical_ai_retrieval.retrievers import LocalCorpusRetriever, RoutingRetriever
from clinical_ai_retrieval.retrievers.types import RetrieverOutput
from clinical_ai_retrieval.schemas import (
    EvidenceMetadata,
    EvidenceSourceType,
    RetrievalBackend,
    RetrievalResult,
)
from clinical_ai_retrieval.scoring import attach_reliability_scores
from clinical_ai_safety import HumanApprovalWorkflowEngine


@dataclass
class RecordingQdrantRetriever:
  """Test double that records Qdrant-path invocations without a live vector store."""

  backend: RetrievalBackend = RetrievalBackend.QDRANT
  calls: list[RetrievalContext] = field(default_factory=list)

  async def retrieve_candidates(self, context: RetrievalContext) -> RetrieverOutput:
      self.calls.append(context)
      result = RetrievalResult(
          chunk_id="qdrant:renal-guidance:0",
          document_id="nice_guideline:renal-guidance",
          score=0.91,
          text="Vancomycin dosing should consider renal function and creatinine trends.",
          metadata=EvidenceMetadata(
              source_type=EvidenceSourceType.NICE_GUIDELINE,
              source_id="renal-guidance",
              title="Renal dosing guidance",
              citation_id="nice_guideline:renal-guidance",
              evidence_level="guideline",
          ),
          dense_score=0.91,
      )
      scored = attach_reliability_scores([result])
      return RetrieverOutput(
          candidates=scored,
          backend=self.backend,
          dense_result_count=len(scored),
      )


def _workflow_payload(*, include_inline_corpus: bool) -> dict:
    payload = {
        "case_id": "case-qdrant",
        "patient_context": {
            "patient_id": "patient-1",
            "vitals": [
                {
                    "name": "heart_rate",
                    "value": {"value": 112, "unit": "beats/min"},
                    "temporal": {"observed_at": "2026-05-20T08:00:00Z"},
                }
            ],
            "labs": [
                {
                    "test_name": "creatinine",
                    "value": {"value": 1.8, "unit": "mg/dL"},
                    "temporal": {"observed_at": "2026-05-20T08:10:00Z"},
                }
            ],
            "medications": [
                {
                    "medication_name": "vancomycin",
                    "route": "IV",
                    "temporal": {"observed_at": "2026-05-20T08:15:00Z"},
                }
            ],
        },
        "evidence_query": "creatinine vancomycin renal dosing",
        "top_k": 1,
        "enable_reranking": False,
    }
    if include_inline_corpus:
        payload["evidence_corpus"] = [
            {
                "source_id": "local-renal-dosing",
                "source_type": "local_policy",
                "title": "Renal dosing policy",
                "text": (
                    "Vancomycin dosing should consider renal function "
                    "and creatinine trends."
                ),
                "citation_id": "local_policy:local-renal-dosing",
                "evidence_level": "guideline",
            }
        ]
    return payload


def _build_qdrant_agent_container(
    qdrant_retriever: RecordingQdrantRetriever,
) -> AgentContainer:
    retrieval_service = RetrievalService(
        retriever=RoutingRetriever(
            local=LocalCorpusRetriever(),
            qdrant=qdrant_retriever,
        ),
    )
    evidence_retrieval_agent = EvidenceRetrievalAgent(retrieval_service=retrieval_service)
    orchestrator = AgentWorkflowOrchestrator(
        patient_context_agent=PatientContextAgent(processor=PatientContextProcessor()),
        evidence_retrieval_agent=evidence_retrieval_agent,
        risk_analysis_agent=RiskAnalysisAgent(),
        retrieval_service=retrieval_service,
    )
    e2e_runner = EndToEndClinicalReliabilityWorkflowRunner(
        orchestrator=orchestrator,
        metrics_sink=NoopMetricsSink(),
    )
    safety_aware_runner = SafetyAwareClinicalWorkflowRunner(
        base_runner=e2e_runner,
        approval_engine=HumanApprovalWorkflowEngine(),
    )
    return AgentContainer(
        agents_enabled=True,
        retrieval_mode="qdrant",
        orchestrator=orchestrator,
        safety_aware_runner=safety_aware_runner,
        retrieval_service=retrieval_service,
    )


def test_api_workflow_hits_qdrant_retriever_when_no_inline_corpus() -> None:
    qdrant_retriever = RecordingQdrantRetriever()
    container = _build_qdrant_agent_container(qdrant_retriever)

    app = create_app()
    app.dependency_overrides[get_agent_container] = lambda: container
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows/clinical-reliability",
            json=_workflow_payload(include_inline_corpus=False),
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["status"] == "completed"
        assert len(qdrant_retriever.calls) == 1
        assert qdrant_retriever.calls[0].query.query == "creatinine vancomycin renal dosing"
        assert payload["evidence"][0]["source_id"] == "renal-guidance"
        assert payload["retrieval_metadata"]["retrieval_mode"] == "qdrant"
        assert payload["citations"][0]["citation_id"] == "nice_guideline:renal-guidance"


def test_inline_corpus_routes_to_local_even_when_qdrant_configured() -> None:
    qdrant_retriever = RecordingQdrantRetriever()
    container = _build_qdrant_agent_container(qdrant_retriever)

    app = create_app()
    app.dependency_overrides[get_agent_container] = lambda: container
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/workflows/clinical-reliability",
            json=_workflow_payload(include_inline_corpus=True),
        )

        assert response.status_code == 200
        payload = response.json()["data"]
        assert len(qdrant_retriever.calls) == 0
        assert payload["evidence"][0]["source_id"] == "local-renal-dosing"
        assert payload["retrieval_metadata"]["retrieval_mode"] == "local_corpus"


def test_evidence_retrieval_agent_in_container_uses_injected_retrieval_service() -> None:
    container = _build_qdrant_agent_container(RecordingQdrantRetriever())

    from clinical_ai_agents.contracts import AgentRole

    agent = container.orchestrator._agents[AgentRole.EVIDENCE_RETRIEVAL]  # noqa: SLF001
    assert isinstance(agent, EvidenceRetrievalAgent)
    assert agent._retrieval_service is container.retrieval_service  # noqa: SLF001
