import operator
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict


class RuleRecord(TypedDict):
    rule_id: str
    rule_type: Literal["trigger", "answer", "dynamic"]
    version: Literal["v1", "v2"]
    speaker: str
    evaluation_type: Literal["entire", "first", "last"]
    n_messages: int

    # Dynamic metrics store both descriptions; static/answer rules leave these None
    trigger_description: Optional[str]
    trigger_speaker: Optional[str]

    current_description: str
    iteration_history: List[Dict[str, Any]]

    current_predictions: Dict[str, str]
    current_rationales: Dict[str, str]
    current_accuracy: float
    current_precision: float
    current_recall: float
    current_f1: float
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int
    not_applicable_count: int
    rca_findings: Optional[str]
    alignment_audit: Optional[str]
    audit_iteration: Optional[int]
    optimization_notes: Optional[str]
    status: Literal["pending", "optimizing", "converged", "max_iterations_reached"]

    # Regression tracking — set during first benchmarking pass
    initial_accuracy: Optional[float]
    best_accuracy: Optional[float]
    best_description: Optional[str]
    best_trigger_description: Optional[str]
    best_predictions: Optional[Dict[str, str]]
    best_rationales: Optional[Dict[str, str]]
    original_description: Optional[str]


ParameterOptimizationRecord = RuleRecord


class ClarifyingQuestion(TypedDict, total=False):
    question_id: str
    parameter_name: str
    question_text: str
    rationale: str
    clarification_forced: bool  # True when forced as fallback; False/absent for LLM-generated
    question_type: str  # "ambiguity" (default) | "pivot"


class OptimizationState(TypedDict):
    session_id: str
    system_prompt: str
    system_prompt_v2: str
    language: str
    llm_config: Dict[str, str]

    conversations: List[Dict[str, Any]]
    rules: List[Dict[str, Any]]
    ground_truth_map: Dict[str, Dict[str, str]]
    excluded_rules: List[str]

    clarifying_questions: List[ClarifyingQuestion]
    user_answers: Dict[str, str]
    clarification_complete: bool
    clarified_rule_ids: List[str]
    pivot_asked_rule_ids: List[str]   # rules that received a pivot (logic-replace) question
    pivot_approved_rules: List[str]   # rules where user approved discarding current description logic
    pre_audit_results: Dict[str, str]  # rule_id → pre-flight GT audit text (all audited rules)

    current_iteration: int
    max_iterations: int
    accuracy_target: float
    parameter_records: Dict[str, ParameterOptimizationRecord]

    optimization_complete: bool
    parameters_meeting_target: List[str]
    parameters_below_target: List[str]

    progress_log: Annotated[List[str], operator.add]
    current_phase: Literal[
        "ingesting", "detecting_ambiguity", "awaiting_clarification",
        "generating_baselines", "evaluating", "benchmarking",
        "analyzing_failures", "optimizing_prompts", "complete", "error"
    ]

    final_report: Optional[Dict[str, Any]]
    skip_setup: bool  # True skips csv_ingestion → ambiguity_detection → baseline_prompt_generator
