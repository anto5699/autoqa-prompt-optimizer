# AutoQA Prompt Optimizer

An agentic system that autonomously optimizes LLM evaluation prompts for contact center quality assurance. Upload a CSV of conversations with ground truth labels — the system iteratively refines your evaluation rule descriptions until they hit a configurable accuracy target.

---

## How It Works

```
Upload CSV  →  Enter Descriptions  →  Answer Clarifications  →  Watch Optimization  →  Export Results
```

1. **Upload** a CSV of conversations paired with per-rule ground truth labels (Yes / No / NA)
2. **Describe** what each evaluation parameter means in plain language
3. **Answer** any clarifying questions the system asks about ambiguous rules
4. **Watch** the agent iterate: evaluate → analyse failures → rewrite descriptions → repeat
5. **Export** results in three formats: evaluations CSV (wide format), optimised prompts CSV, or a full PDF report

The system stops when every rule meets the accuracy target or the iteration cap is reached — whichever comes first.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+, npm
- An OpenAI API key

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
# Set OPENAI_API_KEY in .env

uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npx ng serve --proxy-config proxy.conf.json --port 4200
```

Open `http://localhost:4200`.

The proxy config routes all `/api` requests to `http://localhost:8000`, so CORS is not an issue during development.

---

## Environment Variables

Create `backend/.env` (see `backend/.env.example`):

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | Model for all LLM calls. `gpt-4o-mini` works for lower cost |
| `MAX_CONCURRENT_LLM_CALLS` | `5` | Semaphore cap on parallel evaluator calls |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CORS_ORIGINS` | `http://localhost:4200` | Allowed origins for the FastAPI backend |
| `ACCURACY_TARGET` | `0.90` | Default accuracy target used if not specified at upload |

---

## CSV Format

The input CSV has **one row per conversation × rule combination**. If you have 20 conversations and 4 rules, that is 80 rows.

### Column Reference

| Column | Type | Description |
|---|---|---|
| `conversation_id` | string | Unique identifier for the conversation. All rows sharing an ID use the same transcript. |
| `transcript` | JSON string | Array of message objects (see format below) |
| `rule_id` | string | Unique rule identifier. Use `rule_answer_N` for answer rules, `rule_trigger_N` for trigger rules, linked by the same suffix N. |
| `rule_type` | `answer` \| `trigger` | `answer` — evaluates agent adherence. `trigger` — detects whether the scenario is in scope for this conversation. |
| `speaker` | `agent` \| `customer` | Whose behaviour is being evaluated |
| `evaluation_type` | `first` \| `last` \| `entire` | Which part of the conversation to consider: first N messages, last N messages, or the entire transcript |
| `n_messages` | integer | Number of messages to consider when `evaluation_type` is `first` or `last`. Ignored for `entire`. |
| `description` | string | Your initial natural-language description of what this rule checks. The optimizer will refine this. |
| `ground_truth` | `Yes` \| `No` \| `NA` | Ground truth label. `NA` rows are excluded from all accuracy calculations. |

### Transcript JSON Format

Each `transcript` cell is a JSON array of message objects:

```json
[
  {
    "msg": "Thank you for calling. My name is Sarah, how can I help?",
    "messageId": 1,
    "speaker": "agent",
    "timestamp": 1700000000
  },
  {
    "msg": "Hi, I need to track my order.",
    "messageId": 2,
    "speaker": "customer",
    "timestamp": 1700000030
  }
]
```

### Trigger vs Answer Rules (Dynamic Metrics)

Some evaluation parameters only apply to conversations where a specific scenario occurred. These use a **trigger + answer pair**:

- `rule_trigger_N` — detects whether the scenario is in scope (`isQualified: true/false`)
- `rule_answer_N` — evaluates adherence, **linked to trigger_N by the same suffix**

When a trigger rule returns `isQualified: false`, the corresponding answer rule ground truth is treated as `NA` and excluded from accuracy math.

Static metrics (always applicable) have an answer rule only — no trigger.

### Minimum Data Requirements

Rules with fewer than 5 evaluable rows (non-NA ground truths) are excluded from the optimization run. Aim for at least 10–20 conversations per rule for reliable accuracy measurements.

### Example CSV

A 15-conversation × 4-rule demo CSV is included at `demo_conversations.csv`. It covers a retail support scenario with:

- `rule_answer_1` — agent states their name in the first 2 messages
- `rule_trigger_2` — customer provides an order number
- `rule_answer_2` — agent repeats the order number verbatim (NA when trigger=No)
- `rule_answer_3` — agent asks "is there anything else" in the last 2 messages

Generate your own demo data:

```bash
python generate_demo_csv.py
```

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Angular Frontend                             │
│   Upload CSV → Enter Descriptions → Answer Questions → View Report  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP / SSE
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                              │
│   POST /sessions          POST /sessions/{id}/descriptions           │
│   POST /sessions/{id}/answers     GET /sessions/{id}/report         │
│   In-memory session store (session_id → state snapshot)             │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ asyncio.create_task
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     LangGraph Agent Graph                            │
│                                                                      │
│  ingestion → baseline_generator → ambiguity_detection               │
│       ↓ (interrupt on questions)                                     │
│  [user answers via API resume]                                       │
│       ↓                                                              │
│  evaluator → benchmarking → router                                   │
│       ↓ (below target)              ↓ (all converged or max_iter)    │
│  rca_analyzer → prompt_optimizer   finalize_report                   │
│       └────────── loop back to evaluator ──────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    OpenAI API (ChatOpenAI)
```

### Agent Nodes

| Node | Purpose |
|---|---|
| `ingestion` | Parses the uploaded CSV into per-rule `parameter_records`; validates state |
| `baseline_generator` | Normalises all rule descriptions into the required structured format (METRIC_NAME / SPEAKER / ACTION / PASS_LOGIC / PASS_CRITERIA / EXAMPLES) before the first evaluation. Generates from scratch when no description is provided, rewrites from clarification answers when answers exist, and reformats plain-text descriptions that are already written but not in the structured format — without changing their meaning. |
| `ambiguity_detection` | LLM-classifies each description for ambiguity; generates up to 2 targeted clarification questions per ambiguous rule; pauses the graph via `interrupt()` |
| `evaluator` | Sends **one LLM call per conversation** containing all rule descriptions; parses the JSON response into per-rule predictions |
| `benchmarking` | Computes accuracy / precision / recall / F1 per rule; regression guard reverts a description if it performs worse than the prior best |
| `router` | Routes to `finalize_report` when all rules converge or the iteration cap is hit; otherwise continues to `rca_analyzer` |
| `rca_analyzer` | Collects FP/FN examples with full transcripts; asks the LLM to identify the root cause of failures in the current description |
| `prompt_optimizer` | Reads RCA findings, accuracy trajectory, and clarification answers; rewrites the description to address identified weaknesses; detects stagnation (4+ identical accuracy values) and forces a different rewrite strategy |
| `evaluator` | Sends **one LLM call per conversation** containing all active (non-converged) rule descriptions; converged rules are skipped to prevent LLM non-determinism from regressing rules that already hit target |
| `finalize_report` | Assembles the structured result with per-rule metrics, optimized descriptions, regression warnings, and root cause analysis for rules that didn't converge |

### Optimization Loop

```
For each iteration (up to max_iterations):
  1. Evaluate all conversations → per-rule confusion matrices
  2. Benchmark: compute accuracy, apply regression guard
  3. If all rules converged → stop
  4. For rules below target:
     a. RCA: identify why FP/FN cases failed
     b. Optimizer: rewrite description addressing root causes
  5. Repeat
```

The optimizer never modifies the master evaluation system prompt — only the `description` field within each rule object is rewritten.

### Clarification Interrupt Pattern

Before the first evaluation, `ambiguity_detection` may pause the graph:

```
POST /sessions/{id}/descriptions   →  graph starts
                                    →  graph reaches ambiguity_detection
                                    →  graph calls interrupt()
GET  /sessions/{id}/stream          ←  SSE event: clarification_needed
POST /sessions/{id}/answers         →  graph resumes with answers injected
                                    →  evaluator → benchmarking → ...
```

### Real-time Progress

The frontend connects to `GET /sessions/{id}/stream` (Server-Sent Events). Each phase transition emits an SSE event with a phase label and log message. The progress page displays a live log and phase indicator.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions` | Upload CSV, set `max_iterations` and `accuracy_target`. Returns `session_id`. |
| `GET` | `/api/sessions/{id}` | Fetch session state including parsed rules |
| `POST` | `/api/sessions/{id}/descriptions` | Submit initial descriptions; starts the graph |
| `GET` | `/api/sessions/{id}/stream` | SSE stream of phase events and log lines |
| `POST` | `/api/sessions/{id}/answers` | Submit clarification answers; resumes the graph |
| `GET` | `/api/sessions/{id}/report` | Fetch the final structured report |

---

## Running Tests

```bash
cd backend
pytest tests/
```

Tests cover CSV parsing, accuracy metric calculation, benchmarking logic, regression guard, and the evaluator node. No live LLM calls are made in tests — all LLM interactions are mocked.

---

## Limitations

- **In-memory only.** Session state is lost on server restart.
- **Single-user.** No auth, no multi-tenancy.
- **LLM cost.** Each iteration makes `N_conversations + N_rules_below_target` LLM calls. A 20-conversation × 4-rule run over 5 iterations costs roughly 600–1000 OpenAI API calls.
- **Not for production.** This is an R&D prototype built for demonstrating the optimization concept.

---

## Project Structure

```
autoqa-prompt-optimizer/
├── backend/
│   ├── agents/
│   │   ├── graph.py              # LangGraph StateGraph definition
│   │   └── nodes/
│   │       ├── ingestion.py
│   │       ├── baseline_generator.py
│   │       ├── ambiguity_detection.py
│   │       ├── evaluator.py
│   │       ├── benchmarking.py
│   │       ├── rca_analyzer.py
│   │       ├── prompt_optimizer.py
│   │       └── finalize_report.py
│   ├── api/
│   │   └── routes/
│   │       ├── sessions.py       # REST endpoints
│   │       └── stream.py         # SSE endpoint
│   ├── utils/
│   │   └── csv_parser.py
│   ├── config.py                 # Pydantic settings
│   ├── main.py                   # FastAPI app entrypoint
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/app/
│       ├── pages/
│       │   ├── upload/           # CSV upload + config
│       │   ├── descriptions/     # Initial rule descriptions
│       │   ├── progress/         # Live SSE log
│       │   ├── clarification/    # Clarification Q&A
│       │   └── results/          # Final report
│       └── core/
│           ├── services/         # SessionService (HTTP + SSE)
│           └── models/           # TypeScript interfaces
├── demo_conversations.csv        # 15-conversation demo dataset
├── generate_demo_csv.py          # Script to regenerate demo data
└── ARCHITECTURE.md               # Detailed architecture diagrams
```
