"""Skill ontology loaded from YAML: synonyms, light typos, autocomplete."""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_EMBED_THRESHOLD = 0.82


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    decay: str
    specializations: tuple[str, ...]
    synonyms: tuple[str, ...]


@dataclass(frozen=True)
class Specialization:
    id: str
    name: str
    adjacent: tuple[str, ...]


@dataclass(frozen=True)
class NamedItem:
    id: str
    name: str


@dataclass
class Catalog:
    skills: list[Skill]
    specializations: list[Specialization]
    domains: list[NamedItem]
    decline_reasons: list[NamedItem]
    exact: dict[str, str]
    domain_exact: dict[str, str]


_CATALOG: Catalog | None = None
_EMBED_CACHE: tuple[int, np.ndarray, list[str]] | None = None


def taxonomy_dir() -> Path:
    configured = Path(get_settings().taxonomy_dir)
    if configured.is_absolute() and configured.is_dir():
        return configured
    cwd_path = Path.cwd() / configured
    if cwd_path.is_dir():
        return cwd_path
    repo_path = Path(__file__).resolve().parents[4] / configured
    if repo_path.is_dir():
        return repo_path
    if configured.is_dir():
        return configured
    raise FileNotFoundError(f"Каталог онтологии не найден: {configured}")


def fold(text: str) -> str:
    lowered = text.strip().lower().replace("ё", "е")
    cleaned: list[str] = []
    for char in lowered:
        if char.isalnum() or char in "+#.":
            cleaned.append(char)
        else:
            cleaned.append(" ")
    return " ".join("".join(cleaned).split())


def _max_distance(length: int) -> int:
    if length >= 8:
        return 2
    if length >= 5:
        return 1
    return 0


def levenshtein(left: str, right: str, limit: int) -> int:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for index, right_char in enumerate(right, start=1):
        current = [index]
        row_min = current[0]
        for column, left_char in enumerate(left, start=1):
            insert_cost = current[column - 1] + 1
            delete_cost = previous[column] + 1
            replace_cost = previous[column - 1] + (left_char != right_char)
            best = min(insert_cost, delete_cost, replace_cost)
            current.append(best)
            if best < row_min:
                row_min = best
        if row_min > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        logger.warning("taxonomy file is missing: %s", path)
        return []
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded or []


def _load_catalog() -> Catalog:
    root = taxonomy_dir()
    skills: list[Skill] = []
    exact: dict[str, str] = {}
    for item in _read_yaml(root / "skills.yaml"):
        if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
            continue
        decay = str(item.get("decay") or "framework")
        if decay not in {"fundamental", "framework"}:
            decay = "framework"
        specs = tuple(str(part) for part in item.get("specializations") or [])
        synonyms = tuple(str(part) for part in item.get("synonyms") or [])
        skill = Skill(
            id=str(item["id"]),
            name=str(item["name"]),
            decay=decay,
            specializations=specs,
            synonyms=synonyms,
        )
        skills.append(skill)
        for key in (skill.id, skill.name, *skill.synonyms):
            folded = fold(key)
            if not folded:
                continue
            previous = exact.get(folded)
            if previous is not None and previous != skill.id:
                logger.warning("synonym %s maps to both %s and %s", folded, previous, skill.id)
                continue
            exact[folded] = skill.id

    specializations: list[Specialization] = []
    for item in _read_yaml(root / "specializations.yaml"):
        if not isinstance(item, dict) or not item.get("id"):
            continue
        specializations.append(
            Specialization(
                id=str(item["id"]),
                name=str(item.get("name") or item["id"]),
                adjacent=tuple(str(part) for part in item.get("adjacent") or []),
            )
        )

    domains = _named_items(_read_yaml(root / "domains.yaml"))
    reasons = _named_items(_read_yaml(root / "decline_reasons.yaml"))
    domain_exact: dict[str, str] = {}
    for domain in domains:
        for key in (domain.id, domain.name):
            folded = fold(key)
            if folded:
                domain_exact[folded] = domain.id
    return Catalog(
        skills=skills,
        specializations=specializations,
        domains=domains,
        decline_reasons=reasons,
        exact=exact,
        domain_exact=domain_exact,
    )


def _named_items(raw: Any) -> list[NamedItem]:
    items: list[NamedItem] = []
    if not isinstance(raw, list):
        return items
    for item in raw:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        items.append(NamedItem(id=str(item["id"]), name=str(item.get("name") or item["id"])))
    return items


def catalog() -> Catalog:
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    with _LOCK:
        if _CATALOG is None:
            _CATALOG = _load_catalog()
    return _CATALOG


def _fuzzy(folded: str, table: dict[str, str]) -> str | None:
    limit = _max_distance(len(folded))
    if limit == 0:
        return None
    best = limit + 1
    found: list[str] = []
    for key, item_id in table.items():
        if len(key) < 5 or abs(len(key) - len(folded)) > limit:
            continue
        distance = levenshtein(folded, key, limit)
        if distance > limit:
            continue
        if distance < best:
            best = distance
            found = [item_id]
        elif distance == best and item_id not in found:
            found.append(item_id)
    if len(found) == 1:
        return found[0]
    return None


def _unit(vector: Any) -> np.ndarray:
    array = np.asarray(vector, dtype=float).reshape(-1)
    norm = float(np.linalg.norm(array))
    if norm == 0:
        return array
    return array / norm


def _embedding_fallback(folded: str) -> str | None:
    if len(folded) < 4:
        return None
    from app.embeddings.service import peek_model

    model = peek_model()
    if model is None:
        return None
    try:
        matrix, ids = _skill_matrix(model)
        if matrix.size == 0:
            return None
        encoded = model.encode([f"query: {folded}"], batch_size=32, normalize_embeddings=True)
        query = _unit(encoded[0])
        if matrix.shape[1] != query.shape[0]:
            return None
        scores = matrix @ query
        best = int(np.argmax(scores))
        top = float(scores[best])
        if top < _EMBED_THRESHOLD:
            return None
        close = [index for index, score in enumerate(scores) if float(score) >= top - 0.01]
        if len(close) != 1:
            return None
        return ids[best]
    except Exception:
        logger.exception("embedding fallback for skill normalize failed")
        return None


def _skill_matrix(model: Any) -> tuple[np.ndarray, list[str]]:
    global _EMBED_CACHE
    marker = id(model)
    if _EMBED_CACHE is not None and _EMBED_CACHE[0] == marker:
        return _EMBED_CACHE[1], _EMBED_CACHE[2]
    data = catalog()
    passages = [f"passage: {skill.name} {' '.join(skill.synonyms)}".strip() for skill in data.skills]
    ids = [skill.id for skill in data.skills]
    if not passages:
        empty = np.zeros((0, 0))
        _EMBED_CACHE = (marker, empty, [])
        return empty, []
    encoded = model.encode(passages, batch_size=32, normalize_embeddings=True)
    matrix = np.vstack([_unit(row) for row in encoded])
    _EMBED_CACHE = (marker, matrix, ids)
    return matrix, ids


def normalize(text: str) -> str | None:
    """Map free text to a skill id using synonyms, case, and light typos."""
    folded = fold(text)
    if not folded:
        return None
    data = catalog()
    exact = data.exact.get(folded)
    if exact:
        return exact
    fuzzy = _fuzzy(folded, data.exact)
    if fuzzy:
        return fuzzy
    return _embedding_fallback(folded)


def normalize_domain(text: str) -> str | None:
    folded = fold(text)
    if not folded:
        return None
    data = catalog()
    exact = data.domain_exact.get(folded)
    if exact:
        return exact
    return _fuzzy(folded, data.domain_exact)


def decay_of(skill_id: str) -> str | None:
    for skill in catalog().skills:
        if skill.id == skill_id:
            return skill.decay
    return None


def search_skills(query: str = "", limit: int = 10) -> list[Skill]:
    size = 10 if limit is None else max(1, min(int(limit), 50))
    data = catalog()
    folded = fold(query)
    if not folded:
        return data.skills[:size]
    ranked: list[tuple[int, str, Skill]] = []
    distance_limit = _max_distance(len(folded))
    for skill in data.skills:
        keys = [fold(skill.id), fold(skill.name), *[fold(item) for item in skill.synonyms]]
        keys = [key for key in keys if key]
        score: int | None = None
        for key in keys:
            if key == folded or key.startswith(folded):
                score = 0
                break
        if score is None:
            for key in keys:
                if folded in key:
                    score = 1
                    break
        if score is None and distance_limit:
            best = distance_limit + 1
            for key in keys:
                if len(key) < 5:
                    continue
                distance = levenshtein(folded, key, distance_limit)
                if distance < best:
                    best = distance
            if best <= distance_limit:
                score = 2 + best
        if score is not None:
            ranked.append((score, skill.name.lower(), skill))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:size]]


def list_specializations() -> list[Specialization]:
    return list(catalog().specializations)


def list_domains() -> list[NamedItem]:
    return list(catalog().domains)


def list_decline_reasons() -> list[NamedItem]:
    return list(catalog().decline_reasons)
