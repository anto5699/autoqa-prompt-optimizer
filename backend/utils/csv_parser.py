import json
import logging
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    "conversation_id", "transcript", "rule_id", "rule_type",
    "speaker", "evaluation_type", "n_messages", "description", "ground_truth",
}

VALID_RULE_TYPES = {"trigger", "answer"}
VALID_EVALUATION_TYPES = {"entire", "first", "last"}
VALID_SPEAKERS = {"agent", "customer"}
VALID_GROUND_TRUTHS = {"Yes", "No", "NA"}


class CSVParseError(ValueError):
    pass


def parse(
    file_content: bytes,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Dict[str, str]], List[str]]:
    """Parse and validate the input CSV.

    Returns:
        conversations: deduplicated list of {conversation_id, transcript}
        rules: list of unique rule metadata dicts
        ground_truth_map: {conv_id: {rule_id: "Yes"|"No"|"NA"}}
        excluded_rules: rule_ids with <5 evaluable (non-NA) rows
    """
    try:
        df = pd.read_csv(
            pd.io.common.BytesIO(file_content),
            dtype=str,
            keep_default_na=False,
            na_values=[],
        )
    except Exception as exc:
        raise CSVParseError(f"Failed to read CSV: {exc}") from exc

    # 1. Required columns
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise CSVParseError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()

    # 2. Normalize rule_type
    df["rule_type"] = df["rule_type"].str.strip().str.lower()
    bad_rule_type = df[~df["rule_type"].isin(VALID_RULE_TYPES)]
    if not bad_rule_type.empty:
        raise CSVParseError(
            f"Invalid rule_type values in rows {bad_rule_type.index.tolist()}: "
            f"must be 'trigger' or 'answer'"
        )

    # 3. evaluation_type
    df["evaluation_type"] = df["evaluation_type"].str.strip().str.lower()
    bad_eval = df[~df["evaluation_type"].isin(VALID_EVALUATION_TYPES)]
    if not bad_eval.empty:
        raise CSVParseError(
            f"Invalid evaluation_type values in rows {bad_eval.index.tolist()}: "
            f"must be 'entire', 'first', or 'last'"
        )

    # 4. n_messages must be non-negative integer
    try:
        df["n_messages"] = df["n_messages"].astype(int)
    except (ValueError, TypeError) as exc:
        raise CSVParseError(f"n_messages must be an integer: {exc}") from exc
    if (df["n_messages"] < 0).any():
        raise CSVParseError("n_messages must be a non-negative integer")

    # 5. speaker
    df["speaker"] = df["speaker"].str.strip().str.lower()
    bad_speaker = df[~df["speaker"].isin(VALID_SPEAKERS)]
    if not bad_speaker.empty:
        raise CSVParseError(
            f"Invalid speaker values in rows {bad_speaker.index.tolist()}: "
            f"must be 'agent' or 'customer'"
        )

    # 6. ground_truth normalize — use explicit mapping so "NA" never becomes "Na"
    _gt_map = {"yes": "Yes", "no": "No", "na": "NA"}
    df["ground_truth"] = df["ground_truth"].str.strip().str.lower().map(_gt_map)
    bad_gt = df[df["ground_truth"].isna()]
    if not bad_gt.empty:
        raise CSVParseError(
            f"Invalid ground_truth values in rows {bad_gt.index.tolist()}: "
            f"must be 'Yes', 'No', or 'NA'"
        )

    # 7. transcript must be valid JSON list
    def parse_transcript(val: str) -> list:
        try:
            parsed = json.loads(val)
            if not isinstance(parsed, list):
                raise ValueError("transcript must be a JSON array")
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            raise CSVParseError(f"Invalid transcript JSON: {exc}") from exc

    parsed_transcripts: Dict[str, list] = {}
    for idx, row in df.iterrows():
        conv_id = str(row["conversation_id"]).strip()
        if conv_id not in parsed_transcripts:
            parsed_transcripts[conv_id] = parse_transcript(str(row["transcript"]))

    # 8. Minimum 10 valid rows
    if len(df) < 10:
        raise CSVParseError(f"CSV must have at least 10 rows; found {len(df)}")

    # 9. Rule metadata consistency within each rule_id
    metadata_cols = ["rule_type", "speaker", "evaluation_type", "n_messages"]
    for rule_id, group in df.groupby("rule_id"):
        for col in metadata_cols:
            if group[col].nunique() > 1:
                raise CSVParseError(
                    f"Inconsistent {col!r} values for rule_id {rule_id!r}: "
                    f"{group[col].unique().tolist()}"
                )

    # Build ground_truth_map
    ground_truth_map: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        conv_id = str(row["conversation_id"]).strip()
        rule_id = str(row["rule_id"]).strip()
        ground_truth_map.setdefault(conv_id, {})[rule_id] = row["ground_truth"]

    # 9. Each rule_id must have ≥5 evaluable (non-NA) rows; excluded otherwise
    all_rule_ids = df["rule_id"].unique().tolist()
    excluded_rules: List[str] = []
    valid_rule_ids: List[str] = []

    for rule_id in all_rule_ids:
        evaluable_count = sum(
            1 for conv_gt in ground_truth_map.values()
            if conv_gt.get(rule_id) in ("Yes", "No")
        )
        if evaluable_count < 5:
            excluded_rules.append(rule_id)
            logger.info("Excluding rule_id=%s: only %d evaluable rows", rule_id, evaluable_count)
        else:
            valid_rule_ids.append(rule_id)

    logger.info(
        "CSV parsed: %d conversations, %d rules (%d excluded)",
        len(parsed_transcripts), len(valid_rule_ids), len(excluded_rules),
    )

    # Build deduplicated conversations list
    conversations: List[Dict[str, Any]] = [
        {"conversation_id": conv_id, "transcript": transcript}
        for conv_id, transcript in parsed_transcripts.items()
    ]

    # Build rules list (unique rule metadata, only valid rules)
    seen_rule_ids: set = set()
    rules: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        rule_id = str(row["rule_id"]).strip()
        if rule_id in valid_rule_ids and rule_id not in seen_rule_ids:
            seen_rule_ids.add(rule_id)
            rules.append({
                "rule_id": rule_id,
                "rule_type": row["rule_type"],
                "speaker": row["speaker"],
                "evaluation_type": row["evaluation_type"],
                "n_messages": int(row["n_messages"]),
                "description": str(row["description"]).strip(),
            })

    return conversations, rules, ground_truth_map, excluded_rules
