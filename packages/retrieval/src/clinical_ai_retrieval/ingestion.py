from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from clinical_ai_retrieval.observability import NoopRetrievalObserver, RetrievalObserver
from clinical_ai_retrieval.schemas import (
    EvidenceDocument,
    EvidenceMetadata,
    EvidenceSourceType,
    IngestionFailure,
    IngestionResult,
    IngestionStatus,
    IndexingResult,
    LoadedDocument,
)


class IndexingPipeline(Protocol):
    async def index_document(self, document: EvidenceDocument) -> IndexingResult:
        """Index one normalized evidence document."""


class DocumentLoader(ABC):
    source_type: EvidenceSourceType

    @abstractmethod
    async def load(self, source_uri: str) -> list[LoadedDocument]:
        """Load source content into raw documents."""


class DocumentProcessor(ABC):
    source_type: EvidenceSourceType

    @abstractmethod
    async def process(self, document: LoadedDocument) -> list[EvidenceDocument]:
        """Normalize a loaded source document into indexable evidence documents."""


class TextFileLoader(DocumentLoader):
    def __init__(self, source_type: EvidenceSourceType) -> None:
        self.source_type = source_type

    async def load(self, source_uri: str) -> list[LoadedDocument]:
        path = Path(source_uri)
        return [
            LoadedDocument(
                source_uri=str(path),
                source_type=self.source_type,
                raw_text=path.read_text(encoding="utf-8"),
                raw_metadata={"filename": path.name},
            )
        ]


class JsonRecordLoader(DocumentLoader):
    def __init__(self, source_type: EvidenceSourceType) -> None:
        self.source_type = source_type

    async def load(self, source_uri: str) -> list[LoadedDocument]:
        path = Path(source_uri)
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else payload.get("records", [payload])
        return [
            LoadedDocument(
                source_uri=f"{path}#{index}",
                source_type=self.source_type,
                raw_text=str(record.get("abstract") or record.get("text") or ""),
                raw_metadata={
                    key: value
                    for key, value in record.items()
                    if key not in {"abstract", "text"}
                },
            )
            for index, record in enumerate(records)
            if isinstance(record, dict)
        ]


class DirectoryLoader(DocumentLoader):
    def __init__(
        self,
        source_type: EvidenceSourceType,
        *,
        patterns: tuple[str, ...] = ("*.txt", "*.md", "*.json"),
    ) -> None:
        self.source_type = source_type
        self.patterns = patterns

    async def load(self, source_uri: str) -> list[LoadedDocument]:
        path = Path(source_uri)
        documents: list[LoadedDocument] = []
        for pattern in self.patterns:
            for file_path in sorted(path.glob(pattern)):
                loader: DocumentLoader
                if file_path.suffix.lower() == ".json":
                    loader = JsonRecordLoader(self.source_type)
                else:
                    loader = TextFileLoader(self.source_type)
                documents.extend(await loader.load(str(file_path)))
        return documents


class BaseEvidenceProcessor(DocumentProcessor):
    def __init__(
        self,
        source_type: EvidenceSourceType,
        *,
        default_clinical_domains: list[str] | None = None,
    ) -> None:
        self.source_type = source_type
        self.default_clinical_domains = default_clinical_domains or []

    async def process(self, document: LoadedDocument) -> list[EvidenceDocument]:
        source_id = str(
            document.raw_metadata.get("pmid")
            or document.raw_metadata.get("source_id")
            or document.raw_metadata.get("id")
            or stable_source_id(document.source_uri)
        )
        title = optional_string(document.raw_metadata.get("title"))
        metadata = EvidenceMetadata(
            source_type=self.source_type,
            source_id=source_id,
            title=title,
            url=optional_string(document.raw_metadata.get("url")),
            authors=list_value(document.raw_metadata.get("authors")),
            publication_year=optional_int(
                document.raw_metadata.get("publication_year") or document.raw_metadata.get("year")
            ),
            guideline_org=optional_string(document.raw_metadata.get("guideline_org")),
            protocol_version=optional_string(document.raw_metadata.get("protocol_version")),
            clinical_domains=list_value(
                document.raw_metadata.get("clinical_domains"),
                default=self.default_clinical_domains,
            ),
            evidence_level=optional_string(document.raw_metadata.get("evidence_level")),
            jurisdiction=optional_string(document.raw_metadata.get("jurisdiction")),
            citation_id=f"{self.source_type.value}:{source_id}",
            citation_text=build_citation_text(
                self.source_type,
                source_id,
                title,
                document.raw_metadata,
            ),
            source_version=optional_string(document.raw_metadata.get("source_version")),
            section_path=list_value(document.raw_metadata.get("section_path")),
            extra=primitive_metadata(document.raw_metadata),
        )
        return [
            EvidenceDocument(
                document_id=f"{self.source_type.value}:{source_id}",
                text=document.raw_text,
                metadata=metadata,
            )
        ]


class PubMedAbstractProcessor(BaseEvidenceProcessor):
    def __init__(self) -> None:
        super().__init__(
            EvidenceSourceType.PUBMED,
            default_clinical_domains=["biomedical_literature"],
        )


class NiceGuidelineProcessor(BaseEvidenceProcessor):
    def __init__(self) -> None:
        super().__init__(
            EvidenceSourceType.NICE_GUIDELINE,
            default_clinical_domains=["guideline"],
        )


class SyntheticProtocolProcessor(BaseEvidenceProcessor):
    def __init__(self) -> None:
        super().__init__(
            EvidenceSourceType.SYNTHETIC_PROTOCOL,
            default_clinical_domains=["synthetic_protocol"],
        )


class ClinicalPolicyProcessor(BaseEvidenceProcessor):
    def __init__(self) -> None:
        super().__init__(
            EvidenceSourceType.LOCAL_POLICY,
            default_clinical_domains=["policy"],
        )


class KnowledgeIngestionPipeline:
    def __init__(
        self,
        *,
        loaders: dict[EvidenceSourceType, DocumentLoader],
        processors: dict[EvidenceSourceType, DocumentProcessor],
        indexer: IndexingPipeline,
        observer: RetrievalObserver | None = None,
        continue_on_error: bool = True,
    ) -> None:
        self.loaders = loaders
        self.processors = processors
        self.indexer = indexer
        self.observer = observer or NoopRetrievalObserver()
        self.continue_on_error = continue_on_error

    async def ingest(self, source_uri: str, source_type: EvidenceSourceType) -> IngestionResult:
        failures: list[IngestionFailure] = []
        documents: list[EvidenceDocument] = []
        indexed_count = 0
        chunks_indexed = 0
        try:
            loaded_documents = await self.loaders[source_type].load(source_uri)
        except Exception as exc:
            failure = ingestion_failure(source_uri, "load", exc, recoverable=False)
            return IngestionResult(
                source_uri=source_uri,
                status=IngestionStatus.FAILED,
                failures=[failure],
            )

        processor = self.processors[source_type]
        for loaded_document in loaded_documents:
            try:
                documents.extend(await processor.process(loaded_document))
            except Exception as exc:
                failures.append(ingestion_failure(loaded_document.source_uri, "process", exc))
                if not self.continue_on_error:
                    break

        for document in documents:
            try:
                result = await self.indexer.index_document(document)
                indexed_count += 1
                chunks_indexed += result.chunk_count
            except Exception as exc:
                failures.append(ingestion_failure(document.document_id, "index", exc))
                if not self.continue_on_error:
                    break

        await self.observer.record_ingestion(
            source_uri=source_uri,
            source_type=source_type.value,
            document_count=len(documents),
            failure_count=len(failures),
        )
        status = (
            IngestionStatus.FAILED
            if failures and indexed_count == 0
            else IngestionStatus.INDEXED
        )
        citations = [document_to_citation(document) for document in documents[:indexed_count]]
        return IngestionResult(
            source_uri=source_uri,
            status=status,
            documents_loaded=len(loaded_documents),
            documents_indexed=indexed_count,
            chunks_indexed=chunks_indexed,
            citations=citations,
            failures=failures,
        )


def default_loaders() -> dict[EvidenceSourceType, DocumentLoader]:
    return {
        EvidenceSourceType.PUBMED: JsonRecordLoader(EvidenceSourceType.PUBMED),
        EvidenceSourceType.NICE_GUIDELINE: DirectoryLoader(EvidenceSourceType.NICE_GUIDELINE),
        EvidenceSourceType.SYNTHETIC_PROTOCOL: DirectoryLoader(
            EvidenceSourceType.SYNTHETIC_PROTOCOL
        ),
        EvidenceSourceType.LOCAL_POLICY: DirectoryLoader(EvidenceSourceType.LOCAL_POLICY),
    }


def default_processors() -> dict[EvidenceSourceType, DocumentProcessor]:
    return {
        EvidenceSourceType.PUBMED: PubMedAbstractProcessor(),
        EvidenceSourceType.NICE_GUIDELINE: NiceGuidelineProcessor(),
        EvidenceSourceType.SYNTHETIC_PROTOCOL: SyntheticProtocolProcessor(),
        EvidenceSourceType.LOCAL_POLICY: ClinicalPolicyProcessor(),
    }


def stable_source_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, value))


def ingestion_failure(
    source_uri: str,
    stage: str,
    exc: Exception,
    *,
    recoverable: bool = True,
) -> IngestionFailure:
    return IngestionFailure(
        source_uri=source_uri,
        stage=stage,
        error_type=type(exc).__name__,
        message=str(exc),
        recoverable=recoverable,
    )


def document_to_citation(document: EvidenceDocument):
    from clinical_ai_retrieval.chunking import chunk_citation

    return chunk_citation(document, 0, document.text)


def build_citation_text(
    source_type: EvidenceSourceType,
    source_id: str,
    title: str | None,
    metadata: dict[str, Any],
) -> str:
    year = optional_int(metadata.get("publication_year") or metadata.get("year"))
    year_text = f" ({year})" if year else ""
    label = title or source_id
    return f"{label}{year_text}. {source_type.value.replace('_', ' ')}: {source_id}."


def optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def list_value(value: object, *, default: list[str] | None = None) -> list[str]:
    if value is None:
        return default or []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def primitive_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    return {
        key: value
        for key, value in metadata.items()
        if isinstance(value, str | int | float | bool)
    }
