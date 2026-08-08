"""Central, overridable configuration.

Every default can be overridden in ``config.yml`` (a YAML file at the project
root). If ``config.yml`` is absent (or a key is missing), the built-in defaults
defined here are used, so the project works without any configuration file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yml"


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Load config.yml; returns {} if the file is missing or invalid."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


_CFG: dict[str, Any] = load_config()


def _section(key: str) -> dict[str, Any]:
    value = _CFG.get(key, {})
    return value if isinstance(value, dict) else {}


def _resolve_path(value: Any, base: Path, default: Path) -> Path:
    if value is None or str(value).strip() == "":
        return default
    p = Path(str(value))
    return p if p.is_absolute() else (base / p)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --- paths ------------------------------------------------------------------
_PATHS = _section("paths")

_data_dir_raw = _PATHS.get("data_dir", "data")
_data_dir_path = Path(str(_data_dir_raw))
DATA_DIR = (
    _data_dir_path if _data_dir_path.is_absolute() else PROJECT_ROOT / _data_dir_path
)


def _data_file(key: str, default: str) -> Path:
    return _resolve_path(_PATHS.get(key, default), DATA_DIR, DATA_DIR / default)


DEFAULT_FEEDS_PATH = _data_file("feeds", "feeds.yml")
DEFAULT_ENTRIES_PATH = _data_file("filtered_entries", "filtered_entries.yml")
DEFAULT_PARSED_ENTRIES_PATH = _data_file("parsed_entries", "parsed_entries.yml")
DEFAULT_PREPARED_ENTRIES_PATH = _data_file("prepared_entries", "prepared_entries.yml")
DEFAULT_MP3_PATH = _data_file("mp3", "editorial.mp3")
DEFAULT_INTERESTS_PATH = _data_file("interests", "readers_interests.md")
DEFAULT_TITLE_GUIDE_PATH = _data_file("title_guide", "titre.md")
DEFAULT_ARRANK_PROMPT_PATH = _data_file("additional_rerank_prompt", "additional_rerank_prompt.md")
DEFAULT_DB_PATH = _data_file("db", "pressroom.db")
DEFAULT_TEMPLATE_DIR = _resolve_path(
    _PATHS.get("template_dir"),
    PROJECT_ROOT,
    PROJECT_ROOT / "src" / "templates",
)

# --- models -----------------------------------------------------------------
_MODELS = _section("models")

DEFAULT_MODEL = str(_MODELS.get("default", "qwen/qwen-2.5-7b-instruct:nitro"))
FANCY_MODEL = str(_MODELS.get("fancy", "deepseek/deepseek-v4-flash-0731:nitro"))
DEFAULT_SECTION_MODEL = str(_MODELS.get("section", FANCY_MODEL))

# --- pipeline ---------------------------------------------------------------
_PIPELINE = _section("pipeline")

DEFAULT_CANDIDATES_COUNT = _as_int(_PIPELINE.get("candidates_count"), 120)
DEFAULT_FINAL_COUNT = _as_int(_PIPELINE.get("final_count"), 50)
DEFAULT_MAX_PER_SOURCE = _as_int(_PIPELINE.get("max_per_source"), 10)
DEFAULT_SECTION_SIZE = _as_int(_PIPELINE.get("section_size"), 5)

# --- editorial --------------------------------------------------------------
_EDITORIAL = _section("editorial")

DEFAULT_EDITORIAL_MINUTES = _as_int(_EDITORIAL.get("minutes"), 5)

# --- web --------------------------------------------------------------------
_WEB = _section("web")

SECRET_KEY = str(_WEB.get("secret_key", "dev-secret-change-me"))
SERVE_PORT = _as_int(_WEB.get("port"), 8080)

# --- archive.ph exclusions --------------------------------------------------
_DEFAULT_EXCLUDED_DOMAINS = [
    "blog.mondediplo.net",
    "politico.eu",
    "politico.com",
    "rts.ch",
    "srf.ch",
    "eldiario.es",
    "elpais.com",
    "lvsl.fr",
    "contretemps.eu",
    "chinadaily.com.cn",
    "mediapart.fr",
    "news.cgtn.com",
    "granma.cu",
    "cubadebate.cu",
    "jornada.com",
    "solidaire.org",
    "orientxxi.info",
]

_excluded = _CFG.get("excluded_domains")
if _excluded is None:
    DEFAULT_EXCLUDED_DOMAINS = set(_DEFAULT_EXCLUDED_DOMAINS)
else:
    DEFAULT_EXCLUDED_DOMAINS = {
        str(d).strip() for d in _excluded if str(d).strip()
    }

# --- pipeline schedule ------------------------------------------------------
_SCHEDULE = _section("schedule")

SCHEDULE_ENABLED = bool(_SCHEDULE.get("enabled", True))
SCHEDULE_TIME = str(_SCHEDULE.get("time", "06:00"))
SCHEDULE_USERS = [u for u in (_SCHEDULE.get("users") or ["titou"]) if u]
SCHEDULE_TIMEZONE = str(_SCHEDULE.get("timezone", "Europe/Paris"))


def schedule_clock() -> tuple[int, int]:
    """Return (hour, minute) parsed from SCHEDULE_TIME (fallback 06:00)."""
    try:
        hour, _, minute = SCHEDULE_TIME.partition(":")
        return int(hour), int(minute)
    except ValueError:
        return 6, 0


def schedule_timezone() -> "ZoneInfo":
    """Return the schedule IANA timezone, falling back to Europe/Paris if invalid."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return ZoneInfo(SCHEDULE_TIMEZONE)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Europe/Paris")