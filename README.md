# OrderTrack Pro

Order tracking, job-work (annexure) control and document printing for a machining shop, driven entirely by the
Excel workbooks the team already maintains. Admin-only, JWT-secured, fully on-premise: **no external AI service is
used and no data leaves the server.**

## Run it on your computer

Requirements: **Python 3.11+** (tick "Add python.exe to PATH" when installing) and **Node.js LTS**
(only needed to build the screens the first time).

Open a terminal **in this folder** and run:

```sh
python run.py
```

That's all. The first run installs everything (a few minutes), then the browser opens at http://localhost:8000.
Click **Create an account** on the sign-in page, choose any username and password, and use them to sign in on every
later visit. Keep the terminal open while you use the app; press **Ctrl+C** to stop.

| Command | What it does |
|---|---|
| `python run.py` | Normal use: one server on http://localhost:8000 (UI + API) |
| `python run.py --dev` | Developer mode: auto-reloading API + live-reloading UI on http://localhost:5173 |
| `python run.py --test` | Run the automated tests |
| `npm start` / `npm run dev` / `npm test` | The same three commands, via npm |

Then upload the workbooks in **Data Sheets** (`annexure 2026 - 2027.xls`, `ORDER SHEET 2026 - 2027.xlsx`).

**Deploying to production for free** (Vercel + Render + Neon + Backblaze B2): see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

## What it does

| Feature | Where |
|---|---|
| Live status by order number: **green = live / in progress, red = completed**, stage timeline, current activity ("HEAT TREATMENT at VT Vacuum Heat Treaters since 15 Sep 2026, DC 4326"), quantities, job-work trail. Auto-refreshes every 15 s | Live Tracker |
| Update progress (coating, despatch, rejects, invoice) with formula columns recomputed and an audit trail | Live Tracker → Update progress |
| Annexure with order no., items requested, operation, unit cost, value of goods, invoice/DC date, HRC check (spec vs measured, OK / out-of-spec). Choose entries and copies, download **PDF or Excel**, **Submit** → numbered document (`ANX/26-27/00001`) + printer dialog | Annexure & Print |
| Route card (from the "Print Sheet" layout) | Annexure & Print → Route card |
| Print history with reprint | Annexure & Print → Print history |
| Dashboard: KPIs, intake vs despatch trend, live work by stage / customer / vendor, job-work spend, at-risk orders, cost anomalies, storage | Dashboard |
| Plain-English command bar (Ctrl K): "emergency orders pending for taegutec", "what is at globe-tech", "how many overdue orders for tungaloy", "annexure for 2052" | Top bar |
| Data sheets: upload, versioning (replace / archive / restore), per-table grid with search, sort, add / edit / delete, Excel/CSV export, column-mapping editor, data-quality report | Data Sheets |

## How "not hard-coded" works

Nothing in the code knows the client's column names, sheet names or layout. The pipeline is:

1. **Ingestion** (`backend/app/ingest/reader.py`): reads `.xls / .xlsx / .xlsm / .csv`, segments each sheet into
   independent tables (side-by-side lists, merged cells), detects the header row by scoring, separates printable
   templates (forms) from data tables, and strips pre-filled template rows (serials plus formula defaults).
2. **Column understanding**, a neural network (`intelligence/column_model.py`): an MLP (4117→256→96→42) reads each
   column's header *and* its values (char n-grams, value vocabulary, value shapes, 21 distribution statistics) and
   predicts its meaning. It is trained on synthetic columns generated from the knowledge base
   `intelligence/ontology.json`, plus every correction the admin makes in the mapping editor, so it learns the
   client's vocabulary over time.
3. **Assignment and typing** (`intelligence/profiler.py`): the Hungarian algorithm assigns columns to meanings
   one-to-one, and a weighted evidence score decides the table type (order book, job-work ledger, vendor master, …).
   The result is a **JSON profile** per table that holds the field mapping, the stage pipeline, the completion rules and
   any **discovered formulas** (e.g. `Reject = Issued − Coating`, found by exhaustive search over column relations).
   Profiles are viewable and editable in the UI.
4. **Rule engine** (`intelligence/rules.py`): stages and "completed" are evaluated from the JSON rules, not from
   code.

## Intelligence (all local, scikit-learn)

| Model | Algorithm | Measured on the client data |
|---|---|---|
| Column meaning | Multi-layer perceptron + Hungarian assignment | 88–91 % hold-out accuracy on synthetic columns; every real column of both workbooks mapped correctly (the CLASSIC sheet's swapped *Unit cost / Value of goods* headers need one manual correction) |
| Completion-date forecast | Histogram gradient boosting (MAE) + P80 quantile model | ±13.0 days CV error vs ±17.3 naive baseline (25 % better) on 1,861 completed lines |
| Job-work cost anomalies | Isolation Forest + robust z-score per operation | 177 of 4,403 entries flagged (e.g. unit cost ₹1 for blank milling, typical ₹60) |
| Command bar | TF-IDF (word + char n-grams) → logistic regression; fuzzy gazetteer + interval scheduling for entities | 8 intents |
| Spelling variants | Union-find over fuzzy matches | "HI-SPEED SPARES" = "Hi-Speed Spares", … |

**Is an AI provider API needed?** No. The one thing these models cannot do is answer *arbitrary* free-form questions in
prose (open chat). Every operation this application needs is covered offline and deterministically.

## Data engineering

- Lineage: every record keeps its source file, sheet and row; edits are audited with before/after values.
- Versioning: re-uploading a workbook is detected (same name or sheet structure) and offered as *replace* (the old
  version is archived) instead of silently double-counting orders. Identical order lines from two files are
  counted once.
- Data quality rules per table (duplicate order numbers, invalid / impossible dates, despatch > issued, negative
  quantities, annexure references to unknown orders, HRC out of spec, material at a vendor > 30 days) with a score
  and drill-down to the rows.
- Entity resolution, multi-reference parsing (`2328/29` → orders 2328 and 2329), derived-column recomputation.

## Security and data protection

- **Accounts:** standard **Create account** and **Sign in** pages. Any username and password are allowed (no format
  rules), and accounts are stored permanently in the database. Users can add, remove and unlock users, and everyone can
  change their own username or password. A **New sign-ups** switch (Settings → Users) closes registration once your
  team is set up.
- **Sign-in protection:** bcrypt hashing, per-account lockout after 5 wrong passwords (escalating 1 → 60 min),
  per-IP rate limiting, signed expiring JWTs, instant revocation on password change or *Sign out everywhere*.
- **Transport and browser:** HTTPS/HSTS, strict Content-Security-Policy (no inline or third-party scripts), framing
  blocked, `noindex` everywhere, CORS limited to your own frontend, API docs off in production.
- **Data at rest:** workbooks go to a private, encrypted S3 bucket (or a local folder). The database is Neon
  PostgreSQL (encrypted, TLS) or local SQLite. No data, secrets or Excel files are ever committed to the
  repository (`.gitignore`).
- **Audit trail** of every sign-in, upload, edit, print and account change.

## Storage

| Setting | Local / own server (default) | Free cloud |
|---|---|---|
| Database | SQLite file in `DATA_DIR` | `DATABASE_URL` = Neon PostgreSQL |
| Workbook files | `DATA_DIR/files` | `S3_BUCKET` + keys = Backblaze B2 / Cloudflare R2 |

The quota is `STORAGE_QUOTA_GB` (default 10 GB; requirement: more than 5 GB), and usage is shown in the app.

## Configuration

Nothing is required locally. Optional overrides go in `backend/.env` (see `backend/.env.example`). In production,
set environment variables on the host; `render.yaml` defines them for Render. The frontend reads `VITE_API_URL` at
build time when the UI and API are on different domains.

## Tests

```sh
python run.py --test
```
GitHub runs the same tests plus the website build on every push (**Actions ▸ CI**). Render deploys the backend only
after these checks pass (see DEPLOYMENT.md, step 3.8).
These are unit tests for parsing, rules, formula discovery, entity resolution and segmentation, plus an end-to-end
API test: upload → ML profiling → live status → progress update → annexure submit → PDF/XLSX.

## Project layout

```
backend/app
  ingest/        reader (segmentation, header detection), pipeline (profiling, indexing)
  intelligence/  ontology.json, features, synth, column_model (MLP), profiler, rules,
                 eta (GBM), anomaly (IsolationForest), canonical (union-find), nlq
  services/      workspace (joins + status engine + quality), orders, documents (PDF/XLSX), keys
  routers/       auth, data (files/tables/mapping/quality), orders (tracker/annexure/print/dashboard/ask)
frontend/src     React + TypeScript + Tailwind (pages: Dashboard, Tracker, Orders, Annexure, DataSheets,
                 TableView, Insights, Settings)
```

## Notes on the client data

- About 1,050 live order lines are past their ETD with no coating or despatch recorded. Many are probably finished
  but not yet updated in the sheet; the Overdue view lists them for clean-up.
- `Reject Qty` in the order sheet is a formula (`Issued − Coating`), so before coating it equals the issued
  quantity. The app shows it only once coating or despatch is recorded.
- In the `CLASSIC` annexure sheet, the *Value of goods* and *Unit cost* headers are swapped relative to their values.
  Correct this once in Data Sheets → CLASSIC → Column mapping.
- 412 annexure entries reference previous-year order numbers; they are listed in the data-quality report.
