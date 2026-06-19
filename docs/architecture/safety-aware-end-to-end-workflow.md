# Safety-Aware End-To-End Workflow

The safety-aware end-to-end workflow is the first fully composed reliability workflow for the
platform. It runs the existing patient context, evidence retrieval, and risk analysis pipeline, then
adds Safety Critic-style validation, hallucination detection, evidence verification, uncertainty
scoring, escalation analysis, human approval checkpointing, and explainable structured output.

The implementation lives in:

```text
packages/agents/src/clinical_ai_agents/safety_aware_workflow.py
```

## Orchestration Workflow

```text
SafetyAwareWorkflowRequest
  -> patient context ingestion
  -> evidence retrieval
  -> risk analysis
  -> base explainable output
  -> Safety Critic evaluation
  -> hallucination detection
  -> evidence verification
  -> uncertainty scoring
  -> escalation analysis
  -> human approval checkpoint
  -> SafetyAwareWorkflowOutput
```

This workflow is infrastructure orchestration. It does not generate diagnoses and does not act as a
chatbot. It packages traceable, auditable reliability outputs for downstream systems.

## Safety-Aware Execution Pipeline

The runner first calls the existing `EndToEndClinicalReliabilityWorkflowRunner`. That preserves the
established agent chain:

1. Patient Context Agent.
2. Evidence Retrieval Agent.
3. Risk Analysis Agent.
4. Explainable structured output builder.
5. Workflow trace graph and observability payload.

It then adds safety stages:

1. Convert risk factors and risk summary into structured claims.
2. Convert retrieved evidence and citations into `EvidenceReference` objects.
3. Run hallucination detection against claims and evidence.
4. Run evidence verification for claim-evidence support.
5. Run uncertainty scoring across retrieval, grounding, modality, temporal, and contradiction
   signals.
6. Run escalation policy analysis.
7. Create a human approval checkpoint when required.
8. Package final safety-aware output.

## Structured Workflow Outputs

`SafetyAwareWorkflowOutput` includes:

- output ID;
- workflow ID;
- trace ID;
- case ID;
- status;
- base workflow output;
- retrieved evidence;
- risk analysis;
- hallucination risk report;
- evidence verification report;
- uncertainty report;
- escalation decision;
- Safety Critic evaluation summary;
- safety events;
- approval payload;
- approval requirements;
- explainability metadata;
- workflow trace IDs;
- observability payload;
- failure recovery plan.

Statuses:

- `completed`: no safety interruption.
- `qualified`: output may proceed with reliability qualification.
- `requires_review`: human approval is required before release.
- `blocked`: output must not be released.
- `failed`: base workflow failed.

## Safety Event Logging

Safety events are normalized from:

- escalation events;
- hallucination failed checks;
- evidence verification failed checks;
- uncertainty sources;
- Safety Critic summary.

Events should be logged by ID, type, severity, action, trigger type, and trace linkage. Raw patient
notes and full evidence text should remain in secured artifacts rather than general logs.

Recommended events:

- `safety_aware_workflow_started`;
- `hallucination_detection_completed`;
- `evidence_verification_completed`;
- `uncertainty_scoring_completed`;
- `escalation_analysis_completed`;
- `human_approval_checkpoint_created`;
- `safety_aware_workflow_completed`;
- `safety_aware_workflow_failed`.

## Observability Integration

The observability payload includes:

- workflow ID;
- trace ID;
- case ID;
- base workflow status;
- hallucination risk score;
- uncertainty score;
- escalation action;
- safety event count;
- approval state;
- approval required flag.

This gives operations teams high-signal production telemetry without exposing raw clinical content.

## Trace Propagation

Trace propagation uses:

- `workflow_id`;
- `trace_id`;
- `case_id`;
- `approval_id`;
- base agent run IDs from the original trace graph;
- escalation decision ID;
- safety report IDs;
- audit event IDs when approval decisions are applied.

The final output keeps these IDs together so dashboards, auditors, and Safety Critic workflows can
move from the final result back to evidence, risk factors, safety checks, escalation events, and
human review.

## Escalation Handling

Escalation is policy-driven through `EscalationPolicy`.

Inputs include:

- hallucination risk score;
- retrieval confidence;
- grounding confidence;
- verification confidence;
- uncertainty score;
- contradiction count;
- unsupported claim count;
- missing required modalities;
- unstable temporal trend count;
- upstream safety recommendations.

The escalation result decides whether the workflow can continue, must be qualified, must pause for
review, or must block output.

## Human Approval Checkpoint

The workflow creates a pre-output-release approval checkpoint when:

- escalation requires human review;
- escalation blocks downstream output;
- the caller explicitly requires a checkpoint for audit coverage.

The approval packet includes:

- escalation events;
- evidence refs;
- claim refs;
- modality refs;
- confidence summary;
- risk summary;
- limitations;
- recommended review questions.

This allows clinician, safety, or governance reviewers to approve, conditionally approve, reject, or
request more information.

## Failure Recovery Logic

The final output includes a failure recovery plan:

- blocked outputs should not be released and should route to safety or governance review;
- review-required outputs should pause until approval is recorded;
- qualified outputs may release only with explicit reliability qualification;
- completed outputs require no recovery action;
- failed base workflows should preserve traces and errors for retry or investigation.

Recovery is deliberately explicit because enterprise AI systems need predictable operational
behavior under partial failure.

## Explainability Metadata

Explainability metadata includes:

- base explainable output;
- Safety Critic status;
- safety failed checks;
- escalation trigger types;
- trace linkage.

This supports clinician dashboards, evaluation pipelines, audit systems, and future governance
dashboards.

## Enterprise-Grade Trustworthy AI Infrastructure

The workflow is built as enterprise reliability infrastructure:

- modular safety stages;
- structured contracts;
- policy-driven escalation;
- human approval checkpointing;
- audit-ready IDs;
- observability-safe logs;
- explainable safety outputs;
- failure recovery guidance.

The design avoids conversational orchestration. It treats patient context, evidence, risk analysis,
safety checks, approval, and explainability as typed workflow artifacts.
