from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agents.nodes.ambiguity_detection import ambiguity_detection
from agents.nodes.baseline_prompt_generator import baseline_prompt_generator
from agents.nodes.benchmarking import benchmarking
from agents.nodes.csv_ingestion import csv_ingestion
from agents.nodes.evaluator import evaluator
from agents.nodes.finalize import finalize
from agents.nodes.prompt_optimizer import prompt_optimizer
from agents.nodes.rca_analyzer import rca_analyzer
from agents.state import OptimizationState


def convergence_check(state: OptimizationState) -> str:
    if not state["parameters_below_target"]:
        return "finalize"
    if state["current_iteration"] >= state["max_iterations"]:
        return "finalize"
    return "rca_analyzer"


_builder = StateGraph(OptimizationState)

_builder.add_node("csv_ingestion", csv_ingestion)
_builder.add_node("ambiguity_detection", ambiguity_detection)
_builder.add_node("baseline_prompt_generator", baseline_prompt_generator)
_builder.add_node("evaluator", evaluator)
_builder.add_node("benchmarking", benchmarking)
_builder.add_node("rca_analyzer", rca_analyzer)
_builder.add_node("prompt_optimizer", prompt_optimizer)
_builder.add_node("finalize", finalize)

_builder.set_entry_point("csv_ingestion")
_builder.add_edge("csv_ingestion", "ambiguity_detection")
_builder.add_edge("ambiguity_detection", "baseline_prompt_generator")
_builder.add_edge("baseline_prompt_generator", "evaluator")
_builder.add_edge("evaluator", "benchmarking")
_builder.add_conditional_edges(
    "benchmarking",
    convergence_check,
    {"finalize": "finalize", "rca_analyzer": "rca_analyzer"},
)
_builder.add_edge("rca_analyzer", "prompt_optimizer")
_builder.add_edge("prompt_optimizer", "evaluator")
_builder.add_edge("finalize", END)

graph_app = _builder.compile(checkpointer=MemorySaver())
