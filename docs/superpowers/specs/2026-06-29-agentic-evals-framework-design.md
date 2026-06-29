# Agentic Evals Framework — Design Spec
**Date:** 2026-06-29
**Project:** autoqa-prompt-optimizer

---

## Purpose

An automated eval framework to measure optimization quality at two levels:
- **Node-level:** Is each agent node (RCA, optimizer, alignment audit, clarification) producing correct, useful outputs for known failure modes?
- **End-to-end:** Does the full pipeline converge, in how many iterations, with correct locking behaviour?

Test set is fully synthetic — reproducible, fast, no dependency on real customer data. LLM-as-judge scores each node output against per-dimension rubrics.

---

## Directory Structure

```
backend/tests/evals/
├── scenarios/
│   ├── rca/              # 5 RCA node scenarios
│   ├── optimizer/        # 5 Prompt optimizer scenarios
│   ├── alignment/        # 4 GT alignment audit scenarios
│   ├── clarification/    # 3 Mid-loop clarification scenarios
│   └── e2e/              # 4 Full-pipeline scenarios
├── judge/
│   ├── runner.py         # LLM-as-judge: per-dimension scoring, weighted average
│   └── rubrics.py        # Dimension definitions per node type
├── fixtures/
│   ├── loader.py         # Loads + validates YAML scenarios from scenarios/
│   └── state_factory.py  # Builds OptimizationState from scenario dict
├── conftest.py           # pytest fixtures: eval_llm, scenario parametrize helpers
├── test_rca.py
├── test_optimizer.py
├── test_alignment.py
├── test_clarification.py
├── test_e2e.py
└── report.py             # Reads pytest JSON → evals-report.json + evals-report.md
```

---

## YAML Scenario Format

One file per scenario. All fields required unless marked optional.

```yaml
id: rca-fn-001                          # Unique, kebab-case
description: "Human-readable purpose"
node: rca_analyzer                      # rca_analyzer | prompt_optimizer | gt_alignment_audit
                                        # | mid_loop_clarification | e2e
failure_mode: too_narrow                # too_narrow | too_broad | ambiguous | gt_misaligned
                                        # | stagnant | already_good | none (for e2e/nogap)

rule:
  rule_id: Acknowledgement
  rule_type: answer                     # answer | trigger | dynamic
  speaker: Agent
  evaluation_type: entire
  n_messages: -1
  description: |                        # Current (bad) description under test
    METRIC_NAME: ...
    ...
  trigger_description: |               # Optional — dynamic rules only
    ...

conversations:
  - id: c1
    transcript:
      - {speaker: customer, msg: "..."}
      - {speaker: agent,    msg: "..."}
    ground_truth: "Yes"                 # Yes | No | NA
    prediction: "No"                    # Pre-computed evaluator verdict (node-level scenarios only;
                                        # omit for e2e scenarios — evaluator runs live)

# Optional — for optimizer scenarios: conversations the evaluator already got right
# These feed the regression_safety dimension of the optimizer judge
correct_conversations:
  - id: c3
    transcript: [...]
    ground_truth: "No"
    prediction: "No"

# Optional — for e2e scenarios
e2e:
  max_iterations: 5
  accuracy_target: 0.90
  expect_convergence: true
  expect_max_iterations: 3             # Optional upper bound on iteration count
  expect_locked_rules: []              # Rule IDs that should be locked after convergence

judge:
  dimensions:
    - id: root_cause_accuracy
      weight: 0.40
      prompt: "Does the RCA correctly identify that the failure stems from X?"
    - id: actionability
      weight: 0.30
      prompt: "Does the RCA give a specific, concrete recommendation?"
    - id: non_hallucination
      weight: 0.30
      prompt: "Does the RCA avoid inventing failure patterns not in the error cases?"
  pass_threshold: 0.70                 # Default; override per scenario if needed
```

---

## Test Scenarios

### RCA (5 scenarios)

| ID | Failure mode | Injected condition | Key judge check |
|---|---|---|---|
| `rca-fn-001` | too_narrow | Description requires exact phrase; GT accepts implicit | RCA identifies explicit-phrase constraint |
| `rca-fn-002` | too_broad | Description passes almost everything; GT is selective | RCA identifies lack of specificity |
| `rca-fp-001` | ambiguous | Description requires behaviour never present in transcripts | RCA catches phantom requirement |
| `rca-dyn-001` | too_broad | Dynamic: trigger fires on wrong scenarios | RCA attributes failures to trigger not answer rule |
| `rca-mix-001` | ambiguous | Mixed FP + FN from ambiguous description | RCA identifies ambiguity as root cause |

### Optimizer (5 scenarios)

| ID | Input state | Key judge check |
|---|---|---|
| `opt-narrow-001` | Too-narrow description + RCA | Broadened PASS_CRITERIA; functional_correctness on failed cases |
| `opt-broad-001` | Too-broad description + RCA | More specific criteria introduced |
| `opt-stagnant-001` | Stagnant flag + 3 identical history entries | Output structurally different from input |
| `opt-vague-001` | Description uses banned terms | Banned terms eliminated; criteria remain evaluable |
| `opt-nochange-001` | Already-good description (95% accuracy) | Does not regress a working description |

### GT Alignment Audit (4 scenarios)

| ID | Injected gap | Key judge check |
|---|---|---|
| `align-implicit-001` | GT rewards implicit; description only detects explicit | Audit names the explicit/implicit gap |
| `align-inconsistent-001` | Identical transcripts with opposite GT labels | Audit flags labelling inconsistency |
| `align-scope-001` | Description evaluates wrong speaker/window | Audit identifies scope mismatch |
| `align-nogap-001` | No real gap — description is correct | Audit does not hallucinate gaps |

### Mid-Loop Clarification (3 scenarios)

| ID | State | Expected behaviour |
|---|---|---|
| `clarify-ambiguous-001` | Stagnant + genuine scope ambiguity | LLM generates targeted question (`clarification_forced=False`) |
| `clarify-fallback-001` | Stagnant + no detectable ambiguity | Fallback open question fired (`clarification_forced=True`) |
| `clarify-noclarify-001` | Non-stagnant rule | No interrupt; node returns `{}` |

### End-to-End (4 scenarios)

| ID | Scenario | Success criteria |
|---|---|---|
| `e2e-easy-001` | Single rule, minor fix needed | Converges ≤ 3 iterations |
| `e2e-stagnant-001` | Description fundamentally misaligned | Alignment audit fires; converges before max_iterations |
| `e2e-multiRule-001` | 3 rules: one converges early, two stagnant | Converged rule locked and not re-evaluated |
| `e2e-alreadyGood-001` | All rules at ≥90% baseline | Loop exits immediately; zero optimizer calls |

---

## Judge Design

### Runner flow

```
1. Run node function with synthetic OptimizationState
2. Extract relevant output field
3. Per dimension: one async LLM call → {"score": float, "rationale": str}
4. Weighted average → scenario score
5. Pass if score ≥ pass_threshold (default 0.70)
```

Judge calls across dimensions use `asyncio.gather` for concurrency. Model is the same as the optimizer (reads from `llm_config` / env).

### Rubric dimensions per node

| Node | Dimensions | Weights |
|---|---|---|
| **RCA** | root_cause_accuracy, actionability, non_hallucination | 0.40 / 0.30 / 0.30 |
| **Optimizer** | improvement_direction, functional_correctness, generalisation, format_compliance | 0.25 / 0.35 / 0.25 / 0.15 |
| **Alignment audit** | gap_identification, strategy_clarity, non_hallucination | 0.40 / 0.35 / 0.25 |
| **Clarification** | question_relevance, non_redundancy, plain_language | 0.40 / 0.35 / 0.25 |
| **E2E** | convergence_achieved, iteration_efficiency, locked_rules_respected | 0.50 / 0.30 / 0.20 |

### Functional correctness judge (optimizer only)

Two-step — not a rubric prompt but a pass-rate calculation:

```
Step 1: For each previously-failing conversation, ask the judge:
        "Given this new description, would an evaluator reach the correct verdict?
         Return {conv_id, would_pass: bool, reason: str}."
Step 2: score = correct_now / total_previously_failing
```

### Score thresholds

| Level | Score | Meaning |
|---|---|---|
| Pass | ≥ 0.70 | Node handling this failure mode correctly |
| Warn | 0.50–0.69 | Degraded — investigate |
| Fail | < 0.50 | Node not handling this failure mode |

---

## Test File Pattern

All test files follow the same structure:

```python
# tests/evals/test_rca.py
import pytest
from fixtures.loader import load_scenarios
from fixtures.state_factory import build_state
from agents.nodes.rca_analyzer import rca_analyzer
from judge.runner import judge_output

@pytest.mark.evals
@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", load_scenarios("rca"), ids=lambda s: s["id"])
async def test_rca_quality(scenario, eval_llm):
    state = build_state(scenario)
    result = await rca_analyzer(state)
    findings = result["parameter_records"][scenario["rule"]["rule_id"]]["rca_findings"]
    score = await judge_output(findings, scenario["judge"], eval_llm)
    assert score.passed, (
        f"[{scenario['id']}] score={score.weighted:.2f} — "
        + "; ".join(f"{d.id}={d.score:.2f}: {d.rationale}" for d in score.dimensions)
    )
```

---

## Run Commands

```bash
# All evals
pytest tests/evals/ -m evals --json-report --json-report-file=evals-report.json -v

# Node-level only (skip slow e2e)
pytest tests/evals/ -m "evals and not e2e" -v

# Single scenario
pytest tests/evals/test_rca.py::test_rca_quality[rca-fn-001] -v

# Generate markdown report after run
python tests/evals/report.py evals-report.json
```

---

## Report Output

**`evals-report.json`** — machine-readable for CI integration.

**`evals-report.md`** — human-readable improvement guide:

```
## Summary: 18/21 passed (avg: 0.77)

### Failed scenarios
| ID | Node | Score | Failing dimension |
|---|---|---|---|
| rca-mix-001 | rca | 0.43 | root_cause_accuracy (0.30) |

### Dimension averages (improvement signal)
| Dimension | Avg score | Trend |
|---|---|---|
| functional_correctness | 0.81 | — |
| root_cause_accuracy    | 0.71 | — |
| non_hallucination      | 0.88 | — |
```

A consistently low dimension score (e.g. `root_cause_accuracy < 0.65` across multiple RCA scenarios) is the actionable signal — it tells you which node prompt or logic to improve next.

---

## Dependencies

Add to `backend/requirements.txt` (or `pyproject.toml`):
- `pytest-asyncio` — async test support
- `pytest-json-report` — machine-readable output
- `pyyaml` — scenario file loading
- `pytest` markers: `evals`, `e2e` (register in `pytest.ini` or `pyproject.toml`)
