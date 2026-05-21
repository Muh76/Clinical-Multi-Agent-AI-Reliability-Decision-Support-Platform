# Agent Orchestration Layer

The orchestration layer coordinates the platform's initial reliability workflow:

```text
Patient Context Agent
  -> Evidence Retrieval Agent
  -> Risk Analysis Agent
```

It is async-first, traceable, observable, and contract-driven. The goal is reliable workflow
coordination for evidence grounding and risk-oriented infrastructure, not autonomous clinical
decision-making.

## Orchestration Architecture

```text
Workflow request
  -> AgentWorkflowOrchestrator
  -> WorkflowExecutionContext
  -> WorkflowGraph
  -> WorkflowNode execution
  -> Shared state update
  -> WorkflowExecutionOutput
```

Implementation:

```text
packages/agents/src/clinical_ai_agents/orchestration.py
```

The first graph is intentionally sequential:

1. Patient Context Agent structures multimodal patient context.
2. Evidence Retrieval Agent retrieves and packages citeable evidence.
3. Risk Analysis Agent evaluates risk-oriented reliability signals.

## Workflow Engine

`AgentWorkflowOrchestrator` owns execution of the graph. It:

- creates workflow and trace IDs;
- binds execution context into structured logs;
- executes each node asynchronously;
- passes shared state between agents;
- records per-node result metadata;
- stops required downstream nodes when dependencies fail;
- returns a structured workflow output.

Current entrypoint:

```python
await orchestrator.run_patient_evidence_risk_workflow(
    case_id="case-001",
    payload={...},
)
```

The current workflow is sequential, but the graph schema supports future branching and conditional
edges.

## Execution Context Design

`WorkflowExecutionContext` includes:

- workflow ID;
- trace ID;
- case ID;
- request ID;
- correlation ID;
- workflow name;
- workflow version;
- start time;
- metadata.

Each agent receives an `AgentTraceContext` derived from the workflow context. This gives every agent
run a stable `agent_run_id` plus parent linkage to the previous agent run.

## Shared State Management

The orchestrator keeps in-memory shared state for the first implementation:

- root input payload;
- Patient Context Agent structured payload;
- Evidence Retrieval Agent evidence package;
- Risk Analysis Agent report.

The final `WorkflowExecutionOutput` summarizes shared state rather than returning every raw payload
twice. Future production state can move to:

- Postgres audit records;
- Redis workflow progress;
- object storage for large patient/evidence payloads;
- event-sourced workflow logs.

## Trace Propagation

Trace propagation uses:

- `workflow_id`;
- `trace_id`;
- `request_id`;
- `correlation_id`;
- `agent_run_id`;
- `parent_agent_run_id`.

The orchestrator sets the same workflow and trace IDs on all agent inputs. Each downstream agent
receives the previous completed agent run ID as its parent, which makes the chain auditable.

## Structured Workflow Outputs

`WorkflowExecutionOutput` includes:

- workflow ID;
- trace ID;
- case ID;
- workflow status;
- graph;
- node results;
- shared state summary;
- aggregate confidence;
- timestamps and latency;
- human review flag;
- future integration points.

Each node result includes:

- node ID;
- agent role;
- status;
- agent run ID;
- latency;
- agent output or error.

## Orchestration Logging

The orchestrator emits:

- `workflow_started`;
- `workflow_node_started`;
- `workflow_node_completed`;
- `workflow_node_failed`;
- `workflow_completed`.

Log fields include:

- workflow ID;
- trace ID;
- case ID;
- workflow name/version;
- node ID;
- agent role;
- agent run ID;
- status;
- latency;
- confidence;
- human review flag.

Logs should use identifiers, counts, status, and scores. Raw clinical notes and evidence bodies
should stay in controlled payload storage, not general logs.

## Failure Handling

Failure handling is dependency-aware:

- failed node results record error type and message;
- required downstream nodes are skipped when dependencies fail;
- workflow status becomes `failed` when any node fails;
- workflow status becomes `partial` when nodes are skipped;
- human review is flagged when any agent requests review.

This makes failures explicit and replayable. The orchestrator does not hide partial execution.

## Future Branching Workflows

The graph schema supports future nodes and edges for:

- Safety Critic Agent;
- Explainability Agent;
- Audit Agent;
- human approval checkpoints;
- modality-specific branches;
- evaluation replay branches;
- policy-based routing.

Example future graph:

```text
Patient Context Agent
  -> Evidence Retrieval Agent
  -> Risk Analysis Agent
      -> Safety Critic Agent
      -> Explainability Agent
      -> Audit Agent
      -> Human Approval Checkpoint
```

## Orchestration Patterns

Useful patterns:

- **Sequential chain**: clear dependencies and simple replay.
- **Fan-out/fan-in**: parallel evidence or modality agents, followed by aggregation.
- **Conditional routing**: invoke Safety Critic only for high-risk or low-confidence workflows.
- **Human checkpoint**: pause when risk, contradiction, or uncertainty crosses threshold.
- **Evaluation replay**: rerun the same graph on frozen inputs and corpus snapshots.

The first workflow uses a sequential chain because reliability and traceability matter more than
agent autonomy at this stage.

## Workflow Reliability

Reliability depends on:

- strict agent input/output schemas;
- explicit node dependencies;
- trace propagation;
- structured failures;
- replayable state references;
- confidence aggregation;
- human review flags.

The workflow should fail visibly and preserve partial results rather than fabricating continuity.

## State Propagation

State propagation is explicit:

- Patient Context Agent output becomes retrieval profile and context summary.
- Evidence Retrieval Agent output becomes evidence package and citation allow-list.
- Risk Analysis Agent receives patient context plus retrieved evidence.

Agents do not mutate each other's outputs. The orchestrator copies structured payloads into shared
state and passes role-specific views to the next agent.

## Production Best Practices

- Keep orchestration framework-neutral.
- Treat workflow graphs as versioned contracts.
- Persist agent outputs by reference for large payloads.
- Add OpenTelemetry spans around workflow and node execution.
- Add queue-backed async execution for long-running retrieval or Safety Critic workflows.
- Store audit events for every node transition.
- Avoid raw PHI or large clinical text in logs.
- Keep human approval checkpoints explicit and resumable.

The orchestration layer should make the platform more reliable, explainable, and auditable. It
should not turn the system into an unconstrained autonomous clinical agent.
