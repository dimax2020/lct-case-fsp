"""Выгружает тест рабочего стиля для моков фронтенда (apps/web/app/api/mock/psych-bank.json).

Запуск из services/api: python scripts/export_psych_bank.py
Ключ попадает только в мок-режим фронтенда (NUXT_PUBLIC_API_MOCKS=1), где бэкенда нет.
В боевом режиме ключ остаётся на сервере.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.psych import bank  # noqa: E402

TARGET = Path(__file__).resolve().parents[3] / "apps" / "web" / "app" / "api" / "mock" / "psych-bank.json"


def main() -> None:
    payload = {
        "public": bank.public_test(),
        "key": {
            "disc": [[scale for _, scale in block] for block in bank.DISC_BLOCKS],
            "disc_info": bank.DISC_INFO,
            "statements": bank.STATEMENT_KEY,
            "social_items": bank.SOCIAL_DESIRABILITY_ITEMS,
            "social_flag": bank.SOCIAL_DESIRABILITY_FLAG,
            "cases": [{"scales": list(case["scales"]), "points": [list(p) for p in case["points"]]} for case in bank.CASES],
            "scale_info": bank.SCALE_INFO,
            "levels": {key: list(value) for key, value in bank.LEVEL_TEXT.items()},
            "fits": bank.FIT_PROFILES,
            "limitations": bank.LIMITATIONS,
        },
    }
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"written {TARGET}")


if __name__ == "__main__":
    main()
