# Safety Evaluation Framework

The Safety Evaluation Framework benchmarks clinical AI reliability behavior. It is not generic model
evaluation. It evaluates safety validation, hallucination detection, evidence grounding,
escalation behavior, uncertainty calibration, contradiction handling, unsupported-claim detection,
and robustness under adversarial retrieval and patient-context conditions.

The implementation lives in:

```text
packages/evaluation/src/clinical_ai_evaluation/safety.py
```

## Safety Evaluation Architecture

```text
SafetyBenchmarkDataset
  -> SafetyBenchmarkCase[]
  -> platform safety workflow under test
  -> SafetyPrediction[]
  -> evaluate_safety_benchmark
  -> metrics + confusion counts + robustness slices
  -> SafetyEvaluationReport
```

The framework is designed to evaluate outputs from:

- hallucination detection;
- evidence verification;
- uncertainty scoring;
- escalation logic;
- Safety Critic validation;
- full end-to-end reliability workflows.

## Benchmark Schemas

Core schemas:

- `SafetyBenchmarkDataset`: named benchmark with version, description, cases, and metadata.
- `SafetyBenchmarkCase`: one labeled case with scenario type, claims, evidence, missing
  modalities, retrieval corruption labels, expected escalation, and uncertainty bounds.
- `SafetyBenchmarkClaim`: labeled claim with expected support, citations, contradiction, and
  unsupported-claim flags.
- `SafetyBenchmarkEvidence`: labeled evidence with citation ID, source type, reliability,
  relevance, contradiction flag, and metadata.
- `SafetyPrediction`: normalized platform output for evaluation.
- `SafetyEvaluationReport`: metric results, confusion counts, failed cases, slices, and
  observability payload.

Scenario types:

- supported claim;
- hallucination;
- contradictory evidence;
- missing modality;
- retrieval corruption;
- unsupported claim;
- high uncertainty;
- escalation required.

## Safety Metrics

Safety metrics should measure whether the platform catches unsafe reliability conditions and routes
them correctly.

Implemented metrics:

- hallucination precision;
- hallucination recall;
- unsupported claim detection rate;
- contradiction detection accuracy;
- grounding faithfulness;
- escalation accuracy;
- uncertainty calibration error;
- retrieval corruption detection rate.

Confusion counts are emitted for:

- hallucination;
- escalation;
- contradiction;
- unsupported claim.

## Hallucination Metrics

Hallucination evaluation should distinguish:

- unsupported medical claims;
- fabricated citations;
- real citations attached to unsupported claims;
- claims that ignore contradictory evidence;
- overconfident claims under weak grounding.

Primary metrics:

- **Hallucination precision**: proportion of flagged hallucinations that are true hallucinations.
- **Hallucination recall**: proportion of expected hallucinations that were detected.
- **Unsupported claim detection**: proportion of expected unsupported-claim cases detected.
- **False allow rate**: unsafe hallucination cases allowed without qualification or review.

Precision matters because excess false positives create review fatigue. Recall matters because false
negatives can permit unsafe downstream output.

## Grounding Metrics

Grounding evaluation checks whether claims are supported by cited evidence.

Metrics:

- grounding faithfulness;
- citation validity;
- citation traceability;
- evidence coverage;
- source trust agreement;
- contradiction surfacing rate.

Grounding failures should be sliced by source type, evidence level, patient population, recency,
retrieval mode, and citation formatting path.

## Escalation Metrics

Escalation evaluation checks whether safety signals are converted into the correct operational
action.

Metrics:

- escalation accuracy;
- false allow rate;
- false block rate;
- human-review precision;
- human-review recall;
- qualification accuracy;
- blocking accuracy for critical cases;
- policy threshold sensitivity.

The framework currently evaluates exact expected escalation action:

- allow;
- qualify;
- human review;
- block.

## Uncertainty Evaluation

Uncertainty evaluation checks whether the platform expresses uncertainty in the right direction and
at the right magnitude.

Metrics:

- uncertainty calibration error;
- overconfidence rate;
- underconfidence rate;
- expected calibration error by confidence bin;
- component calibration for retrieval, grounding, modality completeness, risk stability,
  contradiction, and temporal consistency.

The first implementation supports expected uncertainty ranges per case and reports average distance
outside those ranges.

## Edge-Case Testing Framework

Edge-case tests should be curated into scenario families:

- adversarial clinical scenarios;
- contradictory evidence scenarios;
- missing modality scenarios;
- retrieval corruption scenarios;
- unsupported claim scenarios;
- temporal inconsistency scenarios;
- source reliability mismatch scenarios.

Each case should include:

- structured claims;
- retrieved evidence;
- expected citation IDs;
- expected support labels;
- expected contradiction labels;
- expected escalation action;
- expected uncertainty range;
- tags for slicing and regression analysis.

## Synthetic Safety Dataset Strategy

Synthetic safety cases should be explicit, labeled, and non-authoritative.

Generation strategy:

- create a safe control case for every unsafe case;
- preserve citation IDs across claims and evidence;
- introduce one failure mode at a time before composing multiple failures;
- vary modality availability, source reliability, temporal quality, and evidence conflict;
- label expected escalation action and uncertainty range;
- include metadata for scenario family, clinical domain, source type, and perturbation type;
- keep synthetic protocols clearly marked so retrieval systems do not treat them as clinical
  authority.

Minimum labels:

- expected hallucination;
- expected escalation;
- expected supported claim;
- expected contradicted claim;
- expected unsupported claim;
- expected uncertainty range.

## Adversarial Clinical Scenarios

Examples:

- A risk output claims a medication is safe while the evidence only discusses monitoring.
- A claim cites a real PubMed abstract but changes the population from adults to pediatrics.
- A generated risk factor is plausible but absent from patient context and evidence.
- A recommendation-like statement omits uncertainty language from weak evidence.
- An output cites a synthetic protocol as if it were clinical authority.

Expected behavior:

- unsupported or hallucinated claims are detected;
- citation faithfulness drops;
- uncertainty increases;
- escalation requests review or blocking when severity is high.

## Contradictory Evidence Scenarios

Examples:

- One guideline recommends an intervention while another says to avoid it for a subgroup.
- PubMed abstract reports potential benefit while NICE guidance recommends against routine use.
- Local policy conflicts with a general guideline because of operational constraints.
- Evidence contains both recommendation language and contraindication language.

Expected behavior:

- contradiction detection identifies conflict;
- grounding and uncertainty scores reflect conflict;
- escalation requests human review or blocks repeated contradictions.

## Missing Modality Scenarios

Examples:

- Risk analysis references renal safety but labs are missing.
- Trend analysis claims instability with only one timestamped vital.
- Medication risk is assessed without medication timing.
- Imaging-related risk is asserted without imaging metadata.

Expected behavior:

- modality completeness drops;
- uncertainty sources include missing modalities;
- escalation triggers review when required modalities are absent.

## Retrieval Corruption Scenarios

Examples:

- Citation IDs are swapped between evidence chunks.
- Retrieved evidence is topically similar but from the wrong population.
- High-ranked evidence is stale or low reliability.
- Evidence payload is missing while citation IDs remain.
- Contradictory evidence is removed from the retrieval package.

Expected behavior:

- citation traceability or grounding faithfulness fails;
- retrieval confidence or evidence verification confidence drops;
- escalation qualifies, reviews, or blocks depending on severity.

## Why Safety Evaluation Matters

Clinical AI reliability failures can look fluent and credible. A system can retrieve evidence,
format citations, and still make unsupported or unsafe claims. Safety evaluation measures whether
the platform detects those failures before they reach downstream users or automated workflows.

Safety evaluation also creates regression gates. When retrieval, reranking, evidence packaging,
Safety Critic logic, or escalation thresholds change, the benchmark should reveal whether safety
behavior improved or degraded.

## Enterprise Reliability Testing

Enterprise reliability testing requires:

- repeatable benchmark datasets;
- stable schemas and labels;
- metric history over time;
- scenario slicing;
- audit artifacts;
- policy threshold tests;
- failure triage workflows;
- dashboards for safety trends.

Benchmarks should run in continuous integration and in scheduled offline evaluations against larger
scenario sets.

## Trustworthy AI Evaluation Concepts

Trustworthy AI evaluation should measure more than answer quality. It should measure:

- provenance preservation;
- evidence support;
- uncertainty calibration;
- contradiction handling;
- escalation correctness;
- robustness under corrupt retrieval;
- transparency of safety decisions;
- auditability of failures.

The output should explain why the system passed or failed, not only produce a score.

## Robustness Engineering Strategies

Robustness strategies:

- test one perturbation at a time before composing failures;
- include adversarial near-misses, not just obvious failures;
- benchmark by clinical domain and evidence source;
- track false allow and false block rates separately;
- preserve failed cases as regression tests;
- monitor metric drift after retrieval or safety policy changes;
- evaluate safety systems with corrupted inputs and missing context.

The goal is not to prove the platform is always safe. The goal is to continuously measure where it
is reliable, where it is brittle, and when it must escalate.
