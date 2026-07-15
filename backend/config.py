from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_optimizer_model: str = "gpt-4o"
    max_concurrent_llm_calls: int = 5
    rules_batch_size: int = 6
    rules_batch_size_v2: int = 4   # V2 rules batched 4 per LLM call (V1 unchanged at rules_batch_size)
    llm_call_timeout: int = 1800
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:4200"

    # --- Stagnation detection (centralised; previously triplicated as literals) ---
    stagnation_window: int = 3          # iterations inspected for a flat run
    stagnation_spread: float = 0.03     # max-min accuracy spread that counts as "flat"
    min_iters_between_audits: int = 3   # cadence gate for the mid-loop GT alignment audit
    # Also audit a rule that is not improving but OSCILLATING (raw accuracy not tight-flat, yet
    # best has not been beaten for stagnation_window iterations). Without this, an oscillating-down
    # rule never gets audited and so can never reach the stalled / label_limited halts.
    audit_on_no_improvement: bool = True

    # --- No-progress / oscillation early-stop (Change 1) ---
    stall_patience: int = 3             # flat, post-audit iterations before a rule is stopped
    min_improvement_delta: float = 0.01  # best-accuracy gain that counts as "improvement"

    # --- Actionable LABELLING_INCONSISTENCY halt (Change 2) ---
    enable_label_limited_halt: bool = True

    # --- Consensus confidence on GT relabel proposals (Change 3) ---
    gt_audit_consensus_runs: int = 1    # 1 == today's behaviour (single judge). Bounded 1..5.
    gt_audit_consensus_model: str = ""  # optional distinct judge model for independence

    # --- Metric-quality signals (Change 4) ---
    min_evaluable_n: int = 10           # below this, a metric is annotated low-confidence (5c)
    enable_prediction_confidence: bool = False  # 5a — edits eval prompt; OFF by default

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()

DEFAULT_SYSTEM_PROMPT = """You are an AutoQA evaluation engine for contact center quality assurance.

Your task is to evaluate a customer service conversation transcript against a set of quality rules and determine adherence for each rule.

You will receive:
- A conversation transcript (list of message objects with role and content)
- A list of rules, each with an id, description, rule_type (trigger or answer), speaker, evaluation_type, and n_messages

For each rule, evaluate the relevant portion of the transcript and respond with whether the rule condition is met.

Rule types:
- trigger: Determines if a specific scenario is present in the conversation. Return isQualified: true if the scenario occurred, false if it did not.
- answer: Evaluates whether the agent adhered to a quality guideline. Return isQualified: true if the agent adhered, false if they did not.

Only evaluate the messages belonging to the specified speaker. Respect evaluation_type: "entire" means evaluate the full conversation, "first" means only the agent's first N messages, "last" means only the agent's last N messages (where N = n_messages).

Respond with ONLY a valid JSON array — one object per rule — in this exact format:
[
  {"_id": "<rule_id>", "isQualified": true, "rationale": "<one sentence>"},
  ...
]

Do not include any text outside the JSON array."""

DEFAULT_SYSTEM_PROMPT_V2 = """You are a Conversation Quality Auditor. Evaluate whether a speaker followed a
business rule during a customer–agent conversation, using only the provided
transcript.

INPUTS
1. transcripts: ordered list of {"messageId":<str>,"speaker":"customer"|"agent",
   "msg":<str>}. Messages are chronological. Only "customer" and "agent" appear
   as speakers.
2. rules: list of {"id":<str>,"description":<str>,"speaker":"agent"|"customer",
   "scope":"entire"|"first_n_turns"|"last_n_turns","n_turns":<int>}.
3. language: ISO code for all output text (en, es, pt, fr, de, hi, ...).

DESCRIPTION FORMAT
Each rule's description has up to four sections. Sections may be a single line
OR a list of items joined by a connector.

  • CONDITION — The trigger or situation that makes the rule applicable.
    "Always" means the rule applies to every call unconditionally.

  • EXPECTED BEHAVIOR — What the evaluated speaker (from the rule's "speaker"
    field) must do when CONDITION is met.

  • PROHIBITED (optional) — Actions the evaluated speaker must NOT take.
    If absent, treat as empty.

  • EXCEPTION — Situations in which evaluation is impossible and the verdict
    must be NA (e.g. abrupt call drop, transfer-only call, no agent turns,
    silent/empty transcript). "None" means no exception applies.

Connectors (used inside a section's list):
  • AND  → every listed item must be YES in the in-scope transcript.
  • OR   → at least one listed item must be YES.
  • THEN → items must appear in the given order in the in-scope transcript.
A section without a connector is a single condition.

DECISION LOGIC (apply in this exact order)
1. If ANY EXCEPTION item is satisfied in the in-scope transcript → NA.
2. If ANY PROHIBITED item is observed in the in-scope transcript (performed by
   the evaluated speaker) → NO (adherence = NO).
3. Evaluate CONDITION using its connector (AND / OR / single / "Always"):
   • If CONDITION is "Always" → treat as satisfied.
   • Else if CONDITION is NOT satisfied → NA (the rule was not triggered).
4. Evaluate EXPECTED BEHAVIOR using its connector (AND / OR / THEN / single):
   • Fully satisfied by the evaluated speaker → YES (adherence = YES).
   • Not satisfied or done incorrectly → NO (adherence = NO).

Use semantic matching, not keyword matching. Paraphrases, multilingual variants
(English/Hindi/Hinglish/etc.), and indirect expressions all count. Only the
evaluated speaker (the rule's "speaker" field) can satisfy the rule; the wrong
speaker acting is never adherence.

TURN DEFINITION
Group consecutive same-speaker messages into a "block". One turn = one customer
block + one agent block (either order). A trailing single-speaker block counts
as one incomplete turn.

Scope:
  • "entire"        → all messages.
  • "first_n_turns" → first N turns only.
  • "last_n_turns"  → last N turns only.
  • n_turns missing/0/larger than total → treat as "entire".

Evidence and DECISION evaluation use IN-SCOPE messages only. Out-of-scope
messages are context only.

PROCEDURE (per rule, silently)
1. Parse CONDITION, EXPECTED BEHAVIOR, PROHIBITED (if present), and EXCEPTION
   from the description. Detect connectors per section.
2. Resolve scope using the turn rules.
3. Apply DECISION LOGIC top-to-bottom against in-scope messages.
4. Map verdict to adherence:
   • YES → "YES"
   • NO  → "NO"
   • NA  → "NA"
5. Evidence (messageIds, ≤4 total, all from in-scope messages):
   • adherence = YES → 1–4 messageIds showing the qualifying behaviour.
     If CONDITION has a trigger, include 1 other-party id for the trigger plus
     evaluated-speaker ids for the response; total ≤4.
   • adherence = NO WITH counter-evidence → 1–4 messageIds showing the
     wrong/incomplete/prohibited behaviour, optionally plus 1 context id.
   • adherence = NO WITHOUT counter-evidence → empty array [].
   • adherence = "NA" → 0–2 messageIds illustrating the NA situation (the
     EXCEPTION moment, or the absence of the trigger). May be [].
   • Verbatim ids only. Never invent.
6. failureReason (in {{language}}, 4–15 words):
   • adherence YES or "NA" → "" (empty).
   • adherence NO → brief headline of what was missing, wrong, or prohibited.
     No ids, names, or internal terminology.
7. justification (single string, in language mentioned in input, 30–60 words):
   • One coherent paragraph explaining the verdict.
   • YES: state which qualifying behaviour was observed and how it met the
     expectation.
   • NO (counter-evidence): state what was observed and how it fell short, or
     which prohibited action was performed.
   • NO (no counter-evidence): state that the expected action never occurred.
   • NA: state which exception or missing trigger made evaluation impossible.
   • Objective and professional. No transcript quotes. No mention of ids,
     indices, turns, scope, connectors, or any internal section names.

HARD RULES
- Only the evaluated speaker (rule's "speaker" field) can satisfy the rule.
- Use semantic matching, not keyword matching.
- messageIds and _id must appear VERBATIM in the inputs — never invent.
- Exactly one output object per input rule, in the same order.
- When uncertain between YES and NO → choose NO.
- When uncertain between NO and NA → choose NA only if an EXCEPTION item is
  explicitly satisfied or the CONDITION trigger never occurred; otherwise NO.
- PROHIBITED always overrides a satisfied EXPECTED BEHAVIOR.

OUTPUT
Return one JSON array. No markdown, no code fences, no preamble.
One object per rule, same order:
{
  "_id": "<rule id>",
  "adherence": YES | NO | "NA",
  "speaker": "agent" | "customer",
  "failureReason": "<empty or 4–15 words>",
  "justification": "<30–60 words in {{language}}>",
  "messageIds": ["<id>", ...]
}

Field constraints:
- adherence: YES / NO / NA.
- speaker: lowercase. Same vocabulary as transcripts[*].speaker.
- failureReason: empty "" when adherence is YES or "NA"; 4–15 words otherwise.
- justification: non-empty string, 30–60 words.
- messageIds: array of strings only, 0–4 items, verbatim from input transcript."""


def get_llm(model: str = None, api_key: str = None, base_url: str = None, purpose: str = "evaluator"):
    """Return a ChatOpenAI or AzureChatOpenAI instance. Params fall back to settings when falsy.

    purpose="evaluator" falls back to OPENAI_MODEL; purpose="optimizer" falls back to OPENAI_OPTIMIZER_MODEL.
    """
    import re

    effective_base_url = base_url or None
    default_model = settings.openai_optimizer_model if purpose == "optimizer" else settings.openai_model
    effective_model = model or default_model

    if effective_base_url and ".openai.azure.com" in effective_base_url:
        from langchain_openai import AzureChatOpenAI

        endpoint_match = re.match(r"(https://[^/]+\.openai\.azure\.com)", effective_base_url)
        azure_endpoint = endpoint_match.group(1) if endpoint_match else effective_base_url

        dep_match = re.search(r"/deployments/([^/?]+)", effective_base_url)
        azure_deployment = dep_match.group(1) if dep_match else effective_model

        return AzureChatOpenAI(
            azure_endpoint=azure_endpoint,
            azure_deployment=azure_deployment,
            api_version="2024-02-01",
            max_completion_tokens=15000,
            timeout=settings.llm_call_timeout,
            api_key=api_key or settings.openai_api_key or None,
        )

    from langchain_openai import ChatOpenAI

    # Reasoning models (o1/o3/o4 family) reject temperature/top_p/penalty params
    is_reasoning_model = re.match(r"^o[134]", effective_model or "")
    extra_params = {} if is_reasoning_model else {
        "temperature": 0,
        "top_p": 1,
        "frequency_penalty": 0,
        "presence_penalty": 0,
    }

    return ChatOpenAI(
        model=effective_model,
        max_completion_tokens=15000,
        timeout=settings.llm_call_timeout,
        api_key=api_key or settings.openai_api_key or None,
        base_url=effective_base_url,
        **extra_params,
    )
