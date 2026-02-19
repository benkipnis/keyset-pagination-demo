#!/usr/bin/env python3
"""
Validate that .env is loaded and MONGODB_URI is set and valid.
Run from project root:  python -m scripts.validate_env
Or:  python scripts/validate_env.py  (from project root)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Resolve project root (parent of scripts/) and load .env from there so this works from any cwd
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(_PROJECT_ROOT / ".env")

from src.config_loader import ConfigError, get_mongodb_uri


def is_valid_mongodb_uri(uri: str) -> bool:
    """Return True if URI looks like a MongoDB connection string."""
    return (
        uri.startswith("mongodb://")
        or uri.startswith("mongodb+srv://")
    ) and " " not in uri.strip()


def main() -> int:
    print("Validating .env and MONGODB_URI...")
    try:
        uri = get_mongodb_uri()
    except ConfigError as e:
        print(f"FAIL: {e}")
        return 1

    if not uri:
        print("FAIL: MONGODB_URI is set but empty.")
        return 1

    if not is_valid_mongodb_uri(uri):
        print("FAIL: MONGODB_URI does not look like a MongoDB URI (expected mongodb:// or mongodb+srv://, no spaces).")
        return 1

    print("OK: MONGODB_URI is set and format is valid.")

    # Optional: ping MongoDB (don't print URI)
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        client.close()
        print("OK: Successfully connected to MongoDB (ping succeeded).")
    except Exception as e:
        print(f"WARN: Could not connect to MongoDB: {e}")
        print("      (URI format is valid; check network, credentials, or firewall.)")
        return 0  # Still pass if format is valid

    return 0


if __name__ == "__main__":
    sys.exit(main())
