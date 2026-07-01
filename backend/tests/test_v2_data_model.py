from api.schemas.session import MetricConfig


def test_metric_config_v1_defaults():
    cfg = MetricConfig(type="static", answer_description="foo")
    assert cfg.version == "v1"
    assert cfg.evaluation_type == "entire"
    assert cfg.n_messages == 0


def test_metric_config_v2_explicit():
    cfg = MetricConfig(
        type="static",
        answer_description="CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent greets.\nEXCEPTION: None.",
        version="v2",
        evaluation_type="first",
        n_messages=5,
    )
    assert cfg.version == "v2"
    assert cfg.evaluation_type == "first"
    assert cfg.n_messages == 5


def test_metric_config_rejects_bad_version():
    import pytest
    with pytest.raises(Exception):
        MetricConfig(type="static", answer_description="foo", version="v3")
