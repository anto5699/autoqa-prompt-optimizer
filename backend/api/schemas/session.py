from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ParameterInfo(BaseModel):
    parameter_name: str
    has_na: bool


class MetricConfig(BaseModel):
    type: Literal["static", "dynamic"]
    answer_description: str
    trigger_description: Optional[str] = None


class CreateSessionResponse(BaseModel):
    session_id: str
    parameters_detected: List[ParameterInfo]
    excluded_parameters: List[str]
    conversation_count: int


class ParameterSummary(BaseModel):
    accuracy: float
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    current_phase: str
    current_iteration: int
    parameters: List[ParameterInfo] = Field(default_factory=list)
    clarifying_questions: List[Dict[str, Any]] = Field(default_factory=list)
    parameter_summary: Dict[str, ParameterSummary] = Field(default_factory=dict)
    progress_log: List[str] = Field(default_factory=list)


class SubmitAnswersRequest(BaseModel):
    answers: Dict[str, str]


class SubmitAnswersResponse(BaseModel):
    status: str


class SubmitDescriptionsRequest(BaseModel):
    descriptions: Dict[str, MetricConfig]


class SubmitDescriptionsResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
