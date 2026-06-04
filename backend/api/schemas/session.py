from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RuleInfo(BaseModel):
    rule_id: str
    rule_type: str
    speaker: str
    evaluation_type: str
    n_messages: int


class CreateSessionResponse(BaseModel):
    session_id: str
    rules_detected: List[RuleInfo]
    excluded_rules: List[str]
    conversation_count: int


class ParameterSummary(BaseModel):
    accuracy: float
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    current_phase: str
    current_iteration: int
    rules: List[RuleInfo] = Field(default_factory=list)
    clarifying_questions: List[Dict[str, Any]] = Field(default_factory=list)
    parameter_summary: Dict[str, ParameterSummary] = Field(default_factory=dict)
    progress_log: List[str] = Field(default_factory=list)


class SubmitAnswersRequest(BaseModel):
    answers: Dict[str, str]


class SubmitAnswersResponse(BaseModel):
    status: str


class SubmitDescriptionsRequest(BaseModel):
    descriptions: Dict[str, str]


class SubmitDescriptionsResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
