"""Bounded live smoke test — proves the scraper can get past anti-bot and
collect listing URLs, without doing a full detail-page crawl.

Run: pipenv run python scripts/live_smoke.py
"""

import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

from etl.extraction.habitaclia import HabitacliaProvider

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("live_smoke")

provider = HabitacliaProvider()
with provider:
    provider.driver.get(provider.base_url)
    provider._accept_cookies()
    blocked = provider._is_blocked()
    log.info("Blocked by anti-bot? %s", blocked)
    num_pages = provider.get_number_of_pages()
    log.info("Detected page count: %s", num_pages)
    urls = provider.scroll_and_collect_urls(scroll_steps=2)
    log.info("Collected %d unique listing URLs", len(urls))
    for u in urls[:5]:
        log.info("  sample: %s", u)
