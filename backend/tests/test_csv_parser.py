import io
import json

import pandas as pd
import pytest

from utils.csv_parser import CSVParseError, parse

VALID_TRANSCRIPT = json.dumps([
    {"msg": "Hello", "messageId": 0, "speaker": "agent", "timestamp": 1000}
])


def make_df(**overrides) -> pd.DataFrame:
    """Return a minimal valid wide-format DataFrame with 10 rows and 2 metrics."""
    base = {
        "ConversationID": [f"conv_{i}" for i in range(10)],
        "transcript": [VALID_TRANSCRIPT] * 10,
        "greeting_compliance": ["Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No"],
        "empathy_score":       ["No", "Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No", "Yes"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


# ── valid input ──────────────────────────────────────────────────────────────────

def test_valid_csv_returns_correct_structures():
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(make_df()))
    assert len(convs) == 10
    assert set(metrics) == {"greeting_compliance", "empathy_score"}
    assert excluded == []
    assert gt_map["conv_0"]["greeting_compliance"] == "Yes"
    assert gt_map["conv_1"]["greeting_compliance"] == "No"


def test_ground_truth_normalized_case():
    df = make_df(greeting_compliance=["yes", "NO", "na", "Yes", "No", "Yes", "No", "Yes", "No", "Yes"])
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(df))
    assert gt_map["conv_0"]["greeting_compliance"] == "Yes"
    assert gt_map["conv_1"]["greeting_compliance"] == "No"
    assert gt_map["conv_2"]["greeting_compliance"] == "NA"


def test_na_detected_parameters():
    df = make_df(empathy_score=["NA", "Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No", "Yes"])
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(df))
    assert "empathy_score" in na_detected
    assert "greeting_compliance" not in na_detected


def test_no_na_detected_when_all_yes_no():
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(make_df()))
    assert na_detected == []


def test_deduplication_keeps_first_transcript():
    df = make_df()
    dup_row = df.iloc[0].copy()
    dup_row["transcript"] = json.dumps([{"msg": "OTHER", "messageId": 0, "speaker": "agent", "timestamp": 1}])
    df2 = pd.concat([df, dup_row.to_frame().T], ignore_index=True)
    convs, _, _, _, _ = parse(to_csv_bytes(df2))
    conv_map = {c["conversation_id"]: c for c in convs}
    assert conv_map["conv_0"]["transcript"][0]["msg"] == "Hello"


def test_single_metric_column_valid():
    df = make_df().drop(columns=["empathy_score"])
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(df))
    assert metrics == ["greeting_compliance"]


# ── missing required columns ─────────────────────────────────────────────────────

def test_missing_conversation_id_raises():
    df = make_df().rename(columns={"ConversationID": "conv_id"})
    with pytest.raises(CSVParseError, match="Missing required columns"):
        parse(to_csv_bytes(df))


def test_missing_transcript_raises():
    df = make_df().drop(columns=["transcript"])
    with pytest.raises(CSVParseError, match="Missing required columns"):
        parse(to_csv_bytes(df))


def test_no_metric_columns_raises():
    df = make_df()[["ConversationID", "transcript"]]
    with pytest.raises(CSVParseError, match="at least one metric column"):
        parse(to_csv_bytes(df))


# ── bad ground truth values ───────────────────────────────────────────────────────

def test_bad_ground_truth_raises():
    df = make_df(greeting_compliance=["Maybe"] * 10)
    with pytest.raises(CSVParseError, match="greeting_compliance"):
        parse(to_csv_bytes(df))


def test_empty_ground_truth_normalises_to_na():
    # Blank cells map to NA; all 10 rows become NA → metric excluded (< 5 evaluable)
    df = make_df(greeting_compliance=[""] * 10)
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(df))
    assert "greeting_compliance" in excluded


# ── transcript validation ────────────────────────────────────────────────────────

def test_invalid_transcript_json_wraps_as_plain_text():
    df = make_df(transcript=["not-json"] * 10)
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(df))
    assert isinstance(convs[0]["transcript"], list)
    assert convs[0]["transcript"][0]["speaker"] == "conversation"
    assert convs[0]["transcript"][0]["msg"] == "not-json"


def test_transcript_non_list_wraps_as_plain_text():
    raw = json.dumps({"msg": "hi"})
    df = make_df(transcript=[raw] * 10)
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(df))
    assert isinstance(convs[0]["transcript"], list)
    assert convs[0]["transcript"][0]["speaker"] == "conversation"


# ── row count threshold ───────────────────────────────────────────────────────────

def test_fewer_than_10_rows_raises():
    df = make_df().iloc[:9]
    with pytest.raises(CSVParseError, match="10 rows"):
        parse(to_csv_bytes(df))


# ── metric exclusion ─────────────────────────────────────────────────────────────

def test_metric_with_fewer_than_5_evaluable_rows_excluded():
    df = make_df(greeting_compliance=["Yes", "No", "Yes", "No", "NA", "NA", "NA", "NA", "NA", "NA"])
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(df))
    assert "greeting_compliance" in excluded
    assert "greeting_compliance" not in metrics


def test_metric_with_5_evaluable_rows_kept():
    df = make_df(greeting_compliance=["Yes", "No", "Yes", "No", "Yes", "NA", "NA", "NA", "NA", "NA"])
    convs, metrics, gt_map, excluded, na_detected = parse(to_csv_bytes(df))
    assert excluded == []
    assert "greeting_compliance" in metrics
