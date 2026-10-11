"""Publish vacancies and move applications sent → viewed → accepted or declined."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.company.models import Company
from app.core.auth import Principal
from app.core.enums import Grade, Specialization
from app.core.errors import AppError
from app.core.models import User
from app.core.provision import provision_user
from app.profile.models import Candidate
from app.vacancy.models import Application, Vacancy
from app.vacancy.schemas import (
    ApplicationCreate,
    ApplicationList,
    ApplicationOut,
    DeclineIn,
    VacancyOut,
    VacancyWrite,
    applicant_email,
    applicant_phone,
    ensure_vacancy_bounds,
    status_counts,
)

_ACTIONS: dict[tuple[str, str], str] = {
    ("sent", "view"): "viewed",
    ("sent", "accept"): "accepted",
    ("sent", "decline"): "declined",
    ("viewed", "view"): "viewed",
    ("viewed", "accept"): "accepted",
    ("viewed", "decline"): "declined",
}
_STAMPS = {"viewed": "viewed_at", "accepted": "accepted_at", "declined": "declined_at"}


def next_application_status(status: str, action: str) -> str:
    try:
        return _ACTIONS[(status, action)]
    except KeyError:
        raise AppError("invalid_transition", "Недопустимый переход статуса", status_code=409) from None


def vacancy_visible(status: str, *, viewer_role: str, owns: bool) -> bool:
    if status == "open":
        return viewer_role in {"candidate", "employer"}
    return viewer_role == "employer" and owns


def resolve_list_role(principal_role: str, requested: str | None) -> str:
    role = (requested or principal_role).strip()
    if role not in {"candidate", "employer"}:
        raise AppError("validation_error", "Укажите роль candidate или employer", status_code=422)
    if role != principal_role:
        raise AppError("forbidden", "Недостаточно прав", status_code=403)
    return role


def _optional_filter(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def clean_catalog_filters(specialization: str | None, grade: str | None) -> tuple[str | None, str | None]:
    spec = _optional_filter(specialization)
    parsed_grade = _optional_filter(grade)
    if spec is not None:
        try:
            spec = Specialization(spec).value
        except ValueError:
            raise AppError("validation_error", "Неизвестная специализация", status_code=422) from None
    if parsed_grade is not None:
        try:
            parsed_grade = Grade(parsed_grade).value
        except ValueError:
            raise AppError("validation_error", "Неизвестный грейд", status_code=422) from None
    return spec, parsed_grade


def _apply_transition(application: Application, action: str, *, reason: str | None) -> None:
    cleaned: str | None = None
    if action == "decline":
        if reason is None or not reason.strip():
            raise AppError("validation_error", "Укажите причину отказа", status_code=422)
        cleaned = reason.strip()
    target = next_application_status(application.status, action)
    if target == application.status:
        return
    application.status = target
    if action == "decline":
        application.decline_reason = cleaned
    setattr(application, _STAMPS[target], datetime.now(UTC))


def to_vacancy_out(vacancy: Vacancy, company_name: str) -> VacancyOut:
    return VacancyOut(
        id=vacancy.id,
        company_id=vacancy.company_id,
        company_name=company_name,
        title=vacancy.title,
        specialization=vacancy.specialization,
        grades=list(vacancy.grades),
        salary_from=vacancy.salary_from,
        salary_to=vacancy.salary_to,
        formats=list(vacancy.formats),
        city=vacancy.city,
        must_skills=list(vacancy.must_skills),
        description=vacancy.description,
        domain=vacancy.domain,
        status=vacancy.status,
    )


def _ensure(body: VacancyWrite) -> None:
    try:
        ensure_vacancy_bounds(body.salary_from, body.salary_to, body.grades)
    except ValueError as exc:
        raise AppError("validation_error", str(exc), status_code=422) from None


def _fill(vacancy: Vacancy, body: VacancyWrite) -> None:
    _ensure(body)
    vacancy.title = body.title
    vacancy.specialization = body.specialization.value
    vacancy.grades = list(body.grades)
    vacancy.salary_from = body.salary_from
    vacancy.salary_to = body.salary_to
    vacancy.formats = [item.value for item in body.formats]
    vacancy.city = body.city
    vacancy.must_skills = list(body.must_skills)
    vacancy.description = body.description
    vacancy.domain = body.domain


def _application_out(
    application: Application,
    vacancy: Vacancy,
    company_name: str,
    *,
    viewer: str,
    email: str | None = None,
    phone: str | None = None,
) -> ApplicationOut:
    show_contacts = viewer == "employer"
    return ApplicationOut(
        id=application.id,
        vacancy_id=vacancy.id,
        status=application.status,
        message=application.message,
        created_at=application.created_at,
        title=vacancy.title,
        audience=viewer,
        company_name=company_name,
        salary_from=vacancy.salary_from,
        salary_to=vacancy.salary_to,
        candidate_email=email if show_contacts else None,
        candidate_phone=phone if show_contacts else None,
        decline_reason=application.decline_reason,
    )


async def _user(session: AsyncSession, principal: Principal) -> User:
    return await provision_user(session, principal)


async def _company_for(session: AsyncSession, user_id: UUID) -> Company:
    company = await session.scalar(select(Company).where(Company.owner_user_id == user_id))
    if company is None:
        raise AppError("not_found", "Компания не найдена", status_code=404)
    return company


async def _candidate_for(session: AsyncSession, user_id: UUID) -> Candidate:
    candidate = await session.scalar(select(Candidate).where(Candidate.user_id == user_id))
    if candidate is None:
        raise AppError("not_found", "Профиль кандидата не найден", status_code=404)
    return candidate


async def _company_name(session: AsyncSession, company_id: UUID) -> str:
    name = await session.scalar(select(Company.name).where(Company.id == company_id))
    return name or ""


def _catalog_stmt(principal: Principal, company_id: UUID | None, specialization: str | None, grade: str | None):
    stmt = select(Vacancy, Company.name).join(Company, Company.id == Vacancy.company_id)
    if principal.role == "candidate":
        stmt = stmt.where(Vacancy.status == "open")
    else:
        stmt = stmt.where(or_(Vacancy.status == "open", Vacancy.company_id == company_id))
    if specialization:
        stmt = stmt.where(Vacancy.specialization == specialization)
    if grade:
        stmt = stmt.where(Vacancy.grades.overlap([grade]))
    return stmt.order_by(Vacancy.created_at.desc(), Vacancy.id.desc())


async def list_vacancies(
    session: AsyncSession,
    principal: Principal,
    *,
    specialization: str | None = None,
    grade: str | None = None,
) -> list[VacancyOut]:
    spec, parsed_grade = clean_catalog_filters(specialization, grade)
    user = await _user(session, principal)
    company_id: UUID | None = None
    if principal.role == "employer":
        company_id = (await _company_for(session, user.id)).id
    rows = (await session.execute(_catalog_stmt(principal, company_id, spec, parsed_grade))).all()
    await session.commit()
    return [to_vacancy_out(vacancy, name or "") for vacancy, name in rows]


async def create_vacancy(session: AsyncSession, principal: Principal, body: VacancyWrite) -> VacancyOut:
    user = await _user(session, principal)
    company = await _company_for(session, user.id)
    vacancy = Vacancy(company_id=company.id, status="open")
    _fill(vacancy, body)
    session.add(vacancy)
    await session.commit()
    await session.refresh(vacancy)
    return to_vacancy_out(vacancy, company.name or "")


async def get_vacancy(session: AsyncSession, principal: Principal, vacancy_id: UUID) -> VacancyOut:
    user = await _user(session, principal)
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise AppError("not_found", "Вакансия не найдена", status_code=404)
    owns = False
    if principal.role == "employer":
        owns = vacancy.company_id == (await _company_for(session, user.id)).id
    if not vacancy_visible(vacancy.status, viewer_role=principal.role, owns=owns):
        raise AppError("not_found", "Вакансия не найдена", status_code=404)
    name = await _company_name(session, vacancy.company_id)
    await session.commit()
    return to_vacancy_out(vacancy, name)


async def update_vacancy(session: AsyncSession, principal: Principal, vacancy_id: UUID, body: VacancyWrite) -> VacancyOut:
    user = await _user(session, principal)
    company = await _company_for(session, user.id)
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None or vacancy.company_id != company.id:
        raise AppError("not_found", "Вакансия не найдена", status_code=404)
    _fill(vacancy, body)
    await session.commit()
    await session.refresh(vacancy)
    return to_vacancy_out(vacancy, company.name or "")


async def _open_vacancy(session: AsyncSession, vacancy_id: UUID) -> Vacancy:
    vacancy = await session.get(Vacancy, vacancy_id)
    if vacancy is None:
        raise AppError("not_found", "Вакансия не найдена", status_code=404)
    if vacancy.status != "open":
        raise AppError("vacancy_closed", "Вакансия закрыта", status_code=409)
    return vacancy


async def apply_to_vacancy(
    session: AsyncSession,
    principal: Principal,
    vacancy_id: UUID,
    body: ApplicationCreate,
) -> ApplicationOut:
    del session, principal, vacancy_id, body
    raise AppError(
        "applications_disabled",
        "Отклики отключены. Работодатель сам присылает приглашение, при желании — с тестовым заданием.",
        status_code=409,
    )


async def _contacts(session: AsyncSession, candidate_id: UUID) -> tuple[str | None, str | None]:
    row = (
        await session.execute(
            select(Candidate.contact_email, Candidate.phone, User.email)
            .join(User, User.id == Candidate.user_id)
            .where(Candidate.id == candidate_id)
        )
    ).one()
    return applicant_email(row.contact_email, row.email), applicant_phone(row.phone)


async def _owned_application(
    session: AsyncSession, principal: Principal, application_id: UUID
) -> tuple[Application, Vacancy, str]:
    user = await _user(session, principal)
    company = await _company_for(session, user.id)
    application = await session.get(Application, application_id)
    if application is None:
        raise AppError("not_found", "Отклик не найден", status_code=404)
    vacancy = await session.get(Vacancy, application.vacancy_id)
    if vacancy is None or vacancy.company_id != company.id:
        raise AppError("not_found", "Отклик не найден", status_code=404)
    return application, vacancy, company.name or ""


async def _employer_action(
    session: AsyncSession,
    principal: Principal,
    application_id: UUID,
    action: str,
    *,
    reason: str | None = None,
) -> ApplicationOut:
    application, vacancy, company_name = await _owned_application(session, principal, application_id)
    _apply_transition(application, action, reason=reason)
    await session.commit()
    await session.refresh(application)
    email, phone = await _contacts(session, application.candidate_id)
    return _application_out(application, vacancy, company_name, viewer="employer", email=email, phone=phone)


async def view_application(session: AsyncSession, principal: Principal, application_id: UUID) -> ApplicationOut:
    return await _employer_action(session, principal, application_id, "view")


async def accept_application(session: AsyncSession, principal: Principal, application_id: UUID) -> ApplicationOut:
    return await _employer_action(session, principal, application_id, "accept")


async def decline_application(
    session: AsyncSession,
    principal: Principal,
    application_id: UUID,
    body: DeclineIn,
) -> ApplicationOut:
    return await _employer_action(session, principal, application_id, "decline", reason=body.reason)


async def list_applications(session: AsyncSession, principal: Principal, role: str | None) -> ApplicationList:
    viewer = resolve_list_role(principal.role, role)
    user = await _user(session, principal)
    stmt = (
        select(Application, Vacancy, Company.name, Candidate.contact_email, Candidate.phone, User.email)
        .join(Vacancy, Vacancy.id == Application.vacancy_id)
        .join(Company, Company.id == Vacancy.company_id)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(User, User.id == Candidate.user_id)
        .order_by(Application.created_at.desc(), Application.id.desc())
    )
    if viewer == "candidate":
        candidate = await _candidate_for(session, user.id)
        stmt = stmt.where(Application.candidate_id == candidate.id)
    else:
        company = await _company_for(session, user.id)
        stmt = stmt.where(Vacancy.company_id == company.id)
    rows = (await session.execute(stmt)).all()
    await session.commit()
    items: list[ApplicationOut] = []
    for application, vacancy, company_name, contact_email, phone, user_email in rows:
        email = applicant_email(contact_email, user_email) if viewer == "employer" else None
        shown_phone = applicant_phone(phone) if viewer == "employer" else None
        items.append(
            _application_out(
                application,
                vacancy,
                company_name or "",
                viewer=viewer,
                email=email,
                phone=shown_phone,
            )
        )
    return ApplicationList(items=items, counts=status_counts([item.status for item in items]))
