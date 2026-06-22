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
- [x] **idealista scraper** — implemented (selectors are best-effort guesses, marked `# TODO: verify`) — **NOT yet production-verified, see Task P-IDEALISTA**
- [x] **fotocasa scraper** — implemented (layered fallback selectors, marked `# TODO: verify`) — **NOT yet production-verified, see Task P-FOTOCASA**
- [x] **Unit tests** — 59 passing, fully offline (no browser/network)
- [x] **Orchestrator** — `etl/run_all.py` (per-provider isolation)
- [x] **Airflow DAG stub** — `dags/daily_etl.py`
- [x] **Live run verified (habitaclia only)** — fixed 2 real bugs: `_is_blocked()` false positive on `<meta robots>`, and habitaclia feature-index off-by-one (first `<strong>` is price)
- [x] **Docker infrastructure** — Postgres 16 + pgAdmin running via `docker-compose.yml`; pgAdmin at `http://localhost:5050`
- [x] **End-to-end DB load** — schema applied, 9 real habitaclia rows in `properties`; upsert idempotency confirmed (zero duplicate `(provider,url)` pairs); `--limit` flag added for bounded smoke runs

---

## How to Read This Plan

Every task below is written to be **self-contained and executable** without re-deriving context.
Each carries:

- **Goal** — the single outcome that means "done".
- **Steps** — concrete, ordered actions (file-level where possible).
- **Files** — what gets created or touched.
- **Acceptance criteria** — objective checks; if they all pass, the task is closed.
- **Depends on** — hard blockers.

Provider onboarding (Tasks **P-IDEALISTA** and **P-FOTOCASA**) is special: each provider is
driven through a repeating **CODE → TEST → INTEGRATION → SECURITY → repeat** loop and is only
"fully built" when an entire loop pass produces **zero** new findings. That loop is defined once
in **§ The Provider Onboarding Loop** and referenced by both provider tasks.

---

## Remaining — Index

| # | Task | Theme | Depends on |
|---|------|-------|-----------|
| 1 | ~~Install Docker Desktop~~ ✅ | Infra | — |
| 2 | ~~End-to-end DB load (habitaclia)~~ ✅ | Infra | 1 |
| 3 | ~~Add + enforce ruff / mypy~~ ✅ | Quality gate | — |
| P-IDEALISTA | Fully build idealista provider (full loop) | Extraction | 1, 2, 3 |
| P-FOTOCASA | Fully build fotocasa provider (full loop) | Extraction | 1, 2, 3 |
| 5 | DataDome bypass spike (Playwright + proxies) | Extraction | — |
| 6 | Scala Spark transformation layer | Transform | 2 |
| 7 | Scala API | Serve | 6 |
| 8 | Streamlit dashboard | Frontend | 7 |
| 9 | Supabase migration | Infra | 2 |
| 10 | Integration test suite | Quality gate | 2 |

---

## Task 1 — Install Docker Desktop

**Goal.** A working local Postgres can be brought up from `database/docker-compose.yml`.

**Steps.**
1. Install Docker Desktop for Windows 11 (WSL2 backend). Confirm virtualization is enabled in BIOS.
2. `docker --version` and `docker compose version` both succeed in PowerShell.
3. `docker compose -f database/docker-compose.yml up -d` starts the Postgres + pgAdmin containers.
4. `docker compose -f database/docker-compose.yml ps` shows both containers healthy.

**Files.** `database/docker-compose.yml` — added `pgAdmin` service and `pgadmin_data` volume. Credentials match `config.py` default DSN (`admin:admin1234@localhost:5432/barcelona-real-state`).

**pgAdmin access.**
- URL: `http://localhost:5050`
- Login: `admin@admin.com` / `admin1234`
- To connect to the DB inside pgAdmin: Add Server → Host `db`, Port `5432`, User `admin`, Password `admin1234`, DB `barcelona-real-state`. Use `db` (the service name) as host, not `localhost`, because both containers share the same Docker network.

**Acceptance criteria.**
- [x] `psql postgresql://admin:admin1234@localhost:5432/barcelona-real-state -c '\dt'` connects (empty is fine).
- [x] Container survives a machine reboot or has a documented `up -d` restart step. (`restart: always` in compose; re-run `docker compose -f database/docker-compose.yml up -d` after a manual stop.)
- [x] pgAdmin reachable at `http://localhost:5050` and can browse the `barcelona-real-state` database.

**Depends on.** — (blocker recorded in memory: Docker not installed on dev machine.)

---

## Task 2 — End-to-end DB load (habitaclia)

**Goal.** Real habitaclia rows land in Postgres via the existing pipeline, idempotently.

**Steps.**
1. With Postgres up (Task 1), apply schema:
   `psql "$DATABASE_URL" -f database/schema.sql` — confirm `properties` table + 3 indexes + unique constraint.
2. Run a bounded live scrape: `pipenv run python etl/run_all.py --only habitaclia`.
   (Consider temporarily capping pages/URLs for the first run — see note below.)
3. Verify rows: `SELECT provider, count(*) FROM properties GROUP BY provider;`
4. Re-run the same command and confirm **no duplicate rows** appear (upsert on `(provider,url)` works);
   confirm `scraped_at` advanced on existing rows.
5. Spot-check 5 rows for field correctness (price, size, rooms, bathrooms not empty/garbled).

**Files.** Possibly add a `--max-pages` / `--limit` CLI flag to `etl/run_all.py` and a matching
optional cap in `HabitacliaProvider.run()` so the smoke load is bounded and cheap. Keep default = unbounded.

**Acceptance criteria.**
- [x] ≥ 1 habitaclia row present with non-trivial field values. (9 rows; prices, location, size, rooms all populated)
- [x] Second run changes `scraped_at` but **not** row count for unchanged listings. (upsert on `(provider,url)` confirmed; zero duplicate rows)
- [x] Run logged total loaded count matches `SELECT count(*)`.

**Depends on.** Task 1.

---

## Task 3 — Add + enforce ruff / mypy

**Goal.** Lint + type checks are installed, pass clean, and are runnable with one command.

**Steps.**
1. Add `ruff` and `mypy` to `Pipfile` `[dev-packages]`; `pipenv install --dev`; commit `Pipfile.lock`.
2. Confirm `pyproject.toml` ruff + mypy config targets `components/`, `etl/`, `dags/`, `scripts/`, `tests/`.
3. Run `pipenv run ruff check .` and `pipenv run ruff format --check .`; fix or `--fix` findings.
4. Run `pipenv run mypy components etl dags scripts`; fix type findings. Known hotspots:
   - `etl/extraction/*.py` `sys.path.append` shim — keep but ensure imports still type-resolve.
   - BeautifulSoup `anchor["href"]` returns `str | list[str]`; tighten with explicit `str()` / guards.
   - `provider.py` `self._driver.page_source` accessed in `_is_blocked()` while typed `Optional` — guard or use the `driver` property.
5. Document the two commands in the "How to Run" section (already present below; keep in sync).

**Files.** `Pipfile`, `Pipfile.lock`, possibly small typing fixes across `components/` and `etl/`.

**Acceptance criteria.**
- [x] `ruff check .` → 0 errors. `ruff format --check .` → clean.
- [x] `mypy components etl dags` → 0 errors. (`scripts/` omitted — directory does not exist yet.)
- [x] Both commands documented and reproducible from a fresh `pipenv install --dev`.

**Depends on.** —

---

# The Provider Onboarding Loop

> Applies to **P-IDEALISTA** and **P-FOTOCASA**. A provider is *fully built* only when one complete
> pass through all four phases yields **zero** new findings. If any phase produces a finding, fix it
> and **restart the loop from CODE** (a security fix can break parsing; a parsing change can reopen a
> security hole — so we re-walk the whole loop, not just the failing phase).

```
        ┌──────────────────────────────────────────────┐
        │                                              │
        ▼                                              │
   ① CODE  ──►  ② TEST  ──►  ③ INTEGRATION  ──►  ④ SECURITY
        ▲                                              │
        │           any finding ⇒ fix + restart        │
        └──────────────────────────────────────────────┘
                  zero findings in a full pass ⇒ DONE
```

### ① CODE
- Open the provider in a **real, non-headless** `uc.Chrome()` session against live Barcelona listing + detail pages.
- Resolve **every** `# TODO: verify selector against live HTML` against the real DOM. For each selector:
  inspect the live element, replace the guess, and **delete the TODO** once confirmed.
- Verify the four scraper surfaces individually:
  - `get_property_urls(soup)` returns absolute, de-duplicated listing URLs.
  - `get_number_of_pages()` returns the true pagination max (not `1` fallback, not an off-by-one).
  - `_accept_cookies()` actually dismisses the consent dialog (Didomi/OneTrust id may differ per site).
  - `get_property_data(url)` → `_parse_property(...)` fills `price, name, size, rooms, bathrooms, squere_meter_price, location, description` with correct, non-empty values, and sets `url` for dedup.
- Watch for **field-order traps** (habitaclia had a price-as-first-`<strong>` off-by-one — assume the new provider has its own).
- Keep `_parse_property` a **pure function** (soup in, `Property` out) so it stays unit-testable.
- Run ruff + mypy on the touched files (Task 3 tooling).

### ② TEST  (offline, mandatory before any further live runs)
- Capture **real** saved HTML fixtures from the CODE phase: one search-results page and ≥ 3 detail pages
  (cheap/normal/edge — e.g. missing bathrooms, missing price/m², long description). Store under
  `tests/unit/python/fixtures/<provider>/`.
- Extend `tests/unit/python/test_<provider>.py` to assert, against those fixtures:
  - URL extraction count + absolute-URL shaping.
  - Pagination number parsing (including the "no pagination ⇒ 1" path).
  - Each `Property` field parsed from each fixture (exact expected values).
  - Graceful empty-string (not crash) when an element is absent.
- **Mock the browser/HTTP layer** — never hit the live site in unit tests (per CLAUDE.md).
- All tests green: `pipenv run pytest -q`. Coverage for the provider's parser ≈ 100% of branches.

### ③ INTEGRATION
- Bounded live run through the orchestrator into Postgres:
  `pipenv run python etl/run_all.py --only <provider>` (use the `--max-pages`/`--limit` cap from Task 2).
- Confirm rows land with correct `provider` value and populated fields; re-run to confirm
  `(provider,url)` upsert idempotency (no dupes, `scraped_at` advances).
- Confirm **per-provider isolation**: force this provider to raise and verify `run_all.py` still
  completes the others (it catches + logs + continues).
- Confirm the Airflow DAG (`dags/daily_etl.py`) references the provider and the task parses.
- Record real-world reliability: pages before first block, block type, success rate.

### ④ SECURITY
Review the provider + its data path against this checklist; any "no" is a finding:
- **Secrets:** no hardcoded credentials, proxy auth, cookies, or API keys; all via env (`DATABASE_URL` pattern). Nothing sensitive logged.
- **SQL:** writes go only through `loader.py` parameterized `execute_values` — no string-built SQL anywhere in the new path.
- **Injection / SSRF:** scraped URLs are constrained to the provider's own domain before `driver.get()` (validate host allowlist); never feed scraped text into shell, SQL, `eval`, or file paths.
- **Untrusted-content size:** cap description/field lengths so a hostile listing can't bloat the DB or memory.
- **Dependency hygiene:** `pip audit` / GitHub advisories clean for any new deps (e.g. Playwright). Pin versions in `Pipfile.lock`.
- **Robots/legal & rate:** scraping cadence stays within the anti-bot rules in CLAUDE.md (randomized delays, backoff, shuffled order); document the provider's `robots.txt` stance.
- **PII:** listing data is non-personal; confirm no agent phone/email is stored unless intended.
- Run `/security-review` on the branch diff and triage every finding.

### Exit criterion (per provider)
- [ ] A full loop pass (① → ④) completed with **zero** new findings.
- [ ] Provider's TODO selector comments are all gone.
- [ ] Unit tests green and committed with fixtures.
- [ ] Live integration produced real, idempotent rows.
- [ ] Security checklist fully satisfied; `/security-review` clean.

---

## Task P-IDEALISTA — Fully build the idealista provider

**Goal.** `etl/extraction/idealista.py` is production-verified and survives a full onboarding loop with zero findings.

### Current state (as of 2026-06-22)

The **transport has already been switched to Playwright + playwright-stealth** (ahead of Task 5,
because plain `uc.Chrome()` is known to lose to DataDome). What exists now:

- `etl/extraction/idealista.py` rewritten on a Playwright backend:
  - `start()`/`stop()` launch a non-headless Chromium with stealth patches, randomized
    viewport + user-agent, `locale="es-ES"`.
  - `_is_blocked()`, `_get_with_retry()`, `scroll_and_collect_urls()` reimplemented on the
    Playwright `Page` (selenium driver from `Provider` is never started for this provider).
  - `_proxy_config()` reads `PLAYWRIGHT_PROXY_SERVER` / `_USERNAME` / `_PASSWORD` from env;
    no proxy by default, drop-in residential proxy without code changes.
  - `_parse_property` kept a **pure function** — the 59 existing unit tests still pass.
- `scripts/idealista_probe.py` — live probe: opens the search page, reports block status,
  saves a search-results fixture + ≥ 3 detail fixtures to `tests/unit/python/fixtures/idealista/`,
  and prints every parsed field (flagging empties) so selectors can be confirmed/corrected.
- `playwright` + `playwright-stealth` added to `Pipfile`/`Pipfile.lock`; Chromium binary installed.
- ruff + mypy clean on the touched files.

> Note: `playwright-stealth` ≥ 2.x replaced the old `stealth_sync(page)` free function with
> `Stealth().apply_stealth_sync(page)` — the code uses the new API.

### Known limitations & resolution plan

Three open limitations remain. Each is addressed by a dedicated sub-step below; all three feed
the onboarding loop (§ The Provider Onboarding Loop) and **must be closed before the loop can
report zero findings**.

#### L1 — All selectors are unverified guesses (CODE phase blocker)

*Problem.* Every selector in `get_property_urls`, `get_number_of_pages`, `_accept_cookies`, and
`_parse_property` is a best-effort guess marked `# TODO: verify selector against live HTML`. A wrong
selector fails **silently** — the field returns `""` rather than raising — so bad data is invisible
without a live check. Affected guesses:
`article.item` / `a.item-link` (URLs), `ul.pagination a` (pages), `#didomi-notice-agree-button`
(cookies), `span.info-data-price` (price), `h1.main-info__title-main` (name),
`span.main-info__title-minor` (location), `div.info-features span` (size/rooms/baths — **order
unconfirmed**), `span.price-per-meter` (€/m²), `div.comment` (description).

*Plan.*
1. Run `pipenv run python scripts/idealista_probe.py` (needs `pipenv run playwright install chromium`
   once). This is gated by L2 — if DataDome blocks, resolve L2 first.
2. For every field the probe prints with a **correct, non-empty** value → delete its `# TODO` in
   `idealista.py`.
3. For every field the probe flags `[EMPTY]` or wrong → open the saved fixture HTML in DevTools,
   find the real selector, update the code, re-run the probe until all fields populate.
4. **Field-order trap (high risk):** confirm the `info-features` span order is exactly
   size → rooms → bathrooms against ≥ 3 real listings. Habitaclia had a price-as-first-element
   off-by-one; assume idealista has its own (e.g. a leading floor/plant span). If order differs,
   fix the index mapping in `_parse_property` rather than blindly trusting `features[0..2]`.
5. Re-run ruff + mypy on the touched files.

*Done when:* zero `# TODO: verify` comments remain in `idealista.py` and the probe prints
non-empty, correct values for all eight fields across ≥ 3 listings.

#### L2 — DataDome may still block even with Playwright + stealth (INTEGRATION phase blocker)

*Problem.* `playwright-stealth` patches JS-surface fingerprints (navigator.webdriver, Canvas,
WebGL, plugins) but **not** TLS/HTTP2 fingerprinting or behavioural scoring, which DataDome also
uses. Stealth alone has a real but non-guaranteed success rate; sustained multi-page runs are the
most likely to trip a soft-ban.

*Plan (escalating, stop at the first tier that works):*
1. **Tier 0 — stealth only.** Run the probe as-is. Record: did the search page load? how many
   detail pages before the first block? what block type (`geo.captcha-delivery.com` redirect vs.
   "comprueba que eres humano" interstitial vs. soft-block with empty cards)?
2. **Tier 1 — pacing.** If blocked after a few pages, widen the delays in `_get_with_retry` /
   `scroll_and_collect_urls` and reduce per-session page count; rely on the existing exponential
   backoff. Cheapest fix; try before paying for proxies.
3. **Tier 2 — residential proxy rotation.** If Tier 1 is insufficient, provision a residential
   proxy and set `PLAYWRIGHT_PROXY_SERVER` (+ `_USERNAME`/`_PASSWORD`). Code already supports it —
   no edits needed. Keep all proxy creds in env only (never committed). This is the formal hand-off
   to **Task 5** (DataDome bypass spike); record the chosen provider, reliability ceiling, and cost.
4. **Tier 3 — accept partial coverage.** If even proxies are unreliable, document idealista as
   "best-effort / bounded runs only" and cap `--limit` low, rather than blocking the whole pipeline.
   Per-provider isolation in `run_all.py` already prevents an idealista failure from stopping the others.

*Done when:* a repeatable bounded run loads the search page + ≥ 3 detail pages without a CAPTCHA,
**and** the reliability profile (tier used, pages-before-block, with/without proxy) is recorded in
the *Per-Provider Scraping Status* table.

#### L3 — Pagination URL pattern is assumed, not verified

*Problem.* `run()` builds subsequent pages as `f"{base_url}pagina-{n}.htm"`. If idealista uses a
different scheme (query param, different slug, or pagination injected via XHR), the loop silently
scrapes only page 1 — no error, just missing breadth.

*Plan.*
1. During the probe/CODE phase, manually click to page 2 in the live browser and read the real URL.
2. Confirm `get_number_of_pages()` returns the true max (not the `1` fallback, not an off-by-one)
   against the saved search fixture.
3. Fix the URL template in `run()` to match the observed pattern; if pagination is XHR-driven,
   switch to clicking the "next" control via Playwright instead of constructing URLs.
4. Verify by logging collected-URL counts across the first 2–3 pages and confirming they grow
   (i.e. page 2 yields *new* URLs, not a repeat of page 1).

*Done when:* a 2–3 page run collects strictly more unique URLs than a 1-page run, proving real
pagination traversal.

### Steps

Run **§ The Provider Onboarding Loop** end-to-end for idealista, threading the three limitations:

1. **L2 first (gate):** run the probe at Tier 0. If blocked, escalate L2 (Tiers 1→3 / Task 5) until
   the search page + detail pages load. Nothing else can be verified until a page renders.
2. **L1 (CODE):** with pages loading, resolve every selector via the probe + fixtures; kill all TODOs;
   confirm the `info-features` field order.
3. **L3 (CODE):** verify the real pagination URL/mechanism and the page-count parse.
4. **② TEST:** commit the captured fixtures; rewrite `tests/unit/python/test_idealista.py` to assert
   against **real** values (current tests assert against guessed HTML and must be replaced). Cover:
   URL extraction + absolute shaping, pagination parse incl. the `⇒ 1` path, every `Property` field
   per fixture, and graceful-empty on missing elements. `pipenv run pytest -q` green.
5. **③ INTEGRATION:** bounded live load `pipenv run python etl/run_all.py --only idealista --limit N`;
   confirm rows land with `provider='idealista'` + populated fields; re-run for `(provider,url)` upsert
   idempotency; confirm per-provider isolation (force a raise, others still load); confirm
   `dags/daily_etl.py` references idealista and parses.
6. **④ SECURITY:** run the §④ checklist + `/security-review`. Idealista-specific watch items:
   proxy creds env-only and never logged; scraped URLs constrained to `www.idealista.com` before
   `page.goto()` (host allowlist — guards against SSRF via a hostile listing link); cap description/
   field lengths; `pip audit` clean for the new `playwright` / `playwright-stealth` deps.
7. **Any finding ⇒ fix + restart from CODE.** Loop closes when a full ①→④ pass yields zero findings.

**Files.** `etl/extraction/idealista.py`, `scripts/idealista_probe.py`,
`tests/unit/python/test_idealista.py`, `tests/unit/python/fixtures/idealista/*`,
`Pipfile`/`Pipfile.lock` (done), possibly `provider.py` (if the Playwright transport is later
abstracted there and shared with fotocasa).

**Acceptance criteria.** The per-provider Exit criterion above, plus:
- [ ] L1 closed: no `# TODO: verify` comments left; `info-features` order confirmed against ≥ 3 listings.
- [ ] L2 closed: repeatable bounded run loads search + ≥ 3 detail pages without CAPTCHA; reliability
      profile (tier, pages-before-block, with/without proxy, cost) recorded in the status table.
- [ ] L3 closed: a 2–3 page run collects strictly more unique URLs than a 1-page run.
- [ ] `info-features` span order confirmed (size/rooms/bathrooms) against ≥ 3 real listings.

**Depends on.** Tasks 1, 2, 3. Task 5 is folded in via L2 Tier 2/3 (proxy transport) if stealth alone
proves insufficient.

---

## Task P-FOTOCASA — Fully build the fotocasa provider

**Goal.** `etl/extraction/fotocasa.py` is production-verified and survives a full onboarding loop with zero findings.

**Provider-specific context.**
- **DataDome** also protects fotocasa — same caveats as idealista; Task 5 likely applies.
- The fotocasa module already uses **layered fallback selectors** (multiple candidate classes per field);
  the CODE phase must collapse each fallback chain down to the one that's actually live, and delete the rest
  plus their TODOs. Watch its size/rooms/bathrooms ordering for the same off-by-one class of bug.
- Verify its cookie-consent flow and pagination URL pattern against the live site.

**Steps.** Run **§ The Provider Onboarding Loop** end-to-end for fotocasa.

**Files.** `etl/extraction/fotocasa.py`, `tests/unit/python/test_fotocasa.py`,
`tests/unit/python/fixtures/fotocasa/*`, possibly shared transport in `provider.py`.

**Acceptance criteria.** The per-provider Exit criterion above, plus:
- [ ] Fallback selector chains reduced to verified single selectors (no dead branches left).
- [ ] Sustained run reliability documented.

**Depends on.** Tasks 1, 2, 3; likely Task 5.

---

## Task 5 — DataDome bypass spike (Playwright + stealth + proxies)

**Goal.** Decide and implement the transport that lets idealista + fotocasa scrape reliably.

**Steps.**
1. Time-boxed spike: `pip install playwright playwright-stealth`, `playwright install chromium`.
   Try a stealth Playwright session against one idealista + one fotocasa listing page.
2. If still blocked, add **residential proxy rotation** (evaluate a provider; keep creds in env only).
3. Decide the abstraction: either a second `Provider` transport backend (Selenium/UC ↔ Playwright)
   behind the existing abstract methods, or a per-provider override. Keep `_parse_property` transport-agnostic.
4. Record results in this plan's "Per-Provider Scraping Status" table.

**Files.** `Pipfile` (+ `playwright`), possibly a `components/etl_components/transport*.py`, provider updates.

**Acceptance criteria.**
- [ ] At least one of {idealista, fotocasa} loads a real detail page without a CAPTCHA in a repeatable run.
- [ ] Chosen approach documented with its reliability ceiling and cost (proxy spend).

**Depends on.** —

---

## Task 6 — Scala Spark transformation layer

**Goal.** Raw `properties` rows are normalized, deduplicated, and enriched with investment metrics into a clean table.

**Steps.**
1. `transformation/build.sbt`: Spark + Postgres JDBC + ScalaTest deps. scalafmt + scalastyle configured.
2. Read raw `properties` via JDBC (env-driven `DATABASE_URL`, same swap pattern as Python).
3. **Normalize** the all-`TEXT` raw fields into typed columns:
   - `price` → numeric EUR (strip `€`, thousands separators, "/mes" rent guard).
   - `size` → numeric m²; `rooms`/`bathrooms` → ints; parse `squere_meter_price` or derive `price / size`.
   - `location` → cleaned neighborhood/district string.
4. **Deduplicate** across providers (same physical flat listed on 2 sites): key on normalized
   `(location, size, rooms, price-band)` heuristic; keep the freshest `scraped_at`.
5. **Compute metrics**: €/m², price vs. district median, simple rental-yield estimate, price-trend over scrape history.
6. Write to a `clean_properties` table (extend `schema.sql` / add a migration).
7. Keep transforms as **pure functions** `(DataFrame) => DataFrame` for ScalaTest.

> Scala teaching note (user is learning Scala): prefer `case class` row models + immutable `val`;
> structure each transform as a pure `Dataset[A] => Dataset[B]` so it can be unit-tested with a local
> `SparkSession` and no DB. Explain any Spark-specific idioms (e.g. `withColumn`, `Window` for trends,
> `Encoders`) inline in code comments when first introduced.

**Files.** `transformation/build.sbt`, `transformation/src/main/scala/transformation/*`,
`tests/unit/scala/*`, `database/schema.sql` (+ `clean_properties`).

**Acceptance criteria.**
- [ ] ScalaTest unit tests on each pure transform pass with synthetic DataFrames.
- [ ] A local run reads raw rows and writes ≥ 1 `clean_properties` row with €/m² computed.
- [ ] scalafmt + scalastyle clean.

**Depends on.** Task 2.

---

## Task 7 — Scala API

**Goal.** Clean data is served over HTTP for the dashboard.

**Steps.**
1. Pick framework (Play vs **http4s** — TBD; recommend http4s for a small read-only JSON API). Record the decision here.
2. Endpoints: `GET /properties` (filter by district, price, €/m², min yield; paginated),
   `GET /properties/{id}`, `GET /health`.
3. Read from `clean_properties` via JDBC/Doobie; immutable case-class DTOs; JSON via circe.
4. Config from env (port, `DATABASE_URL`).

**Files.** `api/build.sbt`, `api/src/main/scala/api/*`, `tests/unit/scala/*`.

**Acceptance criteria.**
- [ ] `GET /health` 200; `GET /properties?district=Eixample` returns filtered JSON.
- [ ] Route/serialization tests pass; scalafmt + scalastyle clean.

**Depends on.** Task 6.

---

## Task 8 — Streamlit dashboard

**Goal.** A usable investment-screening UI over the API.

**Steps.**
1. `dashboard/app.py` consumes the Scala API (base URL from env).
2. Views: ranked opportunities by €/m² and estimated yield; district filters; price/size sliders;
   per-listing detail; price-trend chart.
3. Cache API calls; handle API-down gracefully.

**Files.** `dashboard/app.py`, dashboard deps in `Pipfile`.

**Acceptance criteria.**
- [ ] `streamlit run dashboard/app.py` renders ranked listings from live API data.
- [ ] Filters change results without errors.

**Depends on.** Task 7.

---

## Task 9 — Supabase migration

**Goal.** Same code runs against Supabase by swapping `DATABASE_URL` only.

**Steps.**
1. Create Supabase project; apply `database/schema.sql` (+ `clean_properties`).
2. Set `DATABASE_URL` to the Supabase pooler string in the prod environment.
3. Run a bounded scrape + load against Supabase; verify rows; verify upsert idempotency.
4. Confirm no code change was required (config-only swap is the whole point).

**Files.** None (config/env). Optionally `database/migrations/` for ordered DDL.

**Acceptance criteria.**
- [ ] Pipeline writes to Supabase with `DATABASE_URL` swap and zero code edits.
- [ ] SSL/connection-pooling settings documented.

**Depends on.** Task 2.

---

## Task 10 — Integration test suite

**Goal.** Cross-component flows are tested against a real ephemeral Postgres (not the live sites).

**Steps.**
1. `tests/integration/`: spin a throwaway Postgres (testcontainers or compose), apply `schema.sql`.
2. Test `loader.load_properties` end-to-end: insert, upsert idempotency, `scraped_at` refresh.
3. Test orchestrator isolation with stubbed providers (one raises, others still load).
4. Feed saved provider HTML fixtures through `_parse_property` → `loader` → DB and assert rows.
5. Wire into CI (Task 4) as a separate, slower job.

**Files.** `tests/integration/*`, CI job.

**Acceptance criteria.**
- [ ] Integration job green in CI against ephemeral Postgres; no live-site access.
- [ ] Upsert idempotency and provider isolation both asserted.

**Depends on.** Task 2.

---

## How to Run (dev)

```bash
# Tests
python -m pipenv run pytest -q

# Lint + types (after Task 3)
python -m pipenv run ruff check .
python -m pipenv run ruff format --check .
python -m pipenv run mypy components etl dags scripts

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

| Provider | Anti-bot | Status | Onboarding loop |
|----------|----------|--------|-----------------|
| habitaclia | none significant | ✅ works with undetected-chromedriver alone | n/a (already verified) |
| idealista | **DataDome** | ⚠️ Playwright+stealth transport built; selectors unverified, DataDome bypass untested live | **Task P-IDEALISTA** (L2 may need Task 5 proxies) |
| fotocasa | **DataDome** | ⚠️ structure built; fallback selectors unverified | **Task P-FOTOCASA** (likely needs Task 5) |
