# Rejestr Klauzul Scraper

Web scraper do pobierania wpisów klauzul niedozwolonych z rejestru UOKiK (Urząd Ochrony Konkurencji i Konsumentów).

## Opis

Ten projekt pobiera dane z [Rejestru Klauzul Niedozwolonych UOKiK](https://rejestr.uokik.gov.pl) i zapisuje je w bazie danych SQLite. Dane obejmują:

- Data wyroku
- Sygnatura wyroku
- Postanowienie niedozwolone (treść klauzuli)
- Branża
- Nazwa powoda
- Nazwa pozwanego
- Data wpisu
- Zagadnienie prawne

## Wymagania

- Python 3.12+
- uv (package manager)

## Instalacja

1. Sklonuj repozytorium:
```bash
git clone <repository-url>
cd rejestr_klauzul_scraper
```

2. Zainstaluj zależności używając uv:
```bash
uv sync
```

3. Skonfiguruj połączenie z bazą danych w pliku `.env`:
```bash
cp .env.example .env
# Edytuj .env i ustaw DATABASE_URL
```

4. Zainicjalizuj bazę danych:
```bash
uv run init_database.py
```

## Użycie

### Pełne scrapowanie (pierwsze uruchomienie)

Uruchom scraper:
```bash
uv run main.py
```

Scraper automatycznie:
1. Zainicjalizuje bazę danych PostgreSQL (jeśli tabele nie istnieją)
2. Pobierze dane z wszystkich stron rejestru UOKiK (~747 stron)
3. Zapisze wpisy w bazie danych
4. Wyświetli podsumowanie operacji

**Uwaga**: Scraper pobiera pełną treść klauzul z podstron szczegółów (~7470 dodatkowych żądań). Używa opóźnień 2-5 sekund między stronami i 0.5-1.5s między szczegółami. Pełne scrapowanie zajmie około **3-4 godziny**.

### Aktualizacja inkrementalna (pobieranie nowych wpisów)

Po pierwszym pełnym scrapowaniu, możesz pobierać tylko nowe wpisy:
```bash
uv run update_new_entries.py
```

Skrypt aktualizacji:
1. Sprawdza najwyższy numer wpisu w bazie danych
2. Pobiera tylko nowsze wpisy z rejestru UOKiK (domyślnie sprawdza pierwsze 5 stron)
3. Zapisuje nowe wpisy do bazy
4. Wyświetla podsumowanie

**Zaleta**: Znacznie szybsze (~1-2 minuty) - pobiera tylko nowe dane zamiast wszystkich ~7470 wpisów.

## Struktura projektu

```
rejestr_klauzul_scraper/
├── main.py              # Główny skrypt orkiestrujący działanie
├── scraper.py           # Logika scrapowania strony UOKiK
├── models.py            # Modele bazy danych (SQLAlchemy)
├── database.py          # Połączenie z bazą danych i inicjalizacja
├── config.py            # Konfiguracja (URL, timeout, headers)
├── pyproject.toml       # Konfiguracja projektu i zależności (uv)
└── README.md            # Ten plik
```

## Konfiguracja

Konfigurację ustaw w pliku `.env`:

```env
DATABASE_URL=postgresql://user:password@host:port/database_name
```

## Baza danych

Dane są zapisywane w bazie SQLite w tabeli `klauzule_niedozwolone` z następującymi polami:

- `id` - Klucz główny
- `numer_postanowienia` - Unikalny numer postanowienia
- `data_wyroku` - Data wydania wyroku
- `sygnatura` - Sygnatura wyroku
- `postanowienie_niedozwolone` - Treść niedozwolonej klauzuli
- `branza` - Branża
- `powod` - Nazwa powoda
- `pozwany` - Nazwa pozwanego
- `data_wpisu` - Data wpisu do rejestru
- `zagadnienie` - Zagadnienie prawne
- `created_at` - Data utworzenia rekordu
- `updated_at` - Data aktualizacji rekordu

## Uwagi

Scraper jest skonfigurowany do pracy z aktualną strukturą strony UOKiK. W razie zmian w strukturze HTML strony, może być konieczna aktualizacja funkcji parsujących w `scraper.py`.

## Licencja

MIT
