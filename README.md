# GeM Astra — AI-Driven Public Procurement Analytics

GeM Astra helps authorised procurement reviewers identify potentially suspicious
bidding patterns in Government e-Marketplace (GeM) tenders.

> **Disclaimer:** Risk indicators are analytical signals only. All findings require
> expert human review. This tool does not determine guilt or recommend punitive action.

---

## Requirements

- Python 3.9+
- pip

## Installation

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` by default.  
The SQLite database (`data/gem_astra.db`) is created automatically on first launch.

## React frontend (Steps 1–4 complete)

```bash
# Terminal 1 — FastAPI backend (port 8000)
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — React / Vite dev server (port 5173)
cd frontend
npm install        # first time only
npm run dev
```

| Server | URL |
|---|---|
| React frontend | http://localhost:5173 |
| FastAPI backend | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/api/docs |
| Health check | http://localhost:8000/api/health |
| Network graph | http://localhost:8000/api/network |
| Risk analysis | http://localhost:8000/api/risk |

The Vite dev server proxies all `/api/*` requests to FastAPI automatically.

> **Note:** If port 8000 is occupied by a stale process, run:
> `uvicorn backend.main:app --port 8001` and update the proxy target in
> `frontend/vite.config.ts` to `http://localhost:8001` temporarily.

## Run tests

```bash
python -m pytest tests/ -v
```

---

## Importing real GeM tender records

1. Prepare a CSV with the tender schema (see below).
2. Open the app → **Tender Explorer** → **Import** tab.
3. Upload the CSV file.
4. Select the correct source type:
   - `real_public_data` — verified official GeM exports only
   - `synthetic` — demo / test data
   - `unknown` — unverified source
5. Click **Import into database**.

The importer will report inserted / duplicate / rejected counts.  
Duplicate `tender_id` values are skipped; existing records are never overwritten.  
A failed import is fully rolled back — no partial records are written.

---

## Data files

| File | Purpose |
|---|---|
| `data/gem_tenders.csv` | Verified GeM tender metadata (header-only until real data is supplied) |
| `data/demo_bids.csv` | Synthetic bid-level data for testing (labelled `source_type=synthetic`) |
| `data/raw/` | Drop raw source documents here |
| `data/processed/` | Cleaned/transformed outputs |

### Tender schema
`tender_id, item_name, department, start_date, end_date, status, quantity, official_url, source_type, source_document`

### Bid schema
`tender_id, bidder_id, bid_amount, bid_timestamp, outcome, product_category, source_type`

---

## Project structure

```
app.py                  # Main Streamlit entry point
pages/
  overview.py
  tender_explorer.py
  coming_soon.py
  about.py
utils/
  data_loader.py
data/
  gem_tenders.csv
  demo_bids.csv
  raw/
  processed/
requirements.txt
README.md
```

## Status

| Module | Status |
|---|---|
| Overview | ✅ Live — database-derived metrics |
| Tender Explorer | ✅ Live — SQLite browse, search, CSV import |
| Risk Analysis | ✅ Live — engine findings, score, evidence |
| Bidder Network | ✅ Live — SVG co-participation graph |
| Investigation Reports | 🔜 Planned |
| About | ✅ Done |
