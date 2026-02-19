"""
Create and ensure MongoDB indexes for the claims collection.
Idempotent: safe to run multiple times.
"""

from __future__ import annotations

from pymongo.collection import Collection

# Compound index for query by billing provider + optional service date range + keyset pagination.
# Includes serviceEndDate so date-range overlap filter (serviceEndDate >= start, serviceBeginDate <= end)
# can be satisfied from the index without fetching every document.
# Query key: billingProvider.providerId (not providerTin)
CLAIMS_INDEX_KEY = [
    ("billingProvider.providerId", 1),
    ("serviceBeginDate", 1),
    ("serviceEndDate", 1),
    ("_id", 1),
]

CLAIMS_INDEX_NAME = "idx_provider_id_service_begin_end_id"

# Previous index names; dropped when ensuring the new index
_OLD_INDEX_NAMES = [
    "idx_provider_tin_service_begin_id",
    "idx_provider_id_service_begin_id",
]


def ensure_claims_index(collection: Collection) -> str:
    """
    Create the compound index on the claims collection if it does not exist.
    Uses billingProvider.providerId as query key. Drops older index variants if present.
    Idempotent: safe to call repeatedly.

    Returns:
        The name of the index (existing or newly created).
    """
    try:
        existing = list(collection.list_indexes())
        names = [spec.get("name") for spec in existing if spec.get("name")]
        for old in _OLD_INDEX_NAMES:
            if old in names:
                collection.drop_index(old)
    except Exception:
        pass
    return collection.create_index(
        CLAIMS_INDEX_KEY,
        name=CLAIMS_INDEX_NAME,
        background=False,
    )
