# Rejestr Klauzul Scraper

Web scraper do pobierania wpisów klauzul niedozwolonych z rejestru UOKiK (Urząd Ochrony Konkurencji i Konsumentów).

## Opis

Ten projekt obsługuje **dwa źródła danych**:

1. **Stary rejestr** (`https://rejestr.uokik.gov.pl`) — oryginalna strona z klauzulami niedozwolonymi w formacie tabeli HTML. Obecnie nie jest już aktualizowana.
2. **Nowa baza decyzji** (`https://decyzje.uokik.gov.pl/bp/dec_prez.nsf`) — strona Urzędu z decyzjami Prezesa UOKiK, w tym decyzjami w sprawach klauzul niedozwolonych publikowanych od 2017 roku w formacie PDF.

Dane są zapisywane w bazie SQLite/PostgreSQL.

## Wymagania

- Python 3.12+
- uv (package manager)
- **Google Chrome** (wymagane przez undetected-chromedriver do pobierania danych z nowej strony)
- *(opcjonalnie)* **Tesseract OCR** + **Poppler** — jeśli chcesz parsować skany PDF (`apt install tesseract-ocr tesseract-ocr-pol poppler-utils` na Ubuntu)
- *(opcjonalnie)* **Ollama** — jeśli chcesz używać lokalnego modelu LLM do ekstrakcji klauzul

## Instalacja

1. Sklonuj repozytorium i zainstaluj zależności Python:
```bash
uv sync
```

2. Skonfiguruj połączenie z bazą danych oraz parser w pliku `.env`:
```bash
cp .env.example .env
# Edytuj .env — ustaw DATABASE_URL, wybierz backend parsera, opcjonalnie podaj klucze API
```

Przykładowy `.env`:
```bash
DATABASE_URL=postgresql://username:password@localhost:5432/klauzule

# Backend parsera: rule_based | ollama | gemini | openai | claude
PARSER_BACKEND=rule_based

# Ollama (lokalny LLM)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# Klucze API (wymagane tylko dla wybranych backendów)
GEMINI_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here
CLAUDE_API_KEY=your-key-here
```

3. Zainicjalizuj bazę danych:
```bash
uv run init_database.py
```

## Użycie

### Stary rejestr (rejestr.uokik.gov.pl)

#### Pełne scrapowanie (pierwsze uruchomienie)
```bash
uv run main.py
```

#### Aktualizacja inkrementalna (pobieranie nowych wpisów)
```bash
uv run update_new_entries.py
```

### Nowa baza decyzji (decyzje.uokik.gov.pl)

#### Scrapowanie metadanych decyzji
```bash
# Wszystkie lata (2017-2026)
uv run scrape_decyzje.py --all

# Wybrane lata
uv run scrape_decyzje.py --years 2024,2025

# Pojedynczy rok
uv run scrape_decyzje.py --years 2024
```

Scraper otwiera prawdziwą przeglądarkę Chrome (przez undetected-chromedriver), przechodzi przez formularz Lotus Notes, wypełnia kryteria wyszukiwania (Klauzule niedozwolone + rok), a następnie zapisuje metadane decyzji do bazy.

#### Pobieranie plików PDF
```bash
# Wszystkie niepobrane decyzje
uv run download_pdfs.py

# Wybrane lata
uv run download_pdfs.py --years 2024,2025

# Inny katalog wyjściowy
uv run download_pdfs.py --output-dir ./data/pdfs --years 2024
```

PDF-y są pobierane przez przeglądarkę (XMLHttpRequest) z pominięciem WAF, i zapisywane w strukturze: `pdfs/<rok>/<nazwa_pliku>.pdf`

#### Parsowanie PDF i ekstrakcja klauzul

Parser wspiera **cztery backendy ekstrakcji** — wybierasz jeden w `.env` (`PARSER_BACKEND`):

| Backend | Wymagania | Opis |
|---------|-----------|------|
| `rule_based` | brak | Domyślny, w pełni offline — heurystyki języka prawnego (bez API, bez kluczy). |
| `ollama` | Ollama lokalnie | Lokalny model LLM (np. `llama3.1`, `qwen2.5`). Darmowy, prywatny, działa offline. |
| `gemini` | `GEMINI_API_KEY` | Google Gemini 1.5 Flash. Szybki i tani. |
| `openai` | `OPENAI_API_KEY` | OpenAI GPT-4o-mini. Wysoka jakość, kosztowny przy dużej liczbie PDF. |
| `claude` | `CLAUDE_API_KEY` | Anthropic Claude 3 Haiku. Dobra jakość, średni koszt. |

```bash
# Podgląd (bez zapisywania do bazy)
uv run parse_pdfs.py --dry-run --years 2024

# Parsowanie + zapisanie wyciągniętych klauzul do tabeli klauzule_niedozwolone
uv run parse_pdfs.py --save-to-db --years 2024

# Wszystkie lata
uv run parse_pdfs.py --save-to-db
```

**OCR (skany PDF)** — jeśli PDF jest skanem obrazu (brak warstwy tekstu), parser automatycznie próbuje OCR (wymagane `pdf2image` + `pytesseract` + `poppler` system-wide). Jeśli OCR jest niedostępny, decyzja zostanie oznaczona jako `blad`.

**Przykład z Ollama (lokalny LLM):**
```bash
# 1. Zainstaluj Ollama: https://ollama.com
# 2. Pobierz model: ollama pull llama3.1
# 3. Upewnij się że serwer działa: ollama serve
# 4. W .env ustaw: PARSER_BACKEND=ollama
# 5. Parsuj:
uv run parse_pdfs.py --save-to-db --years 2024
```

#### Aktualizacja inkrementalna
```bash
uv run update_decyzje.py --years 2024,2025
```

### Pipeline kompletny (nowe decyzje)

```bash
# 1. Pobierz metadane
uv run scrape_decyzje.py --all

# 2. Pobierz PDF-y
uv run download_pdfs.py

# 3. Wyciągnij klauzule i zapisz do bazy
uv run parse_pdfs.py --save-to-db
```

## Struktura projektu

```
uokik-fetch/
├── main.py                    # Główny skrypt dla starego rejestru
├── scraper.py                 # Scraper starego rejestru
├── update_new_entries.py      # Aktualizacja inkrementalna starego rejestru
├── init_database.py           # Inicjalizacja bazy danych
│
├── scrape_decyzje.py          # CLI: scrapowanie nowej bazy decyzji
├── scraper_decyzje.py         # Scraper nowej strony (undetected-chromedriver)
├── download_pdfs.py           # CLI: pobieranie PDF-ów
├── pdf_downloader.py          # Downloader PDF przez browser XHR
├── parse_pdfs.py              # CLI: parsowanie PDF
├── pdf_parser.py              # Parser PDF (heurystyki + OCR + LLM)
├── ocr_extractor.py           # OCR dla skanów PDF (pdf2image + pytesseract)
├── llm_extractor.py           # LLM integrations (Ollama, Gemini, OpenAI, Claude)
├── update_decyzje.py          # Aktualizacja inkrementalna nowej strony
│
├── webbridge_client.py        # Klient Kimi WebBridge (fallback)
├── models.py                  # Modele SQLAlchemy (stary + nowe tabele)
├── database.py                # Połączenie z bazą
├── config.py                  # Konfiguracja URL-i, parsera, API keys
├── pyproject.toml             # Zależności projektu
└── README.md                  # Ten plik
```

## Baza danych

### Tabela `klauzule_niedozwolone` (stary rejestr)
- `id` — klucz główny
- `numer_postanowienia` — unikalny numer wpisu
- `data_wyroku` — data wydania wyroku
- `sygnatura` — sygnatura wyroku
- `postanowienie_niedozwolone` — treść klauzuli
- `branza` — branża
- `powod` — nazwa powoda
- `pozwany` — nazwa pozwanego
- `data_wpisu` — data wpisu do rejestru
- `zagadnienie` — zagadnienie prawne
- `source` — źródło: `stary_rejestr` lub `decyzje_uokik`
- `created_at`, `updated_at`

### Tabela `decyzje_uokik` (nowa strona)
- `id` — klucz główny
- `numer_decyzji` — np. RGD-2/2026
- `data_wydania` — data wydania decyzji
- `sygnatura_akt` — sygnatura akt
- `uczestnicy_postepowania` — nazwa firmy
- `rodzaj_praktyki` — zawsze "Klauzule niedozwolone"
- `kara` — Tak/Nie
- `branza` — branża
- `region` — region
- `odwolanie_do_sadu` — Tak/Nie
- `orzecznictwo` — orzecznictwo
- `unid` — identyfikator Lotus Notes
- `pdf_url` — link do PDF
- `pdf_filename` — nazwa pliku PDF
- `pdf_local_path` — lokalna ścieżka po pobraniu
- `status_parsowania` — `nowe` / `pobrane` / `sparsowane` / `blad`
- `extracted_klauzula` — wyciągnięta treść klauzuli z PDF
- `rok` — rok decyzji
- `created_at`, `updated_at`

### Tabela `decyzje_pdfs`
- `id` — klucz główny
- `decyzja_id` — FK → decyzje_uokik.id
- `pdf_url` — URL pliku
- `local_path` — lokalna ścieżka
- `file_size` — rozmiar w bajtach
- `download_date` — data pobrania

## Uwagi techniczne

### Ochrona WAF (TSPD)

Strona `decyzje.uokik.gov.pl` używa **Imperva TSPD** — zaawansowanego firewalla, który blokuje zwykłe żądania HTTP i wymaga wykonania JavaScript challenge w przeglądarce. Z tego powodu:

- Scraper używa **undetected-chromedriver** (prawdziwa przeglądarka Chrome)
- PDF-y są pobierane przez **XMLHttpRequest w przeglądarce** (nie przez requests)
- Pierwsze uruchomienie może otworzyć okno Chrome na kilka sekund

### Wydajność

- Scrapowanie metadanych: ~30-60 sekund na rok (zależnie od liczby decyzji)
- Pobieranie PDF: ~5-15 sekund na plik (zależnie od rozmiaru)
- Parsowanie PDF: ~1-3 sekundy na plik

### Znane ograniczenia

- **OCR**: Wymaga zainstalowania Tesseract + Poppler w systemie operacyjnym. Bez nich skany PDF zostaną oznaczone jako `blad`.
- **LLM (cloud)**: Kosztowne przy dużej liczbie PDF-ów. Zalecane testowanie na małej próbie (`--dry-run`) przed pełnym uruchomieniem.
- **LLM (Ollama)**: Wymaga uruchomionego serwera Ollama i pobranego modelu. Jakość zależy od modelu — `llama3.1` i `qwen2.5` dają dobre wyniki w języku polskim.
- **Rate limiting**: Zbyt częste uruchamianie scrapera może spowodować tymczasowe zablokowanie IP przez TSPD. Zalecane jest użycie opóźnień (domyślnie 2–5 s między żądaniami) i nie częściej niż raz dziennie.

## Licencja

MIT
