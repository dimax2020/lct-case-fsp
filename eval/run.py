"""NDCG@10 of matching.service.score_pair against a skill-overlap baseline.

Run with the API virtualenv from the repo root:

    services/api/.venv/bin/python eval/run.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "api"))

from app.matching.service import NeedView, RequirementView, score_pair
from app.profile.service import CandidateFeatures, EvidenceFeature, FspFeature, SkillFeature
from eval.metrics import ndcg_at_k

TODAY = date(2026, 10, 11)
STUB_NOTE = (
    "score_pair всё ещё константная заглушка фазы 0 (s=0.5). "
    "Цифры NDCG не осмысленны, пока агент D не заменит score_pair."
)


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _need_view(raw: dict, benefits: list[str]) -> NeedView:
    return NeedView(
        id=raw["id"],
        specialization=raw["specialization"],
        grades=list(raw["grades"]),
        salary_from=int(raw["salary_from"]),
        salary_to=int(raw["salary_to"]),
        formats=list(raw["formats"]),
        city=raw.get("city"),
        must_skills=list(raw["must_skills"]),
        nice_skills=list(raw["nice_skills"]),
        domain=raw.get("domain"),
        stages=int(raw["stages"]),
        benefits=list(benefits),
        requirements=[
            RequirementView(
                id=item["id"],
                task=item["task"],
                domain=item.get("domain"),
                skills=list(item["skills"]),
                scale=item.get("scale"),
                kind=item["kind"],
                embedding=None,
            )
            for item in raw["requirements"]
        ],
        description=raw["description"],
    )


def _features(raw: dict, open_invites: int) -> CandidateFeatures:
    parts = raw["full_name"].split()
    display = parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][:1]}."
    starts = [item["start"] for item in raw["experiences"] if item.get("start")]
    years = None
    if starts:
        first = min(date.fromisoformat(item) for item in starts)
        years = round((TODAY - first).days / 365.25, 2)
    last_active = datetime.fromisoformat(raw["last_active_at"]) if raw.get("last_active_at") else None
    return CandidateFeatures(
        candidate_id=raw["id"],
        full_name=raw["full_name"],
        display_name=display,
        specialization=raw["specialization"],
        grade=raw["grade"],
        grade_score=None if raw["grade_score"] is None else float(raw["grade_score"]),
        min_salary=raw["min_salary"],
        formats=list(raw["formats"]),
        status=raw["status"],
        visible=bool(raw["visible"]),
        city=raw["city"],
        liked_skills=list(raw["liked_skills"]),
        disliked_skills=list(raw["disliked_skills"]),
        liked_domains=list(raw["liked_domains"]),
        blocked_domains=list(raw["blocked_domains"]),
        last_active_at=last_active,
        skills=[
            SkillFeature(
                skill_id=item["skill_id"],
                score=None if item["score"] is None else float(item["score"]),
                source=item["source"],
            )
            for item in raw["skills"]
        ],
        evidence=[
            EvidenceFeature(
                id=item["id"],
                task=item["task"],
                domain=item.get("domain"),
                skills=list(item["skills"]),
                role=item["role"],
                date=date.fromisoformat(item["date"]) if item.get("date") else None,
                trust=float(item["trust"]),
                embedding=None,
                origin=item["origin"],
                evidence_span=item.get("evidence_span"),
            )
            for item in raw["evidence"]
        ],
        fsp=[
            FspFeature(
                discipline=item["discipline"],
                event=item["event"],
                place=item.get("place"),
                year=item.get("year"),
            )
            for item in raw["fsp"]
        ],
        open_invites=open_invites,
        experience_years=years,
    )


def _overlap(need: dict, candidate: dict) -> int:
    owned = {item["skill_id"] for item in candidate["skills"]}
    wanted = set(need["must_skills"]) | set(need["nice_skills"])
    return len(owned & wanted)


async def evaluate() -> dict:
    candidates = {row["id"]: row for row in _load_json(ROOT / "seed" / "data" / "candidates.json")}
    needs = {row["id"]: row for row in _load_json(ROOT / "seed" / "data" / "needs.json")}
    companies = {row["id"]: row for row in _load_json(ROOT / "seed" / "data" / "companies.json")}
    invitations = _load_json(ROOT / "seed" / "data" / "invitations.json")
    gold = _jsonl(ROOT / "eval" / "gold.jsonl")
    opens: dict[str, int] = {}
    for invitation in invitations:
        if invitation["status"] in {"sent", "viewed"}:
            opens[invitation["candidate_id"]] = opens.get(invitation["candidate_id"], 0) + 1

    grouped: dict[str, list[dict]] = {}
    for row in gold:
        grouped.setdefault(row["need_id"], []).append(row)

    rows = []
    stub_flags: list[bool] = []
    for need_id, labeled in grouped.items():
        need = needs[need_id]
        view = _need_view(need, companies[need["company_id"]]["benefits"])
        formula: list[tuple[float, str, int]] = []
        baseline: list[tuple[int, str, int]] = []
        for item in labeled:
            candidate = candidates[item["candidate_id"]]
            breakdown = await score_pair(view, _features(candidate, opens.get(candidate["id"], 0)))
            formula.append((breakdown.s, candidate["id"], int(item["relevance"])))
            baseline.append((_overlap(need, candidate), candidate["id"], int(item["relevance"])))
            stub_flags.append(breakdown.explanations == ["Заглушка фазы 0"] and breakdown.s == 0.5)
        formula.sort(key=lambda item: (-item[0], item[1]))
        baseline.sort(key=lambda item: (-item[0], item[1]))
        rows.append(
            {
                "need_id": need_id,
                "title": need["title"],
                "n": len(labeled),
                "formula": ndcg_at_k([item[2] for item in formula]),
                "baseline": ndcg_at_k([item[2] for item in baseline]),
            }
        )
    rows.sort(key=lambda item: item["title"])
    macro_formula = sum(item["formula"] for item in rows) / len(rows)
    macro_baseline = sum(item["baseline"] for item in rows) / len(rows)
    stub = bool(stub_flags) and all(stub_flags)
    return {
        "rows": rows,
        "macro_formula": macro_formula,
        "macro_baseline": macro_baseline,
        "stub": stub,
        "note": STUB_NOTE if stub else "score_pair отвечает разными скорами.",
    }


def _bar(value: float) -> str:
    return "█" * int(round(value * 20))


def render(result: dict) -> str:
    lines = [
        "NDCG@10  formula (score_pair) vs baseline (overlapping skills)",
        f"{'need':<44} {'n':>3} {'formula':>8} {'baseline':>8}",
    ]
    for row in result["rows"]:
        title = row["title"] if len(row["title"]) <= 44 else row["title"][:41] + "..."
        lines.append(f"{title:<44} {row['n']:>3} {row['formula']:>8.3f} {row['baseline']:>8.3f}")
    lines.append(
        f"{'MACRO':<44} {len(result['rows']):>3} {result['macro_formula']:>8.3f} {result['macro_baseline']:>8.3f}"
    )
    lines.append("")
    lines.append(f"formula   {result['macro_formula']:.3f}  {_bar(result['macro_formula'])}")
    lines.append(f"baseline  {result['macro_baseline']:.3f}  {_bar(result['macro_baseline'])}")
    lines.append("")
    lines.append(result["note"])
    thresholds = json.loads((ROOT / "eval" / "sim_thresholds.json").read_text(encoding="utf-8"))
    lines.append(
        "sim proxy  "
        f"offset={thresholds['sim_offset']} scale={thresholds['sim_scale']} "
        f"spearman={thresholds['spearman']} apply_to_config={thresholds['apply_to_config']}"
    )
    lines.append(
        "sim tz     "
        f"offset={thresholds['tz_defaults']['sim_offset']} scale={thresholds['tz_defaults']['sim_scale']} "
        "(оставить в matching/config.py, пока нет e5)"
    )
    return "\n".join(lines)


def main() -> None:
    print(render(asyncio.run(evaluate())))


if __name__ == "__main__":
    main()
