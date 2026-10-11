from datetime import datetime
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
