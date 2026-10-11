"""Deterministic synthetic seed for the FSP career demo.

Texts come from templates and a fixed random stream. Nothing here calls a model.
Run from the repo root: ``services/api/.venv/bin/python seed/generate.py``.
"""

from __future__ import annotations

import json
import math
import random
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SEED_DIR))

import catalog
from eval.label import relevance
from eval.metrics import binary_token_cosine, fit_sim_thresholds

SEED = 20261011
TODAY = date(2026, 10, 11)
NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)
NS = uuid.UUID("a3f1c2e0-7b44-5d18-9c01-6e5d4c3b2a10")
DEMO_KEY = "cand-backend-000"
DEMO_EMAIL = "candidate@demo.fsp"
EMPLOYER_EMAIL = "employer@demo.fsp"
ADMIN_EMAIL = "admin@demo.fsp"

# Mirrors MVP TZ §6 only so the demo script can be checked before agent D
# replaces score_pair. eval/run.py does not use these numbers.
E_WEIGHTS = {
    "intern": {"must_cov": 0.25, "grade_fit": 0.20, "ef": 0.10, "skill_avg": 0.20, "fsp": 0.15, "fresh": 0.10, "nice_cov": 0.0},
    "junior": {"must_cov": 0.25, "grade_fit": 0.20, "ef": 0.10, "skill_avg": 0.20, "fsp": 0.15, "fresh": 0.10, "nice_cov": 0.0},
    "middle": {"must_cov": 0.30, "grade_fit": 0.20, "ef": 0.25, "skill_avg": 0.15, "fsp": 0.05, "fresh": 0.05, "nice_cov": 0.0},
    "senior": {"must_cov": 0.20, "grade_fit": 0.15, "ef": 0.40, "skill_avg": 0.10, "fsp": 0.03, "fresh": 0.05, "nice_cov": 0.07},
    "lead": {"must_cov": 0.20, "grade_fit": 0.15, "ef": 0.40, "skill_avg": 0.10, "fsp": 0.03, "fresh": 0.05, "nice_cov": 0.07},
}
C_DEFAULT = {"salary_fit": 0.35, "format_fit": 0.20, "stack_interest": 0.20, "domain_fit": 0.10, "benefits": 0.10, "process": 0.05}
_SENIOR = 0.60 / 0.65
C_SENIOR = {
    "salary_fit": 0.40,
    "format_fit": C_DEFAULT["format_fit"] * _SENIOR,
    "stack_interest": C_DEFAULT["stack_interest"] * _SENIOR,
    "domain_fit": C_DEFAULT["domain_fit"] * _SENIOR,
    "benefits": C_DEFAULT["benefits"] * _SENIOR,
    "process": C_DEFAULT["process"] * _SENIOR,
}
BENEFITS = ("dms", "accreditation", "flexible_start")
_RECRUITERS = (
    "Марина Орлова",
    "Илья Белов",
    "Софья Морозова",
    "Кирилл Волков",
    "Дарья Соколова",
    "Егор Лебедев",
    "Алина Козлова",
    "Роман Новиков",
    "Вера Фролова",
    "Павел Семёнов",
    "Ксения Голубева",
    "Денис Виноградов",
    "Полина Богданова",
    "Глеб Воробьёв",
    "Таисия Федотова",
)
GRADE_ORDER = ("intern", "junior", "middle", "senior", "lead")
SKILL_COUNT = {"intern": (2, 3), "junior": (2, 4), "middle": (3, 5), "senior": (4, 6), "lead": (4, 6)}
N_EXP = {"intern": 1, "junior": 1, "middle": 2, "senior": 2, "lead": 3}
N_PROJ = {"intern": 1, "junior": 1, "middle": 1, "senior": 2, "lead": 2}
YEARS = {"intern": 0, "junior": 1, "middle": 3, "senior": 6, "lead": 9}
SALARY = {
    "intern": (50_000, 80_000),
    "junior": (90_000, 150_000),
    "middle": (160_000, 280_000),
    "senior": (280_000, 420_000),
    "lead": (400_000, 650_000),
}
SCORE = {"intern": (48, 8), "junior": (62, 8), "middle": (74, 7), "senior": (84, 6), "lead": (91, 4)}
SOURCE_WEIGHTS = {
    "intern": (("resume", 60), ("project", 30), ("test", 10)),
    "junior": (("resume", 45), ("project", 30), ("test", 25)),
    "middle": (("test", 45), ("project", 30), ("resume", 25)),
    "senior": (("test", 55), ("project", 25), ("resume", 20)),
    "lead": (("test", 60), ("project", 25), ("resume", 15)),
}
FORMATS = (
    (["remote"], 40),
    (["hybrid"], 25),
    (["office"], 15),
    (["remote", "hybrid"], 12),
    (["hybrid", "office"], 8),
)
STATUSES = (("seeking", 75), ("open", 15), ("paused", 10))
GOLD_KEYS = (
    "need-demo-kafka",
    "need-backend-senior-go",
    "need-backend-lead-platform",
    "need-frontend-react",
    "need-frontend-senior-react",
    "need-frontend-junior-middle",
    "need-ml-pytorch",
    "need-ml-kafka",
    "need-devops-middle",
    "need-devops-middle-go",
)
INVITE_STATUSES = (
    ["sent"] * 18 + ["viewed"] * 14 + ["accepted"] * 16 + ["declined"] * 14 + ["expired"] * 10 + ["revoked"] * 8
)
DECLINE = ("salary", "stack", "format", "found_job", "other")
DETAIL = {
    "backend": (
        "Сервис принимал запросы соседней команды и писал ошибку так, чтобы её можно было прочитать без автора.",
        "Ночная пачка больше не копилась до утра: сбой оставался в журнале, а не в чужой памяти.",
    ),
    "frontend": (
        "Экран показывал пустое состояние и ошибку сети отдельно, чтобы человек не думал, что данных нет.",
        "Фильтр переживал обновление страницы, и возврат из карточки не сбрасывал список.",
    ),
    "data_ml": (
        "Пересчёт писал, откуда взялись строки, и повтор на том же наборе не удваивал показатель.",
        "Пустой пример не получал оценку: правило останавливалось и оставляло причину.",
    ),
    "devops": (
        "Сборка поднималась по заметке, а откат был отдельным шагом, а не восстановлением машины.",
        "Падение одного шага оставляло имя версии, а не безымянный мусор на стенде.",
    ),
}


def sid(key: str) -> str:
    return str(uuid.uuid5(NS, key))


def pick(rng: random.Random, pairs: tuple) -> object:
    total = sum(weight for _, weight in pairs)
    cursor = rng.randrange(total)
    acc = 0
    for value, weight in pairs:
        acc += weight
        if cursor < acc:
            return value
    return pairs[-1][0]


def gauss_int(rng: random.Random, mean: int, std: int, low: int, high: int) -> int:
    value = int(round(rng.gauss(mean, std)))
    return max(low, min(high, value))


def salary_for(rng: random.Random, grade: str) -> int:
    low, high = SALARY[grade]
    steps = (high - low) // 10_000
    return low + rng.randint(0, steps) * 10_000


def female_last(last: str) -> str:
    if last.endswith(("ов", "ев", "ёв", "ин", "ын")):
        return last + "а"
    return last


def load_stop(path: Path) -> list[str]:
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.split("#", 1)[0].strip().casefold().replace("ё", "е")
        if item:
            items.append(item)
    return sorted(set(items))


def forbidden(name: str, stop: list[str]) -> str | None:
    norm = name.casefold().replace("ё", "е")
    for item in stop:
        if len(item) < 4:
            if norm == item:
                return item
        elif item in norm:
            return item
    return None


def assert_allowed(names: list[str], stop: list[str]) -> None:
    for name in names:
        hit = forbidden(name, stop)
        if hit:
            raise RuntimeError(f"company name {name!r} matches stop-list entry {hit!r}")


def skill_label(skill_id: str) -> str:
    return catalog.SKILL_NAMES[skill_id][0]


def family_for(spec: str, skills: list[str]) -> str:
    owned = set(skills)
    if "kafka" in owned:
        return "stream-kafka"
    if "pytorch" in owned:
        return "ml-train"
    if spec == "frontend":
        return "frontend-ui"
    if spec == "devops" or "kubernetes" in owned or "docker" in owned:
        return "devops-cluster"
    if "postgresql" in owned:
        return "warehouse-sql"
    return "backend-api"


def people_pool(rng: random.Random) -> list[tuple[str, bool, str]]:
    pool: list[tuple[str, bool, str]] = []
    for first in catalog.FIRST_M:
        for last in catalog.LAST:
            pool.append((first, False, last))
    for first in catalog.FIRST_F:
        for last in catalog.LAST:
            pool.append((first, True, last))
    rng.shuffle(pool)
    return pool


def make_phone(rng: random.Random) -> str:
    return "+79" + f"{rng.randrange(10**9):09d}"


def make_skills(rng: random.Random, spec: str, grade: str) -> list[dict]:
    pool = catalog.SKILL_POOL[spec]
    low, high = SKILL_COUNT[grade]
    high = min(high, len(pool))
    low = min(low, high)
    chosen = rng.sample(pool, rng.randint(low, high))
    rows = []
    mean, std = SCORE[grade]
    for skill_id in chosen:
        source = str(pick(rng, SOURCE_WEIGHTS[grade]))
        score = gauss_int(rng, mean, std, 20, 100) if source == "test" else None
        rows.append({"skill_id": skill_id, "score": score, "source": source})
    return rows


def story(rng: random.Random, spec: str, skills: list[str], company: str) -> str:
    names = ", ".join(skill_label(skill) for skill in skills[:3]) or "внутренние инструменты"
    detail = rng.choice(DETAIL[spec])
    return (
        f"Компания {company}: задачи вокруг {names}. {detail} "
        "Рядом была маленькая команда, ревью не копилось дольше дня, а результат можно было показать на примере."
    )


def make_candidate(rng: random.Random, spec: str, index: int, person: tuple[str, bool, str] | None) -> dict:
    key = f"cand-{spec}-{index:03d}"
    demo = key == DEMO_KEY
    if demo:
        full_name = "Алексей Кузнецов"
        email = DEMO_EMAIL
    else:
        assert person is not None
        first, female, last = person
        last_name = female_last(last) if female else last
        patr = catalog.PATR_F[index % len(catalog.PATR_F)] if female else catalog.PATR_M[index % len(catalog.PATR_M)]
        full_name = f"{first} {patr} {last_name}"
        email = f"{key}@seed.fsp"
    user_id = sid(f"user:{email}")
    candidate_id = sid(f"candidate:{email}")
    return {
        "id": candidate_id,
        "key": key,
        "email": email,
        "pool_role": "demo" if demo else None,
        "user": {"id": user_id, "kc_sub": f"seed:{email}", "role": "candidate", "email": email},
        "full_name": full_name,
        "city": catalog.CITIES[0] if demo else rng.choice(catalog.CITIES),
        "specialization": spec,
        "grade": "middle" if demo else "junior",
        "grade_score": 90 if demo else 60,
        "min_salary": 220_000 if demo else 120_000,
        "formats": ["remote"],
        "status": "seeking",
        "visible": True,
        "liked_skills": [],
        "disliked_skills": [],
        "liked_domains": ["fintech"] if demo else [],
        "blocked_domains": [],
        "last_active_at": NOW.isoformat(),
        "phone": "+79130001122" if demo else make_phone(rng),
        "contact_email": email,
        "skills": [],
        "experiences": [],
        "projects": [],
        "evidence": [],
        "fsp": [],
        "resume": None,
    }


def fill_candidate(rng: random.Random, candidate: dict, grade: str) -> None:
    spec = candidate["specialization"]
    candidate["grade"] = grade
    low, high = {"intern": (35, 55), "junior": (50, 68), "middle": (65, 82), "senior": (78, 92), "lead": (88, 98)}[grade]
    candidate["grade_score"] = 90 if candidate["pool_role"] == "demo" else rng.randint(low, high)
    candidate["min_salary"] = 220_000 if candidate["pool_role"] == "demo" else salary_for(rng, grade)
    candidate["formats"] = ["remote"] if candidate["pool_role"] == "demo" else list(pick(rng, FORMATS))
    candidate["status"] = "seeking" if candidate["pool_role"] == "demo" else str(pick(rng, STATUSES))
    candidate["visible"] = True if candidate["pool_role"] == "demo" else rng.randrange(100) < 95
    skills = make_skills(rng, spec, grade)
    candidate["skills"] = skills
    skill_ids = [row["skill_id"] for row in skills]
    liked_domain = rng.choice(catalog.DOMAINS)
    candidate["liked_domains"] = ["fintech"] if candidate["pool_role"] == "demo" else [liked_domain]
    if candidate["pool_role"] != "demo" and rng.randrange(100) < 12:
        blocked = rng.choice([item for item in catalog.DOMAINS if item != liked_domain])
        candidate["blocked_domains"] = [blocked]
    extra = [skill for skill in catalog.SKILL_POOL[spec] if skill not in skill_ids]
    disliked = []
    if extra and candidate["pool_role"] != "demo" and rng.randrange(100) < 10:
        disliked = [rng.choice(extra)]
    candidate["disliked_skills"] = disliked
    candidate["liked_skills"] = list(skill_ids) if candidate["pool_role"] == "demo" else list(skill_ids[:2] or skill_ids)
    days = 0 if candidate["pool_role"] == "demo" else rng.randint(0, 90)
    candidate["last_active_at"] = (NOW - timedelta(days=days)).isoformat()
    company = "Пыльный Абак" if candidate["pool_role"] == "demo" else rng.choice(catalog.PAST_COMPANIES)
    exp_skills = skill_ids or catalog.SKILL_POOL[spec][:1]
    experiences = []
    for index in range(N_EXP[grade]):
        start = TODAY - timedelta(days=365 * max(YEARS[grade], 1) + 30 * index + rng.randint(0, 40))
        end = None if index == 0 else start + timedelta(days=200 + rng.randint(0, 300))
        if end and end > TODAY:
            end = TODAY - timedelta(days=10)
        description = story(rng, spec, exp_skills, company if index == 0 else rng.choice(catalog.PAST_COMPANIES))
        experiences.append(
            {
                "id": sid(f"experience:{candidate['email']}:{index}"),
                "company": company if index == 0 else rng.choice(catalog.PAST_COMPANIES),
                "role": catalog.ROLE_RU[spec][grade],
                "start": start.isoformat(),
                "end": end.isoformat() if end else None,
                "description": description,
                "evidence_span": description,
                "skills": list(exp_skills),
            }
        )
    projects = []
    for index in range(N_PROJ[grade]):
        proj_skills = exp_skills[: max(1, min(3, len(exp_skills)))]
        task = story(rng, spec, proj_skills, experiences[0]["company"])
        projects.append(
            {
                "id": sid(f"project:{candidate['email']}:{index}"),
                "task": task,
                "role": str(pick(rng, (("contributor", 50), ("owner", 30), ("participant", 20)))),
                "skills": list(proj_skills),
                "scale": rng.choice(("одна команда", "несколько смежных сервисов", "внутренний кабинет")),
                "outcome": "Задачу довели до использования соседней командой.",
                "date": (TODAY - timedelta(days=40 * (index + 1))).isoformat(),
                "url": None,
                "source": "self",
            }
        )
    candidate["experiences"] = experiences
    candidate["projects"] = projects


def render_need(spec: dict) -> str:
    parts = [spec["intro"], *[item["task"] for item in spec["requirements"]], spec["outro"], catalog.PAD]
    return " ".join(" ".join(part.split()) for part in parts)


def assign_company_indexes(needs: list[dict], companies: list[dict]) -> list[int]:
    counts = [0] * len(companies)
    assigned = [0] * len(needs)
    assigned[0] = 0
    counts[0] = 1
    for index, need in enumerate(needs):
        if index == 0:
            continue
        options = [pos for pos, company in enumerate(companies) if company["domain"] == need["domain"]]
        if not options:
            options = list(range(len(companies)))
        options.sort(key=lambda pos: (counts[pos], pos))
        chosen = options[0]
        assigned[index] = chosen
        counts[chosen] += 1
    return assigned


def build_companies() -> list[dict]:
    benefit_cycle = (
        ["dms", "accreditation", "flexible_start"],
        ["dms"],
        ["accreditation", "flexible_start"],
        ["dms", "flexible_start"],
        ["accreditation"],
    )
    companies = []
    for index, raw in enumerate(catalog.HIRING_COMPANIES):
        email = EMPLOYER_EMAIL if index == 0 else f"employer-{index:02d}@seed.fsp"
        name = _RECRUITERS[index]
        companies.append(
            {
                "id": sid(f"company:{raw['name']}"),
                "name": raw["name"],
                "city": raw["city"],
                "size": raw["size"],
                "domain": raw["domain"],
                "industry": catalog.DOMAIN_RU[raw["domain"]],
                "about": raw["about"],
                "benefits": list(benefit_cycle[0] if index == 0 else benefit_cycle[index % len(benefit_cycle)]),
                "user": {"id": sid(f"user:{email}"), "kc_sub": f"seed:{email}", "role": "employer", "email": email},
                "recruiter_contact": {
                    "name": name,
                    "email": email,
                    "phone": "+73830001122" if index == 0 else f"+7800{index:07d}",
                },
            }
        )
    return companies


def build_needs(companies: list[dict]) -> list[dict]:
    specs = catalog.NEED_SPECS
    indexes = assign_company_indexes(specs, companies)
    needs = []
    for spec, company_index in zip(specs, indexes, strict=True):
        company = companies[company_index]
        description = render_need(spec)
        city = company["city"] if set(spec["formats"]) & {"office", "hybrid"} else None
        requirements = []
        for req_index, req in enumerate(spec["requirements"]):
            requirements.append(
                {
                    "id": sid(f"requirement:{spec['key']}:{req_index}"),
                    "task": req["task"],
                    "domain": spec["domain"],
                    "skills": list(req["skills"]),
                    "scale": req["scale"],
                    "kind": req["kind"],
                    "family": req["family"],
                    "evidence_span": req["task"],
                }
            )
        needs.append(
            {
                "id": sid(f"need:{spec['key']}"),
                "key": spec["key"],
                "company_id": company["id"],
                "company_index": company_index,
                "title": spec["title"],
                "specialization": spec["specialization"],
                "grades": list(spec["grades"]),
                "salary_from": spec["salary_from"],
                "salary_to": spec["salary_to"],
                "formats": list(spec["formats"]),
                "city": city,
                "must_skills": list(spec["must_skills"]),
                "nice_skills": list(spec["nice_skills"]),
                "description": description,
                "domain": spec["domain"],
                "stages": spec["stages"],
                "status": "open",
                "requirements": requirements,
                "gold": spec["key"] in GOLD_KEYS,
            }
        )
    return needs


def shape_demo(candidate: dict, need: dict) -> None:
    tasks = {tuple(req["skills"]): req["task"] for req in need["requirements"]}
    kafka = tasks[("kafka",)]
    go_task = tasks[("go",)]
    postgres = tasks[("postgresql",)]
    candidate["city"] = "Новосибирск"
    candidate["grade"] = "middle"
    candidate["grade_score"] = 90
    candidate["min_salary"] = 220_000
    candidate["formats"] = ["remote"]
    candidate["status"] = "seeking"
    candidate["visible"] = True
    candidate["liked_skills"] = ["kafka", "go", "postgresql", "docker", "kubernetes"]
    candidate["disliked_skills"] = []
    candidate["liked_domains"] = ["fintech"]
    candidate["blocked_domains"] = []
    candidate["last_active_at"] = NOW.isoformat()
    candidate["skills"] = [
        {"skill_id": "kafka", "score": 98, "source": "test"},
        {"skill_id": "go", "score": 97, "source": "test"},
        {"skill_id": "postgresql", "score": 96, "source": "test"},
        {"skill_id": "docker", "score": None, "source": "resume"},
        {"skill_id": "kubernetes", "score": None, "source": "project"},
    ]
    experience = (
        f"В Пыльном Абаке делал сервис вердиктов для платёжной смены. {go_task} {postgres} "
        "Задержка разбора держалась в минутах, а не дожидалась утренней пачки."
    )
    candidate["experiences"] = [
        {
            "id": sid(f"experience:{candidate['email']}:0"),
            "company": "Пыльный Абак",
            "role": "backend-разработчик",
            "start": "2023-04-01",
            "end": "2026-08-01",
            "description": experience,
            "evidence_span": experience,
            "skills": ["go", "postgresql", "kafka"],
        }
    ]
    candidate["projects"] = [
        {
            "id": sid(f"project:{candidate['email']}:0"),
            "task": kafka,
            "role": "owner",
            "skills": ["kafka", "go", "postgresql"],
            "scale": "хакатон, поток платежей",
            "outcome": "Команда разобрала кейс по теме, а не по утренней выгрузке.",
            "date": "2025-06-15",
            "url": None,
            "source": "self",
        }
    ]
    lines = [
        "Алексей Кузнецов",
        "Новосибирск",
        "candidate@demo.fsp",
        "Backend-разработчик, грейд middle",
        "",
        "Опыт",
        "Пыльный Абак — backend-разработчик, апрель 2023 — август 2026",
        experience,
        "",
        "Проекты",
        "Хакатон ФСП «Антифрод на Kafka», роль owner, июнь 2025",
        kafka,
        "",
        "Навыки",
        "Kafka, Go, PostgreSQL, Docker, Kubernetes",
    ]
    raw = "\n".join(lines)
    for span in (experience, kafka, go_task, postgres):
        if span not in raw and span not in experience:
            raise RuntimeError("demo resume is missing an evidence span")
    if go_task not in experience or postgres not in experience or kafka not in raw:
        raise RuntimeError("demo spans are not exact substrings")
    candidate["resume"] = {
        "id": sid(f"resume:{candidate['email']}"),
        "file_path": "seed/demo/candidate.pdf",
        "status": "confirmed",
        "raw_text": raw,
        "parsed_json": {
            "experiences": [
                {
                    "company": "Пыльный Абак",
                    "role": "backend-разработчик",
                    "start": "2023-04-01",
                    "end": "2026-08-01",
                    "description": experience,
                    "evidence_span": experience,
                }
            ],
            "skills": [
                {"name": "Kafka", "evidence_span": "Kafka, Go, PostgreSQL, Docker, Kubernetes"},
                {"name": "Go", "evidence_span": "Kafka, Go, PostgreSQL, Docker, Kubernetes"},
                {"name": "PostgreSQL", "evidence_span": "Kafka, Go, PostgreSQL, Docker, Kubernetes"},
                {"name": "Docker", "evidence_span": "Kafka, Go, PostgreSQL, Docker, Kubernetes"},
                {"name": "Kubernetes", "evidence_span": "Kafka, Go, PostgreSQL, Docker, Kubernetes"},
            ],
            "projects": [
                {
                    "task": kafka,
                    "role": "owner",
                    "skills": ["Kafka", "Go", "PostgreSQL"],
                    "outcome": "Команда разобрала кейс по теме, а не по утренней выгрузке.",
                    "evidence_span": kafka,
                }
            ],
        },
    }


def shape_rival(candidate: dict, confirmed: bool) -> None:
    salary = {"junior": 140_000, "middle": 240_000, "senior": 300_000}[candidate["grade"]]
    kafka_score = 70 if confirmed else None
    candidate["pool_role"] = "confirmed" if confirmed else "resume"
    candidate["skills"] = [
        {"skill_id": "kafka", "score": kafka_score, "source": "test" if confirmed else "resume"},
        {"skill_id": "go", "score": None, "source": "resume"},
        {"skill_id": "postgresql", "score": None, "source": "resume"},
    ]
    candidate["min_salary"] = salary
    candidate["formats"] = ["remote"]
    candidate["status"] = "seeking"
    candidate["visible"] = True
    candidate["blocked_domains"] = [item for item in candidate["blocked_domains"] if item != "fintech"]
    candidate["liked_skills"] = ["kafka", "go", "postgresql"]
    candidate["disliked_skills"] = []
    candidate["last_active_at"] = (NOW - timedelta(days=45)).isoformat()
    candidate["fsp"] = []
    company = candidate["experiences"][0]["company"] if candidate["experiences"] else "Пыльный Абак"
    description = (
        f"Поддержка внутренних сервисов в компании {company}: очереди сообщений, правки схемы таблиц "
        f"и ответы соседним командам. В ежедневной работе были Kafka, Go и PostgreSQL, "
        f"без отдельного контура антифрода и без своей витрины кейсов."
    )
    candidate["experiences"] = [
        {
            "id": sid(f"experience:{candidate['email']}:0"),
            "company": company,
            "role": catalog.ROLE_RU["backend"][candidate["grade"]],
            "start": "2022-03-01",
            "end": "2024-11-01",
            "description": description,
            "evidence_span": description,
            "skills": ["kafka", "go", "postgresql"],
        }
    ]
    candidate["projects"] = [
        {
            "id": sid(f"project:{candidate['email']}:0"),
            "task": (
                "Внутренний сервис заявок: форма, статус и уведомление коллегам. "
                "Kafka здесь была транспортом между двумя сервисами, без платёжных тем и без правил антифрода."
            ),
            "role": "contributor",
            "skills": ["kafka", "go"],
            "scale": "десятки запросов в минуту",
            "outcome": "Сервис остался внутренним.",
            "date": "2024-05-01",
            "url": None,
            "source": "self",
        }
    ]


def take_rivals(backend: list[dict]) -> None:
    plan = (
        [("junior", "confirmed")] * 5
        + [("middle", "confirmed")] * 2
        + [("senior", "confirmed")] * 1
        + [("junior", "resume")] * 5
        + [("middle", "resume")] * 5
        + [("senior", "resume")] * 5
    )
    used: set[str] = set()
    for grade, role in plan:
        chosen = next(
            item
            for item in backend
            if item["key"] != DEMO_KEY and item["grade"] == grade and item["id"] not in used and item["pool_role"] is None
        )
        used.add(chosen["id"])
        shape_rival(chosen, confirmed=role == "confirmed")


def strip_kafka(candidates: list[dict]) -> None:
    protected = {item["id"] for item in candidates if item.get("pool_role") in {"demo", "confirmed", "resume"}}
    for candidate in candidates:
        if candidate["specialization"] != "backend" or candidate["id"] in protected:
            continue
        candidate["skills"] = [row for row in candidate["skills"] if row["skill_id"] != "kafka"]
        for project in candidate["projects"]:
            project["skills"] = [skill for skill in project["skills"] if skill != "kafka"]
        for experience in candidate["experiences"]:
            experience["skills"] = [skill for skill in experience.get("skills", []) if skill != "kafka"]


def achievement(candidate: dict, rng: random.Random, *, demo: bool) -> dict:
    if demo:
        return {
            "id": sid(f"fsp:{candidate['email']}:0"),
            "discipline": "backend",
            "event": "Хакатон ФСП «Антифрод на Kafka»",
            "place": 1,
            "year": 2025,
            "summary": "Собрали поток антифрод-событий и показали кейс по теме Kafka, а не по утренней выгрузке.",
        }
    events = {
        "backend": "Хакатон ФСП «Платёжный контур»",
        "frontend": "Хакатон ФСП «Витрина»",
        "data_ml": "Чемпионат ФСП по данным",
        "devops": "Хакатон ФСП «Кластер»",
    }
    same = rng.randrange(100) < 70
    spec = candidate["specialization"]
    discipline = spec if same else rng.choice([item for item in catalog.SPECS if item != spec])
    return {
        "id": sid(f"fsp:{candidate['email']}:0"),
        "discipline": discipline,
        "event": events[discipline],
        "place": rng.choice([1, 2, 3, 5, None]),
        "year": rng.choice([2023, 2024, 2025]),
        "summary": "Командное достижение ФСП по профильной или соседней дисциплине.",
    }


def assign_fsp(candidates: list[dict], rng: random.Random) -> None:
    demo = next(item for item in candidates if item["key"] == DEMO_KEY)
    eligible = [item for item in candidates if item.get("pool_role") not in {"confirmed", "resume"} and item is not demo]
    if len(eligible) < 119:
        raise RuntimeError("not enough candidates for the 30 percent FSP quota")
    for candidate in rng.sample(eligible, 119):
        candidate["fsp"] = [achievement(candidate, rng, demo=False)]
    demo["fsp"] = [achievement(demo, rng, demo=True)]
    for candidate in candidates:
        if not candidate["fsp"]:
            candidate["fsp"] = []


def attach_fsp_skill(candidates: list[dict]) -> None:
    for candidate in candidates:
        if candidate.get("pool_role") == "demo":
            continue
        if not any(item["discipline"] == candidate["specialization"] for item in candidate["fsp"]):
            continue
        pool = [skill for skill in catalog.SKILL_POOL[candidate["specialization"]] if skill != "kafka"]
        if not pool:
            continue
        skill_id = pool[0]
        if any(row["skill_id"] == skill_id and row["source"] == "fsp_id" for row in candidate["skills"]):
            continue
        candidate["skills"].append({"skill_id": skill_id, "score": None, "source": "fsp_id"})


def refresh_evidence(candidate: dict) -> None:
    units = []
    domain = candidate["liked_domains"][0] if candidate["liked_domains"] else None
    for index, project in enumerate(candidate["projects"]):
        skills = list(project["skills"])
        units.append(
            {
                "id": sid(f"evidence:{candidate['email']}:project:{index}"),
                "origin": "project",
                "origin_id": project["id"],
                "task": project["task"],
                "domain": domain,
                "skills": skills,
                "role": project["role"],
                "date": project["date"],
                "trust": 0.35,
                "evidence_span": project["task"],
                "family": family_for(candidate["specialization"], skills),
            }
        )
    for index, experience in enumerate(candidate["experiences"]):
        skills = list(experience.get("skills") or [])
        units.append(
            {
                "id": sid(f"evidence:{candidate['email']}:experience:{index}"),
                "origin": "experience",
                "origin_id": experience["id"],
                "task": experience["description"],
                "domain": domain,
                "skills": skills,
                "role": "contributor",
                "date": experience["end"] or experience["start"],
                "trust": 0.6,
                "evidence_span": experience["evidence_span"],
                "family": family_for(candidate["specialization"], skills),
            }
        )
    for index, item in enumerate(candidate["fsp"]):
        skills = ["kafka"] if item["event"].startswith("Хакатон ФСП «Антифрод") else []
        task = f"{item['event']}. {item['summary']}"
        units.append(
            {
                "id": sid(f"evidence:{candidate['email']}:fsp:{index}"),
                "origin": "fsp",
                "origin_id": item["id"],
                "task": task,
                "domain": item["discipline"] if item["discipline"] in catalog.DOMAINS else domain,
                "skills": skills,
                "role": "owner" if candidate.get("pool_role") == "demo" else "participant",
                "date": f"{item['year']}-06-01" if item.get("year") else None,
                "trust": 1.0,
                "evidence_span": item["summary"],
                "family": "stream-kafka" if "kafka" in skills else family_for(item["discipline"], skills),
            }
        )
    candidate["evidence"] = units


def build_invitations(rng: random.Random, needs: list[dict], candidates: list[dict], companies: list[dict]) -> list[dict]:
    by_spec: dict[str, list[dict]] = {spec: [] for spec in catalog.SPECS}
    for candidate in candidates:
        if candidate["email"] == DEMO_EMAIL:
            continue
        by_spec[candidate["specialization"]].append(candidate)
    pairs: list[tuple[dict, dict]] = []
    for need in needs:
        for candidate in by_spec[need["specialization"]]:
            pairs.append((need, candidate))
    rng.shuffle(pairs)
    company_by_id = {company["id"]: company for company in companies}
    chosen: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for need, candidate in pairs:
        key = (need["id"], candidate["id"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append((need, candidate))
        if len(chosen) == 80:
            break
    if len(chosen) != 80:
        raise RuntimeError(f"expected 80 invitations, got {len(chosen)}")
    statuses = list(INVITE_STATUSES)
    rng.shuffle(statuses)
    invitations = []
    for index, ((need, candidate), status) in enumerate(zip(chosen, statuses, strict=True)):
        created = datetime(2026, 8, 1, 10, 0, tzinfo=UTC) + timedelta(days=index % 40)
        company = company_by_id[need["company_id"]]
        row = {
            "id": sid(f"invitation:{need['key']}:{candidate['email']}"),
            "need_id": need["id"],
            "candidate_id": candidate["id"],
            "status": status,
            "title": need["title"],
            "message": "Здравствуйте! Посмотрели профиль и хотим обсудить задачу команды. Вилка в карточке приглашения.",
            "salary_from": need["salary_from"],
            "salary_to": need["salary_to"],
            "contact_channel": "email",
            "contact_value": company["recruiter_contact"]["email"],
            "deadline": (created + timedelta(days=14)).isoformat() if status in {"sent", "viewed"} else None,
            "decline_reason": DECLINE[index % len(DECLINE)] if status == "declined" else None,
            "hiring_stage": "interview" if status == "accepted" and index % 2 == 0 else "offer" if status == "accepted" else None,
            "created_at": created.isoformat(),
            "viewed_at": (created + timedelta(days=1)).isoformat() if status in {"viewed", "accepted", "declined"} else None,
            "accepted_at": (created + timedelta(days=3)).isoformat() if status == "accepted" else None,
            "declined_at": (created + timedelta(days=2)).isoformat() if status == "declined" else None,
            "expired_at": (created + timedelta(days=15)).isoformat() if status == "expired" else None,
            "revoked_at": (created + timedelta(days=4)).isoformat() if status == "revoked" else None,
        }
        invitations.append(row)
    return invitations


def assign_ranks(candidates: list[dict]) -> None:
    for spec in catalog.SPECS:
        group = [item for item in candidates if item["specialization"] == spec]
        group.sort(key=lambda item: (-item["grade_score"], item["id"]))
        for rank, candidate in enumerate(group, start=1):
            candidate["category_rank"] = rank
            candidate["category_size"] = len(group)
            candidate["ready_for_next"] = candidate["grade"] != "lead" and candidate["grade_score"] >= 85


def coverage(candidate: dict, skill_id: str) -> float:
    best = 0.0
    for row in candidate["skills"]:
        if row["skill_id"] != skill_id:
            continue
        if row["source"] == "test":
            best = max(best, (row["score"] or 0) / 100)
        elif row["source"] in {"resume", "project"}:
            best = max(best, 0.4)
        elif row["source"] == "fsp_id":
            best = max(best, 0.8)
    return best


def grade_distance(left: str, right: str) -> int:
    return abs(GRADE_ORDER.index(left) - GRADE_ORDER.index(right))


def passes_sql(candidate: dict, need: dict) -> bool:
    spec = candidate["specialization"]
    if spec != need["specialization"] and spec not in catalog.ADJACENT[need["specialization"]]:
        return False
    distance = min(grade_distance(candidate["grade"], grade) for grade in need["grades"])
    if distance > 1:
        return False
    if need["salary_to"] < (candidate["min_salary"] or 0) * 0.9:
        return False
    if not (set(candidate["formats"]) & set(need["formats"])):
        return False
    if candidate["status"] not in {"seeking", "open"} or not candidate["visible"]:
        return False
    if need["domain"] in candidate["blocked_domains"]:
        return False
    return True


def passes_gate(candidate: dict, need: dict) -> bool:
    return all(coverage(candidate, skill) >= 0.3 for skill in need["must_skills"])


def fsp_value(candidate: dict) -> float:
    if not candidate["fsp"]:
        return 0.0
    if any(item["discipline"] == candidate["specialization"] for item in candidate["fsp"]):
        return 1.0
    return 0.5


def freshness(iso: str | None) -> float:
    if not iso:
        return 0.0
    moment = datetime.fromisoformat(iso)
    days = max(0.0, (NOW - moment).total_seconds() / 86400)
    return math.exp(-days / 60)


def recency(iso: str | None) -> float:
    if not iso:
        return 0.5
    day = date.fromisoformat(iso[:10])
    years = max(0.0, (TODAY - day).days / 365.25)
    return 0.5 ** (years / 2.0)


def salary_fit(salary_to: int, min_salary: int | None) -> float:
    if not min_salary:
        return 1.0
    low = 0.9 * min_salary
    high = 1.15 * min_salary
    if salary_to <= low:
        return 0.0
    if salary_to >= high:
        return 1.0
    return (salary_to - low) / (high - low)


def format_fit(candidate_formats: list[str], need_formats: list[str]) -> float:
    if set(candidate_formats) & set(need_formats):
        return 1.0
    if "remote" in candidate_formats and "hybrid" in need_formats:
        return 0.5
    return 0.0


def stack_interest(need: dict, candidate: dict) -> float:
    need_skills = set(need["must_skills"]) | set(need["nice_skills"])
    liked = set(candidate["liked_skills"])
    union = need_skills | liked
    jac = len(need_skills & liked) / len(union) if union else 0.0
    penalty = 0.5 * len(need_skills & set(candidate["disliked_skills"]))
    return max(0.0, min(1.0, jac - penalty))


def ef_proxy(candidate: dict, need: dict) -> float:
    def unit_s(req: dict, evidence: dict) -> float:
        sim = binary_token_cosine(req["task"], evidence["task"])
        depth = {"owner": 1.0, "contributor": 0.8, "participant": 0.6}.get(evidence["role"], 0.6)
        return sim * float(evidence["trust"]) * recency(evidence.get("date")) * depth

    def cover(req: dict) -> float:
        scores = sorted((unit_s(req, evidence) for evidence in candidate["evidence"]), reverse=True)[:3]
        prod = 1.0
        for score in scores:
            prod *= 1 - min(1.0, score)
        return 1 - prod

    must = [req for req in need["requirements"] if req["kind"] == "must"]
    nice = [req for req in need["requirements"] if req["kind"] == "nice"]
    if not must:
        return 0.0
    must_prod = 1.0
    for req in must:
        must_prod *= cover(req)
    nice_mean = sum(cover(req) for req in nice) / len(nice) if nice else 0.0
    return must_prod ** (1 / len(must)) * (0.7 + 0.3 * nice_mean)


def preview_s(candidate: dict, need: dict, company: dict, open_invites: int, ef: float) -> dict[str, float]:
    grade = max(need["grades"], key=lambda item: GRADE_ORDER.index(item))
    weights = E_WEIGHTS[grade]
    musts = [coverage(candidate, skill) for skill in need["must_skills"]]
    must_cov = sum(musts) / len(musts)
    distance = min(grade_distance(candidate["grade"], item) for item in need["grades"])
    grade_fit = 1.0 if distance == 0 else 0.5 if distance == 1 else 0.0
    tests = [row["score"] for row in candidate["skills"] if row["source"] == "test" and row["score"] is not None]
    skill_avg = (sum(tests) / len(tests) / 100) if tests else 0.0
    fsp = fsp_value(candidate)
    fresh = freshness(candidate["last_active_at"])
    nices = [coverage(candidate, skill) for skill in need["nice_skills"]]
    nice_cov = sum(nices) / len(nices) if nices else 0.0
    features = {
        "must_cov": must_cov,
        "grade_fit": grade_fit,
        "ef": ef,
        "skill_avg": skill_avg,
        "fsp": fsp,
        "fresh": fresh,
        "nice_cov": nice_cov,
    }
    employer = sum(weights[name] * features[name] for name in weights)
    c_weights = C_SENIOR if grade in {"senior", "lead"} else C_DEFAULT
    c_features = {
        "salary_fit": salary_fit(need["salary_to"], candidate["min_salary"]),
        "format_fit": format_fit(candidate["formats"], need["formats"]),
        "stack_interest": stack_interest(need, candidate),
        "domain_fit": 1.0 if need["domain"] in candidate["liked_domains"] else 0.0 if need["domain"] in candidate["blocked_domains"] else 0.5,
        "benefits": sum(1 for item in BENEFITS if item in company["benefits"]) / len(BENEFITS),
        "process": 1.0 if need["stages"] <= 2 else 0.5 if need["stages"] == 3 else 0.0,
    }
    candidate_fit = sum(c_weights[name] * c_features[name] for name in c_weights)
    score = employer * candidate_fit / (1 + 0.15 * open_invites)
    return {"s": score, "e": employer, "c": candidate_fit, **features}


def rank_pool(pool: list[dict], need: dict, company: dict, opens: dict[str, int], ef_of) -> list[tuple[float, dict]]:
    scored = [(preview_s(candidate, need, company, opens.get(candidate["id"], 0), ef_of(candidate))["s"], candidate) for candidate in pool]
    scored.sort(key=lambda item: (-item[0], item[1]["id"]))
    return scored


def demo_scenario(candidates: list[dict], needs: list[dict], companies: list[dict], invitations: list[dict]) -> dict:
    need = next(item for item in needs if item["key"] == "need-demo-kafka")
    company = next(item for item in companies if item["id"] == need["company_id"])
    main = [item for item in candidates if passes_sql(item, need) and passes_gate(item, need)]
    confirmed = [item for item in main if any(row["skill_id"] == "kafka" and row["source"] == "test" for row in item["skills"])]
    if len(main) != 24 or len(confirmed) != 9:
        raise RuntimeError(f"demo pool is {len(main)} / confirmed {len(confirmed)}, expected 24 / 9")
    opens: dict[str, int] = {}
    for invitation in invitations:
        if invitation["status"] in {"sent", "viewed"}:
            opens[invitation["candidate_id"]] = opens.get(invitation["candidate_id"], 0) + 1
    zero = rank_pool(main, need, company, opens, lambda _candidate: 0.0)
    proxy = rank_pool(main, need, company, opens, lambda candidate: ef_proxy(candidate, need))
    demo = next(item for item in candidates if item["key"] == DEMO_KEY)
    zero_rank = next(index for index, (_, item) in enumerate(zero, start=1) if item["id"] == demo["id"])
    proxy_rank = next(index for index, (_, item) in enumerate(proxy, start=1) if item["id"] == demo["id"])
    if zero_rank > 5 or proxy_rank > 5:
        lines = [f"equal_ef rank {zero_rank}, proxy rank {proxy_rank}"]
        for score, item in zero[:8]:
            lines.append(f"  {score:.4f} {item['key']} {item['grade']} {item['pool_role']}")
        raise RuntimeError("demo candidate is outside the top 5\n" + "\n".join(lines))
    zero_scores = [score for score, _ in zero]
    confirmed_ids = {item["id"] for item in confirmed}
    confirmed_scores = [score for score, item in zero if item["id"] in confirmed_ids]
    breakdown = preview_s(demo, need, company, opens.get(demo["id"], 0), 0.0)
    return {
        "seed": SEED,
        "candidate_email": DEMO_EMAIL,
        "employer_email": EMPLOYER_EMAIL,
        "admin_email": ADMIN_EMAIL,
        "candidate_id": demo["id"],
        "candidate_name": demo["full_name"],
        "candidate_kc_sub": demo["user"]["kc_sub"],
        "employer_kc_sub": company["user"]["kc_sub"],
        "company_id": company["id"],
        "company_name": company["name"],
        "need_id": need["id"],
        "need_key": need["key"],
        "need_title": need["title"],
        "hint": "Kafka только подтверждённая",
        "pool_before": len(main),
        "pool_after": len(confirmed),
        "demo_rank_equal_ef": zero_rank,
        "demo_rank_proxy_ef": proxy_rank,
        "mean_s_before": round(sum(zero_scores) / len(zero_scores), 4),
        "mean_s_after": round(sum(confirmed_scores) / len(confirmed_scores), 4),
        "demo_features_equal_ef": {key: round(value, 4) for key, value in breakdown.items()},
        "resume_pdf": "seed/demo/candidate.pdf",
        "score_pair_is_stub": True,
        "assumptions": [
            "Ранг посчитан локальной копией §6, не matching.service.score_pair.",
            "equal_ef ставит experience fit в 0: так ведёт себя заглушка эмбеддингов.",
            "proxy_ef берёт косинус токенов как sim и не использует пороги 0.75/0.15.",
            "kc_sub вида seed:<email> не совпадёт с sub Keycloak, пока агент A не свяжет пользователя по email.",
        ],
    }


def select_gold(candidates: list[dict], needs: list[dict]) -> list[dict]:
    names = {skill: aliases for skill, aliases in catalog.SKILL_NAMES.items()}
    rows = []
    for need in needs:
        if need["key"] not in GOLD_KEYS:
            continue
        buckets: dict[int, list[dict]] = {0: [], 1: [], 2: [], 3: []}
        for candidate in candidates:
            label = relevance(candidate, need, catalog.ADJACENT, names)
            buckets[label].append(candidate)
        for items in buckets.values():
            items.sort(key=lambda item: item["id"])
        quotas = {3: 8, 2: 8, 1: 7, 0: 7}
        chosen: list[tuple[int, dict]] = []
        for label, quota in quotas.items():
            take = buckets[label][:quota]
            chosen.extend((label, item) for item in take)
            buckets[label] = buckets[label][len(take) :]
        if len(chosen) < 30:
            rest = [(label, item) for label in (3, 2, 1, 0) for item in buckets[label]]
            rest.sort(key=lambda item: (-item[0], item[1]["id"]))
            chosen.extend(rest[: 30 - len(chosen)])
        if len(chosen) != 30:
            raise RuntimeError(f"{need['key']} gold slice is {len(chosen)}")
        for label, candidate in chosen:
            rows.append({"need_id": need["id"], "candidate_id": candidate["id"], "relevance": label})
    rows.sort(key=lambda item: (item["need_id"], item["candidate_id"]))
    return rows


def sim_pair_label(req: dict, evidence: dict, candidate: dict, need: dict) -> int:
    skills_hit = bool(set(req["skills"]) & set(evidence["skills"]))
    spec = candidate["specialization"]
    need_spec = need["specialization"]
    if req["family"] == evidence["family"] and skills_hit:
        return 3
    if spec == need_spec and skills_hit:
        return 2
    if spec == need_spec or spec in catalog.ADJACENT[need_spec]:
        return 1
    return 0


def build_sim_pairs(rng: random.Random, candidates: list[dict], needs: list[dict]) -> list[dict]:
    buckets: dict[int, list[dict]] = {0: [], 1: [], 2: [], 3: []}
    for need in needs:
        for req in need["requirements"]:
            for candidate in candidates:
                for evidence in candidate["evidence"]:
                    label = sim_pair_label(req, evidence, candidate, need)
                    buckets[label].append(
                        {
                            "requirement": req["task"],
                            "evidence": evidence["task"],
                            "label": label,
                            "need_id": need["id"],
                            "candidate_id": candidate["id"],
                            "requirement_id": req["id"],
                            "evidence_id": evidence["id"],
                        }
                    )
    quotas = {3: 15, 2: 15, 1: 10, 0: 10}
    chosen: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for label, quota in quotas.items():
        pool = buckets[label]
        rng.shuffle(pool)
        taken = 0
        for pair in pool:
            key = (pair["requirement_id"], pair["evidence_id"])
            if key in seen:
                continue
            seen.add(key)
            chosen.append(pair)
            taken += 1
            if taken == quota:
                break
        if taken < quota:
            sizes = {key: len(value) for key, value in buckets.items()}
            raise RuntimeError(f"sim pair label {label} has {taken}/{quota}; buckets {sizes}")
    for pair in chosen:
        pair["token_cosine"] = round(binary_token_cosine(pair["requirement"], pair["evidence"]), 4)
    chosen.sort(key=lambda item: (item["requirement_id"], item["evidence_id"]))
    return chosen


def build_dataset() -> dict:
    rng = random.Random(SEED)
    stop = load_stop(SEED_DIR / "stop_companies.txt")
    companies = build_companies()
    needs = build_needs(companies)
    names = people_pool(rng)
    name_cursor = 0
    candidates: list[dict] = []
    for spec in catalog.SPECS:
        grades: list[str] = []
        for grade, count in catalog.GRADE_QUOTAS:
            grades.extend([grade] * count)
        rng.shuffle(grades)
        if spec == "backend" and grades[0] != "middle":
            swap = grades.index("middle")
            grades[0], grades[swap] = grades[swap], grades[0]
        for index, grade in enumerate(grades):
            person = None
            if not (spec == "backend" and index == 0):
                person = names[name_cursor]
                name_cursor += 1
            candidate = make_candidate(rng, spec, index, person)
            fill_candidate(rng, candidate, grade)
            candidates.append(candidate)
    demo = next(item for item in candidates if item["key"] == DEMO_KEY)
    demo_need = next(item for item in needs if item["key"] == "need-demo-kafka")
    shape_demo(demo, demo_need)
    take_rivals([item for item in candidates if item["specialization"] == "backend"])
    strip_kafka(candidates)
    assign_fsp(candidates, rng)
    attach_fsp_skill(candidates)
    for candidate in candidates:
        refresh_evidence(candidate)
    invitations = build_invitations(rng, needs, candidates, companies)
    assign_ranks(candidates)
    scenario = demo_scenario(candidates, needs, companies, invitations)
    gold = select_gold(candidates, needs)
    pairs = build_sim_pairs(rng, candidates, needs)
    thresholds = fit_sim_thresholds(pairs)
    users = [item["user"] for item in candidates]
    users.extend(item["user"] for item in companies)
    users.append({"id": sid(f"user:{ADMIN_EMAIL}"), "kc_sub": f"seed:{ADMIN_EMAIL}", "role": "admin", "email": ADMIN_EMAIL})
    fsp_rows = []
    for candidate in candidates:
        for item in candidate["fsp"]:
            fsp_rows.append(
                {
                    "id": item["id"],
                    "candidate_id": candidate["id"],
                    "candidate_key": candidate["key"],
                    "email": candidate["email"],
                    "discipline": item["discipline"],
                    "event": item["event"],
                    "place": item["place"],
                    "year": item["year"],
                }
            )
    company_names = [item["name"] for item in companies]
    experience_names = [exp["company"] for candidate in candidates for exp in candidate["experiences"]]
    assert_allowed(company_names + list(catalog.PAST_COMPANIES) + experience_names, stop)
    check_dataset(candidates, companies, needs, invitations, fsp_rows, gold, scenario)
    return {
        "candidates": candidates,
        "companies": companies,
        "needs": needs,
        "invitations": invitations,
        "users": users,
        "fsp_achievements": fsp_rows,
        "scenario": scenario,
        "gold": gold,
        "sim_pairs": pairs,
        "sim_thresholds": thresholds,
        "resume_text": demo["resume"]["raw_text"],
    }


def check_dataset(candidates, companies, needs, invitations, fsp_rows, gold, scenario) -> None:
    if len(candidates) != 400 or len(companies) != 15 or len(needs) != 25 or len(invitations) != 80:
        raise RuntimeError("unexpected seed counts")
    if len(fsp_rows) != 120:
        raise RuntimeError(f"expected 120 FSP rows, got {len(fsp_rows)}")
    if len(gold) != 300:
        raise RuntimeError(f"expected 300 gold rows, got {len(gold)}")
    by_spec: dict[str, int] = {}
    by_grade: dict[str, int] = {}
    for candidate in candidates:
        by_spec[candidate["specialization"]] = by_spec.get(candidate["specialization"], 0) + 1
        by_grade[candidate["grade"]] = by_grade.get(candidate["grade"], 0) + 1
        for row in candidate["skills"]:
            if row["skill_id"] not in catalog.SKILL_NAMES:
                raise RuntimeError(f"unknown skill {row['skill_id']}")
    if set(by_spec) != set(catalog.SPECS) or any(count != 100 for count in by_spec.values()):
        raise RuntimeError(f"specialization mix {by_spec}")
    for grade, _count in catalog.GRADE_QUOTAS:
        if by_grade.get(grade, 0) != _count * 4:
            raise RuntimeError(f"grade mix drifted: {by_grade}")
    for need in needs:
        if len(need["description"]) < 300:
            raise RuntimeError(f"{need['key']} description is {len(need['description'])} chars")
        for req in need["requirements"]:
            if req["task"] not in need["description"]:
                raise RuntimeError(f"{need['key']} drops a requirement span")
        if set(need["must_skills"]) & set(need["nice_skills"]):
            raise RuntimeError(f"{need['key']} overlaps must and nice")
    statuses = {item["status"] for item in invitations}
    if statuses != {"sent", "viewed", "accepted", "declined", "expired", "revoked"}:
        raise RuntimeError(f"invitation statuses {statuses}")
    if any(item["candidate_id"] == scenario["candidate_id"] and item["need_id"] == scenario["need_id"] for item in invitations):
        raise RuntimeError("demo candidate already has an invitation on the demo need")
    if scenario["mean_s_after"] <= scenario["mean_s_before"]:
        raise RuntimeError("confirmed-kafka slice does not raise the mean score")


def dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_outputs(data: dict) -> None:
    data_dir = SEED_DIR / "data"
    demo_dir = SEED_DIR / "demo"
    data_dir.mkdir(parents=True, exist_ok=True)
    demo_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "candidates.json").write_text(dumps(data["candidates"]), encoding="utf-8")
    (data_dir / "companies.json").write_text(dumps(data["companies"]), encoding="utf-8")
    (data_dir / "needs.json").write_text(dumps(data["needs"]), encoding="utf-8")
    (data_dir / "invitations.json").write_text(dumps(data["invitations"]), encoding="utf-8")
    (data_dir / "users.json").write_text(dumps(data["users"]), encoding="utf-8")
    (SEED_DIR / "fsp_achievements.json").write_text(dumps(data["fsp_achievements"]), encoding="utf-8")
    (demo_dir / "scenario.json").write_text(dumps(data["scenario"]), encoding="utf-8")
    gold_path = ROOT / "eval" / "gold.jsonl"
    gold_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data["gold"]), encoding="utf-8")
    pairs_path = ROOT / "eval" / "sim_pairs.jsonl"
    pairs_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in data["sim_pairs"]), encoding="utf-8")
    (ROOT / "eval" / "sim_thresholds.json").write_text(dumps(data["sim_thresholds"]), encoding="utf-8")
    write_pdf(demo_dir / "candidate.pdf", data["resume_text"])


def write_pdf(path: Path, text: str) -> None:
    import pymupdf

    # Arial (not Unicode) rewrites spaces as NBSP and hyphens as soft hyphens, so the
    # text layer no longer contains the evidence spans. Prefer a font that round-trips.
    fonts = (
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    font = next((item for item in fonts if Path(item).exists()), None)
    if font is None:
        raise RuntimeError("no Cyrillic TTF found for the demo resume PDF")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_font(fontname="resume", fontfile=font)
    unused = page.insert_textbox(pymupdf.Rect(48, 48, 548, 800), text, fontname="resume", fontsize=11)
    if isinstance(unused, float) and unused < 0:
        raise RuntimeError("demo resume does not fit on one PDF page")
    if isinstance(unused, str) and unused.strip():
        page = doc.new_page()
        page.insert_font(fontname="resume", fontfile=font)
        page.insert_textbox(pymupdf.Rect(48, 48, 548, 800), unused, fontname="resume", fontsize=11)
    doc.set_metadata(
        {
            "title": "Алексей Кузнецов",
            "author": "fsp-seed",
            "creator": "fsp-seed",
            "producer": "fsp-seed",
            "creationDate": "D:20261011090000Z",
            "modDate": "D:20261011090000Z",
        }
    )
    doc.subset_fonts()
    doc.save(path, garbage=4, deflate=True)
    doc.close()
    check = pymupdf.open(path)
    extracted = "".join(page.get_text() for page in check)
    check.close()
    for needle in ("Алексей Кузнецов", "Kafka", "PostgreSQL", "антифрод-событий в Kafka"):
        if needle not in extracted:
            raise RuntimeError(f"PDF text layer is missing {needle}")


def main() -> None:
    data = build_dataset()
    write_outputs(data)
    scenario = data["scenario"]
    print(
        f"seed={SEED} candidates=400 companies=15 needs=25 invitations=80 fsp=120 "
        f"demo_rank={scenario['demo_rank_equal_ef']} pool={scenario['pool_before']}→{scenario['pool_after']} "
        f"mean_s={scenario['mean_s_before']}→{scenario['mean_s_after']}"
    )


if __name__ == "__main__":
    main()
