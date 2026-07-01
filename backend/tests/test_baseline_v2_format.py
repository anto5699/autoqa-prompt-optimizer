from agents.nodes.baseline_prompt_generator import _is_structured_v2


def test_is_structured_v2_detects_condition_prefix():
    desc = "CONDITION: Always.\nEXPECTED BEHAVIOR:\n  - Agent greets.\nEXCEPTION: None."
    assert _is_structured_v2(desc) is True


def test_is_structured_v2_detects_expected_behavior_line():
    desc = "CONDITION: Customer requests help.\nEXPECTED BEHAVIOR:\n  - Agent assists.\nEXCEPTION: None."
    assert _is_structured_v2(desc) is True


def test_is_structured_v2_rejects_v1_format():
    desc = "METRIC_NAME: Greeting Check\nSPEAKER: Agent\nACTION: Greets.\nPASS_LOGIC: ALL\nPASS_CRITERIA:\n1. Said hello."
    assert _is_structured_v2(desc) is False


def test_is_structured_v2_rejects_plain_text():
    desc = "The agent must greet the customer at the start of the call."
    assert _is_structured_v2(desc) is False
