from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    max_concurrent_llm_calls: int = 5
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:4200"

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


@lru_cache(maxsize=1)
def get_llm():
    """Return the shared ChatOpenAI instance. Deferred so startup never requires a key."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openai_model,
        temperature=0,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        max_completion_tokens=15000,
        timeout=180,
        api_key=settings.openai_api_key or None,
    )
