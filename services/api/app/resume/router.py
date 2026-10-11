from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.auth import Principal, require_role
from app.core.errors import not_implemented
from app.resume.schemas import ParsedResume, ResumeUploadOut, ResumeView

router = APIRouter(tags=["resume"])


@router.post("/candidates/me/resume", response_model=ResumeUploadOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    _: Principal = Depends(require_role("candidate")),
) -> None:
    del file
    not_implemented()


@router.get("/candidates/me/resume/{id}", response_model=ResumeView)
async def get_resume(id: UUID, _: Principal = Depends(require_role("candidate"))) -> None:
    del id
    not_implemented()


@router.post("/candidates/me/resume/{id}/confirm", response_model=ResumeView)
async def confirm_resume(
    id: UUID,
    body: ParsedResume,
    _: Principal = Depends(require_role("candidate")),
) -> None:
    del id, body
    not_implemented()
