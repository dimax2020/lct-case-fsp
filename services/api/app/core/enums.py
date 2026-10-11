from enum import StrEnum


class Role(StrEnum):
    candidate = "candidate"
    employer = "employer"
    admin = "admin"


class Specialization(StrEnum):
    backend = "backend"
    frontend = "frontend"
    data_ml = "data_ml"
    devops = "devops"


class Grade(StrEnum):
    intern = "intern"
    junior = "junior"
    middle = "middle"
    senior = "senior"
    lead = "lead"


class WorkFormat(StrEnum):
    remote = "remote"
    hybrid = "hybrid"
    office = "office"


class CandidateStatus(StrEnum):
    seeking = "seeking"
    open = "open"
    paused = "paused"


class SkillSource(StrEnum):
    test = "test"
    resume = "resume"
    project = "project"
    fsp_id = "fsp_id"


class ProjectRole(StrEnum):
    owner = "owner"
    contributor = "contributor"
    participant = "participant"


class EvidenceOrigin(StrEnum):
    project = "project"
    experience = "experience"
    fsp = "fsp"


class RequirementKind(StrEnum):
    must = "must"
    nice = "nice"


class ResumeStatus(StrEnum):
    uploaded = "uploaded"
    parsing = "parsing"
    parsed = "parsed"
    confirmed = "confirmed"
    failed = "failed"


class NeedStatus(StrEnum):
    draft = "draft"
    open = "open"
    closed = "closed"


class TaskKind(StrEnum):
    mcq = "mcq"
    code = "code"


class Verdict(StrEnum):
    OK = "OK"
    WRONG_ANSWER = "WRONG_ANSWER"
    TIME_LIMIT = "TIME_LIMIT"
    MEMORY_LIMIT = "MEMORY_LIMIT"
    COMPILE_ERROR = "COMPILE_ERROR"
    RUNTIME_ERROR = "RUNTIME_ERROR"
    PENDING = "PENDING"


class InvitationStatus(StrEnum):
    sent = "sent"
    viewed = "viewed"
    accepted = "accepted"
    declined = "declined"
    expired = "expired"
    revoked = "revoked"


class DeclineReason(StrEnum):
    salary = "salary"
    stack = "stack"
    work_format = "format"
    found_job = "found_job"
    other = "other"


class MessageKind(StrEnum):
    text = "text"
    slots = "slots"
    system = "system"


class HiringStage(StrEnum):
    interview = "interview"
    team = "team"
    offer = "offer"
    closed = "closed"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Benefit(StrEnum):
    dms = "dms"
    accreditation = "accreditation"
    flexible_start = "flexible_start"


class ContactChannel(StrEnum):
    email = "email"
    phone = "phone"
    telegram = "telegram"


GRADE_ORDER: tuple[Grade, ...] = (
    Grade.intern,
    Grade.junior,
    Grade.middle,
    Grade.senior,
    Grade.lead,
)


def grade_distance(left: str, right: str) -> int | None:
    try:
        return abs(GRADE_ORDER.index(Grade(left)) - GRADE_ORDER.index(Grade(right)))
    except ValueError:
        return None
