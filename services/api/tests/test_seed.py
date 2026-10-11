"""Seed and eval checks that do not need Postgres."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "seed"))


def _generate():
    spec = importlib.util.spec_from_file_location("seed_generate", REPO / "seed" / "generate.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generated():
    return _generate().build_dataset()


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_committed_json_matches_generator(generated) -> None:
    for name in ("candidates", "companies", "needs", "invitations", "users"):
        assert _json(REPO / "seed" / "data" / f"{name}.json") == generated[name]
    assert _json(REPO / "seed" / "fsp_achievements.json") == generated["fsp_achievements"]
    assert _json(REPO / "seed" / "demo" / "scenario.json") == generated["scenario"]
    gold = [json.loads(line) for line in (REPO / "eval" / "gold.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert gold == generated["gold"]
    pairs = [json.loads(line) for line in (REPO / "eval" / "sim_pairs.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert pairs == generated["sim_pairs"]
    assert _json(REPO / "eval" / "sim_thresholds.json") == generated["sim_thresholds"]


def test_seed_shape_and_stop_list() -> None:
    generate = _generate()
    candidates = _json(REPO / "seed" / "data" / "candidates.json")
    companies = _json(REPO / "seed" / "data" / "companies.json")
    needs = _json(REPO / "seed" / "data" / "needs.json")
    invitations = _json(REPO / "seed" / "data" / "invitations.json")
    fsp = _json(REPO / "seed" / "fsp_achievements.json")
    skills = yaml.safe_load((REPO / "taxonomy" / "data" / "skills.yaml").read_text(encoding="utf-8"))
    skill_ids = {item["id"] for item in skills}
    by_spec: dict[str, int] = {}
    for candidate in candidates:
        by_spec[candidate["specialization"]] = by_spec.get(candidate["specialization"], 0) + 1
        for row in candidate["skills"]:
            assert row["skill_id"] in skill_ids
    assert by_spec == {"backend": 100, "frontend": 100, "data_ml": 100, "devops": 100}
    assert len(companies) == 15
    assert len(needs) == 25
    assert len(invitations) == 80
    assert len(fsp) == 120
    assert {item["status"] for item in invitations} == {"sent", "viewed", "accepted", "declined", "expired", "revoked"}
    stop = generate.load_stop(REPO / "seed" / "stop_companies.txt")
    assert generate.forbidden("Яндекс", stop) == "яндекс"
    assert generate.forbidden("Северная Лампа", stop) is None
    for company in companies:
        assert generate.forbidden(company["name"], stop) is None
    for need in needs:
        assert len(need["description"]) >= 300
        assert 1 <= len(need["must_skills"]) <= 5


def test_demo_scenario_ranks_candidate() -> None:
    scenario = _json(REPO / "seed" / "demo" / "scenario.json")
    assert scenario["candidate_email"] == "candidate@demo.fsp"
    assert scenario["employer_email"] == "employer@demo.fsp"
    assert scenario["hint"] == "Kafka только подтверждённая"
    assert scenario["pool_before"] == 24
    assert scenario["pool_after"] == 9
    assert scenario["demo_rank_equal_ef"] <= 5
    assert scenario["demo_rank_proxy_ef"] <= 5
    assert scenario["mean_s_after"] > scenario["mean_s_before"]
    text = (REPO / "seed" / "demo" / "candidate.pdf").read_bytes()
    assert text.startswith(b"%PDF")


def test_pdf_has_text_layer() -> None:
    import pymupdf

    doc = pymupdf.open(REPO / "seed" / "demo" / "candidate.pdf")
    extracted = " ".join(page.get_text() for page in doc)
    doc.close()
    assert "Алексей Кузнецов" in extracted
    assert "антифрод-событий в Kafka" in extracted
    assert "PostgreSQL" in extracted


def test_gold_follows_rubric_not_formula() -> None:
    import catalog
    from eval.label import relevance

    candidates = {row["id"]: row for row in _json(REPO / "seed" / "data" / "candidates.json")}
    needs = {row["id"]: row for row in _json(REPO / "seed" / "data" / "needs.json")}
    rows = [json.loads(line) for line in (REPO / "eval" / "gold.jsonl").read_text(encoding="utf-8").splitlines() if line]
    by_need: dict[str, int] = {}
    for row in rows:
        again = relevance(candidates[row["candidate_id"]], needs[row["need_id"]], catalog.ADJACENT, catalog.SKILL_NAMES)
        assert again == row["relevance"]
        by_need[row["need_id"]] = by_need.get(row["need_id"], 0) + 1
    assert len(by_need) == 10
    assert set(by_need.values()) == {30}


def test_ndcg_identity() -> None:
    from eval.metrics import ndcg_at_k

    assert ndcg_at_k([3, 2, 1, 0]) == pytest.approx(1)
    assert ndcg_at_k([0, 1, 2, 3]) < 0.9


def test_loader_does_not_import_foreign_models() -> None:
    forbidden = {
        "app.profile.models",
        "app.company.models",
        "app.need.models",
        "app.invitation.models",
        "app.resume.models",
        "app.assessment.models",
        "app.chat.models",
        "app.matching.config",
    }
    demo = REPO / "services" / "api" / "app" / "demo"
    for path in demo.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
        assert forbidden.isdisjoint(modules), path.name


@pytest.mark.asyncio
async def test_eval_run_flags_stub_score_pair() -> None:
    from eval.run import evaluate

    result = await evaluate()
    assert result["stub"] is True
    assert "не осмыслен" in result["note"]
    assert 0 <= result["macro_formula"] <= 1
    assert 0 <= result["macro_baseline"] <= 1
    assert len(result["rows"]) == 10
