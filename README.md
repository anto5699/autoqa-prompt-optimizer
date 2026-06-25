# AutoQA Prompt Optimizer

An agentic system that autonomously optimizes LLM evaluation prompts for contact center quality assurance. Upload a CSV of conversations with ground truth labels — the system iteratively refines your evaluation rule descriptions until they hit a configurable accuracy target.
<img width="1195" height="1021" alt="image" src="https://github.com/user-attachments/assets/b110ddad-d425-44d4-945d-501dc4d99966" />

---

## How It Works

```
Upload CSV  →  Enter Descriptions  →  Answer Clarifications  →  Watch Optimization  →  Export Results
```

1. **Upload** a CSV of conversations paired with per-metric ground truth labels (Yes / No / NA)
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
| `OPENAI_MODEL` | `gpt-4o` | Model used for conversation evaluation |
| `OPENAI_OPTIMIZER_MODEL` | `gpt-4o` | Model used for prompt optimization, RCA, and analysis |
| `MAX_CONCURRENT_LLM_CALLS` | `5` | Semaphore cap on parallel evaluator calls |
| `RULES_BATCH_SIZE` | `6` | Number of rules bundled per LLM call in the evaluator. Match this to your production batch size for realistic accuracy measurements. |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CORS_ORIGINS` | `http://localhost:4200` | Allowed origins for the FastAPI backend |
| `ACCURACY_TARGET` | `0.90` | Default accuracy target used if not specified at upload |

---

## CSV Format

The input CSV uses a **wide format** — one row per conversation, one column per evaluation metric.

### Required Columns

| Column | Description |
|---|---|
| `ConversationID` | Unique identifier for the conversation |
| `transcript` | The conversation text (see Transcript Format below) |
| `<MetricName>` | One column per evaluation metric, e.g. `Greeting`, `Verification`. Values must be `Yes`, `No`, or `NA` (see Ground Truth Values below). Add as many metric columns as needed. |

### Ground Truth Values

Each metric column accepts the following values (case-insensitive):

| Accepted value | Normalises to | Meaning |
|---|---|---|
| `Yes` / `yes` / `YES` | `Yes` | Agent adhered |
| `No` / `no` / `NO` | `No` | Agent did not adhere |
| `NA` / `na` | `NA` | Not applicable — excluded from accuracy math |
| `N/A` / `n/a` | `NA` | Not applicable (slash variant) |
| *(blank cell)* | `NA` | Not applicable |

`NA` rows are excluded from all accuracy calculations. Denominator = TP + TN + FP + FN only.

### Transcript Format

The `transcript` column accepts two formats:

**JSON array (preferred):** An array of message objects. Each object needs at minimum a `msg` field; `speaker`, `messageId`, and `timestamp` are optional but useful:

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

**Plain text:** If the transcript column contains plain text rather than JSON, the system wraps it automatically and passes it to the LLM as-is. Timestamps and speaker labels embedded in the text are preserved. No conversion is required.

### Minimum Data Requirements

- At least **10 rows** (conversations) in the CSV
- Metrics with fewer than **5 evaluable rows** (non-NA ground truths) are automatically excluded from the optimization run
- Aim for at least 10–20 conversations per metric for reliable accuracy measurements

### Example Row

```
ConversationID,transcript,Greeting,Verification,Closure
conv_001,"[{""msg"":""Hi, Sarah speaking..."",""speaker"":""agent""}]",Yes,No,Yes
conv_002,"[{""msg"":""Good morning..."",""speaker"":""agent""}]",Yes,NA,Yes
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
| `baseline_generator` | Normalises all rule descriptions into the required structured format (METRIC_NAME / SPEAKER / ACTION / PASS_LOGIC / PASS_CRITERIA / EXAMPLES) before the first evaluation. Generates from scratch when no description is provided, rewrites from clarification answers when answers exist, and reformats plain-text descriptions that are already written but not in the structured format — without changing their meaning. Generated descriptions are capped at 800 tokens. |
| `ambiguity_detection` | LLM-classifies each description for ambiguity; generates up to 2 targeted clarification questions per ambiguous rule; pauses the graph via `interrupt()` |
| `evaluator` | Sends LLM calls per conversation with rules batched in groups of `RULES_BATCH_SIZE`. Converged rules are excluded from evaluation to prevent LLM non-determinism from regressing parameters that already hit target. |
| `benchmarking` | Computes accuracy / precision / recall / F1 per rule; regression guard reverts a description if it performs worse than the prior best |
| `router` | Routes to `finalize_report` when all rules converge or the iteration cap is hit; otherwise continues to `rca_analyzer` |
| `rca_analyzer` | Collects FP/FN examples with full transcripts; asks the LLM to identify the root cause of failures in the current description |
| `prompt_optimizer` | Reads RCA findings, accuracy trajectory, and clarification answers; rewrites the description to address identified weaknesses; detects stagnation (4+ identical accuracy values) and forces a different rewrite strategy. Rewrites are capped at 800 tokens. |
| `finalize_report` | Assembles the structured result with per-rule metrics, optimized descriptions, regression warnings, and root cause analysis for rules that didn't converge |

### Optimization Loop

```
For each iteration (up to max_iterations):
  1. Evaluate all conversations → per-rule confusion matrices
     (rules batched in groups of RULES_BATCH_SIZE per conversation)
  2. Benchmark: compute accuracy, apply regression guard
  3. If all rules converged → stop
  4. For rules below target:
     a. RCA: identify why FP/FN cases failed
     b. Optimizer: rewrite description addressing root causes (≤800 tokens)
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
- **LLM cost.** Each iteration makes roughly `ceil(N_rules / RULES_BATCH_SIZE) × N_conversations` evaluation calls plus one RCA + one optimizer call per underperforming rule. A 20-conversation × 4-rule run over 5 iterations with batch size 6 costs roughly 100–200 OpenAI API calls.
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
