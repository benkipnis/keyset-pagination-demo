"""
Phase 4: Unit and integration tests for data generator.
Unit tests need no MongoDB; integration test requires MONGODB_URI and write access.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.data_generator import (
    _parse_date,
    generate_claims_for_provider,
    get_provider_claim_counts,
    run_data_generation,
)

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
CONFIG_EXAMPLE = PROJECT_ROOT / "config" / "config.example.yaml"


# --- Unit tests ---


def test_parse_date():
    """_parse_date parses YYYY-MM-DD to UTC midnight."""
    dt = _parse_date("2000-01-01")
    assert dt.year == 2000 and dt.month == 1 and dt.day == 1
    assert dt.tzinfo is timezone.utc
    dt2 = _parse_date("2003-12-31")
    assert dt2.year == 2003 and dt2.month == 12 and dt2.day == 31


def test_get_provider_claim_counts_from_example_config():
    """Tier config yields correct number of providers and total ~3M."""
    from src.config_loader import load_config

    config = load_config(CONFIG_EXAMPLE, require_uri=False)
    counts = get_provider_claim_counts(config)
    total = sum(c for _, c in counts)
    assert abs(total - 3_000_000) < 100_000
    # Each tier should have at least one provider with that tier's count
    tier_sizes = {1000, 5000, 10000, 50000, 100000, 500000, 1000000}
    counts_per_provider = {c for _, c in counts}
    for size in tier_sizes:
        assert size in counts_per_provider, f"Expected at least one provider with {size} claims"


def test_get_provider_claim_counts_provider_id_unique():
    """Each provider has a unique providerId."""
    config = {
        "data_generation": {
            "tiers": [
                {"claims_per_provider": 10, "num_providers": 3},
                {"claims_per_provider": 5, "num_providers": 2},
            ]
        }
    }
    counts = get_provider_claim_counts(config)
    ids = [pid for pid, _ in counts]
    assert len(ids) == len(set(ids))
    assert len(counts) == 5
    assert sum(c for _, c in counts) == 40  # 3*10 + 2*5


def test_generate_claims_for_provider_count_and_dates():
    """Generated claims have correct count and serviceBeginDate >= 2000."""
    date_start = datetime(2002, 1, 1, tzinfo=timezone.utc)
    date_end = datetime(2002, 12, 31, tzinfo=timezone.utc)
    docs = generate_claims_for_provider(
        provider_id="00-000001",
        claim_count=20,
        date_start=date_start,
        date_end=date_end,
    )
    assert len(docs) == 20
    for doc in docs:
        assert doc["serviceBeginDate"] >= datetime(2000, 1, 1, tzinfo=timezone.utc)
        assert doc["serviceEndDate"] >= datetime(2000, 1, 1, tzinfo=timezone.utc)
        assert doc["billingProvider"]["providerId"] == "00-000001"


def test_generate_claims_for_provider_unique_claim_ids():
    """Claim IDs are unique when using offset."""
    date_start = datetime(2002, 1, 1, tzinfo=timezone.utc)
    date_end = datetime(2002, 1, 2, tzinfo=timezone.utc)
    docs1 = generate_claims_for_provider(
        provider_id="00-000001",
        claim_count=5,
        date_start=date_start,
        date_end=date_end,
        offset=0,
    )
    docs2 = generate_claims_for_provider(
        provider_id="00-000001",
        claim_count=5,
        date_start=date_start,
        date_end=date_end,
        offset=5,
    )
    ids1 = {d["identifiers"]["claimSystemClaimId"] for d in docs1}
    ids2 = {d["identifiers"]["claimSystemClaimId"] for d in docs2}
    assert ids1.isdisjoint(ids2)
    assert len(ids1) == 5 and len(ids2) == 5


# --- Integration test ---


@pytest.mark.integration
def test_run_data_generation_small_insert():
    """Run generator with tiny config; verify collection count and one provider count."""
    import os
    from src.config_loader import load_config, MONGODB_URI_ENV

    if not os.environ.get(MONGODB_URI_ENV):
        pytest.skip("MONGODB_URI not set")

    base = load_config(CONFIG_EXAMPLE, require_uri=True)
    # Small config: same DB as example, test collection; 2 providers, 25 claims each = 50 total
    small_config = {
        **base,
        "mongodb": {**base["mongodb"], "collection": "_data_gen_test"},
        "data_generation": {
            "date_start": "2002-01-01",
            "date_end": "2002-01-31",
            "tiers": [{"claims_per_provider": 25, "num_providers": 2}],
            "batch_size": 10,
        },
    }

    from src.db import get_client, get_collection

    client = get_client()
    try:
        collection = get_collection(client, small_config)
        # Clear test collection so count is predictable
        collection.delete_many({})
        inserted = run_data_generation(collection, small_config)
        assert inserted == 50
        assert collection.count_documents({}) == 50
        # One provider ID from our tier is 00-000000 or 00-000001
        count0 = collection.count_documents({"billingProvider.providerId": "00-000000"})
        count1 = collection.count_documents({"billingProvider.providerId": "00-000001"})
        assert count0 == 25 and count1 == 25
        # Cleanup
        collection.delete_many({})
    finally:
        client.close()
