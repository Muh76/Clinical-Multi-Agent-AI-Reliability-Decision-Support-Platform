# Patient Context Agent

The Patient Context Agent aggregates and structures multimodal patient context into a unified
representation for downstream reasoning systems. It does not generate diagnosis predictions. Its job
is structured patient intelligence infrastructure: normalization, missingness, temporal ordering,
modality abstraction, patient summarization, confidence metadata, and traceable handoff to retrieval,
risk analysis, safety evaluation, explainability, and future multimodal fusion.

## Patient Context Agent Architecture

```text
AgentInput
  -> PatientContextAgent
  -> RawPatientContext validation
  -> PatientContextProcessor
  -> modality context construction
  -> timeline summarization
  -> missingness profiling
  -> modality fusion preparation
  -> confidence scoring
  -> AgentOutput
```

Implementation:

```text
packages/agents/src/clinical_ai_agents/patient_context.py
packages/agents/src/clinical_ai_agents/temporal.py
```

The agent wraps the existing multimodal `PatientContextProcessor` so the platform has one patient
context normalization engine. The agent adds orchestration-facing output: confidence, findings,
trace IDs, modality fusion inputs, explainability metadata, and safety hooks.

## Agent Implementation

`PatientContextAgent` implements the shared `ClinicalAgent` contract:

```python
agent = PatientContextAgent()
output = await agent.run(agent_input)
```

Expected input payload:

```json
{
  "patient_context": {
    "patient_id": "patient-001",
    "demographics": {},
    "vitals": [],
    "labs": [],
    "medications": [],
    "clinical_notes": [],
    "imaging_metadata": []
  }
}
```

The agent also accepts a raw `RawPatientContext`-shaped payload directly. This keeps it compatible
with API workflows, worker jobs, evaluation fixtures, and future MCP-compatible tools.

## Structured Patient Representation Schema

The agent emits `PatientContextAgentRepresentation`:

- `patient_id`;
- `context_id`;
- `generated_at`;
- `modality_summaries`;
- `temporal_summary`;
- `missingness_summary`;
- `retrieval_profile`;
- `explainability_profile`;
- `safety_profile`;
- `modality_fusion_inputs`;
- `validation_findings`.

Each modality summary includes:

- modality name;
- present/absent flag;
- record count;
- missing field count;
- quality finding count.

The full normalized `StructuredPatientContext` is also included in `AgentOutput.structured_payload`
so downstream systems can inspect source records when needed.

## Temporal Processing Utilities

`temporal.py` provides timeline summaries over normalized `TimelineEvent` records:

- total event count;
- events with and without timestamps;
- first and last event time;
- per-modality event counts;
- temporal completeness score.

Temporal processing preserves the distinction between observed and recorded timestamps from the
underlying patient context model. The agent summarizes temporal readiness without inferring disease
state or outcomes.

## Modality Fusion Preparation

The agent prepares a modality fusion input block:

- context ID;
- patient ID;
- available modalities;
- per-modality record counts;
- timeline event count;
- retrieval terms;
- note types;
- fusion readiness flag.

This lets future multimodal orchestration decide whether a case can flow into text-only retrieval,
temporal reasoning, imaging-aware review, note summarization, or human review.

## Confidence Metadata

Confidence is a structured `ConfidenceScore` with component scores:

- modality coverage;
- temporal completeness;
- validation quality;
- missingness quality;
- provenance quality.

Bands:

- `high`: strong modality, timestamp, validation, and provenance coverage;
- `moderate`: usable context with some missingness or provenance limitations;
- `low`: incomplete or weakly timestamped context;
- `unknown`: insufficient structured context.

Confidence is not clinical certainty. It describes readiness and reliability of the structured
patient context for downstream infrastructure.

## Tracing Integration

The agent uses `AgentTraceContext` from the shared agent contracts:

- workflow ID;
- trace ID;
- agent run ID;
- request ID;
- correlation ID;
- parent agent run ID.

The same trace context is returned in `AgentOutput`, allowing the orchestrator to connect Patient
Context Agent output to Evidence Retrieval Agent, Risk Analysis Agent, Safety Critic, evaluation, and
audit events.

## Observability Hooks

The agent emits structured logs:

- `agent_run_started`;
- `agent_run_completed`;
- `agent_run_failed`.

Important log fields:

- agent name;
- agent role;
- workflow ID;
- trace ID;
- agent run ID;
- case ID;
- status;
- confidence score;
- confidence band;
- latency;
- validation finding count.

Logs avoid raw clinical note bodies and large patient payloads. The response can carry structured
context, but infrastructure logs should use identifiers, counts, and quality signals.

## Downstream Support

Retrieval:

- emits query terms from vitals, labs, medications, notes, and imaging metadata;
- preserves context and patient IDs;
- exposes normalized modality summaries for query construction.

Explainability:

- provides source systems, available modalities, validation findings, and timeline summaries;
- retains the full structured patient context as an auditable payload.

Risk analysis:

- exposes missingness, validation severity, temporal completeness, and provenance quality;
- marks outputs that require human review.

Safety evaluation:

- sets `safe_for_diagnosis_prediction` to false;
- separates quality findings from clinical conclusions;
- provides future Safety Critic hooks through the shared agent output contract.

Future multimodal fusion:

- exposes modality availability and record counts;
- keeps modality-specific normalized records in the structured patient context;
- avoids collapsing all inputs into a text-only summary.

## Non-Goals

- no diagnosis prediction;
- no treatment recommendation;
- no imputation of missing values;
- no hidden feature engineering;
- no autonomous clinical decision-making.

The Patient Context Agent is a reliability and orchestration component. It makes patient context
explicit, structured, traceable, and ready for downstream systems that can reason over evidence,
risk, safety, and explainability.
