# repogitactions

Projekt Django z kompletnym pipeline CI/CD opartym na GitHub Actions.

## Spis treści

- [Wymagania](#wymagania)
- [Uruchomienie lokalne](#uruchomienie-lokalne)
- [CI/CD](#cicd)
  - [Przegląd pipeline](#przegląd-pipeline)
  - [Joby i ich zadania](#joby-i-ich-zadania)
  - [Wymagane sekrety](#wymagane-sekrety)
  - [Triggery workflow](#triggery-workflow)
  - [Proces deployu](#proces-deployu)
  - [Debugowanie błędów](#debugowanie-błędów)
  - [Rollback](#rollback)

---

## Wymagania

- Python 3.12
- PostgreSQL 16
- Redis 7
- Docker (do lokalnego budowania obrazu)

## Uruchomienie lokalne

```bash
# 1. Sklonuj repozytorium
git clone https://github.com/Siajuu/repogitactions.git
cd repogitactions

# 2. Utwórz i aktywuj środowisko wirtualne
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Zainstaluj zależności
pip install -r requirements.txt

# 4. Ustaw zmienne środowiskowe
export SECRET_KEY="twoj-lokalny-klucz"
export DB_ENGINE="django.db.backends.sqlite3"   # SQLite lokalnie

# 5. Wykonaj migracje i uruchom serwer
python manage.py migrate
python manage.py runserver
```

---

## CI/CD

### Przegląd pipeline

Pipeline uruchamia się automatycznie przy każdym pushu i pull requeście do gałęzi `main`. Składa się z pięciu równoległych jobów, z których `deploy` czeka na pomyślne zakończenie pozostałych czterech.

```
push / pull_request
        │
        ├── test          (PostgreSQL + testy jednostkowe)
        ├── lint          (flake8 + black + isort)
        ├── security      (bandit + pip-audit)
        ├── celery-tests  (Redis + worker Celery + testy async)
        │
        └── deploy ──── (tylko main, po przejściu wszystkich powyższych)
                         buduje obraz Docker → pushuje do GHCR
```

Joby `test`, `lint`, `security` i `celery-tests` działają **równolegle** — nie czekają na siebie nawzajem, co skraca łączny czas pipeline.

Workflow używa mechanizmu `concurrency` — jeśli nowy push trafi na gałąź `main` zanim poprzedni pipeline zdąży się skończyć, poprzedni zostaje **automatycznie anulowany**. Zapobiega to kolejkowaniu się wielu równoczesnych uruchomień.

---

### Joby i ich zadania

#### `test`

Uruchamia testy jednostkowe Django na prawdziwej bazie PostgreSQL.

| Co robi | Szczegóły |
|---|---|
| Baza danych | PostgreSQL 16 jako Docker service |
| Testy | `core.tests.SanityCheckTests` |
| Cache | pip cache oparty na `requirements.txt` |

#### `lint`

Sprawdza jakość i formatowanie kodu.

| Narzędzie | Co sprawdza |
|---|---|
| `flake8` | Zgodność z PEP8, błędy składniowe |
| `black --check` | Formatowanie kodu |
| `isort --check` | Kolejność importów |

Błąd w którymkolwiek z tych kroków blokuje merge pull requesta.

#### `security`

Statyczna analiza bezpieczeństwa kodu i zależności.

| Narzędzie | Co sprawdza |
|---|---|
| `bandit -ll` | Podatności w kodzie (severity Medium i wyżej) |
| `pip-audit` | Znane CVE w zależnościach z `requirements.txt` |

#### `celery-tests`

Testy integracyjne tasków asynchronicznych Celery.

| Co robi | Szczegóły |
|---|---|
| Broker | Redis 7 jako Docker service |
| Worker | Uruchamiany w tle z `--pool=solo` |
| Testy | `core.tests.CeleryTaskTests` |
| Logi workera | Zawsze dostępne w kroku "Logi workera Celery" |

#### `deploy`

Buduje i publikuje obraz Docker do GitHub Container Registry.

| Co robi | Szczegóły |
|---|---|
| Trigger | Tylko push do `main` (nie PR) |
| Warunek | Musi przejść: `test`, `lint`, `security`, `celery-tests` |
| Registry | `ghcr.io/siajuu/repogitactions` |
| Tagi obrazu | `:latest` oraz `:<git-sha>` |
| Autoryzacja | `GITHUB_TOKEN` (automatyczny, bez konfiguracji) |

---

### Wymagane sekrety

Sekrety konfiguruje się w: **Settings → Secrets and variables → Actions → New repository secret**

| Sekret | Wymagany przez | Opis |
|---|---|---|
| `SECRET_KEY` | `test`, `celery-tests` | Django SECRET_KEY dla środowiska CI. Wygeneruj losowy ciąg min. 50 znaków. |

> **Uwaga:** `GITHUB_TOKEN` jest generowany automatycznie przez GitHub Actions — nie trzeba go ręcznie konfigurować.

#### Sekrety do przyszłego deployu SSH

Gdy skonfigurujesz serwer docelowy, dodaj dodatkowo:

| Sekret | Opis |
|---|---|
| `DEPLOY_HOST` | Adres IP lub domena serwera |
| `DEPLOY_USER` | Nazwa użytkownika SSH |
| `DEPLOY_SSH_KEY` | Prywatny klucz SSH (zawartość pliku `~/.ssh/id_rsa`) |

#### Jak wygenerować SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

### Triggery workflow

Workflow uruchamia się gdy:

- Zrobisz `git push` do gałęzi `main`
- Otworzysz lub zaktualizujesz Pull Request do `main`

Workflow **nie uruchamia się** gdy zmienisz tylko:

- Pliki `*.md` (dokumentacja)
- Folder `docs/`
- Plik `.gitignore`

Dzięki temu poprawki w dokumentacji nie generują niepotrzebnych uruchomień pipeline.

---

### Proces deployu

Deploy wykonuje się automatycznie po każdym mergu do `main`, bez żadnej ręcznej interwencji.

**Kroki:**

1. Wszystkie cztery joby (`test`, `lint`, `security`, `celery-tests`) muszą zakończyć się sukcesem
2. Job `deploy` buduje obraz Docker z `Dockerfile` w katalogu głównym
3. Obraz jest pushowany do GHCR z dwoma tagami:
   - `:latest` — zawsze wskazuje na najnowszy build
   - `:<git-sha>` — unikalny tag dla każdego commita, np. `:a1b2c3d`
4. Obraz jest dostępny pod adresem: `ghcr.io/siajuu/repogitactions`

**Sprawdzenie dostępności obrazu:**

```bash
docker pull ghcr.io/siajuu/repogitactions:latest
docker run -p 8000:8000 ghcr.io/siajuu/repogitactions:latest
```

---

### Debugowanie błędów

#### Job `test` lub `celery-tests` kończy się błędem

1. Wejdź w zakładkę **Actions**, kliknij w nieudane uruchomienie
2. Kliknij w job który zawiódł
3. Rozwiń krok który pokazuje czerwoną ✗
4. Przeczytaj pełny traceback błędu

Najczęstsze przyczyny:

| Błąd | Przyczyna | Rozwiązanie |
|---|---|---|
| `RuntimeError: Retry limit exceeded` | `CeleryTaskTests` odpalają się bez Redis | Sprawdź czy uruchamiasz `core.tests.SanityCheckTests` w jobie `test`, a `core.tests.CeleryTaskTests` tylko w `celery-tests` |
| `connection refused :5432` | PostgreSQL nie zdążył wystartować | Zwiększ `--health-retries` w konfiguracji service |
| `ModuleNotFoundError` | Brakuje pakietu w `requirements.txt` | Dodaj pakiet i zaktualizuj plik |

#### Job `lint` kończy się błędem

```bash
# Uruchom lokalnie przed pushem:
flake8 .
black --check .
isort --check .

# Automatyczne naprawienie formatowania:
black .
isort .
```

#### Job `security` kończy się błędem

- **bandit** — otwórz log i znajdź linię z `Severity: MEDIUM` lub `HIGH`. Popraw kod lub dodaj komentarz `# nosec BXXX` jeśli to false positive
- **pip-audit** — zaktualizuj podatną zależność do bezpiecznej wersji: `pip install pakiet==nowa_wersja`, zaktualizuj `requirements.txt`

#### Job `deploy` kończy się błędem przy budowaniu obrazu

```bash
# Zbuduj obraz lokalnie żeby zobaczyć błąd:
docker build -t test-build .
```

Najczęstsza przyczyna: błąd w `Dockerfile` lub brakujący plik kopiowany przez `COPY`.

#### Cache pip nie działa

Sprawdź w logach kroku "Instalacja Pythona 3.12" czy pojawia się `Cache hit` lub `Cache miss`. Pierwsze uruchomienie zawsze daje `Cache miss` — cache pojawia się od drugiego uruchomienia. Jeśli cache nigdy nie działa, sprawdź czy plik `requirements.txt` istnieje w głównym katalogu repo.

---

### Rollback

Każdy build jest tagowany unikalnym SHA commita. Żeby wrócić do poprzedniej wersji:

```bash
# 1. Znajdź SHA poprzedniego działającego commita
git log --oneline

# 2. Uruchom poprzednią wersję obrazu
docker pull ghcr.io/siajuu/repogitactions:<poprzedni-sha>
docker stop django-app
docker run -d --name django-app -p 8000:8000 \
  ghcr.io/siajuu/repogitactions:<poprzedni-sha>
```

Wszystkie dostępne wersje obrazów widoczne są w zakładce **Packages** na stronie profilu GitHub.
