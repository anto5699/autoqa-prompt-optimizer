"""get_llm must wire settings.llm_call_timeout into both the OpenAI and Azure clients
(regression guard for the hardcoded timeout=180 bug that crashed slow RCA calls)."""

import config
from config import get_llm


def _timeout_of(llm):
    # langchain_openai exposes the constructor `timeout` as `request_timeout`.
    return getattr(llm, "request_timeout", None) or getattr(llm, "timeout", None)


def test_get_llm_uses_settings_timeout_openai(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_call_timeout", 4242)
    llm = get_llm(model="gpt-4o", api_key="test-key")
    assert _timeout_of(llm) == 4242


def test_get_llm_uses_settings_timeout_azure(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_call_timeout", 999)
    llm = get_llm(
        model="gpt-4o",
        api_key="test-key",
        base_url="https://example.openai.azure.com/deployments/mydep",
    )
    # Azure path is selected for .openai.azure.com base URLs
    assert type(llm).__name__ == "AzureChatOpenAI"
    assert _timeout_of(llm) == 999


def test_get_llm_default_timeout_is_not_hardcoded_180(monkeypatch):
    # The old bug hardcoded 180; assert the setting (default 1800) flows through instead.
    monkeypatch.setattr(config.settings, "llm_call_timeout", 1800)
    llm = get_llm(model="gpt-4o", api_key="test-key")
    assert _timeout_of(llm) == 1800
