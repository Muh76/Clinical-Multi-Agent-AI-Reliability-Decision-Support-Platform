# End-To-End Evidence Grounding Workflow

This workflow is the first platform path that connects patient context processing to evidence
retrieval, reranking, evidence packaging, and trace logging. It is intentionally not a predictive
model and does not generate clinical recommendations. It prepares a grounded evidence response that
downstream answer generation, explainability, hallucination detection, and future Safety Critic
validation can inspect.

## Orchestration Flow

```text
POST /api/v1/workflows/evidence-grounding
  -> ingest synthetic or MIMIC-shaped patient case from request payload
  -> process patient context with PatientContextProcessor
  -> prepare retrieval query from explicit query or patient context retrieval terms
  -> retrieve candidate evidence
  -> rerank evidence candidates
  -> package grounded evidence response
  -> emit structured workflow trace logs
  -> return evidence, citations, confidence, metadata, and trace IDs
```

The first implementation uses a lightweight local evidence retriever over request-supplied evidence
snippets. That keeps the workflow deterministic and testable while preserving the service boundary
needed to swap in Qdrant-backed hybrid retrieval later.

## Async Workflow Service

The workflow service is `EvidenceGroundingWorkflowService`.

Responsibilities:

- assign `workflow_id` and `trace_id`;
- bind workflow IDs into structured logging context;
- process patient context through the multimodal package;
- derive a retrieval query from context when the caller does not provide one;
- retrieve and rerank candidate evidence;
- produce citations and confidence scores;
- return a trace of every workflow step;
- raise a structured application error when the workflow cannot produce a grounded response.

The current endpoint is synchronous from the API caller's perspective but implemented as an async
service method. Later versions can move the same service call into a worker queue without changing
the response contract.

## Evidence Response Schema

Response fields include:

- `workflow_id`;
- `status`;
- `case_id`;
- `patient_id`;
- `context_id`;
- `evidence`;
- `citations`;
- `confidence_score`;
- `retrieval_metadata`;
- `trace`;
- `safety_critic_integration_points`.

Each evidence item contains:

- rank;
- source ID and source type;
- evidence text;
- citation payload;
- final score;
- retrieval score;
- rerank score;
- source reliability score;
- confidence score;
- source metadata.

This gives downstream systems the evidence package, citation allow-list, score components, and trace
IDs needed for grounding checks.

## Workflow Tracing

Every workflow run emits:

- `workflow_id`: stable ID for the workflow execution;
- `trace_id`: trace ID for all workflow steps;
- `request_id`: inbound HTTP request ID;
- `correlation_id`: inbound workflow or caller correlation ID;
- step name;
- step status;
- step start and completion time;
- latency in milliseconds;
- step metadata;
- error detail for failed steps.

Current steps:

- `ingest_patient_case`;
- `process_patient_context`;
- `prepare_retrieval_query`;
- `retrieve_evidence`;
- `rerank_evidence`;
- `package_grounded_evidence_response`.

## Observability Hooks

The workflow logs:

- `evidence_workflow_started`;
- `evidence_workflow_step_completed`;
- `evidence_workflow_step_failed`;
- `evidence_workflow_completed`;
- `evidence_workflow_failed`.

Useful fields:

- workflow ID;
- trace ID;
- case ID;
- patient ID;
- context ID;
- candidate count;
- retrieved count;
- citation count;
- confidence score;
- latency;
- validation finding count.

This makes workflow behavior queryable without logging raw clinical notes or large evidence bodies in
normal application logs.

## Structured Logging

The API already binds request and correlation IDs through tracing middleware. The workflow service
adds workflow-level context using `bind_execution_context()`, so request logs, workflow logs,
retrieval logs, and future Safety Critic logs can be connected.

Log payloads should prefer stable identifiers, counts, scores, and risk labels over raw clinical
content. Raw patient text and note bodies should remain in controlled storage and response payloads,
not broad infrastructure logs.

## Error Handling

The service wraps unexpected workflow failures in an `AppError` with code
`evidence_workflow_failed`. Failed steps are added to the trace before the exception is raised, and
the structured logger records the step name, latency, and error type.

Expected future failure classes:

- invalid patient context;
- unsupported source modality;
- retrieval backend unavailable;
- empty evidence package when evidence is required;
- citation packaging failure;
- Safety Critic block verdict.

## Future Safety Critic Integration Points

The response includes explicit Safety Critic integration points:

- `citation_allow_list`: already available from packaged citations;
- `grounding_consistency_check`: planned check between candidate answer, evidence, and citations;
- `recommendation_strength_review`: planned check that final recommendations do not exceed evidence
  strength or ignore low-confidence retrieval.

Future Safety Critic inputs:

- structured patient context;
- retrieved evidence;
- citations;
- confidence scores;
- source reliability scores;
- retrieval metadata;
- workflow trace IDs;
- validation findings.

## Orchestration Design

The workflow keeps each step narrow and observable. Patient context processing is separate from
retrieval. Retrieval is separate from reranking. Reranking is separate from evidence packaging. This
keeps failures attributable and lets future workers retry or replace individual steps.

The first retrieval implementation is local and deterministic. Production retrieval can replace it
with the existing Qdrant, BM25, hybrid fusion, and cross-encoder reranking stack while preserving the
same response schema.

## Workflow Reliability

Reliability comes from explicit contracts:

- strict request schemas;
- patient context validation findings;
- trace IDs on every run;
- per-step latency and status;
- citation allow-list;
- score component exposure;
- structured application errors.

The workflow does not hide low confidence. If no evidence is retrieved, it returns an empty evidence
list, no citations, and a low confidence score so downstream systems can abstain or request review.

## Evidence Traceability

Every returned evidence item carries a citation. Citations include source ID, source type, title,
URL, publication year, quote preview, and attribution text. This supports citation verification and
lets explainability views show exactly which evidence was available to downstream agents.

Workflow trace IDs connect the evidence response back to logs and future audit records.

## Future Scalability

The service can scale in stages:

- replace local evidence retrieval with Qdrant hybrid retrieval;
- move long-running workflows to Redis-backed or database-backed job queues;
- store workflow traces and evidence packages as audit records;
- add OpenTelemetry spans around each workflow step;
- call Safety Critic after evidence packaging;
- split patient context processing, retrieval, and safety validation into worker tasks;
- cache retrieval results by context and query fingerprint.

The response contract is designed to survive those changes: callers receive grounded evidence,
citations, confidence, retrieval metadata, and trace IDs regardless of the execution backend.
