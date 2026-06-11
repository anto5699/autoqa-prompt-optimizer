from __future__ import annotations

import logging

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from openai import AsyncOpenAI

from api.schemas.config import ModelConfigValidateRequest, ModelConfigValidateResponse
from config import get_llm, settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config")


async def _fetch_models(api_key: str | None, base_url: str | None) -> list[str] | None:
    try:
        client = AsyncOpenAI(
            api_key=api_key or settings.openai_api_key or None,
            base_url=base_url or None,
        )
        result = await client.models.list()
        return sorted(m.id for m in result.data)
    except Exception:
        return None


@router.post("/validate", response_model=ModelConfigValidateResponse)
async def validate_model_config(body: ModelConfigValidateRequest) -> ModelConfigValidateResponse:
    try:
        llm = get_llm(
            model=body.model or None,
            api_key=body.api_key or None,
            base_url=body.base_url or None,
        )
        response = await llm.ainvoke(
            [HumanMessage(content="hi")],
            config={"max_tokens": 1},
        )
        model_used = (response.response_metadata or {}).get("model_name") or body.model or None
        models = await _fetch_models(body.api_key or None, body.base_url or None)
        return ModelConfigValidateResponse(valid=True, model_used=model_used, models=models)
    except Exception as exc:
        logger.info("model config validation failed: %s", exc)
        return ModelConfigValidateResponse(valid=False, error=str(exc))
