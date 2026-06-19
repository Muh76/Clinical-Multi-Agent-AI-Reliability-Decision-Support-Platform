# Human Approval Workflow Layer

The Human Approval Workflow Layer enables safe human-in-the-loop review for high-risk,
low-confidence, or policy-interrupted clinical AI workflows. It turns escalation decisions into
review checkpoints, reviewer context packages, approval decisions, audit events, and structured
workflow release signals.

The implementation lives in:

```text
packages/safety/src/clinical_ai_safety/approval.py
```

## Approval Workflow Architecture

```text
EscalationDecision or HumanReviewRequest
  -> ApprovalWorkflowRequest
  -> ReviewCheckpoint
  -> ReviewerContextPackage
  -> ApprovalWorkflowRecord
  -> ApprovalDecision
  -> ApprovalAuditEvent
  -> ApprovalWorkflowOutput
```

The layer is intentionally separate from the escalation policy engine. Escalation decides that a
review is required. Approval workflow manages review state, context, decision capture, audit, and
release behavior.

## Review State Machine

States:

- `not_required`: review checkpoint evaluated but no review is needed.
- `requested`: review has been requested and queued.
- `in_review`: reviewer has started review.
- `approved`: workflow may resume and output may be released.
- `approved_with_conditions`: workflow may resume only with required conditions.
- `rejected`: workflow should not proceed.
- `more_information_required`: workflow is paused pending additional information.
- `cancelled`: review was cancelled.
- `expired`: review was not completed inside policy timing.

Decision transitions:

- approve -> `approved`;
- approve with conditions -> `approved_with_conditions`;
- reject -> `rejected`;
- request more information -> `more_information_required`;
- cancel -> `cancelled`.

Terminal states such as `cancelled` and `expired` remain stable if additional decisions arrive.

## Reviewer Context Packaging

`ReviewerContextPackage` gives a reviewer enough explainable context to make a decision without
requiring raw internal logs.

It includes:

- case ID;
- workflow ID;
- trace ID;
- checkpoint metadata;
- summary;
- escalation events;
- evidence references;
- claim references;
- modality references;
- confidence summary;
- risk summary;
- limitations;
- recommended review questions;
- redacted payload references.

Recommended review questions are generated from escalation triggers. For example, contradictory
evidence asks the reviewer how the conflict should be resolved, while unsupported claims ask whether
claims should be removed, rewritten, or blocked.

## Escalation Review Integration

The approval layer consumes:

- `EscalationDecision`;
- `HumanReviewRequest`;
- escalation events;
- workflow checkpoint metadata;
- evidence, claim, and modality references;
- confidence and risk summaries.

If the escalation decision requires human review, the approval workflow starts in `requested`.
Otherwise, it starts as `not_required`. This allows every checkpoint to produce an audit artifact,
even when review is not needed.

## Audit Event Structure

Each `ApprovalAuditEvent` includes:

- audit event ID;
- approval ID;
- event type;
- previous state;
- next state;
- actor ID;
- actor role;
- reason;
- trace ID;
- workflow ID;
- metadata;
- timestamp.

Audit events are append-only artifacts. They should be stored immutably in production so governance,
clinical safety, and compliance teams can reconstruct why a workflow was approved, rejected,
qualified, or blocked.

## Trace Linkage

Traceability is preserved through:

- approval ID;
- review context ID;
- audit event IDs;
- case ID;
- workflow ID;
- trace ID;
- checkpoint ID;
- escalation event IDs;
- human review request ID.

This linkage lets dashboards move from a final approval decision back to safety events, evidence
references, claims, modalities, workflow traces, and the original checkpoint policy.

## Structured Approval Outputs

`ApprovalWorkflowOutput` includes:

- approval ID;
- final approval state;
- whether workflow may resume;
- whether output may be released;
- whether follow-up is required;
- approval conditions;
- requested information;
- audit event IDs;
- observability payload.

The distinction between workflow resume and output release matters. A workflow may continue with
conditions while still preventing unqualified output from being released.

## Observability Integration

Observability payloads include:

- approval ID;
- case ID;
- workflow ID;
- trace ID;
- checkpoint ID and type;
- approval state;
- queue;
- blocking flag;
- decision count;
- audit event count;
- human review request ID when present.

Recommended log events:

- `approval_review_requested`;
- `approval_review_started`;
- `approval_decision_recorded`;
- `approval_workflow_completed`;
- `approval_workflow_failed`;
- `approval_audit_event_recorded`.

Logs should not contain raw clinical notes or full evidence text. Store review packets and audit
records in secured review/audit storage and log stable references.

## Human-In-The-Loop AI Concepts

Human-in-the-loop AI is not simply placing a person after a model. It requires clear triggers,
reviewable context, decision authority, audit trails, and a release mechanism that respects the
review outcome. The reviewer must understand why the system escalated and what action they are
being asked to approve or reject.

In reliability platforms, humans review uncertainty, evidence conflict, unsupported claims, missing
context, policy violations, and whether downstream output should be allowed.

## Healthcare Review Workflows

Healthcare review workflows need:

- role-aware reviewers;
- high-priority queues for safety-critical cases;
- clear patient-context and evidence limitations;
- distinction between clinical review and AI governance review;
- decision rationale;
- conditions and follow-up requests;
- immutable audit records.

The approval layer does not make clinical decisions. It provides structured infrastructure for
reviewers to approve, reject, qualify, or request more information about AI workflow outputs.

## Enterprise Governance Design

Enterprise governance workflows can use approval records to:

- monitor review queues;
- inspect review turnaround time;
- audit policy threshold effectiveness;
- detect repeated escalation patterns;
- route cases to clinician, safety, or governance reviewers;
- analyze approvals by model version, workflow version, source type, or policy ID.

Approval outputs should integrate with dashboards, ticketing systems, governance stores, and future
deployment approval processes.

## Traceability Importance

Traceability is essential because safety decisions must be explainable after the fact. A reviewer
approval should link back to the exact workflow run, evidence package, claims, escalation events,
policy version, and audit trail. Without traceability, teams cannot investigate failures, tune
thresholds, satisfy governance requirements, or learn from near misses.
