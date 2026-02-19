#!/usr/bin/env python3
"""
Run the claims facet-by-provider aggregation and print results.
Requires .env (MONGODB_URI) and config. Optional: --date-start, --date-end (YYYY-MM-DD).

  python -m scripts.run_facet_by_provider
  python -m scripts.run_facet_by_provider --date-start 2002-01-01 --date-end 2002-12-31
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from src.config_loader import load_config
from src.db import get_client, get_collection
from src.aggregations import run_claims_facet_by_provider


def main() -> int:
    ap = argparse.ArgumentParser(description="Facet claims by provider (billingProvider.providerId)")
    ap.add_argument("--date-start", default=None, help="Filter: serviceEndDate >= date (YYYY-MM-DD)")
    ap.add_argument("--date-end", default=None, help="Filter: serviceBeginDate <= date (YYYY-MM-DD)")
    ap.add_argument("--limit", type=int, default=20, help="Max number of providers to print (default 20)")
    ap.add_argument("--json", action="store_true", help="Output full result as JSON")
    args = ap.parse_args()

    config_path = _PROJECT_ROOT / "config" / "config.yaml"
    if not config_path.exists():
        config_path = _PROJECT_ROOT / "config" / "config.example.yaml"
    config = load_config(config_path, require_uri=True)

    client = get_client()
    try:
        collection = get_collection(client, config)
        results = run_claims_facet_by_provider(
            collection,
            service_date_start=args.date_start,
            service_date_end=args.date_end,
        )
        if args.json:
            print(json.dumps(results, default=str, indent=2))
        else:
            total_claims = sum(r["count"] for r in results)
            print(f"Providers: {len(results)}, Total claims: {total_claims}\n")
            for i, r in enumerate(results[: args.limit]):
                print(f"  {r['providerId']}: {r['count']:,} claims  (min begin: {r.get('minServiceBeginDate')}, max end: {r.get('maxServiceEndDate')})")
            if len(results) > args.limit:
                print(f"  ... and {len(results) - args.limit} more providers")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
