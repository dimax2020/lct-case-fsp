"""Profile extras: seed email attach, consents, standard PDF, employer bank."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pymupdf
import pytest
from app.core.auth import Principal
from app.core.enums import CandidateStatus, Grade, ProjectRole, SkillSource, Specialization
from app.core.models import User
from app.core.provision import email_attach_decision, provision_user
from app.profile.bank import BANK_LIMIT, bank_statement, like_pattern, stack_tokens
from app.profile.fsp import load_achievements
from app.profile.models import Candidate
from app.profile.pdf import EMPTY_FSP_LINE, profile_lines, render_profile_pdf, transliterate
from app.profile.present import candidate_profile
from app.profile.schemas import (
    CandidateBankItem,
    CandidateProfile,
    CandidateSettings,
    CandidateUpdate,
    FspAchievementOut,
    ProjectOut,
    SkillOut,
)
from app.profile.storage import apply_profile_update, settings_view, update_settings
from sqlalchemy.dialects import postgresql

MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "004_profile_extras.py"


class _Rows:
    def __init__(self, rows: list[User]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class FakeSession:
    def __init__(self, by_sub: User | None, email_rows: list[User]) -> None:
        self.by_sub = by_sub
        self.email_rows = email_rows
        self.added: list[User] = []
        self.email_lookups = 0

    async def execute(self, statement: object) -> "_Result":
        return _Result(self.by_sub)

    async def scalars(self, statement: object) -> _Rows:
        self.email_lookups += 1
        return _Rows(self.email_rows)

    def add(self, obj: User) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


class _Result:
    def __init__(self, user: User | None) -> None:
        self._user = user

    def scalar_one_or_none(self) -> User | None:
        return self._user


def _silence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.provision._candidate_hook", None)
    monkeypatch.setattr("app.core.provision._company_hook", None)


def _sql(**kwargs: object) -> str:
    statement = bank_statement(**kwargs)  # type: ignore[arg-type]
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _plain(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split())


def _pdf_text(data: bytes) -> str:
    document = pymupdf.open(stream=data, filetype="pdf")
    try:
        return _plain("\n".join(page.get_text() for page in document))
    finally:
        document.close()


def _profile(**overrides: object) -> CandidateProfile:
    payload: dict[str, object] = {
        "id": uuid4(),
        "full_name": "Анна Смирнова",
        "display_name": "Анна С.",
        "city": "Казань",
        "specialization": Specialization.backend,
        "grade": Grade.middle,
        "status": CandidateStatus.seeking,
        "visible": True,
        "in_pool_eligible": True,
        "skills": [SkillOut(skill_id="python", source=SkillSource.project)],
        "projects": [
            ProjectOut(id=uuid4(), task="Платёжный API", role=ProjectRole.owner, skills=["python"], source="self")
        ],
        "fsp_achievements": [],
    }
    payload.update(overrides)
    return CandidateProfile(**payload)  # type: ignore[arg-type]


def test_email_attach_decision_reuses_seed_email_and_keeps_known_sub() -> None:
    assert email_attach_decision(True, "anna@example.com", True) == "use_sub"
    assert email_attach_decision(True, None, False) == "use_sub"
    assert email_attach_decision(False, "anna@example.com", True) == "attach_email"
    assert email_attach_decision(False, "  anna@example.com  ", True) == "attach_email"
    assert email_attach_decision(False, "anna@example.com", False) == "create"
    assert email_attach_decision(False, None, True) == "create"
    assert email_attach_decision(False, "   ", True) == "create"


async def test_provision_attaches_seed_row_and_does_not_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    _silence(monkeypatch)
    other = User(kc_sub="kc-old", role="candidate", email="anna@example.com")
    seed = User(kc_sub="seed:anna@example.com", role="candidate", email="anna@example.com")
    session = FakeSession(None, [other, seed])
    user = await provision_user(session, Principal(sub="kc-new", role="candidate", email="Anna@Example.com"))
    assert user is seed
    assert seed.kc_sub == "kc-new"
    assert other.kc_sub == "kc-old"
    assert session.added == []
    assert seed.email == "Anna@Example.com"


async def test_provision_creates_when_email_is_new_and_updates_known_sub(monkeypatch: pytest.MonkeyPatch) -> None:
    _silence(monkeypatch)
    session = FakeSession(None, [])
    created = await provision_user(session, Principal(sub="kc-new", role="candidate", email="new@example.com"))
    assert session.added == [created]
    assert created.kc_sub == "kc-new"
    assert created.email == "new@example.com"

    existing = User(kc_sub="kc-1", role="candidate", email="old@example.com")
    again = FakeSession(existing, [existing])
    user = await provision_user(again, Principal(sub="kc-1", role="candidate", email="new@example.com"))
    assert user is existing
    assert user.email == "new@example.com"
    assert again.added == []
    assert again.email_lookups == 0


async def test_provision_without_email_does_not_attach(monkeypatch: pytest.MonkeyPatch) -> None:
    _silence(monkeypatch)
    seed = User(kc_sub="seed:anna@example.com", role="candidate", email="anna@example.com")
    session = FakeSession(None, [seed])
    user = await provision_user(session, Principal(sub="kc-2", role="employer", email=None))
    assert user is not seed
    assert seed.kc_sub == "seed:anna@example.com"
    assert session.added == [user]
    assert session.email_lookups == 0


async def test_attach_still_runs_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []

    async def candidate_hook(session: object, user: User) -> None:
        seen.append(("candidate", user.kc_sub))

    async def company_hook(session: object, user: User) -> None:
        seen.append(("employer", user.kc_sub))

    monkeypatch.setattr("app.core.provision._candidate_hook", candidate_hook)
    monkeypatch.setattr("app.core.provision._company_hook", company_hook)
    seed = User(kc_sub="seed:anna@example.com", role="candidate", email="anna@example.com")
    await provision_user(FakeSession(None, [seed]), Principal(sub="kc-new", role="candidate", email="anna@example.com"))
    employer = await provision_user(
        FakeSession(None, []), Principal(sub="emp-1", role="employer", email="boss@example.com")
    )
    assert seen == [("candidate", "kc-new"), ("employer", employer.kc_sub)]


def test_profile_read_and_patch_keep_consents_and_soft_skills() -> None:
    candidate = Candidate(
        id=uuid4(),
        user_id=uuid4(),
        full_name="Анна Смирнова",
        city="Казань",
        specialization="backend",
        grade="middle",
        status="seeking",
        visible=True,
        formats=["remote"],
        min_salary=120000,
        consent_processing=True,
        consent_publication=False,
        soft_skills=["эмпатия"],
    )
    view = candidate_profile(candidate, [], [], [], [])
    assert view.consent_processing is True
    assert view.consent_publication is False
    assert view.soft_skills == ["эмпатия"]
    assert view.fsp_achievements == []
    apply_profile_update(
        candidate,
        CandidateUpdate(city="Уфа", consent_publication=True, soft_skills=["  менторство  ", "менторство", ""]).model_dump(
            mode="json", exclude_unset=True
        ),
    )
    assert candidate.city == "Уфа"
    assert candidate.consent_processing is True
    assert candidate.consent_publication is True
    assert candidate.soft_skills == ["менторство"]


async def test_settings_persist_consents_and_soft_skills() -> None:
    candidate = SimpleNamespace(
        visible=True,
        hidden_company_ids=[],
        consent_processing=False,
        consent_publication=False,
        soft_skills=[],
        last_active_at=None,
    )
    saved = await update_settings(
        FakeSession(None, []),  # type: ignore[arg-type]
        candidate,  # type: ignore[arg-type]
        CandidateSettings(
            visible=False,
            consent_processing=True,
            consent_publication=True,
            soft_skills=["командная работа", "  командная работа  ", ""],
        ),
    )
    assert saved.visible is False
    assert saved.consent_processing is True
    assert saved.consent_publication is True
    assert saved.soft_skills == ["командная работа"]
    fetched = await settings_view(candidate)  # type: ignore[arg-type]
    assert fetched.soft_skills == ["командная работа"]


def test_empty_fsp_payloads_stay_an_empty_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "fsp.json"
    monkeypatch.setattr("app.profile.fsp.achievements_path", lambda: path)
    path.write_text("[]", encoding="utf-8")
    assert load_achievements("seed:a@b.c", "a@b.c") == []
    path.write_text('{"by_sub": {"seed:a@b.c": []}, "by_email": {"a@b.c": []}}', encoding="utf-8")
    assert load_achievements("seed:a@b.c", "a@b.c") == []
    path.write_text('{"achievements": []}', encoding="utf-8")
    assert load_achievements("seed:a@b.c", "a@b.c") == []
    monkeypatch.setattr("app.profile.fsp.achievements_path", lambda: tmp_path / "missing.json")
    assert load_achievements("seed:a@b.c", "a@b.c") == []


def test_profile_pdf_bytes_and_empty_fsp_line() -> None:
    profile = _profile()
    assert EMPTY_FSP_LINE in profile_lines(profile)
    data = render_profile_pdf(profile)
    assert data.startswith(b"%PDF")
    text = _pdf_text(data)
    assert "Анна Смирнова" in text or "Anna Smirnova" in text
    assert EMPTY_FSP_LINE in text or transliterate(EMPTY_FSP_LINE) in text
    filled = _profile(
        fsp_achievements=[
            FspAchievementOut(id=uuid4(), discipline="алгоритмы", event="Кубок", place=1, year=2024)
        ]
    )
    assert EMPTY_FSP_LINE not in profile_lines(filled)
    filled_text = _pdf_text(render_profile_pdf(filled))
    assert "Кубок" in filled_text or "Kubok" in filled_text


def test_profile_pdf_transliterates_when_no_cyrillic_font(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.profile.pdf.cyrillic_font_path", lambda: None)
    assert transliterate(EMPTY_FSP_LINE) == "Dostizheniy FSP net"
    data = render_profile_pdf(_profile())
    assert data.startswith(b"%PDF")
    text = _pdf_text(data)
    assert "Dostizheniy FSP net" in text
    assert "Anna Smirnova" in text


def test_bank_sql_filters_cap_and_hides_contacts() -> None:
    sql = _sql(specialization="backend", grade="middle", stack="Python, Kafka", fsp=True, q="Анна")
    folded = sql.lower()
    assert f"LIMIT {BANK_LIMIT}" in sql
    assert BANK_LIMIT == 50
    assert "backend" in folded
    assert "middle" in folded
    assert "python" in folded
    assert "kafka" in folded
    assert "анна" in folded
    assert "fsp_achievements" in folded
    assert "visible" in folded
    assert "contact_email" not in folded
    assert "phone" not in folded
    assert "users" not in folded
    hidden = _sql(fsp=False)
    assert "fsp_achievements" in hidden.lower()
    assert "NOT" in hidden.upper()
    assert f"LIMIT {BANK_LIMIT}" in _sql()


def test_bank_helpers_and_public_fields() -> None:
    assert like_pattern("a%b_c") == "%a\\%b\\_c%"
    assert stack_tokens(" Python, python  Kafka ") == ["python", "kafka"]
    assert stack_tokens("  ") == []
    assert set(CandidateBankItem.model_fields) == {
        "id",
        "display_name",
        "specialization",
        "grade",
        "city",
        "skills",
        "has_fsp",
        "test_score",
    }


def test_migration_adds_profile_columns_if_missing() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision = "003_grade_policy"' in text
    assert text.count("ADD COLUMN IF NOT EXISTS") == 3
    assert "consent_processing" in text
    assert "consent_publication" in text
    assert "soft_skills" in text


def test_candidate_routes_keep_me_ahead_of_the_bank() -> None:
    from app.main import app

    paths = [path for path in app.openapi()["paths"] if path.startswith("/api/v1/candidates")]
    me = paths.index("/api/v1/candidates/me")
    pdf = paths.index("/api/v1/candidates/me/profile.pdf")
    bank = paths.index("/api/v1/candidates")
    assert me < pdf < bank
    assert "/api/v1/candidates/me/settings" in paths
