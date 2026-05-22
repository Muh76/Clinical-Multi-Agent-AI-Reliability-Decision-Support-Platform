# Evidence Verification Layer

The Evidence Verification Layer validates whether retrieved evidence actually supports downstream
risk analysis, reasoning metadata, and explainable outputs. It is not a second retriever and it does
not generate clinical recommendations. It checks claim-to-evidence support, citation traceability,
contradiction signals, source trust, confidence alignment, and audit-ready observability.

The implementation lives in:

```text
packages/safety/src/clinical_ai_safety/verification.py
```

## Verification Architecture

```text
Risk claims + retrieved evidence
  -> EvidenceVerificationRequest
  -> citation allow-list validation
  -> claim-evidence matching
  -> contradiction analysis
  -> source trust scoring
  -> evidence coverage scoring
  -> confidence-aware verification
  -> escalation recommendation
  -> EvidenceVerificationReport
```

The layer consumes structured claims and `EvidenceReference` objects. This keeps verification
deterministic, traceable, and suitable for Safety Critic integration.

## Claim-Evidence Matching Pipeline

Pipeline stages:

1. Build the citation allow-list from retrieved evidence or explicit workflow citation IDs.
2. Verify each claim has citations.
3. Reject citations not present in the retrieved citation allow-list.
4. Resolve citations to evidence payloads.
5. Score lexical clinical-term overlap between each claim and cited evidence.
6. Classify each claim as verified, partially verified, unsupported, contradicted, untraceable, or
   unknown.
7. Calculate per-claim source trust from cited evidence.
8. Emit explainable `ClaimEvidenceMatch` records.

The first implementation uses deterministic lexical support as a conservative baseline. Future
versions can add biomedical natural language inference, UMLS concept matching, MeSH expansion,
study-population matching, and guideline hierarchy rules.

## Citation Verification Logic

Citation verification checks:

- each claim has at least one citation ID;
- citation IDs exist in the current retrieved evidence allow-list;
- each traceable citation resolves to an evidence payload;
- invalid and missing citations are preserved in structured results;
- traceability contributes to verification confidence.

Citation statuses:

- `traceable`: every citation maps to retrieved evidence;
- `partial`: some citations are traceable and some are invalid;
- `missing`: the claim has no citations;
- `invalid`: no cited IDs exist in the allow-list.

This supports hallucination detection by making fabricated and mismatched citations visible before
any downstream output is approved.

## Contradiction Analysis

Contradiction analysis looks for recommendation-like or assertive claims that conflict with
retrieved evidence containing avoidance, contraindication, no-evidence, harm, or
insufficient-evidence language. A contradiction is only recorded when the claim and evidence share
clinical terms, which reduces false positives from unrelated evidence.

Contradicted claims should normally trigger blocking or human review because an apparently grounded
answer can still be unsafe if it selectively uses evidence while ignoring conflict.

## Evidence Coverage Scoring

Evidence coverage answers a practical question: how much of the downstream claim set is actually
grounded?

Coverage uses:

- verified claim count;
- partially verified claim count;
- unsupported claim count;
- contradicted claim count;
- untraceable claim count;
- per-claim support and coverage scores;
- citation traceability score.

`EvidenceCoverageSummary` exposes both evidence coverage and citation traceability so dashboards and
Safety Critic policies can distinguish weak support from broken provenance.

## Source Trust Scoring

Source trust is separate from claim relevance. A source can be relevant and still weak.

The first source trust model combines:

- upstream evidence reliability score;
- source type score;
- evidence level score;
- recency score.

Example source-type priors:

- NICE guideline: high trust;
- local policy: high operational trust, jurisdiction dependent;
- PubMed: strong but study-design dependent;
- synthetic protocol: useful for development, not clinical authority;
- imaging metadata: context only unless linked to validated interpretation.

Missing evidence level or publication year lowers explainability confidence and is recorded as a
note in `SourceTrustScore`.

## Structured Verification Reports

`EvidenceVerificationReport` includes:

- report ID;
- case, workflow, and trace IDs;
- overall verification status;
- verification confidence;
- evidence coverage summary;
- aggregate source trust score;
- contradiction count;
- claim-evidence matches;
- citation verification results;
- source trust breakdowns;
- unsupported claim IDs;
- contradicted claim IDs;
- escalation recommendation;
- failed checks;
- observability payload;
- generated timestamp.

The report is designed for hallucination detection, explainability panels, audit storage, governance
rules, and escalation workflows.

## Observability Integration

The observability payload intentionally avoids raw evidence text and clinical notes. It contains:

- case ID;
- workflow ID;
- trace ID;
- claim count;
- evidence count;
- overall status;
- verification confidence;
- evidence coverage score;
- citation traceability score;
- source trust score;
- contradiction count;
- escalation recommendation;
- failed checks.

Suggested log events:

- `evidence_verification_started`;
- `citation_verification_completed`;
- `claim_evidence_match_completed`;
- `source_trust_scored`;
- `evidence_verification_completed`;
- `evidence_verification_failed`;
- `verification_escalation_recommended`.

## Evidence Verification Strategies

Reliable verification should combine several strategies:

- deterministic citation allow-list checks;
- claim decomposition before support scoring;
- lexical and semantic evidence matching;
- source hierarchy and study-design scoring;
- contradiction and uncertainty detection;
- population, intervention, comparator, outcome, and setting checks;
- confidence penalties for missing citations or low coverage;
- regression tests for known grounding failures.

Deterministic checks should run first because they are easy to audit and hard for generation systems
to bypass.

## Medical Citation Reliability

Medical citation reliability depends on provenance, study design, freshness, population fit,
journal or source quality, guideline authority, jurisdiction, and whether the cited passage supports
the exact claim being made. PubMed citations are not automatically authoritative; abstracts may be
incomplete, observational, outdated, retracted, or mismatched to the patient population.

Guidelines and local policies also need context. A guideline may be reliable but not applicable to
a specific patient, care setting, jurisdiction, age group, pregnancy status, comorbidity, or
medication interaction.

## Retrieval Grounding Limitations

Retrieval can fail even when the answer appears cited:

- top-ranked evidence may be relevant but not supportive;
- the right evidence may be retrieved but ignored;
- a citation may point to a source that discusses the topic but not the claim;
- evidence can be contradictory across guidelines, studies, and populations;
- abstracts may omit contraindications or statistical uncertainty;
- synthetic protocols may be accidentally treated as clinical authority.

The verification layer lowers confidence and escalates when retrieval-grounding gaps appear.

## Explainable Validation Techniques

Explainability comes from structured, inspectable outputs:

- every claim has a verification status;
- every claim links to cited evidence IDs and citation IDs;
- invalid citations are preserved;
- contradictory evidence IDs are surfaced;
- source trust is decomposed into components;
- confidence is separated into coverage, traceability, trust, and contradiction handling;
- failed checks are stable machine-readable strings.

This makes the verification result useful for clinician dashboards, Safety Critic reports,
governance review, audit trails, and evaluation pipelines.
