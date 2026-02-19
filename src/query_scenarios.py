"""
Test scenarios / use cases for querying claims by providerId with optional service date.
All use the same filter semantics (overlap dates) and keyset-friendly sort.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

# Sort for keyset pagination (matches compound index: providerId, serviceBeginDate, serviceEndDate, _id)
CLAIMS_QUERY_SORT = [("serviceBeginDate", 1), ("serviceEndDate", 1), ("_id", 1)]

# Reverse sort for "last page" via index scan from the end (no skip)
CLAIMS_QUERY_SORT_REVERSE = [("serviceBeginDate", -1), ("serviceEndDate", -1), ("_id", -1)]


def _parse_date(s: str) -> datetime:
    dt = datetime.strptime(s.strip()[:10], "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


def build_filter(
    provider_id: str,
    service_date_start: str | datetime | None = None,
    service_date_end: str | datetime | None = None,
) -> dict[str, Any]:
    """
    Build the query filter for providerId and optional service date range (overlap semantics).
    Dates can be "YYYY-MM-DD" strings or datetime; they are converted to UTC.
    """
    filt: dict[str, Any] = {"billingProvider.providerId": provider_id}
    if service_date_start is not None:
        d = _parse_date(service_date_start) if isinstance(service_date_start, str) else service_date_start
        filt["serviceEndDate"] = {"$gte": d}
    if service_date_end is not None:
        d = _parse_date(service_date_end) if isinstance(service_date_end, str) else service_date_end
        filt["serviceBeginDate"] = {"$lte": d}
    return filt


def build_keyset_filter_after(
    base_filter: dict[str, Any],
    last_service_begin_date: datetime,
    last_service_end_date: datetime,
    last_id: Any,
) -> dict[str, Any]:
    """
    Add keyset condition for "next page": (serviceBeginDate, serviceEndDate, _id) > cursor.
    Use the last document on the current page to get the next page.
    Matches the compound index (providerId, serviceBeginDate, serviceEndDate, _id).
    """
    return {
        "$and": [
            base_filter,
            {
                "$or": [
                    {"serviceBeginDate": {"$gt": last_service_begin_date}},
                    {
                        "serviceBeginDate": last_service_begin_date,
                        "serviceEndDate": {"$gt": last_service_end_date},
                    },
                    {
                        "serviceBeginDate": last_service_begin_date,
                        "serviceEndDate": last_service_end_date,
                        "_id": {"$gt": last_id},
                    },
                ]
            },
        ]
    }


def build_keyset_filter_before(
    base_filter: dict[str, Any],
    first_service_begin_date: datetime,
    first_service_end_date: datetime,
    first_id: Any,
) -> dict[str, Any]:
    """
    Add keyset condition for "previous page": (serviceBeginDate, serviceEndDate, _id) < cursor.
    Use the first document on the current page to get the page before it.
    """
    return {
        "$and": [
            base_filter,
            {
                "$or": [
                    {"serviceBeginDate": {"$lt": first_service_begin_date}},
                    {
                        "serviceBeginDate": first_service_begin_date,
                        "serviceEndDate": {"$lt": first_service_end_date},
                    },
                    {
                        "serviceBeginDate": first_service_begin_date,
                        "serviceEndDate": first_service_end_date,
                        "_id": {"$lt": first_id},
                    },
                ]
            },
        ]
    }


# --- Use case 1: count_documents ---


def use_case_count_documents(
    collection: Any,
    provider_id: str,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
) -> int:
    """
    Run count_documents() with the filter for the given providerId and optional service date range.
    """
    filt = build_filter(provider_id, service_date_start, service_date_end)
    return collection.count_documents(filt)


# --- Use case 2: standard find ---


def use_case_find(
    collection: Any,
    provider_id: str,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Run a standard find() with the filter for the given providerId and optional date range.
    Results are sorted by (serviceBeginDate, _id) for consistency with keyset pagination.
    """
    filt = build_filter(provider_id, service_date_start, service_date_end)
    cursor = collection.find(filt).sort(CLAIMS_QUERY_SORT)
    if limit is not None:
        cursor = cursor.limit(limit)
    return list(cursor)


# --- Use case 3: first page via aggregation (total + page + num pages + keyset cursor) ---


def get_first_page_aggregation_pipeline(
    provider_id: str,
    page_size: int,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
) -> list[dict[str, Any]]:
    """Return the aggregation pipeline used for first-page + total. Used for explain."""
    filt = build_filter(provider_id, service_date_start, service_date_end)
    return [
        {"$match": filt},
        {
            "$facet": {
                "total": [{"$count": "count"}],
                "firstPage": [
                    {"$sort": {"serviceBeginDate": 1, "serviceEndDate": 1, "_id": 1}},
                    {"$limit": page_size + 1},
                ],
            }
        },
    ]


def use_case_first_page_aggregation(
    collection: Any,
    provider_id: str,
    page_size: int = 100,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
) -> dict[str, Any]:
    """
    Run an aggregation that returns the first page of results, total count, number of pages,
    and a nextCursor for keyset-based pagination.

    Uses $facet: one branch counts all matching docs, the other returns the first page
    (match, sort, limit). Page size is optional (default 100).

    Returns:
        {
          "total": int,
          "pageSize": int,
          "numPages": int,
          "documents": [...],
          "nextCursor": { "serviceBeginDate", "serviceEndDate", "_id" } | None  (None if no next page)
        }
    """
    filt = build_filter(provider_id, service_date_start, service_date_end)
    pipeline = get_first_page_aggregation_pipeline(
        provider_id, page_size, service_date_start, service_date_end
    )
    result = list(collection.aggregate(pipeline))
    if not result:
        return {
            "total": 0,
            "pageSize": page_size,
            "numPages": 0,
            "documents": [],
            "nextCursor": None,
        }
    facet = result[0]
    total = (facet["total"][0]["count"]) if facet["total"] else 0
    first_page = facet["firstPage"]
    # We requested page_size + 1 to detect if there is a next page
    has_more = len(first_page) > page_size
    documents = first_page[:page_size]
    last_doc = documents[-1] if documents else None
    next_cursor = None
    if has_more and last_doc is not None:
        next_cursor = {
            "serviceBeginDate": last_doc["serviceBeginDate"],
            "serviceEndDate": last_doc["serviceEndDate"],
            "_id": last_doc["_id"],
        }
    num_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return {
        "total": total,
        "pageSize": page_size,
        "numPages": num_pages,
        "documents": documents,
        "nextCursor": next_cursor,
    }


def use_case_first_page_count_and_find(
    collection: Any,
    provider_id: str,
    page_size: int = 100,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
) -> dict[str, Any]:
    """
    Same return shape as use_case_first_page_aggregation, but using two index-friendly
    operations: count_documents() and find().sort().limit(). Typically faster than the
    $facet aggregation when the provider has many claims, since both ops use the index
    and the find stops after page_size+1 docs.
    """
    filt = build_filter(provider_id, service_date_start, service_date_end)
    total = collection.count_documents(filt)
    first_page = list(
        collection.find(filt).sort(CLAIMS_QUERY_SORT).limit(page_size + 1)
    )
    has_more = len(first_page) > page_size
    documents = first_page[:page_size]
    last_doc = documents[-1] if documents else None
    next_cursor = None
    if has_more and last_doc is not None:
        next_cursor = {
            "serviceBeginDate": last_doc["serviceBeginDate"],
            "serviceEndDate": last_doc["serviceEndDate"],
            "_id": last_doc["_id"],
        }
    num_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return {
        "total": total,
        "pageSize": page_size,
        "numPages": num_pages,
        "documents": documents,
        "nextCursor": next_cursor,
    }


def use_case_next_page_find(
    collection: Any,
    provider_id: str,
    cursor: dict[str, Any],
    page_size: int = 100,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
) -> list[dict[str, Any]]:
    """
    Get the next page of results using keyset pagination (cursor from previous page).
    cursor must have "serviceBeginDate", "serviceEndDate", and "_id".
    """
    base = build_filter(provider_id, service_date_start, service_date_end)
    filt = build_keyset_filter_after(
        base,
        cursor["serviceBeginDate"],
        cursor["serviceEndDate"],
        cursor["_id"],
    )
    return list(
        collection.find(filt)
        .sort(CLAIMS_QUERY_SORT)
        .limit(page_size)
    )


def use_case_next_page_with_cursor(
    collection: Any,
    provider_id: str,
    cursor: dict[str, Any],
    page_size: int = 100,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
) -> dict[str, Any]:
    """
    Get the next page using keyset pagination; returns documents and nextCursor
    (for the following page) in the same shape as first-page responses.
    """
    base = build_filter(provider_id, service_date_start, service_date_end)
    filt = build_keyset_filter_after(
        base,
        cursor["serviceBeginDate"],
        cursor["serviceEndDate"],
        cursor["_id"],
    )
    page = list(
        collection.find(filt).sort(CLAIMS_QUERY_SORT).limit(page_size + 1)
    )
    has_more = len(page) > page_size
    documents = page[:page_size]
    last_doc = documents[-1] if documents else None
    next_cursor = None
    if has_more and last_doc is not None:
        next_cursor = {
            "serviceBeginDate": last_doc["serviceBeginDate"],
            "serviceEndDate": last_doc["serviceEndDate"],
            "_id": last_doc["_id"],
        }
    return {"documents": documents, "nextCursor": next_cursor}


def use_case_last_page_reverse(
    collection: Any,
    provider_id: str,
    page_size: int = 100,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
) -> list[dict[str, Any]]:
    """
    Get the last page of results by scanning the index in reverse, then re-sorting
    in memory. Avoids skip/limit; cost is O(page_size) index read + O(page_size log page_size) sort.
    Returns documents in the same ascending order as normal pagination.
    """
    filt = build_filter(provider_id, service_date_start, service_date_end)
    reverse_page = list(
        collection.find(filt).sort(CLAIMS_QUERY_SORT_REVERSE).limit(page_size)
    )
    # Re-sort to canonical (serviceBeginDate, serviceEndDate, _id) ascending for display
    return sorted(
        reverse_page,
        key=lambda d: (d["serviceBeginDate"], d["serviceEndDate"], d["_id"]),
    )


def use_case_previous_page_with_cursor(
    collection: Any,
    provider_id: str,
    cursor: dict[str, Any],
    page_size: int = 100,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
) -> dict[str, Any]:
    """
    Get the previous page using keyset "before" cursor (first doc of current page).
    Uses reverse sort + limit, then re-sorts to ascending. Returns documents and
    nextCursor (last doc of returned page) so the client can go forward again.
    """
    base = build_filter(provider_id, service_date_start, service_date_end)
    filt = build_keyset_filter_before(
        base,
        cursor["serviceBeginDate"],
        cursor["serviceEndDate"],
        cursor["_id"],
    )
    # Get page_size documents before the cursor (reverse order from index)
    reverse_page = list(
        collection.find(filt).sort(CLAIMS_QUERY_SORT_REVERSE).limit(page_size)
    )
    documents = sorted(
        reverse_page,
        key=lambda d: (d["serviceBeginDate"], d["serviceEndDate"], d["_id"]),
    )
    last_doc = documents[-1] if documents else None
    next_cursor = None
    if last_doc is not None:
        next_cursor = {
            "serviceBeginDate": last_doc["serviceBeginDate"],
            "serviceEndDate": last_doc["serviceEndDate"],
            "_id": last_doc["_id"],
        }
    return {"documents": documents, "nextCursor": next_cursor}
