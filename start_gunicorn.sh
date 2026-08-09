#!/usr/bin/env bash
set -euo pipefail

# Start the press-room Flask app with gunicorn, bound exclusively to
# 127.0.0.1:8000 so only the Nginx reverse proxy can reach it.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_PYTHON="/opt/homebrew/Caskroom/miniconda/base/envs/press_room/bin/python"
ENV_GUNICORN="/opt/homebrew/Caskroom/miniconda/base/envs/press_room/bin/gunicorn"
PYTHON="${ENV_PYTHON:-$(command -v python)}"
GUNICORN="${ENV_GUNICORN:-$(command -v gunicorn)}"

cd "$PROJECT_DIR"

# Idempotent: create/migrate tables on a fresh clone that hasn't seeded the DB.
"$PYTHON" -c "import src.db as d; d.init_db()"

exec "$GUNICORN" \
  -b 127.0.0.1:8000 \
  -w 1 \
  --threads 4 \
  --worker-class gthread \
  --timeout 120 \
  --chdir "$PROJECT_DIR" \
  'app:create_app()'
