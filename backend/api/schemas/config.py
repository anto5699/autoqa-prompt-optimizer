from __future__ import annotations

from pydantic import BaseModel


class ModelConfigValidateRequest(BaseModel):
    model: str = ""
    api_key: str = ""
    base_url: str = ""


class ModelConfigValidateResponse(BaseModel):
    valid: bool
    model_used: str | None = None
    error: str | None = None
    models: list[str] | None = None  # populated on success; None if listing fails
