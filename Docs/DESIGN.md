# Design Document: PBM Integration Services – Claims Query Demo

**Version:** 1.0  
**Last Updated:** February 2025  
**Target:** MongoDB Atlas, Python

---

## 1. Introduction & Goals

### 1.1 Purpose

This document describes the design for a customer-facing demonstration of MongoDB’s ability to query and return large volumes of claim documents quickly. The scenario is an integration between a **healthcare provider** and a **pharmacy benefits manager (PBM)**. Claims are stored as individual documents; the primary access pattern is querying by **billing provider** (identified by TIN) with an **optional service date range**.

### 1.2 Success Criteria

- **Performance:** Queries are as fast as possible for the chosen workload and indexes.
- **Cost:** Design avoids unnecessary hardware; indexing and query patterns are optimized for efficiency.
- **Deliverables:** Sample data generator, query API with keyset pagination and total count, performance test script with a summary report.

### 1.3 Out of Scope

- Full PBM adjudication logic, eligibility, or clinical rules.
- Authentication/authorization (demo-only).
- Production security hardening or audit logging.

---

## 2. Schema & Data Model

### 2.1 Document Structure

Claims are stored as one document per claim. The structure is derived from `Docs/sample.json` with inferred types and semantics.

| Field | Type | Description |
|-------|------|-------------|
| `renderingProvider.providerName` | string | Name of the provider who rendered the service. |
| `billingProvider.providerTin` | string | Billing provider Tax Identification Number (TIN). |
| `billingProvider.patientAccountNumber` | string | Provider’s internal account number for the patient. |
| `billingProvider.providerId` | string | **Payer-assigned provider identifier. Primary query key.** |
| `billingProvider.providerNpi` | string | National Provider Identifier (10 digits). |
| `billingProvider.providerName` | string | Billing provider legal or doing-business-as name. |
| `serviceBeginDate` | date | Start of service (date or datetime at midnight UTC). |
| `serviceEndDate` | date | End of service (date or datetime at midnight UTC). |
| `patientInformation.fullName` | string | Patient full name (for demo, can be synthetic). |
| `identifiers.claimSystemCode` | string | System/source of the claim (e.g. NCPDP, internal). See §6. |
| `identifiers.claimSystemClaimId` | string | Unique claim ID within that system. |
| `lastUpdatedTs` | datetime | Last update timestamp (e.g. for recoupment or adjustment). |
| `processedAmounts.overpaymentBalance.amount` | decimal | Current overpayment balance (e.g. in dollars). |
| `processedAmounts.overpaymentAmount.amount` | decimal | Original overpayment amount. |
| `processedAmounts.recoupedAmount.amount` | decimal | Amount recouped to date. |
| `recoveryMethod` | string | How recovery is being applied. See §6. |


### 2.2 Data Types (Storage)

- **Dates:** `serviceBeginDate`, `serviceEndDate` → BSON Date (UTC).
- **Timestamps:** `lastUpdatedTs` → BSON Date (UTC).
- **Amounts:** Store as **BSON Decimal128** (or, if preferred for simplicity, double) for currency; application layer can format.
- **Strings:** All identifiers and names as string; NPI and TIN can be zero-padded strings for consistent length and indexing.

### 2.3 Unique Identity

- **Application-level:** `identifiers.claimSystemCode` + `identifiers.claimSystemClaimId` should be unique per claim.
- **MongoDB:** Rely on `_id` (ObjectId) for keyset pagination and uniqueness. Optionally add a unique compound index on `(identifiers.claimSystemCode, identifiers.claimSystemClaimId)` if duplicate prevention is required during load.

---

## 3. Indexing Strategy

### 3.1 Primary Query Pattern

- Filter by **billing provider:** `billingProvider.providerId`.
- Optional filter by **service date range:** `serviceBeginDate` and/or `serviceEndDate` (e.g. claims that overlap or fall within a range).
- Sort: **deterministic and stable** for keyset pagination (e.g. `_id` or compound of date + `_id`).
- Need: **total count** for the current filter and **paginated result set**.

### 3.2 Recommended Indexes

**Compound index for “by provider + optional date range” and sort**

- **Index:** `{ "billingProvider.providerId": 1, "serviceBeginDate": 1, "serviceEndDate": 1, "_id": 1 }` (name: `idx_provider_id_service_begin_end_id`).
- **Rationale:**
  - Equality on `providerId` narrows to one provider.
  - `serviceBeginDate` and `serviceEndDate` support overlap filters from the index without extra fetches.
  - `_id` gives a unique, stable sort; keyset cursor is `(serviceBeginDate, serviceEndDate, _id)`.

### 3.3 Date Range Semantics

- **“Claims in date range”** can be defined as: claim’s service interval overlaps the requested range.  
  Example: request `[start, end]` →  
  `serviceBeginDate <= end AND serviceEndDate >= start`.
- Index order `(providerId, serviceBeginDate, serviceEndDate, _id)` supports:
  - Filter: `providerId == X`, overlap on dates (both predicates from index).
  - Sort: `serviceBeginDate`, `serviceEndDate`, `_id` for keyset pagination.

---

## 4. Query Design

### 4.1 Parameters

- **Required:** `billingProviderId` (value of `billingProvider.providerId`).
- **Optional:** `serviceDateStart`, `serviceDateEnd` (inclusive or as-overlap; see §3.3).
- **Pagination:** keyset (cursor-based) using the last seen document’s sort key + `_id`.

### 4.2 Total Count: count_documents vs $facet

**Recommendation: use a separate `count_documents()` (or equivalent count) for the total.**

- **count_documents:** One round-trip; uses the same index; returns a single number. For “count all matching,” this is simple and fast.
- **$facet with count + data:** One round-trip but the aggregation pipeline is heavier (two sub-pipelines: one for count, one for sorted + limited docs). For large result sets, the count branch still scans all matching documents; it does not avoid work and can be slower than a dedicated count that uses the index and returns only the count.
- **When $facet might help:** If the client always needs both “first page” and “total count” in one call and the typical result set is small, a single aggregation with `$facet` could be acceptable. For large provider volumes (e.g. 100K–1M claims per provider), a separate count is expected to be more predictable and often faster.

**Implementation:** Run `count_documents(filter)` in parallel with the first page query, or run it in a separate call. Report both “time to first page” and “time to count” in the performance script so the customer can compare.

### 4.3 Keyset (Cursor-Based) Pagination

- **Sort:** Use a deterministic order, e.g. `serviceBeginDate` ascending, then `_id` ascending. So sort: `[("serviceBeginDate", 1), ("_id", 1)]`.
- **Next page (forward):**  
  - Cursor = last document’s `(serviceBeginDate, _id)`.  
  - Filter: same provider (and date range) **and** `(serviceBeginDate, _id) > (last_serviceBeginDate, last_id)` in sort order.  
  - In MongoDB:  
    `$or` with two conditions:  
    - `serviceBeginDate > last_serviceBeginDate`  
    - `serviceBeginDate == last_serviceBeginDate and _id > last_id`  
  - Or use a compound value (e.g. array) if the driver supports it; otherwise two conditions as above.
- **Previous page (backward):** Same idea with `(serviceBeginDate, _id) < (first_serviceBeginDate, first_id)` and sort reversed for the previous page.

This avoids skip/offset and keeps execution time stable as the user moves through pages.

### 4.4 Query Shape (Pseudocode)

```text
filter = { "billingProvider.providerId": billingProviderId }
if serviceDateStart is not None:
    filter["serviceEndDate"] = { "$gte": serviceDateStart }
if serviceDateEnd is not None:
    filter["serviceBeginDate"] = { "$lte": serviceDateEnd }

# Count (separate call)
total = collection.count_documents(filter)

# Page (keyset)
sort = [("serviceBeginDate", 1), ("_id", 1)]
if next_cursor:
    filter["$or"] = [
        {"serviceBeginDate": {"$gt": next_cursor.serviceBeginDate}},
        {"serviceBeginDate": next_cursor.serviceBeginDate, "_id": {"$gt": next_cursor._id}}
    ]
docs = collection.find(filter).sort(sort).limit(page_size)
# Return docs + total + cursor for next/prev
```

---

## 5. Data Generation

### 5.1 Total Volume and Tier Rules

- **Target total:** ~3,000,000 claims.
- **Tiers (claims per provider):** At least one provider in each tier: **1K, 5K, 10K, 50K, 100K, 500K, 1M**.
- **Minimum from “one per tier”:** 1,000 + 5,000 + 10,000 + 50,000 + 100,000 + 500,000 + 1,000,000 = **1,666,000** claims.
- **Remainder:** ~1,334,000 claims, distributed with **more providers at lower tiers** (e.g. many providers at 1K/5K/10K, fewer at 500K).

### 5.2 Distribution Strategy

- **Ramp by tier:** Number of providers in each tier increases as tier size decreases (e.g. 1–2 extra at 500K; many at 1K).
- **Example distribution (conceptual):**

| Tier (claims/provider) | Min providers | Extra providers | Total providers | Total claims |
|------------------------|---------------|-----------------|-----------------|-------------|
| 1,000,000              | 1             | 0               | 1               | 1,000,000   |
| 500,000                | 1             | 1–2             | 2               | 1,000,000   |
| 100,000                | 1             | 2–4             | 4               | 400,000     |
| 50,000                 | 1             | 4–8             | 8               | 400,000     |
| 10,000                 | 1             | 10–20           | 20              | 200,000     |
| 5,000                  | 1             | 20–40           | 40              | 200,000     |
| 1,000                  | 1             | 100–200         | 150             | 150,000     |

- Exact counts should be tuned so the **total is ~3M** and overlap (same provider, overlapping service dates) is intentional for realism and stress-testing.

### 5.3 Overlap and Realism

- **Providers:** Reuse a fixed set of TINs (and NPIs/names) per tier; multiple claims per provider.
- **Dates:** Spread `serviceBeginDate` / `serviceEndDate` over a defined window (e.g. 2–3 years) so that:
  - All generated service dates are **after the year 2000** (e.g. `serviceBeginDate` and `serviceEndDate` ≥ 2000-01-01).
  - Same provider has many dates.
  - Different providers have overlapping date ranges for fair performance tests.
- **Identifiers:** `claimSystemClaimId` (and optionally `claimSystemCode`) must be unique per claim; can be synthetic (e.g. UUID or counter-based).

### 5.4 Reference Value Sets (Public-Based)

Values below are based on common healthcare/PBM and Medicare terminology. Use these for `recoveryMethod`, `identifiers.claimSystemCode`, and (if needed) adjustment-style concepts.

**recoveryMethod (recoupment / overpayment recovery):**

- `IMMEDIATE_RECOUPMENT` – Recovery by offsetting future payments.
- `EXTENDED_REPAYMENT_SCHEDULE` – Repayment over time (e.g. ERS).
- `DIRECT_PAYMENT` – Provider pays back directly (e.g. check/EFT).
- `PENDING` – Identified but not yet applied.
- `OFFSET` – Same as immediate recoupment in some contexts; can be used as alias or separate.

**identifiers.claimSystemCode (claim source / system):**

- `NCPDP_D0` – NCPDP D.0 (pharmacy).
- `NCPDP_5` – NCPDP Version 5.
- `INTERNAL` – Internal/system claim.
- `X12_837P` – Professional (e.g. physician) claim.
- `PDE` – Prescription Drug Event (Part D).

**Amounts and identifiers:**

- Generate `overpaymentBalance`, `overpaymentAmount`, `recoupedAmount` with plausible decimal values (e.g. positive, with recouped ≤ overpayment).
- `patientAccountNumber`: alphanumeric (e.g. 8–12 chars).
- `providerId`, `providerNpi`: 10-digit NPI; TIN as 9-digit (with or without hyphen).
- `lastUpdatedTs`: between `serviceEndDate` and “now.”

---

## 6. Performance Testing

### 6.1 Objectives

- Measure query latency and count latency for “by provider” and “by provider + date range.”
- Compare count via `count_documents` vs (optional) `$facet` in one run.
- Produce a **script** that runs the tests and a **report/readout** at the end.
- No fixed SLA; goal is to optimize and report what’s achieved.

### 6.2 Script Behavior

- **Configuration:** Use app config for non-secrets (e.g. collection name, page size, date range); env for Atlas URI and credentials.
- **Test cases (conceptual):**
  - Select one billing TIN per tier (1K, 5K, 10K, 50K, 100K, 500K, 1M).
  - For each: run “by provider only” and “by provider + date range” (e.g. 1-year window).
  - For each run: total count time, first-page time, optional second-page time (keyset).
- **Iterations:** Run each scenario N times (e.g. 5–10); report min/max/avg/p95 (or p50/p95/p99) for latency.
- **Report at end:** Table of (provider tier, query type, count latency, first-page latency, sample total count). Optionally: same for $facet if implemented.

### 6.3 Metrics to Report

- **Count query:** Time for `count_documents(filter)` in ms.
- **First page:** Time for `find(...).sort(...).limit(page_size)` in ms.
- **Next page (keyset):** Time for one keyset-based next page in ms.
- **Total count** returned (sanity check).

---

## 7. Configuration

### 7.1 Separation of Concerns

- **Secrets (not in repo):** MongoDB Atlas connection string (URI), any API keys. Source: environment variables or a dedicated secrets store; never in config files committed to version control.
- **Non-secrets:** Collection name, database name, batch sizes for data generation, page size, date range defaults, test iteration counts, etc. Source: configuration file(s).

### 7.2 Suggested Layout

- **Config file (e.g. `config.yaml` or `config.json`):**
  - `mongodb.database`
  - `mongodb.collection`
  - `data_generation.*` (tier definition, total claims target, date range)
  - `query.default_page_size`
  - `performance.iterations`, `performance.tiers_to_test`
- **Environment:** `MONGODB_URI` (and optionally `MONGODB_URI_TEST` for a separate test cluster). Application reads config file + env and composes the client.

---

## 8. Atlas Considerations

- **Connection:** Use Atlas connection string (SRV or standard) from env; TLS by default.
- **Indexes:** Create indexes via application or script (e.g. `create_indexes()` at startup or in a one-off script) so they exist before performance runs.
- **Metrics:** Atlas metrics (e.g. query performance) can complement the script’s report; the design does not depend on Atlas-specific APIs.
- **Deployment:** No special Atlas-only query features required; standard MongoDB driver and compound indexes are sufficient.

---

## 9. Summary of Decisions

| Topic | Decision |
|-------|----------|
| Query key | `billingProvider.providerId` (payer-assigned provider ID) |
| Date range | `serviceBeginDate` / `serviceEndDate` (overlap semantics) |
| Pagination | MongoDB-style keyset using `(serviceBeginDate, _id)` |
| Total count | Separate `count_documents()`; optional $facet comparison in perf script |
| Index | `(billingProvider.providerId, serviceBeginDate, _id)` |
| Data volume | ~3M claims; ≥1 provider per tier 1K–1M; more providers at lower tiers |
| Config | Config file for non-secrets; env for URI/credentials |
| Platform | MongoDB Atlas |

---

## 10. Next Steps

1. Implement config loading (YAML/JSON + env).
2. Implement data generator with tier distribution and reference value sets (§5–6).
3. Create indexes (application or one-off script).
4. Implement query API (filter, count, keyset pagination).
5. Implement performance script and report.
6. Run and tune (e.g. index order, date filter shape) based on report.
