"""
Tests for query scenarios (filter builder, count, find, first-page aggregation with keyset).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.query_scenarios import (
    CLAIMS_QUERY_SORT,
    build_filter,
    build_keyset_filter_after,
    use_case_count_documents,
    use_case_find,
    use_case_first_page_aggregation,
    use_case_next_page_find,
)


def test_build_filter_provider_only():
    f = build_filter("00-000001")
    assert f == {"billingProvider.providerId": "00-000001"}


def test_build_filter_with_dates():
    f = build_filter("00-000001", "2002-01-01", "2002-12-31")
    assert f["billingProvider.providerId"] == "00-000001"
    assert "serviceEndDate" in f and "$gte" in f["serviceEndDate"]
    assert "serviceBeginDate" in f and "$lte" in f["serviceBeginDate"]


def test_build_keyset_filter_after():
    base = {"billingProvider.providerId": "00-000001"}
    sbd = datetime(2022, 3, 15, tzinfo=timezone.utc)
    sed = datetime(2022, 3, 20, tzinfo=timezone.utc)
    oid = "fake_id"
    f = build_keyset_filter_after(base, sbd, sed, oid)
    assert "$and" in f
    assert base in f["$and"]
    or_clause = [c for c in f["$and"] if "$or" in c][0]
    assert {"serviceBeginDate": {"$gt": sbd}} in or_clause["$or"]
    assert {"serviceBeginDate": sbd, "serviceEndDate": {"$gt": sed}} in or_clause["$or"]
    assert {"serviceBeginDate": sbd, "serviceEndDate": sed, "_id": {"$gt": oid}} in or_clause["$or"]


def test_use_case_count_documents_calls_with_filter():
    coll = MagicMock()
    coll.count_documents.return_value = 42
    out = use_case_count_documents(coll, "00-000001", "2002-01-01", None)
    assert out == 42
    coll.count_documents.assert_called_once()
    call_filter = coll.count_documents.call_args[0][0]
    assert call_filter["billingProvider.providerId"] == "00-000001"
    assert "serviceEndDate" in call_filter


def test_use_case_find_sorts_and_limits():
    coll = MagicMock()
    coll.find.return_value.sort.return_value.limit.return_value.__iter__ = lambda s: iter([])
    use_case_find(coll, "00-000001", limit=10)
    coll.find.assert_called_once()
    coll.find.return_value.sort.assert_called_once_with(CLAIMS_QUERY_SORT)
    coll.find.return_value.sort.return_value.limit.assert_called_once_with(10)


def test_use_case_first_page_aggregation_empty():
    coll = MagicMock()
    coll.aggregate.return_value = [{"total": [], "firstPage": []}]
    out = use_case_first_page_aggregation(coll, "00-000001", page_size=10)
    assert out["total"] == 0
    assert out["numPages"] == 0
    assert out["documents"] == []
    assert out["nextCursor"] is None
    assert out["pageSize"] == 10


def test_use_case_first_page_aggregation_returns_next_cursor_when_more():
    from bson import ObjectId
    oid1 = ObjectId()
    oid2 = ObjectId()
    sbd = datetime(2022, 1, 1, tzinfo=timezone.utc)
    sed = datetime(2022, 1, 5, tzinfo=timezone.utc)
    coll = MagicMock()
    # firstPage has page_size + 1 to indicate there is a next page
    coll.aggregate.return_value = [{
        "total": [{"count": 25}],
        "firstPage": [
            {"_id": oid1, "serviceBeginDate": sbd, "serviceEndDate": sed, "x": 1},
            {"_id": oid2, "serviceBeginDate": sbd, "serviceEndDate": sed, "x": 2},
        ],
    }]
    out = use_case_first_page_aggregation(coll, "00-000001", page_size=1)
    assert out["total"] == 25
    assert out["numPages"] == 25
    assert len(out["documents"]) == 1
    assert out["nextCursor"] is not None
    assert out["nextCursor"]["_id"] == oid1
    assert out["nextCursor"]["serviceBeginDate"] == sbd
    assert out["nextCursor"]["serviceEndDate"] == sed
