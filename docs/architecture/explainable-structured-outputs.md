# Explainable Structured Output System

The explainable structured output system provides platform-wide schemas for evidence attribution,
confidence visibility, traceable reasoning metadata, modality contributions, risk contribution
summaries, citation formatting, and serialization. It is explainability infrastructure, not
conversational response generation.

Consumers:

- clinician dashboards;
- future audit systems;
- Safety Critic agents;
- evaluation pipelines;
- observability systems.

## Output Schemas

Core package:

```text
packages/shared/src/clinical_ai_shared/explainability.py
```

Primary schema:

```text
ExplainableOutput
  -> WorkflowTraceLink
  -> EvidenceAttribution[]
  -> ConfidenceRepresentation
  -> ReasoningMetadata[]
  -> ModalityContribution[]
  -> RiskContributionSummary[]
  -> CitationFormat[]
  -> structured_payload
```

The schema is intentionally generic so agent outputs, workflow outputs, Safety Critic decisions,
evaluation reports, and clinician dashboard cards can share one explainability contract.

## Evidence Attribution Format

`EvidenceAttribution` preserves:

- evidence ID;
- citation ID;
- source ID;
- source type;
- title;
- URL;
- publication year;
- section path;
- quote preview;
- relevance score;
- source reliability score;
- attribution text.

This format supports citation verification, hallucination detection, dashboard source panels, and
future audit storage.

## Confidence Representation

`ConfidenceRepresentation` includes:

- score;
- band;
- component scores;
- rationale;
- calibration notes.

Confidence is visible and decomposed. It should not be hidden behind a single opaque scalar. Safety
Critics and evaluation pipelines can inspect component-level confidence such as retrieval confidence,
source reliability, grounding consistency, temporal completeness, or uncertainty penalties.

## Explainability Metadata

`ReasoningMetadata` stores traceable reasoning metadata without requiring free-form chain-of-thought.
It includes:

- reasoning ID;
- summary;
- method;
- input references;
- evidence references;
- risk factor references;
- limitations;
- generated timestamp.

The goal is to make the system explainable and auditable without exposing private hidden reasoning or
turning explanations into unstructured prose.

## Modality Contribution Structure

`ModalityContribution` captures how each modality contributed:

- modality name;
- present/absent flag;
- record count;
- contribution direction;
- contribution score;
- summary;
- source references;
- missingness notes.

Contribution directions include:

- increases risk;
- decreases risk;
- supports evidence;
- contradicts evidence;
- contextual;
- unknown.

This gives dashboards and multimodal orchestration a stable way to show which modalities mattered and
which were missing.

## Workflow Trace Linkage

`WorkflowTraceLink` connects output records to execution:

- workflow ID;
- trace ID;
- case ID;
- request ID;
- correlation ID;
- agent run IDs;
- node IDs.

Trace linkage lets audit systems and observability tools connect a structured output back to the
workflow graph, agent runs, evidence retrieval, Safety Critic review, and human approvals.

## Citation Formatting

Citation utilities:

- `citation_display_text()`;
- `format_citation()`;
- `attach_formatted_citations()`.

Formatted citations provide:

- citation ID;
- display text;
- source label;
- inline marker;
- URL.

The formatter derives stable display citations from evidence attribution records. Downstream answer
generation should still cite only IDs present in the citation allow-list.

## Serialization Utilities

Serialization helpers:

- `serialize_explainable_output()`;
- `serialize_explainable_output_json()`;
- `redacted_observability_payload()`.

The normal serializers include structured output details and formatted citations. The redacted
observability payload keeps only IDs, counts, confidence, audience, and trace fields so logs do not
carry raw clinical notes or long evidence passages.

## Dashboard Support

Clinician dashboards can render:

- confidence score and component breakdown;
- evidence cards with citations;
- modality contribution panels;
- risk factor summaries;
- trace IDs for audit lookup;
- limitation and uncertainty panels.

The schema avoids conversational assumptions so dashboards can display structured facts rather than
generated narrative.

## Safety Critic Support

Safety Critics can inspect:

- evidence attribution and citation allow-list;
- confidence components;
- risk contributions;
- modality missingness;
- reasoning metadata limitations;
- trace IDs.

This supports blocking, qualifying, or escalating outputs without parsing free text.

## Evaluation And Audit Support

Evaluation pipelines can compare:

- cited evidence IDs;
- confidence calibration;
- modality contribution coverage;
- risk contribution labels;
- reasoning limitations;
- trace completeness.

Audit systems can persist the same records as append-only explainability artifacts linked to workflow
and agent run IDs.

## Observability Support

Observability systems should use `redacted_observability_payload()` for logs and metrics. This emits
counts, IDs, confidence, and trace metadata while avoiding raw patient content.

The structured output system is the shared explanation layer under agents, workflows, safety checks,
evaluation reports, dashboards, and audit records.
