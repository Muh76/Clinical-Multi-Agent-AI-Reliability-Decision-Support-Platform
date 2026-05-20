# Agent Orchestration Foundation

This architecture defines the foundational agent layer for the Clinical AI Reliability & Decision
Intelligence Platform. It is not a diagnosis chatbot. Agents are reliability infrastructure units:
they process patient context, retrieve evidence, analyze risk, explain provenance, and support
human-in-the-loop governance.

Initial agents:

- **Patient Context Agent**: prepares structured patient context from synthetic, MIMIC, or future
  multimodal inputs.
- **Evidence Retrieval Agent**: retrieves, reranks, and packages citeable evidence.
- **Risk Analysis Agent**: evaluates reliability, missingness, uncertainty, and workflow risk.

Future agents:

- Safety Critic Agent;
- Explainability Agent;
- Audit Agent;
- MCP-compatible Tool Agent;
- Evaluation Agent;
- multimodal modality-specific agents.

## Agent Base Architecture

```text
Workflow request
  -> Orchestrator
  -> AgentRunContext
  -> Patient Context Agent
  -> Evidence Retrieval Agent
  -> Risk Analysis Agent
  -> Grounded workflow output
  -> Audit, evaluation, and future Safety Critic hooks
```

Core package:

```text
packages/agents/src/clinical_ai_agents/
  contracts.py       structured agent interfaces and shared schemas
```

The agent layer should stay framework-neutral. LangGraph, OpenAI Agents SDK, MCP tools, Celery,
Temporal, or a custom async runner can be adapted later. The stable contract is the platform's
structured `AgentInput` and `AgentOutput`, not the orchestration vendor.

## Abstract Agent Interface

The base interface is async-first:

```python
class ClinicalAgent(Protocol):
    name: str
    role: AgentRole

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        ...
```

Every agent receives:

- case ID;
- role;
- trace context;
- structured payload;
- evidence references;
- tool references;
- metadata.

Every agent returns:

- run status;
- structured payload;
- findings;
- confidence score;
- citation references;
- explainability data;
- safety hooks;
- timestamps;
- trace context.

This keeps agents testable and composable without forcing every agent to exchange free text.

## Agent Lifecycle Design

Agent lifecycle states:

1. **Created**: orchestrator allocates `agent_run_id` and trace context.
2. **Input validated**: schema and required references are checked.
3. **Context bound**: workflow, trace, request, and correlation IDs are attached to logs.
4. **Tools resolved**: retrieval, patient context, cache, or MCP tools are made available.
5. **Run started**: agent emits `agent_run_started`.
6. **Work executed**: agent performs one bounded responsibility.
7. **Output validated**: structured output is validated before leaving the agent boundary.
8. **Run completed or failed**: agent emits status, latency, confidence, and findings.
9. **State persisted**: orchestrator stores output references, trace metadata, and audit events.

Agents should be idempotent when practical. Retrying a Patient Context Agent should not change the
meaning of the normalized patient context for the same input snapshot. Retrying retrieval should
preserve corpus snapshot IDs and model metadata.

## Initial Agent Responsibilities

### Patient Context Agent

Inputs:

- raw synthetic or MIMIC-shaped patient context;
- admission or encounter identifiers;
- modality availability metadata.

Outputs:

- structured patient context;
- timeline events;
- missingness profile;
- validation findings;
- retrieval terms;
- safety profile.

Boundaries:

- does not diagnose;
- does not infer missing measurements;
- does not create predictive labels.

### Evidence Retrieval Agent

Inputs:

- retrieval query;
- structured patient context summary;
- source filters;
- corpus snapshot or request-supplied evidence.

Outputs:

- retrieved evidence;
- citations;
- confidence scores;
- retrieval metadata;
- source reliability notes;
- citation allow-list for Safety Critic and hallucination detection.

Boundaries:

- retrieves evidence;
- does not generate recommendations;
- does not treat synthetic evidence as clinical authority.

### Risk Analysis Agent

Inputs:

- structured patient context;
- evidence package;
- validation findings;
- retrieval diagnostics.

Outputs:

- reliability findings;
- missingness risks;
- grounding risks;
- human-review recommendation;
- confidence score;
- Safety Critic handoff metadata.

Boundaries:

- analyzes risk and uncertainty;
- does not replace clinical judgment;
- does not produce diagnosis or treatment instructions.

## Orchestration Patterns

Supported patterns:

- **Sequential pipeline**: patient context -> evidence retrieval -> risk analysis. Best for the first
  workflow because dependencies are clear and traceability is simple.
- **Fan-out/fan-in**: run multiple retrieval or modality agents in parallel, then aggregate evidence.
  Useful for future multimodal workflows.
- **Supervisor orchestration**: a coordinator chooses which agents to run based on modality
  availability, risk level, or user intent.
- **Human gate**: pause after risk analysis or Safety Critic failure for reviewer input.
- **Evaluation replay**: rerun the same agent graph against frozen inputs and corpus snapshots.

Recommended first pattern:

```text
PatientContextAgent
  -> EvidenceRetrievalAgent
  -> RiskAnalysisAgent
  -> SafetyCriticAgent future hook
```

Avoid fully autonomous agent loops in clinical reliability workflows. Bounded, observable agent steps
are easier to validate, audit, and replay.

## Inter-Agent Communication Schemas

Use structured envelopes:

```json
{
  "case_id": "case-001",
  "role": "evidence_retrieval",
  "trace": {
    "workflow_id": "workflow-123",
    "trace_id": "trace-456",
    "agent_run_id": "agent-run-789",
    "request_id": "request-abc",
    "correlation_id": "correlation-def",
    "parent_agent_run_id": "agent-run-456"
  },
  "payload": {
    "query": "creatinine vancomycin renal dosing",
    "patient_context_ref": "context-001",
    "filters": {"source_types": ["local_policy", "pubmed"]}
  },
  "evidence_refs": [],
  "tool_refs": ["retrieval.hybrid_search"],
  "metadata": {
    "workflow_version": "v1"
  }
}
```

Agent output:

```json
{
  "case_id": "case-001",
  "role": "evidence_retrieval",
  "status": "completed",
  "summary": "Retrieved two renal dosing evidence items with verified citations.",
  "structured_payload": {
    "evidence_package_ref": "evidence-package-001",
    "retrieved_count": 2
  },
  "findings": [],
  "confidence": {
    "score": 0.84,
    "band": "moderate",
    "components": {
      "retrieval": 0.88,
      "citation_integrity": 1.0,
      "source_reliability": 0.78
    },
    "rationale": "Relevant evidence retrieved with valid citations; source mix includes PubMed."
  },
  "citations": ["local_policy:renal-dosing", "pubmed:12345678"],
  "explainability": {
    "top_sources": ["local_policy", "pubmed"]
  },
  "safety_hooks": {
    "citation_allow_list_available": true,
    "requires_safety_critic": true
  }
}
```

## Tracing Integration

Trace IDs should flow through every agent run:

- `request_id`: HTTP or external request ID;
- `correlation_id`: cross-system workflow ID;
- `workflow_id`: platform workflow execution;
- `trace_id`: end-to-end trace;
- `agent_run_id`: specific agent invocation;
- `parent_agent_run_id`: dependency chain.

Agents should emit:

- `agent_run_started`;
- `agent_tool_called`;
- `agent_run_completed`;
- `agent_run_failed`;
- `agent_human_review_requested`.

Logs should include stable identifiers, latency, status, counts, score components, and risk labels.
Do not log raw clinical notes or large evidence passages in infrastructure logs.

## Confidence Scoring Abstraction

Confidence is a structured object, not a single hidden model score:

```text
confidence =
  weighted_components
  + rationale
  + confidence_band
  + calibration metadata
```

Recommended component families:

- input completeness;
- validation quality;
- retrieval confidence;
- citation integrity;
- source reliability;
- grounding consistency;
- temporal consistency;
- safety risk.

Confidence bands:

- `high`: output is well-supported and traceable;
- `moderate`: usable with qualification or review;
- `low`: incomplete, weakly grounded, or risky;
- `unknown`: insufficient evidence to score.

Overconfidence should be treated as a safety risk. Agents should expose component scores so Safety
Critic, evaluation pipelines, and auditors can inspect why confidence moved.

## Structured Output Design

Every agent output should separate:

- `summary`: short human-readable description;
- `structured_payload`: machine-readable result;
- `findings`: warnings, errors, risk labels, missingness, grounding issues;
- `confidence`: score, band, components, rationale;
- `citations`: citation IDs or evidence references;
- `explainability`: provenance and reasoning metadata;
- `safety_hooks`: fields needed by future Safety Critic or human review;
- `trace`: execution identifiers.

This lets UI, API, audit, evaluation, and downstream agents consume the same output without parsing
free text.

## State Management Strategies

Options:

- **Stateless request mode**: agent outputs returned directly in the API response. Simple and good for
  early synchronous workflows.
- **Reference-based state**: payloads stored in Postgres/object storage, agents pass references.
  Better for large notes, images, evidence packages, and auditability.
- **Redis workflow state**: short-lived state for queues, retries, and progress updates.
- **Event-sourced audit state**: append-only agent events for governance and replay.

Recommended path:

1. start with stateless request mode plus structured traces;
2. add Postgres audit records for agent runs;
3. add Redis-backed workflow progress for async jobs;
4. add durable event logs for regulated review and replay.

## Enterprise Agent Design Patterns

Useful patterns:

- **Single-responsibility agents**: one bounded clinical reliability function per agent.
- **Contract-first design**: schemas before prompts, tools, or providers.
- **Tool isolation**: tools are injected and logged, not globally available.
- **Human escalation path**: agents can request review without pretending certainty.
- **Replayable execution**: store enough references to rerun with the same inputs.
- **Policy-aware routing**: high-risk cases run Safety Critic and Audit Agent.
- **Provider-neutral orchestration**: agent framework can change without changing contracts.
- **Evidence-first outputs**: citations and provenance travel with agent claims.

## Orchestration Tradeoffs

Sequential orchestration is simple and auditable, but slower when independent work could run in
parallel. Parallel orchestration improves latency but complicates ordering, failure handling, and
trace readability. Supervisor orchestration is flexible but can become opaque if routing decisions
are not logged and constrained.

For clinical reliability, prefer explicit graphs over unconstrained autonomous loops. The platform
should optimize for explainability, replay, and safety review before optimizing for agent autonomy.

## Why Modularity Matters

Modularity keeps clinical safety and engineering reliability aligned:

- retrieval can improve without rewriting patient context processing;
- Safety Critic can block outputs without being embedded inside generation;
- evaluation can replay agent steps independently;
- MCP tools can be added without changing core schemas;
- multimodal agents can join the graph without breaking text-only workflows;
- audit and explainability can inspect structured outputs instead of prompts.

The platform's trustworthiness comes from separable, traceable components. Agents should make the
system more observable and governable, not more mysterious.
