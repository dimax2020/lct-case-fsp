"""Invitation state machine, favorites, and contact reveal."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.enums import ContactChannel, DeclineReason, InvitationStatus
from app.core.errors import AppError
from app.core.models import User
from app.invitation.access import current_user
from app.invitation.models import Favorite, Invitation
from app.invitation.schemas import DeclineIn, FavoriteOut, InvitationCreate, InvitationList, InvitationOut
from app.matching.service import invalidate

_OPEN = frozenset({"sent", "viewed"})
_TRANSITIONS: dict[str, dict[str, str]] = {
    "sent": {
        "view": "viewed",
        "revoke": "revoked",
        "expire": "expired",
    },
    "viewed": {
        "view": "viewed",
        "accept": "accepted",
        "decline": "declined",
        "revoke": "revoked",
        "expire": "expired",
    },
}
_STATUS_FILTERS: dict[str, frozenset[str] | None] = {item.value: frozenset({item.value}) for item in InvitationStatus}
_STATUS_FILTERS.update(
    {
        "all": None,
        "incoming": frozenset({"sent", "viewed"}),
        "inbox": frozenset({"sent", "viewed"}),
        "waiting": frozenset({"sent", "viewed"}),
        "pending": frozenset({"sent", "viewed"}),
    }
)


@dataclass(frozen=True)
class _Company:
    id: UUID
    owner_user_id: UUID
    name: str
    recruiter_contact: dict[str, Any]


@dataclass(frozen=True)
class _Need:
    id: UUID
    company_id: UUID
    title: str


@dataclass(frozen=True)
class _Candidate:
    id: UUID
    user_id: UUID
    full_name: str
    display_name: str
    initials: str
    city: str | None
    specialization: str | None
    grade: str | None
    grade_score: float | None
    phone: str | None
    contact_email: str | None
    user_email: str | None

    @property
    def email(self) -> str | None:
        return self.contact_email or self.user_email


def reveal_contacts(
    status: str | None,
    email: str | None = None,
    phone: str | None = None,
    *,
    recruiter_contact: str | None = None,
    viewer: str = "employer",
) -> dict[str, Any]:
    """Contacts stay out of the payload until the invitation is accepted."""
    accepted = status == InvitationStatus.accepted
    revealed: dict[str, Any] = {"contacts_revealed": accepted}
    if not accepted:
        return revealed
    if viewer in {"employer", "admin"}:
        revealed["email"] = email
        revealed["phone"] = phone
        revealed["candidate_email"] = email
        revealed["candidate_phone"] = phone
    if viewer == "candidate":
        revealed["recruiter_contact"] = recruiter_contact
    return revealed


def _uuid(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _person_names(full_name: str) -> tuple[str, str]:
    parts = [part for part in full_name.split() if part]
    if not parts:
        return "Кандидат", "К."
    if len(parts) == 1:
        return parts[0], f"{parts[0][0]}."
    display = f"{parts[0]} {parts[1][0]}."
    initials = " ".join(f"{part[0]}." for part in parts[:3])
    return display, initials


def _category(specialization: str | None, grade: str | None) -> str:
    parts = [part for part in (specialization, grade) if part]
    return " · ".join(parts) if parts else "—"


def _experience_years(spans: list[tuple[date | None, date | None]]) -> float | None:
    starts = [start for start, _end in spans if start is not None]
    if not starts:
        return None
    start = min(starts)
    ends = [end for _start, end in spans if end is not None]
    end = max(ends) if ends else date.today()
    if end < start:
        end = date.today()
    return round((end - start).days / 365.25, 1)


def _target_status(current: str, action: str) -> str:
    allowed = _TRANSITIONS.get(current, {})
    if action not in allowed:
        raise AppError("invalid_transition", "Недопустимый переход статуса", status_code=409)
    return allowed[action]


def _apply(inv: Invitation, action: str, *, reason: str | None, now: datetime) -> bool:
    target = _target_status(inv.status, action)
    if target == inv.status:
        return False
    if action == "decline" and not reason:
        raise AppError("validation_error", "Укажите причину отказа", status_code=422)
    if action == "decline":
        inv.decline_reason = reason
    inv.status = target
    stamp = {
        "viewed": "viewed_at",
        "accepted": "accepted_at",
        "declined": "declined_at",
        "expired": "expired_at",
        "revoked": "revoked_at",
    }[target]
    setattr(inv, stamp, now)
    return True


async def apply_action(session: AsyncSession, inv: Invitation, action: str, *, reason: str | None = None) -> bool:
    changed = _apply(inv, action, reason=reason, now=datetime.now(UTC))
    await session.commit()
    if changed:
        await invalidate(inv.need_id)
    return changed


def _format_recruiter_contact(contact: dict[str, Any] | None) -> str | None:
    if not contact:
        return None
    parts: list[str] = []
    for key in ("name", "email", "phone"):
        value = contact.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return ", ".join(parts) or None


def _company_from_row(row: Any) -> _Company:
    contact = row["recruiter_contact"] or {}
    if not isinstance(contact, dict):
        contact = {}
    return _Company(
        id=_uuid(row["id"]),
        owner_user_id=_uuid(row["owner_user_id"]),
        name=str(row["name"] or ""),
        recruiter_contact=dict(contact),
    )


async def _company_by_id(session: AsyncSession, company_id: UUID) -> _Company | None:
    row = (
        (
            await session.execute(
                text("SELECT id, owner_user_id, name, recruiter_contact FROM companies WHERE id = :id"),
                {"id": company_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return _company_from_row(row)


async def _company_by_owner(session: AsyncSession, owner_user_id: UUID) -> _Company | None:
    row = (
        (
            await session.execute(
                text("SELECT id, owner_user_id, name, recruiter_contact FROM companies WHERE owner_user_id = :id"),
                {"id": owner_user_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return _company_from_row(row)


async def _need(session: AsyncSession, need_id: UUID) -> _Need | None:
    row = (
        (
            await session.execute(
                text("SELECT id, company_id, title FROM needs WHERE id = :id"),
                {"id": need_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return _Need(id=_uuid(row["id"]), company_id=_uuid(row["company_id"]), title=str(row["title"]))


async def _hidden_from(session: AsyncSession, candidate_id: UUID, company_id: UUID) -> bool:
    row = (
        await session.execute(
            text("SELECT (NOT visible) OR (:company = ANY(hidden_company_ids)) FROM candidates WHERE id = :id"),
            {"id": candidate_id, "company": company_id},
        )
    ).first()
    return bool(row[0]) if row is not None else False


async def _candidate(session: AsyncSession, candidate_id: UUID) -> _Candidate | None:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT c.id, c.user_id, c.full_name, c.city, c.specialization, c.grade,
                       c.grade_score, c.phone, c.contact_email, u.email AS user_email
                FROM candidates c
                JOIN users u ON u.id = c.user_id
                WHERE c.id = :id
                """
                ),
                {"id": candidate_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    full_name = str(row["full_name"] or "")
    display, initials = _person_names(full_name)
    score = row["grade_score"]
    return _Candidate(
        id=_uuid(row["id"]),
        user_id=_uuid(row["user_id"]),
        full_name=full_name,
        display_name=display,
        initials=initials,
        city=row["city"],
        specialization=row["specialization"],
        grade=row["grade"],
        grade_score=float(score) if score is not None else None,
        phone=row["phone"],
        contact_email=row["contact_email"],
        user_email=row["user_email"],
    )


async def _candidate_id_for_user(session: AsyncSession, user_id: UUID) -> UUID | None:
    row = (
        await session.execute(
            text("SELECT id FROM candidates WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
    ).first()
    if row is None:
        return None
    return _uuid(row[0])


def _recruiter_line(profile: _Company | None, contact_value: str | None) -> str | None:
    base = _format_recruiter_contact(profile.recruiter_contact if profile else None)
    extra = contact_value.strip() if isinstance(contact_value, str) else ""
    if base and extra and extra not in base:
        return f"{base}; {extra}"
    return base or extra or None


async def _serialize(session: AsyncSession, inv: Invitation, viewer: str) -> InvitationOut:
    need = await _need(session, inv.need_id)
    candidate = await _candidate(session, inv.candidate_id)
    profile = await _company_by_id(session, need.company_id) if need is not None else None
    recruiter = _recruiter_line(profile, inv.contact_value)
    contacts = reveal_contacts(
        inv.status,
        candidate.email if candidate else None,
        candidate.phone if candidate else None,
        recruiter_contact=recruiter,
        viewer=viewer,
    )
    payload: dict[str, Any] = {
        "id": inv.id,
        "need_id": inv.need_id,
        "candidate_id": inv.candidate_id,
        "status": inv.status,
        "title": inv.title,
        "message": inv.message or "",
        "salary_from": inv.salary_from,
        "salary_to": inv.salary_to,
        "contact_channel": ContactChannel(inv.contact_channel) if inv.contact_channel else None,
        "deadline": inv.deadline,
        "decline_reason": DeclineReason(inv.decline_reason) if inv.decline_reason else None,
        "created_at": inv.created_at,
        "company_name": profile.name if profile and profile.name else None,
        "need_title": need.title if need else None,
        "candidate_display_name": candidate.display_name if candidate else None,
    }
    for key in ("candidate_email", "candidate_phone", "recruiter_contact"):
        if key in contacts and contacts[key] is not None:
            payload[key] = contacts[key]
    return InvitationOut(**payload)


def _viewer(principal: Principal, role: str | None) -> str:
    if role is not None and role not in {"candidate", "employer", "admin"}:
        raise AppError("validation_error", "Неизвестная роль", status_code=422)
    if role is not None and principal.role != "admin" and role != principal.role:
        raise AppError("forbidden", "Недостаточно прав", status_code=403)
    if principal.role == "admin":
        return role or "admin"
    return principal.role


def _status_filter(status: str | None) -> frozenset[str] | None:
    if status is None or status == "":
        return None
    if status not in _STATUS_FILTERS:
        raise AppError("validation_error", "Неизвестный фильтр статуса", status_code=422)
    return _STATUS_FILTERS[status]


def _counts(rows: list[Invitation]) -> dict[str, int]:
    counts = {item.value: 0 for item in InvitationStatus}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    counts["incoming"] = counts["sent"] + counts["viewed"]
    counts["waiting"] = counts["incoming"]
    counts["pending"] = counts["incoming"]
    counts["all"] = sum(counts[item.value] for item in InvitationStatus)
    return counts


async def _scoped(session: AsyncSession, user: User, viewer: str) -> list[Invitation]:
    if viewer == "admin":
        stmt = select(Invitation)
    elif viewer == "employer":
        profile = await _company_by_owner(session, user.id)
        if profile is None:
            return []
        need_ids = list(
            (
                await session.execute(
                    text("SELECT id FROM needs WHERE company_id = :cid"),
                    {"cid": profile.id},
                )
            )
            .scalars()
            .all()
        )
        if not need_ids:
            return []
        stmt = select(Invitation).where(Invitation.need_id.in_(need_ids))
    else:
        candidate_id = await _candidate_id_for_user(session, user.id)
        if candidate_id is None:
            return []
        stmt = select(Invitation).where(Invitation.candidate_id == candidate_id)
    stmt = stmt.order_by(Invitation.created_at.desc(), Invitation.id.desc())
    return list(await session.scalars(stmt))


async def _for_candidate(session: AsyncSession, invitation_id: UUID, user: User) -> Invitation:
    inv = await session.get(Invitation, invitation_id)
    owner = await _candidate_id_for_user(session, user.id)
    if inv is None or owner is None or owner != inv.candidate_id:
        raise AppError("not_found", "Приглашение не найдено", status_code=404)
    return inv


async def _for_employer(session: AsyncSession, invitation_id: UUID, user: User) -> Invitation:
    inv = await session.get(Invitation, invitation_id)
    need = await _need(session, inv.need_id) if inv is not None else None
    profile = await _company_by_id(session, need.company_id) if need is not None else None
    if inv is None or profile is None or profile.owner_user_id != user.id:
        raise AppError("not_found", "Приглашение не найдено", status_code=404)
    return inv


async def _candidate_exists(session: AsyncSession, candidate_id: UUID) -> bool:
    row = (await session.execute(text("SELECT 1 FROM candidates WHERE id = :id"), {"id": candidate_id})).first()
    return row is not None


async def create_invitation(session: AsyncSession, principal: Principal, body: InvitationCreate) -> InvitationOut:
    user = await current_user(session, principal)
    if body.salary_to < body.salary_from:
        raise AppError("validation_error", "Верх вилки меньше низа", status_code=422)
    need = await _need(session, body.need_id)
    profile = await _company_by_id(session, need.company_id) if need is not None else None
    if need is None or profile is None or profile.owner_user_id != user.id:
        raise AppError("not_found", "Потребность не найдена", status_code=404)
    if await _candidate(session, body.candidate_id) is None:
        raise AppError("not_found", "Кандидат не найден", status_code=404)
    if await _hidden_from(session, body.candidate_id, need.company_id):
        # Кандидат скрыл профиль от этой компании в настройках приватности.
        raise AppError("not_found", "Кандидат не найден", status_code=404)
    existing = await session.scalar(
        select(Invitation.id).where(
            Invitation.need_id == body.need_id,
            Invitation.candidate_id == body.candidate_id,
        )
    )
    if existing is not None:
        raise AppError(
            "invitation_exists",
            "Приглашение этому кандидату по этой потребности уже отправлено",
            status_code=409,
        )
    inv = Invitation(
        need_id=body.need_id,
        candidate_id=body.candidate_id,
        status=InvitationStatus.sent,
        title=body.title.strip(),
        message=body.message,
        salary_from=body.salary_from,
        salary_to=body.salary_to,
        contact_channel=body.contact_channel.value,
        contact_value=body.contact_value.strip(),
        deadline=_utc(body.deadline),
        created_at=datetime.now(UTC),
    )
    session.add(inv)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise AppError(
            "invitation_exists",
            "Приглашение этому кандидату по этой потребности уже отправлено",
            status_code=409,
        ) from None
    await invalidate(inv.need_id)
    return await _serialize(session, inv, principal.role)


async def list_invitations(
    session: AsyncSession,
    principal: Principal,
    *,
    role: str | None,
    status: str | None,
) -> InvitationList:
    user = await current_user(session, principal)
    viewer = _viewer(principal, role)
    selected = _status_filter(status)
    rows = await _scoped(session, user, viewer)
    counts = _counts(rows)
    visible = rows if selected is None else [row for row in rows if row.status in selected]
    items = [await _serialize(session, row, viewer if viewer != "admin" else principal.role) for row in visible]
    return InvitationList(items=items, counts=counts)


async def view_invitation(session: AsyncSession, principal: Principal, invitation_id: UUID) -> InvitationOut:
    user = await current_user(session, principal)
    inv = await _for_candidate(session, invitation_id, user)
    await apply_action(session, inv, "view")
    return await _serialize(session, inv, principal.role)


async def accept_invitation(session: AsyncSession, principal: Principal, invitation_id: UUID) -> InvitationOut:
    user = await current_user(session, principal)
    inv = await _for_candidate(session, invitation_id, user)
    await apply_action(session, inv, "accept")
    return await _serialize(session, inv, principal.role)


async def decline_invitation(
    session: AsyncSession,
    principal: Principal,
    invitation_id: UUID,
    body: DeclineIn,
) -> InvitationOut:
    user = await current_user(session, principal)
    inv = await _for_candidate(session, invitation_id, user)
    await apply_action(session, inv, "decline", reason=body.reason.value)
    return await _serialize(session, inv, principal.role)


async def revoke_invitation(session: AsyncSession, principal: Principal, invitation_id: UUID) -> InvitationOut:
    user = await current_user(session, principal)
    inv = await _for_employer(session, invitation_id, user)
    await apply_action(session, inv, "revoke")
    return await _serialize(session, inv, principal.role)


async def remind_invitation(session: AsyncSession, principal: Principal, invitation_id: UUID) -> InvitationOut:
    user = await current_user(session, principal)
    inv = await _for_employer(session, invitation_id, user)
    if inv.status not in _OPEN:
        raise AppError("invalid_transition", "Напомнить можно только приглашение без ответа", status_code=409)
    return await _serialize(session, inv, principal.role)


async def expire_invitation(session: AsyncSession, invitation_id: UUID) -> None:
    inv = await session.get(Invitation, invitation_id)
    if inv is None:
        raise AppError("not_found", "Приглашение не найдено", status_code=404)
    await apply_action(session, inv, "expire")


async def expire_due(session: AsyncSession, *, now: datetime | None = None) -> int:
    moment = _utc(now) or datetime.now(UTC)
    rows = list(
        await session.scalars(
            select(Invitation).where(
                Invitation.status.in_(("sent", "viewed")),
                Invitation.deadline.is_not(None),
                Invitation.deadline <= moment,
            )
        )
    )
    need_ids: list[UUID] = []
    for inv in rows:
        if _apply(inv, "expire", reason=None, now=moment):
            need_ids.append(inv.need_id)
    await session.commit()
    for need_id in dict.fromkeys(need_ids):
        await invalidate(need_id)
    return len(need_ids)


async def add_favorite(session: AsyncSession, principal: Principal, candidate_id: UUID) -> FavoriteOut:
    user = await current_user(session, principal)
    profile = await _company_by_owner(session, user.id)
    if profile is None:
        raise AppError("not_found", "Компания не найдена", status_code=404)
    if not await _candidate_exists(session, candidate_id):
        raise AppError("not_found", "Кандидат не найден", status_code=404)
    existing = await session.get(Favorite, (profile.id, candidate_id))
    if existing is None:
        session.add(Favorite(company_id=profile.id, candidate_id=candidate_id))
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
    return FavoriteOut(candidate_id=candidate_id, favorite=True)


async def remove_favorite(session: AsyncSession, principal: Principal, candidate_id: UUID) -> FavoriteOut:
    user = await current_user(session, principal)
    profile = await _company_by_owner(session, user.id)
    if profile is None:
        raise AppError("not_found", "Компания не найдена", status_code=404)
    if not await _candidate_exists(session, candidate_id):
        raise AppError("not_found", "Кандидат не найден", status_code=404)
    existing = await session.get(Favorite, (profile.id, candidate_id))
    if existing is not None:
        await session.delete(existing)
        await session.commit()
    return FavoriteOut(candidate_id=candidate_id, favorite=False)


async def build_candidate_card(session: AsyncSession, need_id: UUID, candidate_id: UUID) -> dict[str, Any]:
    """Card for the employer. Email and phone are omitted until the invitation is accepted."""
    if await _need(session, need_id) is None:
        raise AppError("not_found", "Потребность не найдена", status_code=404)
    candidate = await _candidate(session, candidate_id)
    if candidate is None:
        raise AppError("not_found", "Кандидат не найден", status_code=404)
    status_row = (
        await session.execute(
            text("SELECT status FROM invitations WHERE need_id = :need_id AND candidate_id = :candidate_id"),
            {"need_id": need_id, "candidate_id": candidate_id},
        )
    ).first()
    status = str(status_row[0]) if status_row is not None else None
    contacts = reveal_contacts(status, candidate.email, candidate.phone, viewer="employer")
    skills = list(
        (
            await session.execute(
                text("SELECT skill_id FROM candidate_skills WHERE candidate_id = :id ORDER BY skill_id"),
                {"id": candidate_id},
            )
        )
        .scalars()
        .all()
    )
    projects = [
        str(task)
        for task in (
            await session.execute(
                text("SELECT task FROM projects WHERE candidate_id = :id ORDER BY created_at NULLS LAST LIMIT 20"),
                {"id": candidate_id},
            )
        )
        .scalars()
        .all()
        if task
    ]
    spans = [
        (_as_date(row["start"]), _as_date(row["end"]))
        for row in (
            await session.execute(
                text('SELECT start, "end" FROM experiences WHERE candidate_id = :id'),
                {"id": candidate_id},
            )
        )
        .mappings()
        .all()
    ]
    badge_row = (
        (
            await session.execute(
                text(
                    """
                SELECT discipline, event, place, year
                FROM fsp_achievements
                WHERE candidate_id = :id
                LIMIT 1
                """
                ),
                {"id": candidate_id},
            )
        )
        .mappings()
        .first()
    )
    badge = None
    if badge_row is not None:
        bits = [str(badge_row["event"])]
        if badge_row["place"] is not None:
            bits.append(f"{badge_row['place']} место")
        if badge_row["year"] is not None:
            bits.append(str(badge_row["year"]))
        badge = {"discipline": str(badge_row["discipline"]), "text": ", ".join(bits)}
    card: dict[str, Any] = {
        "candidate_id": candidate.id,
        "display_name": candidate.display_name,
        "full_name_initials": candidate.initials,
        "category": _category(candidate.specialization, candidate.grade),
        "city": candidate.city,
        "experience_years": _experience_years(spans),
        "match": 0,
        "test_score": candidate.grade_score,
        "explanations": [],
        "skills": [str(skill) for skill in skills],
        "projects": projects,
        "invitation_status": status,
        "contacts_revealed": bool(contacts["contacts_revealed"]),
    }
    if badge is not None:
        card["fsp_badge"] = badge
    if contacts["contacts_revealed"]:
        card["email"] = contacts.get("email")
        card["phone"] = contacts.get("phone")
    return card
