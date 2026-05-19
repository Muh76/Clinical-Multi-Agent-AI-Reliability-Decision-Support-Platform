from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from clinical_ai_retrieval.schemas import (
    EvidenceChunk,
    EvidenceMetadata,
    MetadataFilter,
    RetrievalResult,
    VectorRecord,
)


class QdrantVectorStore:
    def __init__(
        self,
        *,
        url: str,
        collection_name: str,
        vector_size: int,
        api_key: SecretStr | None = None,
        distance: models.Distance = models.Distance.COSINE,
    ) -> None:
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._distance = distance
        self._client = AsyncQdrantClient(
            url=url,
            api_key=api_key.get_secret_value() if api_key else None,
        )

    async def ensure_collection(self) -> None:
        exists = await self._client.collection_exists(self.collection_name)
        if not exists:
            await self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=self._distance,
                ),
            )
        await self._ensure_payload_indexes()

    async def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        points = [
            models.PointStruct(
                id=qdrant_point_id(record.id),
                vector=record.vector,
                payload=chunk_to_payload(record.chunk),
            )
            for record in records
        ]
        await self._client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    async def search(
        self,
        *,
        query_vector: list[float],
        limit: int,
        filters: MetadataFilter,
        score_threshold: float | None = None,
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> list[RetrievalResult]:
        results = await self._client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=build_qdrant_filter(filters),
            limit=limit,
            score_threshold=score_threshold,
            with_payload=with_payload,
            with_vectors=with_vectors,
        )
        return [scored_point_to_result(point) for point in results]

    async def close(self) -> None:
        await self._client.close()

    async def _ensure_payload_indexes(self) -> None:
        keyword_fields = [
            "source_type",
            "source_id",
            "patient_id",
            "encounter_id",
            "guideline_org",
            "imaging_modality",
            "body_part",
            "clinical_domains",
            "evidence_level",
        ]
        for field_name in keyword_fields:
            await self._client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        await self._client.create_payload_index(
            collection_name=self.collection_name,
            field_name="publication_year",
            field_schema=models.PayloadSchemaType.INTEGER,
        )


def qdrant_point_id(record_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, record_id))


def chunk_to_payload(chunk: EvidenceChunk) -> dict[str, object]:
    metadata = chunk.metadata.model_dump(mode="json")
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "text": chunk.text,
        "chunk_index": chunk.chunk_index,
        "token_estimate": chunk.token_estimate,
        **metadata,
    }


def scored_point_to_result(point: models.ScoredPoint) -> RetrievalResult:
    payload = point.payload or {}
    metadata = EvidenceMetadata.model_validate(payload_metadata(payload))
    return RetrievalResult(
        chunk_id=str(payload.get("chunk_id", point.id)),
        document_id=str(payload.get("document_id", "")),
        score=float(point.score),
        text=str(payload.get("text", "")),
        metadata=metadata,
        payload=payload,
    )


def payload_metadata(payload: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key not in {"chunk_id", "document_id", "text", "chunk_index", "token_estimate"}
    }


def build_qdrant_filter(filters: MetadataFilter) -> models.Filter | None:
    conditions: list[models.FieldCondition] = []
    if filters.source_types:
        conditions.append(
            models.FieldCondition(
                key="source_type",
                match=models.MatchAny(
                    any=[source_type.value for source_type in filters.source_types]
                ),
            )
        )
    for key, value in {
        "patient_id": filters.patient_id,
        "encounter_id": filters.encounter_id,
        "guideline_org": filters.guideline_org,
        "imaging_modality": filters.imaging_modality,
        "body_part": filters.body_part,
        "evidence_level": filters.evidence_level,
    }.items():
        if value is not None:
            conditions.append(models.FieldCondition(key=key, match=models.MatchValue(value=value)))

    if filters.clinical_domains:
        conditions.append(
            models.FieldCondition(
                key="clinical_domains",
                match=models.MatchAny(any=filters.clinical_domains),
            )
        )
    year_range = models.Range(
        gte=filters.publication_year_min,
        lte=filters.publication_year_max,
    )
    if year_range.gte is not None or year_range.lte is not None:
        conditions.append(models.FieldCondition(key="publication_year", range=year_range))
    if not conditions:
        return None
    return models.Filter(must=conditions)
