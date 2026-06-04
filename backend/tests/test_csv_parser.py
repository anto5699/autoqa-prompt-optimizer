import io
import json

import pandas as pd
import pytest

from utils.csv_parser import CSVParseError, parse

# ── helpers ────────────────────────────────────────────────────────────────────

VALID_TRANSCRIPT = json.dumps([
    {"msg": "Hello", "messageId": 0, "speaker": "agent", "timestamp": 1000}
])


def make_df(**overrides) -> pd.DataFrame:
    """Return a minimal valid DataFrame with 10 rows for rule_answer_1."""
    base = {
        "conversation_id": [f"conv_{i}" for i in range(10)],
        "transcript": [VALID_TRANSCRIPT] * 10,
        "rule_id": ["rule_answer_1"] * 10,
        "rule_type": ["answer"] * 10,
        "speaker": ["agent"] * 10,
        "evaluation_type": ["entire"] * 10,
        "n_messages": ["0"] * 10,
        "description": ["Agent greeted customer"] * 10,
        "ground_truth": ["Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


# ── valid input ─────────────────────────────────────────────────────────────────

def test_valid_csv_returns_correct_structures():
    convs, rules, gt_map, excluded = parse(to_csv_bytes(make_df()))
    assert len(convs) == 10
    assert len(rules) == 1
    assert rules[0]["rule_id"] == "rule_answer_1"
    assert rules[0]["rule_type"] == "answer"
    assert excluded == []
    assert gt_map["conv_0"]["rule_answer_1"] == "Yes"


def test_ground_truth_normalized_case():
    # lowercase and uppercase variants are normalized to canonical form
    df = make_df(ground_truth=["yes", "NO", "na", "Yes", "No", "Yes", "No", "Yes", "No", "Yes"])
    convs, rules, gt_map, excluded = parse(to_csv_bytes(df))
    assert gt_map["conv_0"]["rule_answer_1"] == "Yes"
    assert gt_map["conv_1"]["rule_answer_1"] == "No"
    assert gt_map["conv_2"]["rule_answer_1"] == "NA"


def test_ground_truth_normalized_na():
    # "NA" must survive normalization as "NA" (not "Na" from .title())
    df = make_df(ground_truth=["NA", "No", "Yes", "No", "Yes", "No", "Yes", "No", "Yes", "No"])
    convs, rules, gt_map, excluded = parse(to_csv_bytes(df))
    assert gt_map["conv_0"]["rule_answer_1"] == "NA"


def test_deduplication_keeps_first_transcript():
    df = make_df()
    # Add duplicate conv_0 with a different transcript
    dup_row = df.iloc[0].copy()
    dup_row["transcript"] = json.dumps([{"msg": "OTHER", "messageId": 0, "speaker": "agent", "timestamp": 1}])
    df2 = pd.concat([df, dup_row.to_frame().T], ignore_index=True)
    convs, _, _, _ = parse(to_csv_bytes(df2))
    conv_map = {c["conversation_id"]: c for c in convs}
    # First transcript should be retained
    assert conv_map["conv_0"]["transcript"][0]["msg"] == "Hello"


def test_rule_type_case_insensitive():
    df = make_df(rule_type=["Answer"] * 10)
    _, rules, _, _ = parse(to_csv_bytes(df))
    assert rules[0]["rule_type"] == "answer"


# ── missing columns ─────────────────────────────────────────────────────────────

def test_missing_column_raises():
    df = make_df()
    df = df.drop(columns=["ground_truth"])
    with pytest.raises(CSVParseError, match="Missing required columns"):
        parse(to_csv_bytes(df))


def test_multiple_missing_columns_named():
    df = make_df()
    df = df.drop(columns=["ground_truth", "rule_id"])
    with pytest.raises(CSVParseError, match="Missing required columns"):
        parse(to_csv_bytes(df))


# ── bad field values ────────────────────────────────────────────────────────────

def test_bad_ground_truth_raises():
    df = make_df(ground_truth=["Maybe"] * 10)
    with pytest.raises(CSVParseError):
        parse(to_csv_bytes(df))


def test_bad_rule_type_raises():
    df = make_df(rule_type=["unknown"] * 10)
    with pytest.raises(CSVParseError, match="rule_type"):
        parse(to_csv_bytes(df))


def test_bad_evaluation_type_raises():
    df = make_df(evaluation_type=["rolling"] * 10)
    with pytest.raises(CSVParseError, match="evaluation_type"):
        parse(to_csv_bytes(df))


def test_bad_speaker_raises():
    df = make_df(speaker=["supervisor"] * 10)
    with pytest.raises(CSVParseError, match="speaker"):
        parse(to_csv_bytes(df))


def test_negative_n_messages_raises():
    df = make_df(n_messages=["-1"] * 10)
    with pytest.raises(CSVParseError, match="non-negative"):
        parse(to_csv_bytes(df))


def test_non_integer_n_messages_raises():
    df = make_df(n_messages=["abc"] * 10)
    with pytest.raises(CSVParseError, match="integer"):
        parse(to_csv_bytes(df))


# ── transcript validation ───────────────────────────────────────────────────────

def test_invalid_transcript_json_raises():
    df = make_df(transcript=["not-json"] * 10)
    with pytest.raises(CSVParseError, match="transcript"):
        parse(to_csv_bytes(df))


def test_transcript_non_list_raises():
    df = make_df(transcript=[json.dumps({"msg": "hi"})] * 10)
    with pytest.raises(CSVParseError, match="transcript"):
        parse(to_csv_bytes(df))


# ── row count threshold ─────────────────────────────────────────────────────────

def test_fewer_than_10_rows_raises():
    df = make_df().iloc[:9]
    with pytest.raises(CSVParseError, match="10 rows"):
        parse(to_csv_bytes(df))


# ── rule exclusion ──────────────────────────────────────────────────────────────

def test_rule_with_fewer_than_5_evaluable_rows_excluded():
    # 4 evaluable (Yes/No) + 6 NA
    df = make_df(ground_truth=["Yes", "No", "Yes", "No", "NA", "NA", "NA", "NA", "NA", "NA"])
    _, rules, _, excluded = parse(to_csv_bytes(df))
    assert "rule_answer_1" in excluded
    assert rules == []


def test_rule_with_5_evaluable_rows_kept():
    df = make_df(ground_truth=["Yes", "No", "Yes", "No", "Yes", "NA", "NA", "NA", "NA", "NA"])
    _, rules, _, excluded = parse(to_csv_bytes(df))
    assert excluded == []
    assert len(rules) == 1


# ── metadata inconsistency ──────────────────────────────────────────────────────

def test_inconsistent_rule_metadata_raises():
    df = make_df()
    # Change speaker for row 5 under the same rule_id
    df.loc[5, "speaker"] = "customer"
    with pytest.raises(CSVParseError, match="speaker"):
        parse(to_csv_bytes(df))
