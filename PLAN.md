# Project Plan — Barcelona Real Estate

A personal pipeline to surface real estate investment opportunities in Barcelona:
scrape listings → store raw → transform/compute metrics → serve via API → Streamlit dashboard.

See `CLAUDE.md` for architecture, stack, and conventions.

---

## Pipeline Overview

```
[Airflow — daily]
   → Python scrapers (habitaclia, idealista, fotocasa)
   → raw PostgreSQL (Docker dev → Supabase prod)
   → Scala Spark transform (normalize, dedupe, metrics)
   → clean PostgreSQL
   → Scala API → Streamlit dashboard
```

---

## Status

### Done ✅
- [x] **Foundation** — `Property` frozen dataclass (with `url` dedup key), `loader.py` (upsert on `(provider,url)`), `schema.sql`, env-driven `config.py` (Docker ↔ Supabase swap)
- [x] **Provider base class** — `provider.py` with shared anti-bot logic (retry/backoff, randomized delays + viewport, block detection, scroll-collect, context manager)
- [x] **habitaclia scraper** — implemented, verified against live HTML (910 pages detected, real Property extracted)
- [x] **idealista scraper** — implemented (selectors are best-effort guesses, marked `# TODO: verify`)
- [x] **fotocasa scraper** — implemented (layered fallback selectors, marked `# TODO: verify`)
- [x] **Unit tests** — 59 passing, fully offline (no browser/network)
- [x] **Orchestrator** — `etl/run_all.py` (per-provider isolation)
- [x] **Airflow DAG stub** — `dags/daily_etl.py`
- [x] **Live run verified** — fixed 2 real bugs: `_is_blocked()` false positive on `<meta robots>`, and habitaclia feature-index off-by-one (first `<strong>` is price)

### Remaining ⬜

| # | Task | Notes | Blocker |
|---|------|-------|---------|
| 1 | **Install Docker Desktop** | Required to run `database/docker-compose.yml` | Not installed on dev machine |
| 2 | **End-to-end DB load** | Bring up Postgres, apply `schema.sql`, run `run_all.py --only habitaclia`, confirm rows | Needs #1 |
| 3 | **Tune idealista/fotocasa selectors** | Verify every `# TODO: verify selector against live HTML` against real pages | Needs a live browser run per site |
| 4 | **DataDome strategy for idealista/fotocasa** | undetected-chromedriver alone insufficient; evaluate Playwright + playwright-stealth + residential proxies | — |
| 5 | **Add + enforce ruff/mypy** | Configured in `pyproject.toml` but not installed; add to Pipfile dev-packages and fix findings | — |
| 6 | **Scala Spark transformation layer** | normalize, dedupe, compute price/m², trends → clean table | Not started |
| 7 | **Scala API** | serve clean data (Play or http4s — TBD) | Needs #6 |
| 8 | **Streamlit dashboard** | consume API, investment views | Needs #7 |
| 9 | **Supabase migration** | swap `DATABASE_URL`; same schema | Future |
| 10 | **Integration tests** | planned after unit coverage is stable | Future |

---

## How to Run (dev)

```bash
# Tests
python -m pipenv run pytest -q

# Live URL-collection smoke test (opens real Chrome)
python -m pipenv run python scripts/live_smoke.py

# Live single-property extraction probe
python -m pipenv run python scripts/live_detail_probe.py

# Full scrape + load (needs Postgres up)
python -m pipenv run python etl/run_all.py --only habitaclia

# Database (after installing Docker Desktop)
docker compose -f database/docker-compose.yml up -d
```

> Env notes: Python 3.12 only (no 3.10); `setuptools<81` pinned in Pipfile to restore
> `distutils` for undetected-chromedriver. Deps live in a project-local pipenv venv.

---

## Per-Provider Scraping Status

| Provider | Anti-bot | Status |
|----------|----------|--------|
| habitaclia | none significant | ✅ works with undetected-chromedriver alone |
| idealista | **DataDome** | ⚠️ structure built; will need Playwright + proxies |
| fotocasa | **DataDome** | ⚠️ structure built; will need Playwright + proxies |
