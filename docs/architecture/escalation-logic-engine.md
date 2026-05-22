# Escalation Logic Engine

The Escalation Logic Engine turns reliability and safety signals into workflow decisions. It is the
policy-driven control layer that decides whether a workflow can continue, must continue with
qualification, must pause for human review, or must block downstream output.

The implementation lives in:

```text
packages/safety/src/clinical_ai_safety/escalation.py
```

## Escalation Architecture

```text
Safety and reliability reports
  -> EscalationSignals
  -> EscalationPolicy
  -> threshold evaluation
  -> structured EscalationEvent[]
  -> WorkflowInterruptionDecision
  -> optional HumanReviewRequest
  -> EscalationDecision
  -> audit + observability payloads
```

The engine is designed to run at safety checkpoints after retrieval, evidence verification, risk
analysis, uncertainty scoring, hallucination detection, or final structured output assembly.

## Escalation Policy Engine

`EscalationPolicyEngine` evaluates an `EscalationRequest` using:

- a policy ID and version;
- configurable thresholds;
- review queue names;
- governance queue names;
- contradiction and hallucination blocking flags;
- incoming safety and reliability signals.

The default policy is conservative for clinical reliability workflows. It blocks critical
hallucination risk and repeated contradictions, pauses for human review on high-risk validation
failures, and allows qualified continuation for lower-confidence but non-blocking issues.

## Threshold Framework

`EscalationThresholds` includes:

- hallucination risk threshold for human review;
- hallucination risk threshold for blocking;
- minimum retrieval confidence;
- minimum grounding confidence;
- minimum verification confidence;
- uncertainty threshold for human review;
- uncertainty threshold for blocking;
- maximum contradictions before blocking;
- maximum unsupported claims before review;
- maximum missing required modalities before review;
- maximum unstable temporal trends before review.

Thresholds are explicit policy inputs, not hidden constants inside agent logic. This supports
governance, testing, jurisdiction-specific policy, and later enterprise policy-system integration.

## Escalation Event Schemas

Each `EscalationEvent` contains:

- event ID;
- trigger type;
- severity;
- workflow action;
- message;
- threshold;
- observed value;
- evidence, claim, and modality references;
- human-review flag;
- review queue;
- policy ID;
- timestamp.

Trigger types include:

- high hallucination risk;
- contradictory evidence;
- low retrieval confidence;
- missing modality;
- unstable temporal trend;
- high uncertainty;
- unsupported claim;
- low grounding confidence;
- low verification confidence;
- workflow failure.

## Workflow Interruption Logic

Workflow interruption is separated from event detection.

Actions:

- `continue`: no threshold violation.
- `continue_with_qualification`: workflow may proceed with explicit reliability qualification.
- `pause_for_human_review`: workflow should stop until a reviewer decision is recorded.
- `block_output`: downstream output should not be shown or used.

Priority order:

1. Any blocking event blocks output.
2. Any human-review event pauses the workflow.
3. Any qualification event allows continuation with qualification.
4. No events allow normal continuation.

This priority order prevents a benign average score from hiding a critical safety signal.

## Human-Review Integration Points

When human review is required, the engine emits `HumanReviewRequest` with:

- review ID;
- queue;
- priority;
- case ID;
- workflow ID;
- trace ID;
- reason;
- blocking flag;
- linked event IDs;
- policy metadata.

Future integrations can map this request to clinician review queues, task systems, governance
dashboards, or EHR-adjacent approval workflows.

## Observability Hooks

The observability payload includes:

- case ID;
- workflow ID;
- trace ID;
- checkpoint ID;
- policy ID and version;
- event count;
- critical and high event counts;
- recommended action;
- interruption flag;
- human-review flag;
- qualification flag;
- trigger types.

Recommended events:

- `escalation_policy_started`;
- `escalation_event_emitted`;
- `workflow_interruption_decided`;
- `human_review_requested`;
- `escalation_policy_completed`;
- `escalation_policy_failed`.

Raw clinical notes and full evidence text should not be logged. Logs should contain stable IDs,
counts, trigger types, actions, and queue names.

## Structured Escalation Outputs

`EscalationDecision` includes:

- decision ID;
- case, workflow, and trace IDs;
- checkpoint ID;
- policy ID and version;
- recommended action;
- workflow interruption decision;
- escalation events;
- optional human review request;
- audit metadata;
- observability payload;
- generated timestamp.

The output can be stored as an audit artifact and referenced by downstream Safety Critic,
explainability, governance, analytics, and human-review systems.

## Escalation Engineering Concepts

Escalation engineering is about converting safety signals into operational control. In clinical AI,
the key design rule is that critical signals should interrupt the workflow even when average
confidence appears acceptable. Escalation systems therefore need explicit policies, ordered actions,
audit logs, and human-review routing.

Good escalation systems are:

- deterministic where possible;
- configurable by policy;
- explainable to operators;
- auditable after the fact;
- observable in production;
- conservative for safety-critical failures.

## Human-In-The-Loop AI

Human review should not be a vague fallback. It should be a structured workflow with a reason,
queue, priority, blocking status, linked events, and trace IDs. Reviewers need enough context to
decide whether to approve, reject, qualify, or request more information.

The engine emits the review request, but it does not assume a specific review tool. That keeps the
platform ready for clinician queues, governance dashboards, enterprise ticketing, or policy engines.

## Safety-Critical Workflow Design

Safety-critical workflows should separate:

- signal generation;
- policy evaluation;
- interruption decision;
- human review;
- audit recording;
- downstream output release.

This separation prevents retrieval, generation, risk analysis, and safety policy from becoming
tangled. It also lets each layer evolve independently and be tested in isolation.

## Governance Integration Strategies

Enterprise governance systems can use escalation outputs to:

- monitor safety-event rates by workflow;
- review policy threshold changes;
- audit blocked or reviewed cases;
- measure false block and false allow rates;
- route high-severity cases to clinical safety committees;
- power dashboards for reliability and compliance teams;
- create benchmark datasets from recurring escalation patterns.

Policy IDs, versions, thresholds, and event metadata should be preserved so every decision can be
reconstructed later.
