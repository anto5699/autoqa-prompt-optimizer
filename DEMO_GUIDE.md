# AutoQA Prompt Optimizer — Stakeholder Demo Guide

This document gives you everything you need to run a clean, end-to-end demo in under 15 minutes.

---

## What the Demo Shows

The system takes vague, human-written descriptions of QA evaluation rules and autonomously refines them until they achieve ≥90% accuracy against ground truth labels — without anyone writing a single line of prompt engineering.

The demo uses a retail contact centre dataset (15 conversations, 4 rules). The rules start with intentionally imprecise descriptions that are semantically plausible but analytically incomplete. The system:
1. Detects ambiguity and asks clarifying questions
2. Runs the vague descriptions against the conversations and scores accuracy
3. Analyses which conversations were misclassified and why (RCA with full transcript evidence)
4. Rewrites the description to address the failure pattern
5. Repeats until the rule converges at ≥90% or the iteration budget is exhausted

---

## Setup (do this before the meeting)

```bash
# Terminal 1 — Backend
cd autoqa-prompt-optimizer/backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd autoqa-prompt-optimizer/frontend
ng serve --proxy-config proxy.conf.json
```

Open `http://localhost:4200` and confirm the upload screen is visible.

**Demo file:** `autoqa-prompt-optimizer/demo_conversations.csv`

---

## Step 1 — Upload the CSV

**What to say:**
> "We start by uploading a CSV of real conversations with QA parameters defined by the operations team. The system parses the rules and ground truth labels automatically."

**Action:** Upload `demo_conversations.csv`.

Leave the defaults:
- **Max iterations:** 5
- **Accuracy target:** 90%

**What appears:** 4 rules detected — 3 answer rules and 1 trigger rule — across 15 conversations.

**Talking point:** Trigger rules detect whether a scenario is in scope for a conversation (e.g. "did the customer have an order number?"). Answer rules evaluate what the agent did. Dynamic metrics pair a trigger with an answer — the answer is only scored when the trigger fires.

---

## Step 2 — Enter Rule Descriptions

**What to say:**
> "Now we enter how QA managers would naturally describe each rule — in plain language, the way they'd write it in a style guide or briefing document. No structured syntax required."

Enter exactly these descriptions:

| Rule ID | Description to type |
|---|---|
| `rule_answer_1` | The agent greeted the customer warmly |
| `rule_trigger_2` | The customer had a specific request |
| `rule_answer_2` | The agent confirmed the customer's details |
| `rule_answer_3` | The call was wrapped up properly |

**Talking point:** These descriptions are deliberately vague — exactly the quality you'd find in a real QA handbook written for human raters, not LLMs. The goal is to turn these into machine-executable evaluation criteria.

---

## Step 3 — Clarification Questions

**What to say:**
> "Before touching a single conversation, the system detects which descriptions are ambiguous and asks targeted questions. It doesn't ask about everything — only genuine semantic gaps that would cause misclassification."

The system will generate 2 questions per ambiguous rule. Answer as follows:

### `rule_answer_1` — "The agent greeted the customer warmly"

| Question (paraphrased) | Answer to give |
|---|---|
| What specific behaviour constitutes a warm greeting? | By "warm greeting" I mean the agent explicitly states their name — e.g. "My name is Sarah" or "This is James" |
| Is this evaluated on the opening or the entire conversation? | Only in the first 2 messages of the conversation |

### `rule_trigger_2` — "The customer had a specific request"

| Question (paraphrased) | Answer to give |
|---|---|
| What qualifies as a "specific request" vs a general enquiry? | A specific request means the customer provides an alphanumeric order number or reference number during the conversation |
| Any request about an account, or only certain types? | Only conversations where the customer explicitly states an order ID, reference number, or ticket number |

### `rule_answer_2` — "The agent confirmed the customer's details"

| Question (paraphrased) | Answer to give |
|---|---|
| Which details must be confirmed — account info, order number, address? | The agent must confirm the exact order or reference number the customer provided |
| What counts as confirmation — paraphrase or verbatim repeat? | The agent must read back the exact same number verbatim — not just acknowledge it |

### `rule_answer_3` — "The call was wrapped up properly"

| Question (paraphrased) | Answer to give |
|---|---|
| What does "properly" mean here — polite farewell, resolution check, or a specific phrase? | "Properly" means the agent explicitly asks "Is there anything else I can help you with?" |
| Is this based on the entire conversation or just the closing? | Only the last 2 messages |

**Talking point:** Notice the questions are surgical — they ask exactly what an LLM needs to know to evaluate the rule unambiguously. Each answer completely redefines what the rule measures without requiring the user to write a structured prompt.

---

## Step 4 — Watch the Optimization Run

**What to say (while the progress bar runs):**

**During baseline evaluation (iteration 0):**
> "The system first evaluates all 15 conversations using the vague descriptions. This gives us a baseline accuracy score — the ceiling for what an untuned prompt can achieve."

Expected baseline accuracy (approximate):
- `rule_answer_1`: ~55–65% (many agents sound warm without saying their name)
- `rule_trigger_2`: ~60–70% (many customers have "specific requests" that aren't order numbers)
- `rule_answer_2`: ~55–65% (acknowledging an issue ≠ repeating the reference verbatim)
- `rule_answer_3`: ~65–75% (polite farewells ≠ asking the specific closing question)

**During RCA (iterations 1–3):**
> "For each failing rule, the system reads the actual transcripts from the misclassified conversations. It sees exactly what was said, identifies the pattern — for example, an agent saying 'How can I help?' without a name — and rewrites the description to block that failure mode."

**Talking point:** The key insight is that the LLM doing the RCA sees the same transcripts a human QA analyst would review. It's not guessing from statistics — it's reading the evidence.

---

## Step 5 — View the Report

**What to say:**
> "The final report shows exactly what changed, why it changed, and what accuracy each rule reached. It's auditable — you can trace every decision from the initial description through to the final prompt."

**Things to point out in the report:**

1. **Convergence table** — which rules hit 90% and which didn't, with final accuracy and status.

2. **Per-rule descriptions** — show the initial vs final description for `rule_answer_1`. The final version will have specific PASS_CRITERIA about agent name-stating, with concrete transcript examples.

3. **Accuracy trajectory** — for any rule that took multiple iterations, show the iteration-by-iteration improvement.

4. **Rules that converged early** — `rule_trigger_4` typically converges at iteration 0 if the description is semantically aligned. Point out the system is smart enough not to touch what's already working.

**Talking point:** This entire process — from upload to convergence — took under 5 minutes and produced prompts that achieve >90% accuracy. The equivalent manual process (iterating on prompts with a human analyst and re-running evaluations) typically takes days.

---

## Key Talking Points (Stakeholder Questions)

**"How does it know when to stop?"**
> Each rule has an accuracy target (90% here). The moment a rule hits the target, it's locked — no further changes. The system never modifies a rule that's already working. If a rule can't reach target within the iteration budget, it's flagged for human review with the root cause analysis attached.

**"What stops it from over-engineering the prompts?"**
> Two mechanisms. First, a regression guard — if a new description performs worse than the previous best, the system reverts automatically. Second, stagnation detection — if the same accuracy repeats 4 iterations in a row, the system escalates to a structural rewrite rather than incremental tweaks.

**"How does this plug into our existing QA workflow?"**
> The system outputs a structured evaluation description — an explicit PASS/FAIL criteria format with concrete examples. Those descriptions slot directly into the evaluation system as LLM instructions. No custom code required.

**"What happens when a rule genuinely can't be automated?"**
> The report surfaces rules that reached the iteration cap with a root cause analysis explaining why. For example, if a rule requires judgment beyond the transcript (like "did the agent sound empathetic?"), the system will identify that the criterion can't be observed from text alone and flag it for human evaluation.

---

## Ground Truth Reference (for presenter awareness)

| Conversation | Scenario | A1 (name) | T2 (order#) | A2 (repeats#) | A3 (AITAE) |
|---|---|---|---|---|---|
| conv_001 | Order tracking | Yes (Sarah) | Yes (ORD-44218) | Yes | Yes |
| conv_002 | Delivery delay | Yes (James) | Yes (REF-78201) | Yes | Yes |
| conv_003 | Wrong item | Yes (Maria) | Yes (TKT-22913) | Yes | **No** |
| conv_004 | Missing package | **No** | Yes (ORD-99341) | Yes | Yes |
| conv_005 | Overcharge | **No** | Yes (REF-11562) | **No** | Yes |
| conv_006 | Return policy | Yes (David) | **No** | NA | Yes |
| conv_007 | Product availability | Yes (Lisa) | **No** | NA | Yes |
| conv_008 | Password reset | **No** | **No** | NA | **No** |
| conv_009 | Refund status | Yes (Tom) | Yes (ORD-55783) | **No** | **No** |
| conv_010 | Shipping question | **No** | **No** | NA | Yes |
| conv_011 | Damaged product | Yes (Rachel) | Yes (REF-88213) | Yes | Yes |
| conv_012 | Duplicate charge | **No** | Yes (TKT-33418) | Yes | Yes |
| conv_013 | Promo code | Yes (Kevin) | **No** | NA | **No** |
| conv_014 | Address change | Yes (Amy) | Yes (ORD-71924) | **No** | Yes |
| conv_015 | Payment method | **No** | **No** | NA | **No** |
