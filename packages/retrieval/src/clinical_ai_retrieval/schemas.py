from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceSourceType(StrEnum):
    PUBMED = "pubmed"
    NICE_GUIDELINE = "nice_guideline"
    SYNTHETIC_PROTOCOL = "synthetic_protocol"
    IMAGING_REPORT_METADATA = "imaging_report_metadata"
    LOCAL_POLICY = "local_policy"


class RetrievalModality(StrEnum):
    TEXT = "text"
    TABLE = "table"
    IMAGING_METADATA = "imaging_metadata"
    MULTIMODAL_SUMMARY = "multimodal_summary"


class IndexingStatus(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"


class IngestionStatus(StrEnum):
    LOADED = "loaded"
    PROCESSED = "processed"
    INDEXED = "indexed"
    FAILED = "failed"


class RetrievalMode(StrEnum):
    DENSE = "dense"
    BM25 = "bm25"
    HYBRID = "hybrid"


class FusionStrategy(StrEnum):
    WEIGHTED_SUM = "weighted_sum"
    RECIPROCAL_RANK_FUSION = "reciprocal_rank_fusion"


class RetrievalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceMetadata(RetrievalModel):
    source_type: EvidenceSourceType
    source_id: str
    title: str | None = None
    url: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    guideline_org: str | None = None
    protocol_version: str | None = None
    imaging_modality: str | None = None
    body_part: str | None = None
    patient_id: str | None = Field(
        default=None,
        description="Only for synthetic or de-identified local development datasets.",
    )
    encounter_id: str | None = None
    clinical_domains: list[str] = Field(default_factory=list)
    evidence_level: str | None = None
    jurisdiction: str | None = None
    citation_id: str | None = None
    citation_text: str | None = None
    source_version: str | None = None
    section_path: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    extra: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class EvidenceDocument(RetrievalModel):
    document_id: str
    text: str
    metadata: EvidenceMetadata


class LoadedDocument(RetrievalModel):
    source_uri: str
    source_type: EvidenceSourceType
    raw_text: str
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    loaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Citation(RetrievalModel):
    citation_id: str
    source_type: EvidenceSourceType
    source_id: str
    title: str | None = None
    url: str | None = None
    publication_year: int | None = Field(default=None, ge=1800, le=2200)
    section_path: list[str] = Field(default_factory=list)
    quote: str | None = Field(default=None, max_length=1_000)
    attribution_text: str


class EvidenceChunk(RetrievalModel):
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int = Field(ge=0)
    metadata: EvidenceMetadata
    citation: Citation | None = None
    token_estimate: int = Field(default=0, ge=0)


class VectorRecord(RetrievalModel):
    id: str
    vector: list[float]
    chunk: EvidenceChunk


class MetadataFilter(RetrievalModel):
    source_types: list[EvidenceSourceType] = Field(default_factory=list)
    clinical_domains: list[str] = Field(default_factory=list)
    patient_id: str | None = None
    encounter_id: str | None = None
    guideline_org: str | None = None
    imaging_modality: str | None = None
    body_part: str | None = None
    publication_year_min: int | None = Field(default=None, ge=1800, le=2200)
    publication_year_max: int | None = Field(default=None, ge=1800, le=2200)
    evidence_level: str | None = None


class RetrievalQuery(RetrievalModel):
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    candidate_limit: int = Field(default=50, ge=1, le=500)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    filters: MetadataFilter = Field(default_factory=MetadataFilter)
    mode: RetrievalMode = RetrievalMode.HYBRID
    fusion_strategy: FusionStrategy = FusionStrategy.WEIGHTED_SUM
    dense_weight: float = Field(default=0.65, ge=0.0, le=1.0)
    bm25_weight: float = Field(default=0.35, ge=0.0, le=1.0)
    rerank: bool = True
    include_payload: bool = True
    include_vectors: bool = False


class RetrievalResult(RetrievalModel):
    chunk_id: str
    document_id: str
    score: float
    text: str
    metadata: EvidenceMetadata
    dense_score: float | None = None
    lexical_score: float | None = None
    rerank_score: float | None = None
    source_reliability_score: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)


class RetrievalEvidenceItem(RetrievalModel):
    chunk_id: str
    document_id: str
    text: str
    citation: Citation
    metadata: EvidenceMetadata
    score: float = Field(ge=0.0)
    confidence_score: float = Field(ge=0.0, le=1.0)
    source_reliability_score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1)
    scoring_components: dict[str, float] = Field(default_factory=dict)


class RetrievalDiagnostics(RetrievalModel):
    mode: RetrievalMode
    fusion_strategy: FusionStrategy
    dense_result_count: int = Field(default=0, ge=0)
    bm25_result_count: int = Field(default=0, ge=0)
    reranked: bool = False
    filters_applied: bool = False
    reliability_notes: list[str] = Field(default_factory=list)


class EvidencePackage(RetrievalModel):
    query: str
    evidence: list[RetrievalEvidenceItem]
    citations: list[Citation]
    diagnostics: RetrievalDiagnostics
    confidence_score: float = Field(ge=0.0, le=1.0)


class IndexingResult(RetrievalModel):
    document_id: str
    status: IndexingStatus
    chunk_count: int = Field(ge=0)
    collection_name: str


class IngestionFailure(RetrievalModel):
    source_uri: str
    stage: str
    error_type: str
    message: str
    recoverable: bool = True


class IngestionResult(RetrievalModel):
    source_uri: str
    status: IngestionStatus
    documents_loaded: int = Field(default=0, ge=0)
    documents_indexed: int = Field(default=0, ge=0)
    chunks_indexed: int = Field(default=0, ge=0)
    citations: list[Citation] = Field(default_factory=list)
    failures: list[IngestionFailure] = Field(default_factory=list)
