"""Weights and thresholds from MVP TZ §6 and §7. One place, no magic numbers elsewhere.

MATCH_ALPHA and MATCH_BETA in settings override alpha/beta at runtime (§8.4).
"""

from app.core.enums import grade_distance

__all__ = ["grade_distance"]

ALPHA = 1.0
BETA = 0.15

MUST_GATE = 0.3
SHORTLIST_CAP = 300
CACHE_TTL_SECONDS = 3600
NEIGHBOR_CATEGORIES = 3

SIM_OFFSET = 0.75
SIM_SCALE = 0.15
TOP_EVIDENCE = 3
EF_NICE_WEIGHT = 0.3

SALARY_FLOOR_RATIO = 0.9
SALARY_FULL_RATIO = 1.15
FRESH_TAU_DAYS = 60.0
RECENCY_HALF_LIFE_YEARS = 2.0

COVERAGE_TEST = "score/100"
COVERAGE_RESUME = 0.4
COVERAGE_PROJECT = 0.4
COVERAGE_FSP = 0.8
COVERAGE_NONE = 0.0

TRUST = {
    "test": 1.0,
    "employer_task": 1.0,
    "fsp_id": 1.0,
    "github": 0.8,
    "resume": 0.6,
    "self": 0.35,
    "project": 0.35,
}

DEPTH = {
    "owner": 1.0,
    "contributor": 0.8,
    "participant": 0.6,
}

# Intern/Junior share a row. Senior/Lead share a row. nice_cov is senior-only.
E_WEIGHTS: dict[str, dict[str, float]] = {
    "intern": {
        "must_cov": 0.25,
        "grade_fit": 0.20,
        "ef": 0.10,
        "skill_avg": 0.20,
        "fsp": 0.15,
        "fresh": 0.10,
        "nice_cov": 0.0,
    },
    "junior": {
        "must_cov": 0.25,
        "grade_fit": 0.20,
        "ef": 0.10,
        "skill_avg": 0.20,
        "fsp": 0.15,
        "fresh": 0.10,
        "nice_cov": 0.0,
    },
    "middle": {
        "must_cov": 0.30,
        "grade_fit": 0.20,
        "ef": 0.25,
        "skill_avg": 0.15,
        "fsp": 0.05,
        "fresh": 0.05,
        "nice_cov": 0.0,
    },
    "senior": {
        "must_cov": 0.20,
        "grade_fit": 0.15,
        "ef": 0.40,
        "skill_avg": 0.10,
        "fsp": 0.03,
        "fresh": 0.05,
        "nice_cov": 0.07,
    },
    "lead": {
        "must_cov": 0.20,
        "grade_fit": 0.15,
        "ef": 0.40,
        "skill_avg": 0.10,
        "fsp": 0.03,
        "fresh": 0.05,
        "nice_cov": 0.07,
    },
}

# Senior/Lead: salary_fit = 0.40, the other weights shrink in proportion (sum stays 1).
_C_BASE = {
    "salary_fit": 0.35,
    "format_fit": 0.20,
    "stack_interest": 0.20,
    "domain_fit": 0.10,
    "benefits": 0.10,
    "process": 0.05,
}
_SENIOR_FACTOR = 0.60 / 0.65
C_WEIGHTS: dict[str, dict[str, float]] = {
    "default": dict(_C_BASE),
    "senior": {
        "salary_fit": 0.40,
        "format_fit": _C_BASE["format_fit"] * _SENIOR_FACTOR,
        "stack_interest": _C_BASE["stack_interest"] * _SENIOR_FACTOR,
        "domain_fit": _C_BASE["domain_fit"] * _SENIOR_FACTOR,
        "benefits": _C_BASE["benefits"] * _SENIOR_FACTOR,
        "process": _C_BASE["process"] * _SENIOR_FACTOR,
    },
}
C_WEIGHTS["lead"] = dict(C_WEIGHTS["senior"])

GRADE_FIT_EXACT = 1.0
GRADE_FIT_NEIGHBOR = 0.5
GRADE_FIT_FAR = 0.0

HINT_EFFORT = {
    "mini_test": 1.0,
    "project": 2.0,
    "conditions": 1.0,
}
HINT_TOP = 3
HINT_ACTIVE_DAYS = 14
EMPLOYER_HINT_MIN_POOL = 5

# §6.1 pool statuses and the §7.2 "active 14 days" window already above.
# "Активен за 30 дней" is the shortlist filter (POOL-3).
ACTIVE_WINDOW_DAYS = 30
CANDIDATE_POOL_STATUSES = ("seeking", "open")
OPEN_INVITE_STATUSES = ("sent", "viewed")

# FSP disciplines that count as the profile discipline for a specialization
# (must_cov 0.8 and fsp feature 1.0). The specialization id itself is included.
PROFILE_DISCIPLINES: dict[str, frozenset[str]] = {
    "backend": frozenset({"backend", "algo"}),
    "frontend": frozenset({"frontend", "product"}),
    "data_ml": frozenset({"data_ml", "algo"}),
    "devops": frozenset({"devops", "infosec"}),
}

BENEFIT_KEYS = ("dms", "accreditation", "flexible_start")
TEST_SCORE_MAX = 100.0
STACK_DISLIKE_PENALTY = 0.5
FORMAT_EXACT = 1.0
FORMAT_HYBRID_REMOTE = 0.5
FORMAT_MISS = 0.0
DOMAIN_LIKED = 1.0
DOMAIN_NEUTRAL = 0.5
DOMAIN_BLOCKED = 0.0
FSP_PROFILE = 1.0
FSP_OTHER = 0.5
FSP_NONE = 0.0
PROCESS_FULL_MAX_STAGES = 2
PROCESS_MID_STAGES = 3
PROCESS_FULL = 1.0
PROCESS_MID = 0.5
PROCESS_NONE = 0.0
RECENCY_BASE = 0.5
EXPLANATION_MAX = 3
MATCH_SCALE = 100

# Sample sizes for §7.1 rank counterfactuals ("по выборке потребностей").
HINT_NEED_SAMPLE = 10
HINT_PEER_CAP = 30

