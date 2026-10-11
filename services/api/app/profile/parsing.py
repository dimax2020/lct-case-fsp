"""Small parsers shared by the profile API and evidence rebuild."""

from datetime import UTC, date, datetime

from app.profile.models import Experience


def display_name(full_name: str) -> str:
    parts = [part for part in full_name.split() if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


def in_pool_eligible(min_salary: int | None, formats: list[str] | None) -> bool:
    return min_salary is not None and bool(formats)


def as_date(value: datetime | date | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    if len(text) == 4 and text.isdigit():
        return date(int(text), 1, 1)
    return None


def as_datetime(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def canonical_role(value: str | None, default: str = "participant") -> str:
    if not value:
        return default
    key = value.strip().lower().replace("ё", "е")
    mapping = {
        "owner": "owner",
        "contributor": "contributor",
        "participant": "participant",
        "сделал сам": "owner",
        "автор": "owner",
        "в команде": "contributor",
        "участник": "participant",
    }
    return mapping.get(key, default)


def experience_years(rows: list[Experience]) -> float | None:
    today = datetime.now(UTC).date()
    starts: list[date] = []
    ends: list[date] = []
    for row in rows:
        if row.start is None:
            continue
        end = row.end or today
        if end < row.start:
            continue
        starts.append(row.start)
        ends.append(end)
    if not starts:
        return None
    return round((max(ends) - min(starts)).days / 365.25, 2)
