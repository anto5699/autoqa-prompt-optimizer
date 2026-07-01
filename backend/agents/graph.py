from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from agents.nodes.ambiguity_detection import ambiguity_detection
from agents.nodes.baseline_prompt_generator import baseline_prompt_generator
from agents.nodes.benchmarking import benchmarking
from agents.nodes.csv_ingestion import csv_ingestion
from agents.nodes.evaluator import evaluator
from agents.nodes.finalize import finalize
from agents.nodes.gt_alignment_audit import gt_alignment_audit
from agents.nodes.mid_loop_clarification import mid_loop_clarification
from agents.nodes.prompt_optimizer import prompt_optimizer
from agents.nodes.rca_analyzer import rca_analyzer
from agents.state import OptimizationState


def convergence_check(state: OptimizationState) -> str:
    if not state["parameters_below_target"]:
        return "finalize"
    if state["current_iteration"] >= state["max_iterations"]:
        return "finalize"
    return "rca_analyzer"


def _needs_alignment_audit(state: OptimizationState) -> str:
    records = state["parameter_records"]
    below = state["parameters_below_target"]
    current_iteration = state["current_iteration"]
    for rule_id in below:
        record = records.get(rule_id, {})
        history = record.get("iteration_history", [])
        if len(history) < 3:
            continue
        recent = [h["accuracy"] for h in history[-3:]]
        if (max(recent) - min(recent)) >= 0.03:
            continue
        # Stagnant — check if audit is due
        last_audit = record.get("audit_iteration")
        if last_audit is None or (current_iteration - last_audit) >= 3:
            return "gt_alignment_audit"
    return "mid_loop_clarification"


def route_entry(state: OptimizationState) -> str:
    return "evaluator" if state.get("skip_setup") else "csv_ingestion"


_builder = StateGraph(OptimizationState)

_builder.add_node("csv_ingestion", csv_ingestion)
_builder.add_node("ambiguity_detection", ambiguity_detection)
_builder.add_node("baseline_prompt_generator", baseline_prompt_generator)
_builder.add_node("evaluator", evaluator)
_builder.add_node("benchmarking", benchmarking)
_builder.add_node("rca_analyzer", rca_analyzer)
_builder.add_node("gt_alignment_audit", gt_alignment_audit)
_builder.add_node("mid_loop_clarification", mid_loop_clarification)
_builder.add_node("prompt_optimizer", prompt_optimizer)
_builder.add_node("finalize", finalize)

_builder.add_conditional_edges(
    START,
    route_entry,
    {"csv_ingestion": "csv_ingestion", "evaluator": "evaluator"},
)
_builder.add_edge("csv_ingestion", "ambiguity_detection")
_builder.add_edge("ambiguity_detection", "baseline_prompt_generator")
_builder.add_edge("baseline_prompt_generator", "evaluator")
_builder.add_edge("evaluator", "benchmarking")
_builder.add_conditional_edges(
    "benchmarking",
    convergence_check,
    {"finalize": "finalize", "rca_analyzer": "rca_analyzer"},
)
_builder.add_conditional_edges(
    "rca_analyzer",
    _needs_alignment_audit,
    {"gt_alignment_audit": "gt_alignment_audit", "mid_loop_clarification": "mid_loop_clarification"},
)
_builder.add_edge("gt_alignment_audit", "mid_loop_clarification")
_builder.add_edge("mid_loop_clarification", "prompt_optimizer")
_builder.add_edge("prompt_optimizer", "evaluator")
_builder.add_edge("finalize", END)

graph_app = _builder.compile(checkpointer=MemorySaver())
