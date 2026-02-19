# Plan: Clean Build for Sharing

This document details what is **required to run the application** vs **development-only artifacts**, and how to produce a shareable asset (e.g. for a wider team) without dev docs, tests, or dev scripts.

---

## 1. Required to run the application

These are the **runtime/production** pieces. Someone receiving only these can run the web app and use the app as intended (query claims by provider with keyset pagination).

| Item | Purpose |
|------|--------|
| **`src/`** | Application code: config loader, DB, indexes, query layer, claims schema, aggregations. |
| **`web/`** | Flask app and static UI: `web/app.py`, `web/static/index.html`. |
| **`config/config.example.yaml`** | Template config (recipient copies to `config/config.yaml` or renames). |
| **`.env.example`** | Template for `MONGODB_URI` (recipient copies to `.env` and fills in). |
| **`requirements.txt`** | Python dependencies. |
| **`scripts/ensure_index.py`** | One-time (or idempotent) index creation; needed so the app’s queries use the compound index. |
| **`web/README.md`** (optional) | Run instructions for the sample UI; helpful for recipients. |

**Minimum steps for a recipient to run:**

1. Copy `config/config.example.yaml` → `config/config.yaml` (or point app at the example).
2. Copy `.env.example` → `.env` and set `MONGODB_URI`.
3. `pip install -r requirements.txt`
4. (Once) Run index creation, e.g. `python -m scripts.ensure_index` (or your existing entrypoint).
5. Start the app: `python -m web.app` or `flask --app web.app:app run --host 0.0.0.0 --port 5000`.

So the **minimal runnable set** is: `src/`, `web/`, `config/config.example.yaml`, `.env.example`, `requirements.txt`, and `scripts/ensure_index.py`. Optionally include `web/README.md` and a short root README with the steps above.

---

## 2. Development-related artifacts

These support building, testing, and designing the system but are **not required to run** the app.

| Category | Items | Notes |
|----------|--------|------|
| **Tests** | `tests/`, `pytest.ini` | Pytest suite and config; used only for development/CI. |
| **Test/dev caches** | `.pytest_cache/`, `htmlcov/`, `.coverage` | Already in `.gitignore`; never share. |
| **Dev / design docs** | `Docs/` (all current files) | BUILD_PLAN, DESIGN, user_requirements, MONGODB_PERMISSIONS, query_scenarios, aggregations, architecture, etc. Useful for developers, not needed to run the app. |
| **Dev/demo scripts** | `scripts/validate_env.py`, `scripts/run_data_generator.py`, `scripts/run_query_scenarios.py`, `scripts/run_facet_by_provider.py` | Environment check, data generation, and query/perf demos. Not required for “run the web app” use case. |
| **Secrets / local config** | `.env`, `config/config.yaml` | Already in `.gitignore`; must not be shared. |
| **Environment / IDE** | `venv/`, `.venv/`, `__pycache__/`, `.idea/`, `.DS_Store` | Already in `.gitignore`; never share. |

Summary:

- **Keep in repo but treat as “dev-only” when sharing:** `tests/`, `pytest.ini`, `Docs/`, and the scripts listed above (except `ensure_index.py`).
- **Never commit/share:** Anything already in `.gitignore` (`.env`, `config/config.yaml`, `venv/`, caches, IDE files).

---

## 3. How to exclude dev artifacts from the shared asset

**.gitignore** is the right tool for **not committing** certain files (secrets, venv, caches, local config). It does **not** by itself create a “clean” shareable package: the shared asset is whatever you **deliver** (repo clone, zip, or tarball).

Two common approaches:

### Option A: One repo + runbook (recommended baseline)

- **Keep** tests, `Docs/`, and dev scripts in the repo (all version-controlled).
- **Do not** add them to `.gitignore` (you’d lose history and the ability to run tests).
- **Add a short runbook** (e.g. root `README.md` or `Docs/RUNBOOK.md`) that states:
  - **To run the application** you only need: (list from section 1).
  - **Development-only:** tests, `Docs/`, and scripts other than `ensure_index` (list from section 2).
- **Sharing:** Share the repo as-is. The “wider team” runs the app using the runbook and can ignore or not clone dev-only parts if they only need to run the app. No change to `.gitignore` for dev docs/tests.

**Pros:** Simple, one source of truth, no duplicate layout.  
**Cons:** The shared “asset” still contains dev folders; you rely on documentation to define “what’s for running” vs “what’s for development.”

### Option B: Release bundle (zip/tarball with only runtime files)

- Keep the **full project** in git (as in Option A).
- **Add a script or manifest** that builds a **release bundle** (e.g. `make release` or `scripts/build_release.sh`) which copies only the “required to run” paths into a folder or archive (e.g. `dist/` or `release-pov-YYYYMMDD.zip`).
- **Sharing:** Share that zip/tarball (or the contents of that folder). The repo stays full; the “clean build” is the bundle.

**Include in bundle:** `src/`, `web/`, `config/config.example.yaml`, `.env.example`, `requirements.txt`, `scripts/ensure_index.py`, and optionally `web/README.md` + a one-page root README with run steps.  
**Exclude from bundle:** `tests/`, `Docs/`, `pytest.ini`, `validate_env`, `run_data_generator`, `run_query_scenarios`, `run_facet_by_provider`, and anything in `.gitignore`.

**Pros:** Recipients get a minimal, run-only tree; no tests or internal docs.  
**Cons:** Extra step to build the bundle; two shapes of the project (repo vs bundle).

### What not to do

- **Do not** put `tests/` or `Docs/` in `.gitignore` just to “clean the build.” That removes them from the repo for everyone and is not standard practice; `.gitignore` is for generated files, secrets, and local environment, not for “dev vs prod” content in the same repo.

---

## 4. Recommended next steps

1. **Keep current `.gitignore`** for: `config/config.yaml`, `.env`, `venv/`, `.pytest_cache/`, coverage, IDE/OS cruft. No need to add tests or Docs there.
2. **Add a short runbook** (e.g. root `README.md` or `Docs/RUNBOOK.md`) that:
   - Lists **what is required to run the application** (section 1) and the minimal run steps.
   - Lists **what is development-only** (section 2) so the wider team knows what they can ignore.
3. **Optional:** Add a **release script** (Option B) that builds a zip or `dist/` containing only the runtime set, so you can hand out a “clean” shareable asset when needed.

If you tell me whether you prefer “runbook only” (Option A) or “runbook + release bundle” (Option B), I can draft the exact README/RUNBOOK text and, for B, a minimal `scripts/build_release.sh` or `Makefile` target.
