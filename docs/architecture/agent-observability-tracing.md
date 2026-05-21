# Agent Observability And Tracing

Agent observability captures structured execution traces, graph metadata, latency, confidence,
evidence sources, risk events, escalation indicators, failures, and future token accounting. It is
designed for debugging AI workflows, enterprise monitoring, audit support, and future Langfuse or
OpenTelemetry integration.

## Tracing Architecture

```text
AgentInput
  -> AgentObservabilityMiddleware
  -> ClinicalAgent.run()
  -> AgentExecutionLogger
  -> AgentExecutionTrace
  -> MetricsSink
  -> structured logs / future tracing backend
```

Workflow-level traces are derived from orchestration outputs:

```text
WorkflowExecutionOutput
  -> workflow_trace_from_output()
  -> WorkflowTraceGraph
  -> record_workflow_observability()
```

Implementation:

```text
packages/agents/src/clinical_ai_agents/observability.py
```

## Agent Execution Logger

`AgentExecutionLogger` records success and failure traces. It captures:

- workflow ID;
- trace ID;
- agent run ID;
- parent agent run ID;
- case ID;
- agent name and role;
- sequence index;
- status;
- timestamps;
- latency breakdown;
- confidence score and band;
- evidence sources;
- citation IDs;
- escalation indicators;
- risk events;
- token usage;
- error type and message.

The logger emits redacted structured logs and sends the full structured trace to a pluggable
`MetricsSink`.

## Workflow Trace Schema

`WorkflowTraceGraph` captures workflow visualization metadata:

- workflow ID;
- trace ID;
- case ID;
- graph ID;
- workflow status;
- duration;
- graph nodes;
- graph edges;
- aggregate confidence;
- human-review flag;
- evidence sources;
- escalation indicators.

This is suitable for clinician-facing workflow progress views, operations dashboards, audit records,
and future graph visualizations.

## Observability Middleware

`AgentObservabilityMiddleware` wraps any `ClinicalAgent`:

```python
observed_agent = AgentObservabilityMiddleware(agent, sequence_index=1)
output = await observed_agent.run(agent_input)
```

The wrapper:

- binds workflow and agent context into structured logs;
- measures execution latency;
- records success traces;
- records failure traces;
- preserves the original agent output contract.

This keeps observability separate from agent business logic.

## Metrics Hooks

`MetricsSink` is a protocol with:

- `record_agent_execution()`;
- `record_workflow_trace()`.

`NoopMetricsSink` is the default. Production sinks can forward traces to:

- OpenTelemetry;
- Prometheus counters and histograms;
- Langfuse;
- Datadog;
- CloudWatch;
- audit databases;
- evaluation stores.

## Structured Trace Outputs

Structured trace outputs include:

- `AgentExecutionTrace`;
- `WorkflowTraceGraph`;
- `WorkflowTraceNode`;
- `WorkflowTraceEdge`;
- `LatencyBreakdown`;
- `TokenUsage`.

These schemas are intentionally Pydantic models so they can be serialized to JSON, stored, tested,
and compared in evaluation pipelines.

## Error Observability

Failure traces capture:

- failed agent name and role;
- error type;
- error message;
- latency until failure;
- trace IDs;
- parent run ID;
- case ID;
- metadata.

Errors are logged with `logger.exception()` and sent through the same metrics sink, giving operators
one path for successful and failed executions.

## Token Tracking Abstraction

`TokenUsage` tracks:

- input tokens;
- output tokens;
- total tokens;
- provider;
- model;
- estimation method.

The current platform does not require every agent to use an LLM. Token usage is therefore optional
and defaults to `not_measured`. LLM-backed agents can attach token usage later without changing trace
schemas.

## Tracked Workflow Signals

The observability layer supports:

- agent execution order through sequence index and parent agent run IDs;
- retrieval latency and reranking latency when provided by retrieval metadata;
- workflow duration;
- evidence source types;
- citation counts;
- risk scoring latency;
- risk factor events;
- escalation indicators;
- confidence score and band;
- failure events.

## Future Langfuse Integration Design

`langfuse_trace_payload()` converts `WorkflowTraceGraph` into a Langfuse-style trace payload with
workflow metadata and node spans.

Future integration should:

- create one Langfuse trace per workflow;
- create one span per agent node;
- attach confidence, evidence sources, escalation indicators, and latency metadata;
- avoid raw patient notes and full evidence text unless explicitly approved;
- link Langfuse IDs back to platform audit records.

## Why Observability Matters

Clinical AI workflows can fail in ways that are not obvious from final output alone. Retrieval may
miss evidence, reranking may bury the right source, confidence may be overestimated, or risk analysis
may escalate because of missing modalities. Observability makes those internal steps visible,
debuggable, and auditable.

## Debugging AI Workflows

Debugging requires seeing:

- which agents ran;
- in what order;
- with which trace IDs;
- how long each step took;
- what evidence sources were used;
- where confidence dropped;
- whether escalation was triggered;
- where failures occurred.

Structured traces answer those questions without reading raw prompts or clinical text.

## Enterprise Tracing Strategies

Recommended strategy:

1. use structured logs for every workflow and agent step;
2. persist workflow trace summaries for audit and replay;
3. export latency and count metrics to monitoring;
4. export graph spans to Langfuse or OpenTelemetry;
5. keep raw clinical payloads out of generic logs;
6. correlate request, workflow, trace, and agent run IDs.

## Production AI Monitoring Concepts

Production monitoring should track:

- latency distributions by agent and workflow;
- retrieval and reranking latency;
- failure rates;
- empty evidence retrieval rates;
- confidence distributions;
- escalation rates;
- source distribution drift;
- contradiction signal frequency;
- human-review volume;
- token usage and model/provider cost when LLM agents are introduced.

The observability layer gives the platform a stable foundation for that monitoring without locking
the architecture to a single tracing vendor.
