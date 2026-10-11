"""Code runner seam. Agent C talks to Piston; this stub is deterministic."""

from dataclasses import dataclass


@dataclass
class RunResult:
    verdict: str
    passed: int
    total: int
    stdout: str = ""
    stderr: str = ""


async def run_code(task_id: str, code: str, language: str, hidden: bool) -> RunResult:
    del task_id, code, language, hidden
    return RunResult(verdict="OK", passed=1, total=1)
