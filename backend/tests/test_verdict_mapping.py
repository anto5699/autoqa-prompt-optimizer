# backend/tests/test_verdict_mapping.py
import pytest
from agents.nodes.evaluator import _verdict_from_v2_result

@pytest.mark.parametrize("result,expected", [
    ({"isQualified": True}, "Yes"),
    ({"isQualified": False}, "No"),
    ({"isQualified": None}, "NA"),
    ({}, "NA"),
    # explicit verdict wins over isQualified
    ({"verdict": "YES", "isQualified": False}, "Yes"),
    ({"verdict": "no", "isQualified": True}, "No"),
    ({"verdict": "NA", "isQualified": True}, "NA"),
    ({"verdict": "yes"}, "Yes"),
])
def test_verdict_from_v2_result(result, expected):
    assert _verdict_from_v2_result(result) == expected
