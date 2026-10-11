import asyncio
import logging
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, require_role
from app.core.enums import ResumeStatus
from app.core.errors import AppError
from app.profile.service import current_candidate, get_db
from app.resume.models import Resume
from app.resume.schemas import ParsedResume, ResumeUploadOut, ResumeView
from app.resume.service import assert_pdf, confirm, parse_in_session, parsed_view, read_pdf, upload_root
from app.resume.tasks import parse_resume

logger = logging.getLogger(__name__)

router = APIRouter(tags=["resume"])


async def _db() -> AsyncIterator[AsyncSession]:
    async for session in get_db():
        yield session


async def _kick_parse(resume_id: UUID) -> None:
    try:
        await asyncio.wait_for(parse_resume.kiq(str(resume_id)), timeout=0.25)
    except Exception:
        logger.info("parse_resume was not queued for %s", resume_id)


def _view(resume: Resume) -> ResumeView:
    status = resume.status if resume.status in {item.value for item in ResumeStatus} else ResumeStatus.failed.value
    return ResumeView(
        id=resume.id,
        status=ResumeStatus(status),
        error=resume.error,
        parsed=parsed_view(resume.parsed_json) if resume.status in {"parsed", "confirmed"} else None,
    )


@router.post("/candidates/me/resume", response_model=ResumeUploadOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> ResumeUploadOut:
    candidate = await current_candidate(session, principal)
    payload = await read_pdf(file)
    assert_pdf(payload)
    resume_id = uuid4()
    path = upload_root() / str(candidate.id) / f"{resume_id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    resume = Resume(id=resume_id, candidate_id=candidate.id, file_path=str(path), status="parsing")
    session.add(resume)
    await session.flush()
    try:
        await parse_in_session(session, resume)
    except Exception:
        logger.exception("resume parse failed for %s", resume_id)
        resume.status = "failed"
        resume.error = "Не удалось разобрать резюме"
    await _kick_parse(resume_id)
    return ResumeUploadOut(resume_id=resume.id, status=ResumeStatus(resume.status))


@router.get("/candidates/me/resume/{id}", response_model=ResumeView)
async def get_resume(
    id: UUID,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> ResumeView:
    candidate = await current_candidate(session, principal)
    resume = await session.get(Resume, id)
    if resume is None or resume.candidate_id != candidate.id:
        raise AppError("not_found", "Резюме не найдено", status_code=404)
    return _view(resume)


@router.post("/candidates/me/resume/{id}/confirm", response_model=ResumeView)
async def confirm_resume(
    id: UUID,
    body: ParsedResume,
    principal: Principal = Depends(require_role("candidate")),
    session: AsyncSession = Depends(_db),
) -> ResumeView:
    candidate = await current_candidate(session, principal)
    resume = await session.get(Resume, id)
    if resume is None or resume.candidate_id != candidate.id:
        raise AppError("not_found", "Резюме не найдено", status_code=404)
    await confirm(session, resume, body)
    return _view(resume)
