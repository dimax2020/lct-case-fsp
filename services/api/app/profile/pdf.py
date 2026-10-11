"""Standard candidate profile PDF. Cyrillic uses a real TTF when one is installed."""

import logging
from pathlib import Path

import pymupdf

from app.profile.schemas import CandidateProfile

logger = logging.getLogger(__name__)

EMPTY_FSP_LINE = "Достижений ФСП нет"
_FONT_SIZE = 11
_RECT = pymupdf.Rect(48, 48, 548, 800)

_CYRILLIC = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

_font_ready = False
_font_path: str | None = None


def transliterate(text: str) -> str:
    pieces: list[str] = []
    for char in text:
        mapped = _CYRILLIC.get(char.lower())
        if mapped is None:
            pieces.append(char)
            continue
        if char.isupper() and mapped:
            mapped = mapped[0].upper() + mapped[1:]
        pieces.append(mapped)
    return "".join(pieces)


def _enum_text(value: object) -> str:
    if value is None:
        return "—"
    raw = getattr(value, "value", value)
    text = str(raw).strip()
    return text or "—"


def profile_lines(profile: CandidateProfile) -> list[str]:
    name = profile.full_name.strip() or profile.display_name.strip() or "—"
    skills = ", ".join(item.skill_id for item in profile.skills) or "—"
    lines = [
        "Профиль кандидата",
        f"Имя: {name}",
        f"Город: {profile.city or '—'}",
        f"Специализация: {_enum_text(profile.specialization)}",
        f"Грейд: {_enum_text(profile.grade)}",
        f"Навыки: {skills}",
        "Проекты:",
    ]
    if profile.projects:
        for project in profile.projects:
            role = _enum_text(project.role)
            lines.append(f"- {project.task} ({role})")
    else:
        lines.append("- нет")
    lines.append("Достижения ФСП:")
    if profile.fsp_achievements:
        for item in profile.fsp_achievements:
            bits = [item.event, item.discipline]
            if item.place is not None:
                bits.append(f"место {item.place}")
            if item.year is not None:
                bits.append(str(item.year))
            lines.append("- " + ", ".join(bits))
    else:
        lines.append(EMPTY_FSP_LINE)
    lines.append("Ежедневные задачи:")
    if profile.daily_stories:
        for story in profile.daily_stories:
            lines.append(f"- {story.skill_label}: {story.answer}")
    else:
        lines.append("- нет")
    return lines


def _font_candidates() -> list[Path]:
    found: list[Path] = []
    here = Path(__file__).resolve()
    if len(here.parents) > 4:
        repo = here.parents[4] / "apps" / "web" / "public" / "fonts"
        if repo.is_dir():
            found.extend(sorted(repo.rglob("*.ttf")))
            found.extend(sorted(repo.rglob("*.otf")))
    system = [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"),
    ]
    return [*found, *system]


def _covers_cyrillic(path: Path) -> bool:
    try:
        font = pymupdf.Font(fontfile=str(path))
    except Exception:
        logger.info("pdf font is unreadable: %s", path)
        return False
    return font.has_glyph(ord("Д")) > 0 and font.has_glyph(ord("я")) > 0


def cyrillic_font_path() -> str | None:
    global _font_path, _font_ready
    if _font_ready:
        return _font_path
    chosen: str | None = None
    for path in _font_candidates():
        if path.is_file() and _covers_cyrillic(path):
            chosen = str(path)
            break
    _font_path = chosen
    _font_ready = True
    return _font_path


def _draw(page: pymupdf.Page, lines: list[str], fontfile: str | None) -> float:
    if fontfile:
        page.insert_font(fontname="body", fontfile=fontfile)
        fontname = "body"
    else:
        fontname = "helv"
    return page.insert_textbox(_RECT, "\n".join(lines), fontname=fontname, fontsize=_FONT_SIZE)


def _fits(lines: list[str], fontfile: str | None) -> bool:
    document = pymupdf.open()
    try:
        page = document.new_page()
        return _draw(page, lines, fontfile) >= 0
    finally:
        document.close()


def _fit_count(lines: list[str], fontfile: str | None) -> int:
    if len(lines) <= 1:
        return 1
    if _fits(lines, fontfile):
        return len(lines)
    best = 1
    low = 1
    high = len(lines) - 1
    while low <= high:
        mid = (low + high) // 2
        if _fits(lines[:mid], fontfile):
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best


def _pdf_bytes(lines: list[str], fontfile: str | None) -> bytes:
    document = pymupdf.open()
    try:
        rest = lines or [""]
        while rest:
            count = _fit_count(rest, fontfile)
            page = document.new_page()
            _draw(page, rest[:count], fontfile)
            rest = rest[count:]
        return document.tobytes()
    finally:
        document.close()


def render_profile_pdf(profile: CandidateProfile) -> bytes:
    lines = profile_lines(profile)
    font = cyrillic_font_path()
    if font is None:
        return _pdf_bytes([transliterate(line) for line in lines], None)
    try:
        return _pdf_bytes(lines, font)
    except Exception:
        logger.warning("cyrillic profile pdf failed; transliterating the body")
        return _pdf_bytes([transliterate(line) for line in lines], None)
