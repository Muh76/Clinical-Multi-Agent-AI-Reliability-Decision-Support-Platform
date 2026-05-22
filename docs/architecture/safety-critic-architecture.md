# Safety Critic Architecture

The Safety Critic is the platform's independent reliability validation layer. It is not a diagnosis
system and does not produce clinical recommendations. Its responsibility is to inspect structured
patient context, retrieved evidence, risk analysis outputs, reasoning metadata, citations, modality
consistency, and workflow traces for safety and reliability failures.

Responsibilities:

- hallucination detection;
- unsupported claim detection;
- evidence verification;
- citation grounding;
- uncertainty analysis;
- escalation logic;
- safety policy enforcement;
- reliability validation;
- audit-ready safety event generation.

## Safety Critic Architecture

```text
ExplainableOutput or EndToEndWorkflowOutput
  -> SafetyCriticOrchestrator
  -> input contract validation
  -> evidence and citation verification
  -> claim and grounding validation
  -> risk and modality consistency checks
  -> uncertainty and confidence review
  -> policy enforcement
  -> escalation decision
  -> SafetyCriticReport
  -> observability + audit events
```

Core design principles:

- keep safety validation independent from generation and retrieval;
- use structured inputs, not conversational text parsing;
- preserve citation and evidence IDs through every safety finding;
- produce explainable safety outputs with confidence and escalation metadata;
- fail closed for critical grounding or policy violations;
- support human review and governance workflows.

## Safety Evaluation Pipeline

The Safety Critic should run after evidence retrieval and risk analysis, before any downstream
clinical-facing output is approved.

Pipeline:

1. **Input integrity validation**: confirm required workflow, trace, evidence, citation, confidence,
   patient context, and risk fields are present.
2. **Evidence verification**: ensure retrieved evidence has source metadata, citation IDs, and source
   reliability scores.
3. **Citation grounding validation**: ensure cited claims use citation IDs from the available
   citation allow-list.
4. **Unsupported claim detection**: identify claims or risk statements that lack supporting evidence
   or source references.
5. **Hallucination risk review**: detect claims, citations, or risk factors not present in structured
   evidence or patient context.
6. **Contradiction review**: inspect contradictory evidence signals and unresolved risk-analysis
   contradictions.
7. **Modality consistency review**: verify risk statements do not depend on absent or low-confidence
   modalities without qualification.
8. **Uncertainty and confidence review**: compare confidence scores against missingness,
   contradiction, source reliability, and evidence completeness.
9. **Policy enforcement**: apply safety policy rules such as block, qualify, request review, or allow.
10. **Escalation decision**: emit human review, governance, audit, or workflow routing actions.

## Validation Stages

| Stage | Purpose | Example failure |
| --- | --- | --- |
| Input integrity | Verify structured workflow output is complete | Missing workflow trace ID |
| Evidence validity | Verify evidence objects are citeable and attributed | Evidence lacks citation ID |
| Citation grounding | Verify citations are in the allow-list | Output cites unknown citation |
| Claim support | Verify claims map to evidence or patient context | Risk factor has no source refs |
| Contradiction review | Detect unresolved evidence conflict | Recommend/avoid conflict present |
| Modality consistency | Check whether outputs overuse absent modalities | Imaging-based claim without imaging |
| Confidence review | Detect overconfidence under uncertainty | High confidence with no evidence |
| Policy enforcement | Apply governance rules | Critical violation not blocked |
| Escalation routing | Decide reviewer/governance path | Human approval required |

Validation should be composable. Each stage should be independently testable and able to emit safety
events without depending on a monolithic prompt.

## Safety Event Schemas

Recommended safety event:

```json
{
  "event_id": "safety-event-001",
  "workflow_id": "workflow-123",
  "trace_id": "trace-456",
  "case_id": "case-001",
  "stage": "citation_grounding",
  "severity": "high",
  "event_type": "invalid_citation",
  "message": "Claim references a citation ID that was not retrieved.",
  "evidence_refs": ["pubmed:12345678"],
  "citation_refs": ["unknown:citation"],
  "modality_refs": [],
  "risk_factor_refs": [],
  "requires_human_review": true,
  "policy_action": "block",
  "confidence_impact": -0.25
}
```

Recommended report:

```json
{
  "report_id": "safety-report-001",
  "workflow_id": "workflow-123",
  "trace_id": "trace-456",
  "case_id": "case-001",
  "status": "requires_review",
  "overall_severity": "high",
  "safety_confidence": {
    "score": 0.72,
    "band": "moderate",
    "components": {
      "evidence_integrity": 0.9,
      "citation_grounding": 0.6,
      "modality_consistency": 0.8,
      "uncertainty_alignment": 0.65
    }
  },
  "events": [],
  "escalation": {
    "action": "human_review",
    "reason": "Citation grounding failed for high-impact claim.",
    "review_queue": "clinical_safety_review"
  }
}
```

## Confidence Scoring Abstraction

Safety confidence should be decomposed. It should not mirror retrieval or workflow confidence.

Suggested components:

- **Evidence integrity**: evidence exists, has source metadata, and has reliability scores.
- **Citation grounding**: citations are valid and map to cited evidence.
- **Claim support**: structured claims and risk factors have patient or evidence references.
- **Contradiction handling**: contradictory evidence is surfaced and not ignored.
- **Modality consistency**: outputs do not depend on absent or untrusted modalities.
- **Uncertainty alignment**: confidence is not overstated when evidence is weak or missing.
- **Policy compliance**: outputs satisfy configured safety rules.

Example:

```text
safety_confidence =
  0.20 * evidence_integrity
  + 0.20 * citation_grounding
  + 0.20 * claim_support
  + 0.15 * contradiction_handling
  + 0.10 * modality_consistency
  + 0.10 * uncertainty_alignment
  + 0.05 * policy_compliance
```

Confidence bands:

- `high`: validation passed with strong evidence and citation grounding;
- `moderate`: validation passed with qualifications or non-critical uncertainty;
- `low`: validation found material gaps or unresolved contradictions;
- `unknown`: insufficient structured information to validate.

## Escalation Framework

Escalation actions:

- `allow`: no material safety issue detected.
- `allow_with_qualification`: output may proceed with uncertainty or limitation labels.
- `human_review`: reviewer approval required before use.
- `governance_review`: policy, compliance, or deployment governance review required.
- `block`: output should not be shown or used downstream.
- `audit_only`: record event without blocking.

Escalation triggers:

- invalid citation on a safety-critical claim;
- unsupported clinical claim;
- high-confidence output with weak or missing evidence;
- contradiction between retrieved evidence and risk analysis;
- risk analysis depends on absent modality;
- synthetic evidence treated as authoritative;
- missing workflow trace or audit identifiers;
- critical policy violation.

The escalation decision should be explainable and include the safety events that triggered it.

## Observability Integration

Safety Critic logs should include:

- report ID;
- workflow ID;
- trace ID;
- case ID;
- safety status;
- overall severity;
- event count;
- policy action;
- human-review flag;
- safety confidence score;
- failed validation stages;
- latency.

Logs should not include raw clinical notes or full evidence text. Store detailed safety reports in
auditable storage and log stable IDs, counts, severities, and actions.

Recommended events:

- `safety_critic_started`;
- `safety_stage_completed`;
- `safety_event_recorded`;
- `safety_critic_completed`;
- `safety_critic_failed`;
- `human_review_requested`;
- `policy_action_applied`.

## Structured Safety Outputs

`SafetyCriticReport` should include:

- report ID;
- workflow and trace IDs;
- case ID;
- validation status;
- overall severity;
- safety confidence;
- safety events;
- failed stages;
- escalation decision;
- policy actions;
- audit references;
- generated timestamp.

Each safety event should include:

- stage;
- severity;
- event type;
- message;
- evidence references;
- citation references;
- modality references;
- risk factor references;
- confidence impact;
- human-review flag;
- policy action.

The output must be useful to clinician dashboards, governance systems, evaluation suites, audit
stores, and observability tools.

## Future Integration Support

Human approval workflows:

- Safety Critic emits `human_review` with queue name, reason, and blocking status.
- Reviewer decisions become audit events linked to the safety report.

Governance systems:

- Policy actions can route to model governance, deployment approval, or clinical safety committees.

Policy engines:

- Validation stages can call configurable policies by source type, jurisdiction, modality, risk
  level, or confidence band.

Audit infrastructure:

- Safety reports should be immutable append-only artifacts linked to workflow traces and evidence
  packages.

Reliability benchmarking:

- Safety events become labels for regression tests, red-team cases, and calibration benchmarks.

## AI Safety Architecture Principles

- Separate generation from validation.
- Validate against structured evidence, not narrative plausibility.
- Preserve provenance and citation IDs.
- Treat confidence as inspectable and decomposed.
- Fail closed for critical grounding violations.
- Make every escalation explainable.
- Keep human review paths explicit and auditable.
- Prefer deterministic policy checks before model-based adjudication.

## Healthcare Reliability Concerns

Healthcare AI failures can be persuasive, subtle, and high-impact. Risks include unsupported clinical
claims, stale evidence, wrong population, missing contraindication context, absent modality
assumptions, and overconfident summaries. The Safety Critic should treat uncertainty and missingness
as first-class safety signals.

## Enterprise AI Governance Concepts

Enterprise governance requires:

- traceability from output to evidence and workflow;
- immutable audit artifacts;
- configurable policy enforcement;
- separation of duties between generator, retriever, critic, and reviewer;
- measurable safety metrics;
- escalation workflows;
- benchmarking and regression gates.

The Safety Critic provides the validation substrate for those governance controls.

## Hallucination Risks In Healthcare

Healthcare hallucinations include:

- fabricated citations;
- real citation attached to unsupported claim;
- unsupported risk factor;
- overstated evidence strength;
- missing uncertainty qualifier;
- wrong patient population;
- modality-inconsistent conclusion;
- synthetic protocol presented as clinical authority;
- confident answer despite missing evidence.

The Safety Critic should detect these patterns before downstream systems present or act on the
output.
