# Fully Orchestrated End-To-End Workflow

This workflow is the first complete enterprise AI reliability path in the platform. It ingests a
patient case, runs the Patient Context Agent, Evidence Retrieval Agent, and Risk Analysis Agent,
generates an explainable structured output, and records workflow traces. It is infrastructure for
clinical AI reliability, not chatbot logic.

## Orchestration Entrypoint

Implementation:

```text
packages/agents/src/clinical_ai_agents/end_to_end.py
```

Entrypoint:

```python
runner = EndToEndClinicalReliabilityWorkflowRunner()
output = await runner.run(
    EndToEndWorkflowRequest(
        case_id="case-001",
        patient_context={...},
        evidence_query="renal dosing creatinine vancomycin",
        evidence_corpus=[...],
    )
)
```

The runner returns `EndToEndWorkflowOutput`, a single structured artifact for dashboards, audit,
Safety Critic, evaluation, and observability.

## Workflow Runner

The runner performs:

1. Build workflow payload.
2. Execute `AgentWorkflowOrchestrator`.
3. Record workflow observability through `record_workflow_observability()`.
4. Build `ExplainableOutput`.
5. Attach formatted citations.
6. Return final structured workflow output.

The lower-level orchestrator remains responsible for agent chaining and shared state. The
end-to-end runner is responsible for final packaging and explainability.

## Shared Execution Context

Trace and context fields include:

- case ID;
- workflow ID;
- trace ID;
- request ID;
- correlation ID;
- agent run IDs;
- node IDs.

The same workflow trace links patient context, retrieval, risk analysis, explainability, and
observability.

## Structured Workflow Output

`EndToEndWorkflowOutput` includes:

- output ID;
- workflow ID;
- trace ID;
- case ID;
- status;
- structured patient context;
- retrieved evidence;
- citations;
- confidence scores;
- risk analysis;
- escalation indicators;
- explainability metadata;
- workflow trace graph;
- redacted observability payload;
- generated timestamp.

This object is intentionally machine-readable and dashboard-ready.

## Observability Integration

The runner calls `record_workflow_observability()` to produce `WorkflowTraceGraph` metadata.

The final output includes:

- workflow graph;
- node statuses;
- node latencies;
- aggregate confidence;
- evidence sources;
- escalation indicators;
- human-review flag.

Logs use IDs, counts, scores, and trace fields rather than raw clinical notes.

## Async Execution Flow

The runner is async-first:

```text
await runner.run(...)
  -> await orchestrator.run_patient_evidence_risk_workflow(...)
  -> await record_workflow_observability(...)
  -> package explainable output
```

Future production execution can move this runner behind a queue or workflow engine without changing
the structured output contract.

## Workflow Tracing

The output links:

- workflow trace graph;
- explainable output trace;
- agent run IDs;
- node IDs;
- formatted citations;
- risk contribution summaries.

This lets audit systems reconstruct what ran, what evidence was retrieved, what risk signals were
identified, and why human review was requested.

## Failure Handling

Failure handling is inherited from the orchestrator:

- failed nodes are recorded as node results;
- dependent nodes are skipped when required dependencies fail;
- partial and failed workflow statuses are explicit;
- explainability metadata records incomplete workflows as limitations.

The runner does not hide partial results.

## Final Output Contents

The final output includes:

- structured patient context from Patient Context Agent;
- retrieved evidence from Evidence Retrieval Agent;
- formatted citations from evidence attribution;
- workflow and per-agent confidence scores;
- risk analysis report;
- escalation indicators;
- explainability metadata;
- redacted observability payload;
- workflow trace IDs.

## Enterprise AI Reliability Posture

This workflow is designed for:

- clinical reliability review;
- explainability dashboards;
- Safety Critic handoff;
- auditability;
- evaluation replay;
- observability and monitoring.

It does not produce conversational responses, diagnosis predictions, or treatment recommendations.
