"""Piston client. Limits: 2s CPU and 256 MB. Transport errors become PENDING upstream."""

import logging
import re
from dataclasses import dataclass

import httpx

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

CPU_LIMIT_MS = 2_000
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
WALL_LIMIT_MS = 5_000
COMPILE_WALL_MS = 10_000

_FILENAMES = {"python": "main.py", "go": "main.go"}
_LANGUAGE_ALIASES = {
    "python": "python",
    "python3": "python",
    "py": "python",
    "go": "go",
    "golang": "go",
}

_SEVERITY = {
    "OK": 0,
    "WRONG_ANSWER": 1,
    "RUNTIME_ERROR": 2,
    "COMPILE_ERROR": 3,
    "MEMORY_LIMIT": 4,
    "TIME_LIMIT": 5,
    "PENDING": 6,
}


@dataclass(frozen=True)
class StageOutcome:
    problem: str | None
    stdout: str
    stderr: str


def canonical_language(language: str) -> str | None:
    return _LANGUAGE_ALIASES.get(language.strip().lower())


def normalize_output(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(line.rstrip() for line in lines)


def worse(left: str, right: str) -> str:
    return left if _SEVERITY.get(left, 0) >= _SEVERITY.get(right, 0) else right


def build_payload(language: str, code: str, stdin: str) -> dict[str, object]:
    return {
        "language": language,
        "version": "*",
        "files": [{"name": _FILENAMES[language], "content": code}],
        "stdin": stdin,
        "args": [],
        "compile_timeout": COMPILE_WALL_MS,
        "run_timeout": WALL_LIMIT_MS,
        "compile_cpu_time": CPU_LIMIT_MS,
        "run_cpu_time": CPU_LIMIT_MS,
        "compile_memory_limit": MEMORY_LIMIT_BYTES,
        "run_memory_limit": MEMORY_LIMIT_BYTES,
    }


def _problem(stage: dict[str, object], *, compile: bool) -> str | None:
    signal = str(stage.get("signal") or "")
    blob = " ".join(str(stage.get(key) or "") for key in ("stderr", "stdout", "output", "message")).lower()
    # Match whole words so a runtime panic like "boom" is not treated as OOM.
    if re.search(r"out of memory|memory limit|cannot allocate|\boom\b|oom-kill", blob):
        return "MEMORY_LIMIT"
    timed = signal == "SIGXCPU" or any(token in blob for token in ("time limit", "timed out", "cpu time limit"))
    if timed or signal == "SIGKILL":
        return "TIME_LIMIT"
    code = stage.get("code")
    if code not in (0, None) or signal:
        return "COMPILE_ERROR" if compile else "RUNTIME_ERROR"
    return None


def interpret(payload: dict[str, object]) -> StageOutcome:
    compile_stage = payload.get("compile")
    if isinstance(compile_stage, dict) and _problem(compile_stage, compile=True):
        return StageOutcome(
            problem=_problem(compile_stage, compile=True),
            stdout=str(compile_stage.get("stdout") or ""),
            stderr=str(compile_stage.get("stderr") or ""),
        )
    run = payload.get("run")
    if not isinstance(run, dict):
        return StageOutcome(problem="RUNTIME_ERROR", stdout="", stderr="")
    return StageOutcome(
        problem=_problem(run, compile=False),
        stdout=str(run.get("stdout") or ""),
        stderr=str(run.get("stderr") or ""),
    )


async def post_execute(payload: dict[str, object]) -> dict[str, object]:
    settings = get_settings()
    url = settings.piston_url.rstrip("/") + "/api/v2/execute"
    async with httpx.AsyncClient(timeout=8.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("piston returned a non-object")
    return data


def clip(parts: list[str], limit: int = 4000) -> str:
    text = "\n---\n".join(parts)
    if len(text) <= limit:
        return text
    return text[:limit]


def log_piston_failure(exc: Exception) -> None:
    logger.warning("piston request failed: %s", exc)
