"""Pure §6 scoring. Every threshold is read from matching.config or settings."""

import math
from datetime import UTC, date, datetime, timedelta

from app.core.enums import GRADE_ORDER, Grade, grade_distance
from app.core.settings import get_settings
from app.matching.config import (
    BENEFIT_KEYS,
    C_WEIGHTS,
    COVERAGE_FSP,
    COVERAGE_NONE,
    COVERAGE_PROJECT,
    COVERAGE_RESUME,
    DAILY_BOOST,
    DEPTH,
    DOMAIN_BLOCKED,
    DOMAIN_LIKED,
    DOMAIN_NEUTRAL,
    E_WEIGHTS,
    EF_NICE_WEIGHT,
    EXPLANATION_FACT_MAX,
    EXPLANATION_MAX,
    FORMAT_EXACT,
    FORMAT_HYBRID_REMOTE,
    FORMAT_MISS,
    FRESH_TAU_DAYS,
    FSP_NONE,
    FSP_OTHER,
    FSP_PROFILE,
    GRADE_FIT_EXACT,
    GRADE_FIT_FAR,
    GRADE_FIT_NEIGHBOR,
    MATCH_SCALE,
    MUST_GATE,
    PROCESS_FULL,
    PROCESS_FULL_MAX_STAGES,
    PROCESS_MID,
    PROCESS_MID_STAGES,
    PROCESS_NONE,
    PROFILE_DISCIPLINES,
    RECENCY_BASE,
    RECENCY_HALF_LIFE_YEARS,
    SALARY_FLOOR_RATIO,
    SALARY_FULL_RATIO,
    SIM_OFFSET,
    SIM_SCALE,
    SKILL_SIM_OTHER_DOMAIN,
    STACK_DISLIKE_PENALTY,
    TEST_SCORE_MAX,
    TOP_EVIDENCE,
)
from app.matching.service import NeedView, PairExplanation, RequirementView, ScoreBreakdown
from app.profile.service import CandidateFeatures, EvidenceFeature, SkillFeature


def clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def grade_index(grade: str | None) -> int | None:
    if grade is None:
        return None
    try:
        return GRADE_ORDER.index(Grade(grade))
    except ValueError:
        return None


def highest_grade(grades: list[str]) -> str:
    ranked = [grade for grade in grades if grade_index(grade) is not None]
    if not ranked:
        return "middle"
    return max(ranked, key=lambda grade: grade_index(grade) or 0)


def grade_window(grades: list[str]) -> tuple[int, int] | None:
    indexes = [index for index in (grade_index(grade) for grade in grades) if index is not None]
    if not indexes:
        return None
    return min(indexes) - 1, max(indexes) + 1


def profile_disciplines(specialization: str | None) -> frozenset[str]:
    if not specialization:
        return frozenset()
    return PROFILE_DISCIPLINES.get(specialization, frozenset({specialization}))


def has_profile_fsp(candidate: CandidateFeatures, specialization: str | None) -> bool:
    allowed = profile_disciplines(specialization)
    return any(item.discipline in allowed for item in candidate.fsp)


def skill_coverage_value(matches: list[SkillFeature], profile_fsp: bool) -> float:
    """One skill: a test score wins when present, otherwise FSP, otherwise resume/project."""
    tests = [item for item in matches if item.source == "test"]
    if tests:
        best = max((item.score or 0.0) for item in tests)
        return clip(best / TEST_SCORE_MAX)
    if profile_fsp and any(item.source == "fsp_id" for item in matches):
        return COVERAGE_FSP
    if any(item.source == "resume" for item in matches):
        return COVERAGE_RESUME
    if any(item.source == "project" for item in matches):
        return COVERAGE_PROJECT
    return COVERAGE_NONE


def skill_coverages(need: NeedView, candidate: CandidateFeatures, skills: list[str]) -> dict[str, float]:
    profile = has_profile_fsp(candidate, need.specialization)
    grouped: dict[str, list[SkillFeature]] = {skill: [] for skill in skills}
    for item in candidate.skills:
        if item.skill_id in grouped:
            grouped[item.skill_id].append(item)
    return {skill: skill_coverage_value(grouped[skill], profile) for skill in skills}


def mean_coverage(coverages: dict[str, float]) -> float:
    if not coverages:
        return 0.0
    return sum(coverages.values()) / len(coverages)


def is_gated(must_coverages: dict[str, float]) -> bool:
    return any(value < MUST_GATE for value in must_coverages.values())


def grade_fit(need_grades: list[str], candidate_grade: str | None) -> float:
    if not candidate_grade:
        return GRADE_FIT_FAR
    distances = [grade_distance(candidate_grade, grade) for grade in need_grades]
    known = [distance for distance in distances if distance is not None]
    if not known:
        return GRADE_FIT_FAR
    best = min(known)
    if best == 0:
        return GRADE_FIT_EXACT
    if best == 1:
        return GRADE_FIT_NEIGHBOR
    return GRADE_FIT_FAR


def utc_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value.date()
    return value


def fresh_score(last_active: datetime | date | None, today: date) -> float:
    active = utc_date(last_active)
    if active is None:
        return 0.0
    days = (today - active).days
    if days < 0:
        days = 0
    return math.exp(-days / FRESH_TAU_DAYS)


def daily_boost_score(until: datetime | None, today: date) -> float:
    if until is None:
        return 0.0
    end = utc_date(until)
    if end is None or today >= end:
        return 0.0
    return 1.0


def fsp_score(candidate: CandidateFeatures, specialization: str | None) -> float:
    if not candidate.fsp:
        return FSP_NONE
    if has_profile_fsp(candidate, specialization):
        return FSP_PROFILE
    return FSP_OTHER


def skill_average(candidate: CandidateFeatures) -> float:
    scores = [item.score for item in candidate.skills if item.source == "test" and item.score is not None]
    if not scores:
        return 0.0
    return clip((sum(scores) / len(scores)) / TEST_SCORE_MAX)


def usable_embedding(vector: list[float] | None) -> bool:
    if not vector:
        return False
    return any(component != 0.0 for component in vector)


def cosine(left: list[float] | None, right: list[float] | None) -> float | None:
    if not usable_embedding(left) or not usable_embedding(right) or left is None or right is None:
        return None
    if len(left) != len(right):
        return None
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for x_value, y_value in zip(left, right, strict=True):
        dot += x_value * y_value
        left_norm += x_value * x_value
        right_norm += y_value * y_value
    if left_norm <= 0.0 or right_norm <= 0.0:
        return None
    return dot / math.sqrt(left_norm * right_norm)


def similarity_from_cosine(value: float) -> float:
    return clip((value - SIM_OFFSET) / SIM_SCALE)


def recency_factor(years: float | None) -> float:
    """0.5 ** (years / 2). A missing date does not decay the pair."""
    if years is None:
        return 1.0
    if years < 0:
        years = 0.0
    return RECENCY_BASE ** (years / RECENCY_HALF_LIFE_YEARS)


def years_between(moment: date | None, today: date) -> float | None:
    if moment is None:
        return None
    return (today - moment).days / 365.25


def depth_factor(role: str) -> float:
    return DEPTH.get(role, DEPTH["participant"])


def pair_strength(sim: float, trust: float, recency: float, depth: float) -> float:
    return clip(sim) * clip(trust) * clip(recency) * clip(depth)


def requirement_coverage(strengths: list[float]) -> float:
    """Noisy-OR. An empty set of evidence covers nothing."""
    if not strengths:
        return 0.0
    missed = 1.0
    for strength in strengths:
        missed *= 1.0 - clip(strength)
    return 1.0 - missed


def _nearest(requirement: RequirementView, evidence: list[EvidenceFeature]) -> list[tuple[float, EvidenceFeature]]:
    ranked: list[tuple[float, EvidenceFeature]] = []
    for item in evidence:
        value = cosine(requirement.embedding, item.embedding)
        if value is None:
            continue
        ranked.append((value, item))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].id))
    return ranked[:TOP_EVIDENCE]


def skill_similarity(requirement: RequirementView, evidence: EvidenceFeature) -> float:
    """Fallback similarity without vectors: share of requirement skills found in the evidence.

    The API image is built without the ML extra, so embeddings stay NULL there. Skill tags on
    both sides come from the same taxonomy, so their overlap is a fair proxy for the cosine.
    """
    wanted = set(requirement.skills)
    if not wanted:
        return 0.0
    hit = len(wanted & set(evidence.skills)) / len(wanted)
    if requirement.domain and requirement.domain != evidence.domain:
        hit *= SKILL_SIM_OTHER_DOMAIN
    return clip(hit)


def _nearest_by_skills(requirement: RequirementView, evidence: list[EvidenceFeature]) -> list[tuple[float, EvidenceFeature]]:
    ranked = [(skill_similarity(requirement, item), item) for item in evidence]
    ranked = [pair for pair in ranked if pair[0] > 0.0]
    ranked.sort(key=lambda pair: (-pair[0], pair[1].id))
    return ranked[:TOP_EVIDENCE]


def _pair_text(requirement: RequirementView, evidence: EvidenceFeature) -> str:
    labels = {
        "project": "Проект",
        "experience": "Опыт",
        "fsp": "ФСП",
        "resume": "Резюме",
        "test": "Тест",
        "github": "GitHub",
    }
    label = labels.get(evidence.origin, "Опыт")
    fact = (evidence.evidence_span or evidence.task or "").strip()
    if len(fact) > EXPLANATION_FACT_MAX:
        fact = fact[: EXPLANATION_FACT_MAX - 1].rstrip(" ,.;:") + "…"
    return f"{label}: {fact} ↔ {requirement.task}"


def experience_fit(
    need: NeedView,
    candidate: CandidateFeatures,
    today: date,
) -> tuple[float, list[PairExplanation]]:
    requirements = list(need.requirements)
    if not requirements:
        return 0.0, []
    vectors = any(usable_embedding(item.embedding) for item in requirements) and any(
        usable_embedding(item.embedding) for item in candidate.evidence
    )
    if not vectors and not any(item.skills for item in requirements):
        return 0.0, []

    best_pairs: list[PairExplanation] = []
    must_values: list[float] = []
    nice_values: list[float] = []
    for requirement in requirements:
        if vectors:
            nearest = [(similarity_from_cosine(value), item) for value, item in _nearest(requirement, candidate.evidence)]
        else:
            nearest = _nearest_by_skills(requirement, candidate.evidence)
        strengths: list[float] = []
        scored: list[tuple[float, EvidenceFeature]] = []
        for sim_value, evidence in nearest:
            years = years_between(evidence.date, today)
            strength = pair_strength(
                sim_value,
                evidence.trust,
                recency_factor(years),
                depth_factor(evidence.role),
            )
            strengths.append(strength)
            scored.append((strength, evidence))
        covered = requirement_coverage(strengths)
        if requirement.kind == "must":
            must_values.append(covered)
        else:
            nice_values.append(covered)
        if scored:
            strength, evidence = max(scored, key=lambda pair: (pair[0], pair[1].id))
            best_pairs.append(
                PairExplanation(
                    requirement_id=requirement.id,
                    evidence_id=evidence.id,
                    text=_pair_text(requirement, evidence),
                    score=strength,
                )
            )

    if must_values:
        geometric = math.prod(must_values) ** (1.0 / len(must_values))
    else:
        geometric = 1.0
    if nice_values:
        nice_mean = sum(nice_values) / len(nice_values)
    else:
        nice_mean = 1.0
    fit = geometric * ((1.0 - EF_NICE_WEIGHT) + EF_NICE_WEIGHT * nice_mean)
    return clip(fit), best_pairs


def salary_fit(salary_to: int, min_salary: int | None) -> float:
    if min_salary is None or min_salary <= 0:
        return 1.0
    floor = SALARY_FLOOR_RATIO * min_salary
    full = SALARY_FULL_RATIO * min_salary
    if salary_to <= floor:
        return 0.0
    if salary_to >= full:
        return 1.0
    return (salary_to - floor) / (full - floor)


def format_fit(need_formats: list[str], candidate_formats: list[str]) -> float:
    offered = set(need_formats)
    wanted = set(candidate_formats)
    if offered & wanted:
        return FORMAT_EXACT
    if "remote" in wanted and "hybrid" in offered:
        return FORMAT_HYBRID_REMOTE
    return FORMAT_MISS


def format_compatible(need_formats: list[str], candidate_formats: list[str]) -> bool:
    return format_fit(need_formats, candidate_formats) > FORMAT_MISS


def stack_interest(need: NeedView, candidate: CandidateFeatures) -> float:
    need_skills = set(need.must_skills) | set(need.nice_skills)
    liked = set(candidate.liked_skills)
    union = need_skills | liked
    if not union:
        overlap = 0.0
    else:
        overlap = len(need_skills & liked) / len(union)
    penalty = STACK_DISLIKE_PENALTY * len(set(candidate.disliked_skills) & need_skills)
    return clip(overlap - penalty)


def domain_fit(need: NeedView, candidate: CandidateFeatures) -> float:
    domain = need.domain
    if domain and domain in set(candidate.blocked_domains):
        return DOMAIN_BLOCKED
    if domain and domain in set(candidate.liked_domains):
        return DOMAIN_LIKED
    return DOMAIN_NEUTRAL


def benefits_score(benefits: list[str]) -> float:
    if not BENEFIT_KEYS:
        return 0.0
    marked = set(benefits) & set(BENEFIT_KEYS)
    return len(marked) / len(BENEFIT_KEYS)


def process_score(stages: int) -> float:
    if stages <= PROCESS_FULL_MAX_STAGES:
        return PROCESS_FULL
    if stages == PROCESS_MID_STAGES:
        return PROCESS_MID
    return PROCESS_NONE


def salary_passes(salary_to: int, min_salary: int | None) -> bool:
    if min_salary is None:
        return True
    return salary_to >= min_salary * SALARY_FLOOR_RATIO


def grade_passes(need_grades: list[str], candidate_grade: str | None) -> bool:
    return grade_fit(need_grades, candidate_grade) > GRADE_FIT_FAR


def passes_hard_filters(need: NeedView, candidate: CandidateFeatures, allowed_specs: set[str]) -> bool:
    """Python mirror of the §6.1 SQL predicate. The query in store.py must match it."""
    if candidate.specialization not in allowed_specs:
        return False
    if not grade_passes(need.grades, candidate.grade):
        return False
    if not salary_passes(need.salary_to, candidate.min_salary):
        return False
    if not format_compatible(need.formats, candidate.formats):
        return False
    if candidate.status not in {"seeking", "open"}:
        return False
    if not candidate.visible:
        return False
    if need.domain and need.domain in set(candidate.blocked_domains):
        return False
    return True


def e_weights_for(grades: list[str]) -> dict[str, float]:
    return E_WEIGHTS.get(highest_grade(grades), E_WEIGHTS["middle"])


def c_weights_for(grades: list[str]) -> dict[str, float]:
    grade = highest_grade(grades)
    if grade in C_WEIGHTS:
        return C_WEIGHTS[grade]
    return C_WEIGHTS["default"]


def weighted_sum(features: dict[str, float], weights: dict[str, float]) -> float:
    return sum(weights[name] * clip(features.get(name, 0.0)) for name in weights)


def final_s(e_score: float, c_score: float, open_invites: int, alpha: float, beta: float) -> float:
    invites = open_invites if open_invites > 0 else 0
    return e_score * (max(c_score, 0.0) ** alpha) / (1.0 + beta * invites)


def _skill_label(skill_id: str) -> str:
    if not skill_id:
        return skill_id
    return skill_id[:1].upper() + skill_id[1:]


def build_explanations(
    need: NeedView,
    candidate: CandidateFeatures,
    must_coverages: dict[str, float],
    must_cov: float,
    grade_value: float,
    pairs: list[PairExplanation],
) -> list[str]:
    lines: list[str] = []
    shown: set[str] = set()
    for pair in sorted(pairs, key=lambda item: (-item.score, item.requirement_id, item.evidence_id)):
        # One fact backs several requirements: show it once, against its strongest requirement.
        if pair.score <= 0 or pair.evidence_id in shown:
            continue
        shown.add(pair.evidence_id)
        lines.append(pair.text)
        if len(lines) == EXPLANATION_MAX:
            return lines

    tests_by_skill: dict[str, float] = {}
    for item in candidate.skills:
        if item.source == "test" and item.score is not None and item.skill_id in must_coverages:
            tests_by_skill[item.skill_id] = max(tests_by_skill.get(item.skill_id, 0.0), item.score)
    for skill_id in sorted(tests_by_skill):
        lines.append(f"Тест: {_skill_label(skill_id)} {tests_by_skill[skill_id]:.0f}/100")
        if len(lines) == EXPLANATION_MAX:
            return lines

    for achievement in candidate.fsp:
        place = f"{achievement.place} место, " if achievement.place else ""
        lines.append(f"Достижение ФСП: {place}{achievement.event}")
        if len(lines) == EXPLANATION_MAX:
            return lines

    if len(lines) < 2 and must_coverages:
        lines.append(f"Покрытие обязательных навыков {must_cov:.0%}")
    if len(lines) < 2 and candidate.grade:
        if grade_value == GRADE_FIT_EXACT:
            lines.append(f"Грейд {candidate.grade} совпадает с потребностью")
        elif grade_value == GRADE_FIT_NEIGHBOR:
            lines.append(f"Грейд {candidate.grade} — соседний к потребности")
    return lines[:EXPLANATION_MAX]


def score_breakdown(need: NeedView, candidate: CandidateFeatures, today: date | None = None) -> ScoreBreakdown:
    moment = today or datetime.now(UTC).date()
    must = skill_coverages(need, candidate, list(need.must_skills))
    nice = skill_coverages(need, candidate, list(need.nice_skills))
    fit, pairs = experience_fit(need, candidate, moment)
    features = {
        "must_cov": mean_coverage(must),
        "grade_fit": grade_fit(need.grades, candidate.grade),
        "ef": fit,
        "skill_avg": skill_average(candidate),
        "fsp": fsp_score(candidate, need.specialization),
        "fresh": fresh_score(candidate.last_active_at, moment),
        "nice_cov": mean_coverage(nice),
    }
    boosted = daily_boost_score(candidate.daily_boost_until, moment)
    features["daily_boost"] = boosted
    if boosted:
        features["fresh"] = 1.0
    employer = weighted_sum(features, e_weights_for(need.grades))
    if boosted:
        employer = min(1.0, employer + DAILY_BOOST)
    candidate_features = {
        "salary_fit": salary_fit(need.salary_to, candidate.min_salary),
        "format_fit": format_fit(need.formats, candidate.formats),
        "stack_interest": stack_interest(need, candidate),
        "domain_fit": domain_fit(need, candidate),
        "benefits": benefits_score(need.benefits),
        "process": process_score(need.stages),
    }
    candidate_score = weighted_sum(candidate_features, c_weights_for(need.grades))
    alpha, beta = get_settings().match_alpha, get_settings().match_beta
    total = final_s(employer, candidate_score, candidate.open_invites, alpha, beta)
    explanations = build_explanations(
        need,
        candidate,
        must,
        features["must_cov"],
        features["grade_fit"],
        pairs,
    )
    if boosted:
        until_day = utc_date(candidate.daily_boost_until)
        last_day = until_day - timedelta(days=1) if until_day else moment
        label = f"Ежедневная задача: буст в подборке до {last_day.strftime('%d.%m')}"
        explanations = [label, *explanations][:EXPLANATION_MAX]
    return ScoreBreakdown(
        s=total,
        e=employer,
        c=candidate_score,
        features=features,
        explanations=explanations,
        gated=is_gated(must),
        best_pairs=pairs,
        coverages={**must, **{f"nice:{skill}": value for skill, value in nice.items()}},
    )


def match_percent(score: float) -> int:
    percent = int(round(score * MATCH_SCALE))
    if percent < 0:
        return 0
    if percent > MATCH_SCALE:
        return MATCH_SCALE
    return percent


def split_ranked(scored: list[tuple[str, float, bool]]) -> tuple[list[str], list[str]]:
    """Stable order: higher S first, candidate id ascending on a tie. Gated ids go to hidden."""
    main = sorted((item for item in scored if not item[2]), key=lambda item: (-item[1], item[0]))
    hidden = sorted((item for item in scored if item[2]), key=lambda item: (-item[1], item[0]))
    return [item[0] for item in main], [item[0] for item in hidden]


def drop_must_skill(need: NeedView, skill_id: str) -> NeedView:
    return NeedView(
        id=need.id,
        specialization=need.specialization,
        grades=list(need.grades),
        salary_from=need.salary_from,
        salary_to=need.salary_to,
        formats=list(need.formats),
        city=need.city,
        must_skills=[skill for skill in need.must_skills if skill != skill_id],
        nice_skills=list(need.nice_skills),
        domain=need.domain,
        stages=need.stages,
        benefits=list(need.benefits),
        requirements=[item for item in need.requirements if skill_id not in item.skills or item.kind != "must"],
        description=need.description,
    )


def with_salary_to(need: NeedView, salary_to: int) -> NeedView:
    return NeedView(
        id=need.id,
        specialization=need.specialization,
        grades=list(need.grades),
        salary_from=need.salary_from,
        salary_to=salary_to,
        formats=list(need.formats),
        city=need.city,
        must_skills=list(need.must_skills),
        nice_skills=list(need.nice_skills),
        domain=need.domain,
        stages=need.stages,
        benefits=list(need.benefits),
        requirements=list(need.requirements),
        description=need.description,
    )
