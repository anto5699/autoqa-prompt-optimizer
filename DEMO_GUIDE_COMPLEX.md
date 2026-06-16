# AutoQA Prompt Optimizer — Complex Demo Guide (Healthcare Insurance)

A full optimization run on a healthcare insurance contact centre dataset — 20 member service calls, 7 evaluation parameters, 2–4 iterations to convergence. This demo is designed to show the system under pressure: rules with partial compliance patterns, conditional scope encoded as NA rows, and subjective criteria that admit multiple interpretations all run simultaneously. Healthcare is the right domain for this because the compliance stakes are concrete — HIPAA-compliant identity verification, appeal rights with statutory deadlines, and clinical escalation protocols mean that description vagueness maps directly to auditable compliance gaps, not just lower accuracy scores.

---

## What This Demo Shows (vs the Retail Demo)

| Dimension | Retail demo | This demo |
|---|---|---|
| Conversations | 15 | 20 |
| Parameters | 3 static | 7 (4 static + 3 dynamic) |
| Dynamic parameters | 0 | 3 |
| Expected iterations to converge | 1–2 | 2–4 per rule |
| Domain complexity | Simple retail scripts | Healthcare compliance, clinical escalation, formulary |
| Rules requiring multiple iterations | 0 | 4 (Identity Verification, Drug Coverage, Next Steps, Frustration Acknowledgment) |

What makes this dataset hard:
- **Partial compliance** — agents who asked for a member ID but not a date of birth look compliant under a vague identity verification description; the optimizer must narrow the criterion to catch the missing field
- **Conditional scope** — three parameters only apply when a specific scenario occurs (a claim denial, an urgent medical situation, or a prescription question); NA rows encode that scoping and are excluded from accuracy math entirely
- **Subjective criteria** — "acknowledged feelings" and "offered clinical support" admit multiple interpretations; the optimizer must operationalize them into observable, checkable behaviors
- **Compound failure modes** — `rule_answer_6` (next steps) fails in three distinct ways — no timeline, no reference number, or deferred to email — and the description must address all three before the rule can reach 90% accuracy

---

## Setup

```bash
# Terminal 1 — Backend
cd autoqa-prompt-optimizer/backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd autoqa-prompt-optimizer/frontend
npx ng serve --proxy-config proxy.conf.json
```

Open `http://localhost:4200`.

**Demo file:** `autoqa-prompt-optimizer/complex_demo.csv`

---

## Step 1 — Upload the CSV

**What to say:**
> "We're working with a healthcare insurance contact centre dataset — 20 member service calls covering denied claims, urgent medical situations, pharmacy benefits, and member frustration. The evaluation criteria touch real compliance obligations — HIPAA-compliant identity verification, appeal rights disclosure, clinical escalation protocols."

**Action:** Upload `complex_demo.csv`. Leave defaults (Max iterations: 5, Accuracy target: 90%).

**What appears:** 7 parameters detected across 20 conversations. Three parameters show NA values — those are the dynamic metrics where the scenario wasn't applicable in every call.

**Talking point:** The three parameters with NA values are conditional — "Denied Claim — Appeal Rights" only scores on calls where a claim was actually denied. The 11 calls where no denial occurred are automatically excluded from that parameter's accuracy math. This is how you avoid penalising agents for not reciting appeal rights on a call that never involved a denial.

---

## Step 2 — Enter Rule Descriptions and Set Types

For each parameter, the UI lets you enter a description and choose **Static** or **Dynamic**.

- **Static** = always evaluated on every call
- **Dynamic** = you provide both a trigger description (what makes this call in-scope) and an answer description (what the agent should do when in scope). The NA values in your CSV encode which calls had the trigger fire.

Enter exactly these descriptions:

| Parameter | Type | Description(s) to enter |
|---|---|---|
| `Identity Verification` | **Static** | *Answer:* At the start of the call, the agent confirmed the caller's identity before accessing or discussing any account details. The agent should ask for identifying information to verify the member is who they claim to be. |
| `Denied Claim — Appeal Rights` | **Dynamic** | *Trigger:* The call involves a claim that HealthGuard has denied or not approved for coverage. · *Answer:* When a claim has been denied, the agent should make the member aware of their options to challenge the decision, including any formal appeal or review process available to them. |
| `Urgent Medical — Clinical Support` | **Dynamic** | *Trigger:* The member described a health situation that requires prompt medical attention. · *Answer:* When a member describes an urgent or concerning medical situation, the agent should offer access to medical guidance or clinical support resources. |
| `Rx Benefit — Formulary Confirmation` | **Dynamic** | *Trigger:* The member is asking about their prescription drug benefit or the coverage and cost of a specific medication. · *Answer:* The agent should explain how the member's drug benefit applies to their medication, including whether it is covered and what the member can expect to pay. |
| `Member Frustration — Acknowledgment` | **Dynamic** | *Trigger:* The member showed signs of frustration, upset, or dissatisfaction during the call. · *Answer:* When a member is visibly upset or frustrated, the agent should acknowledge the member's experience before moving on to resolve the issue. |
| `Next Steps Communicated` | **Static** | *Answer:* Before ending the call, the agent should ensure the member understands what will happen next — including any follow-up actions HealthGuard will take and when the member can expect a resolution. |
| `Proper Call Closure` | **Static** | *Answer:* The agent brought the call to a professional close, ensuring the member had everything they needed before ending the interaction. |

**Talking point:** These descriptions read like a real QA rubric — they communicate the intent clearly to a human reviewer and cover the right topics. But they leave too much room for interpretation when used as LLM evaluation criteria. "Confirmed the caller's identity" doesn't specify which fields. "Options to challenge the decision" doesn't distinguish a formal appeal from an internal escalation. "Clinical support resources" doesn't specify whether 911 counts. That gap between human-readable and machine-executable is exactly what the optimizer closes.

---

## Step 3 — Clarification Questions

The system will ask targeted questions for each ambiguous rule. Answer exactly as shown below.

**What to say:**
> "Before evaluating a single conversation, the system runs an ambiguity check. For a healthcare compliance context, these questions are doing real work — the difference between 'asked for any account info' and 'asked for member ID AND date of birth' is the difference between a HIPAA-compliant verification and a security gap."

---

### `rule_answer_1` — "The agent verified the member's identity"

**Why it's ambiguous:** Some agents ask for a member ID, others ask for name + phone, others ask for both member ID and date of birth. The description doesn't specify which combination constitutes successful verification.

| Question (paraphrased) | Answer to give |
|---|---|
| What information must the agent collect to count as verified? | The agent must collect both the member ID and the date of birth — name, email, or phone number alone are not sufficient |
| Does the order matter, or just that both are collected at some point in the call? | Both must be collected — order doesn't matter, but both are required before any account information is shared |

**What this unlocks:** The optimizer will now correctly flag calls where agents asked only for email (conv_005), only a name (conv_003, conv_008), only a phone number (conv_019), or only a member ID without DOB (conv_010, conv_013, conv_017). Without this clarification, those all look like verification attempts and get credited as Yes.

---

### `rule_trigger_2` — "The member was calling about a denied claim"

**Why it's ambiguous:** Multiple call types involve claim disputes, billing confusion, or coverage denials. An EOB copay question (conv_017) or a prior auth pending review could be misread as a denied claim.

| Question (paraphrased) | Answer to give |
|---|---|
| What distinguishes a denied claim from a general billing or coverage question? | The member must explicitly state or acknowledge that a specific claim has been denied — a pending claim, a billing question about a copay, or a coverage eligibility question does not qualify |
| Does a prior authorisation denial count as a denied claim? | No — only post-service claim denials qualify; prior auth denials are a separate process |

**What this unlocks:** Prevents the trigger from firing on conv_017 (copay confusion) and conv_006 (drug cost shock, no claim denial).

---

### `rule_answer_2` — "The agent explained the appeals process"

**Why it's ambiguous:** Agents may acknowledge a denial and offer workarounds (escalation, resubmission, exception requests) without actually explaining that the member has formal appeal rights with a deadline.

| Question (paraphrased) | Answer to give |
|---|---|
| Is it sufficient for the agent to offer an escalation or internal review, or must they specifically mention the member's right to appeal? | The agent must explicitly inform the member they have the right to file a formal appeal — offering an internal escalation or correction does not satisfy this requirement |
| Must the agent mention the appeal deadline (180 days), or just the existence of the process? | The agent must mention the appeal right and the timeframe — stating the right without a deadline is not sufficient |

**What this unlocks:** conv_007 (offered exception review, no appeal rights), conv_012 (offered escalation, no appeal mentioned), conv_016 (offered correction, no appeal rights), conv_019 (told member to negotiate with provider, no appeal) all correctly score as No. conv_003 (escalated only, no appeal) also correctly scores No.

---

### `rule_trigger_3` — "The member had an urgent medical concern"

**Why it's ambiguous:** Many healthcare calls reference health conditions. The distinction between a clinical urgency (needs guidance now) and a routine medical question is critical — over-triggering means agents get scored on clinical escalation in calls that didn't require it.

| Question (paraphrased) | Answer to give |
|---|---|
| What qualifies as an urgent medical concern — any mention of symptoms, or something specific? | The member must describe active or ongoing symptoms that require medical attention soon — for example, current pain, inability to function, or an instruction from a physician to act immediately |
| Does asking about ER coverage for a past visit count as urgent? | No — the concern must be current and active, not a retrospective question about a past event |

**What this unlocks:** conv_014 (ongoing chest pain, member scared) correctly triggers. conv_007 (past claim for ultrasound) does not trigger. conv_001 (mentioned pain historically during a claim call) does not trigger.

---

### `rule_answer_3` — "The agent offered clinical support"

**Why it's ambiguous:** Agents respond to medical urgency in multiple ways — some refer to the ER or 911, some recommend a GP appointment, some offer to connect to HealthGuard's own nurse line or care coordinator. These are very different from a compliance standpoint.

| Question (paraphrased) | Answer to give |
|---|---|
| What form of clinical support counts — telling the member to go to the ER, or something specific to HealthGuard? | The agent must offer to connect the member with HealthGuard's nurse line or care coordinator — telling the member to call 911 or go to the ER counts as safety signposting but does not satisfy this requirement |
| Does suggesting urgent care count? | No — the agent must offer a HealthGuard clinical resource, not a third-party facility |

**What this unlocks:** conv_008 (told member to call 911 but did not offer nurse line — No) and conv_014 (recommended urgent care and PCP but no nurse line offer — No) correctly score as No. conv_004, conv_011, conv_018 (all explicitly offered nurse line or care coordinator) correctly score Yes.

---

### `rule_trigger_4` — "The call involved a prescription or medication"

**Why it's ambiguous:** Many conversations reference medications incidentally (doctor adjusted medication, prior auth for a procedure that involves drugs). The trigger should fire only when the member is specifically asking about their prescription drug benefit.

| Question (paraphrased) | Answer to give |
|---|---|
| Does any mention of a medication trigger this rule, or must the member be asking about drug coverage specifically? | The member must be actively asking about coverage, cost, or access for a specific named drug — incidental mentions of a medication as context for another issue do not qualify |
| What about a call where the agent mentions a medication when explaining a claim denial? | Only triggers if the member's primary reason for calling (or a secondary explicit question) is about a specific drug or pharmacy benefit |

**What this unlocks:** conv_017 (doctor adjusted medication, but member never asked about Rx coverage) does not trigger. conv_004 (asked about ER coverage only; oxycodone not yet prescribed) does not trigger. conv_002, conv_006, conv_008, conv_009, conv_011, conv_013, conv_015, conv_018 all correctly trigger.

---

### `rule_answer_4` — "The agent explained the member's drug coverage"

**Why it's ambiguous:** Agents may confirm that a drug is "covered" or on a "generic tier" without giving the specific formulary tier number or cost-sharing amounts. Confirming coverage in principle ≠ confirming what the member will actually pay.

| Question (paraphrased) | Answer to give |
|---|---|
| Is it enough to confirm the drug is covered, or must the agent give the specific tier and cost? | The agent must confirm both the formulary tier (e.g., Tier 1, Tier 3 specialty) and the member's specific cost-sharing amount — confirming coverage without the dollar amount or tier is not sufficient |
| What if the agent says they'll send the information by email? | Deferring to email without giving tier and cost-sharing during the call does not satisfy the requirement |

**What this unlocks:** conv_006 (said "specialty tier" but didn't give cost amount — No), conv_009 (said non-formulary but couldn't give tier/copay — No), conv_013 (said "generic tier rate" without dollar figure — No), conv_018 (said covered but deferred pricing to email — No) all correctly score No.

---

### `rule_trigger_5` — "The member expressed dissatisfaction"

**Why it's ambiguous:** Members on a healthcare call are often worried or concerned — concern and fear are not the same as dissatisfaction. Over-triggering penalises agents for not performing a de-escalation protocol in calls that were never escalated.

| Question (paraphrased) | Answer to give |
|---|---|
| What distinguishes dissatisfaction from general concern or worry? | The member must use explicit language indicating dissatisfaction with HealthGuard's service, process, or outcome — words like "frustrated," "furious," "outrageous," "unacceptable," "completely fed up," or similar direct expressions of negative emotion directed at the experience |
| Does a member saying they are scared about their health count? | No — fear or worry about a health condition is not dissatisfaction with the service; the emotion must be directed at the interaction or process |

**What this unlocks:** conv_004 (scared parent, not dissatisfied) does not trigger. conv_011 (urgency but matter-of-fact, no frustration language) does not trigger. conv_001, conv_003, conv_006, conv_008, conv_009, conv_012, conv_014, conv_016, conv_018 all correctly trigger because they use explicit frustration language.

---

### `rule_answer_5` — "The agent acknowledged the member's feelings"

**Why it's ambiguous:** Many agents say "I understand" reflexively as a filler before diving into account lookup. A genuine acknowledgment names the emotion and validates the experience before moving to resolution.

| Question (paraphrased) | Answer to give |
|---|---|
| Does saying "I understand" count as acknowledging the member's feelings? | Not on its own — the agent must specifically name or reflect back what the member is experiencing (e.g., "I can hear how frustrated you are," "that's genuinely upsetting news") before attempting to resolve the issue |
| Must the acknowledgment happen before the agent begins investigating the problem? | Yes — an acknowledgment that comes after the agent has already pulled up the account and started explaining the situation does not satisfy the requirement |

**What this unlocks:** conv_006 (said "I understand" mid-investigation — No) and conv_012 (said "I understand" and immediately moved to account lookup — No) correctly score No. conv_001, conv_003, conv_008, conv_009, conv_014, conv_016, conv_018 all acknowledged explicitly before proceeding.

---

### `rule_answer_6` — "The agent told the member what to expect next"

**Why it's ambiguous:** Agents often give vague forward-looking statements ("we'll look into it," "you should hear back"). Genuine next-step communication requires a specific timeline and a reference number the member can use to follow up.

| Question (paraphrased) | Answer to give |
|---|---|
| Does telling the member "we'll process this" or "you'll hear back" count as explaining next steps? | No — the agent must give a specific timeframe (e.g., "within 5 business days," "within 72 hours") AND a case or reference number the member can cite on a future call |
| What if the agent gives a timeline but no reference number? | Both are required — a timeline without a reference number is not sufficient |

**What this unlocks:** conv_004 (offered transfer but no case number — No), conv_006 (promised email info but no case number, no timeline — No), conv_009 (gave timeline but no reference number — No), conv_013 (directed to website, no case number — No), conv_015 (no action taken, no reference — No), conv_019 (told member to call facility, no HealthGuard action, no case number — No) all correctly score No.

---

### `rule_answer_7` — "The agent closed the call properly"

**Why it's ambiguous:** A polite farewell is not the same as a proper closure. Agents who say "goodbye" warmly or thank the member without explicitly checking for remaining needs are closing the call, not closing it properly.

| Question (paraphrased) | Answer to give |
|---|---|
| What does "properly" mean — is a polite goodbye sufficient? | No — the agent must explicitly ask whether there is anything else they can help the member with before ending the call |
| Does transferring a call count as closing it properly? | No — if the agent transfers without asking "is there anything else?", the closure requirement is not met |

**What this unlocks:** conv_002 (transferred abruptly — No), conv_005 ("Good luck with the appeal" — No), conv_011 (transferred without asking — No), conv_013 ("Goodbye" — No), conv_017 ("Goodbye!" — No) all correctly score No.

---

## Step 4 — Watch the Optimization Run

### Expected baseline accuracy (before optimization)

| Rule | Expected baseline | Why it underperforms |
|---|---|---|
| `rule_answer_1` | ~62% | Agents who asked one factor (email, name, phone, member ID only) look compliant with vague description |
| `rule_trigger_2` | ~73% | Billing confusion calls can superficially resemble denied claim calls |
| `rule_answer_2` | ~71% | Escalation and exception offers look like appeals process explanation |
| `rule_trigger_3` | ~67% | Medical worry language in non-urgent calls (past ER visit, general fear) over-triggers |
| `rule_answer_3` | ~62% | ER/911 referrals credited as clinical support; urgent care also credited |
| `rule_trigger_4` | ~70% | Incidental medication mentions trigger the rule |
| `rule_answer_4` | ~58% | "It's covered" or "generic tier" credited as full explanation |
| `rule_trigger_5` | ~66% | Concern, worry, and mild complaints trigger alongside explicit frustration |
| `rule_answer_5` | ~73% | "I understand" as a filler gets credited as acknowledgment |
| `rule_answer_6` | ~58% | Vague "we'll look into it" and "you'll hear back" credited as next steps |
| `rule_answer_7` | ~67% | Polite farewells without explicit "anything else?" get credited |

**What to say during baseline (iteration 0):**
> "The system is now running all 20 conversations through each rule using the vague descriptions you just saw. This is the ceiling for untuned human language — roughly 60–70% accuracy. Better than random, but nowhere near the compliance standard you'd want for regulatory reporting."

### During RCA iterations (1–4)

**What to say:**
> "For each rule below target, the system is reading the actual transcripts from misclassified conversations. For rule_answer_1, it will see that in three consecutive failures, the agent asked for an email address — not a member ID — and correctly identify that the description needs to specify which fields count as verification. This is root cause analysis from transcript evidence, not heuristics."

**Rules likely to require 3+ iterations:**
- `rule_answer_1` — two distinct failure patterns (single-factor vs wrong-factor verification)
- `rule_answer_4` — partial compliance pattern (agents who confirm coverage but not cost-sharing)
- `rule_answer_6` — three distinct failure patterns (no timeline, no reference number, deferred to email)
- `rule_trigger_5` — over-triggering on medical worry language needs surgical boundary definition

**Rules likely to converge in 1–2 iterations:**
- `rule_answer_2` — once the distinction between escalation and formal appeal is established, the pattern is consistent
- `rule_answer_7` — single failure pattern (polite farewell without explicit "anything else?")
- `rule_trigger_2` — once billing confusion is excluded, clear signal

---

## Step 5 — View the Report

**What to say:**
> "The final report shows the full picture — which rules hit 90%, which needed the most iterations, and which failure patterns drove the rewrites. For a compliance team, this is the audit trail — every change is documented with the transcript evidence that triggered it. And everything is ready to export."

**Things to point out:**

1. **Rules that couldn't converge** — `rule_answer_5` (acknowledging feelings before investigating) or `rule_answer_6` (specific timeline + reference number) may hit the iteration cap if the failure pattern is subtle enough to require mid-loop clarification. Point this out: the system flags it, doesn't pretend it converged.

2. **NA distribution** — show any rule with many NA rows in the table. For `rule_answer_3`, only 5 of 20 conversations qualify (those with urgent medical triggers). Point out that the accuracy math excludes the other 15 — the rule isn't irrelevant, it's precisely scoped.

3. **Before/after for `rule_answer_1`** — show the original description ("At the start of the call, the agent confirmed the caller's identity…") alongside the final structured prompt. The "What changed" box explains the optimizer's reasoning — in this case, adding the specific fields (member ID AND date of birth) that the clarification answers defined.

4. **Convergence trajectory for `rule_answer_4`** — show iteration-by-iteration accuracy climbing from ~58% → 70% → 85% → 90%+. This is the story: three rounds of reading transcripts and rewriting until the criterion is machine-executable.

**Export options (demonstrate each):**
- **Export Evaluations CSV** — wide-format: one row per conversation, with ground truth, prediction, and correct columns for each of the 11 rules. Useful for compliance audits or feeding into a reporting dashboard.
- **Export Prompts CSV** — the 11 optimised rule descriptions (parameter name, trigger/answer type, description text) ready to paste directly into the evaluation system.
- **Export Report PDF** — the full infographic: overall accuracy before/after, per-parameter table with start/end accuracy, confusion matrices, iteration trend charts, "What changed" summaries, and the original vs final description for every rule.

---

## Key Talking Points

**"How does it handle healthcare compliance language specifically?"**
> The system doesn't have healthcare domain knowledge built in. It reads the transcripts the same way a senior QA analyst would — looking for what was actually said and matching it against the refined criteria. The domain knowledge comes from your answers during the clarification phase. You told it "member ID and date of birth" — it now enforces that exactly.

**"What happens when a rule is genuinely subjective?"**
> Rules like "acknowledged the member's feelings" have a subjective dimension. The system can operationalise them — it learned to look for explicit emotional validation before any investigation step — but the definition you gave in clarification is what makes it evaluable. If the clarification had been more vague, it would have flagged the rule as non-evaluable. The quality of the output scales with the quality of the input.

**"Could this run on live call transcripts?"**
> The input format is a CSV of transcripts — live transcripts from your contact centre system would just need to be formatted the same way. The optimization happens offline against your labelled ground truth, and the output descriptions become part of your live evaluation prompts. You'd re-run the optimizer periodically as agent behaviour changes.

**"What's the regression guard doing?"**
> If iteration 3 produces a description that performs worse than iteration 2 on the same conversations, the system automatically reverts to the iteration 2 version and tries a different rewrite strategy. You'll see this in the accuracy trajectory — sometimes accuracy dips at one iteration before recovering. That's the guard working.

---

## Ground Truth Reference (for presenter awareness)

| Conv | Scenario | A1 verify | T2 denial | A2 appeal | T3 urgent | A3 nurse | T4 Rx | A4 formulary | T5 frustrated | A5 ack | A6 next steps | A7 close |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| conv_001 | MRI denied, frustrated | **Yes** (ID+DOB) | **Yes** | **Yes** | No | NA | No | NA | **Yes** | **Yes** | **Yes** (CAS-2841) | **Yes** |
| conv_002 | Lantus Rx cost | **Yes** (ID+DOB) | No | NA | No | NA | **Yes** | **Yes** (T3, $65/$45) | No | NA | **Yes** (CAS-7712) | **No** (transferred) |
| conv_003 | Sleep study denied x3 | **No** (name only) | **Yes** | **No** (escalation only) | No | NA | No | NA | **Yes** | **Yes** | **Yes** (CAS-9021) | **Yes** |
| conv_004 | Child fever 103 | **Yes** (ID+DOB) | No | NA | **Yes** | **Yes** (nurse line) | No | NA | No | NA | **No** (no case#) | **Yes** |
| conv_005 | PT denied sessions 7-10 | **No** (email only) | **Yes** | **Yes** (180 days) | No | NA | No | NA | No | NA | **Yes** (form+timeline) | **No** (no "anything else") |
| conv_006 | Humira $800 shock | **Yes** (ID+DOB) | No | NA | No | NA | **Yes** | **No** (no cost given) | **Yes** | **No** ("I understand" mid-flow) | **No** (no case#) | **Yes** |
| conv_007 | Ultrasound OON | **Yes** (ID+DOB) | **Yes** | **No** (exception, no appeal) | No | NA | No | NA | No | NA | **Yes** (CAS-3317) | **Yes** |
| conv_008 | Chest tightness + Lisinopril | **No** (name only) | No | NA | **Yes** | **No** (911 only) | **Yes** | **Yes** (T1, $10/$25) | **Yes** | **Yes** | **Yes** (CAS-5502) | **Yes** |
| conv_009 | Enbrel denied + non-formulary | **Yes** (ID+DOB) | **Yes** | **Yes** (180 days + step therapy) | No | NA | **Yes** | **No** (deferred to email) | **Yes** | **Yes** | **No** (no case#) | **Yes** |
| conv_010 | Mental health coverage | **No** (ID only, no DOB) | No | NA | No | NA | No | NA | No | NA | **Yes** (CAS-1188) | **Yes** |
| conv_011 | Gallbladder surgery urgent + oxycodone | **Yes** (ID+DOB) | No | NA | **Yes** | **Yes** (care coordinator) | **Yes** | **Yes** (T2, $35) | No | NA | **Yes** (CAS-4461) | **No** (transferred) |
| conv_012 | NICU $45K denied | **Yes** (ID+DOB) | **Yes** | **No** (escalation only) | No | NA | No | NA | **Yes** | **No** ("I understand" pre-lookup) | **Yes** (CAS-8830) | **Yes** |
| conv_013 | Metformin coverage | **No** (ID only, no DOB) | No | NA | No | NA | **Yes** | **No** ("generic tier rate", no $) | No | NA | **No** (website only) | **No** (no "anything else") |
| conv_014 | Ongoing chest pain post-ER | **Yes** (ID+DOB) | No | NA | **Yes** | **No** (urgent care, no nurse line) | No | NA | **Yes** | **Yes** | **Yes** (CAS-6619) | **Yes** |
| conv_015 | Dupixent + denied derm claim | **No** (no verification) | **Yes** | **Yes** (180 days) | No | NA | **Yes** | **Yes** (T4, 20%, $500 max) | No | NA | **No** (no case#) | **Yes** |
| conv_016 | Knee surgery denied (laterality) | **Yes** (ID+DOB) | **Yes** | **No** (correction only) | No | NA | No | NA | **Yes** | **Yes** | **Yes** (CAS-7753) | **Yes** |
| conv_017 | EOB copay confusion | **No** (ID only, no DOB) | No | NA | No | NA | No | NA | No | NA | **Yes** (itemized email) | **No** ("Goodbye!") |
| conv_018 | Abdominal pain + Humira | **Yes** (ID+DOB) | No | NA | **Yes** | **Yes** (nurse line) | **Yes** | **No** (deferred to email) | **Yes** | **Yes** | **Yes** (CAS-3398) | **Yes** |
| conv_019 | Sleep study OON denied | **No** (name+phone) | **Yes** | **No** (told to negotiate) | No | NA | No | NA | No | NA | **No** (no action taken) | **Yes** |
| conv_020 | Adding mother as dependent | **Yes** (ID+DOB) | No | NA | No | NA | No | NA | No | NA | **Yes** (CAS-0091) | **Yes** |

---

## Expected Final Descriptions (post-optimization)

These are what the optimizer should converge to after 2–4 iterations. Use for validation.

**`rule_answer_1` — Identity Verification**
> **PASS:** The agent explicitly collected the member's member ID number AND date of birth before providing any account information. Both must be collected — name, email address, or phone number do not substitute for either required field. **FAIL:** The agent accessed the account after collecting only one identifier (member ID alone, name alone, email, or phone), or did not collect any identifying information.

**`rule_answer_2` — Appeal Rights Disclosure**
> **PASS:** The agent explicitly informed the member that they have the right to file a formal appeal against the denial, AND stated the appeal submission deadline (180 days from the denial date). **FAIL:** The agent offered only an internal escalation, a correction request, a claim resubmission, or a retroactive exception review without mentioning the member's formal appeal rights and deadline.

**`rule_answer_3` — Clinical Support Offer**
> **PASS:** The agent explicitly offered to connect the member with HealthGuard's nurse line or a care coordinator during the call — and either made the transfer or provided a direct transfer option. **FAIL:** The agent directed the member to call 911, go to the ER, visit urgent care, or follow up with their own physician without also offering access to a HealthGuard clinical resource.

**`rule_answer_4` — Drug Coverage Explanation**
> **PASS:** The agent stated the specific formulary tier (e.g., Tier 1 generic, Tier 3 brand, Tier 4 specialty) for the member's named drug AND provided the member's specific cost-sharing amount (copay in dollars or coinsurance percentage) during the call. **FAIL:** The agent confirmed the drug is covered without stating the tier, stated the tier without stating the cost-sharing amount, or deferred cost-sharing information to a follow-up email without providing it during the call.

**`rule_answer_5` — Frustration Acknowledgment**
> **PASS:** Before pulling up the account, beginning any investigation, or providing any information, the agent explicitly named or reflected the member's emotional state — for example, "I can hear how frustrated you are," "that's a genuinely upsetting situation," or "I completely understand why you're upset about this." **FAIL:** The agent said only "I understand" as a filler phrase before immediately proceeding to account lookup or explanation, or acknowledged the emotion only after already beginning to address the issue.

**`rule_answer_6` — Next Steps Communication**
> **PASS:** Before ending the call, the agent provided BOTH a specific timeline for the next action (e.g., "within 5 business days," "within 72 hours," "by email today") AND a case or reference number the member can cite on any future contact. **FAIL:** The agent gave only a vague forward-looking statement ("we'll look into it," "you'll hear back"), gave a timeline without a reference number, gave a reference number without a timeline, or directed the member to a third party without providing any HealthGuard action timeline or reference.

**`rule_answer_7` — Call Closure**
> **PASS:** The agent explicitly asked whether there was anything else they could help the member with before ending or transferring the call — using language such as "Is there anything else I can help you with?" or "Before I transfer you, is there anything else?" **FAIL:** The agent ended the call with a polite farewell, a thank-you, or a direct transfer without first checking whether the member had any remaining needs.
