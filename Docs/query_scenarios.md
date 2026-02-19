# Query scenarios (providerId + optional service date)

Three use cases are implemented in `src/query_scenarios.py` and can be run via `scripts/run_query_scenarios.py`.

## Inputs

- **providerId** (required): `billingProvider.providerId` to filter on.
- **service date range** (optional): `date_start` and `date_end`. Filter uses overlap:  
  `serviceEndDate >= dateStart` and `serviceBeginDate <= dateEnd`.
- **page size** (optional, use case 3): number of documents per page (default from config, e.g. 100).

## Use cases

1. **Count documents**  
   `count_documents(filter)` with the same filter used everywhere.  
   Function: `use_case_count_documents(collection, provider_id, service_date_start=None, service_date_end=None)`.

2. **Standard find**  
   `find(filter).sort(CLAIMS_QUERY_SORT).limit(limit)`.  
   Function: `use_case_find(collection, provider_id, service_date_start=None, service_date_end=None, limit=None)`.

3. **First page aggregation (total + first page + keyset cursor)**  
   Single aggregation with `$facet`:
   - One branch: `$count` for total matching documents.
   - Other branch: same filter, sort `[("serviceBeginDate", 1), ("_id", 1)]`, limit `page_size + 1` (to know if there is a next page).  
   Returns: `total`, `pageSize`, `numPages`, `documents` (sliced to `page_size`), and `nextCursor` (keyset for the next page, or `None`).  
   Function: `use_case_first_page_aggregation(collection, provider_id, page_size=100, service_date_start=None, service_date_end=None)`.

   **Next page (keyset)**  
   `use_case_next_page_find(collection, provider_id, cursor, page_size, service_date_start=None, service_date_end=None)`  
   uses a find with a filter that combines the base filter and “after cursor” on `(serviceBeginDate, _id)`.

## Keyset pagination

- **Sort**: `[("serviceBeginDate", 1), ("serviceEndDate", 1), ("_id", 1)]` (aligned with index `idx_provider_id_service_begin_end_id`).
- **Cursor**: last document on the current page: `{ "serviceBeginDate", "serviceEndDate", "_id" }`.
- **Next page filter**: base filter plus “after cursor”:  
  Base filter plus "after cursor" on `(serviceBeginDate, serviceEndDate, _id)` (three-way $or).

This avoids offset-based pagination and stays efficient on large result sets.

## Date-range performance (index includes serviceEndDate)

The overlap filter uses `serviceEndDate >= dateStart` and `serviceBeginDate <= dateEnd`. The compound index is **`(billingProvider.providerId, serviceBeginDate, serviceEndDate, _id)`**, so both date predicates can be applied from the index and date-range queries stay fast. The keyset cursor includes `serviceEndDate` so pagination order matches the index.

**Alternative (simpler UI):** If you only need “claims that **start** in a range”, you can filter by `serviceBeginDate` only (e.g. `serviceBeginDate >= dateStart` and optionally `serviceBeginDate <= dateEnd`). That would work with a smaller index `(providerId, serviceBeginDate, _id)` and no `serviceEndDate` in the cursor, but you would no longer support “overlap” semantics (e.g. a claim that starts before the range but ends inside it would be excluded).

## Use case 3: two implementations (side-by-side)

The script always runs **both** first-page implementations so you can compare timings:

- **3a. agg first page** – Single `$facet` aggregation (total + first page). The two branches run over the full matched set; the sort inside `$facet` often cannot use the index, so latency grows with total matches (e.g. in-memory sort over 10k–50k docs).
- **3b. first page (count+find)** – Same return shape using `count_documents()` + `find().sort().limit()`. Both use the index; the find stops after `page_size+1` docs, so this is typically much faster for large result sets.

- **`--explain`**: run `explain` on the 3a aggregation and print server `executionTimeMillis` and `totalDocsExamined`.

## Running the script

```bash
# Count + find + first page (3a and 3b run every time for comparison)
python -m scripts.run_query_scenarios --provider-id 00-000001

# With service date range
python -m scripts.run_query_scenarios --provider-id 00-000001 --date-start 2002-01-01 --date-end 2002-12-31

# Custom page size and find limit
python -m scripts.run_query_scenarios --provider-id 00-000001 --page-size 10 --find-limit 5

# Include explain for 3a (server executionTimeMillis + totalDocsExamined)
python -m scripts.run_query_scenarios --provider-id 00-000001 --explain
```

The script prints client elapsed time (ms) for each step. When there is a next page, it runs one keyset next-page query.
