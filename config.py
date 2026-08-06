from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_PATH = PROJECT_ROOT / "config.yml"

DEFAULT_FEEDS_PATH = DATA_DIR / "feeds.yml"
DEFAULT_ENTRIES_PATH = DATA_DIR / "filtered_entries.yml"
DEFAULT_PARSED_ENTRIES_PATH = DATA_DIR / "parsed_entries.yml"
DEFAULT_PREPARED_ENTRIES_PATH = DATA_DIR / "prepared_entries.yml"
DEFAULT_MP3_PATH = DATA_DIR / "editorial.mp3"

DEFAULT_MODEL = "qwen/qwen-2.5-7b-instruct:nitro"
FANCY_MODEL = "deepseek/deepseek-v4-flash-0731:nitro"
DEFAULT_INTERESTS_PATH = DATA_DIR / "readers_interests.md"
DEFAULT_TITLE_GUIDE_PATH = DATA_DIR / "titre.md"
DEFAULT_ARRANK_PROMPT_PATH = DATA_DIR / "additional_rerank_prompt.md"

DEFAULT_CANDIDATES_COUNT = 120
DEFAULT_FINAL_COUNT = 50
# DEFAULT_CANDIDATES_COUNT = 15
# DEFAULT_FINAL_COUNT = 4
DEFAULT_MAX_PER_SOURCE = 10
DEFAULT_SECTION_SIZE = 5
DEFAULT_SECTION_MODEL = FANCY_MODEL

DEFAULT_TEMPLATE_DIR = PROJECT_ROOT / "src" / "templates"

DEFAULT_DB_PATH = DATA_DIR / "pressroom.db"
SECRET_KEY = "dev-secret-change-me"

SERVE_PORT = 8080

#: Domains excluded from the archive.ph wrapper by default (fallback for users
#: who have not set their own list in the database).
DEFAULT_EXCLUDED_DOMAINS = {
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
}


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load config.yml; returns {} if the file is missing."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


_schedule = load_config().get("schedule", {})

#: Whether the webapp should run the pipeline on a daily schedule.
SCHEDULE_ENABLED = bool(_schedule.get("enabled", True))

#: Local clock time ("HH:MM") at which the daily pipeline run happens.
SCHEDULE_TIME = str(_schedule.get("time", "06:00"))

#: Usernames to run the pipeline for each day.
SCHEDULE_USERS = [u for u in (_schedule.get("users") or ["titou"]) if u]


def schedule_clock() -> tuple[int, int]:
    """Return (hour, minute) parsed from SCHEDULE_TIME (fallback 06:00)."""
    try:
        hour, _, minute = SCHEDULE_TIME.partition(":")
        return int(hour), int(minute)
    except ValueError:
        return 6, 0
