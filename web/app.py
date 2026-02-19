"""
Sample front-end backend: Flask API for keyset-paginated claims by providerId.
Uses approach 3b (count + find) with separate timings for count, first page, and next page.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from flask import Flask, jsonify, request, send_from_directory

# Project root and path setup for imports
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
import sys
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from src.config_loader import load_config
from src.db import get_client, get_collection as db_get_collection
from src.query_scenarios import (
    build_filter,
    build_keyset_filter_after,
    build_keyset_filter_before,
    CLAIMS_QUERY_SORT,
    CLAIMS_QUERY_SORT_REVERSE,
    use_case_count_documents,
    use_case_last_page_reverse,
    use_case_next_page_with_cursor,
    use_case_previous_page_with_cursor,
)


def _serialize_value(v):
    """Recursively make a value JSON-serializable (ObjectId, datetime)."""
    if hasattr(v, "isoformat"):  # datetime
        return v.isoformat()
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, dict):
        return {k: _serialize_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_serialize_value(x) for x in v]
    return v


def _serialize_doc(doc: dict) -> dict:
    """Make a claim document JSON-serializable (ObjectId and datetime)."""
    out = dict(doc)
    if "_id" in out:
        out["_id"] = str(out["_id"])
    for key in ("serviceBeginDate", "serviceEndDate", "lastUpdatedTs"):
        if key in out and out[key] is not None:
            v = out[key]
            if hasattr(v, "isoformat"):
                out[key] = v.isoformat()
    return out


def _parse_cursor(cursor: dict) -> dict:
    """Parse cursor from JSON: serviceBeginDate, serviceEndDate (ISO str), _id (hex str) -> BSON types."""
    from datetime import datetime
    if not cursor or "serviceBeginDate" not in cursor or "serviceEndDate" not in cursor or "_id" not in cursor:
        raise ValueError("cursor must have serviceBeginDate, serviceEndDate, and _id")
    def parse_dt(v):
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v
    return {
        "serviceBeginDate": parse_dt(cursor["serviceBeginDate"]),
        "serviceEndDate": parse_dt(cursor["serviceEndDate"]),
        "_id": ObjectId(cursor["_id"]),
    }


def create_app():
    app = Flask(__name__, static_folder="static")
    config_path = _PROJECT_ROOT / "config" / "config.yaml"
    if not config_path.exists():
        config_path = _PROJECT_ROOT / "config" / "config.example.yaml"
    app.config["CONFIG"] = load_config(str(config_path), require_uri=True)
    app.config["CLIENT"] = None

    def get_collection():
        if app.config["CLIENT"] is None:
            app.config["CLIENT"] = get_client()
        return db_get_collection(app.config["CLIENT"], app.config["CONFIG"])

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/api/page", methods=["POST"])
    def api_page():
        body = request.get_json(force=True, silent=True) or {}
        provider_id = (body.get("provider_id") or "").strip()
        if not provider_id:
            return jsonify({"error": "provider_id is required"}), 400
        try:
            page_size = int(body.get("page_size", 100))
        except (TypeError, ValueError):
            page_size = 100
        page_size = max(1, min(1000, page_size))
        date_start = body.get("date_start") or None
        date_end = body.get("date_end") or None
        cursor = body.get("cursor")
        before_cursor = body.get("before_cursor")
        include_count = bool(body.get("include_count"))
        last_page = bool(body.get("last_page"))

        coll = get_collection()

        if cursor is None and before_cursor:
            # Previous page (keyset "before"): first doc of current page -> page before it
            try:
                before_parsed = _parse_cursor(before_cursor)
            except Exception as e:
                return jsonify({"error": f"Invalid before_cursor: {e}"}), 400
            t0 = time.perf_counter()
            result = use_case_previous_page_with_cursor(
                coll, provider_id, before_parsed, page_size, date_start, date_end
            )
            prev_page_ms = (time.perf_counter() - t0) * 1000
            prev_page_ms_r = round(prev_page_ms, 2)
            next_cursor = result["nextCursor"]
            if next_cursor is not None:
                next_cursor = {
                    "serviceBeginDate": next_cursor["serviceBeginDate"].isoformat(),
                    "serviceEndDate": next_cursor["serviceEndDate"].isoformat(),
                    "_id": str(next_cursor["_id"]),
                }
            filt = build_filter(provider_id, date_start, date_end)
            keyset_before = build_keyset_filter_before(
                filt,
                before_parsed["serviceBeginDate"],
                before_parsed["serviceEndDate"],
                before_parsed["_id"],
            )
            sort_rev_json = [list(pair) for pair in CLAIMS_QUERY_SORT_REVERSE]
            return jsonify({
                "documents": [_serialize_doc(d) for d in result["documents"]],
                "nextCursor": next_cursor,
                "timings": {"prev_page_ms": prev_page_ms_r},
                "operations": [{
                    "op": "find (prev page, reverse sort) + re-sort",
                    "ms": prev_page_ms_r,
                    "request": {
                        "method": "find",
                        "filter": _serialize_value(keyset_before),
                        "sort": sort_rev_json,
                        "limit": page_size,
                    },
                }],
            })
        if cursor is None and last_page:
            # Last page: reverse index scan + in-memory re-sort (no skip). Count only when include_count.
            operations = []
            timings = {}
            total = None
            num_pages = None
            filt = build_filter(provider_id, date_start, date_end)

            if include_count:
                t0 = time.perf_counter()
                total = use_case_count_documents(coll, provider_id, date_start, date_end)
                count_ms = (time.perf_counter() - t0) * 1000
                count_ms_r = round(count_ms, 2)
                timings["count_ms"] = count_ms_r
                num_pages = (total + page_size - 1) // page_size if page_size else 0
                operations.append({
                    "op": "count_documents",
                    "ms": count_ms_r,
                    "request": {"method": "count_documents", "filter": _serialize_value(filt)},
                })

            t0 = time.perf_counter()
            documents = use_case_last_page_reverse(
                coll, provider_id, page_size, date_start, date_end
            )
            last_page_ms = (time.perf_counter() - t0) * 1000
            last_page_ms_r = round(last_page_ms, 2)
            timings["last_page_ms"] = last_page_ms_r
            sort_rev_json = [list(pair) for pair in CLAIMS_QUERY_SORT_REVERSE]
            operations.append({
                "op": "find (last page, reverse sort) + re-sort",
                "ms": last_page_ms_r,
                "request": {
                    "method": "find",
                    "filter": _serialize_value(filt),
                    "sort": sort_rev_json,
                    "limit": page_size,
                },
            })

            out = {
                "documents": [_serialize_doc(d) for d in documents],
                "nextCursor": None,
                "timings": timings,
                "operations": operations,
            }
            if total is not None:
                out["total"] = total
                out["numPages"] = num_pages
            return jsonify(out)
        if cursor is None:
            # First page: time count and first-page find separately
            t0 = time.perf_counter()
            total = use_case_count_documents(coll, provider_id, date_start, date_end)
            count_ms = (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            filt = build_filter(provider_id, date_start, date_end)
            first_page = list(
                coll.find(filt).sort(CLAIMS_QUERY_SORT).limit(page_size + 1)
            )
            first_page_ms = (time.perf_counter() - t0) * 1000

            has_more = len(first_page) > page_size
            documents = first_page[:page_size]
            last_doc = documents[-1] if documents else None
            next_cursor = None
            if has_more and last_doc is not None:
                next_cursor = {
                    "serviceBeginDate": last_doc["serviceBeginDate"].isoformat(),
                    "serviceEndDate": last_doc["serviceEndDate"].isoformat(),
                    "_id": str(last_doc["_id"]),
                }
            num_pages = (total + page_size - 1) // page_size if page_size else 0

            count_ms_r = round(count_ms, 2)
            first_page_ms_r = round(first_page_ms, 2)
            sort_json = [list(pair) for pair in CLAIMS_QUERY_SORT]
            filter_json = _serialize_value(filt)
            return jsonify({
                "total": total,
                "pageSize": page_size,
                "numPages": num_pages,
                "documents": [_serialize_doc(d) for d in documents],
                "nextCursor": next_cursor,
                "timings": {"count_ms": count_ms_r, "first_page_ms": first_page_ms_r},
                "operations": [
                    {
                        "op": "count_documents",
                        "ms": count_ms_r,
                        "request": {
                            "method": "count_documents",
                            "filter": filter_json,
                        },
                    },
                    {
                        "op": "find (first page)",
                        "ms": first_page_ms_r,
                        "request": {
                            "method": "find",
                            "filter": filter_json,
                            "sort": sort_json,
                            "limit": page_size + 1,
                        },
                    },
                ],
            })
        else:
            # Next page (keyset); optionally run count_documents when include_count is true
            try:
                cursor_parsed = _parse_cursor(cursor)
            except Exception as e:
                return jsonify({"error": f"Invalid cursor: {e}"}), 400

            operations = []
            timings = {}
            total = None
            num_pages = None

            if include_count:
                t0 = time.perf_counter()
                total = use_case_count_documents(coll, provider_id, date_start, date_end)
                count_ms = (time.perf_counter() - t0) * 1000
                count_ms_r = round(count_ms, 2)
                timings["count_ms"] = count_ms_r
                filt = build_filter(provider_id, date_start, date_end)
                operations.append({
                    "op": "count_documents",
                    "ms": count_ms_r,
                    "request": {"method": "count_documents", "filter": _serialize_value(filt)},
                })

            t0 = time.perf_counter()
            result = use_case_next_page_with_cursor(
                coll, provider_id, cursor_parsed, page_size, date_start, date_end
            )
            next_page_ms = (time.perf_counter() - t0) * 1000

            next_cursor = result["nextCursor"]
            if next_cursor is not None:
                next_cursor = {
                    "serviceBeginDate": next_cursor["serviceBeginDate"].isoformat(),
                    "serviceEndDate": next_cursor["serviceEndDate"].isoformat(),
                    "_id": str(next_cursor["_id"]),
                }

            next_page_ms_r = round(next_page_ms, 2)
            timings["next_page_ms"] = next_page_ms_r
            keyset_filter = build_keyset_filter_after(
                build_filter(provider_id, date_start, date_end),
                cursor_parsed["serviceBeginDate"],
                cursor_parsed["serviceEndDate"],
                cursor_parsed["_id"],
            )
            sort_json = [list(pair) for pair in CLAIMS_QUERY_SORT]
            operations.append({
                "op": "find (keyset)",
                "ms": next_page_ms_r,
                "request": {
                    "method": "find",
                    "filter": _serialize_value(keyset_filter),
                    "sort": sort_json,
                    "limit": page_size + 1,
                },
            })

            out = {
                "documents": [_serialize_doc(d) for d in result["documents"]],
                "nextCursor": next_cursor,
                "timings": timings,
                "operations": operations,
            }
            if total is not None:
                out["total"] = total
                out["numPages"] = (total + page_size - 1) // page_size if page_size else 0
            return jsonify(out)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
