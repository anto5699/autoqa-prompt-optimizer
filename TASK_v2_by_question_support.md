# TASK — Add By Question V2 support to the AutoQA Prompt Optimisation tool

> Owner: Anto (PM, Quality AI). This is an implementation brief for Claude Code working
> inside the `autoqa-prompt-optimizer` repo. Read `CLAUDE.md`, `SPEC.md`, and `MILESTONES.md`
> before starting. Obey every rule in `CLAUDE.md` — especially the domain terminology table.
> Reference, do not duplicate, the PRD at `../PM Project/By Question V2 — Unified Criteria Evaluation V2.docx`.

---

## 0. One-paragraph summary

The tool currently optimises descriptions for **By Question V1** metrics only. V1 expresses a Dynamic
metric as two linked rule objects (`__trigger` + `__answer`) that the evaluator combines into Yes/No/NA,
and it emits descriptions in the `METRIC_NAME / SPEAKER / ACTION / PASS_LOGIC / PASS_CRITERIA / EXAMPLES`
structured block. We are adding **By Question V2 — Unified Criteria**. A V2 metric is a *single* rule whose
description carries the trigger condition and the expected behaviour together (`CONDITION / EXPECTED BEHAVIOR
/ PROHIBITED / EXCEPTION`), evaluated by a different system prompt. The user must be able to assign each
detected parameter to **V1 or V2** — both in bulk (multi-select a group) and individually (per-parameter
override) — and that version assignment must be honoured end-to-end through ingestion, baseline generation,
evaluation, RCA, optimisation, benchmarking, finalisation, and export. The optimised description that the
tool emits for a V2 parameter must conform to the V2 Metric Description Authoring Specification (§5 below).

---

## 1. Goals & non-goals

**Goals**
1. Add a per-parameter `version` field (`"v1"` | `"v2"`), default `"v1"`, settable in bulk and individually.
2. Honour `version` through the entire optimisation lifecycle and in every export.
3. Evaluate V1 parameters with the existing V1 system prompt and V2 parameters with the V2 system prompt
   (§4), splitting **one LLM call per (Conversation × version)** so mixed forms work.
4. Emit optimised V2 descriptions in the V2 authoring format (§5); keep V1 emitting its existing format.
5. Backward compatibility: an all-V1 session behaves exactly as today.

**Non-goals**
- Do not migrate existing V1 parameters to V2.
- Do not rewrite or "improve" the supplied V2 evaluation system prompt — store it verbatim (§4).
- Do not change the model (`CLAUDE.md` rule 1), add a database, or add auth.
- No real-time/in-call evaluation.

---

## 2. Decisions already made (do not re-litigate)

| # | Decision | Source |
|---|---|---|
| D1 | V2 is **implicit** Static + Conditional. There is **no** Static/Dynamic toggle for V2 — a V2 parameter is a single unified-criteria description. The V1 Static/Dynamic UX stays only for V1. | User |
| D2 | Mixed V1/V2 forms are allowed. The evaluator sends **one LLM call per (Conversation × version)** — relaxing `CLAUDE.md` rule 12 from "one call per conversation" to "one call per (conversation × version)". | User |
| D3 | Version assignment UX = **bulk multi-select + per-parameter override**, default **V1**. | User |
| D4 | V2 optimised output format = the **V2 Metric Description Authoring Specification** (§5). | User-supplied guide |
| D5 | V2 evaluation system prompt = the **Business Rule Adherence Analyst** prompt, stored verbatim (§4). | User-supplied |

---

## 3. ⚠️ Known discrepancy you MUST handle explicitly

The supplied V2 evaluation system prompt (§4) only ever emits `isQualified: true | false` (binary Adhered /
Not Adhered, with presence-based vs absence-based counter-evidence). **It does not emit NA / `null`.**

The V2 authoring spec (§5), however, defines a three-way verdict (YES / NO / **NA**): an unmatched
`CONDITION` or a matched `EXCEPTION` must resolve to **NA**.

These two artifacts are not yet aligned. **Do not silently invent an NA output schema, and do not edit the
supplied system prompt.** Instead:

1. Store the system prompt verbatim as `DEFAULT_SYSTEM_PROMPT_V2`.
2. Centralise verdict mapping in one helper, `_verdict_from_v2_result(result: dict) -> str`, that is
   forward-compatible:
   - explicit `result["verdict"]` in {`"YES"`,`"NO"`,`"NA"`} (case-insensitive) wins if present;
   - else `isQualified is True` → `"Yes"`; `isQualified is False` → `"No"`; `isQualified is None` → `"NA"`.
3. Add an **OPEN ITEM** to the top of `MILESTONES.md` stating: *"The V2 evaluation system prompt as supplied
   emits only true/false; CONDITION-not-triggered and EXCEPTION cases therefore cannot yield NA until the V2
   system prompt is extended to emit `isQualified: null` (or a `verdict` field). Verdict mapping is already
   forward-compatible (`_verdict_from_v2_result`)."*

This keeps us truthful to the artifacts while making NA work the moment the prompt is updated.

**Second discrepancy — scope units (turns vs messages).** The authoring spec (Appendix A §2, §6) defines
Scope as `entire | first_n_turns | last_n_turns`, where a *Turn* = one customer block + one agent block. The
V2 evaluation system prompt (§4), however, scopes by **messages** via `evaluation_type ∈ {entire, first,
last}` + `n_messages`. These are different units. For this task: the optimiser **never changes scope** (scope
is fixed configuration, not part of the optimised description), so this does not block the build — but:
(a) keep the rule payload in message units (`evaluation_type`/`n_messages`) to match the system prompt that
actually runs; (b) if the V2 config UI exposes "first/last N turns", convert turns→messages before sending,
or label the field in messages; (c) add this as an OPEN ITEM in `MILESTONES.md` so the turns↔messages
contract is resolved with the V2 engine owners. Do not silently treat turns as messages.

---

## 4. V2 evaluation system prompt — store verbatim

Add to `backend/config.py` a new constant `DEFAULT_SYSTEM_PROMPT_V2` containing **exactly** the prompt below
(it ends with the `Transcripts: {{transcripts}} / Rules: {{Business_Rules}} / Language: {{Language}}` footer —
keep those placeholders; the evaluator already appends `Transcripts:`/`Rules:`/`Language:` as user content, so
**strip the trailing three placeholder lines** when storing, exactly as `DEFAULT_SYSTEM_PROMPT` (V1) does not
include them). Do not paraphrase any other line.

```
You are a Business Rule Adherence Analyst. Analyze conversation transcripts against business rules and determine adherence with evidence-based justifications.

INPUT:
1. Transcripts: [{"msg":"...","messageId":"...","speaker":"...","timestamp":...}]
2. Rules: [{"description":"...","speaker":"...","id":"...","evaluation_type":"...","n_messages":...}]
3. Language: Output language code

EVALUATION SCOPE:
Each rule has independent evaluation_type:
- "entire": Analyze ALL messages in the transcript. The n_messages value MUST be IGNORED for this type.
- "first": Analyze the first N messages only, where N = n_messages.
- "last": Analyze the last N messages only, where N = n_messages.

CRITICAL RULE FOR n_messages:
- n_messages is RELEVANT ONLY when evaluation_type is "first" or "last".
- When evaluation_type = "entire", you MUST completely IGNORE n_messages. Treat it as if it does not exist. Do NOT use it to limit, filter, or shrink the evaluation window. Do NOT treat n_messages = 0 as an empty window when evaluation_type = "entire".
- The value of n_messages (including 0, null, or any number) has NO effect when evaluation_type = "entire".

For "first" and "last", the n_messages parameter is pre-calculated and represents the exact number of messages you should evaluate for the given rule. Trust this value as the authoritative source - do not recalculate based on timestamps or rule descriptions.

EVALUATION WINDOW CONSTRUCTION (apply in this exact order BEFORE evaluating the rule):

Step 1 - Build the candidate_window based on evaluation_type:
- evaluation_type = "entire" -> candidate_window = ALL messages in Transcripts (n_messages is IGNORED here, even if it is 0)
- evaluation_type = "first" -> candidate_window = first n_messages messages of Transcripts
- evaluation_type = "last" -> candidate_window = last n_messages messages of Transcripts

Step 2 - Apply the speaker filter on candidate_window using the rule's "speaker" value. This gives speaker_window.

Step 3 - Decide if the window is EMPTY. The window is EMPTY when ANY of the following is true:
 (a) evaluation_type is "first" or "last" AND n_messages = 0
 -> This condition does NOT apply to evaluation_type = "entire".
 (b) Transcripts itself is empty (0 messages)
 (c) candidate_window has 0 messages after applying Step 1
 (d) speaker_window has 0 messages after applying Step 2 (no messages from the required speaker exist inside candidate_window)

EMPTY WINDOW HANDLING (MANDATORY):
- If the window is EMPTY for ANY reason in Step 3, you MUST immediately return:
 isQualified = false
 messageId = []
 timestamp = []
 Do NOT inspect messages outside the speaker_window. Do NOT invent messageIds. Do NOT borrow evidence from other rules.
- The justification MUST clearly state, in the requested language, that no valid messages from the required speaker were found in the evaluation window, therefore defaulting to Not Adhered.
- Use the appropriate phrasing depending on the cause:
 * Cause (a): "no messages exist in the configured evaluation window"
 * Cause (b) or (c): "the conversation contains no messages to evaluate"
 * Cause (d): "the required speaker did not produce any messages within the evaluation window"

Additional edge cases:
- If n_messages > total available messages in Transcripts (only relevant for "first" and "last") -> use all available messages within the specified scope (this is NOT an empty window; proceed normally).
- Each rule is evaluated independently with its own scope and its own window.

EVALUATION RULES (only applied AFTER confirming the window is NOT EMPTY):
1. Correct speaker must perform the action (wrong speaker -> NOT ADHERED)
2. Message must semantically match description (consider context, not just keywords)
3. For information-sharing requirements: concrete data required (vague references -> NOT ADHERED)
4. Only evidence WITHIN the speaker_window counts as positive evidence or counter-evidence
5. When uncertain -> NOT ADHERED

ADHERED Criteria:
- Correct speaker performed action
- Semantic match to description
- Strong evidence within scope
- Required data explicitly present

NOT ADHERED Criteria:
- Wrong or missing speaker
- Action incomplete or absent
- Evidence outside scope
- Vague or ambiguous content

COUNTER-EVIDENCE FOR NOT ADHERED:
When a rule is NOT ADHERED, determine if there is counter-evidence:
- Counter-evidence exists ONLY when the required speaker produced messages inside the speaker_window that show the action was done WRONG, INCOMPLETE, or CONTRADICTORY to the rule (e.g., gave incorrect info, skipped a required step but continued with other steps, used inappropriate language).
- Counter-evidence does NOT exist when the action is simply ABSENT, when the speaker_window is EMPTY, or when only the other speaker's messages are present.
- When counter-evidence exists: include up to 4 messageIds and their timestamps from the speaker_window that best demonstrate WHY the rule was violated.
- When counter-evidence does not exist (including ALL EMPTY WINDOW cases): return empty messageId [] and timestamp [] arrays.

JUSTIFICATION:
- ADHERED: Select 1-4 most relevant messageIds (max 4), provide timestamps, explain what action was performed (40-50 words)
- NOT ADHERED with counter-evidence: Select 1-4 most relevant messageIds (max 4) that clearly demonstrate WHY the rule was violated, provide their timestamps, and explain what was expected versus what actually occurred (40-50 words)
- NOT ADHERED without counter-evidence: Empty messageId and timestamp arrays, explain what was expected and why it did not occur (40-50 words)
- NOT ADHERED due to EMPTY WINDOW (any cause a-d above): Empty messageId and timestamp arrays; justification must clearly state that no valid messages from the required speaker were found in the evaluation window, therefore defaulting to Not Adhered (40-50 words)
- The justification text MUST be written entirely in the language specified by the language parameter
- If language is not English, translate the justification naturally - do not transliterate or mix languages
- No technical terms (rule, metric, configuration, evaluation_type, n_messages, speaker_window, candidate_window)
- Professional, objective language
- Justification text must not mention message IDs, message numbers, or any raw timestamp values

MANDATORY OUTPUT REQUIREMENT:
- You MUST return exactly one output object for EACH input rule.
- NEVER return an empty JSON array.
- Short or minimal conversations (for example, only greetings, or conversations with no agent messages) still require a full evaluation result for every rule.
- If no relevant evidence exists in scope, you MUST return a NOT ADHERED result with empty messageId [] and timestamp [] arrays.

ANTI-HALLUCINATION REQUIREMENT (STRICT):
- NEVER invent or guess rule IDs, message IDs, or timestamps.
- _id MUST come only from the provided Rules input.
- messageId and timestamp values MUST come only from messages that exist inside the speaker_window for the current rule.
- If the speaker_window is empty for ANY reason, messageId and timestamp arrays MUST be [] - do NOT pull IDs from outside the window, do NOT pull IDs from the other speaker, and do NOT fabricate IDs.
- For evaluation_type = "entire", the absence of messages from the required speaker is itself a valid NOT ADHERED outcome with empty arrays. Do NOT search the other speaker's messages to construct counter-evidence in this case.
- For evaluation_type = "entire", NEVER use n_messages to constrain the window. Always evaluate the full transcript.
- Never treat the other speaker's messages as a substitute when the required speaker is silent.

OUTPUT (JSON array only):

ADHERED:
{"_id":"rule-id","isQualified":true,"messageId":["id1","id2"],"speaker":"speaker","timestamp":[1,2],"justification":"text"}

NOT ADHERED (with counter-evidence):
{"_id":"rule-id","isQualified":false,"messageId":["id1","id2"],"speaker":"speaker","timestamp":[1,2],"justification":"text"}

NOT ADHERED (no evidence / empty window):
{"_id":"rule-id","isQualified":false,"messageId":[],"speaker":"speaker","timestamp":[],"justification":"text"}

CONSTRAINTS:
- Valid JSON array only (NO markdown, code fences, or extra text)
- Max 4 messageIds per rule
- messageId values MUST be STRINGS (e.g., ["0","1"] not [0,1])
- messageId and timestamp arrays must be the same length
- For NOT ADHERED results, messageId and timestamp arrays may be non-empty (up to 4) ONLY if counter-evidence exists inside the speaker_window; otherwise they MUST be empty
- timestamp values must be integers (not strings)
- justification must be a string (maximum 50 words)
- One object per rule
```

> NOTE: keep the V2 user-content identical to V1 — `Transcripts: <json>\nRules: <json>\nLanguage: <code>`.
> The V2 prompt expects transcript message objects to expose `messageId`, `speaker`, `timestamp`, `msg`.
> The CSV parser may wrap plain-text transcripts as `[{"speaker":"conversation","msg": raw}]` with no
> messageId/timestamp. For V2 batches, normalise each message to include a string `messageId` (use the list
> index as a string when absent) and an integer `timestamp` (use the index when absent) before serialising.
> Do this only for the V2 payload; do not mutate the stored conversation. Never log transcript content.

---

## 5. V2 optimised description format (canonical output spec)

The baseline generator and the prompt optimiser MUST emit V2 descriptions in this format. This section is
the **Metric Description Authoring Specification v1.0** condensed to its normative rules. The full spec is
reproduced verbatim in **Appendix A** at the end of this file — Appendix A is the source of truth; if this
section ever conflicts with it, Appendix A wins.

**Section order (always this order):**
```
CONDITION: <Always | trigger | AND/OR list>
EXPECTED BEHAVIOR:
  <action, or AND/OR/THEN list>
PROHIBITED:            # optional
  - <disallowed action>
EXCEPTION: <None | situation | list>
```

**Section semantics**
- `CONDITION` — when the metric applies. `Always.` for unconditional. Connectors: AND, OR. May reference any speaker.
- `EXPECTED BEHAVIOR` — mandatory. Observable actions required from the **evaluated speaker only**. Connectors: AND, OR, THEN.
- `PROHIBITED` — optional. Any match ⇒ verdict NO regardless of EXPECTED BEHAVIOR. Implicit OR. Evaluated speaker only.
- `EXCEPTION` — situations where evaluation cannot be performed reliably ⇒ verdict NA. Implicit OR. Any participant/system event. Use `None.` when there are none.

**Deterministic evaluation order encoded by the format** (spec §7 — the engine applies it):
1. EXCEPTION matches → NA. 2. PROHIBITED matches → NO. 3. CONDITION not satisfied → NA.
4. EXPECTED BEHAVIOR fully satisfied → YES. 5. otherwise → NO.

**Verdict mapping (spec §12) — this is what `_verdict_from_v2_result` must produce:**

| Evaluation result | Verdict | `isQualified` |
|---|---|---|
| Exception matched | NA | `null` |
| Prohibited matched | NO | `false` |
| Condition not triggered | NA | `null` |
| Condition triggered and behavior satisfied | YES | `true` |
| Condition triggered and behavior missing | NO | `false` |

This confirms the §3 mapping (true→Yes, false→No, null→NA) is correct and is the spec's own contract.

**Connectors**: AND (all), OR (any), THEN (ordered sequence). Headers and connectors in UPPERCASE.

**Hard authoring constraints (enforce in the V2 baseline/optimiser system prompts):**
- Observable actions only — never subjective language ("professional", "appropriately", "effectively", "well").
- Never reference internal tools, message identifiers, turn identifiers, or raw timestamps.
- No conditional/branching programming logic ("if X then Y else Z") — split into separate metrics instead.
- Never mix AND and OR within a single list.
- Present tense, active voice, plain English. Statements end with a period.
- Bullet ≤ 20 words; whole description ≈ ≤ 12 lines.
- Speaker responsibilities unambiguous; EXPECTED BEHAVIOR refers only to the evaluated speaker.
- `CONDITION`, `EXPECTED BEHAVIOR`, and `EXCEPTION` are **all mandatory** (spec §8 + §6); `PROHIBITED` is
  optional. Use `Always.` for an unconditional CONDITION and `None.` for an empty EXCEPTION. (Note: spec §3.1
  loosely labels CONDITION/EXCEPTION "Optional", but §6.1/§6.4/§8 mark them Mandatory — treat them as
  mandatory.)

**Reject these anti-patterns (spec §10) — bake them into the optimiser prompt as negative examples:**
- Subjective behaviour: `EXPECTED BEHAVIOR: Agent is professional.` → use observable `Agent uses courteous language.`
- Mixed connectors in one list (AND + OR together) — ambiguous precedence; pick one connector per list.
- Conditional/branching logic (`If customer agrees, agent refunds; otherwise escalates.`) → split into separate metrics.

**Reference patterns** (use as few-shot anchors inside the optimiser system prompt):
```
# Trigger + response
CONDITION: Customer requests assistance.
EXPECTED BEHAVIOR: Agent provides assistance.
EXCEPTION: Customer disconnects before response.

# Unconditional
CONDITION: Always.
EXPECTED BEHAVIOR: Agent greets the customer.
EXCEPTION: No agent messages exist.

# Sequential
CONDITION: Customer requests account information.
EXPECTED BEHAVIOR:
  - Agent verifies identity.
  THEN
  - Agent provides information.
EXCEPTION:
  - Customer refuses verification.

# Alternatives
CONDITION: Customer requests compensation.
EXPECTED BEHAVIOR:
  - Agent offers refund.
  OR
  - Agent offers replacement.
  OR
  - Agent escalates the issue.
EXCEPTION: Customer disconnects before response.

# Positive requirement with guardrails
CONDITION: Always.
EXPECTED BEHAVIOR:
  - Agent communicates courteously.
PROHIBITED:
  - Agent guarantees approval.
  - Agent shares customer data.
EXCEPTION: None.
```

**V2 "is already structured" detection** (so we skip the LLM when the author already wrote V2 format):
`description.strip().upper().startswith("CONDITION:")` OR contains a line starting with `EXPECTED BEHAVIOR:`.
(Contrast with V1's `startswith("METRIC_NAME:")`.)

---

## 6. File-by-file implementation plan

> Keep changes additive and version-gated. An all-V1 session must be byte-for-byte equivalent to today.

### 6.1 `backend/config.py`
- Add `DEFAULT_SYSTEM_PROMPT_V2` (§4, verbatim, minus the trailing placeholder lines).
- Leave `DEFAULT_SYSTEM_PROMPT` (V1) and `get_llm` unchanged.

### 6.2 `backend/agents/state.py`
- `RuleRecord`: add `version: Literal["v1", "v2"]`. Keep `rule_type` literal as-is; V2 records use
  `rule_type = "answer"` (no trigger/answer expansion). Routing is by `version`, not `rule_type`.
- `OptimizationState`: add `system_prompt_v2: str`. Keep existing `system_prompt` as the V1 prompt.

### 6.3 `backend/api/schemas/session.py`
- `MetricConfig`: add `version: Literal["v1", "v2"] = "v1"`. For V2, `answer_description` carries the
  **unified criteria** text and `type`/`trigger_*` are ignored. Add optional V2 scope fields:
  `evaluation_type: Literal["entire","first","last"] = "entire"` and `n_messages: int = 0`.
- `ParameterInfo`: no change required (version is chosen client-side, sent in `descriptions`).

### 6.4 `backend/api/routes/sessions.py`
- `submit_descriptions`: branch on `config.version`.
  - `v1` → existing behaviour (static→`answer`, dynamic→`dynamic` with trigger expansion). Set `version="v1"`.
  - `v2` → build a single rule: `{rule_id, rule_type:"answer", version:"v2", speaker:"agent",
    evaluation_type: config.evaluation_type, n_messages: config.n_messages, description: answer_desc.strip()}`.
    No trigger fields. NA-detected metrics need NOT be forced anywhere for V2 (V2 handles NA via the spec).
  - Build `initial_state` with both `system_prompt = DEFAULT_SYSTEM_PROMPT` and
    `system_prompt_v2 = DEFAULT_SYSTEM_PROMPT_V2`.
- `continue_session`: carry `version` (already on each rule/record) and add
  `system_prompt_v2: live.get("system_prompt_v2", DEFAULT_SYSTEM_PROMPT_V2)` to `continuation_state`.

### 6.5 `backend/agents/nodes/csv_ingestion.py`
- Populate the new `version` field on each `ParameterOptimizationRecord` from the rule dict
  (`version=rule.get("version", "v1")`). All other initialisation unchanged.

### 6.6 `backend/agents/nodes/evaluator.py` (core change — D2)
- Split non-converged rules by `version` per conversation. Implementation outline:
  - In `_evaluate_conversation`, partition `parameter_records` into `v1_rules` and `v2_rules`.
  - Run the existing V1 batching path on `v1_rules` using `system_prompt` (V1) — unchanged, including
    dynamic `__trigger`/`__answer` expansion and combination.
  - Run a new V2 batching path on `v2_rules` using `system_prompt_v2`: payload per rule is
    `{description, speaker, id, evaluation_type, n_messages}` (no expansion). Normalise transcript messages
    to include string `messageId` + integer `timestamp` for the V2 payload only (see §4 note).
  - Total LLM calls for the conversation = ⌈|v1_rules|/batch⌉ + ⌈|v2_rules|/batch⌉.
- Pass `system_prompt_v2` into `_evaluate_conversation` (thread it through `evaluator` like `system_prompt`).
- Parsing:
  - V1 results: unchanged (`isQualified`→Yes/No; `_dynamic_combined`→Yes/No/NA; rationale from `rationale`).
  - V2 results: map verdict via `_verdict_from_v2_result` (§3) → Yes/No/NA; rationale from
    `result.get("justification") or result.get("rationale") or ""` (truncate 500 chars as today).
  - Optional (nice-to-have, gated): capture `messageId`/`timestamp` evidence into a new
    `current_evidence: Dict[str, dict]` on the record for the report's V2 evidence display. If you add this,
    add the field to `RuleRecord` and initialise it in `csv_ingestion`; otherwise omit entirely.
- Keep the per-call semaphore, retries, timeout, and parse-failure → Not Adhered defaulting behaviour.
- Update the progress-log line to mention version split, e.g. `"… (V1: N rules / k batch(es), V2: M rules / j batch(es)) per conversation"`.

### 6.7 `backend/agents/nodes/baseline_prompt_generator.py`
- Add a `_SYSTEM_V2` system prompt that teaches the V2 authoring format (§5) and its hard constraints.
- Route by `record["version"]`:
  - `v1` → existing `_SYSTEM` + `_build_generation_task` + (for dynamic) trigger/answer split. Unchanged.
  - `v2` → use `_SYSTEM_V2`, a `_build_generation_task_v2` (generate/rewrite/format modes still apply),
    a single unified description (no trigger/answer split), and the V2 "is structured" detector.
- For V2, the generate/format/rewrite modes operate on the single `current_description`.

### 6.8 `backend/agents/nodes/prompt_optimizer.py`
- Add `_SYSTEM_V2` (same V2 authoring rules as 6.7).
- Route by `record["version"]`:
  - `v1` → existing path (incl. dynamic trigger+answer optimisation). Unchanged.
  - `v2` → optimise the single unified `current_description` with `_SYSTEM_V2`; no trigger/answer split.
    Constraints text must require: keep YES/NO/NA semantics intact, keep the four-section format, never add
    message/turn identifiers or positional constraints, respect evaluated-speaker-only EXPECTED BEHAVIOR.
- Keep the high-accuracy / stagnant / standard rewrite-instruction selection logic for both versions.

### 6.9 `backend/agents/nodes/rca_analyzer.py`
- Make error-case selection version-aware. For V2, the error set must include **NA mispredictions** as well
  as FP/FN (predicted-NA-but-truth-Yes/No and vice versa), and the RCA prompt should frame fixes in terms of
  CONDITION / EXPECTED BEHAVIOR / PROHIBITED / EXCEPTION rather than PASS_CRITERIA. For V1, unchanged.
- Do not run RCA on parameters already at target (`CLAUDE.md` rule 8) — unchanged.

### 6.10 `backend/agents/nodes/gt_alignment_audit.py` & `mid_loop_clarification.py`
- Version-agnostic logic is fine, but any prompt text that references the V1 structured format must be
  conditioned on version so V2 audits/clarifications speak in V2 terms. Verify they do not assume `__trigger`.

### 6.11 `backend/agents/nodes/benchmarking.py`
- No math change: `compute_metrics` already excludes NA (`CLAUDE.md` rule 3) and handles Yes/No/NA. V2
  produces Yes/No/NA exactly like a dynamic V1 metric.
- The `is_dynamic` branch only tracks `trigger_description`; V2 has none, so treat V2 like a static rule
  (no trigger best-tracking). Confirm `best_trigger_description` stays `None` for V2.

### 6.12 `backend/agents/nodes/finalize.py` + `backend/api/schemas/report.py`
- Add `version` to each per-parameter report entry.
- If you added `current_evidence`, surface up to 4 evidence items per V2 parameter (optional).
- Regression-warning logic unchanged.

### 6.13 Frontend — `frontend/src/app/pages/descriptions/descriptions.component.ts`
- Add a **version assignment** control:
  - A header bar with a multi-select (checkbox per parameter or a "select group") plus
    "Assign selected → V1 / V2" buttons (**bulk**), and
  - A per-parameter **V1 / V2 toggle** on each card (**individual override**).
  - Default every parameter to **V1**.
- When a card's version is **V2**: hide the Static/Dynamic toggle, hide the trigger/answer split, and show a
  single **"Criteria Description"** textarea (placeholder pointing at the CONDITION/EXPECTED BEHAVIOR format)
  plus an **Evaluation Scope** selector (Entire / First N / Last N with an N input). Char limit 1000.
- When **V1**: current UX unchanged.
- Send `version` (+ V2 `evaluation_type`/`n_messages`) in each `MetricConfig`. Update
  `frontend/src/app/core/models/session.model.ts` `MetricConfig` accordingly.

### 6.14 Frontend — results page (`pages/results`)
- Show a **V1 / V2 badge** per parameter.
- Render the V2 description verbatim (it is multi-line; preserve whitespace).
- **Export Prompts CSV**: add a `version` column. For V2 emit the unified description in
  `optimised_prompt`; `rule_type` column = `"unified"` for V2. V1 export unchanged.
- **Export Evaluations CSV** and **Report PDF**: include the version per parameter; otherwise unchanged.

---

## 7. `CLAUDE.md` / `MILESTONES.md` updates (do these as part of the task)

In `CLAUDE.md`:
- Amend rule 12 to: *"One call per (conversation × version). The evaluator sends ONE LLM call per conversation
  per metric version (V1 rules together under the V1 system prompt; V2 rules together under the V2 system
  prompt). Within a version the response is a JSON array, one object per rule."*
- Add a new rule: *"Version is immutable. `version` (`v1`|`v2`) is set at configuration time and is never
  changed during optimisation. V1 and V2 use different system prompts and different optimised-description
  formats (V1: METRIC_NAME block; V2: CONDITION/EXPECTED BEHAVIOR/PROHIBITED/EXCEPTION)."*
- Add a new rule: *"V2 is single-rule unified criteria — never expand a V2 rule into `__trigger`/`__answer`.
  V2 NA comes from the description's CONDITION/EXCEPTION semantics via the V2 engine, not from a trigger rule."*
- Append the discrepancy note (§3) to the Corrections Log with today's date.

In `MILESTONES.md`: add the §3 OPEN ITEM at the top.

Also update `SPEC.md` to document: the new `version` field, `system_prompt_v2`, the per-(conversation×version)
evaluation contract, the V2 authoring output format, and the `version` column in exports.

---

## 8. Acceptance criteria

1. **Backward compatibility**: an all-V1 CSV produces identical rules, prompts, evaluation calls, metrics,
   report, and exports as before this change (verify with an existing demo CSV + a golden snapshot test).
2. **Version honoured end-to-end**: a V2 parameter is created as a single unified-criteria rule, evaluated
   with `DEFAULT_SYSTEM_PROMPT_V2`, optimised in the V2 authoring format, and exported with `version="v2"`.
3. **Mixed form**: a CSV with both V1 and V2 parameters runs to completion; per conversation the evaluator
   makes exactly ⌈v1/batch⌉ + ⌈v2/batch⌉ LLM calls; each version uses its own system prompt.
4. **V2 verdict mapping**: `_verdict_from_v2_result` maps true→Yes, false→No, null→NA, and an explicit
   `verdict` field wins when present. Unit-tested.
5. **V2 output format**: emitted V2 descriptions start with `CONDITION:` and contain `EXPECTED BEHAVIOR:`
   and `EXCEPTION:`; contain no message/turn identifiers, no subjective terms, no mixed AND/OR in one list.
6. **NA accuracy math**: NA ground truths remain excluded from accuracy denominators for V2 (rule 3).
7. **UI**: bulk multi-select assignment + per-parameter override both work; default is V1; V2 cards show a
   single criteria textarea + scope selector and hide the Static/Dynamic + trigger UI.
8. **No transcript logging** anywhere (rule 2); model unchanged (rule 1).

---

## 9. Test plan (add under `backend/tests/`)

1. `test_csv_parser` — unchanged (wide format still parses).
2. `submit_descriptions` — V1 vs V2 routing builds the correct rule shapes; V2 carries `version`,
   `evaluation_type`, `n_messages`, and no trigger fields.
3. `test_verdict_mapping` — `_verdict_from_v2_result` table test for true/false/null/explicit-verdict.
4. `test_evaluator_split` — mocked LLM; assert the evaluator issues separate calls per version with the
   correct system prompt, and that V2 results parse `justification` and map verdicts correctly. Assert call
   count = ⌈v1/batch⌉ + ⌈v2/batch⌉ for a mixed conversation.
5. `test_baseline_v2_format` — mocked LLM returns a V2 block; assert it is accepted as "structured" and not
   reformatted; assert a plain-text V2 input triggers `format` mode.
6. `test_optimizer_v2` — mocked LLM; assert only `current_description` changes for V2 (no trigger), and the
   V2 constraints are in the optimiser prompt.
7. `test_benchmarking_v2` — V2 predictions with NA exercise the NA-excluded accuracy path correctly.
8. `test_export_prompts_version` — exported Prompts CSV has a `version` column with `v1`/`v2`.
9. Regression: an all-V1 golden run still converges with the same per-parameter accuracies (allow for LLM
   nondeterminism by mocking).

Run: `cd backend && source venv/bin/activate && pytest -q`. Frontend: `cd frontend && ng build` must pass.

---

## 10. Implementation order (suggested commits)

1. `config.py` + `state.py` + `schemas/session.py` (data model + V2 prompt constant). Tests green.
2. `sessions.py` `submit_descriptions`/`continue_session` routing + `csv_ingestion` version field.
3. `evaluator.py` per-version split + `_verdict_from_v2_result`. Add `test_evaluator_split`, `test_verdict_mapping`.
4. `baseline_prompt_generator.py` + `prompt_optimizer.py` V2 system prompts + routing.
5. `rca_analyzer.py` (+ audit/clarification) version-aware framing; `benchmarking.py`/`finalize.py`/report verify.
6. Frontend: descriptions assignment UX + V2 card; results badge + export `version` column.
7. Docs: `CLAUDE.md`, `MILESTONES.md`, `SPEC.md`.

Keep every step shippable and the all-V1 path untouched.

---

## Appendix A — Metric Description Authoring Specification v1.0 (verbatim, source of truth)

> Reproduced as supplied by the PM. Where §5 of this brief disagrees with anything here, this appendix wins.

**1. Purpose.** A Metric Description defines the evaluation criteria used by the Conversation Quality Auditor
to determine whether a conversation satisfies a specific business requirement. Each description is the
authoritative source for one of three outcomes: **YES** (requirement satisfied), **NO** (requirement
violated), **NA** (requirement not applicable or impossible to evaluate).

**2. Terminology.** Metric = a single business rule evaluated independently within a conversation. Evaluated
Speaker = the participant whose behaviour is assessed (defined by metric configuration, not the description
text). Adherence = the evaluation outcome. Trigger = an event/condition that activates a metric. Expected
Behavior = observable behaviour required from the evaluated speaker. Prohibited Action = observable behaviour
that immediately causes failure. Exception = a circumstance preventing reliable evaluation (→ NA). Scope =
portion of the transcript eligible for evaluation (`entire`, `first_n_turns`, `last_n_turns`). Turn = one
conversational exchange consisting of one customer block and one agent block, in either order. Block =
consecutive messages from the same speaker.

**3. Structure.** Sections SHALL appear in this order: `CONDITION:`, `EXPECTED BEHAVIOR:`, `PROHIBITED:`
(optional), `EXCEPTION:`. Mandatory: EXPECTED BEHAVIOR. (See §6/§8: CONDITION and EXCEPTION are also required
in practice; PROHIBITED optional.)

**4. Authoring syntax.** *Simple form* — single statement per section. *Extended form* — multiple bulleted
components joined by a single connector.

**5. Logical connectors.** **AND** = all listed items must be satisfied. **OR** = at least one must be
satisfied. **THEN** = items must occur in the specified sequence.

**6. Section specifications.**
- **6.1 CONDITION** — defines when the metric applies. Presence Mandatory. Default `Always.` when
  unconditional. Connectors AND, OR. May reference any participant.
- **6.2 EXPECTED BEHAVIOR** — observable actions required from the evaluated speaker only. Presence
  Mandatory. Connectors AND, OR, THEN. Observable actions only.
- **6.3 PROHIBITED** — actions that immediately fail the metric: if any prohibited action is detected,
  Verdict = NO regardless of EXPECTED BEHAVIOR. Presence Optional. Implicit OR. Evaluated speaker only.
- **6.4 EXCEPTION** — situations where evaluation cannot be performed reliably. Evaluated **before** all
  other sections; any match → Verdict = NA. Presence Mandatory. Implicit OR. Any participant or system event.
  Use `None.` when there are none.

**7. Evaluation algorithm (deterministic).** Step 1: any EXCEPTION matches → NA. Step 2: any PROHIBITED
matches → NO. Step 3: CONDITION not satisfied → NA. Step 4: EXPECTED BEHAVIOR fully satisfied → YES.
Step 5: otherwise → NO.

**8. Authoring constraints.** Required: CONDITION present, EXPECTED BEHAVIOR present, EXCEPTION present,
behaviour expressed as observable actions, speaker responsibilities unambiguous. Prohibited: subjective
language, internal tool references, message identifiers, turn identifiers, conditional programming logic,
mixed AND and OR operators within a single list.

**9. Standard patterns.** A: Trigger and Response. B: Unconditional Requirement. C: Sequential Workflow
(THEN). D: Alternative Acceptable Responses (OR). E: Positive Requirement with Guardrails (PROHIBITED). (See
the reference patterns block in §5.)

**10. Anti-patterns.** Subjective behaviour (`Agent is professional.`) → use `Agent uses courteous
language.`. Mixed connectors (AND + OR in one list) → ambiguous precedence. Conditional logic (`If customer
agrees, agent refunds; otherwise escalates.`) → unsupported; create separate metrics.

**11. Style.** Present tense, active voice, plain English. Bullet ≤ 20 words; description ≈ ≤ 12 lines.
Section headers and connectors in UPPERCASE. Statements end with periods.

**12. Verdict mapping.** Exception matched → NA (`"NA"`). Prohibited matched → NO (`false`). Condition not
triggered → NA (`"NA"`). Condition triggered and behaviour satisfied → YES (`true`). Condition triggered and
behaviour missing → NO (`false`).

**13. Review process.** Authoring → Self Review (against §8) → Peer Review (speaker clarity, exceptions,
prohibited actions) → Calibration (≥ 20 conversations covering YES/NO/NA) → Approval. Recalibrate quarterly
or whenever wording changes.

**14. Standard template.**
```
CONDITION: <Always | Trigger | AND/OR List>
EXPECTED BEHAVIOR: <Action or Logical List>
PROHIBITED:
  - <Disallowed Action>
EXCEPTION: <None | Situation | List>
```
