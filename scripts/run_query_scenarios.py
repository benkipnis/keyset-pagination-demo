#!/usr/bin/env python3
"""
Run the three query-scenario use cases with user-supplied providerId and optional service date.
  python -m scripts.run_query_scenarios --provider-id 00-000001
  python -m scripts.run_query_scenarios --provider-id 00-000001 --date-start 2002-01-01 --date-end 2002-12-31
  python -m scripts.run_query_scenarios --provider-id 00-000001 --page-size 10
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from src.config_loader import load_config
from src.db import get_client, get_collection
from src.query_scenarios import (
    get_first_page_aggregation_pipeline,
    use_case_count_documents,
    use_case_find,
    use_case_first_page_aggregation,
    use_case_first_page_count_and_find,
    use_case_next_page_find,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run query scenarios by providerId (optional service date)")
    ap.add_argument("--provider-id", required=True, help="billingProvider.providerId to query")
    ap.add_argument("--date-start", default=None, help="Optional: service date range start (YYYY-MM-DD)")
    ap.add_argument("--date-end", default=None, help="Optional: service date range end (YYYY-MM-DD)")
    ap.add_argument("--page-size", type=int, default=100, help="Page size for use case 3 (default 100)")
    ap.add_argument("--find-limit", type=int, default=None, help="Optional: max docs for use case 2 find")
    ap.add_argument("--explain", action="store_true", help="Run explain on use case 3a aggregation and print server executionTimeMillis + totalDocsExamined")
    args = ap.parse_args()

    config_path = _PROJECT_ROOT / "config" / "config.yaml"
    if not config_path.exists():
        config_path = _PROJECT_ROOT / "config" / "config.example.yaml"
    config = load_config(config_path, require_uri=True)

    client = get_client()
    try:
        collection = get_collection(client, config)

        provider_id = args.provider_id
        date_start = args.date_start
        date_end = args.date_end

        # --- Use case 1: count_documents ---
        t0 = time.perf_counter()
        total = use_case_count_documents(collection, provider_id, date_start, date_end)
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"1. count_documents()  -> total = {total:,}  ({elapsed:.2f} ms)")

        # --- Use case 2: find ---
        t0 = time.perf_counter()
        docs = use_case_find(
            collection, provider_id, date_start, date_end,
            limit=args.find_limit,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"2. find()             -> returned {len(docs):,} docs  ({elapsed:.2f} ms)")

        # --- Use case 3a: first page via $facet aggregation (total + page + keyset cursor) ---
        t0 = time.perf_counter()
        result_agg = use_case_first_page_aggregation(
            collection, provider_id,
            page_size=args.page_size,
            service_date_start=date_start,
            service_date_end=date_end,
        )
        elapsed_agg = (time.perf_counter() - t0) * 1000
        print(f"3a. agg first page    -> total={result_agg['total']:,}  numPages={result_agg['numPages']}  "
              f"documents on this page={len(result_agg['documents'])}  hasNextCursor={result_agg['nextCursor'] is not None}  (client elapsed: {elapsed_agg:.2f} ms)")

        if args.explain:
            pipeline = get_first_page_aggregation_pipeline(
                provider_id, args.page_size, date_start, date_end
            )
            try:
                explain_result = collection.database.command(
                    "explain",
                    {"aggregate": collection.name, "pipeline": pipeline, "cursor": {}},
                    verbosity="executionStats",
                )
                stats = explain_result.get("executionStats") or explain_result
                server_ms = stats.get("executionTimeMillis")
                docs_examined = stats.get("totalDocsExamined")
                if server_ms is None and "stages" in explain_result:
                    for s in explain_result.get("stages", [])[:1]:
                        server_ms = s.get("executionTimeMillis")
                        docs_examined = docs_examined or s.get("totalDocsExamined")
                        break
                if server_ms is not None:
                    print(f"    [explain] server executionTimeMillis: {server_ms}  totalDocsExamined: {docs_examined or 'N/A'}")
                else:
                    print(f"    [explain] raw keys: {list(explain_result.keys())}")
            except Exception as e:
                print(f"    [explain] failed: {e}")

        # --- Use case 3b: first page via count + find (same shape, index-friendly) ---
        t0 = time.perf_counter()
        result_fast = use_case_first_page_count_and_find(
            collection, provider_id,
            page_size=args.page_size,
            service_date_start=date_start,
            service_date_end=date_end,
        )
        elapsed_fast = (time.perf_counter() - t0) * 1000
        print(f"3b. first page (count+find) -> total={result_fast['total']:,}  numPages={result_fast['numPages']}  "
              f"documents on this page={len(result_fast['documents'])}  hasNextCursor={result_fast['nextCursor'] is not None}  (client elapsed: {elapsed_fast:.2f} ms)")

        result = result_fast
        if result["nextCursor"] and result["documents"]:
            # Demonstrate next page via keyset
            t0 = time.perf_counter()
            next_page = use_case_next_page_find(
                collection, provider_id, result["nextCursor"],
                page_size=args.page_size,
                service_date_start=date_start,
                service_date_end=date_end,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            print(f"   next page (keyset) -> {len(next_page):,} docs  ({elapsed:.2f} ms)")

        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
