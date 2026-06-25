from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_optimizer_model: str = "gpt-4o"
    max_concurrent_llm_calls: int = 5
    rules_batch_size: int = 6
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
            timeout=180,
            api_key=api_key or settings.openai_api_key or None,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=effective_model,
        temperature=0,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        max_completion_tokens=15000,
        timeout=180,
        api_key=api_key or settings.openai_api_key or None,
        base_url=effective_base_url,
    )
