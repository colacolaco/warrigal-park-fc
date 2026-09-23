"""Configuration loader.

Configuration is separated from code so that the same source tree can be
deployed to development, test and production without modification.  Values are
resolved in this order (first match wins):

1. real environment variables (set by the shell, a container runtime or CI),
2. the ``.env`` file in the project root, if present,
3. the built-in defaults in :data:`DEFAULTS`.

Only ``config/env.example`` is version controlled.  Every real ``.env`` file is
listed in ``.gitignore``, so credentials and machine-specific paths can never be
committed by accident.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULTS = {
    "APP_ENV": "development",
    "APP_HOST": "127.0.0.1",
    "APP_PORT": "5000",
    "APP_DB_PATH": "data/warrigal_park.db",
    "DATABASE_URL": "",
    "APP_SEED": "true",
    "APP_DEBUG": "false",
    "APP_SECRET_KEY": "development-only-secret",
}

_TRUTHY = {"1", "true", "yes", "on"}


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Read a simple ``KEY=VALUE`` file and return the parsed pairs.

    The parser deliberately supports only the small subset of the format that
    this project needs: blank lines, ``#`` comments, optional surrounding
    quotes and an optional ``export`` prefix.  That keeps the application free
    of third-party dependencies.
    """
    path = path or PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    """Immutable, validated application settings."""

    env: str
    host: str
    port: int
    db_path: Path
    database_url: str
    seed: bool
    debug: bool
    secret_key: str
    source: str = field(default="defaults")

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def is_test(self) -> bool:
        return self.env == "test"

    def describe(self) -> str:
        """Single-line summary printed at start-up (never prints secrets)."""
        return (
            f"env={self.env} host={self.host} port={self.port} "
            f"db={self.db_path} seed={self.seed} debug={self.debug} "
            f"config-source={self.source}"
        )


def _as_bool(value: str) -> bool:
    return str(value).strip().lower() in _TRUTHY


def get_settings(env_file: Path | None = None, **overrides: object) -> Settings:
    """Build the effective :class:`Settings` for this process."""
    file_values = load_dotenv(env_file)

    def resolve(key: str) -> str:
        if key in overrides and overrides[key] is not None:
            return str(overrides[key])
        if key in os.environ:
            return os.environ[key]
        if key in file_values:
            return file_values[key]
        return DEFAULTS[key]

    db_path = Path(resolve("APP_DB_PATH"))
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    if overrides or os.environ.get("APP_ENV") or file_values:
        source = "environment/.env"
    else:
        source = "built-in defaults"

    env = resolve("APP_ENV").strip().lower()
    if env not in {"development", "test", "production"}:
        raise ValueError(
            f"APP_ENV must be development, test or production (got {env!r})"
        )

    try:
        port = int(resolve("APP_PORT"))
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError("APP_PORT must be an integer") from exc

    return Settings(
        env=env,
        host=resolve("APP_HOST"),
        port=port,
        db_path=db_path,
        database_url=resolve("DATABASE_URL"),
        seed=_as_bool(resolve("APP_SEED")),
        debug=_as_bool(resolve("APP_DEBUG")),
        secret_key=resolve("APP_SECRET_KEY"),
        source=source,
    )
