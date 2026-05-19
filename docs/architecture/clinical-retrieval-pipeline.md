# Clinical Retrieval Pipeline

The clinical retrieval pipeline packages evidence for downstream RAG, reliability analysis,
explainability, hallucination detection, and citation verification. It retrieves evidence; it does not
diagnose or make clinical decisions.

## Retrieval Architecture

```text
RetrievalQuery
  -> Dense retrieval via sentence-transformers + Qdrant
  -> BM25 lexical retrieval
  -> Hybrid fusion
  -> Cross-encoder reranking
  -> Reliability and confidence scoring
  -> Citation grounding
  -> EvidencePackage
```

Implemented modules:

- `VectorRetrievalService`: orchestration service.
- `BM25Retriever`: lexical retrieval for exact terms, acronyms, drug names, and guideline IDs.
- `QdrantVectorStore`: dense retrieval over embedded chunks.
- `CrossEncoderReranker`: sentence-transformers cross-encoder reranking.
- `fuse_results()`: weighted fusion now, reciprocal rank fusion path included.
- `SourceAttributionTracker`: citation extraction and claimed-citation verification.
- `RetrievalEvaluator`: evaluation hook for expected source and citation hits.

## Retrieval Services

`VectorRetrievalService.retrieve_evidence()` returns an `EvidencePackage` with:

- ranked evidence items;
- citations;
- scoring components;
- confidence scores;
- source reliability scores;
- diagnostics about dense count, BM25 count, reranking, filters, and reliability notes.

The older `retrieve()` method remains as a compatibility path and returns `RetrievalResult` objects.

## Dense Retrieval

Dense retrieval uses sentence-transformers embeddings and Qdrant vector search. Dense retrieval is
good at semantic similarity, synonyms, and natural language clinical questions, but it can miss exact
identifiers or over-retrieve passages that sound clinically similar while differing in scope.

## BM25 Support

`BM25Retriever` provides in-memory lexical retrieval over `EvidenceDocument` objects. It is suitable
for local corpora, test fixtures, synthetic protocols, and smaller policy sets. Production-scale BM25
can be swapped for OpenSearch, Elasticsearch, PostgreSQL full-text search, or another lexical engine
behind the same service boundary.

BM25 helps with:

- drug names;
- lab names;
- guideline IDs;
- acronyms;
- rare conditions;
- exact policy phrases.

## Hybrid Retrieval And Fusion

Hybrid retrieval combines dense and lexical candidates. The active fusion strategy is weighted sum:

```text
final_score = dense_weight * dense_score + bm25_weight * bm25_score
```

The schema also supports `RECIPROCAL_RANK_FUSION`, which is implemented as a strategy path and can be
tuned later. RRF is useful when dense and lexical score scales are difficult to calibrate.

## Reranker Integration

`CrossEncoderReranker` uses a sentence-transformers cross-encoder over `(query, chunk)` pairs.

Reranking benefits:

- improves top-k precision after broad candidate retrieval;
- catches query-passage alignment better than vector distance alone;
- helps when two chunks are semantically close but only one directly answers the query;
- provides a separate relevance signal for confidence scoring.

Tradeoff: reranking adds latency and model cost. Use larger candidate limits for better quality, but
watch request latency and batch size.

## Evidence Packaging

`EvidencePackage` is the response contract for evidence-grounded AI:

- `evidence`: ranked chunks with citation, metadata, final score, confidence, and scoring components;
- `citations`: source attribution records;
- `diagnostics`: retrieval mode, fusion strategy, filter usage, reranking flag, reliability notes;
- `confidence_score`: package-level confidence average.

This format preserves source attribution for explainability and gives future hallucination detection
a concrete set of allowed citation IDs.

## Scoring Pipeline

The scoring pipeline combines:

- dense similarity score;
- BM25 lexical score;
- optional cross-encoder rerank score;
- source reliability prior;
- evidence-level boost;
- staleness penalty for older sources.

Source reliability priors currently rank guideline and local policy sources above PubMed abstracts,
with synthetic protocols and imaging metadata treated as lower-authority context unless filtered
explicitly.

## Retrieval Evaluation Hooks

`RetrievalEvaluator` supports basic offline evaluation:

- expected source ID hit rate;
- expected citation ID hit rate;
- package confidence threshold;
- pass/fail result for regression tests.

Future evaluation can add nDCG, MRR, recall@k, precision@k, source-type calibration, contradiction
checks, and human-reviewed relevance labels.

## Observability Integration

`RetrievalObserver.record_search()` captures:

- collection name;
- query length;
- result count;
- embedding model;
- filter usage;
- retrieval mode;
- reranking flag.

API routes or workers can implement this protocol with structured logs, metrics, or OpenTelemetry
spans. The retrieval package keeps observability injectable so it can run in API requests, background
jobs, and evaluation harnesses.

## Retrieval Reliability Concepts

Clinical retrieval should be judged by more than similarity:

- **Provenance**: every chunk must identify its source.
- **Authority**: guidelines and policies should usually outrank weak or synthetic evidence.
- **Freshness**: older evidence may need penalties or explicit warnings.
- **Scope fit**: recommendations only apply to the populations and contexts they describe.
- **Citation integrity**: generated answers should only cite retrieved, verified citations.
- **Filter correctness**: jurisdiction, source type, domain, and patient/synthetic boundaries matter.
- **Uncertainty**: low-confidence retrieval should trigger cautious downstream behavior.

## Medical Evidence Grounding Strategies

- Prefer metadata filters for source class when the workflow requires guidelines, policy, or local
  protocols.
- Preserve section paths and citation IDs through retrieval and answer generation.
- Keep contraindications, inclusion criteria, and population limits in the same chunk where possible.
- Use BM25 for exact medical terms and dense search for broader clinical language.
- Use reranking for high-stakes workflows before evidence is passed to an answer generator.
- Keep synthetic protocols clearly labeled so they cannot masquerade as authoritative clinical
  guidance.
- Pass `EvidencePackage.citations` to hallucination detectors as the allowed citation set.

The goal is not to make vector search look certain. The goal is to expose enough retrieval evidence,
scores, citations, and diagnostics for downstream AI systems and humans to judge reliability.
