"""Default dimension weights per node type.

Each scenario YAML overrides the prompt text; this module provides
the canonical dimension IDs and default weights for validation.
"""

DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "rca_analyzer": {
        "root_cause_accuracy": 0.40,
        "actionability": 0.30,
        "non_hallucination": 0.30,
    },
    "prompt_optimizer": {
        "improvement_direction": 0.25,
        "functional_correctness": 0.35,
        "generalisation": 0.25,
        "format_compliance": 0.15,
    },
    "gt_alignment_audit": {
        "gap_identification": 0.40,
        "strategy_clarity": 0.35,
        "non_hallucination": 0.25,
    },
    "mid_loop_clarification": {
        "question_relevance": 0.40,
        "non_redundancy": 0.35,
        "plain_language": 0.25,
    },
    "e2e": {
        "convergence_achieved": 0.50,
        "iteration_efficiency": 0.30,
        "locked_rules_respected": 0.20,
    },
}
