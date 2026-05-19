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


class EvidenceChunk(RetrievalModel):
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int = Field(ge=0)
    metadata: EvidenceMetadata
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
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    filters: MetadataFilter = Field(default_factory=MetadataFilter)
    include_payload: bool = True
    include_vectors: bool = False


class RetrievalResult(RetrievalModel):
    chunk_id: str
    document_id: str
    score: float
    text: str
    metadata: EvidenceMetadata
    payload: dict[str, Any] = Field(default_factory=dict)


class IndexingResult(RetrievalModel):
    document_id: str
    status: IndexingStatus
    chunk_count: int = Field(ge=0)
    collection_name: str
