"""Load seed/tasks YAML into tasks_bank."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import TaskBank

SPECIALIZATIONS = ("backend", "frontend", "data_ml", "devops")
TASKS_PER_SPEC = 12
MCQ_PER_SPEC = 9
CODE_PER_SPEC = 3


@dataclass(frozen=True)
class TaskSpec:
    id: str
    specialization: str
    kind: str
    skills: tuple[str, ...]
    difficulty: int
    body: str
    options: tuple[dict[str, str], ...] | None
    answer: str | None
    tests_public: tuple[dict[str, str], ...] | None
    tests_hidden: tuple[dict[str, str], ...] | None
    languages: tuple[str, ...]
    solutions: dict[str, str]

    def row(self) -> dict[str, object]:
        return {
            "id": self.id,
            "specialization": self.specialization,
            "kind": self.kind,
            "skills": list(self.skills),
            "difficulty": self.difficulty,
            "body": self.body,
            "options": [dict(item) for item in self.options] if self.options else None,
            "answer": self.answer,
            "tests_public": [dict(item) for item in self.tests_public] if self.tests_public else None,
            "tests_hidden": [dict(item) for item in self.tests_hidden] if self.tests_hidden else None,
            "languages": list(self.languages),
        }


def tasks_directory() -> Path:
    override = os.environ.get("SEED_TASKS_DIR")
    if override:
        return Path(override)
    docker = Path("/srv/seed/tasks")
    if (docker / "backend.yaml").is_file():
        return docker
    here = Path(__file__).resolve()
    if len(here.parents) > 4:
        repo = here.parents[4] / "seed" / "tasks"
        if (repo / "backend.yaml").is_file():
            return repo
    return docker


def _skills_file() -> Path | None:
    candidates = [Path("/srv/taxonomy/data/skills.yaml"), Path.cwd() / "taxonomy" / "data" / "skills.yaml"]
    here = Path(__file__).resolve()
    if len(here.parents) > 4:
        candidates.insert(0, here.parents[4] / "taxonomy" / "data" / "skills.yaml")
    for path in candidates:
        if path.is_file():
            return path
    return None


def known_skill_ids() -> set[str] | None:
    path = _skills_file()
    if path is None:
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(document, list):
        return set()
    return {str(item["id"]) for item in document if isinstance(item, dict) and item.get("id")}


def _as_cases(raw: object, task_id: str, field: str) -> tuple[dict[str, str], ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{task_id}: {field} must be a non-empty list")
    cases: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or "stdin" not in item or "expected" not in item:
            raise ValueError(f"{task_id}: {field}[{index}] needs stdin and expected")
        cases.append({"stdin": str(item["stdin"]), "expected": str(item["expected"])})
    return tuple(cases)


def _parse_task(raw: object, specialization: str) -> TaskSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"{specialization}: task entry must be a mapping")
    task_id = str(raw.get("id") or "")
    if not task_id or len(task_id) > 64:
        raise ValueError(f"{specialization}: task id must be 1..64 characters")
    if raw.get("specialization") != specialization:
        raise ValueError(f"{task_id}: specialization must be {specialization}")
    kind = str(raw.get("kind") or "")
    if kind not in {"mcq", "code"}:
        raise ValueError(f"{task_id}: kind must be mcq or code")
    skills_raw = raw.get("skills")
    if not isinstance(skills_raw, list) or not skills_raw:
        raise ValueError(f"{task_id}: skills must be a non-empty list")
    skills = tuple(str(item) for item in skills_raw)
    try:
        difficulty = int(raw["difficulty"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{task_id}: difficulty must be an integer 1..5") from exc
    if difficulty < 1 or difficulty > 5:
        raise ValueError(f"{task_id}: difficulty must be 1..5")
    body = raw.get("body")
    if not isinstance(body, str) or not body.strip():
        raise ValueError(f"{task_id}: body is required")
    options: tuple[dict[str, str], ...] | None = None
    answer: str | None = None
    tests_public: tuple[dict[str, str], ...] | None = None
    tests_hidden: tuple[dict[str, str], ...] | None = None
    languages_raw = raw.get("languages") or []
    if not isinstance(languages_raw, list):
        raise ValueError(f"{task_id}: languages must be a list")
    languages = tuple(str(item) for item in languages_raw)
    solutions_raw = raw.get("solutions") or {}
    if not isinstance(solutions_raw, dict):
        raise ValueError(f"{task_id}: solutions must be a mapping")
    solutions = {str(key): str(value) for key, value in solutions_raw.items()}
    if kind == "mcq":
        option_rows = raw.get("options")
        if not isinstance(option_rows, list) or len(option_rows) < 2:
            raise ValueError(f"{task_id}: mcq needs at least two options")
        parsed: list[dict[str, str]] = []
        for index, item in enumerate(option_rows):
            if not isinstance(item, dict) or not item.get("id") or not item.get("text"):
                raise ValueError(f"{task_id}: options[{index}] needs id and text")
            parsed.append({"id": str(item["id"]), "text": str(item["text"])})
        options = tuple(parsed)
        answer = str(raw.get("answer") or "")
        if answer not in {item["id"] for item in parsed}:
            raise ValueError(f"{task_id}: answer must match an option id")
        if languages:
            raise ValueError(f"{task_id}: mcq languages must be empty")
    else:
        tests_public = _as_cases(raw.get("tests_public"), task_id, "tests_public")
        tests_hidden = _as_cases(raw.get("tests_hidden"), task_id, "tests_hidden")
        if tuple(languages) != ("python", "go"):
            raise ValueError(f"{task_id}: code languages must be python and go")
        for language in ("python", "go"):
            if not solutions.get(language, "").strip():
                raise ValueError(f"{task_id}: missing {language} reference solution")
    return TaskSpec(
        id=task_id,
        specialization=specialization,
        kind=kind,
        skills=skills,
        difficulty=difficulty,
        body=body.strip(),
        options=options,
        answer=answer,
        tests_public=tests_public,
        tests_hidden=tests_hidden,
        languages=languages,
        solutions=solutions,
    )


def read_task_specs() -> list[TaskSpec]:
    directory = tasks_directory()
    catalog = known_skill_ids()
    specs: list[TaskSpec] = []
    seen: set[str] = set()
    for specialization in SPECIALIZATIONS:
        path = directory / f"{specialization}.yaml"
        if not path.is_file():
            raise ValueError(f"missing task bank file: {path}")
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        if not isinstance(document, list):
            raise ValueError(f"{path.name}: document must be a list")
        parsed = [_parse_task(item, specialization) for item in document]
        if len(parsed) != TASKS_PER_SPEC:
            raise ValueError(f"{specialization}: expected {TASKS_PER_SPEC} tasks, got {len(parsed)}")
        mcq = sum(1 for item in parsed if item.kind == "mcq")
        code = sum(1 for item in parsed if item.kind == "code")
        if mcq != MCQ_PER_SPEC or code != CODE_PER_SPEC:
            raise ValueError(f"{specialization}: expected {MCQ_PER_SPEC} mcq and {CODE_PER_SPEC} code tasks")
        for item in parsed:
            if item.id in seen:
                raise ValueError(f"duplicate task id: {item.id}")
            seen.add(item.id)
            if catalog is not None:
                unknown = [skill for skill in item.skills if skill not in catalog]
                if unknown:
                    raise ValueError(f"{item.id}: unknown skill ids {unknown}")
        specs.extend(parsed)
    return specs


def task_by_id(task_id: str) -> TaskSpec | None:
    for spec in read_task_specs():
        if spec.id == task_id:
            return spec
    return None


async def load_tasks(session: AsyncSession) -> int:
    """Read seed YAML and upsert it into tasks_bank. Reference solutions stay out of the table."""
    specs = read_task_specs()
    existing = {row.id: row for row in (await session.scalars(select(TaskBank))).all()}
    for spec in specs:
        payload = spec.row()
        current = existing.get(spec.id)
        if current is None:
            session.add(TaskBank(**payload))
            continue
        for key, value in payload.items():
            setattr(current, key, value)
    await session.flush()
    return len(specs)
