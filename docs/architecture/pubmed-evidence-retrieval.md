# PubMed Evidence Retrieval Integration

PubMed ingestion adds biomedical literature evidence to the retrieval layer so downstream agents can
produce evidence-grounded recommendations, explainability traces, citation verification,
hallucination detection, and future Safety Critic validation. PubMed evidence should be treated as
research evidence, not automatically as operational clinical guidance. Guidelines and local policy
remain higher-authority sources for direct recommendations unless a workflow explicitly asks for
literature review.

The current retrieval package already includes a PubMed source type, JSON record loader, and
`PubMedAbstractProcessor`. This design extends that path into a production-ready ingestion and
retrieval workflow.

## PubMed Retrieval Challenges

PubMed retrieval is harder than general document retrieval because abstracts are compact,
terminology-rich, and often conditional. A semantically similar abstract can differ in population,
study design, comparator, endpoint, time period, intervention dose, or statistical certainty.

Common risks:

- abstract conclusions may overstate findings or omit limitations from the full text;
- MeSH terms, acronyms, genes, drugs, and disease names create lexical ambiguity;
- older studies may be superseded by newer reviews or guidelines;
- single studies should not outrank current clinical guidelines for operational recommendations;
- titles and abstracts may mention outcomes without supporting a recommendation;
- PMID-level citation is not enough when an answer makes a specific claim from a specific abstract
  sentence or section.

The platform should therefore retrieve PubMed as citeable evidence with clear reliability metadata,
not as free-floating clinical truth.

## PubMed Ingestion Architecture

```text
PubMed query or export
  -> PubMed fetch/import job
  -> Raw PubMed record JSON
  -> PubMedAbstractProcessor
  -> abstract normalization
  -> metadata extraction
  -> citation construction
  -> EvidenceDocument
  -> biomedical-aware chunking
  -> embedding + BM25 indexing
  -> Qdrant payload upsert
  -> ingestion observability events
```

Recommended components:

- **PubMed source adapter**: imports PubMed records from an offline JSON export initially, with a
  future NCBI E-utilities fetcher behind the same loader boundary.
- **Raw record store**: persists immutable source records by PMID and retrieval date for audit and
  re-indexing.
- **Abstract processor**: normalizes titles, structured abstract sections, author lists, journal
  metadata, publication dates, MeSH terms, article types, and DOI/PMCID links.
- **Citation builder**: produces stable citation IDs and attribution text for each abstract and
  section-level chunk.
- **Biomedical chunker**: keeps title, objective, methods, results, and conclusions boundaries when
  available.
- **Indexing pipeline**: embeds retrieval-ready text, builds lexical indexes for exact biomedical
  terms, and stores provenance-rich payloads.
- **Reliability scorer**: treats PubMed as medium-authority evidence whose score depends on article
  type, recency, provenance completeness, and applicability.

## Metadata Schema

PubMed should populate the existing `EvidenceMetadata` fields and store PubMed-specific values in
`extra` until they graduate into first-class schema fields.

Core fields:

| Field | Value |
| --- | --- |
| `source_type` | `pubmed` |
| `source_id` | PMID as a string |
| `title` | Article title |
| `url` | `https://pubmed.ncbi.nlm.nih.gov/{pmid}/` |
| `authors` | Normalized author names |
| `publication_year` | Article publication year |
| `clinical_domains` | Curated domains or inferred tags |
| `evidence_level` | Derived from article type when available |
| `citation_id` | `pubmed:{pmid}` or section-specific ID |
| `citation_text` | Human-readable attribution |
| `source_version` | PubMed import batch or record revision date |
| `section_path` | `["Abstract"]`, `["Abstract", "Results"]`, etc. |
| `extra` | Journal, DOI, PMCID, MeSH terms, article types, language, publication date |

Recommended `extra` keys:

```json
{
  "pmid": "12345678",
  "doi": "10.1000/example",
  "pmcid": "PMC123456",
  "journal": "Example Journal of Medicine",
  "publication_date": "2025-04-18",
  "article_type": "Randomized Controlled Trial",
  "mesh_terms": "sepsis; emergency service, hospital; biomarkers",
  "language": "eng",
  "publication_status": "published",
  "pubmed_import_batch": "pubmed-sepsis-2026-05-20"
}
```

Evidence level mapping:

| PubMed signal | `evidence_level` |
| --- | --- |
| Systematic Review, Meta-Analysis | `systematic_review` |
| Randomized Controlled Trial | `randomized_trial` |
| Clinical Trial | `clinical_trial` |
| Observational Study, Cohort, Case-Control | `observational_study` |
| Case Reports | `case_report` |
| Review without systematic label | `narrative_review` |
| Missing or unclear article type | `unclassified_pubmed` |

## Abstract Normalization

Normalize abstracts before chunking and indexing so both dense and lexical retrieval see stable,
meaningful text.

Normalization steps:

1. Preserve the original raw PubMed record in the raw record store.
2. Normalize Unicode punctuation, whitespace, HTML entities, and XML artifacts.
3. Keep the title as a separate leading field, not just metadata.
4. Preserve structured abstract labels such as `Background`, `Objective`, `Methods`, `Results`, and
   `Conclusions`.
5. Standardize section names while retaining the original label in metadata if needed.
6. Remove boilerplate copyright notices from retrieval text but retain licensing metadata separately.
7. Normalize author names and journal names without inventing missing fields.
8. Detect empty, truncated, non-English, or publication-type-only records and mark them as low
   retrieval quality.
9. Preserve statistical details, confidence intervals, comparators, and sample sizes exactly in the
   retrieval text.

Retrieval-ready abstract format:

```text
Title: Early biomarker-guided assessment for suspected sepsis in emergency care
PMID: 12345678
Journal: Example Journal of Medicine
Publication year: 2025
Article type: Randomized Controlled Trial

Abstract > Background:
...

Abstract > Methods:
...

Abstract > Results:
...

Abstract > Conclusions:
...
```

Do not rewrite biomedical claims during normalization. The normalizer may clean formatting, but it
must not summarize, strengthen, weaken, or infer conclusions.

## Citation Handling

Citation integrity is a safety feature. Every retrieved PubMed chunk must carry enough citation data
for answer generation, citation verification, explainability, hallucination detection, and future
Safety Critic validation.

Citation ID strategy:

- PMID-level document citation: `pubmed:{pmid}`.
- Section-level citation: `pubmed:{pmid}:abstract-results`.
- Chunk-level citation when section chunks split further: `pubmed:{pmid}:abstract-results:{index}`.

Citation payload:

```json
{
  "citation_id": "pubmed:12345678:abstract-results",
  "source_type": "pubmed",
  "source_id": "12345678",
  "title": "Early biomarker-guided assessment for suspected sepsis in emergency care",
  "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
  "publication_year": 2025,
  "section_path": ["Abstract", "Results"],
  "quote": "The cited chunk preview is copied from the normalized abstract text.",
  "attribution_text": "Smith A, Jones B. Early biomarker-guided assessment for suspected sepsis in emergency care. Example Journal of Medicine. 2025. PubMed PMID: 12345678."
}
```

Rules:

- Generated answers may only cite citation IDs present in `EvidencePackage.citations`.
- A citation should support the specific sentence it is attached to, not merely come from the same
  article.
- Abstract conclusions should not be cited for numerical result claims unless the result is present in
  the cited chunk.
- The Safety Critic should receive both citation IDs and citation quotes so it can check whether the
  final recommendation is supported, overstated, contradicted, or weakly grounded.
- DOI and PMCID should be logged as provenance, but PMID remains the stable PubMed source ID.

## Indexing Workflow

Offline ingestion should be deterministic and replayable.

1. Define an import manifest with PubMed query, date range, domain, source owner, and batch ID.
2. Fetch or load PubMed records into raw JSON.
3. Validate required fields: PMID, title, abstract or explicit no-abstract flag, publication year.
4. Normalize abstract text and structured sections.
5. Extract metadata into `EvidenceMetadata`.
6. Build stable `EvidenceDocument.document_id` as `pubmed:{pmid}`.
7. Chunk by abstract section first; fall back to sentence-aware windows for unstructured abstracts.
8. Attach citations to every chunk.
9. Embed chunk text with the configured `EmbeddingProvider`.
10. Upsert to Qdrant using deterministic chunk IDs.
11. Index the same normalized documents into BM25 for exact biomedical terms.
12. Emit ingestion, indexing, quality, and failure events.
13. Produce a batch report with indexed counts, skipped records, failures, and quality warnings.

Suggested manifest:

```json
{
  "batch_id": "pubmed-sepsis-2026-05-20",
  "source_type": "pubmed",
  "query": "sepsis emergency department biomarker randomized trial",
  "date_range": {
    "from": "2020-01-01",
    "to": "2026-05-20"
  },
  "clinical_domains": ["sepsis", "emergency_medicine"],
  "language": "eng",
  "imported_at": "2026-05-20T09:00:00Z"
}
```

## Biomedical NLP Considerations

Biomedical text requires lexical precision and metadata-aware ranking.

Considerations:

- Preserve exact drug names, gene symbols, study acronyms, trial names, dosage units, and lab units.
- Use BM25 or another lexical engine alongside dense retrieval for exact identifiers and rare terms.
- Keep abbreviations close to their expansions when present in the abstract.
- Avoid aggressive stemming that conflates clinically distinct concepts.
- Normalize common Greek letters and symbols while preserving the original token in text when
  possible.
- Treat negation carefully: "no significant reduction" and "significant reduction" should not embed
  as equivalent evidence.
- Preserve comparators and endpoints: intervention evidence is incomplete without what it was
  compared against and what outcome was measured.
- Track article type because a review, RCT, observational study, and case report should not receive
  the same reliability prior.
- Detect animal-only, in-vitro, pediatric, pregnancy-specific, or adult-only populations so retrieval
  can filter or qualify applicability.

## Chunking Biomedical Literature

Chunking should preserve claim context. Biomedical abstracts often pack population, intervention,
comparator, outcome, and conclusion into separate sentences. Splitting too aggressively creates
evidence fragments that sound stronger than the source.

Preferred strategy:

- one chunk for short unstructured abstracts under the max size;
- section-level chunks for structured abstracts;
- include the article title and PMID in every chunk prefix;
- keep `Methods` with population and design details;
- keep `Results` with numerical outcomes and uncertainty;
- keep `Conclusions` with source-authored interpretation;
- use overlap only within long sections, not across unrelated abstract sections;
- preserve section path in citation metadata.

Example chunk text:

```text
Title: Early biomarker-guided assessment for suspected sepsis in emergency care
PMID: 12345678
Article type: Randomized Controlled Trial
Section: Abstract > Results

Results: ...
```

Chunking failure modes:

- result numbers separated from comparator or endpoint;
- conclusion chunk retrieved without methods or population;
- pediatric and adult cohorts mixed in one chunk;
- old review conclusions retrieved without publication year visible;
- PMID citation preserved but section identity lost.

## Retrieval Optimization

PubMed retrieval should be optimized for literature evidence and source controls.

Dense retrieval:

- use biomedical-domain embeddings when available and validated against the evaluation suite;
- include title, article type, and section label in embedded text;
- keep source-specific collections or payload filters for public literature vs local/synthetic data.

Lexical retrieval:

- index PMID, DOI, trial acronym, drug names, MeSH terms, journal, and title tokens;
- boost exact PMID and DOI matches;
- boost exact phrase matches for drug names, conditions, and study acronyms;
- avoid losing hyphenated biomedical terms during tokenization.

Hybrid fusion:

- use BM25 to recover exact biomedical entities;
- use dense retrieval for synonymy and broader clinical language;
- use reciprocal rank fusion when dense and lexical scores are poorly calibrated;
- rerank high-stakes requests with a cross-encoder or biomedical reranker.

Reliability ranking:

- systematic reviews and meta-analyses should generally outrank single trials when the question asks
  for evidence summary;
- current guidelines and local policy should outrank PubMed abstracts when the question asks what to
  recommend operationally;
- stale, non-human, case-report, or low-provenance abstracts should receive penalties;
- contradictory abstracts should be surfaced for literature review questions but should lower
  answer confidence if the final answer ignores the conflict.

## Observability Integration

PubMed ingestion and retrieval should emit structured events through the platform observability
layer. Avoid logging raw abstract text in normal logs; log stable IDs and quality summaries.

Ingestion events:

```json
{
  "event": "pubmed_ingestion_completed",
  "batch_id": "pubmed-sepsis-2026-05-20",
  "source_type": "pubmed",
  "records_loaded": 500,
  "records_indexed": 482,
  "records_skipped": 18,
  "chunks_indexed": 933,
  "failure_count": 3,
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "collection_name": "clinical_ai_evidence_384"
}
```

Record quality warning:

```json
{
  "event": "pubmed_record_quality_warning",
  "batch_id": "pubmed-sepsis-2026-05-20",
  "pmid": "12345678",
  "warning_type": "missing_structured_abstract",
  "indexed": true
}
```

Retrieval trace fields:

- `pmid`;
- `citation_id`;
- `article_type`;
- `publication_year`;
- `evidence_level`;
- `section_path`;
- `dense_score`;
- `bm25_score`;
- `rerank_score`;
- `source_reliability_score`;
- `confidence_score`;
- `query_clinical_domain`;
- `retrieval_mode`;
- `filter_usage`.

Safety event fields:

- unsupported PMID citations;
- cited abstract section;
- hallucination risk band;
- contradiction source IDs;
- Safety Critic verdict;
- final answer action: allow, qualify, abstain, or block.

## Support For Downstream Safety

PubMed evidence should flow into downstream systems as structured evidence, not plain context.

Evidence-grounded recommendations:

- answer generators receive ranked `RetrievalEvidenceItem` objects with citations and source
  reliability;
- recommendation prompts should distinguish guideline/policy evidence from research literature;
- PubMed-only evidence should usually produce cautious language unless the workflow is explicitly
  literature review.

Explainability:

- every answer sentence can point to a PMID, section path, and quote preview;
- UI traces can show source type, evidence level, publication year, and article type;
- retrieval diagnostics can explain why PubMed evidence ranked below guidelines or local policy.

Citation verification:

- `SourceAttributionTracker` verifies claimed citation IDs against retrieved citations;
- citation faithfulness evaluation checks that the cited sentence is supported by the cited abstract
  chunk;
- invalid, missing, or mismatched PubMed citations should lower confidence or block answers.

Hallucination detection:

- hallucination detectors compare generated biomedical claims against retrieved PubMed chunks;
- unsupported mechanism, dosage, population, or outcome claims are flagged;
- overconfident recommendations from weak PubMed evidence are treated as higher risk.

Future Safety Critic validation:

- Safety Critic receives the answer, retrieval package, citation allow-list, reliability scores, and
  contradiction notes;
- it checks whether recommendations exceed the strength of the evidence;
- it flags missing guideline evidence when PubMed evidence is being used operationally;
- it can require human review when PubMed evidence conflicts or citation faithfulness fails.

## Acceptance Criteria

Initial integration should satisfy:

- PubMed records ingest from JSON with stable PMID-based document IDs.
- Abstracts preserve title, PMID, article type, section labels, and publication year in retrieval
  text.
- Metadata includes PMID, title, authors, URL, publication year, article type, evidence level, and
  citation ID.
- Every indexed chunk has a citation with PMID, section path, quote preview, and attribution text.
- Hybrid retrieval can recover articles by PMID, title terms, MeSH terms, drug names, and clinical
  paraphrases.
- Retrieval results expose source reliability and evidence level to answer generation and Safety
  Critic workflows.
- Observability records ingestion counts, quality warnings, failures, collection name, and retrieval
  score components.
- Citation verification can reject PubMed citation IDs that were not retrieved in the current
  `EvidencePackage`.
