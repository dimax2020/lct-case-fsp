from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_role
from app.core.errors import not_implemented
from app.profile.schemas import (
    CandidateProfile,
    CandidateSettings,
    CandidateUpdate,
    GradeView,
    Me,
    ProjectIn,
    ProjectOut,
)

router = APIRouter(tags=["profile"])


@router.get("/me", response_model=Me)
async def get_me(_: Principal = Depends(require_role("candidate", "employer", "admin"))) -> None:
    not_implemented()


@router.get("/candidates/me", response_model=CandidateProfile)
async def get_my_candidate(_: Principal = Depends(require_role("candidate"))) -> None:
    not_implemented()


@router.put("/candidates/me", response_model=CandidateProfile)
async def update_my_candidate(
    body: CandidateUpdate,
    _: Principal = Depends(require_role("candidate")),
) -> None:
    del body
    not_implemented()


@router.get("/candidates/me/projects", response_model=list[ProjectOut])
async def list_my_projects(_: Principal = Depends(require_role("candidate"))) -> None:
    not_implemented()


@router.post("/candidates/me/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, _: Principal = Depends(require_role("candidate"))) -> None:
    del body
    not_implemented()


@router.put("/candidates/me/projects/{id}", response_model=ProjectOut)
async def update_project(
    id: UUID,
    body: ProjectIn,
    _: Principal = Depends(require_role("candidate")),
) -> None:
    del id, body
    not_implemented()


@router.delete("/candidates/me/projects/{id}", status_code=204)
async def delete_project(id: UUID, _: Principal = Depends(require_role("candidate"))) -> None:
    del id
    not_implemented()


@router.post("/candidates/me/fsp-link", response_model=CandidateProfile)
async def link_fsp(_: Principal = Depends(require_role("candidate"))) -> None:
    not_implemented()


@router.get("/candidates/me/grade", response_model=GradeView)
async def get_my_grade(_: Principal = Depends(require_role("candidate"))) -> None:
    not_implemented()


@router.get("/candidates/me/settings", response_model=CandidateSettings)
async def get_my_settings(_: Principal = Depends(require_role("candidate"))) -> None:
    not_implemented()


@router.put("/candidates/me/settings", response_model=CandidateSettings)
async def update_my_settings(
    body: CandidateSettings,
    _: Principal = Depends(require_role("candidate")),
) -> None:
    del body
    not_implemented()
