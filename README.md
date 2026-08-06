# Pressroom

A small, automated pipeline that turns a curated list of RSS feeds into a daily static newspaper page with a synthesized editorial, served as a multi-user Flask webapp backed by SQLite.

## To-be-added features
    1. Add a user settings panel to change the RSS feeds and reader preferences directly from the website.
    2. Update the code so it can load substacks and telegram channels as well
    3. Make use of persistence, so editorials focus on novel information, and avoid repeating things.
    4. Add calendar persistent variable, which feeds into a calendar widget which plots upcoming events.
    5. Add a map widget, showing geographical coverage.
    6. Add an alert system, where the user can setup alerts on specific topics/geographies/organization/people. 

## Webapp

The system is a Flask webapp hooked onto SQLite (`pressroom.db` at the project root).

- **Login** — connecting to the site redirects to `/login`. Credentials: demo user `titou` / `titou` (seeded from the `data/` folder).
- **Per-user data** — each user stores their own `feeds.yml` and `readers_interests.md` in the `user_files` table.
- **Per-user per-day issues** — each pipeline stage's output (`filtered_entries`, `parsed_entries`, `prepared_entries`, `editorial.mp3`) is stored in `issue_artifacts`, keyed by `(user, day)` in `issues`. History of editorials, one per day.
- **Date shown in the top bar** — is the time the pipeline ran for that issue (`issues.run_at`), not the page-rendering time.
- **Page generation on login** — after login, the latest (or a historical) issue is rendered from the database.

### Running

```bash
conda activate press_room
cd /path/to/press_room

# 1. Seed the database with the demo user 'titou' (copies data/ files in)
python src/db.py   # runs init_db() + seed_demo_user() (see __main__)

# 2. Run the pipeline for a user (writes all artifacts to SQLite)
python src/run_pipeline.py --user titou

# 3. Start the webapp (login at http://localhost:5000)
python src/app.py
```

## Database

The database is a single SQLite file `pressroom.db` at the project root, created on first run and ignored by git.

### Schema

```sql
-- One row per user account. Passwords are stored as werkzeug password hashes.
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-user configuration files: 'feeds.yml' and 'readers_interests.md'.
CREATE TABLE user_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,          -- e.g. 'feeds.yml', 'readers_interests.md'
    content    TEXT NOT NULL,          -- raw file contents
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, name)
);

-- One issue per (user, day). run_at = when the pipeline last ran for it.
CREATE TABLE issues (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day        TEXT NOT NULL,          -- ISO date, e.g. '2026-08-06'
    run_at     TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, day)
);

-- Pipeline outputs for a given issue.
CREATE TABLE issue_artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_id   INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    stage      TEXT NOT NULL,          -- 'filtered_entries' | 'parsed_entries' | 'prepared_entries' | 'editorial_mp3'
    content    BLOB NOT NULL,          -- YAML (text) or MP3 (binary)
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(issue_id, stage)
);
```

### Usage

All functions live in `src/db.py` and accept an optional `db_path` argument (defaults to `DEFAULT_DB_PATH` from `src/config.py`).

| Function | Purpose |
|---|---|
| `init_db()` | Create tables (and migrate older DBs that lack `issues.run_at`). |
| `create_user(username, password)` | Create a user; returns its id. |
| `get_user(username)` / `verify_user(username, password)` | Look up / authenticate a user. |
| `set_user_file(user_id, name, content)` / `get_user_file(user_id, name)` / `list_user_files(user_id)` | Read/write the user's config files. |
| `get_or_create_issue(user_id, day)` | Return the issue id for a user/day, creating it and stamping `run_at` if needed. |
| `set_artifact(issue_id, stage, content)` / `get_artifact(issue_id, stage)` | Store / fetch a pipeline stage output (bytes). |
| `list_issues(user_id)` / `latest_issue(user_id)` | All issues for a user (newest first) / the latest one. |
| `seed_demo_user()` | Create `titou`/`titou`, copy `data/` files into `user_files`, and seed today's issue with the demo artifacts. |

## What it does

1. **Scrape** – fetches the RSS feeds listed in the user's `feeds.yml`, filters articles by publication date, and writes `filtered_entries`.
2. **Parse** – ranks articles by semantic similarity to the user's `readers_interests.md`, diversifies sources, reranks the top candidates with an LLM for diversity and importance, assigns theme and country tags to each selected article ("international" if multiple countries are concerned), translates non-French text to French, and writes `parsed_entries`.
3. **Prepare** – writes the French editorial and headline, classifies the parsed articles into thematic sections of ~`section_size` articles each (1–2 word titles), and writes `prepared_entries`.
4. **Speak** – synthesizes the editorial to `editorial.mp3` via OpenRouter's TTS API.

All four artifacts are stored per user/day in SQLite. The newspaper HTML is generated on login from the stored data.

## Repository layout

```
.
├── data/                     # Source config + demo pipeline outputs (seeded for 'titou')
│   ├── additional_rerank_prompt.md
│   ├── edito.md              # Prompt for the editorial
│   ├── editorial.mp3         # Demo audio (also copied to DB on seed)
│   ├── feeds.yml             # Demo RSS sources (seeded for user 'titou')
│   ├── filtered_entries.yml  # Demo output (seeded)
│   ├── parsed_entries.yml    # Demo output (seeded)
│   ├── prepared_entries.yml  # Demo output (seeded)
│   ├── titre.md
│   └── readers_interests.md  # Demo reader profile (seeded)
├── pressroom.db              # SQLite database (created on first run, gitignored)
├── src/
│   ├── app.py                # Flask webapp (login + per-user page rendering)
│   ├── config.py             # Paths, model names, serve port, diversity limits
│   ├── db.py                 # SQLite schema + seed + CRUD for users/files/issues/artifacts
│   ├── editorial_to_mp3.py   # Step 4: editorial audio synthesis
│   ├── feed_reader.py        # Step 1: RSS scraping
│   ├── gen_static_page.py    # HTML generation (used at login time)
│   ├── key.py                # OpenRouter API key (gitignored)
│   ├── parse_feed.py         # Step 2: ranking, reranking, translation
│   ├── prepare_entries.py    # Step 3: editorial + section classification
│   ├── rank_entries.py       # WordLlama semantic ranking helper
│   ├── rerank_llm.py         # LLM reranking helper
│   ├── run_pipeline.py       # Per-user pipeline trigger (writes to SQLite)
│   ├── serve.py              # Legacy static file server
│   └── templates/
│       ├── article.html
│       ├── login.html
│       ├── page.css
│       ├── page.html
│       ├── page.js
│       └── reader.html
└── README.md
```

## Requirements

- Python 3.12
- Conda (the project uses a Conda environment, not venv)
- An OpenRouter API key (stored in `src/key.py`)
- Flask

## Setup

1. Create and activate the Conda environment:

```bash
conda create -n press_room python=3.12 pyyaml feedparser requests -y
conda activate press_room
pip install wordllama openrouter flask
```

2. Add your OpenRouter API key to `src/key.py`.

3. Seed the database and run (see "Running" above).

## Running the pipeline

To compute today's issue for a user (writes all artifacts to SQLite):

```bash
conda activate press_room
cd /path/to/press_room
python src/run_pipeline.py --user titou
# optionally pin a day: python src/run_pipeline.py --user titou --day 2026-08-06
```

`run_pipeline.run_for_user()` calls each step in sequence, staging the user's
files (`feeds.yml`, `readers_interests.md`) in a temp dir and storing every
stage's output in the `issue_artifacts` table:

- `feed_reader.scrape_feeds()`
- `parse_feed.parse_and_export()`
- `prepare_entries.prepare_and_export()`
- `editorial_to_mp3.generate_editorial_mp3()`

You can also run each step individually against the `data/` folder (legacy):

```bash
python src/feed_reader.py
python src/parse_feed.py
python src/prepare_entries.py
python src/editorial_to_mp3.py
```

## Serving the webapp

Start the Flask app (login page at the root):

```bash
conda activate press_room
cd /path/to/press_room
python src/app.py
```

- Visit `http://localhost:5000/` — you will be redirected to `/login`.
- Log in as `titou` / `titou` to see the latest issue.
- Add `?day=YYYY-MM-DD` to view a historical issue stored in the database.

## Customization

- **Number of articles:** edit `DEFAULT_CANDIDATES_COUNT` and `DEFAULT_FINAL_COUNT` in `src/config.py`.
- **Section size:** edit `DEFAULT_SECTION_SIZE` in `src/config.py` to control how many articles each thematic section groups.
- **Source diversity:** edit `DEFAULT_MAX_PER_SOURCE` in `src/config.py` to cap candidates per newspaper before LLM reranking.
- **Models:** edit `DEFAULT_MODEL` (reranking/translation/title extraction), `FANCY_MODEL` (editorial), and `DEFAULT_SECTION_MODEL` (section classification) in `src/config.py`. The default slugs include `:nitro` for faster inference on OpenRouter.
- **TTS voice:** edit `DEFAULT_VOICE` in `src/editorial_to_mp3.py`.
- **Styling:** edit `src/templates/page.html`, `src/templates/article.html`, and `src/templates/page.css`.

## Notes

- The extracted headline and the pipeline run time (in French) are displayed at the top of the generated page in a large, responsive font.
- The database `pressroom.db` is created on first run and ignored by git.
