"""One-property live extraction — verifies detail-page selectors against real HTML."""

import logging
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

from dataclasses import asdict

from etl.extraction.habitaclia import HabitacliaProvider

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("probe")

provider = HabitacliaProvider()
with provider:
    provider.driver.get(provider.base_url)
    provider._accept_cookies()
    urls = provider.scroll_and_collect_urls(scroll_steps=1)
    if not urls:
        log.error("No URLs collected")
        sys.exit(1)
    prop = provider.get_property_data(urls[0])
    for k, v in asdict(prop).items():
        log.info("%-18s = %r", k, v)
