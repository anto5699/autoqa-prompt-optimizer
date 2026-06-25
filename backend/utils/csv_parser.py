import json
import logging
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_FIXED_COLUMNS = {"ConversationID", "transcript"}
_GT_MAP = {"yes": "Yes", "no": "No", "na": "NA", "n/a": "NA", "": "NA"}


class CSVParseError(ValueError):
    pass


def parse(
    file_content: bytes,
) -> Tuple[
    List[Dict[str, Any]],        # conversations: [{conversation_id, transcript}]
    List[str],                   # metric_names: valid metric column names
    Dict[str, Dict[str, str]],   # ground_truth_map: {conv_id: {metric_name: GT}}
    List[str],                   # excluded_parameters: metric names with <5 evaluable rows
    List[str],                   # na_detected_parameters: valid metric names with ≥1 NA
]:
    """Parse wide-format CSV. Fixed cols: ConversationID, transcript. Rest = metric columns."""
    try:
        df = pd.read_csv(
            pd.io.common.BytesIO(file_content),
            dtype=str,
            keep_default_na=False,
            na_values=[],
        )
    except Exception as exc:
        raise CSVParseError(f"Failed to read CSV: {exc}") from exc

    # 1. Required fixed columns
    missing = REQUIRED_FIXED_COLUMNS - set(df.columns)
    if missing:
        raise CSVParseError(f"Missing required columns: {sorted(missing)}")

    # 2. Metric columns = everything except the two fixed ones
    metric_columns = [c for c in df.columns if c not in REQUIRED_FIXED_COLUMNS]
    if not metric_columns:
        raise CSVParseError(
            "CSV must have at least one metric column beyond ConversationID and transcript"
        )

    df = df.copy()

    # 3. Normalize ground truth values for all metric columns
    for col in metric_columns:
        df[col] = df[col].str.strip().str.lower().map(_GT_MAP)
        bad = df[df[col].isna()]
        if not bad.empty:
            raise CSVParseError(
                f"Invalid ground_truth values in metric '{col}' at rows "
                f"{bad.index.tolist()}: must be 'Yes', 'No', or 'NA'"
            )

    # 4. Transcript: JSON array preferred; plain text accepted and wrapped as single message
    parsed_transcripts: Dict[str, list] = {}
    for _, row in df.iterrows():
        conv_id = str(row["ConversationID"]).strip()
        if conv_id not in parsed_transcripts:
            raw = str(row["transcript"])
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, list):
                    raise ValueError("transcript must be a JSON array")
                parsed_transcripts[conv_id] = parsed
            except (json.JSONDecodeError, ValueError):
                parsed_transcripts[conv_id] = [{"speaker": "conversation", "msg": raw}]

    # 5. Minimum 10 rows
    if len(df) < 10:
        raise CSVParseError(f"CSV must have at least 10 rows; found {len(df)}")

    # 6. Build ground_truth_map
    ground_truth_map: Dict[str, Dict[str, str]] = {}
    for _, row in df.iterrows():
        conv_id = str(row["ConversationID"]).strip()
        ground_truth_map.setdefault(conv_id, {})
        for col in metric_columns:
            ground_truth_map[conv_id][col] = row[col]

    # 7. Exclude metrics with <5 evaluable (non-NA) rows
    excluded_parameters: List[str] = []
    valid_metric_columns: List[str] = []
    for col in metric_columns:
        evaluable = sum(
            1 for conv_gt in ground_truth_map.values()
            if conv_gt.get(col) in ("Yes", "No")
        )
        if evaluable < 5:
            excluded_parameters.append(col)
            logger.info("Excluding metric=%s: only %d evaluable rows", col, evaluable)
        else:
            valid_metric_columns.append(col)

    # 8. Detect NA in valid metrics
    na_detected_parameters: List[str] = [
        col for col in valid_metric_columns
        if any(conv_gt.get(col) == "NA" for conv_gt in ground_truth_map.values())
    ]

    logger.info(
        "CSV parsed: %d conversations, %d metrics (%d excluded)",
        len(parsed_transcripts), len(valid_metric_columns), len(excluded_parameters),
    )

    conversations: List[Dict[str, Any]] = [
        {"conversation_id": conv_id, "transcript": transcript}
        for conv_id, transcript in parsed_transcripts.items()
    ]

    return conversations, valid_metric_columns, ground_truth_map, excluded_parameters, na_detected_parameters
