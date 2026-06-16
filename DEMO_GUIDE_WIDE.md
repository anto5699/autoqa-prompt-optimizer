# AutoQA Prompt Optimizer — Stakeholder Demo Guide (Wide CSV)

This document gives you everything you need to run a clean, end-to-end demo using the 3-parameter wide-format CSV, in under 15 minutes.

---

## What the Demo Shows

The system takes vague, human-written descriptions of QA evaluation rules and autonomously refines them until they achieve ≥90% accuracy against ground truth labels — without anyone writing a single line of prompt engineering.

The demo uses a retail contact centre dataset (12 conversations, 3 rules). The rules start with intentionally imprecise descriptions that are semantically plausible but analytically incomplete. The system:
1. Detects ambiguity and asks clarifying questions
2. Runs the vague descriptions against the conversations and scores accuracy
3. Analyses which conversations were misclassified and why (RCA with full transcript evidence)
4. Rewrites the description to address the failure pattern
5. Repeats until the rule converges at ≥90% or the iteration budget is exhausted

This demo uses only static (answer) rules — no trigger rules — making it a cleaner walkthrough for audiences unfamiliar with dynamic metrics.

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

**Demo file:** `prompt optimisation POC/demo_wide.csv`

---

## Step 1 — Upload the CSV

**What to say:**
> "We start by uploading a CSV of real conversations with QA parameters defined by the operations team. The system parses the rules and ground truth labels automatically."

**Action:** Upload `demo_wide.csv`.

Leave the defaults:
- **Max iterations:** 5
- **Accuracy target:** 90%

**What appears:** 3 rules detected — all static answer rules — across 12 conversations.

**Talking point:** This dataset uses a wide-format CSV — each evaluation parameter is its own column, each row is a conversation. The system handles both this format and the multi-row format automatically.

---

## Step 2 — Enter Rule Descriptions

**What to say:**
> "Now we enter how QA managers would naturally describe each rule — in plain language, the way they'd write it in a style guide or briefing document. No structured syntax required."

Enter exactly these descriptions:

| Rule ID | Description to type |
|---|---|
| `Greeting Compliance` | The agent gave a professional greeting |
| `Empathy Shown` | The agent was empathetic towards the customer |
| `Call Wrap-up` | The agent ended the call politely |

**Talking point:** These descriptions are deliberately vague — exactly the quality you'd find in a real QA handbook written for human raters, not LLMs. "Professional" and "politely" mean different things to different people. The goal is to turn these into machine-executable evaluation criteria.

---

## Step 3 — Clarification Questions

**What to say:**
> "Before touching a single conversation, the system detects which descriptions are ambiguous and asks targeted questions. It doesn't ask about everything — only genuine semantic gaps that would cause misclassification."

The system will generate 2 questions per ambiguous rule. Answer as follows:

### `Greeting Compliance` — "The agent gave a professional greeting"

| Question (paraphrased) | Answer to give |
|---|---|
| What specific elements constitute a "professional greeting" — tone, content, or both? | Both company name and agent name must appear: the agent must say "ShopDirect" and state their own name (e.g. "My name is Sarah", "I'm Alex", "This is Jamie") |
| Does the greeting need to follow a specific format, or is any mention of the name acceptable? | Any explicit name introduction counts — the format doesn't matter as long as the agent's name is stated in the opening message |

### `Empathy Shown` — "The agent was empathetic towards the customer"

| Question (paraphrased) | Answer to give |
|---|---|
| What language or behavior specifically demonstrates empathy — is willingness to help sufficient? | No — empathy requires explicit emotional acknowledgment: apologies ("I'm sorry", "I apologise", "I sincerely apologise"), validation ("I understand", "I can understand"), or genuine enthusiasm ("I'd be happy to", "I want to make sure you're getting the best"). Simply offering to process a request does not count. |
| Must the empathy be expressed in response to the customer's stated issue, or can it appear anywhere? | It must appear in the agent's first substantive response to what the customer says — not in a generic closing message |

### `Call Wrap-up` — "The agent ended the call politely"

| Question (paraphrased) | Answer to give |
|---|---|
| What makes a call ending "polite" — is any farewell phrase sufficient? | No — the agent must either thank the customer for calling ("Thank you for calling/contacting ShopDirect") OR offer continued assistance ("Is there anything else I can help you with?"). Simply stating the resolution and ending does not qualify. |
| Does the wrap-up apply to the entire conversation or just the closing? | Only the final 2 messages of the conversation are evaluated |

**Talking point:** Notice that the system asks exactly what an LLM needs to know — not open-ended questions, but targeted semantic probes. Each answer completely redefines what the rule measures without requiring the user to write structured prompts.

---

## Step 4 — Watch the Optimization Run

**What to say (while the progress bar runs):**

**During baseline evaluation (iteration 0):**
> "The system first evaluates all 12 conversations using the vague descriptions. This gives us a baseline accuracy score — the ceiling for what an untuned prompt can achieve."

Expected baseline accuracy (approximate):
- `Greeting Compliance`: ~55–65% (agents who say "Hi, ShopDirect support" sound professional without stating a name)
- `Empathy Shown`: ~65–75% (agents saying "I'll check on it" or "Let me check" can read as understanding)
- `Call Wrap-up`: ~60–70% (brief endings like "Okay, is that all?" or "It's on the way. Bye." are ambiguously polite)

**During RCA (iterations 1–3):**
> "For each failing rule, the system reads the actual transcripts from the misclassified conversations. It sees exactly what was said, identifies the pattern — for example, an agent who sounds professional without ever stating their name — and rewrites the description to block that failure mode."

**Talking point:** The key insight is that the LLM doing the RCA sees the same transcripts a human QA analyst would review. It's not guessing from statistics — it's reading the evidence.

**A useful moment to highlight:** conv_008 is the interesting exception in this dataset — the agent passes `Call Wrap-up` ("Done. Anything else?") but fails `Greeting Compliance` and `Empathy Shown`. Point out that the system evaluates each rule independently — good wrap-up behaviour doesn't compensate for a poor opening.

---

## Step 5 — View the Report

**What to say:**
> "The final report shows exactly what changed, why it changed, and what accuracy each rule reached. It's auditable — you can trace every decision from the initial description through to the final prompt."

**Things to point out in the report:**

1. **Convergence table** — which rules hit 90% and which didn't, with final accuracy and status.

2. **Per-rule descriptions** — show the initial vs final description for `Greeting Compliance`. The final version will include specific PASS_CRITERIA about company name and agent name, with concrete transcript examples of what "stating your name" looks like.

3. **Accuracy trajectory** — for `Empathy Shown`, show the iteration-by-iteration improvement. The baseline may misclassify agents who offer functional help ("I'll check on it") as empathetic, which the RCA corrects by tightening the language criteria.

4. **Rules that converge quickly** — `Greeting Compliance` often converges in 1–2 iterations once the name-stating criterion is made explicit. Point out the system locks it and doesn't touch it further.

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
> The report surfaces rules that reached the iteration cap with a root cause analysis explaining why. For example, if a rule requires judgment beyond the transcript (like "did the agent build rapport?"), the system will identify that the criterion can't be reliably observed from text alone and flag it for human evaluation.

**"This dataset only has 12 conversations — does it scale?"**
> The same pipeline runs on datasets of any size. The demo uses 12 to keep the walkthrough fast. In production, larger datasets give the RCA more signal, which typically accelerates convergence.

---

## Ground Truth Reference (for presenter awareness)

| Conversation | Scenario | Greeting Compliance | Empathy Shown | Call Wrap-up |
|---|---|---|---|---|
| conv_001 | Double billing charge | Yes (Sarah) | Yes ("I'm so sorry") | Yes (Have a great day) |
| conv_002 | Return request | No (Hello, what do you want?) | No | No |
| conv_003 | Damaged package | Yes (Alex) | Yes ("I sincerely apologise") | Yes (Is there anything else) |
| conv_004 | Billing question | No (ShopDirect support.) | No | No |
| conv_005 | Order cancellation | Yes (Jamie) | Yes ("I understand that can be frustrating") | Yes (Is there anything else) |
| conv_006 | Late delivery | No (what's your issue?) | No | No |
| conv_007 | Wrong item received | Yes (Sam) | Yes ("I'm truly sorry") | Yes (Have a great day) |
| conv_008 | Address update | **No** (ShopDirect, hello.) | **No** | **Yes** (Anything else?) |
| conv_009 | Refund status | Yes (Chris) | Yes ("I can understand the wait") | Yes (Have a lovely day) |
| conv_010 | Order tracking | No (Support, go ahead.) | No | No |
| conv_011 | Price match | Yes (Taylor) | Yes ("I'd be happy to look into that") | Yes (Is there anything else) |
| conv_012 | Discount code | No (ShopDirect.) | No | No |

**Notable edge cases to be aware of:**
- **conv_008** is the only conversation that passes Call Wrap-up while failing both other rules — useful to highlight independent rule evaluation.
- **conv_011** passes Empathy with enthusiasm language ("I'd be happy to") rather than an apology — a good talking point for how the system learns to recognise diverse empathy signals.
- **conv_004** ends with "Okay, is that all?" which sounds like an offer of further help but is marked No — the RCA will correctly identify that this phrasing is dismissive rather than proactive.
