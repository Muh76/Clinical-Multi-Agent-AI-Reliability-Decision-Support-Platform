# Clinical Retrieval Evaluation Framework

This framework evaluates whether retrieved clinical evidence is reliable, relevant, citeable, and
safe enough to support downstream reliability analysis. It is not a generic RAG scorecard. The goal
is to measure evidence quality, citation grounding, hallucination risk, and retrieval robustness
before generated clinical text is trusted by a user or another agent.

The platform should evaluate retrieval as a clinical evidence supply chain:

```text
Gold QA case
  -> query generation
  -> dense retrieval
  -> BM25 retrieval
  -> hybrid fusion
  -> reranking
  -> evidence reliability scoring
  -> answer and citation generation
  -> grounding evaluation
  -> confidence calibration
  -> regression report
```

## Why Evaluation Matters

Clinical retrieval failures can look persuasive. A passage may be semantically similar, come from a
real source, and still be wrong for the patient population, outdated, contradicted by higher-authority
guidance, or misquoted by the generated answer. Evaluation needs to catch those failures before they
become hidden assumptions in clinical decision support.

Healthcare retrieval is difficult because clinical language is dense, abbreviation-heavy, and
context-sensitive. Drug names, guideline IDs, contraindications, age bands, pregnancy status,
renal function, severity thresholds, and local policy constraints can change whether evidence applies.
Semantic similarity alone is not enough.

Retrieval reliability is critical because every downstream safety mechanism depends on the evidence
package. If the retrieval layer misses the governing guideline, over-ranks weak evidence, hides
contradictions, or emits unverifiable citations, hallucination detectors and answer generators inherit
a distorted view of the clinical record.

## Evaluation Architecture

Core components:

- **Case registry**: versioned gold QA cases with expected evidence, acceptable citations, exclusion
  evidence, contradiction sets, and patient/context constraints.
- **Corpus snapshot registry**: immutable index snapshots with source versions, chunk IDs, embedding
  model, chunking strategy, and metadata schema version.
- **Retrieval runner**: executes dense, BM25, hybrid, filtered, and reranked retrieval against the
  same case set.
- **Evidence evaluator**: scores relevance, authority, freshness, scope fit, contradiction handling,
  and source reliability.
- **Citation evaluator**: verifies that every cited claim maps to retrieved text and that citation IDs
  exist in the `EvidencePackage.citations` allow-list.
- **Grounding evaluator**: checks whether answer claims are supported, partially supported,
  contradicted, or unsupported by retrieved evidence.
- **Robustness evaluator**: runs paraphrases, spelling variants, abbreviation variants, noisy context,
  missing filters, and adversarial distractors.
- **Confidence calibrator**: compares predicted retrieval confidence with observed correctness,
  producing calibration curves and operating thresholds.
- **Evaluation logger**: stores query inputs, corpus versions, scores, failure labels, and cited
  evidence traces for regression analysis.

Recommended execution modes:

- **Pull request gate**: small deterministic suite for retrieval regressions.
- **Nightly benchmark**: full case suite across source types and clinical domains.
- **Corpus release benchmark**: required before promoting a new corpus snapshot.
- **Model release benchmark**: required before changing embedding, reranker, or answer model.
- **Incident replay**: rerun production failure cases after fixes.

## Evaluation Datasets

Use multiple datasets because one benchmark cannot test clinical retrieval reliability by itself.

| Dataset | Purpose | Example sources |
| --- | --- | --- |
| Guideline QA | Tests authoritative recommendation retrieval | NICE, local policy, society guidelines |
| PubMed evidence QA | Tests research evidence retrieval and evidence-level ranking | Abstracts, reviews, trial summaries |
| Local protocol QA | Tests jurisdiction, hospital, and pathway constraints | Synthetic local policies |
| Patient-context QA | Tests whether retrieval respects age, pregnancy, renal function, encounter, and modality filters | Synthetic/de-identified fixtures |
| Citation QA | Tests citation ID integrity and quote/claim alignment | Curated answer-citation pairs |
| Contradiction QA | Tests competing evidence and source-priority behavior | Old vs new guidelines, trial vs guideline |
| Robustness QA | Tests query perturbation stability | Paraphrases, typos, acronyms, abbreviations |
| Negative QA | Tests abstention and low-confidence behavior | Questions with no indexed answer |

Dataset labels should include:

- gold relevant chunk IDs;
- acceptable source IDs;
- required citation IDs;
- unacceptable source IDs;
- source authority tier;
- evidence freshness expectations;
- patient/context applicability constraints;
- known contradictory evidence IDs;
- expected abstention behavior when evidence is missing.

## Gold QA Schema

Each gold case should be a single JSON object. Keep the schema source-aware and citation-aware, not
just question-answer based.

```json
{
  "case_id": "sepsis-adult-initial-assessment-ng51-001",
  "version": "2026-05-20",
  "clinical_domain": ["sepsis", "emergency_medicine"],
  "task_type": "guideline_retrieval",
  "question": "What evidence should support initial assessment of an adult with suspected sepsis?",
  "patient_context": {
    "age_years": 72,
    "pregnancy_status": "not_applicable",
    "setting": "emergency_department",
    "jurisdiction": "UK"
  },
  "retrieval_filters": {
    "source_types": ["nice_guideline", "local_policy"],
    "jurisdiction": "UK"
  },
  "gold_answer_summary": "Retrieve current adult suspected sepsis recognition and escalation guidance.",
  "must_retrieve": [
    {
      "source_id": "NICE-NG51",
      "chunk_id": "nice-ng51-adult-risk-stratification",
      "citation_id": "NICE-NG51:adult-risk-stratification",
      "relevance_grade": 3,
      "authority_tier": "guideline",
      "required": true
    }
  ],
  "acceptable_evidence": [
    {
      "source_id": "LOCAL-SEPSIS-POLICY-2026",
      "chunk_id": "local-sepsis-escalation-pathway",
      "citation_id": "LOCAL-SEPSIS-POLICY-2026:escalation"
    }
  ],
  "excluded_evidence": [
    {
      "source_id": "SYNTH-SEPSIS-DEMO",
      "reason": "synthetic development protocol cannot be treated as clinical authority"
    }
  ],
  "contradictions": [
    {
      "source_id": "OLD-SEPSIS-POLICY-2018",
      "chunk_id": "old-sepsis-screening-threshold",
      "expected_handling": "retrieve_only_with_staleness_warning_or_downrank"
    }
  ],
  "grounding_claims": [
    {
      "claim_id": "claim-001",
      "claim": "The answer should distinguish adult suspected sepsis guidance from pediatric guidance.",
      "supporting_citation_ids": ["NICE-NG51:adult-risk-stratification"],
      "must_not_cite": ["NICE-NG51:pediatric-section"]
    }
  ],
  "expected_behavior": {
    "min_recall_at_10": 1.0,
    "min_citation_faithfulness": 0.95,
    "allow_abstention": false
  }
}
```

## Retrieval Metrics

Evaluate retrieval before reranking and after fusion so regressions can be isolated.

- **Recall@K**: fraction of required gold evidence retrieved in the top K.
- **Precision@K**: fraction of top K results judged clinically relevant.
- **MRR**: reciprocal rank of the first required gold evidence item.
- **NDCG@K**: ranking quality using graded relevance labels, for example 0 irrelevant, 1 adjacent,
  2 relevant, 3 essential.
- **Source hit rate**: whether any acceptable source ID appears in top K.
- **Citation hit rate**: whether required citation IDs appear in top K.
- **Authority-weighted recall**: recall weighted by evidence authority tier.
- **Filtered retrieval correctness**: whether jurisdiction, source type, patient, encounter, and
  date filters exclude inappropriate evidence.
- **Negative-case abstention rate**: proportion of no-answer cases where retrieval confidence stays
  below the answer threshold.

Clinical interpretation:

- High Recall@K with poor NDCG means the right evidence is present but buried.
- High semantic scores with low evidence relevance means the retriever is matching clinical language
  without answering the actual question.
- Good source hit rate with poor citation hit rate means the system found the document but not the
  precise citeable passage.

## Reranking Metrics

Reranking should improve clinical applicability, not merely semantic polish.

- **Delta NDCG@K**: NDCG after reranking minus NDCG before reranking.
- **Delta MRR**: first required evidence rank improvement.
- **Top-1 essential evidence rate**: whether the highest-ranked item is essential evidence.
- **Authority promotion rate**: frequency that guidelines/local policies move above lower-authority
  abstracts when both are relevant.
- **Distractor demotion rate**: frequency that semantically similar but inapplicable chunks move down.
- **Contradiction surfacing rate**: whether known contradictory evidence remains visible when the
  question requires comparison or uncertainty.
- **Latency-normalized gain**: ranking improvement divided by additional reranker latency.

Reranker failure labels:

- over-promoted weak source;
- missed exact drug, lab, or guideline ID;
- selected wrong population;
- selected wrong care setting;
- suppressed clinically important contradiction;
- improved text similarity while reducing citation precision.

## Grounding Metrics

Grounding is evaluated against generated answer claims and the retrieved `EvidencePackage`.

- **Citation faithfulness**: proportion of cited claims fully supported by the cited evidence text.
- **Citation validity**: proportion of citations that exist in the retrieved citation allow-list.
- **Citation precision**: proportion of cited evidence that is relevant to the sentence it supports.
- **Claim support rate**: proportion of answer claims supported by retrieved evidence.
- **Unsupported claim rate**: proportion of answer claims with no retrieved support.
- **Contradicted claim rate**: proportion of answer claims contradicted by retrieved evidence.
- **Grounding consistency**: whether multiple answer claims use citations consistently with source
  scope, population, and recommendation strength.
- **Evidence relevance**: graded relevance of each cited evidence item to the clinical question.
- **Quote/summary alignment**: whether a generated summary preserves the meaning, uncertainty, and
  limits of the cited source.

Suggested claim labels:

- `supported`: directly entailed by retrieved evidence;
- `partially_supported`: directionally related but missing limits or qualifiers;
- `contradicted`: conflicts with retrieved evidence;
- `unsupported`: not present in retrieved evidence;
- `mis-cited`: supported somewhere else, but not by the cited passage;
- `overstated`: source is weaker or more conditional than the answer implies.

## Evidence Reliability Evaluation

Evidence reliability should be scored separately from relevance. A result can be relevant but weak,
stale, synthetic, or inapplicable.

Reliability dimensions:

- **Authority**: guideline, local policy, systematic review, trial, observational study, abstract,
  synthetic fixture.
- **Freshness**: publication year, policy version, superseded status, review date.
- **Applicability**: population, setting, jurisdiction, disease stage, modality, encounter.
- **Provenance completeness**: source ID, title, URL, section path, chunk ID, citation ID.
- **Evidence level**: hierarchy or local evidence grade when available.
- **Conflict status**: whether higher-authority or newer evidence contradicts the result.
- **Synthetic boundary**: whether synthetic evidence is clearly labeled and prevented from becoming
  authoritative clinical guidance.

Evidence reliability score:

```text
reliability_score =
  authority_weight
  * freshness_factor
  * applicability_factor
  * provenance_factor
  * contradiction_factor
  * synthetic_boundary_factor
```

The score should be explainable through component fields, not only a scalar.

## Hallucination Risk Evaluation

Hallucination risk is the probability that the answer layer will produce clinically meaningful claims
not justified by retrieved evidence.

Risk signals:

- low Recall@K for required evidence;
- high unsupported claim rate;
- invalid or missing citations;
- citations attached to the wrong sentence;
- answer uses stronger language than the source;
- retrieved evidence contains contradictions not acknowledged by the answer;
- evidence comes mostly from low-authority or stale sources;
- confidence is high despite poor grounding scores;
- no-answer cases produce confident recommendations.

Risk bands:

| Band | Meaning | Expected behavior |
| --- | --- | --- |
| Low | Required evidence retrieved, citations valid, claims supported | Answer may proceed with citations |
| Moderate | Evidence relevant but incomplete, weak, or partially conflicting | Answer should qualify uncertainty |
| High | Missing essential evidence, contradiction unresolved, or citations invalid | Answer should abstain or request review |
| Critical | Unsupported clinical recommendation or synthetic/invalid evidence presented as authority | Block answer and log safety event |

## Confidence Scoring Design

Confidence should combine retrieval, evidence reliability, reranking, and grounding. It should not be
just average similarity.

Recommended components:

```text
retrieval_confidence =
  0.25 * normalized_recall_proxy
  + 0.20 * top_k_relevance_score
  + 0.15 * reranker_agreement
  + 0.15 * source_reliability_score
  + 0.10 * citation_integrity_score
  + 0.10 * filter_correctness_score
  + 0.05 * contradiction_handling_score
```

For answer-level confidence:

```text
answer_confidence =
  retrieval_confidence
  * citation_faithfulness
  * grounding_consistency
  * (1 - hallucination_risk)
```

Calibration requirements:

- Report expected calibration error by clinical domain and source type.
- Tune thresholds on held-out cases, not the development suite.
- Keep separate thresholds for `answer`, `qualify`, `abstain`, and `block`.
- Penalize overconfidence more heavily than underconfidence.
- Log confidence components so clinicians and developers can see why confidence moved.

Example thresholds:

| Confidence | Action |
| --- | --- |
| >= 0.85 | Allow evidence-grounded answer |
| 0.70-0.84 | Allow answer with uncertainty qualifier |
| 0.50-0.69 | Return evidence only or request clarification |
| < 0.50 | Abstain |
| Any critical grounding failure | Block regardless of numeric confidence |

## Synthetic Evaluation Case Strategy

Synthetic cases are useful for deterministic coverage, but they must be explicitly separated from
clinical authority.

Create synthetic cases for:

- exact guideline ID matching;
- misspelled drug and condition names;
- abbreviation expansion;
- wrong population distractors;
- stale policy distractors;
- synthetic protocol boundary tests;
- no-answer abstention;
- contradictory local policy vs outdated source;
- citation ID corruption;
- retrieved evidence with missing provenance.

Generation approach:

1. Define a clinical scenario template with domain, population, setting, and jurisdiction.
2. Create one authoritative synthetic policy chunk with stable citation IDs.
3. Create two to five distractor chunks that differ by population, age band, care setting, or version.
4. Create paraphrased queries and noisy user questions.
5. Label must-retrieve, acceptable, excluded, and contradictory evidence.
6. Store every generated case with seed, generator version, and corpus snapshot ID.

Synthetic evaluation should test platform behavior, not clinical truth. Real clinical benchmark cases
should be curated separately by qualified reviewers.

## Edge-Case Evaluation Examples

| Edge case | Query | Expected behavior |
| --- | --- | --- |
| Abbreviation ambiguity | "ACS pathway initial meds" | Retrieve acute coronary syndrome only when context supports it; avoid ambiguous expansion if context is absent |
| Population mismatch | "fever infant 6 weeks assessment" | Prioritize neonatal/infant guidance; demote adult fever guidance |
| Renal contraindication | "antibiotic choice renal impairment suspected UTI" | Retrieve renal dosing or contraindication evidence, not only general UTI guidance |
| Pregnancy constraint | "hypertension treatment pregnant patient" | Retrieve pregnancy-specific guidance; exclude general adult-only recommendations |
| Stale guideline | "sepsis screening threshold policy" | Prefer current policy and flag old policy as stale if retrieved |
| Local jurisdiction | "NICE recommendation for ED sepsis escalation" | Respect UK/NICE filter; avoid unrelated US pathway unless explicitly requested |
| No indexed answer | "rare off-label protocol absent from corpus" | Low confidence and abstention rather than invented guidance |
| Citation mismatch | Answer cites pediatric section for adult recommendation | Mark citation faithfulness and grounding consistency failure |
| Synthetic boundary | Synthetic demo protocol ranks above guideline | Penalize authority and flag reliability failure |

## Contradictory Evidence Examples

Contradiction cases should test whether retrieval exposes conflict and whether confidence drops when
the system cannot resolve it.

Example 1: current guideline vs outdated local protocol

- Query: "What threshold should trigger escalation for suspected sepsis in adults?"
- Current evidence: `LOCAL-SEPSIS-POLICY-2026:escalation`.
- Contradictory evidence: `OLD-SEPSIS-POLICY-2018:screening-threshold`.
- Expected retrieval: both may be retrieved, but current policy ranks higher.
- Expected grounding: answer cites current policy and notes the older protocol is superseded if
  mentioned.

Example 2: adult guidance vs pediatric guidance

- Query: "Initial assessment for a 72-year-old with suspected sepsis."
- Relevant evidence: adult sepsis recognition guidance.
- Contradictory or inapplicable evidence: pediatric sepsis escalation thresholds.
- Expected retrieval: adult evidence top-ranked; pediatric evidence demoted or excluded.
- Expected grounding: no pediatric citation attached to adult recommendation.

Example 3: trial abstract vs guideline recommendation

- Query: "Should the system recommend a medication based on a single positive trial abstract?"
- Relevant evidence: guideline recommendation and trial abstract.
- Contradictory evidence: trial suggests benefit, guideline recommends against routine use.
- Expected retrieval: both visible when contradiction matters.
- Expected confidence: moderate or high hallucination risk if answer states a recommendation without
  acknowledging guideline authority and evidence conflict.

Example 4: synthetic protocol vs real source

- Query: "What is the evidence for escalation in suspected sepsis?"
- Relevant evidence: guideline or local policy.
- Contradictory evidence: synthetic demo protocol with different threshold.
- Expected retrieval: synthetic protocol downranked and labeled non-authoritative.
- Expected grounding: generated answer must not cite synthetic protocol as clinical authority.

## Evaluation Logging Structure

Every evaluation run should produce structured JSONL records and an aggregate report.

Per-run metadata:

```json
{
  "run_id": "eval-2026-05-20T09-00-00Z",
  "suite_id": "retrieval-reliability-nightly",
  "git_sha": "abc123",
  "corpus_snapshot_id": "clinical-corpus-2026-05-20",
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "reranker_model": "cross-encoder-v1",
  "chunking_strategy": "section-aware-v2",
  "started_at": "2026-05-20T09:00:00Z"
}
```

Per-case record:

```json
{
  "run_id": "eval-2026-05-20T09-00-00Z",
  "case_id": "sepsis-adult-initial-assessment-ng51-001",
  "query": "What evidence should support initial assessment of an adult with suspected sepsis?",
  "retrieval_mode": "hybrid",
  "filters": {
    "source_types": ["nice_guideline", "local_policy"],
    "jurisdiction": "UK"
  },
  "top_k": 10,
  "retrieved": [
    {
      "rank": 1,
      "source_id": "NICE-NG51",
      "chunk_id": "nice-ng51-adult-risk-stratification",
      "citation_id": "NICE-NG51:adult-risk-stratification",
      "dense_score": 0.82,
      "bm25_score": 0.71,
      "rerank_score": 0.91,
      "final_score": 0.88,
      "source_reliability_score": 0.96,
      "relevance_grade": 3
    }
  ],
  "metrics": {
    "recall_at_5": 1.0,
    "recall_at_10": 1.0,
    "mrr": 1.0,
    "ndcg_at_10": 0.97,
    "citation_faithfulness": 0.96,
    "evidence_relevance": 0.94,
    "grounding_consistency": 0.95,
    "hallucination_risk": 0.04,
    "retrieval_confidence": 0.91
  },
  "failure_labels": [],
  "expected_action": "allow_answer",
  "observed_action": "allow_answer",
  "passed": true
}
```

Aggregate report fields:

- metric means, medians, and lower percentiles;
- failures by domain, source type, and case type;
- confidence calibration by risk band;
- worst regressions compared with baseline;
- top failure labels;
- latency distribution by retrieval mode;
- examples of unsupported, contradicted, and mis-cited claims.

## Minimum Acceptance Gates

Suggested initial gates for platform development:

- Recall@10 for required evidence >= 0.90 on curated guideline QA.
- MRR >= 0.75 on must-retrieve citation cases.
- NDCG@10 >= 0.80 on graded relevance cases.
- Citation validity >= 0.99.
- Citation faithfulness >= 0.95 on answer-grounding cases.
- Grounding consistency >= 0.90 for high-stakes clinical domains.
- Critical hallucination risk cases blocked at 100 percent.
- Negative QA abstention >= 0.90.
- No synthetic protocol may be ranked as authoritative evidence when real clinical evidence is
  available.

These thresholds should tighten as the corpus, labels, and clinical review process mature.
