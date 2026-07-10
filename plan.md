# Plan: Rozszerzenie scrapera UOKiK o nową bazę decyzji (decyzje.uokik.gov.pl)

## Stan obecny

Aplikacja pobiera klauzule niedozwolone ze starej strony `rejestr.uokik.gov.pl` i zapisuje je w bazie SQLite/PostgreSQL w tabeli `klauzule_niedozwolone`.

Od kilku lat wyroki są publikowane przez sąd na nowej stronie: `https://decyzje.uokik.gov.pl/bp/dec_prez.nsf`.

## Zbadana struktura nowej strony

### Formularz wyszukiwania (Lotus Notes/Domino)
- URL: `https://decyzje.uokik.gov.pl/bp/dec_prez.nsf/UOKiK?OpenForm&Seq=1`
- Method: POST, form name: `_UOKiK`
- Hidden field: `__Click=0`
- Select `PraktykaPyt` = `"Klauzule niedozwolone"` (tekst jako value)
- Select `dataRR` = rok (np. `"2017"`)
- Przycisk submit: JS-triggered `input[type=button].btn.btn-default`
- Wyniki: tabela z linkami do decyzji

### Lista decyzji (wyniki wyszukiwania)
- Link do decyzji: `https://decyzje.uokik.gov.pl/bp/dec_prez.nsf/1/<UNID>?editDocument&act=Decyzja`
- Link do przedsiębiorcy: `https://decyzje.uokik.gov.pl/bp//dec_prez.nsf/UOKIK?openform&przeds=<UNID>&act=decyzjekontr`
- Brak widocznej paginacji (może być wewnętrzna w Lotus Notes)

### Strona szczegółów decyzji
- Tabela z polami:
  - Numer decyzji (np. RGD-2/2026)
  - Data wydania decyzji (YYYY-MM-DD)
  - Sygnatura akt
  - Uczestnicy postępowania
  - Rodzaj praktyki (zawsze "Klauzule niedozwolone")
  - Kara (Tak/Nie)
  - Branża
  - Region
  - Decyzja → link do PDF
  - Odwołanie do sądu (Tak/Nie)
  - Orzecznictwo
- Link do PDF: `https://decyzje.uokik.gov.pl/bp/dec_prez.nsf/<dbpath>/<UNID>/$FILE/<filename>.pdf`

## Etapy implementacji

### Stage 1 — Rozszerzenie modelu bazy danych
**Cel:** Dodać nową tabelę `decyzje_uokik` z polami dopasowanymi do nowej strony, plus tabelę `decyzje_pdf` do śledzenia pobranych plików.

Nowa tabela `decyzje_uokik`:
- `id` (PK)
- `numer_decyzji` (String, unique)
- `data_wydania` (Date)
- `sygnatura_akt` (String)
- `uczestnicy_postepowania` (Text)
- `rodzaj_praktyki` (String)
- `kara` (String)
- `branza` (String)
- `region` (String)
- `odwolanie_do_sadu` (String)
- `orzecznictwo` (Text)
- `pdf_url` (String)
- `pdf_filename` (String)
- `pdf_local_path` (String)
- `status_parsowania` (String: 'nowe', 'pobrane', 'sparsowane', 'blad')
- `extracted_klauzula` (Text) — wyciągnięta treść klauzuli z PDF
- `created_at`, `updated_at`

Tabela `decyzje_pdf`:
- `id` (PK)
- `decyzja_id` (FK → decyzje_uokik.id)
- `pdf_url` (String)
- `local_path` (String)
- `file_size` (Integer)
- `download_date` (DateTime)
- `created_at`

### Stage 2 — Nowy scraper dla decyzje.uokik.gov.pl
**Cel:** Moduł `scraper_decyzje.py` który:
1. Wysyła formularz POST z `PraktykaPyt=Klauzule niedozwolone` i `dataRR=<rok>` dla lat 2017–2026
2. Parsuje wyniki wyszukiwania (tabela z linkami)
3. Odwiedza stronę szczegółów każdej decyzji
4. Ekstrahuje metadane z tabeli
5. Zapisuje metadane do bazy (tabela `decyzje_uokik`)

### Stage 3 — Downloader PDF
**Cel:** Moduł `pdf_downloader.py` który:
1. Pobiera pliki PDF ze wszystkich decyzji o statusie 'nowe'
2. Zapisuje w dedykowanym folderze `pdfs/<rok>/`
3. Aktualizuje status w bazie na 'pobrane'
4. Używa opóźnień 1-3s między pobraniami

### Stage 4 — Parser PDF / AI ekstrakcja
**Cel:** Moduł `pdf_parser.py` który:
1. Przegląda pobrane pliki PDF (status 'pobrane')
2. Używa LLM/AI do ekstrakcji treści klauzul niedozwolonych z dokumentów PDF
3. Mapuje wyniki na format istniejącej tabeli `klauzule_niedozwolone`:
   - `numer_postanowienia` → numer decyzji
   - `data_wyroku` → data wydania decyzji
   - `sygnatura` → sygnatura akt
   - `postanowienie_niedozwolone` → wyciągnięta klauzula z PDF
   - `branza` → branża
   - `powod` → UOKiK (Prezes UOKiK)
   - `pozwany` → uczestnicy postępowania
   - `data_wpisu` → data wydania decyzji
   - `zagadnienie` → rodzaj praktyki
4. Zapisuje wyciągnięte dane do tabeli `klauzule_niedozwolone` (lub oznacza do weryfikacji)
5. Aktualizuje status na 'sparsowane'

### Stage 5 — Integracja i CLI
**Cel:** Zmodyfikować `main.py` i dodać nowe skrypty CLI:
- `main.py` — zachować istniejącą logikę, dodać argumenty `--source` (stary/nowy/oba)
- `scrape_decyzje.py` — główny skrypt do scrapowania nowej strony
- `download_pdfs.py` — skrypt do pobierania PDF
- `parse_pdfs.py` — skrypt do parsowania PDF przez AI
- `update_decyzje.py` — inkrementalny updater dla nowej strony

## Pliki do utworzenia/modyfikacji

### Nowe pliki:
- `scraper_decyzje.py` — scraper nowej strony
- `pdf_downloader.py` — pobieranie PDF
- `pdf_parser.py` — parser PDF (AI)
- `scrape_decyzje.py` — CLI do scrapowania decyzji
- `download_pdfs.py` — CLI do pobierania PDF
- `parse_pdfs.py` — CLI do parsowania PDF
- `update_decyzje.py` — inkrementalny updater

### Modyfikowane pliki:
- `models.py` — rozszerzenie o nowe modele
- `database.py` — ewentualne zmiany
- `config.py` — dodanie nowych URL-i i ścieżek
- `main.py` — dodanie argumentów CLI
- `pyproject.toml` — nowe zależności (PyPDF2, pdfplumber, openai itp.)

## Podział na subagentów

| Subagent | Zadanie | Typ |
|----------|---------|-----|
| DB_Modeler | Rozszerzenie models.py o nowe tabele | coder |
| Scraper_Decyzje | Implementacja scraper_decyzje.py + scrape_decyzje.py | coder |
| PDF_Downloader | Implementacja pdf_downloader.py + download_pdfs.py | coder |
| PDF_Parser | Implementacja pdf_parser.py + parse_pdfs.py | coder |
| Integrator | Modyfikacja config.py, main.py, update_decyzje.py, pyproject.toml | coder |

Uwaga: Stage 1 (DB) musi być gotowy przed Stage 2-4. Stage 5 (integracja) po wszystkich.
