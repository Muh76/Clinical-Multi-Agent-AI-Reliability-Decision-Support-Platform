from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from clinical_ai_api.core.errors import AppError
from clinical_ai_api.schemas.workflows import (
    EvidenceCitationResponse,
    EvidenceSourceInput,
    GroundedEvidenceWorkflowRequest,
    GroundedEvidenceWorkflowResponse,
    RetrievedEvidenceResponse,
    RetrievalMetadataResponse,
    SafetyCriticIntegrationPoint,
    WorkflowStatus,
    WorkflowStepStatus,
    WorkflowTrace,
    WorkflowTraceStep,
)
from clinical_ai_multimodal.patient_context import PatientContextProcessor
from clinical_ai_multimodal.patient_context.schemas import StructuredPatientContext
from clinical_ai_platform.observability import bind_execution_context, get_logger


logger = get_logger(__name__)
ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class EvidenceCandidate:
    source: EvidenceSourceInput
    retrieval_score: float
    rerank_score: float | None
    source_reliability_score: float

    @property
    def final_score(self) -> float:
        rerank_component = (
            self.rerank_score if self.rerank_score is not None else self.retrieval_score
        )
        return clamp01(
            0.50 * self.retrieval_score
            + 0.30 * rerank_component
            + 0.20 * self.source_reliability_score
        )

    @property
    def confidence_score(self) -> float:
        return clamp01(0.70 * self.final_score + 0.30 * self.source_reliability_score)


class EvidenceGroundingWorkflowService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        patient_context_processor: PatientContextProcessor | None = None,
    ) -> None:
        self._session = session
        self._patient_context_processor = patient_context_processor or PatientContextProcessor()

    async def run(
        self,
        *,
        payload: GroundedEvidenceWorkflowRequest,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GroundedEvidenceWorkflowResponse:
        _ = self._session
        workflow_id = f"workflow-{uuid4()}"
        trace_id = f"trace-{uuid4()}"
        started_at = now_utc()
        steps: list[WorkflowTraceStep] = []
        bind_execution_context(
            workflow_id=workflow_id,
            workflow_trace_id=trace_id,
            case_id=payload.case_id,
        )
        logger.info(
            "evidence_workflow_started",
            workflow_id=workflow_id,
            trace_id=trace_id,
            case_id=payload.case_id,
        )

        try:
            await self._run_step(
                steps,
                "ingest_patient_case",
                lambda: {
                    "patient_id": payload.patient_context.patient_id,
                    "case_id": payload.case_id,
                    "source": payload.metadata.get("source", "request_payload"),
                },
            )
            structured_context = await self._run_step(
                steps,
                "process_patient_context",
                lambda: self._patient_context_processor.process(payload.patient_context),
                metadata_builder=context_processing_metadata,
            )
            retrieval_query = await self._run_step(
                steps,
                "prepare_retrieval_query",
                lambda: build_retrieval_query(payload, structured_context),
                metadata_builder=lambda query: {"query_length": len(query)},
            )
            candidates = await self._run_step(
                steps,
                "retrieve_evidence",
                lambda: retrieve_candidates(
                    query=retrieval_query,
                    evidence_corpus=payload.evidence_corpus,
                    limit=max(payload.top_k * 4, payload.top_k),
                ),
                metadata_builder=lambda results: {"candidate_count": len(results)},
            )
            ranked_candidates = await self._run_step(
                steps,
                "rerank_evidence",
                lambda: rerank_candidates(
                    query=retrieval_query,
                    candidates=candidates,
                    enabled=payload.enable_reranking,
                    limit=payload.top_k,
                ),
                metadata_builder=lambda results: {
                    "reranked": payload.enable_reranking,
                    "retrieved_count": len(results),
                },
            )
            response = await self._run_step(
                steps,
                "package_grounded_evidence_response",
                lambda: package_response(
                    payload=payload,
                    workflow_id=workflow_id,
                    trace_id=trace_id,
                    request_id=request_id,
                    correlation_id=correlation_id,
                    started_at=started_at,
                    steps=steps,
                    structured_context=structured_context,
                    retrieval_query=retrieval_query,
                    candidates=ranked_candidates,
                ),
                metadata_builder=lambda result: {
                    "confidence_score": result.confidence_score,
                    "citation_count": len(result.citations),
                    "evidence_count": len(result.evidence),
                },
            )
        except Exception as exc:
            logger.exception(
                "evidence_workflow_failed",
                workflow_id=workflow_id,
                trace_id=trace_id,
                case_id=payload.case_id,
                error_type=type(exc).__name__,
            )
            raise AppError(
                code="evidence_workflow_failed",
                message="Evidence workflow failed before a grounded response could be produced.",
                status_code=500,
            ) from exc

        logger.info(
            "evidence_workflow_completed",
            workflow_id=workflow_id,
            trace_id=trace_id,
            case_id=payload.case_id,
            evidence_count=len(response.evidence),
            citation_count=len(response.citations),
            confidence_score=response.confidence_score,
        )
        return response

    async def _run_step(
        self,
        steps: list[WorkflowTraceStep],
        name: str,
        operation: Callable[[], ResultT],
        *,
        metadata_builder: Callable[[ResultT], dict[str, Any]] | None = None,
    ) -> ResultT:
        started_at = now_utc()
        start = perf_counter()
        try:
            result = operation()
        except Exception as exc:
            completed_at = now_utc()
            latency_ms = elapsed_ms(start)
            steps.append(
                WorkflowTraceStep(
                    name=name,
                    status=WorkflowStepStatus.FAILED,
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=latency_ms,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            logger.exception(
                "evidence_workflow_step_failed",
                workflow_step=name,
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
            )
            raise

        completed_at = now_utc()
        latency_ms = elapsed_ms(start)
        metadata = metadata_builder(result) if metadata_builder is not None else {}
        steps.append(
            WorkflowTraceStep(
                name=name,
                status=WorkflowStepStatus.COMPLETED,
                started_at=started_at,
                completed_at=completed_at,
                latency_ms=latency_ms,
                metadata=metadata,
            )
        )
        logger.info(
            "evidence_workflow_step_completed",
            workflow_step=name,
            latency_ms=latency_ms,
            **metadata,
        )
        return result


def build_retrieval_query(
    payload: GroundedEvidenceWorkflowRequest,
    structured_context: StructuredPatientContext,
) -> str:
    if payload.evidence_query:
        return payload.evidence_query
    query_terms = structured_context.unified.retrieval_profile.get("query_terms", [])
    if isinstance(query_terms, list) and query_terms:
        return " ".join(str(term) for term in query_terms)
    note_types = structured_context.unified.retrieval_profile.get("note_types", [])
    if isinstance(note_types, list) and note_types:
        return " ".join(str(note_type) for note_type in note_types)
    return f"clinical evidence for patient context {structured_context.context_id}"


def retrieve_candidates(
    *,
    query: str,
    evidence_corpus: list[EvidenceSourceInput],
    limit: int,
) -> list[EvidenceCandidate]:
    query_tokens = tokenize(query)
    candidates = [
        EvidenceCandidate(
            source=source,
            retrieval_score=lexical_relevance(query_tokens, source),
            rerank_score=None,
            source_reliability_score=source_reliability_score(source),
        )
        for source in evidence_corpus
    ]
    candidates = [
        candidate
        for candidate in candidates
        if candidate.retrieval_score > 0.0 or not query_tokens
    ]
    return sorted(candidates, key=lambda candidate: candidate.retrieval_score, reverse=True)[:limit]


def rerank_candidates(
    *,
    query: str,
    candidates: list[EvidenceCandidate],
    enabled: bool,
    limit: int,
) -> list[EvidenceCandidate]:
    if not enabled:
        return candidates[:limit]

    query_tokens = tokenize(query)
    reranked = [
        EvidenceCandidate(
            source=candidate.source,
            retrieval_score=candidate.retrieval_score,
            rerank_score=rerank_score(query_tokens, candidate.source),
            source_reliability_score=candidate.source_reliability_score,
        )
        for candidate in candidates
    ]
    return sorted(reranked, key=lambda candidate: candidate.final_score, reverse=True)[:limit]


def package_response(
    *,
    payload: GroundedEvidenceWorkflowRequest,
    workflow_id: str,
    trace_id: str,
    request_id: str | None,
    correlation_id: str | None,
    started_at: datetime,
    steps: list[WorkflowTraceStep],
    structured_context: StructuredPatientContext,
    retrieval_query: str,
    candidates: list[EvidenceCandidate],
) -> GroundedEvidenceWorkflowResponse:
    completed_at = now_utc()
    evidence = [
        evidence_response(rank=rank, candidate=candidate)
        for rank, candidate in enumerate(candidates, start=1)
    ]
    citations = [item.citation for item in evidence]
    confidence_score = (
        sum(item.confidence_score for item in evidence) / len(evidence)
        if evidence
        else 0.0
    )
    safety_profile = structured_context.unified.safety_profile
    safety_review_recommended = bool(safety_profile.get("requires_human_review", False))
    trace = WorkflowTrace(
        workflow_id=workflow_id,
        trace_id=trace_id,
        request_id=request_id,
        correlation_id=correlation_id,
        started_at=started_at,
        completed_at=completed_at,
        latency_ms=max(
            0.0,
            (completed_at - started_at).total_seconds() * 1000,
        ),
        steps=steps.copy(),
    )
    return GroundedEvidenceWorkflowResponse(
        workflow_id=workflow_id,
        status=WorkflowStatus.COMPLETED,
        case_id=payload.case_id,
        patient_id=structured_context.patient_id,
        context_id=structured_context.context_id,
        evidence=evidence,
        citations=citations,
        confidence_score=clamp01(confidence_score),
        retrieval_metadata=RetrievalMetadataResponse(
            query=retrieval_query,
            retrieval_mode="local_keyword_rerank_v1",
            candidate_count=len(payload.evidence_corpus),
            retrieved_count=len(evidence),
            reranked=payload.enable_reranking,
            top_k=payload.top_k,
            context_id=structured_context.context_id,
            patient_id=structured_context.patient_id,
            validation_finding_count=len(structured_context.validation_findings),
            safety_review_recommended=safety_review_recommended,
        ),
        trace=trace,
        safety_critic_integration_points=safety_critic_integration_points(),
    )


def evidence_response(*, rank: int, candidate: EvidenceCandidate) -> RetrievedEvidenceResponse:
    source = candidate.source
    citation = citation_response(source)
    return RetrievedEvidenceResponse(
        rank=rank,
        source_id=source.source_id,
        source_type=source.source_type,
        text=source.text,
        citation=citation,
        score=candidate.final_score,
        confidence_score=candidate.confidence_score,
        retrieval_score=candidate.retrieval_score,
        rerank_score=candidate.rerank_score,
        source_reliability_score=candidate.source_reliability_score,
        metadata=source.metadata,
    )


def citation_response(source: EvidenceSourceInput) -> EvidenceCitationResponse:
    citation_id = source.citation_id or f"{source.source_type}:{source.source_id}"
    title = source.title or source.source_id
    year = f" ({source.publication_year})" if source.publication_year else ""
    attribution = f"{title}{year}. {source.source_type.replace('_', ' ')}: {source.source_id}."
    return EvidenceCitationResponse(
        citation_id=citation_id,
        source_id=source.source_id,
        source_type=source.source_type,
        title=source.title,
        url=source.url,
        publication_year=source.publication_year,
        quote=source.text[:500],
        attribution_text=attribution,
    )


def safety_critic_integration_points() -> list[SafetyCriticIntegrationPoint]:
    return [
        SafetyCriticIntegrationPoint(
            name="citation_allow_list",
            status="available",
            required_inputs=["citations", "retrieved_evidence"],
        ),
        SafetyCriticIntegrationPoint(
            name="grounding_consistency_check",
            status="planned",
            required_inputs=["candidate_answer", "retrieved_evidence", "citations"],
        ),
        SafetyCriticIntegrationPoint(
            name="recommendation_strength_review",
            status="planned",
            required_inputs=["confidence_scores", "source_reliability_scores", "patient_context"],
        ),
    ]


def context_processing_metadata(context: StructuredPatientContext) -> dict[str, Any]:
    return {
        "patient_id": context.patient_id,
        "context_id": context.context_id,
        "timeline_event_count": len(context.unified.timeline),
        "validation_finding_count": len(context.validation_findings),
    }


def lexical_relevance(query_tokens: set[str], source: EvidenceSourceInput) -> float:
    if not query_tokens:
        return 0.0
    source_tokens = tokenize(f"{source.title or ''} {source.text}")
    if not source_tokens:
        return 0.0
    overlap = len(query_tokens & source_tokens)
    coverage = overlap / len(query_tokens)
    density = overlap / len(source_tokens)
    exact_bonus = 0.15 if (source.title and source.title.lower() in source.text.lower()) else 0.0
    return clamp01(0.80 * coverage + 0.20 * density + exact_bonus)


def rerank_score(query_tokens: set[str], source: EvidenceSourceInput) -> float:
    base_score = lexical_relevance(query_tokens, source)
    title_tokens = tokenize(source.title or "")
    title_overlap = len(query_tokens & title_tokens) / len(query_tokens) if query_tokens else 0.0
    evidence_bonus = 0.10 if source.evidence_level else 0.0
    return clamp01(0.75 * base_score + 0.15 * title_overlap + evidence_bonus)


def source_reliability_score(source: EvidenceSourceInput) -> float:
    source_type_scores = {
        "nice_guideline": 0.95,
        "local_policy": 0.88,
        "pubmed": 0.78,
        "synthetic_protocol": 0.55,
        "mimic_patient_context": 0.50,
    }
    evidence_level_scores = {
        "guideline": 0.95,
        "systematic_review": 0.86,
        "randomized_trial": 0.82,
        "clinical_trial": 0.78,
        "observational_study": 0.70,
        "case_report": 0.55,
    }
    base = source_type_scores.get(source.source_type, 0.50)
    if source.evidence_level is None:
        return base
    return max(base, evidence_level_scores.get(source.evidence_level, base))


def tokenize(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {token for token in normalized.split() if len(token) > 1}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def now_utc() -> datetime:
    return datetime.now(UTC)


def elapsed_ms(start: float) -> float:
    return max(0.0, (perf_counter() - start) * 1000)
