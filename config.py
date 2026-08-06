from pathlib import Path

DEFAULT_FEEDS_PATH = Path("data/feeds.yml")
DEFAULT_ENTRIES_PATH = Path("data/filtered_entries.yml")
DEFAULT_PARSED_ENTRIES_PATH = Path("data/parsed_entries.yml")
DEFAULT_PREPARED_ENTRIES_PATH = Path("data/prepared_entries.yml")
DEFAULT_MP3_PATH = Path("data/editorial.mp3")

DEFAULT_MODEL = "qwen/qwen-2.5-7b-instruct:nitro"
FANCY_MODEL = "deepseek/deepseek-v4-flash-0731:nitro"
DEFAULT_INTERESTS_PATH = Path("data/readers_interests.md")
DEFAULT_TITLE_GUIDE_PATH = Path("data/titre.md")
DEFAULT_ARRANK_PROMPT_PATH = Path("data/additional_rerank_prompt.md")

DEFAULT_CANDIDATES_COUNT = 120
DEFAULT_FINAL_COUNT = 50
# DEFAULT_CANDIDATES_COUNT = 15
# DEFAULT_FINAL_COUNT = 4
DEFAULT_MAX_PER_SOURCE = 10
DEFAULT_SECTION_SIZE = 5
DEFAULT_SECTION_MODEL = FANCY_MODEL

DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"

SERVE_PORT = 8080
