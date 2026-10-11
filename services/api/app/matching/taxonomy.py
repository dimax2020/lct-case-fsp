"""Specialization titles and neighbours from taxonomy YAML. No matching weights."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.settings import get_settings


@dataclass(frozen=True)
class SpecInfo:
    id: str
    title: str
    adjacent: tuple[str, ...]


def _taxonomy_file(name: str) -> Path:
    configured = Path(get_settings().taxonomy_dir)
    root = Path(__file__).resolve().parents[4]
    candidates = []
    if configured.is_absolute():
        candidates.append(configured / name)
    else:
        candidates.append(root / configured / name)
        candidates.append(Path.cwd() / configured / name)
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


@lru_cache
def specializations() -> dict[str, SpecInfo]:
    path = _taxonomy_file("specializations.yaml")
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    found: dict[str, SpecInfo] = {}
    for item in raw:
        if not isinstance(item, dict) or "id" not in item:
            continue
        spec_id = str(item["id"])
        adjacent = tuple(str(value) for value in item.get("adjacent") or [])
        found[spec_id] = SpecInfo(id=spec_id, title=str(item.get("name") or spec_id), adjacent=adjacent)
    return found


def allowed_specializations(specialization: str) -> list[str]:
    info = specializations().get(specialization)
    ordered = [specialization]
    if info is not None:
        ordered.extend(info.adjacent)
    unique: list[str] = []
    for item in ordered:
        if item not in unique:
            unique.append(item)
    return unique


def specialization_title(specialization: str | None) -> str:
    if not specialization:
        return "Без категории"
    info = specializations().get(specialization)
    return info.title if info is not None else specialization
