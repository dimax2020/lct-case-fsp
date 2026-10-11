from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import Grade, Specialization, TaskKind, Verdict


class AttemptCreate(BaseModel):
    specialization: Specialization
    declared_grade: Grade


class PublicTest(BaseModel):
    stdin: str
    expected: str


class TaskOption(BaseModel):
    id: str
    text: str


class TaskPublic(BaseModel):
    id: str
    kind: TaskKind
    skills: list[str]
    difficulty: int
    body: str
    options: list[TaskOption] | None = None
    tests_public: list[PublicTest] | None = None
    languages: list[str] = Field(default_factory=list)
    title: str | None = None
    format: str | None = None
    time_minutes: int | None = None
    tags: list[str] = Field(default_factory=list)
    multiple: bool = False


class AttemptProgress(BaseModel):
    current: int
    total: int
    answered: int
    skipped: int


class SkillScore(BaseModel):
    skill_id: str
    score: float


class AttemptResult(BaseModel):
    score: float
    grade: Grade
    ready_for_next: bool
    skill_scores: list[SkillScore]
    rank: int | None = None
    category_size: int | None = None
    theta: float | None = None
    se: float | None = None
    decision: str | None = None
    measured_grade: Grade | None = None
    percentile: float | None = None
    message: str | None = None


class AttemptView(BaseModel):
    id: UUID
    specialization: Specialization
    declared_grade: Grade
    started_at: datetime
    deadline_at: datetime
    finished_at: datetime | None = None
    remaining_seconds: int
    progress: AttemptProgress
    task: TaskPublic | None = None
    result: AttemptResult | None = None
    engine: str = "yaml"
    theta: float | None = None
    se: float | None = None
    decision: str | None = None
    measured_grade: Grade | None = None
    percentile: float | None = None
    message: str | None = None


class AnswerIn(BaseModel):
    task_id: str
    answer: str | None = None
    code: str | None = None
    language: str | None = None
    skip: bool = False


class RunIn(BaseModel):
    task_id: str
    code: str = Field(min_length=1)
    language: str


class RunOut(BaseModel):
    verdict: Verdict
    passed: int
    total: int
    stdout: str = ""
    stderr: str = ""


class DemoFinishIn(BaseModel):
    score: float = Field(ge=0, le=100)
    skill_scores: list[SkillScore] = Field(default_factory=list)
    grade: Grade | None = None


class RetakeIn(BaseModel):
    direction: Literal["up", "down"]


class EligibilityOut(BaseModel):
    can_start: bool
    reason: str | None = None
    active_attempt_id: UUID | None = None
    retry_at: datetime | None = None
    grade_change_at: datetime | None = None
    message: str | None = None


class BlueprintSample(BaseModel):
    id: str
    title: str
    format: str
    tags: list[str]


class BlueprintOut(BaseModel):
    specialization: str
    grade: str | None = None
    theory: int
    practice: int
    debug: int
    case: int
    skills: list[str]
    sample: list[BlueprintSample]
    note: str | None = None


class MicroTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    need_id: UUID | None = None


class MicroTaskOut(BaseModel):
    id: UUID
    title: str
    body: str
    need_id: UUID | None = None


class MicroAnswerIn(BaseModel):
    answer: str = Field(min_length=20)


class MicroAnswerOut(BaseModel):
    id: UUID
    task_id: UUID
    answer: str


class RoadmapCreate(BaseModel):
    specialization: Literal["backend", "frontend"]
    declared_grade: Grade


class RoadmapCheckIn(BaseModel):
    id: str
    value: Literal["yes", "no", "unknown"]


class RoadmapChecksIn(BaseModel):
    answers: list[RoadmapCheckIn] = Field(min_length=1)


class RoadmapConcreteIn(BaseModel):
    answer: str = Field(min_length=10, max_length=2000)


class RoadmapCheckOut(BaseModel):
    id: str
    text: str


class RoadmapNode(BaseModel):
    id: str
    label: str
    title: str
    status: Literal["held", "review", "current", "ahead", "aside"]
    order: int | None = None


class RoadmapGap(BaseModel):
    label: str
    title: str
    items: list[str]


class RoadmapResultOut(BaseModel):
    measured_grade: Grade
    outcome: Literal["up", "down", "same"]
    cooldown_days: int
    locked_until: datetime
    message: str
    score: float


class RoadmapView(BaseModel):
    id: UUID
    specialization: Literal["backend", "frontend"]
    declared_grade: Grade
    step: int
    total: int
    phase: Literal["checks", "concrete", "done"]
    title: str | None = None
    prompt: str | None = None
    checks: list[RoadmapCheckOut] = Field(default_factory=list)
    saved_checks: dict[str, Literal["yes", "no", "unknown"]] = Field(default_factory=dict)
    concrete_question: str | None = None
    result: RoadmapResultOut | None = None
    nodes: list[RoadmapNode] = Field(default_factory=list)
    review: list[RoadmapGap] = Field(default_factory=list)


class RoadmapLatest(BaseModel):
    finished: bool
    open: bool
    measured_grade: Grade | None = None
    outcome: Literal["up", "down", "same"] | None = None
    locked_until: datetime | None = None
    message: str | None = None
    nodes: list[RoadmapNode] = Field(default_factory=list)
    review: list[RoadmapGap] = Field(default_factory=list)
