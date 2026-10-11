"""FSP ID stub. Reads seed/fsp_achievements.json (0–3 achievements)."""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def achievements_path() -> Path:
    packaged = Path("/srv/seed/fsp_achievements.json")
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[4] / "seed" / "fsp_achievements.json"


def load_achievements(sub: str, email: str | None) -> list[dict[str, Any]]:
    """Return at most three achievements for this user.

    The file may be a list of achievements (shared stub), a list of records
    tagged with sub/kc_sub/email, or an object with by_sub / by_email / achievements.
    """
    path = achievements_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("fsp achievements file is not valid json: %s", path)
        return []
    selected = _select(data, sub, email)
    parsed: list[dict[str, Any]] = []
    for item in selected:
        row = _parse_item(item)
        if row is None:
            continue
        parsed.append(row)
        if len(parsed) == 3:
            break
    return parsed


def _select(data: Any, sub: str, email: str | None) -> list[Any]:
    if isinstance(data, dict):
        by_sub = data.get("by_sub")
        if isinstance(by_sub, dict):
            rows = by_sub.get(sub) or []
            return rows if isinstance(rows, list) else []
        by_email = data.get("by_email")
        if email and isinstance(by_email, dict):
            rows = by_email.get(email) or []
            return rows if isinstance(rows, list) else []
        rows = data.get("achievements", data.get("default", []))
        return rows if isinstance(rows, list) else []
    if isinstance(data, list):
        tagged = any(isinstance(item, dict) and _has_owner(item) for item in data)
        if tagged:
            return _matching(data, sub, email)
        return data
    return []


def _has_owner(item: dict[str, Any]) -> bool:
    return any(key in item for key in ("sub", "kc_sub", "email"))


def _matching(data: list[Any], sub: str, email: str | None) -> list[Any]:
    found: list[Any] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        owner = item.get("sub") or item.get("kc_sub")
        item_email = item.get("email")
        if owner and owner != sub:
            continue
        if item_email and (not email or item_email != email) and not owner:
            continue
        if not owner and item_email and email and item_email != email:
            continue
        if "achievements" in item and isinstance(item["achievements"], list):
            found.extend(item["achievements"])
        elif "discipline" in item and "event" in item:
            found.append(item)
    return found


def _parse_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    discipline = str(item.get("discipline") or "").strip()
    event = str(item.get("event") or "").strip()
    if not discipline or not event:
        return None
    skills = [str(raw).strip() for raw in item.get("skills") or [] if str(raw).strip()]
    return {
        "discipline": discipline[:64],
        "event": event[:200],
        "place": _int_or_none(item.get("place")),
        "year": _int_or_none(item.get("year")),
        "skills": skills,
    }


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
