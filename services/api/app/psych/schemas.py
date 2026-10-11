from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PsychItem(BaseModel):
    key: str
    text: str


class PsychBlock(BaseModel):
    id: int
    items: list[PsychItem]


class PsychStatement(BaseModel):
    id: int
    text: str


class PsychLikert(BaseModel):
    value: int
    label: str


class PsychCase(BaseModel):
    id: int
    text: str
    options: list[PsychItem]


class PsychPart(BaseModel):
    id: int
    title: str
    meta: str
    hint: str


class PsychTest(BaseModel):
    """Публичная часть теста. Ключ подсчёта в ответ не входит."""

    version: str
    title: str
    subtitle: str
    instruction: str
    parts: list[PsychPart]
    blocks: list[PsychBlock]
    statements: list[PsychStatement]
    likert: list[PsychLikert]
    cases: list[PsychCase]


class PsychAnswers(BaseModel):
    """disc: {"1": {"most": "а", "least": "г"}}, statements: {"1": 4}, cases: {"1": "в"}."""

    disc: dict[str, dict[str, str]] = Field(default_factory=dict)
    statements: dict[str, int] = Field(default_factory=dict)
    cases: dict[str, str] = Field(default_factory=dict)


class PsychProgress(BaseModel):
    blocks_done: int
    blocks_total: int
    statements_done: int
    statements_total: int
    cases_done: int
    cases_total: int


class PsychAttemptOut(BaseModel):
    id: UUID
    version: str
    answers: PsychAnswers
    progress: PsychProgress
    started_at: datetime
    finished_at: datetime | None = None


class PsychFinishIn(BaseModel):
    answers: PsychAnswers | None = None
    share_with_employers: bool | None = None


class PsychState(BaseModel):
    """Состояние для кабинета кандидата: черновик, последний результат и право пересдачи."""

    attempt: PsychAttemptOut | None = None
    result: dict[str, Any] | None = None
    finished_at: datetime | None = None
    can_start: bool = True
    next_attempt_at: datetime | None = None
    share_with_employers: bool = False
    limitations: list[str] = Field(default_factory=list)


class PsychShareIn(BaseModel):
    share_with_employers: bool


class PsychEmployerView(BaseModel):
    """Результат для работодателя. available=False — кандидат не прошёл тест или не открыл его."""

    available: bool
    reason: str | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    limitations: list[str] = Field(default_factory=list)
