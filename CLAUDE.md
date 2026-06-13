# Barcelona Real Estate — Project Guide

## What This Project Does
An automated pipeline that scrapes Barcelona real estate listings from multiple providers, transforms and computes investment metrics, and exposes the data through an API and Streamlit dashboard for identifying investment opportunities.

## Architecture

```
[Airflow — daily trigger]
        |
        v
Python Scrapers (habitaclia, Idealista, Fotocasa)
        |
        v
Raw PostgreSQL (Docker local / Supabase prod)
        |
        v
Scala Spark Transformation (normalize, deduplicate, compute metrics)
        |
        v
Clean PostgreSQL (Docker local / Supabase prod)
        |
        v
Scala API  -->  Streamlit Dashboard
```

## Stack

| Layer | Technology |
|---|---|
| Extraction | Python 3.10, Selenium, undetected-chromedriver, BeautifulSoup4 |
| Orchestration | Apache Airflow |
| Transformation | Scala + Apache Spark |
| Storage (dev) | PostgreSQL via Docker |
| Storage (prod) | Supabase |
| API | Scala (Play Framework or http4s — TBD) |
| Dashboard | Streamlit |
| Python quality | ruff (lint+format), mypy (types) |
| Scala quality | scalafmt (format), scalastyle (lint) |
| Testing | pytest (Python), ScalaTest (Scala) |

## Directory Structure

```
barcelona-real-state/
├── extraction/                    # Python scraping layer
│   ├── base_provider.py           # Abstract base class for all scrapers
│   └── providers/
│       ├── habitaclia.py
│       ├── idealista.py
│       └── fotocasa.py
├── components/
│   └── etl_components/            # Shared Python utilities + models
│       ├── property.py
│       ├── provider.py
│       ├── utils.py
│       └── __init__.py
├── transformation/                # Scala Spark jobs
│   ├── build.sbt
│   └── src/main/scala/transformation/
├── api/                           # Scala REST API
│   ├── build.sbt
│   └── src/main/scala/api/
├── dashboard/                     # Streamlit frontend
│   └── app.py
├── dags/                          # Airflow DAGs
│   └── daily_etl.py
├── database/
│   ├── docker-compose.yml
│   └── migrations/
├── tests/
│   ├── unit/
│   │   ├── python/
│   │   └── scala/
│   └── integration/
├── .scalafmt.conf
├── pyproject.toml                 # ruff + mypy config
└── Pipfile
```

## Data Providers

Three providers are planned. Each gets its own scraper that extends the base provider interface:
- **habitaclia** — partially built (extraction layer in progress)
- **Idealista** — not started
- **Fotocasa** — not started

The `Property` dataclass is the shared output contract for all scrapers:
`price`, `name`, `size`, `rooms`, `bathrooms`, `squere_meter_price`, `location`, `description`, `prop_type`, `provider`

## Anti-Bot Defenses — Critical Context

The biggest current pain point is bypassing anti-bot detection. Follow these rules when writing scraper code:

- Always use `undetected_chromedriver` (`uc.Chrome()`), never plain `selenium.webdriver.Chrome()`
- Never use fixed `time.sleep(N)` — always use `random.uniform(min, max)` with realistic human ranges
- Randomize viewport size and user agent per session
- Add retry logic with exponential backoff on detection/block (HTTP 403, CAPTCHA elements)
- Avoid sequential predictable patterns — shuffle URL order before iterating
- Never run headless unless explicitly tested to bypass detection for that provider
- If a provider proves impossible to scrape reliably, consider Playwright + playwright-stealth as an alternative to Selenium

## DB Connection Pattern

The DB connection must be environment-aware — local Docker vs Supabase. Always read from environment variables, never hardcode credentials:

```python
import os
DB_URL = os.environ["DATABASE_URL"]  # set per environment
```

Local dev: `postgresql://admin:admin1234@localhost:5432/barcelona-real-state`
Prod: Supabase connection string from env

## Code Quality Rules

**Python:**
- Type hints on all function signatures
- `ruff` for linting and formatting (`ruff check`, `ruff format`)
- `mypy` for type checking
- No `print()` in production code — use `logging`

**Scala:**
- `scalafmt` formatting enforced before commit
- `scalastyle` linting
- Prefer immutable data (`val`, `case class`)
- Spark jobs should be pure functions where possible for testability

## Testing

- Unit tests are required for new code
- Python: `pytest` in `tests/unit/python/`
- Scala: `ScalaTest` in `tests/unit/scala/`
- Mock the browser/HTTP layer in scraper tests — never hit live sites in unit tests
- Integration tests are planned for the future; design code to support them

## User Context

- Advanced Python developer
- Learning Scala — explain Scala patterns and idioms when introducing new ones, especially Spark-specific patterns
- Does not need Python explanations
- Prefers code to be structured for testability from the start
