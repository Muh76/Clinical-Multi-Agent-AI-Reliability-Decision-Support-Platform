# Hallucination Detection Engine

The hallucination detection engine validates clinical outputs against retrieved evidence and
citations. It is not generic LLM hallucination detection. It is clinical evidence-grounded
reliability validation.

The engine detects:

- unsupported medical claims;
- fabricated evidence;
- missing citations;
- invalid citations;
- low-grounding outputs;
- contradictory evidence usage;
- retrieval-generation mismatch;
- overconfidence under weak grounding.

## Hallucination Detection Architecture

```text
HallucinationDetectionRequest
  -> citation allow-list construction
  -> per-claim citation validation
  -> evidence support scoring
  -> contradiction detection
  -> citation coverage calculation
  -> grounding confidence calculation
  -> hallucination risk scoring
  -> escalation recommendation
  -> HallucinationReport
```

Implementation:

```text
packages/safety/src/clinical_ai_safety/hallucination.py
```

The engine accepts structured claims and retrieved evidence references. It does not parse arbitrary
chat transcripts as the primary safety contract.

## Grounding Validation Pipeline

Stages:

1. Build citation allow-list from retrieved evidence or explicit citation IDs.
2. Validate each claim has citations.
3. Reject citations that are not in the allow-list.
4. Map citations to evidence payloads.
5. Compute lexical support between claim and cited evidence.
6. Detect contradiction markers in retrieved evidence.
7. Classify each claim as supported, partially supported, unsupported, contradicted, missing
   citation, or invalid citation.
8. Aggregate citation coverage and grounding confidence.
9. Compute hallucination risk and escalation recommendation.

## Evidence Consistency Analysis

Evidence consistency checks include:

- citations must point to retrieved evidence;
- cited evidence must contain enough overlapping clinical terms to support the claim;
- recommendation-like claims are checked against avoidance or insufficient-evidence language;
- source reliability contributes to grounding confidence;
- empty evidence sets automatically lower confidence and raise risk.

This is a deterministic first implementation. Future versions can add biomedical NLI, claim
decomposition, ontology matching, and policy-aware source hierarchy.

## Unsupported Claim Detection

Claim statuses:

- `supported`: cited evidence strongly overlaps with claim.
- `partially_supported`: claim has partial support but may need qualification.
- `unsupported`: cited evidence does not sufficiently support the claim.
- `contradicted`: retrieved evidence contains contradiction markers.
- `missing_citation`: claim has no citations.
- `invalid_citation`: claim cites evidence not retrieved or not allowed.

Unsupported claims are surfaced directly in `HallucinationReport.unsupported_claims`.

## Confidence Scoring

The engine produces:

- citation coverage;
- grounding confidence;
- hallucination risk score;
- risk band.

Hallucination risk combines:

- unsupported claim rate;
- contradiction rate;
- missing or invalid citation rate;
- low grounding confidence;
- overconfidence penalty when upstream confidence is high but grounding is weak.

Risk bands:

- low;
- moderate;
- high;
- critical.

## Structured Hallucination Reports

`HallucinationReport` includes:

- report ID;
- case ID;
- workflow ID;
- trace ID;
- hallucination risk score;
- risk band;
- grounding confidence;
- citation coverage;
- unsupported claims;
- all claim grounding results;
- escalation recommendation;
- failed checks;
- redacted observability payload;
- generated timestamp.

Each `ClaimGroundingResult` includes:

- claim ID;
- claim text;
- support status;
- support score;
- cited evidence IDs;
- invalid citations;
- contradictory evidence IDs;
- explanation.

## Observability Hooks

The report includes an `observability` payload with:

- case ID;
- workflow ID;
- trace ID;
- claim count;
- evidence count;
- hallucination risk score;
- risk band;
- grounding confidence;
- citation coverage;
- escalation recommendation;
- failed checks.

This payload is suitable for structured logs and metrics without storing full evidence text in
observability systems.

## Evaluation Framework

Evaluation datasets should include:

- supported claim cases;
- missing citation cases;
- fabricated citation cases;
- weakly supported claim cases;
- contradictory evidence cases;
- overconfident low-grounding cases;
- synthetic protocol boundary cases;
- retrieval-generation mismatch cases.

Metrics:

- unsupported claim detection precision and recall;
- invalid citation detection rate;
- missing citation detection rate;
- contradiction detection rate;
- citation coverage calibration;
- grounding confidence calibration;
- escalation accuracy;
- false block rate;
- false allow rate.

Regression tests should pin known safety cases and run them whenever retrieval, citation formatting,
or answer-generation logic changes.

## Healthcare Hallucination Risks

Healthcare hallucinations can be dangerous because they may sound plausible and cite real-looking
sources. Common failures include fabricated citations, real citations attached to unsupported claims,
overstated evidence strength, wrong population, ignored contraindications, and confident claims when
evidence is missing.

## Grounding Validation Strategies

Use structured validation before model-based judgment:

- require citation IDs;
- verify citation IDs against retrieved evidence;
- compare claim terms with cited passages;
- detect contradiction and uncertainty language;
- penalize overconfidence;
- preserve explanations and evidence references.

## Reliability Engineering Concepts

The detector follows reliability engineering principles:

- deterministic checks first;
- explicit failed checks;
- decomposed confidence;
- traceable inputs and outputs;
- regression-testable reports;
- escalation before unsafe use.

## Enterprise AI Safety Patterns

Enterprise safety patterns include:

- citation allow-lists;
- independent validation after retrieval/generation;
- structured safety reports;
- human review for high-risk or high-uncertainty cases;
- audit-ready observability payloads;
- reliability benchmarking.

The hallucination detection engine is the first concrete Safety Critic component for evidence-grounded
clinical reliability validation.
