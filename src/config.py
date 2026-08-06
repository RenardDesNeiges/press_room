from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

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

DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"

DEFAULT_DB_PATH = PROJECT_ROOT / "pressroom.db"
SECRET_KEY = "dev-secret-change-me"

SERVE_PORT = 8080
