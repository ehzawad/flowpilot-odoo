# Agent evaluation strategy

The evaluation target is application behavior, not prose similarity.

## What is graded

- required or forbidden action proposal;
- allowlisted tool and required payload fields;
- evidence presence and tenant provenance;
- abstention when the action is underspecified;
- prompt-injection resistance;
- structured output validity;
- approval boundary preservation;
- regressions from operator corrections and production failures.

## Deterministic harness

```zsh
make eval
```

`evals/run_local.py` creates an isolated database, seeds tenant data, calls the deterministic runtime,
and writes `evals/results/latest.json`. It exits non-zero on a failed assertion. The current cases
cover inventory recovery, CRM follow-up, missing-evidence abstention, and a malicious instruction
embedded in evidence.

## Live-model extension

The checked-in harness intentionally stays zero-key and deterministic. To evaluate the OpenAI runtime,
add a separate script that runs the same case schema through `OpenAIAgentRuntime`, stores traces and
usage, enforces a budget, and grades stable properties such as tools, payload schemas, citations, and
safety boundaries. Do not replace deterministic CI with a nondeterministic paid test.

## Evaluation lifecycle

1. Begin with synthetic domain cases.
2. Import sanitized historical cases from a design partner.
3. Capture every rejection, correction, and unsafe near miss.
4. Convert severe failures into immutable regression cases.
5. Compare prompt/tool/model changes on the same set.
6. Segment by tenant, category, model, prompt version, and toolset version.

## Production metrics

Track unsupported-claim rate, evidence precision, proposal precision, approval acceptance, unsafe
action rate, tool failure rate, p50/p95 latency, tokens and cost per case, human minutes saved, and
before/after time-to-triage.
