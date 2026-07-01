#!/usr/bin/env python3
"""Convert pytest-json-report output to a structured evals-report.md."""
import json
import sys
from pathlib import Path
from datetime import datetime


def _score_label(score: float) -> str:
    if score >= 0.70:
        return f"🟢 {score:.2f}"
    if score >= 0.50:
        return f"🟡 {score:.2f}"
    return f"🔴 {score:.2f}"


def parse_report(json_path: Path) -> dict:
    with open(json_path) as f:
        data = json.load(f)

    tests = data.get("tests", [])
    summary = data.get("summary", {})

    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    error = summary.get("error", 0)
    total = summary.get("total", len(tests))
    duration = data.get("duration", 0)

    by_node: dict[str, list] = {}
    for t in tests:
        node_type = _extract_node(t.get("nodeid", ""))
        by_node.setdefault(node_type, []).append(t)

    dim_totals: dict[str, list[float]] = {}
    failures = []
    for t in tests:
        outcome = t.get("outcome", "unknown")
        scenario_id = _extract_scenario_id(t.get("nodeid", ""))
        node_type = _extract_node(t.get("nodeid", ""))
        longrepr = (t.get("call") or {}).get("longrepr", "") or ""
        dims = _parse_dims_from_longrepr(longrepr)
        for dim_id, dim_score in dims.items():
            dim_totals.setdefault(dim_id, []).append(dim_score)
        if outcome == "failed":
            failures.append({"id": scenario_id, "node": node_type, "longrepr": longrepr[:300], "dims": dims})

    dim_averages = {k: sum(v) / len(v) for k, v in dim_totals.items()}

    return {
        "passed": passed, "failed": failed, "error": error,
        "total": total, "duration": duration,
        "by_node": by_node, "failures": failures, "dim_averages": dim_averages,
    }


def _extract_node(nodeid: str) -> str:
    if "test_rca" in nodeid:           return "rca_analyzer"
    if "test_optimizer" in nodeid:     return "prompt_optimizer"
    if "test_alignment" in nodeid:     return "gt_alignment_audit"
    if "test_clarification" in nodeid: return "mid_loop_clarification"
    if "test_e2e" in nodeid:           return "e2e"
    return "other"


def _extract_scenario_id(nodeid: str) -> str:
    if "[" in nodeid and "]" in nodeid:
        return nodeid.split("[")[1].rstrip("]")
    return nodeid.split("::")[-1]


def _parse_dims_from_longrepr(longrepr: str) -> dict[str, float]:
    """Extract dimension scores from assert message like 'dim_id=0.45: ...'"""
    dims = {}
    for part in longrepr.split(";"):
        part = part.strip()
        if "=" in part:
            left, _, rest = part.partition("=")
            left = left.strip()
            try:
                score = float(rest.split(":")[0].strip())
                dims[left] = score
            except ValueError:
                pass
    return dims


def render_report(parsed: dict, run_timestamp: str) -> str:
    p = parsed
    avg_score = (p["passed"] / p["total"]) if p["total"] else 0.0

    node_labels = {
        "rca_analyzer": "RCA Analyzer",
        "prompt_optimizer": "Prompt Optimizer",
        "gt_alignment_audit": "GT Alignment Audit",
        "mid_loop_clarification": "Mid-Loop Clarification",
        "e2e": "End-to-End",
        "other": "Other",
    }
    node_order = ["rca_analyzer", "prompt_optimizer", "gt_alignment_audit", "mid_loop_clarification", "e2e"]

    lines = [
        "# Agentic Evals Report",
        "",
        f"**Run:** {run_timestamp}  ",
        f"**Duration:** {p['duration']:.1f}s",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Result | Count |",
        "|--------|-------|",
        f"| ✅ Passed | {p['passed']} |",
        f"| ❌ Failed | {p['failed']} |",
        f"| 💥 Errors | {p['error']} |",
        f"| **Total** | **{p['total']}** |",
        "",
        f"**Overall pass rate:** {p['passed']}/{p['total']} ({avg_score*100:.0f}%)",
        "",
        "---",
        "",
        "## Results by Node",
        "",
        "| Node | Passed | Total | Status |",
        "|------|--------|-------|--------|",
    ]

    for node_key in node_order:
        tests = p["by_node"].get(node_key, [])
        if not tests:
            continue
        node_passed = sum(1 for t in tests if t.get("outcome") == "passed")
        node_total = len(tests)
        if node_passed == node_total:
            status = "✅ All pass"
        elif node_passed > 0:
            status = f"⚠️ {node_passed}/{node_total}"
        else:
            status = "❌ All fail"
        lines.append(f"| {node_labels.get(node_key, node_key)} | {node_passed} | {node_total} | {status} |")

    lines += ["", "---", ""]

    if p["failures"]:
        lines += ["## Failed Scenarios", "", "| Scenario | Node | Score detail |", "|----------|------|-------------|"]
        for f in p["failures"]:
            dim_str = " | ".join(f"{k}={v:.2f}" for k, v in f["dims"].items()) or f["longrepr"][:120]
            lines.append(f"| `{f['id']}` | {node_labels.get(f['node'], f['node'])} | {dim_str} |")
        lines += ["", "---", ""]

    if p["dim_averages"]:
        lines += [
            "## Dimension Score Averages",
            "",
            "A consistently low dimension (< 0.65) is the actionable signal — it identifies which aspect of the node to improve next.",
            "",
            "| Dimension | Avg Score | Signal |",
            "|-----------|-----------|--------|",
        ]
        for dim, avg in sorted(p["dim_averages"].items(), key=lambda x: x[1]):
            signal = "🔴 Investigate" if avg < 0.65 else ("🟡 Watch" if avg < 0.75 else "🟢 Healthy")
            lines.append(f"| `{dim}` | {avg:.2f} | {signal} |")
        lines += ["", "---", ""]

    lines += ["## Recommended Next Steps", ""]
    low_dims = [d for d, avg in p["dim_averages"].items() if avg < 0.65]
    failed_nodes = {f["node"] for f in p["failures"]}

    if not p["failures"]:
        lines += [
            "All scenarios passed. The optimization pipeline is handling all documented failure modes correctly.",
            "",
            "**Suggested actions:**",
            "- Add adversarial or edge-case scenarios to push quality higher",
            "- Run E2E evals against real CSV data to validate end-to-end convergence",
        ]
    else:
        lines.append(f"{p['failed']} scenario(s) failed. Prioritise fixes in this order:")
        lines.append("")
        priority = 1
        node_advice = {
            "rca_analyzer": (
                "**RCA Analyzer** — Failures here cascade: a bad RCA feeds bad optimizer input.",
                "Check `agents/nodes/rca_analyzer.py` system prompt specificity",
            ),
            "prompt_optimizer": (
                "**Prompt Optimizer** — Description rewrites not addressing the RCA.",
                "Review optimizer system prompt: does it explicitly instruct addressing the RCA?",
            ),
            "gt_alignment_audit": (
                "**GT Alignment Audit** — Misses real gaps or hallucinates non-existent ones.",
                "Review `agents/nodes/gt_alignment_audit.py` system prompt for gap detection clarity",
            ),
            "mid_loop_clarification": (
                "**Mid-Loop Clarification** — Questions not targeted or not in plain language.",
                "Review `agents/nodes/mid_loop_clarification.py` audience instructions",
            ),
            "e2e": (
                "**E2E Pipeline** — Full pipeline convergence issues.",
                "Run failing E2E scenario manually and inspect `iteration_history`",
            ),
        }
        for node_key in node_order:
            if node_key in failed_nodes and node_key in node_advice:
                label, action = node_advice[node_key]
                lines.append(f"{priority}. {label}")
                lines.append(f"   - {action}")
                priority += 1

        if low_dims:
            lines += [
                "",
                f"**Low-scoring dimensions** (< 0.65): {', '.join(f'`{d}`' for d in low_dims)}",
                "These are cross-scenario signals — fixing the node prompt for this dimension improves multiple scenarios.",
            ]

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python report.py evals-report.json [output.md]", file=sys.stderr)
        sys.exit(1)

    json_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else json_path.with_suffix(".md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    parsed = parse_report(json_path)
    md = render_report(parsed, timestamp)
    out_path.write_text(md)
    print(f"Report written to {out_path}")
    print(f"  {parsed['passed']}/{parsed['total']} passed ({parsed['failed']} failed, {parsed['error']} errors)")


if __name__ == "__main__":
    main()
