"""extract(schema_name, text) -> dict. Drops fields whose quote is not in the source."""

import asyncio
import json
import logging
import unicodedata
from pathlib import Path
from typing import Any

from openai import APIConnectionError, AsyncOpenAI, InternalServerError, RateLimitError

from app.core.errors import AppError
from app.core.settings import get_settings

logger = logging.getLogger(__name__)

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
MAX_INPUT_CHARS = 20_000
LLM_TIMEOUT_SECONDS = 30.0
LLM_ATTEMPTS = 3
RETRYABLE = (APIConnectionError, RateLimitError, InternalServerError, json.JSONDecodeError, ValueError)

SYSTEM_PROMPT = (
    "Извлеки факты строго по JSON-схеме. "
    "evidence_span каждой записи — дословная подстрока исходного текста. "
    "Не добавляй факты, которых нет в тексте. Пустые списки и null допустимы."
)


def load_schema(schema_name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / f"{schema_name}.json"
    if not path.is_file():
        raise AppError("not_found", f"Неизвестная схема извлечения: {schema_name}", status_code=404)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AppError("not_found", f"Неизвестная схема извлечения: {schema_name}", status_code=404)
    return loaded


def sanitize(text: str, limit: int = MAX_INPUT_CHARS) -> str:
    """Drop invisible and control characters, then cap the length."""
    if not text:
        return ""
    kept: list[str] = []
    for char in text:
        if char in "\n\r\t":
            kept.append(char)
            continue
        if unicodedata.category(char).startswith("C"):
            continue
        kept.append(char)
    return "".join(kept)[:limit]


def _phase0(schema_name: str, text: str) -> dict[str, Any]:
    if schema_name == "resume":
        return {"experiences": [], "skills": [], "projects": []}
    if schema_name == "evidence_unit":
        return {
            "task": text[:200],
            "domain": None,
            "skills": [],
            "role": "participant",
            "date": None,
            "evidence_span": text[:200],
        }
    if schema_name == "need_requirements":
        return {"requirements": []}
    if schema_name == "need_category":
        return {
            "specialization": "backend",
            "grades": ["middle"],
            "domain": None,
            "evidence_span": text[:200],
        }
    return {}


def _rejected(schema_name: str) -> dict[str, Any]:
    if schema_name == "evidence_unit":
        return {
            "task": "",
            "domain": None,
            "skills": [],
            "role": "participant",
            "date": None,
            "evidence_span": "",
        }
    if schema_name == "need_category":
        return {"specialization": None, "grades": [], "domain": None, "evidence_span": ""}
    return _phase0(schema_name, "")


def _span_ok(span: object, source: str) -> bool:
    return isinstance(span, str) and bool(span.strip()) and span.strip() in source


def _filter_extracted(value: Any, source: str) -> Any:
    if isinstance(value, list):
        kept: list[Any] = []
        for item in value:
            filtered = _filter_extracted(item, source)
            if filtered is not None:
                kept.append(filtered)
        return kept
    if isinstance(value, dict):
        if "evidence_span" in value and not _span_ok(value.get("evidence_span"), source):
            return None
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key == "evidence_span" and isinstance(item, str):
                cleaned[key] = item.strip()
                continue
            if isinstance(item, dict | list):
                filtered = _filter_extracted(item, source)
                if filtered is None:
                    continue
                cleaned[key] = filtered
            else:
                cleaned[key] = item
        return cleaned
    return value


async def _once(schema_name: str, text: str) -> dict[str, Any]:
    settings = get_settings()
    schema = load_schema(schema_name)
    payload_schema = {key: value for key, value in schema.items() if key != "$schema"}
    client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=0,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.llm_model,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": payload_schema},
            },
        )
    finally:
        await client.close()
    content = response.choices[0].message.content or "{}"
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("llm response is not a json object")
    return data


async def _complete(schema_name: str, text: str) -> dict[str, Any]:
    delay = 0.05
    last: Exception | None = None
    for attempt in range(LLM_ATTEMPTS):
        try:
            return await _once(schema_name, text)
        except RETRYABLE as exc:
            last = exc
            logger.warning("llm %s attempt %s failed: %s", schema_name, attempt + 1, exc)
            if attempt + 1 < LLM_ATTEMPTS:
                await asyncio.sleep(delay)
                delay *= 2
    if last is None:
        raise RuntimeError("llm extract did not run")
    raise last


async def extract(schema_name: str, text: str) -> dict[str, Any]:
    """Structured extraction. When LLM_ENABLED is off, return the phase-0 shape."""
    load_schema(schema_name)
    clean = sanitize(text)
    if not get_settings().llm_enabled:
        return _phase0(schema_name, clean)
    try:
        raw = await _complete(schema_name, clean)
    except Exception:
        logger.exception("llm extract failed for %s", schema_name)
        return _phase0(schema_name, clean)
    filtered = _filter_extracted(raw, clean)
    if not isinstance(filtered, dict):
        return _rejected(schema_name)
    return filtered
