"""
Generate claims from tier config and write to MongoDB in batches.
Uses config data_generation.* and claims.build_claim. All service dates after 2000.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

from src.claims.schema import build_claim


def _parse_date(s: str) -> datetime:
    """Parse YYYY-MM-DD string to UTC datetime at midnight."""
    dt = datetime.strptime(s.strip()[:10], "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


def get_provider_claim_counts(config: dict[str, Any]) -> list[tuple[str, int]]:
    """
    From data_generation.tiers build a list of (provider_id, claim_count) per provider.
    Each provider gets a unique providerId (used for querying and tier counts).
    Format: XX-NNNNNN (tier 2 digits + provider 6 digits, e.g. 01-000001).
    """
    dg = config.get("data_generation") or {}
    tiers = dg.get("tiers") or []
    result: list[tuple[str, int]] = []
    for tier_idx, tier in enumerate(tiers):
        count_per = tier.get("claims_per_provider") or 0
        num_providers = tier.get("num_providers") or 0
        for prov_idx in range(num_providers):
            provider_id = f"{tier_idx:02d}-{prov_idx:06d}"
            result.append((provider_id, count_per))
    return result


def _random_service_dates(
    date_start: datetime,
    date_end: datetime,
) -> tuple[datetime, datetime]:
    """Pick random service begin/end in [date_start, date_end]; begin <= end; all >= 2000."""
    delta_days = (date_end - date_start).days
    if delta_days < 0:
        delta_days = 0
    start_offset = random.randint(0, delta_days) if delta_days else 0
    service_begin = date_start + timedelta(days=start_offset)
    span_days = min(14, delta_days - start_offset) if delta_days else 0
    end_offset = random.randint(0, span_days) if span_days >= 0 else 0
    service_end = service_begin + timedelta(days=end_offset)
    if service_end < service_begin:
        service_end = service_begin
    return service_begin, service_end


def generate_claims_for_provider(
    *,
    provider_id: str,
    claim_count: int,
    date_start: datetime,
    date_end: datetime,
    claim_id_prefix: str = "gen",
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    Generate claim_count claim documents for one provider (e.g. a batch slice).
    provider_id is set as billingProvider.providerId (and providerTin) for querying.
    offset is used for unique claim_system_claim_id when generating in chunks.
    Service dates are random in [date_start, date_end].
    """
    docs: list[dict[str, Any]] = []
    for i in range(claim_count):
        service_begin, service_end = _random_service_dates(date_start, date_end)
        claim_id = f"{claim_id_prefix}-{provider_id}-{offset + i}"
        doc = build_claim(
            billing_provider_tin=provider_id,
            service_begin_date=service_begin,
            service_end_date=service_end,
            claim_system_claim_id=claim_id,
            provider_id=provider_id,
        )
        docs.append(doc)
    return docs


def run_data_generation(
    collection: Any,
    config: dict[str, Any],
    progress_callback: Callable[[int, int], None] | None = None,
) -> int:
    """
    Generate claims from config and insert into collection in batches.
    Uses data_generation.tiers, date_start, date_end, batch_size.
    Returns total number of documents inserted.
    """
    dg = config.get("data_generation") or {}
    date_start_s = dg.get("date_start") or "2000-01-01"
    date_end_s = dg.get("date_end") or "2003-12-31"
    batch_size = dg.get("batch_size") or 10_000
    date_start = _parse_date(date_start_s)
    date_end = _parse_date(date_end_s)

    provider_counts = get_provider_claim_counts(config)
    total_expected = sum(c for _, c in provider_counts)
    total_inserted = 0

    for provider_id, claim_count in provider_counts:
        offset = 0
        while offset < claim_count:
            chunk = min(batch_size, claim_count - offset)
            docs = generate_claims_for_provider(
                provider_id=provider_id,
                claim_count=chunk,
                date_start=date_start,
                date_end=date_end,
                offset=offset,
            )
            collection.insert_many(docs)
            total_inserted += len(docs)
            if progress_callback:
                progress_callback(total_inserted, total_expected)
            offset += chunk

    return total_inserted
