"""PDF resume upload, PyMuPDF text, and candidate confirmation."""

import logging
from pathlib import Path
from uuid import UUID

import fitz
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.settings import get_settings
from app.llm.service import extract, sanitize
from app.profile.service import apply_confirmed_resume, finish_evidence
from app.resume.models import Resume
from app.resume.schemas import ParsedResume
from app.taxonomy.service import normalize

logger = logging.getLogger(__name__)

MAX_RESUME_BYTES = 5 * 1024 * 1024
MAX_RESUME_PAGES = 5


async def read_pdf(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    size = 0
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        size += len(block)
        if size > MAX_RESUME_BYTES:
            raise AppError(
                "resume_too_large",
                "Файл резюме больше 5 МБ. Загрузите PDF до 5 МБ и не длиннее 5 страниц.",
                status_code=400,
            )
        chunks.append(block)
    return b"".join(chunks)


def assert_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF"):
        raise AppError("resume_invalid", "Нужен файл в формате PDF.", status_code=400)
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            pages = document.page_count
    except Exception as exc:
        raise AppError("resume_invalid", "Не удалось открыть PDF.", status_code=400) from exc
    if pages > MAX_RESUME_PAGES:
        raise AppError(
            "resume_too_many_pages",
            "В резюме больше 5 страниц. Нужен PDF не длиннее 5 страниц.",
            status_code=400,
        )
    if pages < 1:
        raise AppError("resume_invalid", "В PDF нет страниц.", status_code=400)


def upload_root() -> Path:
    root = Path(get_settings().upload_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def pdf_text(path: Path) -> str:
    with fitz.open(path) as document:
        return "\n".join(page.get_text() for page in document)


def _keep_span(span: object, source: str) -> str | None:
    if not isinstance(span, str):
        return None
    text = span.strip()
    if text and text in source:
        return text
    return None


def prepare_parsed(data: dict, source: str) -> dict:
    """Keep extracted objects whose quote is a substring of the resume text."""
    experiences: list[dict] = []
    for item in data.get("experiences") or []:
        if not isinstance(item, dict):
            continue
        span = _keep_span(item.get("evidence_span"), source)
        if span is None:
            continue
        experiences.append(
            {
                "company": str(item.get("company") or ""),
                "role": str(item.get("role") or ""),
                "start": item.get("start") or None,
                "end": item.get("end") or None,
                "description": str(item.get("description") or ""),
                "evidence_span": span,
            }
        )
    skills: list[dict] = []
    for item in data.get("skills") or []:
        if not isinstance(item, dict):
            continue
        span = _keep_span(item.get("evidence_span"), source)
        if span is None:
            continue
        name = str(item.get("name") or "")
        skills.append({"name": name, "skill_id": normalize(name), "evidence_span": span})
    projects: list[dict] = []
    for item in data.get("projects") or []:
        if not isinstance(item, dict):
            continue
        span = _keep_span(item.get("evidence_span"), source)
        task = str(item.get("task") or "").strip()
        if span is None or not task:
            continue
        projects.append(
            {
                "task": task,
                "role": str(item.get("role") or "participant"),
                "skills": [str(raw) for raw in item.get("skills") or []],
                "outcome": item.get("outcome"),
                "evidence_span": span,
            }
        )
    return {"experiences": experiences, "skills": skills, "projects": projects}


async def parse_in_session(session: AsyncSession, resume: Resume) -> None:
    raw = sanitize(pdf_text(Path(resume.file_path)))
    extracted = await extract("resume", raw)
    resume.raw_text = raw
    resume.parsed_json = prepare_parsed(extracted, raw)
    resume.status = "parsed"
    resume.error = None
    await session.flush()


async def parse_resume_body(resume_id: UUID) -> None:
    from app.core import db

    async with db.SessionLocal() as session:
        resume = await session.get(Resume, resume_id)
        if resume is None:
            return
        try:
            await parse_in_session(session, resume)
        except Exception:
            logger.exception("resume parse failed for %s", resume_id)
            resume.status = "failed"
            resume.error = "Не удалось разобрать резюме"
        await session.commit()


def parsed_view(data: dict | None) -> ParsedResume | None:
    if not data:
        return None
    try:
        return ParsedResume.model_validate(data)
    except Exception:
        logger.exception("parsed resume does not match the response model")
        return None


async def confirm(session: AsyncSession, resume: Resume, body: ParsedResume) -> ParsedResume:
    if resume.status not in {"parsed", "confirmed"}:
        raise AppError("resume_not_ready", "Резюме ещё не разобрано", status_code=409)
    raw_text = resume.raw_text or ""
    stored = await apply_confirmed_resume(session, resume.candidate_id, body.model_dump(mode="json"), raw_text)
    resume.parsed_json = stored
    resume.status = "confirmed"
    resume.error = None
    await finish_evidence(session, resume.candidate_id)
    view = parsed_view(stored)
    return view if view is not None else ParsedResume()
