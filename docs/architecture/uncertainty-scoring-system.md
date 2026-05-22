# Uncertainty Scoring System

The uncertainty scoring system estimates confidence and uncertainty across retrieval quality,
evidence grounding, modality completeness, risk analysis stability, contradiction presence, and
temporal consistency. It is not a diagnosis confidence score. It is reliability metadata for
orchestration, explainability, Safety Critic validation, audit, and escalation.

The implementation lives in:

```text
packages/safety/src/clinical_ai_safety/uncertainty.py
```

## Uncertainty Architecture

```text
Workflow outputs
  -> UncertaintyScoringRequest
  -> retrieval confidence component
  -> grounding and verification component
  -> modality completeness component
  -> risk stability component
  -> contradiction component
  -> temporal consistency component
  -> weighted confidence aggregation
  -> uncertainty banding
  -> escalation recommendation
  -> UncertaintyReport
```

The scoring system is modular. Each component emits its own confidence score, uncertainty score,
weight, rationale, and contributing factors. This makes the final score explainable and lets future
calibration update component weights without changing the report contract.

## Confidence Scoring Framework

The first implementation scores six components:

- **Retrieval quality**: uses retrieval confidence from the Evidence Retrieval Agent.
- **Evidence grounding**: combines grounding confidence, verification confidence, citation coverage,
  evidence coverage, and source trust.
- **Modality completeness**: checks whether required patient context modalities are present,
  sufficiently populated, and free from quality issues.
- **Risk stability**: lowers confidence when unstable trends or many risk factors accumulate.
- **Contradiction handling**: lowers confidence when evidence or reasoning contains contradictions.
- **Temporal consistency**: uses timestamp completeness and temporal inconsistency counts.

Default aggregation:

```text
confidence =
  0.18 * retrieval_quality
  + 0.24 * evidence_grounding
  + 0.16 * modality_completeness
  + 0.14 * risk_stability
  + 0.18 * contradiction_handling
  + 0.10 * temporal_consistency
```

`uncertainty_score = 1 - confidence_score`.

## Uncertainty Aggregation Logic

Aggregation is weighted and composable:

- missing component inputs receive conservative default scores;
- each component records missingness as a contributing factor;
- high contradiction counts can override otherwise acceptable averages;
- escalation uses both the uncertainty band and specific safety signals;
- observability receives scores and source names, not raw clinical content.

Uncertainty bands:

- `low`: score below 0.30;
- `moderate`: score from 0.30 to below 0.55;
- `high`: score from 0.55 to below 0.80;
- `critical`: score at or above 0.80.

## Modality Completeness Scoring

`ModalityCompletenessInput` captures:

- modality name;
- presence;
- whether the modality is required;
- record count;
- missing field count;
- quality issue count;
- optional modality-level confidence.

The modality score combines:

- presence;
- minimum record volume;
- missingness penalty;
- quality issue penalty;
- optional upstream modality confidence.

Absent required modalities become explicit uncertainty sources such as
`modality_absent:labs` or `modality_absent:clinical_notes`.

## Contradiction Uncertainty Scoring

Contradictions are treated differently from normal missingness. A workflow can have high retrieval
confidence and still be unsafe if retrieved evidence conflicts with the risk analysis or reasoning
output.

The contradiction component:

- starts from high confidence when no contradictions are present;
- applies a penalty per contradiction;
- records `contradictions_present` as an uncertainty factor;
- can trigger human review or blocking even when the weighted confidence average looks acceptable.

## Retrieval Confidence Integration

Retrieval confidence should come from the Evidence Retrieval Agent or retrieval evaluation layer.
Useful retrieval signals include:

- top-K score distribution;
- reranker agreement;
- source reliability;
- query coverage;
- citation availability;
- retrieval latency or fallback behavior;
- negative-case abstention confidence.

The uncertainty system does not replace retrieval evaluation. It consumes retrieval confidence as
one component and combines it with grounding, patient-context, temporal, and contradiction signals.

## Structured Uncertainty Outputs

`UncertaintyReport` includes:

- report ID;
- case, workflow, and trace IDs;
- confidence score;
- uncertainty score;
- uncertainty band;
- component scores;
- uncertainty sources;
- reliability indicators;
- escalation recommendation;
- calibration notes;
- observability payload;
- generated timestamp.

Each `UncertaintyComponent` includes:

- source type;
- confidence score;
- uncertainty score;
- weight;
- rationale;
- contributing factors.

Each `ReliabilityIndicator` includes:

- stable code;
- status: strong, acceptable, weak, or missing;
- score;
- message.

## Observability-Ready Design

The observability payload includes:

- case ID;
- workflow ID;
- trace ID;
- confidence score;
- uncertainty score;
- uncertainty band;
- uncertainty sources;
- escalation recommendation;
- contradiction count;
- temporal inconsistency count;
- modality count.

Recommended log events:

- `uncertainty_scoring_started`;
- `uncertainty_component_scored`;
- `uncertainty_scoring_completed`;
- `uncertainty_escalation_recommended`;
- `uncertainty_scoring_failed`.

The payload avoids raw patient values, clinical notes, and evidence text.

## Escalation Integration

Escalation recommendations:

- `allow`: low uncertainty with no material reliability source.
- `qualify`: uncertainty sources exist but are not blocking.
- `human_review`: high uncertainty or any contradiction.
- `block`: critical uncertainty or repeated contradiction.

Escalation policy should remain configurable. Different clinical workflows may require stricter
thresholds for pediatric, oncology, emergency, medication, or high-acuity contexts.

## Calibration Strategies

Calibration requires comparing predicted confidence against observed reliability outcomes.

Recommended strategies:

- maintain labeled evaluation sets for retrieval, grounding, modality completeness, temporal
  consistency, contradiction handling, and risk stability;
- track calibration curves by component and by workflow type;
- measure expected calibration error and reliability diagrams for confidence bins;
- monitor false allow, false block, and false review rates;
- calibrate contradiction and citation failures separately from average confidence;
- tune component weights using validation sets, not production anecdotes;
- preserve raw component scores so recalibration can happen without losing auditability.

Confidence should be treated as operational metadata until validated against outcomes.

## Uncertainty In Healthcare AI

Healthcare AI uncertainty comes from incomplete patient context, changing patient state, ambiguous
timestamps, missing modalities, conflicting guidelines, weak or outdated evidence, population
mismatch, and model limitations. A system may be fluent and still uncertain because the evidence
does not support the claim or the patient context is incomplete.

Uncertainty should be surfaced rather than hidden. Good reliability infrastructure makes uncertainty
visible enough for clinicians, auditors, and safety systems to decide whether to proceed, qualify,
review, or block.

## Reliability Engineering Principles

The uncertainty system follows reliability engineering principles:

- decompose global confidence into inspectable components;
- prefer conservative defaults when inputs are missing;
- treat contradictions as safety signals, not simple score noise;
- log stable structured fields for monitoring;
- separate confidence, uncertainty, and escalation;
- design for calibration and regression testing.

## Why Confidence Alone Is Insufficient

A single confidence number can hide the reason for risk. Two outputs may both score `0.72`, but one
may have weak retrieval while another has missing labs and contradictory evidence. These require
different operational responses.

Confidence alone also fails when:

- evidence is relevant but not supportive;
- citations are valid but incomplete;
- patient modalities are missing;
- timestamps are inconsistent;
- evidence contradicts the downstream reasoning;
- confidence is high because only easy signals were measured.

The platform therefore exposes confidence score, uncertainty sources, reliability indicators, and
escalation recommendations together.
