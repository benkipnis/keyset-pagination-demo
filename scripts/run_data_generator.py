#!/usr/bin/env python3
"""
Generate claims from config and load into MongoDB.
Requires .env (MONGODB_URI) and config with data_generation.* and mongodb.*.
Run from project root:  python -m scripts.run_data_generator [config_path]
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from src.config_loader import load_config
from src.data_generator import get_provider_claim_counts, run_data_generation
from src.db import get_client, get_collection
from src.indexes import ensure_claims_index


def main() -> int:
    config_path = _PROJECT_ROOT / "config" / "config.yaml"
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    if not config_path.exists():
        config_path = _PROJECT_ROOT / "config" / "config.example.yaml"
    if not config_path.exists():
        print("No config file found.")
        return 1

    config = load_config(config_path, require_uri=True)
    provider_counts = get_provider_claim_counts(config)
    total = sum(c for _, c in provider_counts)
    print(f"Will generate {total:,} claims for {len(provider_counts)} providers.")

    client = get_client()
    try:
        collection = get_collection(client, config)
        ensure_claims_index(collection)
        inserted = 0

        def progress(current: int, expected: int) -> None:
            pct = 100 * current / expected if expected else 0
            print(f"  {current:,} / {expected:,} ({pct:.1f}%)")

        inserted = run_data_generation(collection, config, progress_callback=progress)
        print(f"Inserted {inserted:,} claims.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
