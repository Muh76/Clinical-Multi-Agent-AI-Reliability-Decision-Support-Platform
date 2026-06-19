from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from clinical_ai_agents.contracts import (
    AgentFinding,
    AgentInput,
    AgentOutput,
    AgentRole,
    AgentRunStatus,
    ConfidenceBand,
    ConfidenceScore,
)
from clinical_ai_platform.observability import get_logger
from clinical_ai_retrieval.context import EvidenceCorpusItem, build_retrieval_context
from clinical_ai_retrieval.observability import langfuse_retrieval_span
from clinical_ai_retrieval.packaging import relevance_reasoning_for_item
from clinical_ai_retrieval.retrieval_service import RetrievalService
from clinical_ai_retrieval.schemas import (
    EvidencePackage,
    EvidenceSourceType,
    FusionStrategy,
    MetadataFilter,
    RetrievalMode,
    RetrievalQuery,
)
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(__name__)


class RetrievedEvidenceAgentItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rank: int = Field(ge=1)
    chunk_id: str
    document_id: str
    source_id: str
    source_type: str
    title: str | None = None
    text: str
    citation_id: str
    score: float = Field(ge=0.0, le=1.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    source_reliability_score: float = Field(ge=0.0, le=1.0)
    scoring_components: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    relevance_reasoning: str


class EvidenceCitationAgentItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    citation_id: str
    source_type: str
    source_id: str
    title: str | None = None
    url: str | None = None
    publication_year: int | None = None
    section_path: list[str] = Field(default_factory=list)
    quote: str | None = None
    attribution_text: str


class EvidenceRetrievalAgentPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str
    evidence: list[RetrievedEvidenceAgentItem]
    citations: list[EvidenceCitationAgentItem]
    retrieval_confidence: float = Field(ge=0.0, le=1.0)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)
    relevance_reasoning: list[str] = Field(default_factory=list)


class EvidenceRetrievalAgent:
    """Orchestrates evidence retrieval by delegating to an injected ``RetrievalService``.

    This agent is backend-agnostic: it never performs vector, BM25, or corpus search
    internally. All retrieval semantics live in ``clinical_ai_retrieval``.
    """

    name = "evidence_retrieval_agent"
    role = AgentRole.EVIDENCE_RETRIEVAL

    def __init__(self, *, retrieval_service: RetrievalService) -> None:
        self._retrieval_service = retrieval_service

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        started_at = datetime.now(UTC)
        start = perf_counter()
        logger.info(
            "agent_run_started",
            agent_name=self.name,
            agent_role=self.role.value,
            agent_run_id=agent_input.trace.agent_run_id,
            workflow_id=agent_input.trace.workflow_id,
            trace_id=agent_input.trace.trace_id,
            case_id=agent_input.case_id,
        )
        try:
            retrieval_query = build_retrieval_query(agent_input.payload)
            context = build_retrieval_context(retrieval_query, agent_input.payload).model_copy(
                update={
                    "workflow_id": agent_input.trace.workflow_id,
                    "workflow_trace_id": agent_input.trace.trace_id,
                    "agent_run_id": agent_input.trace.agent_run_id,
                    "case_id": agent_input.case_id,
                    "request_id": agent_input.trace.request_id,
                    "correlation_id": agent_input.trace.correlation_id,
                }
            )
            evidence_package = await self._retrieval_service.retrieve_evidence(context)
            retrieval_trace = getattr(self._retrieval_service, "last_trace", None)
            agent_package = build_agent_package(
                evidence_package,
                retrieval_query,
                retrieval_trace=retrieval_trace,
            )
            confidence = build_confidence(evidence_package, agent_package)
            findings = retrieval_findings(evidence_package)
            status = (
                AgentRunStatus.COMPLETED
                if evidence_package.evidence
                else AgentRunStatus.SKIPPED
            )
            output = AgentOutput(
                case_id=agent_input.case_id,
                role=self.role,
                status=status,
                trace=agent_input.trace,
                summary=retrieval_summary(agent_package),
                structured_payload={
                    "evidence_package": agent_package.model_dump(mode="json"),
                    "retrieval_query": retrieval_query.model_dump(mode="json"),
                },
                findings=findings,
                confidence=confidence,
                citations=[citation.citation_id for citation in evidence_package.citations],
                explainability={
                    "retrieval_mode": evidence_package.diagnostics.mode.value,
                    "retrieval_backend": evidence_package.diagnostics.backend.value,
                    "fusion_strategy": evidence_package.diagnostics.fusion_strategy.value,
                    "reranked": evidence_package.diagnostics.reranked,
                    "source_types": sorted(
                        {
                            item.metadata.source_type.value
                            for item in evidence_package.evidence
                        }
                    ),
                    "relevance_reasoning": agent_package.relevance_reasoning,
                },
                safety_hooks={
                    "citation_allow_list": [
                        citation.citation_id for citation in evidence_package.citations
                    ],
                    "requires_grounding_check": True,
                    "requires_safety_critic": bool(evidence_package.evidence),
                    "answer_generation_performed": False,
                },
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
        except Exception:
            logger.exception(
                "agent_run_failed",
                agent_name=self.name,
                agent_role=self.role.value,
                agent_run_id=agent_input.trace.agent_run_id,
                workflow_id=agent_input.trace.workflow_id,
                trace_id=agent_input.trace.trace_id,
                case_id=agent_input.case_id,
            )
            raise

        logger.info(
            "agent_run_completed",
            agent_name=self.name,
            agent_role=self.role.value,
            agent_run_id=agent_input.trace.agent_run_id,
            workflow_id=agent_input.trace.workflow_id,
            trace_id=agent_input.trace.trace_id,
            case_id=agent_input.case_id,
            status=output.status.value,
            confidence_score=output.confidence.score,
            confidence_band=output.confidence.band.value,
            retrieved_count=len(agent_package.evidence),
            citation_count=len(agent_package.citations),
            retrieval_backend=evidence_package.diagnostics.backend.value,
            latency_ms=round((perf_counter() - start) * 1000, 2),
        )
        return output


def build_retrieval_query(payload: dict[str, Any]) -> RetrievalQuery:
    query_text = str(payload.get("query") or payload.get("evidence_query") or "").strip()
    if not query_text:
        patient_context = payload.get("patient_context") or {}
        retrieval_profile = payload.get("retrieval_profile") or patient_context.get(
            "retrieval_profile",
            {},
        )
        query_terms = retrieval_profile.get("query_terms", [])
        query_text = " ".join(str(term) for term in query_terms if str(term).strip())
    if not query_text:
        query_text = "clinical evidence retrieval"

    filters_payload = payload.get("filters", {})
    filters = MetadataFilter(
        source_types=[
            EvidenceSourceType(source_type)
            for source_type in filters_payload.get("source_types", [])
        ],
        clinical_domains=list(filters_payload.get("clinical_domains", [])),
        patient_id=filters_payload.get("patient_id"),
        encounter_id=filters_payload.get("encounter_id"),
        guideline_org=filters_payload.get("guideline_org"),
        imaging_modality=filters_payload.get("imaging_modality"),
        body_part=filters_payload.get("body_part"),
        publication_year_min=filters_payload.get("publication_year_min"),
        publication_year_max=filters_payload.get("publication_year_max"),
        evidence_level=filters_payload.get("evidence_level"),
    )
    return RetrievalQuery(
        query=query_text,
        limit=int(payload.get("limit", payload.get("top_k", 10))),
        candidate_limit=int(payload.get("candidate_limit", 50)),
        score_threshold=payload.get("score_threshold"),
        filters=filters,
        mode=RetrievalMode(payload.get("mode", RetrievalMode.HYBRID.value)),
        fusion_strategy=FusionStrategy(
            payload.get("fusion_strategy", FusionStrategy.WEIGHTED_SUM.value)
        ),
        dense_weight=float(payload.get("dense_weight", 0.65)),
        bm25_weight=float(payload.get("bm25_weight", 0.35)),
        rerank=bool(payload.get("rerank", True)),
        include_payload=bool(payload.get("include_payload", True)),
        include_vectors=bool(payload.get("include_vectors", False)),
    )


def build_agent_package(
    evidence_package: EvidencePackage,
    retrieval_query: RetrievalQuery,
    *,
    retrieval_trace: object | None = None,
) -> EvidenceRetrievalAgentPackage:
    evidence = [
        RetrievedEvidenceAgentItem(
            rank=item.rank,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            source_id=item.metadata.source_id,
            source_type=item.metadata.source_type.value,
            title=item.metadata.title,
            text=item.text,
            citation_id=item.citation.citation_id,
            score=item.score,
            confidence_score=item.confidence_score,
            source_reliability_score=item.source_reliability_score,
            scoring_components=item.scoring_components,
            metadata=item.metadata.model_dump(mode="json"),
            relevance_reasoning=relevance_reasoning_for_item(item, retrieval_query.query),
        )
        for item in evidence_package.evidence
    ]
    citations = [
        EvidenceCitationAgentItem(
            citation_id=citation.citation_id,
            source_type=citation.source_type.value,
            source_id=citation.source_id,
            title=citation.title,
            url=citation.url,
            publication_year=citation.publication_year,
            section_path=citation.section_path,
            quote=citation.quote,
            attribution_text=citation.attribution_text,
        )
        for citation in evidence_package.citations
    ]
    retrieval_metadata: dict[str, Any] = {
        "mode": evidence_package.diagnostics.mode.value,
        "backend": evidence_package.diagnostics.backend.value,
        "fusion_strategy": evidence_package.diagnostics.fusion_strategy.value,
        "dense_result_count": evidence_package.diagnostics.dense_result_count,
        "bm25_result_count": evidence_package.diagnostics.bm25_result_count,
        "reranked": evidence_package.diagnostics.reranked,
        "filters_applied": evidence_package.diagnostics.filters_applied,
        "reliability_notes": evidence_package.diagnostics.reliability_notes,
        "limit": retrieval_query.limit,
        "candidate_limit": retrieval_query.candidate_limit,
        "retrieval_trace_id": evidence_package.retrieval_trace_id,
    }
    if retrieval_trace is not None and hasattr(retrieval_trace, "model_dump"):
        trace_payload = retrieval_trace.model_dump(mode="json")
        retrieval_metadata.update(
            {
                "retrieval_latency_ms": trace_payload["latency"]["retrieval_ms"],
                "reranking_latency_ms": trace_payload["latency"]["reranking_ms"],
                "packaging_latency_ms": trace_payload["latency"]["packaging_ms"],
                "total_retrieval_latency_ms": trace_payload["latency"]["total_ms"],
                "retrieved_document_count": trace_payload["retrieved_document_count"],
                "candidate_count": trace_payload["candidate_count"],
                "retrieval_confidence": trace_payload["retrieval_confidence"],
                "evidence_source_types": trace_payload["evidence_source_types"],
                "collection_name": trace_payload.get("collection_name"),
                "embedding_model": trace_payload.get("embedding_model"),
                "qdrant": trace_payload.get("qdrant"),
                "langfuse_retrieval_span": langfuse_retrieval_span(retrieval_trace),
            }
        )
    return EvidenceRetrievalAgentPackage(
        query=evidence_package.query,
        evidence=evidence,
        citations=citations,
        retrieval_confidence=evidence_package.confidence_score,
        retrieval_metadata=retrieval_metadata,
        relevance_reasoning=[
            relevance_reasoning_for_item(item, retrieval_query.query)
            for item in evidence_package.evidence
        ],
    )


def build_confidence(
    evidence_package: EvidencePackage,
    agent_package: EvidenceRetrievalAgentPackage,
) -> ConfidenceScore:
    retrieval_confidence = evidence_package.confidence_score
    citation_integrity = 1.0 if len(agent_package.citations) == len(agent_package.evidence) else 0.0
    source_reliability = (
        sum(item.source_reliability_score for item in evidence_package.evidence)
        / len(evidence_package.evidence)
        if evidence_package.evidence
        else 0.0
    )
    rerank_score = 1.0 if evidence_package.diagnostics.reranked else 0.65
    diversity_score = source_diversity_score(evidence_package)
    score = clamp01(
        0.35 * retrieval_confidence
        + 0.25 * citation_integrity
        + 0.20 * source_reliability
        + 0.10 * rerank_score
        + 0.10 * diversity_score
    )
    return ConfidenceScore(
        score=score,
        band=confidence_band(score),
        components={
            "retrieval_confidence": retrieval_confidence,
            "citation_integrity": citation_integrity,
            "source_reliability": source_reliability,
            "reranking": rerank_score,
            "source_diversity": diversity_score,
        },
        rationale=confidence_rationale(score, evidence_package),
    )


def retrieval_findings(evidence_package: EvidencePackage) -> list[AgentFinding]:
    findings = [
        AgentFinding(
            code="retrieval.reliability_note",
            severity="warning",
            message=note,
            requires_human_review=False,
        )
        for note in evidence_package.diagnostics.reliability_notes
    ]
    if not evidence_package.evidence:
        findings.append(
            AgentFinding(
                code="retrieval.no_evidence",
                severity="warning",
                message="No evidence was retrieved for the query.",
                requires_human_review=True,
            )
        )
    return findings


def source_diversity_score(evidence_package: EvidencePackage) -> float:
    if not evidence_package.evidence:
        return 0.0
    source_types = {item.metadata.source_type for item in evidence_package.evidence}
    return min(1.0, len(source_types) / 3)


def retrieval_summary(package: EvidenceRetrievalAgentPackage) -> str:
    return (
        f"Retrieved {len(package.evidence)} evidence items with "
        f"{len(package.citations)} citations for query: {package.query!r}."
    )


def confidence_band(score: float) -> ConfidenceBand:
    if score >= 0.85:
        return ConfidenceBand.HIGH
    if score >= 0.65:
        return ConfidenceBand.MODERATE
    if score > 0:
        return ConfidenceBand.LOW
    return ConfidenceBand.UNKNOWN


def confidence_rationale(score: float, evidence_package: EvidencePackage) -> str:
    if not evidence_package.evidence:
        return "No evidence was retrieved; downstream systems should abstain or request review."
    if score >= 0.85:
        return "Evidence retrieval is well-grounded with valid citations and reliable sources."
    if score >= 0.65:
        return "Evidence retrieval is usable with some source or retrieval limitations."
    return "Evidence retrieval is weakly grounded; downstream systems should be cautious."


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
