"""Grade attempts and run code through Piston."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment import piston
from app.assessment.bank import TaskSpec, load_tasks, read_task_specs, task_by_id
from app.assessment.models import Attempt, AttemptAnswer
from app.assessment.schemas import (
    AnswerIn,
    AttemptCreate,
    AttemptProgress,
    AttemptResult,
    AttemptView,
    DemoFinishIn,
    PublicTest,
    RunOut,
    SkillScore,
    TaskOption,
    TaskPublic,
)
from app.assessment.scoring import GradedAnswer, GradedTask, grade_for, score_attempt
from app.core.auth import Principal
from app.core.errors import AppError
from app.core.provision import provision_user
from app.core.settings import get_settings

ATTEMPT_MINUTES = 40


@dataclass
class RunResult:
    verdict: str
    passed: int
    total: int
    stdout: str = ""
    stderr: str = ""


def to_public(spec: TaskSpec) -> TaskPublic:
    options = [TaskOption(id=item["id"], text=item["text"]) for item in spec.options] if spec.options else None
    tests = None
    if spec.kind == "code" and spec.tests_public is not None:
        tests = [PublicTest(stdin=item["stdin"], expected=item["expected"]) for item in spec.tests_public]
    return TaskPublic(
        id=spec.id,
        kind=spec.kind,  # type: ignore[arg-type]
        skills=list(spec.skills),
        difficulty=spec.difficulty,
        body=spec.body,
        options=options,
        tests_public=tests,
        languages=list(spec.languages),
    )


def _pending(total: int) -> RunResult:
    return RunResult(verdict="PENDING", passed=0, total=total, stdout="", stderr="Проверка позже")


async def run_code(task_id: str, code: str, language: str, hidden: bool) -> RunResult:
    spec = task_by_id(task_id)
    if spec is None:
        raise AppError("task_not_found", "Задание не найдено", status_code=404)
    if spec.kind != "code":
        raise AppError("not_code_task", "Для этого задания нет запуска кода", status_code=400)
    normalized = piston.canonical_language(language)
    if normalized is None or normalized not in spec.languages:
        raise AppError("language_not_allowed", "Доступны только Python и Go", status_code=400)
    cases = list((spec.tests_hidden if hidden else spec.tests_public) or [])
    if not get_settings().piston_enabled:
        return _pending(len(cases))
    verdict = "OK"
    passed = 0
    stdouts: list[str] = []
    stderrs: list[str] = []
    for case in cases:
        payload = piston.build_payload(normalized, code, case["stdin"])
        try:
            raw = await piston.post_execute(payload)
        except Exception as exc:
            piston.log_piston_failure(exc)
            return _pending(len(cases))
        outcome = piston.interpret(raw)
        stdouts.append(outcome.stdout)
        stderrs.append(outcome.stderr)
        if outcome.problem:
            verdict = piston.worse(verdict, outcome.problem)
            continue
        if piston.normalize_output(outcome.stdout) == piston.normalize_output(case["expected"]):
            passed += 1
        else:
            verdict = piston.worse(verdict, "WRONG_ANSWER")
    return RunResult(
        verdict=verdict,
        passed=passed,
        total=len(cases),
        stdout=piston.clip(stdouts),
        stderr=piston.clip(stderrs),
    )


def _specs_for(specialization: str) -> list[TaskSpec]:
    return [spec for spec in read_task_specs() if spec.specialization == specialization]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _remaining(deadline: datetime, *, finished: bool) -> int:
    if finished:
        return 0
    seconds = int((_aware(deadline) - datetime.now(UTC)).total_seconds())
    return max(0, seconds)


def _select_current(specs: list[TaskSpec], answers: list[AttemptAnswer], *, finished: bool) -> TaskSpec | None:
    if finished:
        return None
    by_id = {item.task_id: item for item in answers}
    for spec in specs:
        if spec.id not in by_id:
            return spec
    skipped = [spec for spec in specs if by_id[spec.id].skipped]
    if not skipped:
        return None
    skipped.sort(key=lambda spec: _aware(by_id[spec.id].updated_at))
    return skipped[0]


def _progress(specs: list[TaskSpec], answers: list[AttemptAnswer], current: TaskSpec | None) -> AttemptProgress:
    answered = sum(1 for item in answers if not item.skipped)
    skipped = sum(1 for item in answers if item.skipped)
    if current is None:
        cursor = len(specs)
    else:
        cursor = next((index for index, spec in enumerate(specs, start=1) if spec.id == current.id), len(specs))
    return AttemptProgress(current=cursor, total=len(specs), answered=answered, skipped=skipped)


def _skill_models(scores: dict[str, float]) -> list[SkillScore]:
    return [SkillScore(skill_id=skill, score=value) for skill, value in sorted(scores.items())]


async def _candidate_id(session: AsyncSession, principal: Principal) -> UUID:
    user = await provision_user(session, principal)
    found = await session.execute(
        text("SELECT id FROM candidates WHERE user_id = CAST(:user_id AS uuid)"),
        {"user_id": str(user.id)},
    )
    existing = found.scalar_one_or_none()
    if existing is not None:
        return existing if isinstance(existing, UUID) else UUID(str(existing))
    new_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO candidates (
                id, user_id, full_name, formats, status, visible,
                liked_skills, disliked_skills, liked_domains, blocked_domains,
                hidden_company_ids, ready_for_next
            )
            VALUES (
                CAST(:id AS uuid), CAST(:user_id AS uuid), '', ARRAY[]::varchar[],
                'paused', true,
                ARRAY[]::varchar[], ARRAY[]::varchar[], ARRAY[]::varchar[], ARRAY[]::varchar[],
                ARRAY[]::uuid[], false
            )
            """
        ),
        {"id": str(new_id), "user_id": str(user.id)},
    )
    return new_id


async def _owned_attempt(session: AsyncSession, attempt_id: UUID, candidate_id: UUID) -> Attempt:
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None or attempt.candidate_id != candidate_id:
        raise AppError("not_found", "Попытка не найдена", status_code=404)
    return attempt


async def _answers(session: AsyncSession, attempt_id: UUID) -> list[AttemptAnswer]:
    rows = await session.scalars(select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt_id))
    return list(rows.all())


async def _rank_of(session: AsyncSession, candidate_id: UUID) -> tuple[int | None, int | None]:
    found = await session.execute(
        text("SELECT category_rank, category_size FROM candidates WHERE id = CAST(:id AS uuid)"),
        {"id": str(candidate_id)},
    )
    row = found.one()
    rank = int(row[0]) if row[0] is not None else None
    size = int(row[1]) if row[1] is not None else None
    return rank, size


def _result_from(attempt: Attempt, rank: int | None, size: int | None) -> AttemptResult:
    stored = attempt.skill_scores if isinstance(attempt.skill_scores, dict) else {}
    scores = {str(key): float(value) for key, value in stored.items()}
    return AttemptResult(
        score=float(attempt.score or 0),
        grade=attempt.result_grade,  # type: ignore[arg-type]
        ready_for_next=attempt.ready_for_next,
        skill_scores=_skill_models(scores),
        rank=rank,
        category_size=size,
    )


async def _view(session: AsyncSession, attempt: Attempt) -> AttemptView:
    specs = _specs_for(attempt.specialization)
    answers = await _answers(session, attempt.id)
    finished = attempt.finished_at is not None
    current = _select_current(specs, answers, finished=finished)
    result = None
    if finished:
        rank, size = await _rank_of(session, attempt.candidate_id)
        result = _result_from(attempt, rank, size)
    return AttemptView(
        id=attempt.id,
        specialization=attempt.specialization,  # type: ignore[arg-type]
        declared_grade=attempt.declared_grade,  # type: ignore[arg-type]
        started_at=attempt.started_at,
        deadline_at=attempt.deadline_at,
        finished_at=attempt.finished_at,
        remaining_seconds=_remaining(attempt.deadline_at, finished=finished),
        progress=_progress(specs, answers, current),
        task=to_public(current) if current else None,
        result=result,
    )


def _ensure_open(attempt: Attempt) -> None:
    if attempt.finished_at is not None:
        raise AppError("attempt_finished", "Попытка уже завершена", status_code=409)


def _ensure_deadline(attempt: Attempt) -> None:
    if datetime.now(UTC) > _aware(attempt.deadline_at):
        raise AppError("attempt_expired", "Время попытки истекло", status_code=409)


async def _rerank(session: AsyncSession, specialization: str, grade: str) -> None:
    await session.execute(
        text(
            """
            WITH ranked AS (
                SELECT id,
                       RANK() OVER (ORDER BY grade_score DESC NULLS LAST) AS rnk,
                       COUNT(*) OVER () AS sz
                FROM candidates
                WHERE specialization = :spec AND grade = :grade
            )
            UPDATE candidates AS c
            SET category_rank = ranked.rnk,
                category_size = ranked.sz
            FROM ranked
            WHERE c.id = ranked.id
            """
        ),
        {"spec": specialization, "grade": grade},
    )


async def _refresh_downstream(candidate_id: UUID) -> None:
    from app.hints.service import recompute_candidate
    from app.profile.service import get_candidate_features

    await get_candidate_features(candidate_id)
    await recompute_candidate(candidate_id)


async def _apply_result(
    session: AsyncSession,
    attempt: Attempt,
    *,
    score: float,
    grade: str,
    ready: bool,
    skill_scores: dict[str, float],
) -> AttemptResult:
    previous = await session.execute(
        text("SELECT specialization, grade FROM candidates WHERE id = CAST(:id AS uuid)"),
        {"id": str(attempt.candidate_id)},
    )
    old_spec, old_grade = previous.one()
    attempt.score = score
    attempt.skill_scores = skill_scores
    attempt.result_grade = grade
    attempt.ready_for_next = ready
    attempt.finished_at = datetime.now(UTC)
    await session.execute(
        text(
            """
            UPDATE candidates
            SET specialization = :spec,
                grade = :grade,
                grade_score = :score,
                ready_for_next = :ready
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {
            "spec": attempt.specialization,
            "grade": grade,
            "score": score,
            "ready": ready,
            "id": str(attempt.candidate_id),
        },
    )
    await session.execute(
        text("DELETE FROM candidate_skills WHERE candidate_id = CAST(:id AS uuid) AND source = 'test'"),
        {"id": str(attempt.candidate_id)},
    )
    for skill_id, skill_score in skill_scores.items():
        await session.execute(
            text(
                """
                INSERT INTO candidate_skills (id, candidate_id, skill_id, score, source)
                VALUES (CAST(:id AS uuid), CAST(:candidate_id AS uuid), :skill_id, :score, 'test')
                """
            ),
            {
                "id": str(uuid4()),
                "candidate_id": str(attempt.candidate_id),
                "skill_id": skill_id,
                "score": skill_score,
            },
        )
    categories = {(attempt.specialization, grade)}
    if old_spec and old_grade:
        categories.add((str(old_spec), str(old_grade)))
    for spec, grd in categories:
        await _rerank(session, spec, grd)
    await session.commit()
    rank, size = await _rank_of(session, attempt.candidate_id)
    await _refresh_downstream(attempt.candidate_id)
    return AttemptResult(
        score=score,
        grade=grade,  # type: ignore[arg-type]
        ready_for_next=ready,
        skill_scores=_skill_models(skill_scores),
        rank=rank,
        category_size=size,
    )


def _graded(specs: list[TaskSpec], answers: list[AttemptAnswer]) -> tuple[float, dict[str, float]]:
    tasks = [GradedTask(id=spec.id, kind=spec.kind, skills=spec.skills, answer=spec.answer) for spec in specs]
    graded = [
        GradedAnswer(
            task_id=item.task_id,
            answer=item.answer,
            skipped=item.skipped,
            verdict=item.verdict,
            passed=item.passed,
            total=item.total,
        )
        for item in answers
    ]
    return score_attempt(tasks, graded)


async def create_attempt(session: AsyncSession, principal: Principal, body: AttemptCreate) -> AttemptView:
    try:
        await load_tasks(session)
    except ValueError as exc:
        raise AppError("task_bank_invalid", str(exc), status_code=500) from exc
    candidate_id = await _candidate_id(session, principal)
    started = datetime.now(UTC)
    attempt = Attempt(
        candidate_id=candidate_id,
        specialization=body.specialization.value,
        declared_grade=body.declared_grade.value,
        started_at=started,
        deadline_at=started + timedelta(minutes=ATTEMPT_MINUTES),
    )
    session.add(attempt)
    await session.commit()
    return await _view(session, attempt)


async def get_attempt(session: AsyncSession, principal: Principal, attempt_id: UUID) -> AttemptView:
    candidate_id = await _candidate_id(session, principal)
    attempt = await _owned_attempt(session, attempt_id, candidate_id)
    return await _view(session, attempt)


async def save_answer(session: AsyncSession, principal: Principal, attempt_id: UUID, body: AnswerIn) -> AttemptView:
    candidate_id = await _candidate_id(session, principal)
    attempt = await _owned_attempt(session, attempt_id, candidate_id)
    _ensure_open(attempt)
    _ensure_deadline(attempt)
    spec = task_by_id(body.task_id)
    if spec is None or spec.specialization != attempt.specialization:
        raise AppError("task_not_found", "Задание не входит в эту попытку", status_code=404)
    existing = await session.scalar(
        select(AttemptAnswer).where(AttemptAnswer.attempt_id == attempt.id, AttemptAnswer.task_id == spec.id)
    )
    row = existing or AttemptAnswer(attempt_id=attempt.id, task_id=spec.id)
    now = datetime.now(UTC)
    if body.skip:
        row.skipped = True
        row.answer = None
        row.verdict = None
        row.passed = None
        row.total = None
    elif spec.kind == "mcq":
        if not body.answer:
            raise AppError("answer_required", "Выберите вариант ответа", status_code=400)
        row.skipped = False
        row.answer = body.answer
        row.code = None
        row.language = None
        correct = body.answer == spec.answer
        row.verdict = "OK" if correct else "WRONG_ANSWER"
        row.passed = 1 if correct else 0
        row.total = 1
    else:
        if not body.code or not body.code.strip():
            raise AppError("answer_required", "Добавьте код решения", status_code=400)
        if not body.language:
            raise AppError("language_not_allowed", "Укажите язык: Python или Go", status_code=400)
        result = await run_code(spec.id, body.code, body.language, True)
        normalized = piston.canonical_language(body.language)
        row.skipped = False
        row.answer = None
        row.code = body.code
        row.language = normalized
        row.verdict = result.verdict
        row.passed = result.passed
        row.total = result.total
    row.updated_at = now
    session.add(row)
    await session.commit()
    return await _view(session, attempt)


async def finish_attempt(session: AsyncSession, principal: Principal, attempt_id: UUID) -> AttemptResult:
    candidate_id = await _candidate_id(session, principal)
    attempt = await _owned_attempt(session, attempt_id, candidate_id)
    _ensure_open(attempt)
    specs = _specs_for(attempt.specialization)
    answers = await _answers(session, attempt.id)
    score, skill_scores = _graded(specs, answers)
    grade, ready = grade_for(score, attempt.declared_grade)
    return await _apply_result(session, attempt, score=score, grade=grade, ready=ready, skill_scores=skill_scores)


async def demo_finish_attempt(session: AsyncSession, attempt_id: UUID, body: DemoFinishIn) -> AttemptResult:
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None:
        raise AppError("not_found", "Попытка не найдена", status_code=404)
    specs = _specs_for(attempt.specialization)
    answers = await _answers(session, attempt.id)
    _, derived = _graded(specs, answers)
    if body.skill_scores:
        skill_scores = {item.skill_id: item.score for item in body.skill_scores}
    else:
        skill_scores = derived
    grade, _ready = grade_for(body.score, attempt.declared_grade)
    if body.grade is not None:
        grade = body.grade.value
    ready = body.score >= 75
    return await _apply_result(session, attempt, score=body.score, grade=grade, ready=ready, skill_scores=skill_scores)


def to_run_out(result: RunResult) -> RunOut:
    return RunOut(
        verdict=result.verdict,  # type: ignore[arg-type]
        passed=result.passed,
        total=result.total,
        stdout=result.stdout,
        stderr=result.stderr,
    )
