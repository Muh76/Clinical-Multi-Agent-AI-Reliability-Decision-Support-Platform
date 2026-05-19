# Vector Retrieval Layer

The vector retrieval layer provides evidence-grounded search over clinical knowledge assets. It is
designed for reliability and decision intelligence workflows, not autonomous diagnosis.

## Architecture

Core package: `packages/retrieval/src/clinical_ai_retrieval`

```text
EvidenceDocument
  -> TextChunker
  -> EmbeddingProvider
  -> VectorIndexingPipeline
  -> QdrantVectorStore
  -> VectorRetrievalService
  -> RetrievalResult[]
```

Main components:

- `EvidenceMetadata`: source-aware metadata for PubMed, NICE guidelines, synthetic clinical
  protocols, imaging report metadata, and local policy.
- `EmbeddingProvider`: async protocol for embedding providers.
- `SentenceTransformerEmbeddingProvider`: initial local provider using
  `sentence-transformers/all-MiniLM-L6-v2`.
- `TextChunker`: overlap-based text chunking.
- `QdrantVectorStore`: async Qdrant collection management, payload indexing, upsert, and filtered
  search.
- `VectorIndexingPipeline`: chunks documents, embeds batches, and upserts vectors.
- `VectorRetrievalService`: embeds user/query context, searches Qdrant, and optionally calls a future
  reranker.

The service is async-first at the orchestration boundary. Sentence-transformers itself is synchronous,
so the provider runs encoding in a worker thread via `asyncio.to_thread()`. Hosted providers such as
OpenAI, Gemini, Azure OpenAI, or private embedding endpoints can implement the same protocol later.

## Qdrant Setup

Docker Compose now includes:

```text
clinical-ai-qdrant
  http: 6333
  grpc: 6334
  volume: clinical_ai_qdrant_data
```

Local API containers use:

```text
VECTOR_PROVIDER=qdrant
VECTOR_DATABASE_URL=http://clinical-ai-qdrant:6333
VECTOR_COLLECTION_PREFIX=clinical_ai
VECTOR_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

Collections are named with the embedding dimension:

```text
{VECTOR_COLLECTION_PREFIX}_evidence_{dimension}
```

This prevents accidental mixing of vectors produced by incompatible embedding models.

## Metadata Schema

`EvidenceMetadata` supports:

- PubMed: `source_type=pubmed`, `source_id`, `title`, `authors`, `publication_year`, `url`,
  `clinical_domains`, `evidence_level`.
- NICE guidelines: `source_type=nice_guideline`, `guideline_org`, `jurisdiction`, `title`, `url`.
- Synthetic protocols: `source_type=synthetic_protocol`, `protocol_version`, `clinical_domains`.
- Imaging report metadata: `source_type=imaging_report_metadata`, `imaging_modality`, `body_part`,
  `patient_id`, `encounter_id`.
- Local policy: `source_type=local_policy`, `jurisdiction`, `guideline_org`, `protocol_version`.

Qdrant payload indexes are created for common filters:

- `source_type`
- `source_id`
- `patient_id`
- `encounter_id`
- `guideline_org`
- `imaging_modality`
- `body_part`
- `clinical_domains`
- `evidence_level`
- `publication_year`

## Metadata Filtering

`MetadataFilter` allows retrieval to constrain evidence before ranking:

- source type, for example PubMed only or NICE only;
- clinical domains, for example cardiology or sepsis;
- patient or encounter identifiers for synthetic/de-identified local datasets;
- imaging modality and body part;
- publication year range;
- evidence level;
- guideline organization.

Filtering is pushed into Qdrant as payload filters so irrelevant chunks are excluded before vector
similarity ranking. This is important for clinical safety because a high-similarity result from the
wrong source class can be misleading.

## Chunk Indexing Strategies

The initial `TextChunker` uses character windows with overlap:

- default max chunk: 1,800 characters;
- default overlap: 250 characters;
- sentence boundary preference when possible;
- token estimate stored for downstream budgeting.

Recommended strategies by source:

- PubMed abstracts: one chunk for short abstracts; section-aware chunks for full text.
- NICE guidelines: chunk by section and recommendation block, preserving headings in text.
- Synthetic protocols: chunk by protocol step or policy rule.
- Imaging report metadata: chunk the impression, findings summary, modality, body part, and study
  descriptors as a compact text representation.

Production indexers should preserve source section titles in the chunk text and metadata. This makes
retrieved evidence easier to explain and cite.

## Retrieval Flow

1. Caller submits `RetrievalQuery`.
2. Query text is embedded by the configured `EmbeddingProvider`.
3. Metadata filters are translated into a Qdrant filter.
4. Qdrant returns vector hits with payload.
5. Results are normalized into `RetrievalResult`.
6. Optional future `Reranker` reorders the candidate set.

The reranker interface is already present:

```python
class Reranker(Protocol):
    async def rerank(self, *, query: str, results: list[RetrievalResult], limit: int) -> list[RetrievalResult]: ...
```

This can support cross-encoders, hosted rerankers, LLM-based evidence adjudication, or hybrid
lexical/vector scoring.

## Observability-Ready Design

The services keep clear boundaries around:

- embedding latency;
- chunk counts;
- index upsert counts;
- Qdrant query latency;
- result counts;
- score distributions;
- filter usage;
- collection name and embedding model.

Those values should be emitted by API routes, workers, or schedulers using the platform
observability layer. The retrieval package avoids owning global logging configuration so it can be
used inside API requests, background jobs, or evaluation pipelines.

## Scalability Considerations

- Use batch embedding for indexing; keep online query embedding single-input and low latency.
- Separate collections by embedding model and vector dimension.
- Use Qdrant payload indexes for high-cardinality filters used in clinical workflows.
- Keep patient-linked imaging metadata in separate collections or strict filters when moving beyond
  synthetic/de-identified development data.
- Add ingestion idempotency with stable chunk IDs. The current pipeline uses deterministic UUIDs from
  chunk IDs so re-indexing updates the same points.
- Add hybrid retrieval when exact terms matter, especially drug names, guideline IDs, acronyms, and
  rare conditions.
- Add reranking for high-stakes workflows where top-k semantic similarity is insufficient.
- Use background workers for large PubMed/NICE indexing jobs rather than request-time indexing.

## Minimal Usage

```python
from clinical_ai_retrieval import EvidenceDocument, EvidenceMetadata
from clinical_ai_retrieval.factory import build_indexing_pipeline, build_retrieval_service
from clinical_ai_retrieval.schemas import EvidenceSourceType, MetadataFilter, RetrievalQuery

indexer = build_indexing_pipeline(
    url="http://localhost:6333",
    collection_prefix="clinical_ai",
)

document = EvidenceDocument(
    document_id="nice-ng51-sepsis",
    text="Recognise that people with suspected sepsis may have non-specific symptoms...",
    metadata=EvidenceMetadata(
        source_type=EvidenceSourceType.NICE_GUIDELINE,
        source_id="NG51",
        title="Sepsis: recognition, diagnosis and early management",
        guideline_org="NICE",
        clinical_domains=["sepsis", "emergency_medicine"],
    ),
)

await indexer.index_document(document)

retriever = build_retrieval_service(
    url="http://localhost:6333",
    collection_prefix="clinical_ai",
)

results = await retriever.retrieve(
    RetrievalQuery(
        query="adult suspected sepsis initial assessment",
        filters=MetadataFilter(source_types=[EvidenceSourceType.NICE_GUIDELINE]),
    )
)
```
