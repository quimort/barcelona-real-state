"""Idealista live probe — verifies selectors and captures HTML fixtures.

Run:  pipenv run python scripts/idealista_probe.py

First time setup (run once after pipenv install):
  pipenv run playwright install chromium

What this does:
  1. Opens idealista search page with Playwright + stealth (non-headless)
  2. Reports whether DataDome blocked the session
  3. If not blocked: saves search-page HTML, extracts listing URLs, loads up to 3
     detail pages, saves each as a fixture, and prints all parsed field values
  4. If blocked: exits with instructions for enabling a proxy

Fixtures saved to: tests/unit/python/fixtures/idealista/
  search_page.html    — first search-results page
  detail_page_1.html  — first listing detail
  detail_page_2.html  — second listing detail
  detail_page_3.html  — third listing detail

After running, inspect the fixtures and the parsed values printed here.
For each field that is populated correctly, delete the matching # TODO comment
in etl/extraction/idealista.py.  For empty fields, open the saved HTML in a
browser DevTools, find the correct selector, and update the code.
"""

import logging
import os
import sys
from pathlib import Path

sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

from bs4 import BeautifulSoup

from etl.extraction.idealista import IdealistaProvider, _parse_property

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("idealista_probe")

FIXTURE_DIR = Path(__file__).parent.parent / "tests" / "unit" / "python" / "fixtures" / "idealista"
FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

provider = IdealistaProvider()

with provider:
    log.info("Loading search page: %s", provider.base_url)
    if not provider._get_with_retry(provider.base_url):
        log.error("DataDome blocked the search page — could not get through after retries.")
        log.error("To use a residential proxy, set these env vars and re-run:")
        log.error("  PLAYWRIGHT_PROXY_SERVER=http://proxy-host:port")
        log.error("  PLAYWRIGHT_PROXY_USERNAME=user  (if required)")
        log.error("  PLAYWRIGHT_PROXY_PASSWORD=pass  (if required)")
        sys.exit(1)

    if provider._is_blocked():
        log.error("Page loaded but DataDome CAPTCHA detected — check the browser window.")
        sys.exit(1)

    provider._accept_cookies()

    # Save search page
    search_html = provider._page.content()
    search_fixture = FIXTURE_DIR / "search_page.html"
    search_fixture.write_text(search_html, encoding="utf-8")
    log.info("Search page saved → %s (%d bytes)", search_fixture, len(search_html))

    num_pages = provider.get_number_of_pages()
    log.info("Detected page count: %d", num_pages)

    urls = provider.scroll_and_collect_urls(scroll_steps=2)
    log.info("Collected %d unique listing URLs from first page", len(urls))
    for u in urls[:5]:
        log.info("  sample: %s", u)

    if not urls:
        log.error("No listing URLs found — the article/anchor selector is wrong.")
        log.error("Open %s in a browser, inspect the listing cards, and update get_property_urls().", search_fixture)
        sys.exit(1)

    # Probe up to 3 detail pages
    probed = 0
    for url in urls:
        if probed >= 3:
            break
        log.info("--- Detail page %d: %s ---", probed + 1, url)
        if not provider._get_with_retry(url):
            log.warning("Blocked loading this detail page — skipping")
            continue

        html = provider._page.content()
        detail_fixture = FIXTURE_DIR / f"detail_page_{probed + 1}.html"
        detail_fixture.write_text(html, encoding="utf-8")
        log.info("Saved → %s (%d bytes)", detail_fixture, len(html))

        soup = BeautifulSoup(html, "html.parser")
        prop = _parse_property(soup, url, "residential", "idealista")

        log.info("  price              = %r", prop.price)
        log.info("  name               = %r", prop.name)
        log.info("  location           = %r", prop.location)
        log.info("  size               = %r", prop.size)
        log.info("  rooms              = %r", prop.rooms)
        log.info("  bathrooms          = %r", prop.bathrooms)
        log.info("  squere_meter_price = %r", prop.squere_meter_price)
        log.info("  description[:80]   = %r", prop.description[:80] if prop.description else "")

        # Warn on any empty field so selectors are easy to spot
        for field, value in [
            ("price", prop.price),
            ("name", prop.name),
            ("location", prop.location),
            ("size", prop.size),
            ("rooms", prop.rooms),
            ("bathrooms", prop.bathrooms),
        ]:
            if not value:
                log.warning("  [EMPTY] %s — selector may be wrong, inspect the saved HTML", field)

        probed += 1

log.info("")
log.info("Probe complete. Fixtures saved to: %s", FIXTURE_DIR)
log.info("Next steps:")
log.info("  1. For each field that printed a real value → delete its # TODO in idealista.py")
log.info("  2. For each [EMPTY] field → open the fixture HTML, find the correct selector, update idealista.py")
log.info("  3. Update tests/unit/python/test_idealista.py to use real fixture values")
