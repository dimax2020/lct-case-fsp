"""Load tmp_bank/bank.json and turn templates into playable CAT items."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import TaskBank

PLATFORM_TO_BANK = {
    "backend": "Backend",
    "frontend": "Frontend",
    "devops": "DevOps",
    "data_ml": "QA",
}
BANK_TO_PLATFORM = {bank: platform for platform, bank in PLATFORM_TO_BANK.items()}

_OPTIONS_RE = re.compile(r"Варианты:\s*(.+)$", re.IGNORECASE | re.DOTALL)
_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9_./+-]{2,}")
_BRACE_RE = re.compile(r"\{([^{}]+)\}")


@dataclass(frozen=True)
class PlayableItem:
    id: str
    spec: str
    specialization: str
    grade: str
    format: str
    title: str
    tags: tuple[str, ...]
    a: float
    b: float
    time: int
    body: str
    options: tuple[dict[str, str], ...] | None
    correct: tuple[str, ...]
    answer_text: str
    languages: tuple[str, ...]
    kind: str
    difficulty: int
    source: str
    rubric: str

    def row(self) -> dict[str, object]:
        return {
            "id": self.id,
            "specialization": self.specialization,
            "kind": self.kind,
            "skills": list(self.tags) or [self.specialization],
            "difficulty": self.difficulty,
            "body": self.body,
            "options": [dict(item) for item in self.options] if self.options else None,
            "answer": ",".join(self.correct) if self.correct else self.answer_text,
            "tests_public": None,
            "tests_hidden": None,
            "languages": list(self.languages),
        }


def bank_path() -> Path | None:
    override = os.environ.get("ASSESSMENT_BANK")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    here = Path(__file__).resolve()
    candidates = [
        Path("/srv/assessment/bank.json"),
        here.parents[4] / "tmp_bank" / "bank.json" if len(here.parents) > 4 else Path(),
        Path.cwd() / "tmp_bank" / "bank.json",
        here.parents[2] / "data" / "bank.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def available() -> bool:
    return bank_path() is not None


@lru_cache(maxsize=1)
def load_bank() -> dict[str, object]:
    path = bank_path()
    if path is None:
        raise FileNotFoundError("bank.json is not available")
    return json.loads(path.read_text(encoding="utf-8"))


def _fill(text: str) -> str:
    return _BRACE_RE.sub(lambda match: match.group(1).split("/")[0].strip(), text)


def _difficulty(b: float) -> int:
    if b < -1.2:
        return 1
    if b < -0.2:
        return 2
    if b < 0.6:
        return 3
    if b < 1.4:
        return 4
    return 5


def _kind(fmt: str) -> str:
    return "mcq" if fmt in {"MCQ", "MSQ"} else "code"


def _languages(fmt: str, spec: str) -> tuple[str, ...]:
    if fmt != "CODE":
        return ()
    if spec == "Frontend":
        return ("javascript", "python")
    return ("python",)


def _split_options(raw: str) -> list[str]:
    chunk = raw.strip().rstrip(".")
    parts = re.split(r"\s*/\s*|;\s+", chunk)
    return [item.strip(" .;") for item in parts if item.strip(" .;")]


def _parse_options(example: str) -> list[dict[str, str]] | None:
    match = _OPTIONS_RE.search(example)
    if match is None:
        return None
    parts = _split_options(match.group(1))
    if len(parts) < 2:
        return None
    return [{"id": chr(97 + index), "text": text} for index, text in enumerate(parts)]


def _correct_ids(options: list[dict[str, str]], answer: str) -> list[str]:
    lowered = answer.lower()
    hits: list[str] = []
    for option in options:
        text = option["text"].lower()
        token = text.split()[0] if text.split() else text
        if text and (text in lowered or (len(token) >= 2 and token in lowered)):
            hits.append(option["id"])
    return hits


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in _TOKEN_RE.findall(text)}


def overlap(answer: str, reference: str) -> float:
    left = _tokens(answer)
    right = _tokens(reference)
    if not left or not right:
        return 0.0
    return len(left & right) / len(right)


def _from_detailed(raw: dict[str, object]) -> PlayableItem:
    fmt = str(raw.get("format") or "SHORT").upper()
    example = str(raw.get("example") or "").strip()
    statement = _fill(str(raw.get("statement") or "").strip())
    body = example or statement
    title = str(raw.get("title") or raw["id"])
    options = _parse_options(example) if example else None
    answer_text = str(raw.get("example_answer") or raw.get("answer") or "").strip()
    correct = tuple(_correct_ids(options, answer_text)) if options else ()
    if options and not correct and fmt == "MCQ":
        options = None
    tags = tuple(str(item) for item in (raw.get("tags") or []) if item)
    spec = str(raw["spec"])
    return PlayableItem(
        id=str(raw["id"]),
        spec=spec,
        specialization=BANK_TO_PLATFORM.get(spec, "backend"),
        grade=str(raw.get("grade") or "Junior").lower(),
        format=fmt,
        title=title,
        tags=tags,
        a=float(raw["a"]),
        b=float(raw["b"]),
        time=int(raw.get("time") or 5),
        body=body,
        options=tuple(options) if options else None,
        correct=correct,
        answer_text=answer_text,
        languages=_languages(fmt, spec),
        kind=_kind(fmt),
        difficulty=_difficulty(float(raw["b"])),
        source="detailed",
        rubric=str(raw.get("rubric") or raw.get("scoring") or ""),
    )


def _from_short(raw: dict[str, object], source: str) -> PlayableItem:
    fmt = str(raw.get("format") or "SHORT").upper()
    spec = str(raw["spec"])
    topic = str(raw.get("topic") or raw.get("title") or raw["id"])
    template = _fill(str(raw.get("template") or "").strip())
    params = str(raw.get("params") or "").strip()
    rule = str(raw.get("rule") or "").strip()
    body_parts = [topic]
    if template:
        body_parts.append(template)
    if params:
        body_parts.append(f"Параметры: {params}")
    body_parts.append("Ответьте кратко, по сути.")
    tags = tuple(str(item) for item in (raw.get("tags") or []) if item)
    if not tags and topic:
        tags = (topic.split(":")[0].strip().lower().replace(" ", "."),)
    return PlayableItem(
        id=str(raw["id"]),
        spec=spec,
        specialization=BANK_TO_PLATFORM.get(spec, "backend"),
        grade=str(raw.get("grade") or "Junior").lower(),
        format=fmt if fmt != "MCQ" else "SHORT",
        title=topic,
        tags=tags,
        a=float(raw["a"]),
        b=float(raw["b"]),
        time=int(raw.get("time") or 3),
        body="\n\n".join(body_parts),
        options=None,
        correct=(),
        answer_text=rule or topic,
        languages=_languages(fmt, spec),
        kind="code",
        difficulty=_difficulty(float(raw["b"])),
        source=source,
        rubric=rule,
    )


@lru_cache(maxsize=1)
def all_items() -> tuple[PlayableItem, ...]:
    bank = load_bank()
    items: list[PlayableItem] = []
    seen: set[str] = set()
    for raw in bank.get("templates") or []:
        if not isinstance(raw, dict) or raw.get("id") in seen:
            continue
        item = _from_detailed(raw)
        seen.add(item.id)
        items.append(item)
    for raw in bank.get("theory_templates") or []:
        if not isinstance(raw, dict) or raw.get("id") in seen:
            continue
        item = _from_short(raw, "theory")
        seen.add(item.id)
        items.append(item)
    for raw in bank.get("extension_templates") or []:
        if not isinstance(raw, dict) or raw.get("id") in seen:
            continue
        item = _from_short(raw, "extension")
        seen.add(item.id)
        items.append(item)
    return tuple(items)


def items_for(specialization: str) -> tuple[PlayableItem, ...]:
    spec = PLATFORM_TO_BANK.get(specialization, specialization)
    return tuple(item for item in all_items() if item.spec == spec)


def item_by_id(task_id: str) -> PlayableItem | None:
    for item in all_items():
        if item.id == task_id:
            return item
    return None


def micro_tasks() -> list[dict[str, str]]:
    if not available():
        return []
    rows: list[dict[str, str]] = []
    for raw in load_bank().get("micro_tasks") or []:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        spec = str(raw.get("spec") or "")
        kind = str(raw.get("kind") or "Задание")
        rows.append({"id": str(raw.get("id") or ""), "title": f"{spec}: {kind}", "body": text, "spec": spec})
    return rows


def vacancies() -> list[dict[str, object]]:
    if not available():
        return []
    rows: list[dict[str, object]] = []
    for raw in load_bank().get("vacancies") or []:
        if isinstance(raw, dict):
            rows.append(raw)
    return rows


def score_response(item: PlayableItem, *, answer: str | None, code: str | None, skipped: bool) -> float:
    if skipped:
        return 0.0
    text = (answer or code or "").strip()
    if not text:
        return 0.0
    if item.format == "MCQ" and item.correct:
        return 1.0 if text in item.correct else 0.0
    if item.format == "MSQ" and item.correct:
        chosen = {part.strip() for part in re.split(r"[,;\s]+", text) if part.strip()}
        truth = set(item.correct)
        hit = len(chosen & truth)
        false = len(chosen - truth)
        return max(0.0, (hit - false) / len(truth))
    reference = " ".join(part for part in (item.answer_text, item.rubric) if part)
    return overlap(text, reference)


async def upsert_items(session: AsyncSession, items: tuple[PlayableItem, ...]) -> int:
    existing = {row.id: row for row in (await session.scalars(select(TaskBank))).all()}
    for item in items:
        payload = item.row()
        current = existing.get(item.id)
        if current is None:
            session.add(TaskBank(**payload))
            continue
        for key, value in payload.items():
            setattr(current, key, value)
    await session.flush()
    return len(items)
