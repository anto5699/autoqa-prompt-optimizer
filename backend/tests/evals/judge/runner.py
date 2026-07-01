import asyncio
import json
import re
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


@dataclass
class DimensionScore:
    id: str
    score: float
    rationale: str


@dataclass
class JudgeResult:
    scenario_id: str
    weighted: float
    passed: bool
    dimensions: list

    def __str__(self) -> str:
        dims = "; ".join(f"{d.id}={d.score:.2f}: {d.rationale[:80]}" for d in self.dimensions)
        return f"score={self.weighted:.2f} ({'PASS' if self.passed else 'FAIL'}) | {dims}"


_JUDGE_SYSTEM = (
    "You are an objective evaluator of AI system outputs. "
    "Score strictly on the stated criterion. "
    "Return ONLY valid JSON with keys 'score' (float 0.0-1.0) and 'rationale' (string, max 120 chars)."
)


async def _score_dimension(dim: dict, llm: BaseChatModel, retries: int = 2) -> DimensionScore:
    prompt = (
        f"{dim['prompt']}\n\n"
        "Score 1.0 = fully meets criterion, 0.7 = mostly meets it, "
        "0.4 = partially meets it, 0.0 = does not meet it.\n"
        'Return JSON: {"score": float, "rationale": "string"}'
    )
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await llm.ainvoke([
                SystemMessage(content=_JUDGE_SYSTEM),
                HumanMessage(content=prompt),
            ])
            raw = resp.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            data = json.loads(raw)
            return DimensionScore(
                id=dim["id"],
                score=float(data["score"]),
                rationale=str(data.get("rationale", "")),
            )
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)
    raise last_exc


async def judge_output(
    output: str,
    judge_config: dict,
    llm: BaseChatModel,
    *,
    scenario_id: str = "",
) -> JudgeResult:
    """Score a node output against the scenario's per-dimension judge config."""
    dimensions = judge_config["dimensions"]
    pass_threshold = float(judge_config.get("pass_threshold", 0.70))

    enriched = [
        {**dim, "prompt": dim["prompt"].replace("{output}", output)}
        for dim in dimensions
    ]

    scores = await asyncio.gather(*[_score_dimension(d, llm) for d in enriched])
    weighted = sum(d.score * dim["weight"] for d, dim in zip(scores, dimensions))

    return JudgeResult(
        scenario_id=scenario_id,
        weighted=weighted,
        passed=weighted >= pass_threshold,
        dimensions=list(scores),
    )
