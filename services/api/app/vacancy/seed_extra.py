"""Five open demo vacancies attached to seeded companies.

``load_seed`` calls this after companies exist. The insert is skipped when the
vacancies table is not migrated yet, so an older database can still reseed.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

_STRINGS = ARRAY(String())


def _vacancy_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://fsp.local/demo/vacancies/{name}"))


DEMO_VACANCIES: list[dict[str, Any]] = [
    {
        "id": _vacancy_id("payments-backend"),
        "company_id": "bee18ade-6df7-526e-8fdb-49112e58a80b",
        "title": "Backend-разработчик платёжного контура",
        "specialization": "backend",
        "grades": ["middle", "senior"],
        "salary_from": 220_000,
        "salary_to": 350_000,
        "formats": ["remote", "hybrid"],
        "city": "Новосибирск",
        "must_skills": ["go", "postgresql"],
        "description": (
            "Команда развивает платёжный контур: проводит платежи, разбирает инциденты и объясняет правила клиенту банка."
        ),
        "domain": "fintech",
        "status": "open",
    },
    {
        "id": _vacancy_id("delivery-backend"),
        "company_id": "c572ecdd-caa9-544d-8a6c-a1dcc60f6423",
        "title": "Backend-разработчик плеча доставки",
        "specialization": "backend",
        "grades": ["junior", "middle"],
        "salary_from": 140_000,
        "salary_to": 220_000,
        "formats": ["hybrid"],
        "city": "Казань",
        "must_skills": ["python", "postgresql"],
        "description": (
            "Команда следит за плечом доставки и пишет сервисы, которые показывают, где груз задержался дольше обещанного."
        ),
        "domain": "logistics",
        "status": "open",
    },
    {
        "id": _vacancy_id("classroom-frontend"),
        "company_id": "a27c5d90-d524-5f5d-87f7-ed36a90dbe55",
        "title": "Frontend-разработчик учебного кабинета",
        "specialization": "frontend",
        "grades": ["middle"],
        "salary_from": 180_000,
        "salary_to": 260_000,
        "formats": ["remote"],
        "city": "Москва",
        "must_skills": ["react", "typescript"],
        "description": (
            "Нужен разработчик интерфейсов учебного кабинета: списки работ, "
            "попытки учеников и спокойная проверка без лишнего шума."
        ),
        "domain": "edtech",
        "status": "open",
    },
    {
        "id": _vacancy_id("cluster-devops"),
        "company_id": "0d27fff1-bee4-5b80-8c72-a8df8a9d6381",
        "title": "DevOps-инженер контура выкладки",
        "specialization": "devops",
        "grades": ["senior", "lead"],
        "salary_from": 280_000,
        "salary_to": 420_000,
        "formats": ["office", "hybrid"],
        "city": "Санкт-Петербург",
        "must_skills": ["kubernetes", "docker"],
        "description": (
            "Нужен инженер, который держит кластер, выкладку сервисов и ночные дежурства без сюрпризов в понедельник утром."
        ),
        "domain": "gov",
        "status": "open",
    },
    {
        "id": _vacancy_id("shopfloor-data"),
        "company_id": "3babb546-5555-586d-94cc-83892de4135a",
        "title": "Инженер данных сменных показателей",
        "specialization": "data_ml",
        "grades": ["junior", "middle"],
        "salary_from": 160_000,
        "salary_to": 240_000,
        "formats": ["office"],
        "city": "Екатеринбург",
        "must_skills": ["python", "pytorch"],
        "description": ("Ищем инженера данных, который собирает признаки цеха и показывает, какая линия вышла из ритма смены."),
        "domain": "industrial",
        "status": "open",
    },
]

_INSERT = text(
    """
    INSERT INTO vacancies (
        id, company_id, title, specialization, grades, salary_from, salary_to,
        formats, city, must_skills, description, domain, status
    ) VALUES (
        CAST(:id AS uuid), CAST(:company_id AS uuid), :title, :specialization, :grades,
        :salary_from, :salary_to, :formats, :city, :must_skills, :description, :domain, :status
    )
    ON CONFLICT (id) DO UPDATE SET
        company_id = EXCLUDED.company_id,
        title = EXCLUDED.title,
        specialization = EXCLUDED.specialization,
        grades = EXCLUDED.grades,
        salary_from = EXCLUDED.salary_from,
        salary_to = EXCLUDED.salary_to,
        formats = EXCLUDED.formats,
        city = EXCLUDED.city,
        must_skills = EXCLUDED.must_skills,
        description = EXCLUDED.description,
        domain = EXCLUDED.domain,
        status = EXCLUDED.status,
        updated_at = now()
    """
).bindparams(
    bindparam("grades", type_=_STRINGS),
    bindparam("formats", type_=_STRINGS),
    bindparam("must_skills", type_=_STRINGS),
)


async def seed_demo_vacancies(session: AsyncSession) -> int:
    found = await session.scalar(text("SELECT to_regclass('public.vacancies')"))
    if found is None:
        return 0
    await session.execute(_INSERT, DEMO_VACANCIES)
    return len(DEMO_VACANCIES)
