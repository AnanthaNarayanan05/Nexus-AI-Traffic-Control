"""Central configuration loader (spec section 92).

All tunables live in ``configs/config.yaml``; environment variables (``.env``) override
paths and deployment settings only. The resolved config is a frozen, typed object.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

# --- repo layout -----------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_CONFIG_FILE = REPO_ROOT / "configs" / "config.yaml"


def _load_dotenv() -> None:
    """Minimal .env loader (no dependency on python-dotenv at import time)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


class Settings(BaseModel):
    """Deployment/runtime settings (from environment, with defaults)."""

    model_config = ConfigDict(frozen=True)

    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    env: str = "development"

    models_dir: Path = REPO_ROOT / "models"
    data_dir: Path = REPO_ROOT / "data"
    db_url: str = f"sqlite:///{(REPO_ROOT / 'data' / 'nexus.db').as_posix()}"

    sim_adapter: str = "builtin"  # builtin | sumo
    sumo_home: str = ""
    sumo_binary: str = "sumo"
    sumo_config: str = ""

    config_file: Path = DEFAULT_CONFIG_FILE

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv()
        g = os.environ.get
        return cls(
            host=g("NEXUS_HOST", "127.0.0.1"),
            port=int(g("NEXUS_PORT", "8000")),
            log_level=g("NEXUS_LOG_LEVEL", "INFO"),
            env=g("NEXUS_ENV", "development"),
            models_dir=Path(g("NEXUS_MODELS_DIR", str(REPO_ROOT / "models"))),
            data_dir=Path(g("NEXUS_DATA_DIR", str(REPO_ROOT / "data"))),
            db_url=g("NEXUS_DB_URL", f"sqlite:///{(REPO_ROOT / 'data' / 'nexus.db').as_posix()}"),
            sim_adapter=g("NEXUS_SIM_ADAPTER", "builtin"),
            sumo_home=g("SUMO_HOME", ""),
            sumo_binary=g("NEXUS_SUMO_BINARY", "sumo"),
            sumo_config=g("NEXUS_SUMO_CONFIG", ""),
            config_file=Path(g("NEXUS_CONFIG_FILE", str(DEFAULT_CONFIG_FILE))),
        )


class Config(dict):
    """Dict-with-attribute-access wrapper around the YAML config.

    Kept intentionally simple: nested access via ``cfg.simulation.decision_interval_s``
    or ``cfg["simulation"]["decision_interval_s"]``. Values are read-only in practice.
    """

    def __getattr__(self, item: str) -> Any:
        try:
            value = self[item]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(item) from exc
        if isinstance(value, dict) and not isinstance(value, Config):
            value = Config(value)
            self[item] = value
        return value

    @property
    def digest(self) -> str:
        """Stable hash of the config, for experiment reproducibility blobs."""
        blob = json.dumps(self, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()


@functools.lru_cache(maxsize=1)
def get_config() -> Config:
    path = get_settings().config_file
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return Config(raw)


def reload() -> None:
    """Clear caches (used by tests and the /config reload endpoint)."""
    get_settings.cache_clear()
    get_config.cache_clear()
