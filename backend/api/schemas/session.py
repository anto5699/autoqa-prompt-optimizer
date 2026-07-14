from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ParameterInfo(BaseModel):
    parameter_name: str
    has_na: bool


class MetricConfig(BaseModel):
    type: Literal["static", "dynamic"]
    version: Literal["v1", "v2"] = "v1"
    answer_description: str
    trigger_description: Optional[str] = None
    trigger_speaker: Optional[Literal["agent", "customer"]] = "customer"
    evaluation_type: Literal["entire", "first", "last"] = "entire"
    n_messages: int = 0


class CreateSessionResponse(BaseModel):
    session_id: str
    parameters_detected: List[ParameterInfo]
    excluded_parameters: List[str]
    conversation_count: int


class GtAuditCase(BaseModel):
    conversation_id: str
    current_gt: str
    should_be: str
    reason: str


class ParameterSummary(BaseModel):
    accuracy: float
    status: str
    rca_findings: Optional[str] = None
    alignment_audit: Optional[str] = None
    audit_iteration: Optional[int] = None
    gt_audit_cases: Optional[List[GtAuditCase]] = None
    gt_audit_flagged_count: Optional[int] = None


class NodeProgress(BaseModel):
    node: str
    step: int
    total: int


class SessionStatusResponse(BaseModel):
    session_id: str
    current_phase: str
    current_iteration: int
    parameters: List[ParameterInfo] = Field(default_factory=list)
    clarifying_questions: List[Dict[str, Any]] = Field(default_factory=list)
    parameter_summary: Dict[str, ParameterSummary] = Field(default_factory=dict)
    progress_log: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    node_progress: Optional[NodeProgress] = None


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


class ContinueRequest(BaseModel):
    additional_iterations: int = 5


class ContinueResponse(BaseModel):
    new_session_id: str
    parameters_continuing: list[str]
