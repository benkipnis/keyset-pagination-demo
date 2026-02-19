"""
Aggregation pipelines for claims. Query all claims and facet by provider (billingProvider.providerId).
"""

from __future__ import annotations

from typing import Any

# Optional: restrict to a date range (overlap semantics)
# Pass None for no date filter (all claims).
def claims_facet_by_provider_pipeline(
    service_date_start: str | None = None,
    service_date_end: str | None = None,
    include_sample_claim_ids: bool = False,
    sample_size: int = 3,
) -> list[dict[str, Any]]:
    """
    Build an aggregation pipeline that facets all claims by provider (billingProvider.providerId).

    Returns one document per provider with:
      - _id: providerId
      - count: number of claims
      - minServiceBeginDate, maxServiceEndDate (optional)
      - sampleClaimIds (optional): list of a few claim _ids for that provider

    Args:
        service_date_start: Optional "YYYY-MM-DD"; filter to claims with serviceEndDate >= this.
        service_date_end: Optional "YYYY-MM-DD"; filter to claims with serviceBeginDate <= this.
        include_sample_claim_ids:     If True, add sampleClaimIds (first N _ids per provider). Default False to avoid
        pushing large arrays for providers with many claims.
        sample_size: How many _ids to include in sampleClaimIds (only if include_sample_claim_ids).
    """
    stages: list[dict[str, Any]] = []

    # Optional date filter (overlap semantics)
    if service_date_start is not None or service_date_end is not None:
        match: dict[str, Any] = {}
        if service_date_start is not None:
            match["serviceEndDate"] = {"$gte": _parse_date(service_date_start)}
        if service_date_end is not None:
            match["serviceBeginDate"] = {"$lte": _parse_date(service_date_end)}
        if match:
            stages.append({"$match": match})

    # Group by provider
    group: dict[str, Any] = {
        "_id": "$billingProvider.providerId",
        "count": {"$sum": 1},
        "minServiceBeginDate": {"$min": "$serviceBeginDate"},
        "maxServiceEndDate": {"$max": "$serviceEndDate"},
    }
    if include_sample_claim_ids:
        group["sampleClaimIds"] = {"$push": "$_id"}
    stages.append({"$group": group})

    # Keep only first N _ids for sample (if we pushed all)
    if include_sample_claim_ids and sample_size > 0:
        stages.append({
            "$addFields": {
                "sampleClaimIds": {"$slice": ["$sampleClaimIds", sample_size]},
            }
        })

    # Sort by count descending (largest providers first)
    stages.append({"$sort": {"count": -1}})

    # Optional: project a cleaner shape
    stages.append({
        "$project": {
            "_id": 0,
            "providerId": "$_id",
            "count": 1,
            "minServiceBeginDate": 1,
            "maxServiceEndDate": 1,
            "sampleClaimIds": 1,
        }
    })

    return stages


def _parse_date(s: str) -> Any:
    """Return a datetime for YYYY-MM-DD; used in pipeline for $match (BSON date)."""
    from datetime import datetime, timezone
    dt = datetime.strptime(s.strip()[:10], "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


def run_claims_facet_by_provider(
    collection: Any,
    service_date_start: str | None = None,
    service_date_end: str | None = None,
    include_sample_claim_ids: bool = False,
    sample_size: int = 3,
) -> list[dict[str, Any]]:
    """
    Run the facet-by-provider aggregation and return the list of provider summaries.
    """
    pipeline = claims_facet_by_provider_pipeline(
        service_date_start=service_date_start,
        service_date_end=service_date_end,
        include_sample_claim_ids=include_sample_claim_ids,
        sample_size=sample_size,
    )
    return list(collection.aggregate(pipeline))
