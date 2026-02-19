# MongoDB Keyset Pagination Demo

**For MongoDB Solutions Architects.** This repo is a runnable demo you can use to show keyset (cursor-based) pagination on MongoDB, with a small web UI, timings, and a live request log. It started as a PBM integration services POV and is now maintained as a general-purpose demo for solutions architects.

> **Note:** The code and documentation in this repository are predominantly **AI-generated**. They are provided as-is for demo and reference; review and adapt as needed for your environment.

---

## What this demo shows (talking points for the demo)

### Pagination approach

The app demonstrates **keyset (cursor-based) pagination** against a MongoDB collection of claims, filtered by provider (and optional date range). This is the recommended pattern for large result sets: no `skip()`—which gets slower as the offset grows—and consistent latency per page.

- **First page:** The backend runs a **count** (for total and page count) and a **find** with the same filter, index-aligned sort, and `limit(page_size + 1)` to get the first page and a cursor for the next. Both operations use the compound index.
- **Next page:** A single **find** with a “after cursor” filter: documents where `(serviceBeginDate, serviceEndDate, _id)` is greater than the last document of the previous page. Same index, same sort; cost is one index range scan for one page.
- **Previous page:** Implemented with a “before cursor” (the first document of the current page). The backend does a find with **reverse sort** and a “before” keyset filter, then re-sorts the result to ascending so the UI shows the same order as forward pagination.
- **Last page (clever workaround):** Instead of stepping through every page to reach the end, the **Last** button uses a **reverse index scan**: one find with the same filter and **descending** sort, `limit(page_size)`, then an **in-memory re-sort** to ascending. Cost is O(page_size) index read plus O(page_size log page_size) sort—no `skip(total - page_size)`. You can call this out when clicking **Last** on a provider with many pages.

### Keyset pagination in brief

- **Sort** is aligned with the index: e.g. `(serviceBeginDate, serviceEndDate, _id)` ascending.
- **Cursor** is the sort-key values of the last document on the current page (or first document for “previous”).
- **Next page** = find with filter AND `(serviceBeginDate, serviceEndDate, _id) > cursor`, same sort, `limit(page_size + 1)`; slice to `page_size` and use the last doc as the next cursor.

This keeps every page request to a bounded index scan and avoids the pitfalls of offset-based pagination.

### What to point out in the UI while running the demo

- **Timings** (below the controls): After each action you’ll see **Total count**, **First page**, **This page (keyset)**, **Prev page (keyset)**, and **Last page (reverse)** in milliseconds. Use these to show that keyset next/prev and the last-page reverse trick stay fast regardless of page position.
- **MongoDB requests** (right-hand panel): Scrollable list of every request sent to MongoDB. Each entry shows the operation (e.g. `count_documents`, `find` with filter/sort/limit), the request body (filter, sort, limit), and the latency in ms. The banner at the top shows **Viewing page X of Y**. This lets you walk through exactly what the app is doing for each button click.

Optional: use **Run count on every page** to show count cost on next/prev if you want to contrast “count every time” vs “count once on first load.”

---

## What you need to run the application (runtime)

These are the only pieces required to run the app end-to-end:

| Item | Purpose |
|------|--------|
| **`src/`** | Application code: config loader, DB, indexes, query layer, claims schema. |
| **`web/`** | Flask app and static UI (`web/app.py`, `web/static/index.html`). |
| **`config/config.example.yaml`** | Template config (you copy it to `config/config.yaml`). |
| **`.env.example`** | Template for `MONGODB_URI` (you copy it to `.env` and set your URI). |
| **`requirements.txt`** | Python dependencies. |
| **`scripts/ensure_index.py`** | One-time index creation so queries use the compound index. |

Everything else in the repo (tests, design docs, other scripts) is for **development only** and can be ignored if you only need to run the demo.

---

## How to run end-to-end

From the **project root**:

1. **Config and secrets**
   - Copy `config/config.example.yaml` to `config/config.yaml` (or keep the example and point the app at it).
   - Copy `.env.example` to `.env` and set `MONGODB_URI` to your MongoDB connection string.

2. **Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Index (once per database)**
   ```bash
   python -m scripts.ensure_index
   ```

4. **Start the app**
   ```bash
   python -m web.app
   ```
   Or: `flask --app web.app:app run --host 0.0.0.0 --port 5000`

5. **Use the UI**  
   Open **http://localhost:5000** in a browser. Enter a Provider ID (and optional date range), choose records per page, then use **Load first page**, **Next**, **Previous**, and **Last** while watching the timings and the **MongoDB requests** panel.

For UI and API details, see **`web/README.md`**.

---

## Development-only artifacts

These support building, testing, and designing the system but are **not required to run** the demo. Safe to ignore if you only need to run the application.

| Category | Items |
|----------|--------|
| **Tests** | `tests/`, `pytest.ini` — Pytest suite and config. |
| **Design / dev docs** | `Docs/` — BUILD_PLAN, DESIGN, user_requirements, MONGODB_PERMISSIONS, query_scenarios, aggregations, architecture, SHARING_AND_CLEANUP_PLAN, etc. |
| **Dev / demo scripts** | `scripts/validate_env.py`, `scripts/run_data_generator.py`, `scripts/run_query_scenarios.py`, `scripts/run_facet_by_provider.py` — environment check, data generation, and query/perf demos. |

Secrets and local environment (`.env`, `config/config.yaml`, `venv/`, caches, IDE files) are in `.gitignore` and should never be committed or shared.
