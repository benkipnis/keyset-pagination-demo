"""
Load application configuration from a YAML file and environment variables.
Secrets (e.g. MONGODB_URI) are read from the environment only; never from the config file.

A .env file in the project root is loaded automatically so you can set MONGODB_URI there.
Copy .env.example to .env and fill in your Atlas connection string.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Load .env from current working directory (project root when run as python -m ...)
load_dotenv()

# Environment key for MongoDB connection string (required when connecting to DB)
MONGODB_URI_ENV = "MONGODB_URI"


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""

    pass


def load_config(config_path: str | Path, require_uri: bool = False) -> dict[str, Any]:
    """
    Load configuration from a YAML file and optionally inject MONGODB_URI from env.

    Args:
        config_path: Path to the YAML config file.
        require_uri: If True, require MONGODB_URI to be set in the environment
            and add it to config["mongodb"]["uri"]. Raises ConfigError if unset.

    Returns:
        Config dict with keys: mongodb, data_generation, query, performance.
        If require_uri is True, config["mongodb"]["uri"] is set from env.

    Raises:
        ConfigError: If the file cannot be read, YAML is invalid, or require_uri
            is True and MONGODB_URI is not set.
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    with open(path, encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a YAML object (key-value), got {type(data)}")

    # Ensure expected top-level keys exist so callers can assume structure
    config = {
        "mongodb": data.get("mongodb") or {},
        "data_generation": data.get("data_generation") or {},
        "query": data.get("query") or {},
        "performance": data.get("performance") or {},
    }

    if require_uri:
        uri = os.environ.get(MONGODB_URI_ENV)
        if not uri or not uri.strip():
            raise ConfigError(
                f"{MONGODB_URI_ENV} must be set in the environment when connecting to MongoDB"
            )
        config["mongodb"] = {**config["mongodb"], "uri": uri.strip()}

    return config


def get_mongodb_uri() -> str:
    """
    Return MongoDB URI from the environment.
    Raises ConfigError if MONGODB_URI is not set.
    """
    uri = os.environ.get(MONGODB_URI_ENV)
    if not uri or not uri.strip():
        raise ConfigError(
            f"{MONGODB_URI_ENV} must be set in the environment when connecting to MongoDB"
        )
    return uri.strip()
