"""
Phase 3: Unit tests for claim document builder.
No MongoDB required.
"""

from datetime import datetime, timezone

import pytest

from src.claims.schema import (
    CLAIM_SYSTEM_CODES,
    RECOVERY_METHODS,
    build_claim,
)

# Fixed inputs for deterministic tests
TIN = "12-3456789"
NPI = "1234567890"
SERVICE_BEGIN = datetime(2022, 3, 1, tzinfo=timezone.utc)
SERVICE_END = datetime(2022, 3, 15, tzinfo=timezone.utc)
CLAIM_ID = "claim-001"


def test_build_claim_has_all_sample_json_keys():
    """Generated claim has all top-level keys from sample.json."""
    doc = build_claim(
        billing_provider_tin=TIN,
        service_begin_date=SERVICE_BEGIN,
        service_end_date=SERVICE_END,
        claim_system_claim_id=CLAIM_ID,
        claim_system_code="INTERNAL",
        recovery_method="PENDING",
    )
    required_top = [
        "renderingProvider",
        "billingProvider",
        "serviceBeginDate",
        "serviceEndDate",
        "patientInformation",
        "identifiers",
        "lastUpdatedTs",
        "processedAmounts",
        "recoveryMethod",
    ]
    for key in required_top:
        assert key in doc, f"missing key: {key}"
    assert "providerName" in doc["renderingProvider"]
    assert set(doc["billingProvider"].keys()) == {
        "providerTin",
        "patientAccountNumber",
        "providerId",
        "providerNpi",
        "providerName",
    }
    assert set(doc["identifiers"].keys()) == {"claimSystemCode", "claimSystemClaimId"}
    assert set(doc["processedAmounts"].keys()) == {
        "overpaymentBalance",
        "overpaymentAmount",
        "recoupedAmount",
    }
    assert "amount" in doc["processedAmounts"]["overpaymentBalance"]
    assert "amount" in doc["processedAmounts"]["overpaymentAmount"]
    assert "amount" in doc["processedAmounts"]["recoupedAmount"]
    assert "fullName" in doc["patientInformation"]


def test_build_claim_service_dates_after_2000():
    """When given dates after 2000, document contains those dates."""
    doc = build_claim(
        billing_provider_tin=TIN,
        service_begin_date=SERVICE_BEGIN,
        service_end_date=SERVICE_END,
        claim_system_claim_id=CLAIM_ID,
    )
    assert doc["serviceBeginDate"] == SERVICE_BEGIN
    assert doc["serviceEndDate"] == SERVICE_END
    assert doc["serviceBeginDate"].year >= 2000
    assert doc["serviceEndDate"].year >= 2000


def test_build_claim_recovery_method_from_reference_set():
    """recoveryMethod is one of the design's RECOVERY_METHODS."""
    for _ in range(20):
        doc = build_claim(
            billing_provider_tin=TIN,
            service_begin_date=SERVICE_BEGIN,
            service_end_date=SERVICE_END,
            claim_system_claim_id=CLAIM_ID,
        )
        assert doc["recoveryMethod"] in RECOVERY_METHODS


def test_build_claim_claim_system_code_from_reference_set():
    """identifiers.claimSystemCode is one of the design's CLAIM_SYSTEM_CODES."""
    for _ in range(20):
        doc = build_claim(
            billing_provider_tin=TIN,
            service_begin_date=SERVICE_BEGIN,
            service_end_date=SERVICE_END,
            claim_system_claim_id=CLAIM_ID,
        )
        assert doc["identifiers"]["claimSystemCode"] in CLAIM_SYSTEM_CODES


def test_build_claim_explicit_recovery_method_and_claim_system_code():
    """Explicit recovery_method and claim_system_code are used when valid."""
    doc = build_claim(
        billing_provider_tin=TIN,
        service_begin_date=SERVICE_BEGIN,
        service_end_date=SERVICE_END,
        claim_system_claim_id=CLAIM_ID,
        claim_system_code="NCPDP_D0",
        recovery_method="DIRECT_PAYMENT",
    )
    assert doc["recoveryMethod"] == "DIRECT_PAYMENT"
    assert doc["identifiers"]["claimSystemCode"] == "NCPDP_D0"


def test_build_claim_invalid_recovery_method_raises():
    """Invalid recovery_method raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        build_claim(
            billing_provider_tin=TIN,
            service_begin_date=SERVICE_BEGIN,
            service_end_date=SERVICE_END,
            claim_system_claim_id=CLAIM_ID,
            recovery_method="INVALID",
        )
    assert "recovery_method" in str(exc_info.value) or "RECOVERY" in str(exc_info.value)


def test_build_claim_invalid_claim_system_code_raises():
    """Invalid claim_system_code raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        build_claim(
            billing_provider_tin=TIN,
            service_begin_date=SERVICE_BEGIN,
            service_end_date=SERVICE_END,
            claim_system_claim_id=CLAIM_ID,
            claim_system_code="INVALID",
        )
    assert "claim_system_code" in str(exc_info.value) or "CLAIM_SYSTEM" in str(exc_info.value)


def test_build_claim_amounts_plausible():
    """Explicit amounts are stored; recouped <= overpayment, balance = overpayment - recouped."""
    doc = build_claim(
        billing_provider_tin=TIN,
        service_begin_date=SERVICE_BEGIN,
        service_end_date=SERVICE_END,
        claim_system_claim_id=CLAIM_ID,
        overpayment_amount=1000.0,
        recouped_amount=300.0,
    )
    assert doc["processedAmounts"]["overpaymentAmount"]["amount"] == 1000.0
    assert doc["processedAmounts"]["recoupedAmount"]["amount"] == 300.0
    assert doc["processedAmounts"]["overpaymentBalance"]["amount"] == 700.0


def test_build_claim_billing_provider_tin_used():
    """billing_provider_tin appears as billingProvider.providerTin."""
    doc = build_claim(
        billing_provider_tin=TIN,
        service_begin_date=SERVICE_BEGIN,
        service_end_date=SERVICE_END,
        claim_system_claim_id=CLAIM_ID,
    )
    assert doc["billingProvider"]["providerTin"] == TIN
    assert doc["identifiers"]["claimSystemClaimId"] == CLAIM_ID


def test_build_claim_last_updated_after_service_end_when_provided():
    """lastUpdatedTs can be set explicitly."""
    from datetime import timedelta

    last_ts = SERVICE_END + timedelta(days=1)
    doc = build_claim(
        billing_provider_tin=TIN,
        service_begin_date=SERVICE_BEGIN,
        service_end_date=SERVICE_END,
        claim_system_claim_id=CLAIM_ID,
        last_updated_ts=last_ts,
    )
    assert doc["lastUpdatedTs"] == last_ts
