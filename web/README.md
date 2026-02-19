# Sample front-end: Claims by Provider

Minimal UI to query claims by **Provider ID** with **keyset-based pagination** and **timing** for each query step.

## Approach (3b)

The backend uses the **count + find** approach (same as scenario 3b in `run_query_scenarios.py`):

- **Total count**: `count_documents(filter)` — uses the compound index.
- **First page**: `find(filter).sort(serviceBeginDate, _id).limit(page_size + 1)` — index scan, stops after one page.
- **Next pages**: keyset find using the cursor from the previous page — same index, consistent latency.

This avoids the slower `$facet` aggregation (3a), which can do an in-memory sort over all matching documents. Public guidance (e.g. [MongoDB pagination patterns](https://www.mongodb.com/blog/post/pagination-patterns-in-mongodb), keyset vs offset) recommends keyset pagination with an index-aligned sort for large datasets; combining that with a separate count and a limited find is the recommended pattern for “total + first page” UIs.

## Run

1. From the project root, ensure `.env` and `config/config.yaml` (or `config.example.yaml`) are set and MongoDB is reachable.
2. Install deps: `pip install -r requirements.txt` (includes Flask).
3. Start the app:

   ```bash
   python -m web.app
   ```

   or, from the project root:

   ```bash
   flask --app web.app:app run --host 0.0.0.0 --port 5000
   ```

4. Open **http://localhost:5000** in a browser.

## UI

- **Provider ID** and **Records per page** at the top; optional **Date start** / **Date end** (YYYY-MM-DD).  
  Date-range queries can be slower than provider-only: the index is on `(providerId, serviceBeginDate, _id)` and now includes `serviceEndDate`, so date-range overlap queries stay fast. See `Docs/query_scenarios.md` (§ “Why date-range queries can be slower”).
- **Load first page** runs the count and first-page find; **Timings** show count time and first-page time.
- **Previous** / **Next** move through pages; going to the next page runs a keyset query and shows **This page (keyset)** timing.
- Cached pages mean **Previous** does not refetch.

## API

- **POST /api/page**  
  Body (JSON): `provider_id`, `page_size`, optional `date_start`, `date_end`, and optional `cursor` for the next page.
  - Without `cursor`: returns `total`, `numPages`, `documents`, `nextCursor`, and `timings: { count_ms, first_page_ms }`.
  - With `cursor`: returns `documents`, `nextCursor`, and `timings: { next_page_ms }`.
