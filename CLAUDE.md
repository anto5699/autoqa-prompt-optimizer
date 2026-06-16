# CLAUDE.md — AutoQA Prompt Optimization System
# Owner: Anto (PM, Quality AI) | Last updated: June 2026
# Details live in SPEC.md and MILESTONES.md — keep this file under 120 lines.

---

## What This Project Is

A standalone R&D prototype of an agentic system that autonomously optimizes AutoQA evaluation prompts.

**Input:** CSV of contact center conversations with evaluation parameters and manual ground truth labels (Yes/No/NA).
**Output:** Refined LLM evaluation prompts achieving ≥80% accuracy against ground truth, plus a structured report with per-parameter metrics and root cause analysis for underperformers.

Build for correctness and demonstrability. This is not a production feature.

---

## When to Read Other Files

| Task | File |
|---|---|
| Any schema, node, API endpoint, or frontend detail | `SPEC.md` |
| Build order, current phase, completion criteria | `MILESTONES.md` |

---

## Tech Stack — Do Not Deviate

| Layer | Technology |
|---|---|
| Backend | FastAPI ≥0.111, Python 3.11+ |
| Agent orchestration | LangGraph ≥0.2 |
| LLM client | langchain-anthropic — model: `claude-3-5-sonnet-20241022` (fixed, never change) |
| Validation | Pydantic v2 ≥2.7 |
| CSV | pandas ≥2.2 |
| Session store | In-memory dict — no database |
| Streaming | Server-Sent Events (SSE) |
| Frontend | Angular ≥17 standalone components, plain CSS, Angular HttpClient, native EventSource |
| Node | 20+, npm |

---

## Environment Variables (`.env`, gitignored)

```
ANTHROPIC_API_KEY=
MAX_CONCURRENT_LLM_CALLS=5
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:4200
```

---

## Rules — Always Apply

1. **Model is fixed.** Always `claude-3-5-sonnet-20241022`. No exceptions.
2. **No transcript logging.** Transcripts go to the LLM only. Never write transcript content to logs or console.
3. **NA exclusion.** NA ground truths are excluded from all accuracy math. Denominator = TP + TN + FP + FN only.
4. **Prompt versioning.** Append current prompt to `iteration_history` before overwriting `current_prompt`.
5. **Hard iteration cap.** Stop at `max_iterations` regardless. Status = `"max_iterations_reached"`, never `"failed"`.
6. **No fabricated metrics.** Only surface values derived directly from the confusion matrix.
7. **Session isolation.** Each `session_id` is one LangGraph thread. Sessions never share state.
8. **RCA scope.** Never run root cause analysis on parameters already at ≥ accuracy target.
9. **Canonical parameter names.** Never normalize, rename, or transform `parameter_name` values from the CSV.
10. **Async graph execution.** Never use FastAPI `BackgroundTasks` for LangGraph graph runs — use `asyncio.create_task` with an async wrapper. BackgroundTasks runs in a thread pool and conflicts with async LangGraph.

---

## What NOT to Build

No auth, no database, no audio processing, no real-time in-call evaluation, no fine-tuning, no Docker, no CI/CD, no email.

---

## Domain Terminology

Use exactly in UI labels, log messages, and code comments.

| Use | Never substitute with |
|---|---|
| Parameter | metric, criterion, check |
| Evaluation prompt | system prompt, instruction |
| Ground truth | label, answer key, annotation |
| Adhered / Not Adhered / Not Applicable | pass/fail, true/false |
| Accuracy target | goal, threshold, benchmark |
| Iteration | epoch, round, cycle |
| Conversation | call, interaction (or "transcript" as a noun for the data row) |

---

## Dev Commands

```bash
# Backend
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install
ng serve --proxy-config proxy.conf.json
# proxy.conf.json routes /api → http://localhost:8000
```
