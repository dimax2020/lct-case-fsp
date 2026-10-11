from typing import Any

from pydantic import BaseModel, Field


class CandidateHint(BaseModel):
    id: str
    type: str
    title: str
    effect_text: str
    action_label: str
    action_href: str
    priority: float


class HintApply(BaseModel):
    kind: str
    filter: dict[str, Any] | None = None
    patch: dict[str, Any] | None = None


class EmployerHint(BaseModel):
    id: str
    type: str
    title: str
    before: int | None = None
    after: int | None = None
    avg_before: float | None = None
    avg_after: float | None = None
    apply: HintApply | None = None


class HintList(BaseModel):
    items: list[CandidateHint] | list[EmployerHint] = Field(default_factory=list)
