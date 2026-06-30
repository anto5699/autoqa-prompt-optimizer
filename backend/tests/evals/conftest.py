import pytest
from langchain_openai import ChatOpenAI
from config import settings


@pytest.fixture(scope="session")
def eval_llm() -> ChatOpenAI:
    """Shared LLM instance for all judge scoring calls."""
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
