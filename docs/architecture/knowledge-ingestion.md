# Clinical Knowledge Ingestion Pipeline

The clinical knowledge ingestion pipeline prepares trusted knowledge sources for evidence retrieval,
RAG, explainability, hallucination detection, and citation verification. It does not generate medical
advice. It converts source documents into attributed, metadata-rich, vector-indexed evidence chunks.

## Ingestion Architecture

Core package: `packages/retrieval/src/clinical_ai_retrieval`

```text
DocumentLoader
  -> LoadedDocument
  -> DocumentProcessor
  -> EvidenceDocument + EvidenceMetadata
  -> TextChunker + Citation
  -> EmbeddingProvider
  -> VectorIndexingPipeline
  -> QdrantVectorStore
```

The ingestion path is intentionally separate from online retrieval:

- loaders know how to read source files or records;
- processors know how to normalize source metadata;
- chunking knows how to split source text while preserving attribution;
- embedding/indexing knows how to generate vectors and upsert into Qdrant;
- attribution tracking knows how to verify citations later.

This separation lets PubMed, NICE guidelines, synthetic hospital protocols, and local policy
documents evolve independently while preserving one retrieval contract.

## Knowledge Sources

Initial sources:

- PubMed abstracts from JSON records.
- NICE guidelines from text, Markdown, or JSON directories.
- Synthetic hospital protocols from local files.
- Clinical policy documents from local files.

Implemented loaders:

- `JsonRecordLoader`: reads JSON lists, single objects, or `{ "records": [...] }` payloads.
- `TextFileLoader`: reads `.txt` or `.md` source files.
- `DirectoryLoader`: scans directories for `.txt`, `.md`, and `.json` files.

Implemented processors:

- `PubMedAbstractProcessor`
- `NiceGuidelineProcessor`
- `SyntheticProtocolProcessor`
- `ClinicalPolicyProcessor`

All processors emit `EvidenceDocument` objects with normalized `EvidenceMetadata`.

## Metadata Schema

Metadata is defined by `EvidenceMetadata` and includes:

- source type and source ID;
- title, URL, authors, publication year;
- guideline organization and jurisdiction;
- protocol version and source version;
- clinical domains;
- evidence level;
- section path;
- citation ID and citation text;
- local development fields such as synthetic patient or encounter IDs.

Metadata matters because vector similarity alone is not enough for clinical retrieval. A semantically
similar passage can be unsafe if it comes from the wrong jurisdiction, outdated guideline, synthetic
protocol, or unrelated source class. Metadata filters let the retrieval service constrain the search
space before ranking.

## Chunking Strategy

The initial `TextChunker` uses overlapping character windows:

- default size: 1,800 characters;
- default overlap: 250 characters;
- sentence-boundary preference;
- token estimate stored per chunk;
- citation object attached to every chunk.

Why chunking matters:

- chunks that are too large dilute the embedding and retrieve broad but imprecise passages;
- chunks that are too small lose clinical context such as contraindications, population limits, or
  recommendation strength;
- overlap reduces boundary loss when a key concept crosses chunk edges;
- section-aware chunking improves citation quality and explainability.

Recommended future chunking refinements:

- PubMed: abstract-section chunks for Background, Methods, Results, Conclusions when available.
- NICE: recommendation-level chunks with section headings preserved.
- Protocols: step/rule-level chunks with inclusion and exclusion criteria kept together.
- Policy documents: policy clause chunks with version and jurisdiction metadata.

## Indexing Workflow

`KnowledgeIngestionPipeline.ingest()` performs:

1. Resolve the correct `DocumentLoader` for the source type.
2. Load source content into `LoadedDocument`.
3. Process source metadata into `EvidenceDocument`.
4. Chunk text and attach `Citation` records.
5. Embed chunk text through the configured `EmbeddingProvider`.
6. Upsert vectors and payload into Qdrant.
7. Return `IngestionResult` with indexed counts, citations, and failures.

The current embedding provider is sentence-transformers. Hosted OpenAI, Gemini, Azure, or private
embedding services can implement the same provider interface later.

## Source Attribution

Every chunk receives a `Citation` with:

- citation ID;
- source type;
- source ID;
- title;
- URL;
- publication year;
- section path;
- quote preview;
- formatted attribution text.

`SourceAttributionTracker` converts retrieval results into citations and verifies claimed citation
IDs against the retrieved set. This supports:

- answer citation validation;
- hallucination detection;
- evidence traceability;
- explainability views that show which retrieved chunks influenced a response.

## Observability Hooks

`RetrievalObserver` includes hooks for:

- ingestion source URI, source type, document count, and failure count;
- indexing collection, document ID, chunk count, and embedding model;
- retrieval query length, result count, embedding model, and filter usage.

The package ships with `NoopRetrievalObserver`; API routes, workers, or schedulers can provide a
platform observer that emits structured logs, metrics, or OpenTelemetry spans.

## Failure Handling

Failures are represented as `IngestionFailure` objects:

- source URI;
- stage: load, process, or index;
- error type;
- message;
- recoverability flag.

The pipeline defaults to `continue_on_error=True`, which allows one bad document to be recorded
without stopping the full ingestion job. For regulated batch releases, set `continue_on_error=False`
and fail closed.

Failure design goals:

- never silently drop source content;
- preserve enough context for audit and retry;
- distinguish source loading errors from processing and vector-indexing errors;
- support partial success for large document collections.

## Retrieval Quality Tradeoffs

Clinical retrieval quality depends on both semantic matching and source controls:

- High recall is useful for exploratory evidence review, but can surface weak or stale evidence.
- High precision is safer for point-of-care explanation, but can miss useful adjacent evidence.
- Filters improve safety but can hide relevant information if metadata is incomplete.
- Reranking improves top-k quality but adds latency and another model dependency.
- Hybrid lexical/vector search is important for drug names, trial IDs, guideline IDs, acronyms, and
  rare conditions.

## Medical Retrieval Considerations

Production medical retrieval should:

- separate synthetic/local patient-linked material from public evidence collections;
- version indexes by source release and embedding model;
- record source provenance and citation metadata for every retrieved chunk;
- prefer guideline and policy filters when the user asks for operational recommendations;
- expose evidence level and source age to downstream safety checks;
- keep contraindications, scope, and population criteria in the same chunk where possible;
- use human review and governance for curated guideline or policy ingestion.

This pipeline creates the foundation for evidence-grounded AI without pretending vector similarity is
clinical truth. The downstream system still needs source ranking, safety evaluation, clinical review,
and citation-aware answer generation.
