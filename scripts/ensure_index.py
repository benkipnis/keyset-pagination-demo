#!/usr/bin/env python3
"""
Connect to MongoDB and create the claims compound index if it does not exist.
Idempotent: safe to run multiple times.
Requires .env with MONGODB_URI and config (default: config/config.example.yaml or config/config.yaml).

Run from project root:  python -m scripts.ensure_index [config_path]
"""

from __future__ import annotations

import sys
from pathlib import Path

# Project root and path setup
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from pymongo.errors import OperationFailure

from src.config_loader import load_config
from src.db import get_client, get_collection
from src.indexes import ensure_claims_index


def main() -> int:
    config_path = _PROJECT_ROOT / "config" / "config.yaml"
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    if not config_path.exists():
        config_path = _PROJECT_ROOT / "config" / "config.example.yaml"
    if not config_path.exists():
        print("No config file found. Create config/config.yaml or config/config.example.yaml.")
        return 1

    config = load_config(config_path, require_uri=True)
    client = get_client()
    try:
        collection = get_collection(client, config)
        try:
            index_name = ensure_claims_index(collection)
            print(f"Index ready: {index_name}")
            return 0
        except OperationFailure as e:
            if e.details and e.details.get("code") == 13:
                print(
                    "Not authorized to create indexes. Grant your Atlas database user "
                    "readWrite on this database only (see Docs/MONGODB_PERMISSIONS.md)."
                )
                return 1
            raise
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
