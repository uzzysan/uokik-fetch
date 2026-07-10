# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

This is a web scraper that extracts unfair contract terms (klauzule niedozwolone) from the Polish UOKiK (Office of Competition and Consumer Protection) registry at https://rejestr.uokik.gov.pl and stores them in a SQLite database.

**Key characteristics:**
- Single-purpose scraper with SQLAlchemy ORM
- Data includes court rulings, prohibited clauses, industries, plaintiffs, defendants, and legal issues
- Polish language content and date formats (DD.MM.YYYY)
- Uses `uv` as package manager (not pip/poetry)

## Common Commands

### Installing Dependencies
```bash
uv sync
```

### Initializing Database
```bash
uv run init_database.py
```

### Running the Scraper (Full)
```bash
uv run main.py
```

### Running Incremental Update (New Entries Only)
```bash
uv run update_new_entries.py
```

### Activating Virtual Environment (if needed)
```bash
source .venv/bin/activate
```

## Architecture

### Data Flow
1. **main.py** - Full scraper: tests DB connection → initializes DB → scrapes all pages → saves incrementally → displays summary
2. **update_new_entries.py** - Incremental updater: checks max entry in DB → fetches only newer entries → saves to DB
3. **scraper.py** - Web scraping logic: fetches HTML → parses BeautifulSoup → extracts data → returns list of dicts
4. **database.py** - DB management: creates engine → provides session factory → initializes tables
5. **models.py** - SQLAlchemy model: single table `klauzule_niedozwolone` with timestamps and indexes
6. **config.py** - Environment config: loads .env → defines URLs, timeouts, headers
7. **init_database.py** - Standalone initialization script with connection testing and table verification

### Key Design Patterns
- **Duplicate handling**: Check `numer_postanowienia` uniqueness before inserting (see `save_entries_to_db()`)
- **Error isolation**: Each entry saves independently with try/catch and rollback
- **Date parsing**: Multiple format attempts in `parse_date()` due to inconsistent source data
- **Session management**: Manual session handling with explicit `db.close()` in finally blocks

### Database Schema
The `KlauzulaNiedozwolona` model has:
- Primary key: `id` (auto-increment)
- Unique constraint: `numer_postanowienia` (indexed)
- Indexed fields: `data_wyroku`, `sygnatura`, `branza` (for query performance)
- Timestamps: `created_at`, `updated_at` (auto-managed)

### HTML Parsing Strategy
The scraper targets the `table.results` element with `tbody > tr.result_item` rows. Each row has 9 columns:
1. LP (numer_postanowienia) - used as unique identifier
2. DATA WYROKU (verdict date)
3. SYGNATURA (case signature)
4. SĄD (court) - not stored in DB
5. POWÓD (plaintiff)
6. POZWANY (defendant)
7. POSTANOWIENIE NIEDOZWOLONE (prohibited clause text)
8. DATA WPISU (entry date)
9. BRANŻA (industry)

### Pagination Implementation
The scraper:
1. Detects total pages by parsing `ul.paginate` links on the main page
2. Iterates through all pages using URL pattern: `index.php?page=N&view=` (N is 0-indexed)
3. For each entry, fetches detail page to get full text (not truncated)
4. Implements random delays (2-5 seconds) between pages and (0.5-1.5s) between detail page requests
5. Shows progress updates every 50 pages
6. Currently processes ~747 pages with ~10 entries per page = ~7470 detail pages

**Estimated runtime**: ~3-4 hours for full scrape (747 pages + 7470 detail pages with delays)

### Full Text Extraction
The main table shows truncated clause text. To get full text:
- Extracts detail page ID from `data-url` attribute in table row
- Fetches `wyszukiwanie.php?details=<ID>` for each entry
- Parses full text from `div.text > p` elements
- Adds 0.5-1.5s delay between detail requests

## Development Guidelines

### When Modifying the Scraper
- Test against live UOKiK site carefully to avoid rate limiting
- The HTML structure may change; verify selectors in `scraper.py` if no data is returned
- Date parsing supports formats: `DD.MM.YYYY`, `DD-MM-YYYY`, `YYYY-MM-DD`
- Always maintain duplicate detection via `numer_postanowienia`

### Database Changes
- SQLAlchemy migrations are not used; schema changes require manual table drops
- Uses PostgreSQL (not SQLite) - connection configured in `.env`
- Run `init_database.py` to create/verify table structure
- To reset: `DROP TABLE klauzule_niedozwolone;` then rerun `init_database.py`

### Configuration
- Environment variables go in `.env` (not committed)
- **DATABASE_URL**: PostgreSQL connection string in format: `postgresql://user:password@host:port/database`
- **init_database.py**: Standalone script to initialize database tables (creates if not exists)
- Request headers in `config.py` mimic Chrome/Linux to avoid bot detection

### Error Handling
- **Database connection**: Tested before scraping; script exits if connection fails
- **Network errors**: `fetch_page()` returns `None` (caught by requests.exceptions)
- **Date parsing failures**: Return `None` (allows incomplete records)
- **DB integrity errors**: Duplicates are logged and skipped, not raised
- **Entry errors**: Isolated per-entry; one failure doesn't stop the batch

## Project Limitations

### Known Incomplete Features
- **Zagadnienie field**: Not extracted from table (may require detail page scraping)
- **No tests**: No formal test suite (manual verification only)

### Implemented Features
- ✅ Full pagination support (~747 pages)
- ✅ PostgreSQL database with connection testing
- ✅ Rate limiting (respectful to server)
- ✅ Full text extraction from detail pages
- ✅ Incremental updates (update_new_entries.py)
- ✅ Progress bar with statistics
- ✅ Duplicate detection

### Future Enhancements May Need
- Extract `zagadnienie` field (requires detail page scraping)
- Add logging framework (currently uses print statements)
- Add retry logic for failed page requests
- Make rate limiting configurable via environment variables
- Add scheduling support (e.g., daily cron job for updates)

## Ingest webapp (fairpact.pl/ingest)
Portal decyzji jest za WAF (Imperva) i blokuje `scrape_decyzje.py` ("Request Rejected" po submit), więc decyzje dodaje się ręcznie przez `ingest_app.py` (FastAPI; systemd `uokik-ingest` na `127.0.0.1:8010`; nginx `location /ingest`). `decision_extractor.extract_decision(text)` zwraca pola decyzji + listę klauzul (Gemini `GEMINI_MODEL`). Zapis: `klauzule_niedozwolone` (`source='manual'`) + `decyzje_uokik`/`decyzje_pdfs`. Lokalny start: `.venv/bin/uvicorn ingest_app:app --host 127.0.0.1 --port 8010`. Zależności systemowe: tesseract-ocr(+pol), poppler-utils, google-chrome-stable, xvfb.
