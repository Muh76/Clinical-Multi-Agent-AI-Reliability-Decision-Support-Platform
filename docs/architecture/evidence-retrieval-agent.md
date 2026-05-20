# Evidence Retrieval Agent

The Evidence Retrieval Agent retrieves trustworthy, evidence-grounded clinical information relevant
to structured patient context. It focuses on evidence grounding and retrieval reliability, not answer
generation. Its output is a traceable evidence package that downstream explainability, risk analysis,
hallucination detection, Safety Critic, and audit workflows can inspect.

Data sources:

- PubMed;
- NICE guidelines;
- synthetic protocols;
- indexed medical evidence;
- future local policy and curated evidence corpora.

## Evidence Retrieval Agent Architecture

```text
AgentInput
  -> EvidenceRetrievalAgent
  -> RetrievalQuery construction
  -> metadata-aware filters
  -> hybrid retrieval backend
  -> reranking
  -> citation preservation
  -> confidence scoring
  -> relevance reasoning
  -> AgentOutput
```

Implementation:

```text
packages/agents/src/clinical_ai_agents/evidence_retrieval.py
```

The preferred execution path uses an injected `EvidencePackager` from `clinical_ai_retrieval`, which
can run Qdrant dense retrieval, BM25 lexical retrieval, hybrid fusion, reranking, reliability scoring,
and citation packaging. The agent also includes a deterministic request-local corpus fallback for
tests and early workflows.

## Retrieval Orchestration

The agent builds a `RetrievalQuery` from structured payload fields:

- query text;
- source type filters;
- clinical domain filters;
- patient and encounter filters;
- guideline organization;
- imaging modality and body part;
- publication year bounds;
- evidence level;
- retrieval mode;
- fusion strategy;
- dense and BM25 weights;
- reranking flag;
- top-k and candidate limits.

If no explicit query is supplied, the agent can derive a query from the patient context retrieval
profile emitted by the Patient Context Agent.

## Reranking Workflow

Production reranking happens inside the injected retrieval backend:

```text
dense candidates + BM25 candidates
  -> fusion
  -> cross-encoder reranker
  -> source reliability scoring
  -> EvidencePackage
```

The fallback local retriever uses lexical overlap, title overlap, and source reliability to simulate
deterministic ranking. This is not a production biomedical retriever; it is a development seam that
keeps the agent contract testable without requiring Qdrant or model downloads.

## Evidence Packaging Schema

The agent emits `EvidenceRetrievalAgentPackage`:

- query;
- retrieved evidence items;
- citations;
- retrieval confidence;
- retrieval metadata;
- relevance reasoning.

Each evidence item contains:

- rank;
- chunk ID;
- document ID;
- source ID;
- source type;
- title;
- text;
- citation ID;
- score;
- confidence score;
- source reliability score;
- scoring components;
- metadata;
- relevance reasoning.

Each citation contains:

- citation ID;
- source type;
- source ID;
- title;
- URL;
- publication year;
- section path;
- quote preview;
- attribution text.

## Confidence Scoring Logic

The agent computes an agent-level confidence score from:

- retrieval confidence;
- citation integrity;
- source reliability;
- reranking availability;
- source diversity.

Confidence bands:

- `high`: evidence is well-grounded with valid citations and reliable sources;
- `moderate`: evidence is usable but has source or retrieval limitations;
- `low`: evidence is weakly grounded;
- `unknown`: no evidence was retrieved.

Confidence is retrieval readiness, not clinical certainty.

## Source Attribution System

The agent preserves citations from the retrieval package. Generated downstream answers should only
cite IDs from the returned citation allow-list.

Attribution supports:

- citation verification;
- answer grounding checks;
- hallucination detection;
- explainability views;
- Safety Critic validation;
- audit event storage.

Synthetic protocols are explicitly lower-reliability evidence and should not be treated as clinical
authority when guideline or validated policy evidence is available.

## Tracing Integration

The agent uses the shared `AgentTraceContext`:

- workflow ID;
- trace ID;
- agent run ID;
- request ID;
- correlation ID;
- parent agent run ID.

The same trace context is returned in `AgentOutput` so the orchestrator can connect evidence
retrieval to patient context preparation, risk analysis, Safety Critic review, evaluation replay, and
audit records.

## Observability Hooks

The agent logs:

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
- retrieved count;
- citation count;
- confidence score;
- confidence band;
- latency.

Logs should not include full evidence bodies by default. Evidence text belongs in controlled response
payloads or audit storage, while logs should prefer IDs, counts, scores, and risk labels.

## Structured Outputs

The agent returns a standard `AgentOutput` with:

- human-readable summary;
- structured evidence package;
- retrieval query;
- findings;
- confidence;
- citation allow-list;
- explainability metadata;
- Safety Critic hooks.

Safety hooks include:

- citation allow-list;
- grounding check required flag;
- Safety Critic requirement flag;
- `answer_generation_performed=false`.

This makes the boundary clear: the agent retrieves evidence; it does not answer the clinical
question.

## Relevance Reasoning

Each evidence item includes a short relevance rationale:

- matched query terms;
- source type;
- source reliability score;
- rank.

This is designed for explainability and debugging. It is not a chain-of-thought artifact and should
not be treated as clinical reasoning.

## Non-Goals

- no answer generation;
- no diagnosis prediction;
- no treatment recommendation;
- no citation fabrication;
- no hidden use of non-retrieved sources.

The Evidence Retrieval Agent exists to make retrieved evidence reliable, citeable, scored, traceable,
and ready for downstream safety infrastructure.
