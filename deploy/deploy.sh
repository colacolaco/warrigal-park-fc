#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Warrigal Park FC — deployment script
#
# Validates a checkout, snapshots the database, and starts the application with
# the production configuration.  Run from the repository root:
#
#   bash deploy/deploy.sh
#   APP_PORT=9000 bash deploy/deploy.sh
#
# The script is deliberately small and does nothing destructive: it never
# overwrites a database and never deletes anything.
# ---------------------------------------------------------------------------
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

APP_ENV="${APP_ENV:-production}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8080}"
APP_DB_PATH="${APP_DB_PATH:-$PROJECT_ROOT/data/warrigal_park.db}"

export APP_ENV APP_HOST APP_PORT APP_DB_PATH

echo "=============================================================="
echo "  Warrigal Park FC - deployment"
echo "  environment : $APP_ENV"
echo "  listening   : $APP_HOST:$APP_PORT"
echo "  database    : $APP_DB_PATH"
echo "=============================================================="

echo
echo "[1/5] Checking the Python runtime"
python3 --version
python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("Python 3.9 or newer is required")
print("      runtime OK")
PY

echo
echo "[2/5] Running the automated test suite"
python3 -m unittest discover -s tests -t . 2>&1 | tail -n 3

echo
echo "[3/5] Preparing the data directory"
mkdir -p "$(dirname "$APP_DB_PATH")"
if [ -f "$APP_DB_PATH" ]; then
  BACKUP="${APP_DB_PATH%.db}-$(date +%Y%m%d-%H%M%S).db.bak"
  cp "$APP_DB_PATH" "$BACKUP"
  echo "      existing database backed up to $BACKUP"
else
  echo "      no existing database; a new one will be created on first request"
fi

echo
echo "[4/5] Applying the configuration"
python3 - <<'PY'
from config import get_settings
settings = get_settings()
print("      " + settings.describe())
if settings.env == "production" and settings.seed:
    raise SystemExit(
        "APP_SEED must be false in production so the fictitious sample roster "
        "is never loaded over real club data"
    )
if settings.is_production and settings.secret_key.startswith(
    ("development", "test", "change-me", "REPLACE")
):
    print("      WARNING: APP_SECRET_KEY is still a placeholder value")
PY

echo
echo "[5/5] Starting the application (Ctrl+C to stop)"
exec python3 wsgi.py
