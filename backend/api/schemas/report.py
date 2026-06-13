from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ConfusionMatrix(BaseModel):
    tp: int
    tn: int
    fp: int
    fn: int


class IterationEntry(BaseModel):
    iteration: int
    accuracy: float
    description: Optional[str] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1: Optional[float] = None


class ParameterReport(BaseModel):
    status: str
    final_accuracy: float
    final_precision: float
    final_recall: float
    final_f1: float
    confusion_matrix: ConfusionMatrix
    not_applicable_count: int
    final_prompt: str
    optimization_notes: Optional[str] = None
    iteration_history: List[Dict[str, Any]]
    rca_findings: Optional[str] = None
    recommendations: List[str]


class ReportSummary(BaseModel):
    total_parameters: int
    parameters_meeting_target: int
    parameters_below_target: int
    overall_accuracy: float
    overall_precision: float
    overall_recall: float
    total_iterations: int
    total_conversations: int
    accuracy_target: float


class FinalReport(BaseModel):
    session_id: str
    generated_at: str
    summary: ReportSummary
    parameters: Dict[str, ParameterReport]


class ReportInProgressResponse(BaseModel):
    status: str
    current_phase: str
