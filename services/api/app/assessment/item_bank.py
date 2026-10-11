"""Playable CAT items: concrete instances (tmp_bank/instances.json) on top of bank.json templates."""

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
}
BANK_TO_PLATFORM = {bank: platform for platform, bank in PLATFORM_TO_BANK.items()}
SUPPORTED = frozenset(PLATFORM_TO_BANK)

# Bank tags are fine-grained (≈45 per specialization, mostly one item each), so a per-tag score
# is just 0/50/100. Scores are reported on taxonomy skills instead, each backed by several items.
_SKILL_GROUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "backend": {
        "python": (
            "python", "python.basics", "python.collections", "python.oop", "python.asyncio", "concurrency",
        ),
        "sql": ("sql", "sql.select", "sql.null", "sql.join", "sql.aggregate", "sql.window", "orm"),
        "postgresql": ("db.indexes", "db.performance", "db.transactions", "db.isolation", "миграции бд"),
        "http": ("http", "http.status", "api.rest"),
        "git": ("git",),
        "algorithms": ("algorithms.ds", "сложность алгоритмов"),
        "system_design": (
            "system.design", "system.scaling", "system.caching", "кэширование", "system.messaging", "очереди",
            "system.consistency", "консистентность", "system.distributed", "saga", "шардирование",
            "architecture", "resilience",
        ),
        "security": ("security.basics", "аутентификация"),
        "debugging": ("debugging", "code_review", "observability", "incident"),
    },
    "frontend": {
        "javascript": (
            "js.types", "js.basics", "js.arrays", "js.strings", "js.async", "js.eventloop", "js.closures",
            "js.timers", "области видимости", "this", "прототипы", "algorithms",
        ),
        "typescript": ("ts.generics", "ts.types"),
        "react": (
            "react", "react.state", "react.basics", "react.hooks", "react.performance", "react.advanced",
            "гидратация",
        ),
        "css": ("css.cascade", "css.selectors", "box model", "flexbox"),
        "html": ("html.semantics", "a11y", "forms"),
        "web_performance": (
            "fe.performance", "web.vitals", "js.memory", "рендеринг", "браузерный конвейер", "http и браузер",
        ),
        "security": ("security.xss", "security.csrf", "web.csp"),
        "fe_architecture": ("fe.architecture", "design_system", "system.design", "микрофронтенды", "сборка"),
        "debugging": ("debugging", "code_review"),
    },
}
_SKILL_OF: dict[str, dict[str, str]] = {
    spec: {tag: skill for skill, tags in groups.items() for tag in tags} for spec, groups in _SKILL_GROUPS.items()
}


def skills_of(item: PlayableItem) -> tuple[str, ...]:
    mapping = _SKILL_OF.get(item.specialization, {})
    found = dict.fromkeys(mapping.get(tag, tag) for tag in item.tags)
    return tuple(found) or (item.specialization,)

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9_./+-]{2,}")
_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_TEMPLATE_KEYS = ("templates", "theory_templates", "extension_templates")


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
    snippet: str
    placeholder: str
    options: tuple[dict[str, str], ...] | None
    correct: tuple[str, ...]
    multiple: bool
    accept: tuple[str, ...]
    keys: tuple[tuple[str, ...], ...]
    need: int
    answer_text: str
    languages: tuple[str, ...]
    kind: str
    difficulty: int
    source: str

    def row(self) -> dict[str, object]:
        body = f"{self.body}\n\n{self.snippet}" if self.snippet else self.body
        return {
            "id": self.id,
            "specialization": self.specialization,
            "kind": self.kind,
            "skills": list(skills_of(self)),
            "difficulty": self.difficulty,
            "body": body,
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


def instances_path() -> Path | None:
    override = os.environ.get("ASSESSMENT_INSTANCES")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    bank = bank_path()
    if bank is None:
        return None
    path = bank.with_name("instances.json")
    return path if path.is_file() else None


def available() -> bool:
    return bank_path() is not None and instances_path() is not None


@lru_cache(maxsize=1)
def load_bank() -> dict[str, object]:
    path = bank_path()
    if path is None:
        raise FileNotFoundError("bank.json is not available")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_instances() -> dict[str, object]:
    path = instances_path()
    if path is None:
        raise FileNotFoundError("instances.json is not available")
    return json.loads(path.read_text(encoding="utf-8"))


def _as_list(raw: object) -> list[object]:
    return list(raw) if isinstance(raw, list) else []


def _as_float(raw: object, default: float = 0.0) -> float:
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int | float):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return default
    return default


def _as_int(raw: object, default: int) -> int:
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return default


def _strings(raw: object) -> tuple[str, ...]:
    return tuple(str(item) for item in _as_list(raw) if str(item).strip())


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


def _default_languages(fmt: str, spec: str) -> tuple[str, ...]:
    if fmt != "CODE":
        return ()
    return ("javascript", "typescript") if spec == "Frontend" else ("python",)


def _templates() -> dict[str, dict[str, object]]:
    bank = load_bank()
    rows: dict[str, dict[str, object]] = {}
    for key in _TEMPLATE_KEYS:
        for raw in _as_list(bank.get(key)):
            if isinstance(raw, dict) and raw.get("id") and str(raw["id"]) not in rows:
                rows[str(raw["id"])] = raw
    return rows


def _from_instance(raw: dict[str, object], template: dict[str, object]) -> PlayableItem:
    spec = str(template["spec"])
    fmt = str(raw.get("format") or template.get("format") or "SHORT").upper()
    labels = _strings(raw.get("options"))
    options = tuple({"id": chr(97 + index), "text": text} for index, text in enumerate(labels)) or None
    correct = tuple(
        chr(97 + int(index))
        for index in _as_list(raw.get("correct"))
        if isinstance(index, int) and 0 <= index < len(labels)
    )
    keys = tuple(tuple(_strings(group)) for group in _as_list(raw.get("keys")) if _strings(group))
    b = _as_float(template.get("b"))
    return PlayableItem(
        id=str(raw["id"]),
        spec=spec,
        specialization=BANK_TO_PLATFORM[spec],
        grade=str(template.get("grade") or "Junior").lower(),
        format=fmt,
        title=str(raw.get("title") or template.get("title") or template.get("topic") or raw["id"]),
        tags=_strings(template.get("tags")) or (str(template.get("topic") or spec).split(":")[0].strip().lower(),),
        a=_as_float(template.get("a"), 1.0),
        b=b,
        time=_as_int(raw.get("time"), _as_int(template.get("time"), 3)),
        body=str(raw.get("prompt") or "").strip(),
        snippet=str(raw.get("code") or "").rstrip(),
        placeholder=str(raw.get("placeholder") or ""),
        options=options,
        correct=correct,
        multiple=fmt == "MSQ" or len(correct) > 1,
        accept=_strings(raw.get("accept")),
        keys=keys,
        need=max(1, min(_as_int(raw.get("need"), len(keys) or 1), len(keys) or 1)),
        answer_text=str(raw.get("answer") or template.get("example_answer") or ""),
        languages=_strings(raw.get("languages")) or _default_languages(fmt, spec),
        kind="mcq" if options else "code",
        difficulty=_difficulty(b),
        source="theory" if str(raw["id"]).split("-")[1] == "T" else "detailed",
    )


@lru_cache(maxsize=1)
def all_items() -> tuple[PlayableItem, ...]:
    templates = _templates()
    items: list[PlayableItem] = []
    seen: set[str] = set()
    for raw in _as_list(load_instances().get("items")):
        if not isinstance(raw, dict) or not raw.get("id") or str(raw["id"]) in seen:
            continue
        template = templates.get(str(raw["id"]))
        if template is None or str(template.get("spec")) not in BANK_TO_PLATFORM:
            continue
        item = _from_instance(raw, template)
        if not item.body or (item.options and not item.correct):
            continue
        seen.add(item.id)
        items.append(item)
    return tuple(items)


def items_for(specialization: str) -> tuple[PlayableItem, ...]:
    spec = PLATFORM_TO_BANK.get(specialization)
    if spec is None:
        return ()
    return tuple(item for item in all_items() if item.spec == spec)


def item_by_id(task_id: str) -> PlayableItem | None:
    for item in all_items():
        if item.id == task_id:
            return item
    return None


def micro_tasks() -> list[dict[str, str]]:
    if bank_path() is None:
        return []
    rows: list[dict[str, str]] = []
    for raw in _as_list(load_bank().get("micro_tasks")):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        spec = str(raw.get("spec") or "")
        if not text or spec not in BANK_TO_PLATFORM:
            continue
        kind = str(raw.get("kind") or "Задание")
        rows.append({"id": str(raw.get("id") or ""), "title": f"{spec}: {kind}", "body": text, "spec": spec})
    return rows


def vacancies() -> list[dict[str, object]]:
    if bank_path() is None:
        return []
    rows: list[dict[str, object]] = []
    for raw in _as_list(load_bank().get("vacancies")):
        if isinstance(raw, dict):
            rows.append(raw)
    return rows


def _tokens(text: str) -> set[str]:
    return {item.lower() for item in _TOKEN_RE.findall(text)}


def overlap(answer: str, reference: str) -> float:
    left = _tokens(answer)
    right = _tokens(reference)
    if not left or not right:
        return 0.0
    return len(left & right) / len(right)


def _norm(text: str) -> str:
    low = text.lower().replace("ё", "е")
    low = re.sub(r"[\"'`«»]", "", low)
    low = re.sub(r"[\s,;]+", " ", low)
    return low.strip(" .")


def _squash(text: str) -> str:
    return re.sub(r"[^0-9a-zа-я]", "", _norm(text))


def _short_hit(item: PlayableItem, text: str) -> bool:
    got = _norm(text)
    for accepted in item.accept:
        want = _norm(accepted)
        if got == want or _squash(got) == _squash(want):
            return True
        if _NUMBER_RE.fullmatch(want):
            first = _NUMBER_RE.search(got)
            if first and first.group(0).replace(",", ".") == want.replace(",", "."):
                return True
    return False


def score_response(item: PlayableItem, *, answer: str | None, code: str | None, skipped: bool) -> float:
    if skipped:
        return 0.0
    text = (answer or code or "").strip()
    if not text:
        return 0.0
    if item.options:
        chosen = {part for part in re.split(r"[,;\s]+", text) if part}
        truth = set(item.correct)
        if not item.multiple:
            return 1.0 if chosen == truth else 0.0
        hit = len(chosen & truth)
        wrong = len(chosen - truth)
        return max(0.0, (hit - wrong) / len(truth))
    if item.accept:
        return 1.0 if _short_hit(item, text) else 0.0
    if item.keys:
        low = text.lower().replace("ё", "е")
        hits = sum(1 for group in item.keys if any(key.lower().replace("ё", "е") in low for key in group))
        return round(min(1.0, hits / item.need), 4)
    return overlap(text, item.answer_text)


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
