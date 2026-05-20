from __future__ import annotations

from dataclasses import dataclass
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
from clinical_ai_retrieval.contracts import EvidencePackager
from clinical_ai_retrieval.schemas import (
    Citation,
    EvidenceMetadata,
    EvidencePackage,
    EvidenceSourceType,
    FusionStrategy,
    MetadataFilter,
    RetrievalDiagnostics,
    RetrievalEvidenceItem,
    RetrievalMode,
    RetrievalQuery,
)
from pydantic import BaseModel, ConfigDict, Field


logger = get_logger(__name__)


class EvidenceCorpusItem(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: str
    text: str = Field(min_length=1, max_length=100_000)
    source_type: EvidenceSourceType = EvidenceSourceType.SYNTHETIC_PROTOCOL
    title: str | None = None
    citation_id: str | None = None
    url: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    clinical_domains: list[str] = Field(default_factory=list)
    evidence_level: str | None = None
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


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


@dataclass(frozen=True)
class LocalCandidate:
    item: EvidenceCorpusItem
    score: float
    rerank_score: float
    source_reliability_score: float

    @property
    def final_score(self) -> float:
        return clamp01(
            0.50 * self.score
            + 0.25 * self.rerank_score
            + 0.25 * self.source_reliability_score
        )

    @property
    def confidence_score(self) -> float:
        return clamp01(0.70 * self.final_score + 0.30 * self.source_reliability_score)


class EvidenceRetrievalAgent:
    name = "evidence_retrieval_agent"
    role = AgentRole.EVIDENCE_RETRIEVAL

    def __init__(self, retriever: EvidencePackager | None = None) -> None:
        self._retriever = retriever

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
            evidence_package = await self._retrieve(retrieval_query, agent_input.payload)
            agent_package = build_agent_package(evidence_package, retrieval_query)
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
            latency_ms=round((perf_counter() - start) * 1000, 2),
        )
        return output

    async def _retrieve(
        self,
        retrieval_query: RetrievalQuery,
        payload: dict[str, Any],
    ) -> EvidencePackage:
        if self._retriever is not None:
            return await self._retriever.retrieve_evidence(retrieval_query)
        return local_retrieve(retrieval_query, payload)


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


def local_retrieve(query: RetrievalQuery, payload: dict[str, Any]) -> EvidencePackage:
    corpus = [
        EvidenceCorpusItem.model_validate(item)
        for item in payload.get("evidence_corpus", [])
    ]
    query_tokens = tokenize(query.query)
    candidates = [
        candidate
        for item in corpus
        if metadata_matches(item, query.filters)
        for candidate in [local_candidate(item, query_tokens)]
        if candidate.score > 0.0 or not query_tokens
    ]
    ranked = sorted(candidates, key=lambda candidate: candidate.final_score, reverse=True)[
        : query.limit
    ]
    evidence_items = [
        local_evidence_item(rank=rank, candidate=candidate)
        for rank, candidate in enumerate(ranked, start=1)
    ]
    citations = [item.citation for item in evidence_items]
    confidence = (
        sum(item.confidence_score for item in evidence_items) / len(evidence_items)
        if evidence_items
        else 0.0
    )
    return EvidencePackage(
        query=query.query,
        evidence=evidence_items,
        citations=citations,
        diagnostics=RetrievalDiagnostics(
            mode=query.mode,
            fusion_strategy=query.fusion_strategy,
            dense_result_count=len(candidates) if query.mode != RetrievalMode.BM25 else 0,
            bm25_result_count=len(candidates) if query.mode != RetrievalMode.DENSE else 0,
            reranked=query.rerank,
            filters_applied=query.filters != MetadataFilter(),
            reliability_notes=local_reliability_notes(evidence_items),
        ),
        confidence_score=confidence,
    )


def local_candidate(item: EvidenceCorpusItem, query_tokens: set[str]) -> LocalCandidate:
    source_tokens = tokenize(f"{item.title or ''} {item.text}")
    overlap = len(query_tokens & source_tokens)
    coverage = overlap / len(query_tokens) if query_tokens else 0.0
    density = overlap / len(source_tokens) if source_tokens else 0.0
    title_tokens = tokenize(item.title or "")
    title_overlap = len(query_tokens & title_tokens) / len(query_tokens) if query_tokens else 0.0
    retrieval_score = clamp01(0.80 * coverage + 0.20 * density)
    rerank_score = clamp01(0.75 * retrieval_score + 0.25 * title_overlap)
    return LocalCandidate(
        item=item,
        score=retrieval_score,
        rerank_score=rerank_score,
        source_reliability_score=source_reliability_score(
            item.source_type,
            item.evidence_level,
        ),
    )


def local_evidence_item(rank: int, candidate: LocalCandidate) -> RetrievalEvidenceItem:
    item = candidate.item
    citation_id = item.citation_id or f"{item.source_type.value}:{item.source_id}"
    metadata = EvidenceMetadata(
        source_type=item.source_type,
        source_id=item.source_id,
        title=item.title,
        url=item.url,
        publication_year=item.publication_year,
        clinical_domains=item.clinical_domains,
        evidence_level=item.evidence_level,
        citation_id=citation_id,
        citation_text=citation_text(item),
        extra=item.metadata,
    )
    citation = Citation(
        citation_id=citation_id,
        source_type=item.source_type,
        source_id=item.source_id,
        title=item.title,
        url=item.url,
        publication_year=item.publication_year,
        quote=item.text[:500],
        attribution_text=citation_text(item),
    )
    return RetrievalEvidenceItem(
        chunk_id=f"{item.source_type.value}:{item.source_id}:0",
        document_id=f"{item.source_type.value}:{item.source_id}",
        text=item.text,
        citation=citation,
        metadata=metadata,
        score=candidate.final_score,
        confidence_score=candidate.confidence_score,
        source_reliability_score=candidate.source_reliability_score,
        rank=rank,
        scoring_components={
            "retrieval": candidate.score,
            "rerank": candidate.rerank_score,
            "source_reliability": candidate.source_reliability_score,
            "final": candidate.final_score,
        },
    )


def build_agent_package(
    evidence_package: EvidencePackage,
    retrieval_query: RetrievalQuery,
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
            relevance_reasoning=relevance_reasoning(item, retrieval_query.query),
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
    return EvidenceRetrievalAgentPackage(
        query=evidence_package.query,
        evidence=evidence,
        citations=citations,
        retrieval_confidence=evidence_package.confidence_score,
        retrieval_metadata={
            "mode": evidence_package.diagnostics.mode.value,
            "fusion_strategy": evidence_package.diagnostics.fusion_strategy.value,
            "dense_result_count": evidence_package.diagnostics.dense_result_count,
            "bm25_result_count": evidence_package.diagnostics.bm25_result_count,
            "reranked": evidence_package.diagnostics.reranked,
            "filters_applied": evidence_package.diagnostics.filters_applied,
            "reliability_notes": evidence_package.diagnostics.reliability_notes,
            "limit": retrieval_query.limit,
            "candidate_limit": retrieval_query.candidate_limit,
        },
        relevance_reasoning=[
            relevance_reasoning(item, retrieval_query.query)
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


def metadata_matches(item: EvidenceCorpusItem, filters: MetadataFilter) -> bool:
    if filters.source_types and item.source_type not in filters.source_types:
        return False
    if filters.clinical_domains:
        if not set(filters.clinical_domains).intersection(item.clinical_domains):
            return False
    if filters.publication_year_min and item.publication_year:
        if item.publication_year < filters.publication_year_min:
            return False
    if filters.publication_year_max and item.publication_year:
        if item.publication_year > filters.publication_year_max:
            return False
    if filters.evidence_level and item.evidence_level != filters.evidence_level:
        return False
    return True


def source_reliability_score(
    source_type: EvidenceSourceType,
    evidence_level: str | None,
) -> float:
    source_scores = {
        EvidenceSourceType.NICE_GUIDELINE: 0.95,
        EvidenceSourceType.LOCAL_POLICY: 0.88,
        EvidenceSourceType.PUBMED: 0.78,
        EvidenceSourceType.SYNTHETIC_PROTOCOL: 0.55,
        EvidenceSourceType.IMAGING_REPORT_METADATA: 0.45,
    }
    evidence_scores = {
        "guideline": 0.95,
        "systematic_review": 0.86,
        "randomized_trial": 0.82,
        "clinical_trial": 0.78,
        "observational_study": 0.70,
        "case_report": 0.55,
    }
    base = source_scores.get(source_type, 0.50)
    if evidence_level is None:
        return base
    return max(base, evidence_scores.get(evidence_level, base))


def source_diversity_score(evidence_package: EvidencePackage) -> float:
    if not evidence_package.evidence:
        return 0.0
    source_types = {item.metadata.source_type for item in evidence_package.evidence}
    return min(1.0, len(source_types) / 3)


def relevance_reasoning(item: RetrievalEvidenceItem, query: str) -> str:
    query_tokens = tokenize(query)
    evidence_tokens = tokenize(f"{item.metadata.title or ''} {item.text}")
    matched_terms = sorted(query_tokens & evidence_tokens)
    term_text = ", ".join(matched_terms[:8]) if matched_terms else "no exact lexical terms"
    return (
        f"Rank {item.rank} evidence matched {term_text}; "
        f"source type is {item.metadata.source_type.value}; "
        f"source reliability score is {item.source_reliability_score:.2f}."
    )


def local_reliability_notes(evidence: list[RetrievalEvidenceItem]) -> list[str]:
    if not evidence:
        return ["No evidence chunks were retrieved for this query."]
    notes: list[str] = []
    if all(item.metadata.source_type == EvidenceSourceType.SYNTHETIC_PROTOCOL for item in evidence):
        notes.append(
            "Only synthetic protocol evidence was retrieved; do not treat it as clinical authority."
        )
    if any(item.confidence_score < 0.35 for item in evidence):
        notes.append("Some retrieved evidence has low confidence and should be reviewed.")
    return notes


def retrieval_summary(package: EvidenceRetrievalAgentPackage) -> str:
    return (
        f"Retrieved {len(package.evidence)} evidence items with "
        f"{len(package.citations)} citations for query: {package.query!r}."
    )


def citation_text(item: EvidenceCorpusItem) -> str:
    title = item.title or item.source_id
    year = f" ({item.publication_year})" if item.publication_year else ""
    return f"{title}{year}. {item.source_type.value.replace('_', ' ')}: {item.source_id}."


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


def tokenize(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {token for token in normalized.split() if len(token) > 1}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
