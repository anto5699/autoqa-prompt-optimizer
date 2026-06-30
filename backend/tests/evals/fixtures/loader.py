from pathlib import Path
import yaml

_SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"

_REQUIRED_FIELDS = {"id", "description", "node", "conversations", "judge"}


def load_scenarios(node_type: str) -> list[dict]:
    """Return all YAML scenario dicts for a given node type directory."""
    scenario_dir = _SCENARIOS_DIR / node_type
    if not scenario_dir.exists():
        raise FileNotFoundError(f"Scenario directory not found: {scenario_dir}")
    scenarios = []
    for path in sorted(scenario_dir.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        _validate(data, path)
        scenarios.append(data)
    if not scenarios:
        raise ValueError(f"No YAML scenarios found in {scenario_dir}")
    return scenarios


def _validate(data: dict, path: Path) -> None:
    missing = _REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ValueError(f"{path.name}: missing required fields {missing}")
    # Scenarios must define either a single rule or a rules list
    if "rule" not in data and "rules" not in data:
        raise ValueError(f"{path.name}: must define 'rule' (single) or 'rules' (list)")
    if not data.get("judge", {}).get("dimensions"):
        raise ValueError(f"{path.name}: judge.dimensions must be a non-empty list")
