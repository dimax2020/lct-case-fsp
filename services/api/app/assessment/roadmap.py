"""Short adaptive sample of the backend or frontend roadmap."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import RoadmapRun, RoadmapStep
from app.assessment.roadmap_bank import choose_probe_ids, map_label, probe_by_id, probes_for
from app.assessment.roadmap_score import (
    PROBES_PER_RUN,
    block_score,
    check_score,
    concrete_score,
    cooldown_for,
    grade_from_latent,
    level_index,
    next_level,
    result_message,
    start_level,
    study_items,
    update_latent,
)
from app.assessment.schemas import (
    RoadmapCheckOut,
    RoadmapChecksIn,
    RoadmapConcreteIn,
    RoadmapCreate,
    RoadmapGap,
    RoadmapLatest,
    RoadmapNode,
    RoadmapResultOut,
    RoadmapView,
)
from app.assessment.service import ensure_candidate_id
from app.core.auth import Principal
from app.core.enums import GRADE_ORDER, Grade
from app.core.errors import AppError


async def latest(session: AsyncSession, principal: Principal) -> RoadmapLatest:
    candidate_id = await ensure_candidate_id(session, principal)
    run = await _latest_finished(session, candidate_id)
    if run is None or run.locked_until is None or run.measured_grade is None or run.outcome is None:
        return RoadmapLatest(finished=False, open=True)
    nodes, review = await _chart(session, run)
    open_now = run.locked_until <= datetime.now(UTC)
    return RoadmapLatest(
        finished=True,
        open=open_now,
        measured_grade=run.measured_grade,  # type: ignore[arg-type]
        outcome=run.outcome,  # type: ignore[arg-type]
        locked_until=run.locked_until,
        message=run.message,
        nodes=nodes,
        review=review,
    )


async def start_run(session: AsyncSession, principal: Principal, body: RoadmapCreate) -> RoadmapView:
    candidate_id = await ensure_candidate_id(session, principal)
    open_run = await _unfinished(session, candidate_id)
    if open_run is not None:
        return await _view(session, open_run)
    await _ensure_open(session, candidate_id)
    level = start_level(body.declared_grade.value)
    run = RoadmapRun(
        candidate_id=candidate_id,
        specialization=body.specialization,
        declared_grade=body.declared_grade.value,
        level=level,
        latent=level_index(level),
        probe_ids=[],
        step_index=0,
        phase="checks",
    )
    session.add(run)
    await session.flush()
    run.probe_ids = choose_probe_ids(body.specialization, str(run.id), PROBES_PER_RUN)
    flag_modified(run, "probe_ids")
    await session.commit()
    await session.refresh(run)
    return await _view(session, run)


async def save_checks(session: AsyncSession, principal: Principal, run_id: UUID, body: RoadmapChecksIn) -> RoadmapView:
    run = await _owned(session, principal, run_id)
    if run.phase != "checks":
        raise AppError("roadmap_phase", "Сначала ответьте на конкретный вопрос", status_code=409)
    probe = _current_probe(run)
    expected = {item.id for item in probe.levels[run.level]}
    got = {item.id: item.value for item in body.answers}
    if set(got) != expected:
        raise AppError("roadmap_checks", "Отметьте каждое утверждение: да, нет или не знаю", status_code=422)
    step = await _step_for(session, run, probe.id)
    step.level = run.level
    step.checks = got
    run.phase = "concrete"
    await session.commit()
    return await _view(session, run)


async def save_concrete(session: AsyncSession, principal: Principal, run_id: UUID, body: RoadmapConcreteIn) -> RoadmapView:
    run = await _owned(session, principal, run_id)
    if run.phase != "concrete":
        raise AppError("roadmap_phase", "Сначала отметьте утверждения", status_code=409)
    probe = _current_probe(run)
    step = await _step_for(session, run, probe.id)
    if not step.checks:
        raise AppError("roadmap_phase", "Сначала отметьте утверждения", status_code=409)
    values = [str(step.checks[item.id]) for item in probe.levels[step.level]]
    question = probe.concrete[step.level]
    scored = block_score(check_score(values), concrete_score(body.answer, question.needles))
    step.concrete = body.answer.strip()
    step.block_score = scored
    run.latent = update_latent(run.latent, scored)
    run.level = next_level(step.level, scored)
    if run.step_index + 1 >= len(run.probe_ids):
        await _finish(session, run)
    else:
        run.step_index += 1
        run.phase = "checks"
    await session.commit()
    return await _view(session, run)


async def get_run(session: AsyncSession, principal: Principal, run_id: UUID) -> RoadmapView:
    run = await _owned(session, principal, run_id)
    return await _view(session, run)


async def _finish(session: AsyncSession, run: RoadmapRun) -> None:
    rows = list(
        (
            await session.scalars(select(RoadmapStep).where(RoadmapStep.run_id == run.id))
        ).all()
    )
    blocks = [item.block_score for item in rows if item.block_score is not None]
    average = sum(blocks) / len(blocks) if blocks else 0.0
    measured = grade_from_latent(run.latent, run.declared_grade)
    days, outcome = cooldown_for(run.declared_grade, measured)
    now = datetime.now(UTC)
    run.phase = "done"
    run.finished_at = now
    run.score = round(average * 100, 2)
    run.measured_grade = measured
    run.outcome = outcome
    run.cooldown_days = days
    run.locked_until = now + timedelta(days=days)
    run.message = result_message(measured, outcome, days)
    await _write_profile(session, run, measured)


async def _write_profile(session: AsyncSession, run: RoadmapRun, measured: str) -> None:
    from sqlalchemy import text

    current = await session.execute(
        text("SELECT grade FROM candidates WHERE id = CAST(:id AS uuid)"),
        {"id": str(run.candidate_id)},
    )
    stored = current.scalar_one_or_none()
    stored_grade = str(stored) if stored else None
    ready = GRADE_ORDER.index(Grade(measured)) > GRADE_ORDER.index(Grade(stored_grade or run.declared_grade))
    if stored_grade is None:
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
                "spec": run.specialization,
                "grade": measured,
                "score": run.score,
                "ready": ready,
                "id": str(run.candidate_id),
            },
        )
        return
    await session.execute(
        text(
            """
            UPDATE candidates
            SET grade_score = :score,
                ready_for_next = :ready
            WHERE id = CAST(:id AS uuid)
            """
        ),
        {"score": run.score, "ready": ready, "id": str(run.candidate_id)},
    )


def _chart_from(run: RoadmapRun, steps: list[RoadmapStep]) -> tuple[list[RoadmapNode], list[RoadmapGap]]:
    by_id = {item.probe_id: item for item in steps}
    order = [str(item) for item in (run.probe_ids or [])]
    current_id = order[run.step_index] if run.phase != "done" and run.step_index < len(order) else None
    nodes: list[RoadmapNode] = []
    review: list[RoadmapGap] = []
    for probe in probes_for(run.specialization):
        step = by_id.get(probe.id)
        gaps = _gaps(probe, step) if step is not None and step.block_score is not None else []
        if probe.id not in order:
            status = "aside"
        elif probe.id == current_id and (step is None or step.block_score is None):
            status = "current"
            gaps = []
        elif gaps:
            status = "review"
        elif step is not None and step.block_score is not None:
            status = "held"
        else:
            status = "ahead"
        place = order.index(probe.id) + 1 if probe.id in order else None
        nodes.append(RoadmapNode(id=probe.id, label=map_label(probe), title=probe.title, status=status, order=place))  # type: ignore[arg-type]
        if status == "review" and gaps:
            review.append(RoadmapGap(label=map_label(probe), title=probe.title, items=gaps))
    return nodes, review


def _gaps(probe, step: RoadmapStep) -> list[str]:
    question = probe.concrete.get(step.level)
    statements = [(item.id, item.text) for item in probe.levels.get(step.level, ())]
    checks = {str(key): str(value) for key, value in (step.checks or {}).items()}
    if question is None:
        return []
    return study_items(checks, statements, step.concrete, question.question, question.needles)


async def _chart(session: AsyncSession, run: RoadmapRun) -> tuple[list[RoadmapNode], list[RoadmapGap]]:
    steps = list((await session.scalars(select(RoadmapStep).where(RoadmapStep.run_id == run.id))).all())
    return _chart_from(run, steps)


async def _view(session: AsyncSession, run: RoadmapRun) -> RoadmapView:
    nodes, review = await _chart(session, run)
    result = None
    if run.phase == "done" and run.measured_grade and run.outcome and run.locked_until and run.cooldown_days and run.message:
        result = RoadmapResultOut(
            measured_grade=run.measured_grade,  # type: ignore[arg-type]
            outcome=run.outcome,  # type: ignore[arg-type]
            cooldown_days=run.cooldown_days,
            locked_until=run.locked_until,
            message=run.message,
            score=run.score or 0,
        )
        return RoadmapView(
            id=run.id,
            specialization=run.specialization,  # type: ignore[arg-type]
            declared_grade=run.declared_grade,  # type: ignore[arg-type]
            step=len(run.probe_ids),
            total=len(run.probe_ids),
            phase="done",
            result=result,
            nodes=nodes,
            review=review,
        )
    probe = _current_probe(run)
    step = await session.scalar(
        select(RoadmapStep).where(RoadmapStep.run_id == run.id, RoadmapStep.probe_id == probe.id)
    )
    saved = {str(key): str(value) for key, value in (step.checks or {}).items()} if step and step.checks else {}
    show_concrete = run.phase == "concrete"
    return RoadmapView(
        id=run.id,
        specialization=run.specialization,  # type: ignore[arg-type]
        declared_grade=run.declared_grade,  # type: ignore[arg-type]
        step=run.step_index + 1,
        total=len(run.probe_ids),
        phase="concrete" if show_concrete else "checks",
        title=probe.title,
        prompt=probe.prompt,
        checks=[RoadmapCheckOut(id=item.id, text=item.text) for item in probe.levels[run.level if not show_concrete else (step.level if step else run.level)]],
        saved_checks=saved,  # type: ignore[arg-type]
        concrete_question=probe.concrete[(step.level if step else run.level)].question if show_concrete else None,
        nodes=nodes,
        review=review,
    )


def _current_probe(run: RoadmapRun):
    probe_ids = list(run.probe_ids or [])
    if run.step_index >= len(probe_ids):
        raise AppError("roadmap_missing", "Тема теста не найдена", status_code=500)
    probe = probe_by_id(str(probe_ids[run.step_index]))
    if probe is None:
        raise AppError("roadmap_missing", "Тема теста не найдена", status_code=500)
    return probe


async def _step_for(session: AsyncSession, run: RoadmapRun, probe_id: str) -> RoadmapStep:
    found = await session.scalar(select(RoadmapStep).where(RoadmapStep.run_id == run.id, RoadmapStep.probe_id == probe_id))
    if found is not None:
        return found
    created = RoadmapStep(run_id=run.id, probe_id=probe_id, level=run.level)
    session.add(created)
    await session.flush()
    return created


async def _owned(session: AsyncSession, principal: Principal, run_id: UUID) -> RoadmapRun:
    candidate_id = await ensure_candidate_id(session, principal)
    run = await session.get(RoadmapRun, run_id)
    if run is None or run.candidate_id != candidate_id:
        raise AppError("roadmap_not_found", "Тест не найден", status_code=404)
    if run.phase == "done":
        return run
    return run


async def _unfinished(session: AsyncSession, candidate_id: UUID) -> RoadmapRun | None:
    return await session.scalar(
        select(RoadmapRun)
        .where(RoadmapRun.candidate_id == candidate_id, RoadmapRun.finished_at.is_(None))
        .order_by(RoadmapRun.created_at.desc())
    )


async def _latest_finished(session: AsyncSession, candidate_id: UUID) -> RoadmapRun | None:
    return await session.scalar(
        select(RoadmapRun)
        .where(RoadmapRun.candidate_id == candidate_id, RoadmapRun.finished_at.is_not(None))
        .order_by(RoadmapRun.finished_at.desc())
    )


async def _ensure_open(session: AsyncSession, candidate_id: UUID) -> None:
    run = await _latest_finished(session, candidate_id)
    if run is None or run.locked_until is None:
        return
    if run.locked_until > datetime.now(UTC):
        when = run.locked_until.astimezone(UTC).strftime("%d.%m.%Y")
        raise AppError("roadmap_cooldown", f"Следующий тест откроется {when}", status_code=409)
