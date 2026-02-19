"""
Build a single claim document matching sample.json and DESIGN.md.
Reference value sets from DESIGN.md §5.4. No I/O.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timezone
from typing import Any

# Design: recoveryMethod (recoupment / overpayment recovery)
RECOVERY_METHODS = [
    "IMMEDIATE_RECOUPMENT",
    "EXTENDED_REPAYMENT_SCHEDULE",
    "DIRECT_PAYMENT",
    "PENDING",
    "OFFSET",
]

# Design: identifiers.claimSystemCode (claim source / system)
CLAIM_SYSTEM_CODES = [
    "NCPDP_D0",
    "NCPDP_5",
    "INTERNAL",
    "X12_837P",
    "PDE",
]

# Earliest allowed service date (design: all generated dates after year 2000)
MIN_SERVICE_DATE = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _rand_alnum(length: int) -> str:
    """Return a random alphanumeric string of given length."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _rand_amount(min_val: float = 0.0, max_val: float = 9999.99, round_to: int = 2) -> float:
    """Return a random amount rounded to round_to decimal places."""
    return round(random.uniform(min_val, max_val), round_to)


def build_claim(
    *,
    billing_provider_tin: str,
    service_begin_date: datetime,
    service_end_date: datetime,
    claim_system_claim_id: str,
    billing_provider_npi: str | None = None,
    billing_provider_name: str | None = None,
    rendering_provider_name: str | None = None,
    patient_account_number: str | None = None,
    patient_full_name: str | None = None,
    claim_system_code: str | None = None,
    recovery_method: str | None = None,
    overpayment_amount: float | None = None,
    recouped_amount: float | None = None,
    last_updated_ts: datetime | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    """
    Build one claim document (BSON-ready) matching sample.json structure.

    Required: billing_provider_tin, service_begin_date, service_end_date, claim_system_claim_id.
    Optional fields use defaults or random values from design reference sets.
    Dates must be timezone-aware (UTC); service dates should be >= 2000-01-01.
    """
    if claim_system_code is not None and claim_system_code not in CLAIM_SYSTEM_CODES:
        raise ValueError(f"claim_system_code must be one of {CLAIM_SYSTEM_CODES}")
    if recovery_method is not None and recovery_method not in RECOVERY_METHODS:
        raise ValueError(f"recovery_method must be one of {RECOVERY_METHODS}")

    code = claim_system_code if claim_system_code is not None else random.choice(CLAIM_SYSTEM_CODES)
    method = recovery_method if recovery_method is not None else random.choice(RECOVERY_METHODS)

    if overpayment_amount is None:
        overpayment_amount = _rand_amount(10.0, 5000.0)
    if recouped_amount is None:
        recouped_amount = round(
            random.uniform(0, min(overpayment_amount, overpayment_amount * 0.9)), 2
        )
    overpayment_balance = round(overpayment_amount - recouped_amount, 2)

    if last_updated_ts is None:
        # Design: lastUpdatedTs between serviceEndDate and "now"
        end_ts = service_end_date.timestamp()
        now_ts = datetime.now(timezone.utc).timestamp()
        last_updated_ts = datetime.fromtimestamp(
            random.uniform(end_ts, max(now_ts, end_ts + 1)), tz=timezone.utc
        )

    if billing_provider_npi is None:
        billing_provider_npi = "".join(random.choices(string.digits, k=10))
    if billing_provider_name is None:
        billing_provider_name = f"Provider {billing_provider_tin}"
    if rendering_provider_name is None:
        rendering_provider_name = f"Rendering {_rand_alnum(6)}"
    if patient_account_number is None:
        patient_account_number = _rand_alnum(random.randint(8, 12))
    if patient_full_name is None:
        patient_full_name = f"Patient {_rand_alnum(8)}"
    if provider_id is None:
        provider_id = _rand_alnum(8)

    return {
        "renderingProvider": {"providerName": rendering_provider_name},
        "billingProvider": {
            "providerTin": billing_provider_tin,
            "patientAccountNumber": patient_account_number,
            "providerId": provider_id,
            "providerNpi": billing_provider_npi,
            "providerName": billing_provider_name,
        },
        "serviceBeginDate": service_begin_date,
        "serviceEndDate": service_end_date,
        "patientInformation": {"fullName": patient_full_name},
        "identifiers": {
            "claimSystemCode": code,
            "claimSystemClaimId": claim_system_claim_id,
        },
        "lastUpdatedTs": last_updated_ts,
        "processedAmounts": {
            "overpaymentBalance": {"amount": overpayment_balance},
            "overpaymentAmount": {"amount": overpayment_amount},
            "recoupedAmount": {"amount": recouped_amount},
        },
        "recoveryMethod": method,
    }
