# Build Plan: Testable Phases

This plan breaks the PBM Integration demo into **testable phases**. Each phase has a clear deliverable and a way to verify it before moving on. Dependencies flow left to right.

---

## Phase Overview

| Phase | Deliverable | Test / How to verify |
|-------|-------------|----------------------|
| **1** | Project layout + config loading | Unit test: load config and env; no MongoDB required |
| **2** | MongoDB connection + index creation | Script: connect and create index; optional small insert |
| **3** | Claim document builder (in-memory) | Unit test: one claim matches schema and reference values |
| **4** | Data generator (tier math + batch writer) | Unit test: tier counts sum to ~3M; integration: write to DB (small batch) |
| **5** | Query layer (filter, count, keyset page) | Unit test: filter/cursor logic; integration: query real collection |
| **6** | Query API (CLI or minimal HTTP) | Manual: run queries by TIN ± date, check count and pages |
| **7** | Performance script + report | Run script; report prints and matches expected tiers |

---

## Phase 1: Project Layout and Config Loading

**Goal:** Repo structure, config file schema, and loading config + env (no secrets in config).

**Deliverables:**
- Directory layout: `src/`, `tests/`, `config/`, `Docs/`
- `config/config.example.yaml` (or `.json`) with all keys; no URI/passwords
- `src/config_loader.py`: load config file + read `MONGODB_URI` from env
- `requirements.txt` with `pymongo`, `pyyaml` (if YAML)

**How to test:**
- **Unit:** Without MongoDB, load config from a test YAML/JSON; assert database name, collection, page size, tier list.
- **Unit:** With `MONGODB_URI` set in env, assert URI is read; with unset, assert clear error or default behavior per design.

**Exit criteria:** Tests pass; no credentials in config file or in repo.

---

## Phase 2: MongoDB Connection and Index Creation

**Goal:** Connect to Atlas using URI from env and create the single compound index.

**Deliverables:**
- `src/db.py` (or `database.py`): get client and get collection (database/collection from config).
- `src/indexes.py`: create index `(billingProvider.providerTin, serviceBeginDate, _id)`; idempotent (create if not exists).

**How to test:**
- **Integration:** Run a small script that: connects, gets collection, creates index, (optional) inserts one document and finds it. Requires real Atlas URI in env.
- **Unit (optional):** Mock `pymongo` collection and assert `create_index` is called with the correct key spec.

**Exit criteria:** Index appears in Atlas; no errors on repeated runs.

---

## Phase 3: Claim Document Builder

**Goal:** Build a single claim document (dict) that matches `sample.json` structure and design (types, reference value sets). No I/O.

**Deliverables:**
- `src/claims/schema.py` or `claims_builder.py`: one function that, given (e.g.) provider TIN, NPI, name, service dates, claim id, returns one BSON-ready document (dates as `datetime`, amounts as float or Decimal128).
- Reference data in code or config: `recoveryMethod` list, `claimSystemCode` list (from DESIGN.md).

**How to test:**
- **Unit:** Generate one claim; assert keys match `sample.json` (renderingProvider, billingProvider, serviceBeginDate, serviceEndDate, patientInformation, identifiers, lastUpdatedTs, processedAmounts, recoveryMethod).
- **Unit:** Assert `serviceBeginDate` and `serviceEndDate` are after year 2000 when given such inputs.
- **Unit:** Assert `recoveryMethod` and `identifiers.claimSystemCode` are from the design’s reference sets.

**Exit criteria:** All schema and reference-value tests pass.

---

## Phase 4: Data Generator (Tier Distribution + Batch Write)

**Goal:** Generate ~3M claims with correct tier distribution (≥1 provider per 1K–1M tier; more providers at lower tiers) and write to MongoDB in batches.

**Deliverables:**
- Tier configuration in config: tier sizes (1K, 5K, …) and provider counts per tier (or formula) so total ≈ 3M.
- `src/data_generator.py`: compute per-provider claim counts; for each provider, generate that many claims (using claim builder from Phase 3), write in batches (e.g. 5k–10k per batch); progress/logging optional.
- All service dates after 2000; intentional overlap of dates across providers.

**How to test:**
- **Unit:** Given tier config, assert total claim count is ~3M and each tier has at least one provider with the right claim count.
- **Unit:** Assert every generated claim has `serviceBeginDate` ≥ 2000-01-01.
- **Integration:** Run generator with a **small** total (e.g. 100 claims, 2–3 providers) against real DB; then assert collection count and that one provider TIN has expected count.

**Exit criteria:** Small run succeeds; full 3M run can be executed separately (long-running).

---

## Phase 5: Query Layer (Filter, Count, Keyset Pagination)

**Goal:** Core query logic: build filter from provider TIN + optional date range; return total count and one page of docs with keyset cursor for next/prev.

**Deliverables:**
- `src/query.py` (or `claims/query.py`): functions `build_filter(provider_tin, date_start, date_end)`, `get_total_count(collection, filter)`, `get_page(collection, filter, sort, page_size, cursor_after=None, cursor_before=None)`, and cursor encoding/decoding (e.g. last `(serviceBeginDate, _id)` for “next”, first for “prev”).
- Sort: `(serviceBeginDate, 1), (_id, 1)`.
- Date semantics: overlap (serviceEndDate >= start, serviceBeginDate <= end).

**How to test:**
- **Unit:** With a mock collection (or in-memory list of dicts with `serviceBeginDate`, `_id`), assert filter includes provider TIN and date bounds; assert keyset “next” returns correct subset.
- **Integration:** Against collection with data from Phase 4, run get_total_count and get_page for a known provider TIN; assert count matches; assert second page uses cursor and does not duplicate first page.

**Exit criteria:** Count and pagination match expectations; no duplicate or skipped docs when paging.

---

## Phase 6: Query API (CLI or Minimal HTTP)

**Goal:** Expose the query layer so a user can run “by provider” and “by provider + date range” and get total + paginated results.

**Deliverables:**
- CLI (e.g. `python -m src.cli query --provider-tin <TIN> [--date-start YYYY-MM-DD] [--date-end YYYY-MM-DD] [--page-size N]`) or a minimal HTTP API (one GET endpoint with query params). Response: total count, list of documents, next/prev cursor (or link).
- Uses config for default page size and collection; env for URI.

**How to test:**
- **Manual:** Run CLI/API with a real provider TIN from your loaded data; verify total and first page; request next page with cursor and verify different docs and consistent total.

**Exit criteria:** Demo-ready: user can query by TIN and optional date range and page through results.

---

## Phase 7: Performance Script and Report

**Goal:** Run repeated queries (by provider only; by provider + date range) for one TIN per tier; output a report (count latency, first-page latency, optional next-page latency).

**Deliverables:**
- `src/performance.py` or `scripts/run_performance.py`: read tier list and one TIN per tier from config (or from DB); for each, run “provider only” and “provider + date range” N times; collect count time, first-page time, next-page time; compute min/avg/p95 (or similar); print table.
- Config: `performance.iterations`, `performance.tiers_to_test` (or derive from data generator config).

**How to test:**
- **Integration:** Run script against DB with at least two tiers populated (e.g. 1K and 10K); report prints without error and shows different latencies for different tiers.

**Exit criteria:** Report is readable and reflects that larger tiers take longer to count; script runs end-to-end.

---

## Suggested Order and Dependencies

```
Phase 1 (config)     →  Phase 2 (DB + index)
     ↓                        ↓
Phase 3 (claim doc)  →  Phase 4 (data generator)  →  Phase 5 (query layer)
                                                           ↓
Phase 6 (API)  ←──────────────────────────────────────────┘
     ↓
Phase 7 (performance script)
```

- **1 and 3** can be done in parallel after repo layout exists.
- **2** needs 1; **4** needs 1, 2, 3; **5** needs 2 (and ideally 4 for integration tests); **6** needs 5; **7** needs 4 and 5 (and optionally 6 if API is used for perf).

---

## Test Strategy Summary

| Phase | Unit tests | Integration tests |
|-------|------------|--------------------|
| 1 | Config load; env read | — |
| 2 | (optional) Mock index create | Connect + create index (+ 1 doc) |
| 3 | Schema; dates; reference values | — |
| 4 | Tier math; date bounds | Small batch write + count |
| 5 | Filter/cursor logic | Real collection count + 2 pages |
| 6 | — | Manual CLI/API |
| 7 | — | Run script; check report |

Use a **test database or collection** (e.g. `pov_test`) and a **small data set** for integration tests so they stay fast; reserve the full 3M-claim load for a separate, explicit “full load” run.
