from agents.nodes.evaluator import _parse_batch_response


def test_partial_json_recovery():
    """Valid objects are recovered; malformed ones default to isQualified=False, rationale=''."""
    valid_obj = '{"_id": "r1", "isQualified": true, "rationale": "Agent greeted the customer"}'
    # Malformed: no closing brace, invalid JSON
    content = f"[{valid_obj}, {{_id: r2, bad json"

    results, had_error = _parse_batch_response(content, ["r1", "r2"])

    assert had_error
    r1 = next(r for r in results if r["_id"] == "r1")
    r2 = next(r for r in results if r["_id"] == "r2")
    assert r1["isQualified"] is True
    assert r1["rationale"] == "Agent greeted the customer"
    assert r2["isQualified"] is False
    assert r2["rationale"] == ""


def test_valid_json_array_returns_no_error():
    """A fully valid JSON response returns had_error=False."""
    content = '[{"_id": "r1", "isQualified": false, "rationale": "Agent did not greet"}]'
    results, had_error = _parse_batch_response(content, ["r1"])

    assert not had_error
    assert results[0]["_id"] == "r1"
    assert results[0]["isQualified"] is False
    assert results[0]["rationale"] == "Agent did not greet"
