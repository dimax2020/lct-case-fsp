"""extract(schema_name, text) -> dict. Agent B implements the client and the evidence check."""

import json
from pathlib import Path

from app.core.errors import AppError

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def load_schema(schema_name: str) -> dict:
    path = SCHEMA_DIR / f"{schema_name}.json"
    if not path.is_file():
        raise AppError("not_found", f"Неизвестная схема извлечения: {schema_name}", status_code=404)
    return json.loads(path.read_text(encoding="utf-8"))


async def extract(schema_name: str, text: str) -> dict:
    """Phase-0 stub. Returns an empty document that still matches the schema shape."""
    load_schema(schema_name)
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
