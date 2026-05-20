# Risk Analysis Agent

The Risk Analysis Agent performs risk-oriented reliability analysis over structured patient context
and retrieved evidence. It does not generate diagnoses, treatment instructions, or clinical
recommendations. Its purpose is to identify high-risk situations, unstable trends, contradictory
evidence, escalation conditions, and uncertainty patterns so downstream systems can route, explain,
review, or abstain safely.

## Risk Analysis Agent Architecture

```text
AgentInput
  -> RiskAnalysisAgent
  -> structured patient context extraction
  -> retrieved evidence extraction
  -> clinical-context risk factor scan
  -> temporal trend analysis
  -> contradiction detection
  -> escalation trigger evaluation
  -> uncertainty profiling
  -> confidence scoring
  -> AgentOutput
```

Implementation:

```text
packages/agents/src/clinical_ai_agents/risk_analysis.py
```

The agent consumes outputs from the Patient Context Agent and Evidence Retrieval Agent, but it can
also accept raw patient context and evidence-shaped dictionaries for evaluation fixtures and early
workflow integration.

## Risk Scoring Pipeline

The risk score is an explainable aggregate of:

- context risk factors;
- temporal trend signals;
- escalation indicators;
- evidence contradiction signals;
- uncertainty penalties.

Risk levels:

- `low`: minor or weakly supported risk signals;
- `moderate`: meaningful risk indicators or unstable context;
- `high`: high-severity factors, contradiction, or review-worthy escalation condition;
- `critical`: multiple severe factors or strongly escalated context;
- `unknown`: insufficient structured data to evaluate.

The score is not a diagnosis probability. It is a routing and reliability signal for workflow
governance.

## Temporal Trend Analysis

The agent groups vitals and labs by normalized name, orders records by observed or recorded time, and
compares the first and last values when at least two observations exist.

Trend output includes:

- modality;
- signal name;
- direction: increasing, decreasing, or stable;
- first and last value;
- unit;
- observation count;
- confidence;
- explanation.

Trend confidence increases with repeated observations and timestamp completeness. The trend detector
does not infer disease state or causal relationships.

## Escalation Trigger Framework

Escalation indicators are structured routing flags. Initial triggers include:

- high-severity context factor present;
- unstable temporal trend present;
- contradictory evidence present.

Each indicator includes:

- code;
- risk level;
- message;
- contributing factors;
- evidence references;
- human-review flag.

The framework is designed to support future policy-driven escalation rules, Safety Critic review,
and human-in-the-loop workflows.

## Contradiction Detection Design

The first contradiction detector is deliberately conservative. It scans retrieved evidence for
recommendation language, avoidance language, and uncertainty language.

Signals include:

- evidence contains both recommendation and avoidance terms;
- evidence contains limited-evidence or uncertainty terms.

This is not a final clinical adjudicator. It is an evidence reliability warning that downstream
systems should review before presenting grounded recommendations.

## Explainability Metadata

The agent emits:

- top risk factor codes;
- trend signal IDs;
- escalation codes;
- contradiction codes;
- explicit analysis boundary: risk-oriented reliability analysis, no diagnosis generated.

Every factor can carry source references and evidence references, making UI explanation, audit, and
Safety Critic handoff easier.

## Confidence Scoring

Confidence is computed from:

- context completeness;
- evidence support;
- trend confidence;
- uncertainty penalty;
- contradiction penalty.

Confidence describes reliability of the risk analysis, not certainty about a medical condition.
Contradictory evidence and missing modalities reduce confidence.

## Structured Outputs

The agent returns standard `AgentOutput` with:

- summary;
- structured `RiskAnalysisReport`;
- findings;
- confidence;
- evidence references;
- explainability metadata;
- safety hooks.

`RiskAnalysisReport` includes:

- risk level;
- risk score;
- contributing factors;
- trend signals;
- escalation indicators;
- contradiction signals;
- evidence references;
- uncertainty metadata;
- explainability metadata.

## Healthcare Risk Analysis Considerations

Healthcare risk analysis must preserve uncertainty and source context. A single abnormal value, a
short note, or an isolated study rarely tells the whole story. The agent therefore reports signals
and limitations instead of clinical conclusions.

Important considerations:

- missing modalities can make risk analysis incomplete;
- timestamps may reflect charting time rather than observed event time;
- trends are sensitive to sparse data and unit consistency;
- medication risk depends on dose, timing, indication, and patient context;
- evidence can be stale, contradictory, or lower authority than guidelines.

## Uncertainty Handling

The agent tracks:

- absent modalities;
- missing field count;
- evidence count;
- contradiction count;
- timestamped context fraction;
- explicit limitations.

Uncertainty appears in both the report and confidence components so downstream orchestration can
qualify, escalate, abstain, or request human review.

## Explainability Strategies

The output is explainable by construction:

- every risk factor has a code and message;
- factors can reference patient-context source fields;
- evidence-aware findings carry citation or source references;
- trend signals include values, direction, and observation count;
- escalation indicators list contributing factors.

This avoids opaque risk labels and supports audit, evaluation, and user-facing explanation.

## Escalation Logic Principles

Escalation should be conservative, explicit, and auditable:

- escalate high-severity structured signals;
- escalate contradictory evidence before recommendation workflows;
- escalate when uncertainty is high and downstream action would be risky;
- prefer human review over false certainty;
- keep escalation rules separate from diagnosis prediction.

The Risk Analysis Agent is a safety infrastructure component. It identifies reliability-relevant risk
signals and uncertainty patterns so the platform can behave cautiously and transparently.
