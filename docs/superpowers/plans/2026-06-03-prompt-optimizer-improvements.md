# Prompt Optimizer Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve optimization quality by locking converged rules from re-evaluation, guarding against description regressions, adopting a structured description format from the metric guide, rewriting descriptions from clarification answers, and raising the accuracy target to 90%.

**Architecture:** Seven targeted changes to state, benchmarking, evaluator, baseline_prompt_generator, prompt_optimizer, finalize, and the API default. No new nodes or graph edges needed. Changes are additive to existing TypedDict fields and node logic.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, Pydantic v2, pytest

---

## File Map

| File | Change |
|---|---|
| `backend/agents/state.py` | Add `initial_accuracy`, `best_accuracy`, `best_description` to `RuleRecord` |
| `backend/agents/nodes/csv_ingestion.py` | Initialize three new fields to `None` |
| `backend/agents/nodes/benchmarking.py` | Lock converged rules; regression guard (revert on drop) |
| `backend/agents/nodes/evaluator.py` | Skip reset + evaluation for converged rules |
| `backend/agents/nodes/baseline_prompt_generator.py` | Structured format output; clarification-anchored rewrite |
| `backend/agents/nodes/prompt_optimizer.py` | Structured format output |
| `backend/agents/nodes/finalize.py` | Flag regression rules in report with next steps |
| `backend/api/routes/sessions.py` | Default `accuracy_target` 0.80 → 0.90 |
| `backend/tests/test_benchmarking.py` | New: regression guard + converged locking |
| `backend/tests/test_evaluator_skip.py` | New: converged rules skipped in evaluator |

---

## Task 1 — State schema + csv_ingestion initialization

**Files:**
- Modify: `backend/agents/state.py`
- Modify: `backend/agents/nodes/csv_ingestion.py`

- [ ] **Step 1: Add three new fields to `RuleRecord` in `state.py`**

Open `backend/agents/state.py`. Add `Optional` import and three new fields to `RuleRecord` after `status`:

```python
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict


class RuleRecord(TypedDict):
    rule_id: str
    rule_type: Literal["trigger", "answer"]
    speaker: str
    evaluation_type: Literal["entire", "first", "last"]
    n_messages: int

    current_description: str
    iteration_history: List[Dict[str, Any]]

    current_predictions: Dict[str, str]
    current_accuracy: float
    current_precision: float
    current_recall: float
    current_f1: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    not_applicable_count: int
    rca_findings: Optional[str]
    optimization_notes: Optional[str]
    status: Literal["pending", "optimizing", "converged", "max_iterations_reached"]

    # Regression tracking — set during first benchmarking pass
    initial_accuracy: Optional[float]
    best_accuracy: Optional[float]
    best_description: Optional[str]
```

- [ ] **Step 2: Initialize new fields in `csv_ingestion.py`**

In `backend/agents/nodes/csv_ingestion.py`, add three fields to `ParameterOptimizationRecord(...)` call:

```python
parameter_records[rule["rule_id"]] = ParameterOptimizationRecord(
    rule_id=rule["rule_id"],
    rule_type=rule["rule_type"],
    speaker=rule["speaker"],
    evaluation_type=rule["evaluation_type"],
    n_messages=rule["n_messages"],
    current_description=rule["description"],
    iteration_history=[],
    current_predictions={},
    current_accuracy=0.0,
    current_precision=0.0,
    current_recall=0.0,
    current_f1=0.0,
    true_positives=0,
    false_positives=0,
    true_negatives=0,
    false_negatives=0,
    not_applicable_count=0,
    rca_findings=None,
    optimization_notes=None,
    status="pending",
    initial_accuracy=None,
    best_accuracy=None,
    best_description=None,
)
```

- [ ] **Step 3: Commit**

```bash
cd /Users/Prakash.Anto/Projects/autoqa-prompt-optimizer
git add backend/agents/state.py backend/agents/nodes/csv_ingestion.py
git commit -m "feat: add regression tracking fields to RuleRecord"
```

---

## Task 2 — Tests for benchmarking regression guard

**Files:**
- Create: `backend/tests/test_benchmarking.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_benchmarking.py`:

```python
import asyncio
import pytest

from agents.nodes.benchmarking import benchmarking


def _record(description, predictions, *, initial_accuracy=None, best_accuracy=None,
            best_description=None, status="optimizing", current_accuracy=0.0):
    return {
        "rule_id": "r1",
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        "current_description": description,
        "iteration_history": [],
        "current_predictions": predictions,
        "current_accuracy": current_accuracy,
        "current_precision": 0.0,
        "current_recall": 0.0,
        "current_f1": 0.0,
        "true_positives": 0,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0,
        "not_applicable_count": 0,
        "rca_findings": None,
        "optimization_notes": None,
        "status": status,
        "initial_accuracy": initial_accuracy,
        "best_accuracy": best_accuracy,
        "best_description": best_description,
    }


def _state(records, gt_map, *, iteration=0, target=0.9):
    return {
        "session_id": "test",
        "parameter_records": records,
        "ground_truth_map": gt_map,
        "accuracy_target": target,
        "current_iteration": iteration,
        "parameters_meeting_target": [],
        "parameters_below_target": [],
        "progress_log": [],
    }


def test_initial_accuracy_recorded_on_first_pass():
    # 3 correct / 4 total = 75%
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"}
    gt = {
        "c1": {"r1": "Yes"}, "c2": {"r1": "No"},
        "c3": {"r1": "Yes"}, "c4": {"r1": "Yes"},  # c4 FN
    }
    record = _record("desc v1", preds, initial_accuracy=None)
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=0)))

    r = result["parameter_records"]["r1"]
    assert r["initial_accuracy"] == pytest.approx(0.75)
    assert r["best_accuracy"] == pytest.approx(0.75)
    assert r["best_description"] == "desc v1"


def test_regression_reverts_description():
    # initial best: 80% with "desc v1"
    # current eval: TP=1 TN=1 FP=2 FN=1 = 2/5 = 40% with "desc v2"
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No", "c5": "Yes"}
    gt = {
        "c1": {"r1": "Yes"},   # TP
        "c2": {"r1": "No"},    # TN
        "c3": {"r1": "No"},    # FP
        "c4": {"r1": "Yes"},   # FN
        "c5": {"r1": "No"},    # FP
    }
    record = _record(
        "desc v2", preds,
        initial_accuracy=0.80, best_accuracy=0.80, best_description="desc v1",
    )
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=1)))

    r = result["parameter_records"]["r1"]
    assert r["current_description"] == "desc v1"   # reverted to best
    assert r["best_accuracy"] == pytest.approx(0.80)  # best unchanged
    assert r["current_accuracy"] == pytest.approx(0.40)  # actual eval accuracy preserved
    assert "r1" in result["parameters_below_target"]


def test_improvement_updates_best():
    # initial best: 80% with "desc v1"
    # current eval: 4/4 = 100% with "desc v2"
    preds = {"c1": "Yes", "c2": "No", "c3": "Yes", "c4": "No"}
    gt = {"c1": {"r1": "Yes"}, "c2": {"r1": "No"}, "c3": {"r1": "Yes"}, "c4": {"r1": "No"}}
    record = _record(
        "desc v2", preds,
        initial_accuracy=0.80, best_accuracy=0.80, best_description="desc v1",
    )
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=1, target=0.9)))

    r = result["parameter_records"]["r1"]
    assert r["best_accuracy"] == pytest.approx(1.0)
    assert r["best_description"] == "desc v2"
    assert r["current_description"] == "desc v2"
    assert "r1" in result["parameters_meeting_target"]


def test_converged_rule_locked_regardless_of_new_predictions():
    # Rule is converged with 90% accuracy. Predictions would compute 0% if re-evaluated.
    # Expect: status stays converged, accuracy stays 90%, description unchanged.
    preds = {"c1": "Yes"}  # Would be FP if re-evaluated against GT below
    gt = {"c1": {"r1": "No"}}
    record = _record(
        "desc v1", preds,
        initial_accuracy=0.90, best_accuracy=0.90, best_description="desc v1",
        status="converged", current_accuracy=0.90,
    )
    result = asyncio.run(benchmarking(_state({"r1": record}, gt, iteration=1)))

    r = result["parameter_records"]["r1"]
    assert r["status"] == "converged"
    assert r["current_accuracy"] == pytest.approx(0.90)  # not re-computed
    assert r["current_description"] == "desc v1"
    assert "r1" in result["parameters_meeting_target"]
    assert "r1" not in result["parameters_below_target"]
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /Users/Prakash.Anto/Projects/autoqa-prompt-optimizer/backend
source venv/bin/activate
pytest tests/test_benchmarking.py -v
```

Expected: 4 failures (functions not yet updated)

---

## Task 3 — Benchmarking: regression guard + converged locking

**Files:**
- Modify: `backend/agents/nodes/benchmarking.py`

- [ ] **Step 1: Replace `benchmarking.py` with regression guard + converged locking**

Full replacement of `backend/agents/nodes/benchmarking.py`:

```python
import logging

from agents.state import OptimizationState
from utils.accuracy_metrics import compute_metrics
from utils.session_store import session_store

logger = logging.getLogger(__name__)


async def benchmarking(state: OptimizationState) -> dict:
    logger.info(
        "session=%s phase=benchmarking iteration=%d",
        state["session_id"], state["current_iteration"],
    )
    session_store.update(state["session_id"], {"current_phase": "benchmarking"})

    records = dict(state["parameter_records"])
    ground_truth_map = state["ground_truth_map"]
    accuracy_target = state["accuracy_target"]
    current_iteration = state["current_iteration"]

    meeting_target: list[str] = []
    below_target: list[str] = []
    log_lines: list[str] = []

    for rule_id, record in records.items():
        # Converged rules are locked — never re-evaluated or re-routed
        if record.get("status") == "converged":
            meeting_target.append(rule_id)
            log_lines.append(
                f"Iteration {current_iteration} | {rule_id}: "
                f"converged (locked) accuracy={record['current_accuracy']:.2%}"
            )
            continue

        metrics = compute_metrics(record["current_predictions"], ground_truth_map, rule_id)
        new_accuracy = metrics["accuracy"]

        # First pass: seed regression tracking
        if record.get("initial_accuracy") is None:
            initial_accuracy = new_accuracy
            best_accuracy = new_accuracy
            best_description = record["current_description"]
        else:
            initial_accuracy = record["initial_accuracy"]
            best_accuracy = record["best_accuracy"] or record["initial_accuracy"]
            best_description = record["best_description"] or record["current_description"]

        # Regression guard: revert description if this iteration was worse than best
        if new_accuracy < best_accuracy and record.get("initial_accuracy") is not None:
            current_description = best_description
            logger.info(
                "session=%s rule_id=%s regression detected (%.2f < %.2f) — reverting description",
                state["session_id"], rule_id, new_accuracy, best_accuracy,
            )
        else:
            current_description = record["current_description"]
            if new_accuracy >= best_accuracy:
                best_accuracy = new_accuracy
                best_description = record["current_description"]

        history_entry = {
            "iteration": current_iteration,
            "description": record["current_description"],
            "accuracy": new_accuracy,
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
        }

        updated_record = {
            **record,
            "current_description": current_description,
            "current_accuracy": new_accuracy,
            "current_precision": metrics["precision"],
            "current_recall": metrics["recall"],
            "current_f1": metrics["f1"],
            "true_positives": metrics["tp"],
            "false_positives": metrics["fp"],
            "true_negatives": metrics["tn"],
            "false_negatives": metrics["fn"],
            "not_applicable_count": metrics["not_applicable_count"],
            "initial_accuracy": initial_accuracy,
            "best_accuracy": best_accuracy,
            "best_description": best_description,
            "iteration_history": [*record["iteration_history"], history_entry],
        }

        if new_accuracy >= accuracy_target:
            updated_record["status"] = "converged"
            meeting_target.append(rule_id)
        else:
            updated_record["status"] = "optimizing"
            below_target.append(rule_id)

        records[rule_id] = updated_record
        log_lines.append(
            f"Iteration {current_iteration} | {rule_id}: "
            f"accuracy={new_accuracy:.2%} "
            f"(TP={metrics['tp']} TN={metrics['tn']} FP={metrics['fp']} FN={metrics['fn']})"
        )
        logger.info(
            "session=%s rule_id=%s iteration=%d accuracy=%.4f",
            state["session_id"], rule_id, current_iteration, new_accuracy,
        )

    return {
        "parameter_records": records,
        "parameters_meeting_target": meeting_target,
        "parameters_below_target": below_target,
        "current_phase": "benchmarking",
        "progress_log": log_lines,
    }
```

- [ ] **Step 2: Run tests — expect all pass**

```bash
pytest tests/test_benchmarking.py -v
```

Expected: 4 PASSED

- [ ] **Step 3: Run full test suite to check no regressions**

```bash
pytest tests/ -v
```

Expected: all existing tests still pass

- [ ] **Step 4: Commit**

```bash
git add backend/agents/nodes/benchmarking.py backend/tests/test_benchmarking.py
git commit -m "feat: benchmarking regression guard and converged rule locking"
```

---

## Task 4 — Evaluator: skip converged rules

**Files:**
- Modify: `backend/agents/nodes/evaluator.py`
- Create: `backend/tests/test_evaluator_skip.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_evaluator_skip.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch

from agents.nodes.evaluator import evaluator


def _record(rule_id, *, status="optimizing", predictions=None):
    return {
        "rule_id": rule_id,
        "rule_type": "answer",
        "speaker": "Agent",
        "evaluation_type": "entire",
        "n_messages": 0,
        "current_description": "test description",
        "iteration_history": [],
        "current_predictions": predictions or {},
        "current_accuracy": 0.0,
        "current_precision": 0.0,
        "current_recall": 0.0,
        "current_f1": 0.0,
        "true_positives": 0,
        "false_positives": 0,
        "true_negatives": 0,
        "false_negatives": 0,
        "not_applicable_count": 0,
        "rca_findings": None,
        "optimization_notes": None,
        "status": status,
        "initial_accuracy": None,
        "best_accuracy": None,
        "best_description": None,
    }


def _state(records):
    return {
        "session_id": "test",
        "conversations": [
            {"conversation_id": "c1", "transcript": []},
            {"conversation_id": "c2", "transcript": []},
        ],
        "parameter_records": records,
        "system_prompt": "system",
        "language": "en",
        "current_iteration": 1,
        "progress_log": [],
    }


@patch("agents.nodes.evaluator._evaluate_conversation", new_callable=AsyncMock)
def test_converged_predictions_not_reset(mock_eval_conv):
    """Converged rule predictions must not be cleared before evaluation pass."""
    converged_preds = {"c1": "Yes", "c2": "No"}
    records = {
        "r_conv": _record("r_conv", status="converged", predictions=converged_preds.copy()),
        "r_active": _record("r_active", status="optimizing"),
    }

    mock_eval_conv.return_value = ("c1", [{"_id": "r_active", "isQualified": True}])

    result = asyncio.run(evaluator(_state(records)))

    assert result["parameter_records"]["r_conv"]["current_predictions"] == converged_preds


@patch("agents.nodes.evaluator._evaluate_conversation", new_callable=AsyncMock)
def test_converged_rule_excluded_from_llm_payload(mock_eval_conv):
    """_evaluate_conversation must never receive converged rules in its parameter_records arg."""
    converged_preds = {"c1": "Yes"}
    records = {
        "r_conv": _record("r_conv", status="converged", predictions=converged_preds.copy()),
        "r_active": _record("r_active", status="optimizing"),
    }

    mock_eval_conv.return_value = ("c1", [{"_id": "r_active", "isQualified": False}])

    asyncio.run(evaluator(_state(records)))

    for call in mock_eval_conv.call_args_list:
        payload_records = call.args[1]  # second positional arg is parameter_records
        assert "r_conv" not in payload_records, "converged rule must not be in LLM payload"
        assert "r_active" in payload_records
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_evaluator_skip.py -v
```

Expected: 2 failures

- [ ] **Step 3: Replace `evaluator.py` with converged-skip logic**

Full replacement of `backend/agents/nodes/evaluator.py`:

```python
import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import OptimizationState
from config import get_llm, settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)


async def evaluator(state: OptimizationState) -> dict:
    session_id = state["session_id"]
    iteration = state["current_iteration"]
    logger.info("session=%s phase=evaluating iteration=%d", session_id, iteration)
    session_store.update(session_id, {"current_phase": "evaluating"})

    records = dict(state["parameter_records"])

    # Reset predictions only for non-converged rules.
    # Converged rules keep last-known predictions to prevent LLM non-determinism regression.
    for rule_id, record in records.items():
        if record.get("status") != "converged":
            records[rule_id] = {**records[rule_id], "current_predictions": {}}

    # Only submit non-converged rules to the LLM
    rules_to_evaluate = {
        rule_id: record
        for rule_id, record in records.items()
        if record.get("status") != "converged"
    }

    if not rules_to_evaluate:
        session_store.append_log(session_id, f"Iteration {iteration}: all rules converged, evaluation skipped")
        return {
            "parameter_records": records,
            "current_phase": "benchmarking",
            "progress_log": [f"Iteration {iteration}: all rules converged, evaluation skipped"],
        }

    conversations = state["conversations"]
    system_prompt = state["system_prompt"]
    language = state.get("language", "en")

    session_store.append_log(
        session_id,
        f"Iteration {iteration}: evaluating {len(conversations)} conversations "
        f"({len(rules_to_evaluate)} active rules, "
        f"{len(records) - len(rules_to_evaluate)} converged/locked)…",
    )

    semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)

    async def evaluate_one(conv: dict[str, Any]) -> tuple[str, list]:
        async with semaphore:
            return await _evaluate_conversation(conv, rules_to_evaluate, system_prompt, language)

    tasks = [evaluate_one(conv) for conv in conversations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for conv, result in zip(conversations, results):
        conv_id = conv["conversation_id"]
        if isinstance(result, Exception):
            logger.warning(
                "session=%s conversation_id=%s evaluation error: %s",
                session_id, conv_id, type(result).__name__,
            )
            for rule_id in rules_to_evaluate:
                records[rule_id]["current_predictions"][conv_id] = "No"
            continue

        _, rule_results = result
        for rule_result in rule_results:
            rule_id = rule_result.get("_id")
            if rule_id and rule_id in rules_to_evaluate:
                is_qualified = rule_result.get("isQualified", False)
                records[rule_id]["current_predictions"][conv_id] = "Yes" if is_qualified else "No"

    return {
        "parameter_records": records,
        "current_phase": "benchmarking",
        "progress_log": [
            f"Iteration {iteration}: evaluated {len(conversations)} conversations "
            f"across {len(rules_to_evaluate)} active rule(s)"
        ],
    }


async def _evaluate_conversation(
    conv: dict,
    parameter_records: dict,
    system_prompt: str,
    language: str,
) -> tuple[str, list]:
    conv_id = conv["conversation_id"]

    rules_payload = [
        {
            "description": record["current_description"],
            "speaker": record["speaker"],
            "id": record["rule_id"],
            "evaluation_type": record["evaluation_type"],
            "n_messages": record["n_messages"],
        }
        for record in parameter_records.values()
    ]

    user_content = (
        f"Transcripts: {json.dumps(conv['transcript'])}\n"
        f"Rules: {json.dumps(rules_payload)}\n"
        f"Language: {language}"
    )

    response = await get_llm().ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_content),
    ])

    try:
        rule_results = json.loads(response.content)
        if not isinstance(rule_results, list):
            raise ValueError("Expected JSON array")
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "session=unknown conversation_id=%s JSON parse failure — defaulting all rules to No",
            conv_id,
        )
        rule_results = [{"_id": rid, "isQualified": False} for rid in parameter_records]

    return conv_id, rule_results
```

- [ ] **Step 4: Run evaluator tests — expect pass**

```bash
pytest tests/test_evaluator_skip.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add backend/agents/nodes/evaluator.py backend/tests/test_evaluator_skip.py
git commit -m "feat: evaluator skips converged rules to prevent LLM non-determinism regression"
```

---

## Task 5 — baseline_prompt_generator: structured format + clarification rewrite

**Files:**
- Modify: `backend/agents/nodes/baseline_prompt_generator.py`

- [ ] **Step 1: Replace `baseline_prompt_generator.py`**

The structured format is the output contract for all generated descriptions. When `user_answers` exist, always regenerate the description using clarification answers as primary source, even if a description already exists in the CSV.

Full replacement of `backend/agents/nodes/baseline_prompt_generator.py`:

```python
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from agents.state import OptimizationState
from config import get_llm
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert QA rule description writer for contact centre quality evaluation.
Rule descriptions are used by an LLM evaluation system to assess conversation transcripts.

You MUST output descriptions using this exact structured format:

METRIC_NAME: <2-5 word Title Case name>
SPEAKER: <Agent | Customer>
ACTION: <verb-first single sentence describing what is evaluated>
PASS_LOGIC: <ALL | ANY>
PASS_CRITERIA:
1. <atomic observable condition, detectable from transcript text>
2. <atomic observable condition>
EXAMPLES:
PASS:
1. "<example utterance that would pass>"
2. "<example utterance that would pass>"
FAIL:
1. "<example utterance that would fail>"
2. "<example utterance that would fail>"

Format rules:
- METRIC_NAME: 2-5 words, Title Case
- SPEAKER: must exactly match the rule's speaker field (Agent or Customer)
- ACTION: starts with a verb, one sentence only
- PASS_LOGIC: ALL if every criterion must be met; ANY if at least one is sufficient
- PASS_CRITERIA: 2-5 numbered conditions; each must be observable from transcript text alone
- EXAMPLES: minimum 2 PASS and 2 FAIL utterances that would appear verbatim in a transcript
- Never use vague terms: "appropriately", "effectively", "sufficiently", "properly", "well"
- Never require knowledge outside the transcript to evaluate a criterion\
"""


async def baseline_prompt_generator(state: OptimizationState) -> dict:
    logger.info("session=%s phase=generating_baselines", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "generating_baselines"})

    records = dict(state["parameter_records"])
    user_answers = state.get("user_answers", {})
    log_messages = []

    for rule_id, record in records.items():
        has_description = bool(record["current_description"].strip())
        has_clarifications = bool(user_answers)

        if not has_description:
            # No description from CSV — generate from scratch
            task = _build_generation_task(record, user_answers, mode="generate")
            response = await get_llm().ainvoke([
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=task),
            ])
            new_description = response.content.strip()
            records[rule_id] = {**record, "current_description": new_description}
            log_messages.append(f"Generated baseline description for {rule_id}")
            logger.info("session=%s generated baseline for rule_id=%s", state["session_id"], rule_id)

        elif has_clarifications:
            # Clarifications exist — rewrite from scratch anchored to user answers.
            # Prevents semantic drift when clarifications redefine the criterion entirely.
            task = _build_generation_task(record, user_answers, mode="rewrite")
            response = await get_llm().ainvoke([
                SystemMessage(content=_SYSTEM),
                HumanMessage(content=task),
            ])
            new_description = response.content.strip()
            records[rule_id] = {**record, "current_description": new_description}
            log_messages.append(f"Rewrote description for {rule_id} using clarification answers")
            logger.info("session=%s rewrote description from clarifications for rule_id=%s", state["session_id"], rule_id)

    return {
        "parameter_records": records,
        "current_phase": "evaluating",
        "progress_log": log_messages or ["Baselines ready: using production descriptions from CSV"],
    }


def _build_generation_task(record: dict, user_answers: dict, *, mode: str) -> str:
    rule_type = record["rule_type"]
    clarifications = "\n".join(f"- {v}" for v in user_answers.values()) if user_answers else "None"

    if rule_type == "trigger":
        guidance = (
            "Write a TRIGGER rule description that detects whether a specific scenario is present:\n"
            "- PASS_CRITERIA must identify the exact condition from transcript text\n"
            "- Specify whether exact phrasing or semantic equivalents qualify\n"
            "- Identify which speaker initiates or expresses the condition\n"
            "- EXAMPLES should show transcripts that DO and DO NOT trigger the rule"
        )
    else:
        guidance = (
            "Write an ANSWER rule description that evaluates agent adherence to a quality guideline:\n"
            "- PASS_CRITERIA must state exactly what the agent must say or do\n"
            "- FAIL examples must show what 'Not Adhered' looks like in transcript text\n"
            "- Avoid partial adherence ambiguity: define clear pass/fail boundary"
        )

    if mode == "rewrite":
        preamble = (
            f"The existing description may be vague or may measure a DIFFERENT criterion than intended.\n"
            f"The user's clarifications are the authoritative definition of what this rule actually measures.\n"
            f"If the clarifications define a different criterion than the original description, "
            f"write the new description around the clarifications — not the original description.\n\n"
            f"Original description (for reference only):\n{record['current_description']}\n\n"
        )
    else:
        preamble = ""

    return (
        f"{preamble}"
        f"Rule metadata:\n"
        f"- rule_id: {record['rule_id']}\n"
        f"- rule_type: {rule_type}\n"
        f"- speaker: {record['speaker']}\n"
        f"- evaluation_type: {record['evaluation_type']}\n"
        f"- n_messages: {record['n_messages']}\n\n"
        f"User clarifications:\n{clarifications}\n\n"
        f"{guidance}\n\n"
        "Respond with only the structured description, no preamble or explanation."
    )
```

- [ ] **Step 2: Run existing tests to verify no regressions**

```bash
pytest tests/ -v
```

Expected: all pass (no tests directly cover this node)

- [ ] **Step 3: Commit**

```bash
git add backend/agents/nodes/baseline_prompt_generator.py
git commit -m "feat: structured description format and clarification-anchored rewrite in baseline generator"
```

---

## Task 6 — prompt_optimizer: structured format

**Files:**
- Modify: `backend/agents/nodes/prompt_optimizer.py`

- [ ] **Step 1: Update `prompt_optimizer.py` to use structured format**

Replace the `_SYSTEM` constant and `_optimise_description` function. The system prompt is the same structured format contract. The optimization prompt instructs the LLM to produce a structured rewrite that addresses the RCA findings.

```python
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from agents.state import OptimizationState
from config import settings
from utils.session_store import session_store

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are an expert QA rule description writer for contact centre quality evaluation.
Rule descriptions are used by an LLM evaluation system to assess conversation transcripts.

You MUST output descriptions using this exact structured format:

METRIC_NAME: <2-5 word Title Case name>
SPEAKER: <Agent | Customer>
ACTION: <verb-first single sentence describing what is evaluated>
PASS_LOGIC: <ALL | ANY>
PASS_CRITERIA:
1. <atomic observable condition, detectable from transcript text>
2. <atomic observable condition>
EXAMPLES:
PASS:
1. "<example utterance that would pass>"
2. "<example utterance that would pass>"
FAIL:
1. "<example utterance that would fail>"
2. "<example utterance that would fail>"

Format rules:
- METRIC_NAME: 2-5 words, Title Case
- SPEAKER: must exactly match the rule's speaker field (Agent or Customer)
- ACTION: starts with a verb, one sentence only
- PASS_LOGIC: ALL if every criterion must be met; ANY if at least one is sufficient
- PASS_CRITERIA: 2-5 numbered conditions; each must be observable from transcript text alone
- EXAMPLES: minimum 2 PASS and 2 FAIL utterances that would appear verbatim in a transcript
- Never use vague terms: "appropriately", "effectively", "sufficiently", "properly", "well"
- Never require knowledge outside the transcript to evaluate a criterion\
"""


def _get_generation_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0.2,
        top_p=1,
        max_completion_tokens=2000,
        timeout=120,
        api_key=settings.openai_api_key or None,
    )


async def prompt_optimizer(state: OptimizationState) -> dict:
    logger.info(
        "session=%s phase=optimizing_prompts iteration=%d",
        state["session_id"], state["current_iteration"],
    )

    session_id = state["session_id"]
    records = dict(state["parameter_records"])
    below_target = state["parameters_below_target"]
    user_answers = state.get("user_answers", {})
    iteration = state["current_iteration"]

    session_store.update(session_id, {
        "current_phase": "optimizing_prompts",
        "progress_log": list(state.get("progress_log", [])),
    })

    completed_messages: list[str] = []

    try:
        llm = _get_generation_llm()
    except Exception as exc:
        session_store.append_log(session_id, f"ERROR: Could not initialise LLM — {exc}")
        logger.error("session=%s prompt_optimizer LLM init failed: %s", session_id, exc)
        return {
            "parameter_records": records,
            "current_iteration": iteration + 1,
            "current_phase": "error",
            "progress_log": [f"LLM initialisation failed: {exc}"],
        }

    for rule_id in below_target:
        record = records[rule_id]

        session_store.append_log(session_id, f"Optimising description for {rule_id} (iteration {iteration + 1})…")

        history_entry = {
            "iteration": iteration,
            "description": record["current_description"],
            "accuracy": record["current_accuracy"],
            "precision": record["current_precision"],
            "recall": record["current_recall"],
            "f1": record["current_f1"],
        }

        new_description = await _optimise_description(record, user_answers, llm, session_id)

        records[rule_id] = {
            **record,
            "iteration_history": [*record["iteration_history"], history_entry],
            "current_description": new_description,
            "current_predictions": {},
            "optimization_notes": f"Optimised at iteration {iteration + 1}",
        }
        msg = f"Description updated for {rule_id} (iteration {iteration + 1})"
        session_store.append_log(session_id, msg)
        completed_messages.append(msg)
        logger.info("session=%s rule_id=%s description updated for iteration %d", session_id, rule_id, iteration + 1)

    return {
        "parameter_records": records,
        "current_iteration": iteration + 1,
        "current_phase": "evaluating",
        "progress_log": completed_messages,
    }


async def _optimise_description(
    record: dict, user_answers: dict, llm: ChatOpenAI, session_id: str
) -> str:
    rule_type = record["rule_type"]
    clarifications = "\n".join(f"- {v}" for v in user_answers.values()) if user_answers else "None"

    if rule_type == "trigger":
        constraints = (
            "The PASS_CRITERIA must remain detectable from transcript text. "
            "Do not change evaluation_type, n_messages, or speaker."
        )
    else:
        constraints = (
            "The PASS_CRITERIA must be evaluable solely from transcript evidence. "
            "Do not change evaluation_type, n_messages, or speaker."
        )

    prompt = (
        f"Rule ID: {record['rule_id']}\n"
        f"Rule type: {rule_type} | Speaker: {record['speaker']} | "
        f"Evaluation type: {record['evaluation_type']} | n_messages: {record['n_messages']}\n\n"
        f"Current description:\n{record['current_description']}\n\n"
        f"Root cause analysis:\n{record.get('rca_findings', 'No findings available.')}\n\n"
        f"User clarifications:\n{clarifications}\n\n"
        f"Constraints: {constraints}\n\n"
        "Rewrite the description in the structured format to address the identified failure patterns. "
        "Update PASS_CRITERIA to fix the specific errors identified in the RCA. "
        "Add or revise EXAMPLES to reflect the failure cases. "
        "Respond with only the structured description, no preamble."
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=prompt),
        ])
        return response.content.strip()
    except Exception as exc:
        logger.warning(
            "session=%s rule_id=%s optimiser LLM failed: %s",
            session_id, record["rule_id"], type(exc).__name__,
        )
        return record["current_description"]
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add backend/agents/nodes/prompt_optimizer.py
git commit -m "feat: structured description format in prompt optimizer"
```

---

## Task 7 — finalize: regression flagging

**Files:**
- Modify: `backend/agents/nodes/finalize.py`

- [ ] **Step 1: Add regression warning + next steps to finalize report**

Update `finalize.py` — replace `_build_recommendations` and add `regression_warning` to per-rule report:

The `parameters_report` loop needs two small additions — a `regression_warning` field and updated `_build_recommendations` that detects regression.

Modify `backend/agents/nodes/finalize.py`:

1. In the `parameters_report[rule_id] = {...}` block, read `initial_accuracy` from the record (not just iteration_history):

```python
        initial_acc = record.get("initial_accuracy")
        if initial_acc is None:
            # Fallback to iteration_history[0] for backwards compat
            initial = record["iteration_history"][0] if record["iteration_history"] else None
            initial_acc = initial.get("accuracy") if initial else None

        final_acc = record["current_accuracy"]
        regressed = (
            initial_acc is not None
            and final_acc < initial_acc
        )

        parameters_report[rule_id] = {
            "status": record["status"],
            "initial_prompt": initial.get("description", record["current_description"]) if initial else record["current_description"],
            "initial_accuracy": initial_acc,
            "final_accuracy": final_acc,
            "final_precision": record["current_precision"],
            "final_recall": record["current_recall"],
            "final_f1": record["current_f1"],
            "confusion_matrix": {
                "tp": record["true_positives"],
                "tn": record["true_negatives"],
                "fp": record["false_positives"],
                "fn": record["false_negatives"],
            },
            "not_applicable_count": record["not_applicable_count"],
            "final_prompt": record["current_description"],
            "optimization_notes": record.get("optimization_notes"),
            "iteration_history": record["iteration_history"] if converged else [
                {"iteration": h["iteration"], "accuracy": h["accuracy"]}
                for h in record["iteration_history"]
            ],
            "rca_findings": record.get("rca_findings"),
            "regression_warning": _build_regression_warning(record, initial_acc, final_acc) if regressed else None,
            "recommendations": _build_recommendations(record),
            "conversation_results": conversation_results,
        }
```

2. Add `_build_regression_warning` function and update `_build_recommendations`:

```python
def _build_regression_warning(record: dict, initial_accuracy: float, final_accuracy: float) -> dict:
    delta = final_accuracy - initial_accuracy
    return {
        "message": (
            f"Final accuracy ({final_accuracy:.1%}) is lower than initial accuracy "
            f"({initial_accuracy:.1%}) — delta {delta:+.1%}."
        ),
        "root_cause": record.get("rca_findings") or "RCA not available for this rule.",
        "next_steps": [
            "Review the iteration history to identify which optimization step caused the drop.",
            "Manually inspect false positive and false negative cases in conversation_results.",
            "Rewrite the rule description using the structured format with explicit PASS_CRITERIA "
            "and FAIL EXAMPLES derived from the error cases above.",
            "Consider whether this criterion is deterministically evaluable from transcript text alone "
            "— if subjective judgment is required, the rule may need human review.",
        ],
    }
```

Full replacement of `backend/agents/nodes/finalize.py`:

```python
import logging
from datetime import datetime, timezone

from agents.state import OptimizationState
from utils.session_store import session_store

logger = logging.getLogger(__name__)


async def finalize(state: OptimizationState) -> dict:
    logger.info("session=%s phase=finalizing", state["session_id"])
    session_store.update(state["session_id"], {"current_phase": "complete"})

    records = dict(state["parameter_records"])
    below_target = set(state["parameters_below_target"])

    for rule_id, record in records.items():
        if rule_id in below_target:
            records[rule_id] = {**record, "status": "max_iterations_reached"}
        else:
            records[rule_id] = {**record, "status": "converged"}

    total = len(records)
    meeting = [rid for rid, r in records.items() if r["status"] == "converged"]
    not_meeting = [rid for rid, r in records.items() if r["status"] == "max_iterations_reached"]
    overall_accuracy = (
        sum(r["current_accuracy"] for r in records.values()) / total if total else 0.0
    )

    gt_map = state["ground_truth_map"]

    parameters_report: dict = {}
    for rule_id, record in records.items():
        converged = record["status"] == "converged"

        conversation_results = []
        for conv_id in sorted(record["current_predictions"].keys()):
            prediction = record["current_predictions"][conv_id]
            ground_truth = gt_map.get(conv_id, {}).get(rule_id, "NA")
            correct = None if ground_truth == "NA" else (prediction == ground_truth)
            conversation_results.append({
                "conversation_id": conv_id,
                "ground_truth": ground_truth,
                "prediction": prediction,
                "correct": correct,
            })

        initial_acc = record.get("initial_accuracy")
        if initial_acc is None:
            first = record["iteration_history"][0] if record["iteration_history"] else None
            initial_acc = first.get("accuracy") if first else None
        initial_desc = (
            record["iteration_history"][0].get("description", record["current_description"])
            if record["iteration_history"] else record["current_description"]
        )

        final_acc = record["current_accuracy"]
        regressed = initial_acc is not None and final_acc < initial_acc

        parameters_report[rule_id] = {
            "status": record["status"],
            "initial_prompt": initial_desc,
            "initial_accuracy": initial_acc,
            "final_accuracy": final_acc,
            "final_precision": record["current_precision"],
            "final_recall": record["current_recall"],
            "final_f1": record["current_f1"],
            "confusion_matrix": {
                "tp": record["true_positives"],
                "tn": record["true_negatives"],
                "fp": record["false_positives"],
                "fn": record["false_negatives"],
            },
            "not_applicable_count": record["not_applicable_count"],
            "final_prompt": record["current_description"],
            "optimization_notes": record.get("optimization_notes"),
            "iteration_history": record["iteration_history"] if converged else [
                {"iteration": h["iteration"], "accuracy": h["accuracy"]}
                for h in record["iteration_history"]
            ],
            "rca_findings": record.get("rca_findings"),
            "regression_warning": _build_regression_warning(record, initial_acc, final_acc) if regressed else None,
            "recommendations": _build_recommendations(record),
            "conversation_results": conversation_results,
        }

    final_report = {
        "session_id": state["session_id"],
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "summary": {
            "total_parameters": total,
            "parameters_meeting_target": len(meeting),
            "parameters_below_target": len(not_meeting),
            "overall_accuracy": overall_accuracy,
            "total_iterations": state["current_iteration"],
            "total_conversations": len(state["conversations"]),
            "accuracy_target": state["accuracy_target"],
        },
        "parameters": parameters_report,
    }

    logger.info(
        "session=%s finalized: %d/%d rules converged",
        state["session_id"], len(meeting), total,
    )

    return {
        "parameter_records": records,
        "final_report": final_report,
        "optimization_complete": True,
        "current_phase": "complete",
        "progress_log": [
            f"Optimization complete: {len(meeting)}/{total} rules met the accuracy target"
        ],
    }


def _build_regression_warning(record: dict, initial_accuracy: float, final_accuracy: float) -> dict:
    delta = final_accuracy - initial_accuracy
    return {
        "message": (
            f"Final accuracy ({final_accuracy:.1%}) is lower than initial accuracy "
            f"({initial_accuracy:.1%}) — delta {delta:+.1%}."
        ),
        "root_cause": record.get("rca_findings") or "RCA not available for this rule.",
        "next_steps": [
            "Review iteration_history to identify which optimization step caused the drop.",
            "Inspect false positive and false negative cases in conversation_results.",
            "Rewrite the rule description using the structured format with explicit PASS_CRITERIA "
            "and FAIL EXAMPLES derived from the failing cases.",
            "Verify whether the criterion is deterministically evaluable from transcript text alone "
            "— if subjective judgment is required, the rule may need human review.",
        ],
    }


def _build_recommendations(record: dict) -> list[str]:
    if record["status"] == "converged" or not record.get("rca_findings"):
        return []
    recs = [
        "Review the RCA findings and manually refine the rule description.",
        "Consider whether this criterion is automatable from transcript evidence alone.",
    ]
    if record["false_positives"] > record["false_negatives"] * 2:
        recs.insert(0, "High false-positive rate — tighten specificity in PASS_CRITERIA.")
    elif record["false_negatives"] > record["false_positives"] * 2:
        recs.insert(0, "High false-negative rate — broaden or clarify the success criteria.")
    return recs
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add backend/agents/nodes/finalize.py
git commit -m "feat: regression warning with RCA and next steps in finalize report"
```

---

## Task 8 — API default accuracy target 80% → 90%

**Files:**
- Modify: `backend/api/routes/sessions.py`

- [ ] **Step 1: Change the default**

In `backend/api/routes/sessions.py`, find:

```python
    accuracy_target: float = Form(0.80),
```

Replace with:

```python
    accuracy_target: float = Form(0.90),
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -v
```

Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add backend/api/routes/sessions.py
git commit -m "feat: raise default accuracy target from 80% to 90%"
```

---

## Self-Review

**Spec coverage:**
- ✅ Structured description format in baseline_prompt_generator + prompt_optimizer (Tasks 5, 6)
- ✅ Clarification-anchored rewrite (Task 5)
- ✅ Skip converged rules in evaluator (Task 4)
- ✅ Regression guard: revert on drop (Task 3)
- ✅ Converged locking in benchmarking (Task 3)
- ✅ Regression flag in report with RCA + next steps (Task 7)
- ✅ Accuracy target 90% (Task 8)
- ✅ State schema extended for tracking (Task 1)

**Type consistency:**
- `initial_accuracy`, `best_accuracy`, `best_description` defined in Task 1, initialized in Task 1, read in Tasks 3, 7
- `status == "converged"` check used consistently in Tasks 3 and 4
- `rules_to_evaluate` (dict) passed to `_evaluate_conversation` as second positional arg — matches function signature

**No placeholders:** All code blocks are complete and runnable.
