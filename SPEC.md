# SPEC.md — AutoQA Prompt Optimization System
# Schemas, node specs, API contract, frontend specs
# Rules in CLAUDE.md. Build order in MILESTONES.md.

---

## Repository Structure

```
autoqa-prompt-optimizer/
├── CLAUDE.md / SPEC.md / MILESTONES.md
├── .env / .env.example
│
├── backend/
│   ├── requirements.txt
│   ├── main.py                          ← FastAPI app factory, CORS, router mount
│   ├── config.py                        ← pydantic-settings, reads .env
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── sessions.py              ← session CRUD endpoints
│   │   │   └── stream.py               ← SSE streaming endpoint
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── session.py              ← Pydantic request/response models
│   │       └── report.py               ← Report structure models
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py                    ← LangGraph TypedDict state
│   │   ├── graph.py                    ← Graph compilation and entry point
│   │   └── nodes/
│   │       ├── __init__.py
│   │       ├── csv_ingestion.py
│   │       ├── ambiguity_detection.py  ← calls interrupt() to pause for user
│   │       ├── baseline_prompt_generator.py
│   │       ├── evaluator.py
│   │       ├── benchmarking.py
│   │       ├── rca_analyzer.py
│   │       ├── prompt_optimizer.py
│   │       └── finalize.py
│   │       # convergence_check is a conditional edge function in graph.py, not a node file
│   │
│   └── utils/
│       ├── __init__.py
│       ├── csv_parser.py
│       ├── accuracy_metrics.py
│       └── session_store.py
│
└── frontend/
    ├── package.json / angular.json / tsconfig.json / proxy.conf.json
    └── src/app/
        ├── app.config.ts / app.routes.ts
        ├── core/
        │   ├── models/session.model.ts / report.model.ts
        │   └── services/session.service.ts / sse.service.ts
        └── pages/
            ├── upload/          ← Step 1
            ├── clarification/   ← Step 2 (skipped if no questions)
            ├── progress/        ← Step 3
            └── results/         ← Step 4
```

Note: Every Python directory needs an `__init__.py`.

---

## CSV Input Schema

**Format:** Long format — one row per (conversation × parameter) pair.
A single `conversation_id` appears in multiple rows (once per parameter).

### Required Columns

| Column | Type | Notes |
|---|---|---|
| `conversation_id` | string | Unique ID for the transcript |
| `transcript` | string | Full agent–customer conversation text |
| `parameter_name` | string | Short identifier for the evaluation criterion |
| `parameter_description` | string | Natural language description of what to evaluate |
| `ground_truth` | string | `Yes`, `No`, or `NA` (case-insensitive) |

### Validation Rules (enforce in `csv_parser.py`)

1. All five columns must be present — raise a descriptive error naming the missing column.
2. `ground_truth` normalize via `.strip().title()` → must be `Yes`, `No`, or `NA`. Reject rows with other values.
3. `transcript` must be non-empty string.
4. Minimum 10 valid rows after cleaning.
5. Each unique `parameter_name` must have ≥5 evaluable (non-NA) rows to be included. Exclude and note in report.
6. Never log transcript content — log parameter names and row counts only.

### Deduplication note

When building the `conversations` list for state, deduplicate by `conversation_id`. Use the first encountered transcript for each ID. The CSV may repeat the same transcript across multiple parameter rows — only store it once.

---

## LangGraph State Schema (`backend/agents/state.py`)

Use `TypedDict` throughout. Import `Annotated` and `operator` for list reducers.

```python
import operator
from typing import Annotated, TypedDict, Optional, Literal, List, Dict, Any

class ParameterOptimizationRecord(TypedDict):
    parameter_name: str
    parameter_description: str
    current_prompt: str
    current_predictions: Dict[str, str]      # {conversation_id: "Yes"|"No"|"NA"}
    # Written by evaluator, read by benchmarking. Reset each iteration.
    iteration_history: List[Dict[str, Any]]
    # Each entry: {iteration, prompt, accuracy, precision, recall, f1, error_analysis}
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
    optimization_notes: Optional[str]        # key changes made; surfaced in report
    status: Literal["pending", "optimizing", "converged", "max_iterations_reached"]

class ClarifyingQuestion(TypedDict):
    question_id: str
    parameter_name: str
    question_text: str
    rationale: str

class OptimizationState(TypedDict):
    session_id: str

    # From CSV (set once by csv_ingestion)
    conversations: List[Dict[str, str]]           # [{conversation_id, transcript}] — deduplicated
    parameters: List[Dict[str, str]]              # [{parameter_name, parameter_description}]
    ground_truth_map: Dict[str, Dict[str, str]]   # [conv_id][param_name] = "Yes"|"No"|"NA"
    excluded_parameters: List[str]

    # Clarification
    clarifying_questions: List[ClarifyingQuestion]
    user_answers: Dict[str, str]                  # question_id → answer text
    clarification_complete: bool

    # Optimization loop
    current_iteration: int
    max_iterations: int                           # default 5, set at session creation
    accuracy_target: float                        # default 0.80
    parameter_records: Dict[str, ParameterOptimizationRecord]

    # Control
    optimization_complete: bool
    parameters_meeting_target: List[str]
    parameters_below_target: List[str]

    # Progress — use Annotated reducer so nodes append rather than replace
    progress_log: Annotated[List[str], operator.add]
    current_phase: Literal[
        "ingesting", "detecting_ambiguity", "awaiting_clarification",
        "generating_baselines", "evaluating", "benchmarking",
        "analyzing_failures", "optimizing_prompts", "complete", "error"
    ]

    # Output
    final_report: Optional[Dict[str, Any]]
```

**Critical — `progress_log` reducer:** The `Annotated[List[str], operator.add]` annotation tells LangGraph to concatenate lists rather than replace. Every node must return `{"progress_log": ["new message 1", "new message 2"]}` — only the *new* messages, not the full accumulated list.

---

## LangGraph Graph Definition (`agents/graph.py`)

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph

# Compile with MemorySaver for in-memory persistence (lost on server restart — acceptable for prototype)
graph = StateGraph(OptimizationState)
# ... add nodes and edges ...
app = graph.compile(checkpointer=MemorySaver())

# Each session uses session_id as thread_id:
# config = {"configurable": {"thread_id": session_id}}
# await app.ainvoke(initial_state, config=config)      ← initial run
# await app.ainvoke(resume_input, config=config)       ← resume after interrupt
```

**Graph flow:**
```
csv_ingestion
  → ambiguity_detection
      → [questions] INTERRUPT — wait for POST /answers, then resume
      → [no questions] → baseline_prompt_generator
  → baseline_prompt_generator
  → evaluator
  → benchmarking
  → [convergence_check — conditional edge]
      → all pass OR current_iteration >= max_iterations → finalize
      → failures remain → rca_analyzer → prompt_optimizer → evaluator (loop)
```

---

## LangGraph Interrupt Pattern

Use `interrupt()` from `langgraph.types` — called **inside the node function** as a return value, not as a graph-level config.

```python
# In ambiguity_detection.py:
from langgraph.types import interrupt

def ambiguity_detection(state: OptimizationState) -> dict:
    questions = _generate_questions(state)
    if questions:
        # Pause here. Graph resumes when POST /answers calls app.ainvoke() again.
        interrupt({"clarifying_questions": questions})
    return {
        "clarifying_questions": questions,
        "clarification_complete": len(questions) == 0,
        "current_phase": "awaiting_clarification" if questions else "generating_baselines",
        "progress_log": [f"Detected {len(questions)} clarifying questions"]
    }
```

Resuming the graph after interrupt:
```python
# In POST /answers endpoint:
resume_input = Command(resume={"user_answers": answers, "clarification_complete": True})
await graph_app.ainvoke(resume_input, config={"configurable": {"thread_id": session_id}})
```

Import `Command` from `langgraph.types`.

---

## Async Graph Execution

**Do NOT use FastAPI `BackgroundTasks`** — it uses a thread pool which conflicts with async LangGraph.

```python
# In POST /api/sessions — kick off graph asynchronously:
import asyncio

async def run_graph(session_id: str, initial_state: OptimizationState):
    config = {"configurable": {"thread_id": session_id}}
    try:
        await graph_app.ainvoke(initial_state, config=config)
    except Exception as e:
        session_store.update_session(session_id, {"current_phase": "error", "error": str(e)})

# Inside the route handler:
asyncio.create_task(run_graph(session_id, initial_state))
```

---

## Agent Node Specifications

Each node signature: `async def node_name(state: OptimizationState) -> dict`
Return only the keys being modified. For `progress_log`, return only new messages (reducer handles append).

---

### `csv_ingestion`
**Output keys:** `conversations`, `parameters`, `ground_truth_map`, `excluded_parameters`, `current_phase`, `progress_log`

Parse and validate CSV. Deduplicate `conversations` by `conversation_id`. Build `ground_truth_map`. Exclude parameters with <5 evaluable rows. Set `current_phase = "detecting_ambiguity"`.

---

### `ambiguity_detection`
**Output keys:** `clarifying_questions`, `clarification_complete`, `current_phase`, `progress_log`

For each parameter, call Claude to identify: vague/subjective language, missing timing or scope specificity, criteria not detectable from transcript text alone, and implicit QA analyst context.

Max 2 questions per parameter. Max 10 questions total. If questions exist, call `interrupt()` (see Interrupt Pattern above). If none, set `clarification_complete = True`, `current_phase = "generating_baselines"`.

---

### `baseline_prompt_generator`
**Output keys:** `parameter_records`, `current_phase`, `progress_log`

For each parameter, generate an initial evaluation prompt incorporating: parameter description, user clarification answers for that parameter (if any), and contact center domain context.

**Each generated prompt must include:**
- What the criterion is
- What constitutes Yes (passing)
- What constitutes No (failing)
- When to return NA
- Evidence grounding: `"Base your evaluation only on what is explicitly stated or clearly implied in the transcript."`
- Output constraint: `"Respond with exactly one word: Yes, No, or NA. Do not include any explanation."`

Initialize `ParameterOptimizationRecord` for each parameter with `status = "pending"`, `current_predictions = {}`, `iteration_history = []`, all metrics = 0.

---

### `evaluator`
**Output keys:** Updated `parameter_records` (with `current_predictions` populated), `current_phase`, `progress_log`

For each (parameter, conversation) pair where ground truth ≠ NA:
- Call Claude with `current_prompt` + transcript
- Parse response: strip whitespace, title-case → must be `Yes`, `No`, or `NA`
- On parse failure: treat as `No`, append warning to `progress_log` (parameter name + iteration, no transcript content)

Write results to `parameter_records[param_name]["current_predictions"][conversation_id]`.

**Batching:** `asyncio.gather` with semaphore capped at `MAX_CONCURRENT_LLM_CALLS`. Never exceed 20.

```python
semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
async def call_with_limit(param, conv):
    async with semaphore:
        return await _call_llm(param, conv)
tasks = [call_with_limit(p, c) for p, c in pairs]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

---

### `benchmarking`
**Output keys:** Updated `parameter_records` (with metrics), `parameters_meeting_target`, `parameters_below_target`, `current_phase`, `progress_log`

For each parameter, compute from `current_predictions` vs `ground_truth_map`. Exclude NA ground truths.

```
TP = prediction=Yes AND ground_truth=Yes
TN = prediction=No  AND ground_truth=No
FP = prediction=Yes AND ground_truth=No
FN = prediction=No  AND ground_truth=Yes

Accuracy  = (TP + TN) / (TP + TN + FP + FN)  — 0.0 if denominator is 0
Precision = TP / (TP + FP)                    — 0.0 on zero division
Recall    = TP / (TP + FN)                    — 0.0 on zero division
F1        = 2*P*R / (P+R)                     — 0.0 on zero division
```

Append to `iteration_history`: `{iteration: current_iteration, prompt: current_prompt, accuracy, precision, recall, f1}`. Classify into `parameters_meeting_target` / `parameters_below_target` using `accuracy_target`.

---

### `convergence_check` (conditional edge function in `graph.py`, not a separate node)

```python
def convergence_check(state: OptimizationState) -> str:
    if not state["parameters_below_target"]:
        return "finalize"
    if state["current_iteration"] >= state["max_iterations"]:
        return "finalize"
    return "rca_analyzer"
```

---

### `rca_analyzer`
**Output keys:** Updated `parameter_records` (with `rca_findings`), `current_phase`, `progress_log`

For each below-target parameter, send Claude:
- Current evaluation prompt
- Up to 10 error cases (FP + FN) with transcripts and ground truth labels
- Request: identify specific error patterns, what the prompt is missing or over-specifying, whether failures are systematic or random

Store findings as string in `rca_findings`. Set `current_phase = "optimizing_prompts"`.

---

### `prompt_optimizer`
**Output keys:** Updated `parameter_records` (with improved prompts), incremented `current_iteration`, `current_phase`, `progress_log`

For each below-target parameter, send Claude:
- Current prompt
- `rca_findings`
- User clarification answers (if any)
- Instruction to produce an improved prompt addressing the identified failure patterns
- Constraint: preserve the `Yes/No/NA` single-word output format

**Before overwriting `current_prompt`:** append the current prompt + its accuracy to `iteration_history`.
Increment `current_iteration`. Reset `current_predictions = {}` for each affected parameter. Set `current_phase = "evaluating"`.

---

### `finalize`
**Output keys:** `final_report`, `optimization_complete = True`, `current_phase = "complete"`, `progress_log`

Mark below-target parameters as `"max_iterations_reached"`, converged parameters as `"converged"`. Compile `final_report` (see Report Schema).

---

## FastAPI API Contract

Base URL: `/api` — responses `application/json` unless noted.
Errors: `{"error": "<message>", "detail": "<optional>"}`

---

### `POST /api/sessions`
**Content-Type:** `multipart/form-data`
**Fields:** `file` (CSV), `max_iterations` (int, default 5, max 10), `accuracy_target` (float, default 0.80)

**201:**
```json
{
  "session_id": "uuid4",
  "parameters_detected": ["greeting_compliance", "empathy_demonstration"],
  "excluded_parameters": [],
  "conversation_count": 42
}
```
**400:** CSV validation error with specific field/row detail.

Kicks off `asyncio.create_task(run_graph(...))`. Returns immediately without waiting for completion.

---

### `GET /api/sessions/{session_id}`
**200:**
```json
{
  "session_id": "...",
  "current_phase": "awaiting_clarification",
  "current_iteration": 0,
  "clarifying_questions": [...],
  "parameter_summary": {
    "greeting_compliance": {"accuracy": 0.0, "status": "pending"}
  },
  "progress_log": ["CSV parsed: 42 conversations, 2 parameters"]
}
```
`clarifying_questions` is always present (empty array if none). `parameter_summary` reflects latest benchmarking results.

---

### `POST /api/sessions/{session_id}/answers`
**Body:** `{"answers": {"q1": "First name only is acceptable."}}`
**200:** `{"status": "resumed"}`

Resumes the LangGraph graph using `Command(resume=...)`. See Interrupt Pattern above.

---

### `GET /api/sessions/{session_id}/stream`
**Content-Type:** `text/event-stream`

```
event: progress
data: {"phase": "evaluating", "message": "Iteration 2: greeting_compliance (18/42)", "timestamp": "..."}

event: complete
data: {"session_id": "..."}

event: error
data: {"message": "..."}
```

Stream until `complete` or `error`. Backend must set `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers.

---

### `GET /api/sessions/{session_id}/report`
**200:** Full report JSON (see Report Schema).
**202:** `{"status": "in_progress", "current_phase": "..."}` if not complete.

---

### `DELETE /api/sessions/{session_id}`
**204:** No content. Removes session from store.

---

## Report Schema

```json
{
  "session_id": "...",
  "generated_at": "ISO-8601",
  "summary": {
    "total_parameters": 5,
    "parameters_meeting_target": 3,
    "parameters_below_target": 2,
    "overall_accuracy": 0.83,
    "total_iterations": 3,
    "total_conversations": 42,
    "accuracy_target": 0.80
  },
  "parameters": {
    "greeting_compliance": {
      "status": "converged",
      "final_accuracy": 0.87,
      "final_precision": 0.91,
      "final_recall": 0.83,
      "final_f1": 0.87,
      "confusion_matrix": {"tp": 18, "tn": 19, "fp": 2, "fn": 3},
      "not_applicable_count": 5,
      "final_prompt": "...",
      "optimization_notes": "Added first-name specificity based on user clarification.",
      "iteration_history": [
        {"iteration": 0, "accuracy": 0.62},
        {"iteration": 1, "accuracy": 0.79},
        {"iteration": 2, "accuracy": 0.87}
      ],
      "rca_findings": null,
      "recommendations": []
    },
    "technical_accuracy": {
      "status": "max_iterations_reached",
      "final_accuracy": 0.71,
      "rca_findings": "LLM cannot verify factual accuracy without a knowledge base. 73% of errors are FP.",
      "recommendations": [
        "Reframe to evaluate information completeness rather than factual accuracy.",
        "Consider whether this criterion is automatable without a knowledge base."
      ]
    }
  }
}
```

All `ParameterOptimizationRecord` fields must be present per parameter. `rca_findings` and `recommendations` are null/[] for converged parameters. `iteration_history` entries include `prompt` only for converged parameters (omit from max_iterations_reached to keep response size manageable).

---

## Angular Frontend — Page Specifications

**Step 1: Upload (`/upload`)**
- CSV dropzone (click + drag), `.csv` only, client-side type check
- `max_iterations` (default 5) and `accuracy_target` (default 0.80) inputs
- POST → navigate to `/clarification/:id` if `clarifying_questions.length > 0`, else `/progress/:id`

**Step 2: Clarification (`/clarification/:sessionId`)**
- One textarea per question; `rationale` shown as subtext
- All fields required; submit blocked until complete
- POST answers → navigate to `/progress/:id`

**Step 3: Progress (`/progress/:sessionId`)**
- Connect SSE on component mount; disconnect on destroy
- `current_phase` as status badge; scrollable `progress_log`
- Poll `GET /sessions/:id` every 3s for per-parameter accuracy mini-cards
- SSE `complete` → navigate to `/results/:id`; SSE `error` → inline error state

**Step 4: Results (`/results/:sessionId`)**
- Summary cards: total / met target / overall accuracy / iterations
- Parameters table: name, status badge, accuracy, iterations, details toggle
- Detail panel: final prompt + copy button, accuracy sparkline (inline SVG), 2×2 confusion matrix, RCA findings, recommendations
- Status colours: green ≥80%, amber 70–79%, red <70%

---

## LLM Prompt Construction Rules

Apply to every Claude call in every node:

1. Output format constraint (always last line): `"Respond with exactly one word: Yes, No, or NA. Do not include any explanation."`
2. NA definition: `"Respond NA if this criterion is not relevant to or cannot be assessed from this conversation."`
3. Evidence grounding: `"Base your evaluation only on what is explicitly stated or clearly implied in the transcript."`
4. Transcript labelling:
   ```
   TRANSCRIPT:
   {transcript}

   EVALUATION CRITERION:
   {criterion}
   ```
5. No few-shot examples in evaluation prompts (token cost). Use examples only inside the optimizer when generating improved prompts.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| LLM response unparseable | Treat as `No`, log warning with `parameter_name` + `iteration` only |
| CSV validation fails | HTTP 400 with specific error; do not create session |
| Session not found | HTTP 404 |
| Graph execution error | Set `current_phase = "error"`, fire SSE `error` event, store error message in session |
| Failed call in async batch | Catch per call; do not abort the batch |
| SSE client disconnects | Backend continues; full `progress_log` available on next poll |
