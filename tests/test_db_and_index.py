"""
Phase 2: Tests for MongoDB connection and index creation.
Unit tests use mocks; integration test requires MONGODB_URI in .env and skips if unset.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.indexes import CLAIMS_INDEX_KEY, CLAIMS_INDEX_NAME, ensure_claims_index

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
CONFIG_EXAMPLE = PROJECT_ROOT / "config" / "config.example.yaml"


def test_ensure_claims_index_calls_create_index_with_correct_spec():
    """ensure_claims_index calls collection.create_index with the design compound key."""
    mock_coll = MagicMock()
    mock_coll.create_index.return_value = CLAIMS_INDEX_NAME

    result = ensure_claims_index(mock_coll)

    mock_coll.create_index.assert_called_once()
    call_kw = mock_coll.create_index.call_args
    assert call_kw[0][0] == CLAIMS_INDEX_KEY
    assert call_kw[1].get("name") == CLAIMS_INDEX_NAME
    assert result == CLAIMS_INDEX_NAME


def test_claims_index_key_matches_design():
    """Index key uses providerId, serviceBeginDate, serviceEndDate, _id."""
    assert len(CLAIMS_INDEX_KEY) == 4
    assert CLAIMS_INDEX_KEY[0] == ("billingProvider.providerId", 1)
    assert CLAIMS_INDEX_KEY[1] == ("serviceBeginDate", 1)
    assert CLAIMS_INDEX_KEY[2] == ("serviceEndDate", 1)
    assert CLAIMS_INDEX_KEY[3] == ("_id", 1)


@pytest.mark.integration
def test_connect_create_index_insert_find_requires_uri():
    """Integration: connect, get collection, create index, insert one doc, find it, delete. Skips if no URI or insufficient Atlas permissions."""
    import os
    from pymongo.errors import OperationFailure

    from src.config_loader import load_config, MONGODB_URI_ENV

    if not os.environ.get(MONGODB_URI_ENV):
        pytest.skip("MONGODB_URI not set; skipping integration test")

    config = load_config(CONFIG_EXAMPLE, require_uri=True)
    # Use same database as config but a dedicated collection
    test_config = {
        **config,
        "mongodb": {
            **config["mongodb"],
            "collection": "_integration_test_claims",
        },
    }

    from src.db import get_client, get_collection
    from src.indexes import ensure_claims_index

    client = get_client()
    try:
        collection = get_collection(client, test_config)
        try:
            name = ensure_claims_index(collection)
        except OperationFailure as e:
            if e.details and e.details.get("code") == 13:
                pytest.skip(
                    "Atlas user not authorized to create indexes; grant createIndex on the database or skip with -m 'not integration'"
                )
            raise
        assert name == CLAIMS_INDEX_NAME

        # Insert one minimal doc and find it
        doc = {"billingProvider": {"providerId": "99-9999999"}, "serviceBeginDate": None, "_test": True}
        ins = collection.insert_one(doc)
        assert ins.inserted_id is not None
        found = collection.find_one({"_id": ins.inserted_id})
        assert found is not None
        assert found.get("_test") is True
        # Cleanup
        collection.delete_one({"_id": ins.inserted_id})
    finally:
        client.close()
