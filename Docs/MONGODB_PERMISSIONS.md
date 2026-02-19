# MongoDB Atlas – Required Permissions

This app uses **one database** and **specific collections**. Grant permissions **only on that database** (do not use “all databases”).

---

## 1. Database and collections used

| Resource | Config key | Default | Used by |
|----------|------------|---------|---------|
| **Database** | `config.mongodb.database` | `pov_claims` | All app code |
| **Collection** | `config.mongodb.collection` | `claims` | Data generator, query API, performance script, `ensure_index` script |
| **Collection** | (hardcoded in test) | `_integration_test_claims` | Integration test only (create index, insert one doc, find, delete) |

If you change the database or collection name in `config/config.yaml`, the database user must have permissions on **that** database (and its collections).

---

## 2. Minimum actions required

The application needs these **MongoDB actions** on the database above (and its collections):

| Action | Purpose |
|--------|---------|
| **find** | Query API and performance script read claims. |
| **insert** | Data generator inserts claim documents. |
| **createIndex** | `ensure_index` script and integration test create the compound index. |
| **listIndexes** | Used when creating/checking indexes. |
| **remove** | Integration test deletes the single test document it inserts. *(Not needed if you never run integration tests.)* |

We do **not** need: `update`, `drop`, `dropIndex`, `createCollection`, or admin/other-database access.

---

## 3. Grant in Atlas (single database only)

1. In **Atlas** go to **Database Access** → your database user (or create one).
2. Click **Edit** (pencil).
3. Under **Database User Privileges**, add a privilege:
   - **Built-in Role:** `readWrite`
   - **Database:** enter **only** the database name you use in config (default: **`pov_claims`**).  
     Do **not** choose “Atlas admin” or “Read and write to any database” unless you intend to allow access to every database.
4. Remove any privilege that grants access to “all databases” if you want to restrict this user to the POV app only.
5. Save.

Result: the user has `readWrite` (find, insert, update, remove, createIndex, listIndexes, etc.) **only** on the database `pov_claims` (or whatever you set in config).

---

## 4. Custom role (minimal actions, optional)

If you prefer a custom role with only the actions in section 2:

1. **Database Access** → your user → **Edit**.
2. **Add Custom Role** (or create the custom role in the project first).
3. On the database you use (e.g. `pov_claims`), grant:
   - **find**
   - **insert**
   - **createIndex**
   - **listIndexes**
   - **remove** (only if you run the integration test that inserts/deletes one doc)

Atlas may show these under “Collection” or “Database” scope; grant them for the **single database** (e.g. `pov_claims`), not globally.

---

## 5. Summary

- **Database:** The one in `config.mongodb.database` (default **`pov_claims`**).
- **Collections:** `config.mongodb.collection` (default **`claims`**), and **`_integration_test_claims`** only for the integration test.
- **Scope:** Grant **only this database**; do not grant readWrite (or equivalent) to all databases.
- **Easiest:** Built-in role **readWrite** on database **`pov_claims`** (or your configured database name).

After updating the user, run:

```bash
python -m scripts.ensure_index
```

You should see: `Index ready: idx_provider_id_service_begin_end_id`.
