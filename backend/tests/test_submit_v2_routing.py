import pytest
from api.schemas.session import MetricConfig
from api.routes.sessions import _build_rule_from_config


def test_v2_rule_shape():
    """V2 MetricConfig produces a single unified rule with no trigger fields."""
    cfg = MetricConfig(
        type="static",
        version="v2",
        answer_description="CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent greets.\nEXCEPTION: None.",
        evaluation_type="first",
        n_messages=3,
    )
    rule = _build_rule_from_config("greeting_check", cfg)
    assert rule["version"] == "v2"
    assert rule["rule_type"] == "answer"
    assert rule["evaluation_type"] == "first"
    assert rule["n_messages"] == 3
    assert "trigger_description" not in rule


def test_v1_static_rule_shape():
    cfg = MetricConfig(type="static", answer_description="Desc", version="v1")
    rule = _build_rule_from_config("empathy", cfg)
    assert rule["version"] == "v1"
    assert rule["rule_type"] == "answer"
    assert "trigger_description" not in rule


def test_v1_dynamic_rule_shape():
    cfg = MetricConfig(type="dynamic", answer_description="Ans", trigger_description="Trig", version="v1")
    rule = _build_rule_from_config("callback_promise", cfg)
    assert rule["version"] == "v1"
    assert rule["rule_type"] == "dynamic"
    assert rule["trigger_description"] == "Trig"
