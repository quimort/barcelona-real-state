import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Optional

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

from .property import Property

logger = logging.getLogger(__name__)

_VIEWPORTS = [
    (1920, 1080),
    (1366, 768),
    (1536, 864),
    (1440, 900),
    (1280, 800),
]

# Specific block-page phrases — kept narrow to avoid false positives.
# (A bare "robot" matches the legitimate <meta name="robots"> tag, so it is NOT used here.)
_BLOCK_MARKERS = (
    "access to this page has been denied",
    "pardon our interruption",
    "verify you are a human",
    "unusual traffic from your computer",
    "geo.captcha-delivery.com",  # DataDome challenge endpoint
    "please enable javascript and cookies to continue",
)
_BLOCK_TITLE_WORDS = ("captcha", "access denied", "blocked", "forbidden")


def _random_sleep(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


class Provider(ABC):

    def __init__(self, provider_name: str, base_url: str, property_type: str) -> None:
        self.provider_name = provider_name
        self.base_url = base_url
        self.property_type = property_type
        self._driver: Optional[webdriver.Chrome] = None

    @property
    def driver(self) -> webdriver.Chrome:
        if self._driver is None:
            raise RuntimeError("Driver not started — call start() first")
        return self._driver

    def start(self) -> None:
        options = uc.ChromeOptions()
        w, h = random.choice(_VIEWPORTS)
        options.add_argument(f"--window-size={w},{h}")
        self._driver = uc.Chrome(options=options)

    def stop(self) -> None:
        if self._driver:
            self._driver.quit()
            self._driver = None

    def __enter__(self) -> "Provider":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    def _is_blocked(self) -> bool:
        page = self._driver.page_source.lower()
        if any(marker in page for marker in _BLOCK_MARKERS):
            return True
        title = (self._driver.title or "").lower()
        return any(word in title for word in _BLOCK_TITLE_WORDS)

    def _get_with_retry(self, url: str, max_retries: int = 3) -> bool:
        for attempt in range(max_retries):
            self.driver.get(url)
            _random_sleep(2.0, 4.5)
            if not self._is_blocked():
                return True
            backoff = (2 ** attempt) * random.uniform(3.0, 7.0)
            logger.warning("Blocked on %s — retrying in %.1fs (attempt %d/%d)", url, backoff, attempt + 1, max_retries)
            time.sleep(backoff)
        logger.error("Gave up loading %s after %d attempts", url, max_retries)
        return False

    def scroll_and_collect_urls(self, scroll_steps: int = 5) -> list[str]:
        collected: list[str] = []
        for _ in range(scroll_steps):
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            collected.extend(self.get_property_urls(soup))
            ActionChains(self.driver).key_down(Keys.PAGE_DOWN).key_up(Keys.PAGE_DOWN).perform()
            _random_sleep(2.5, 5.5)
        return list(set(collected))

    @abstractmethod
    def get_property_urls(self, soup: BeautifulSoup) -> list[str]:
        ...

    @abstractmethod
    def get_number_of_pages(self) -> int:
        ...

    @abstractmethod
    def get_property_data(self, url: str) -> Property:
        ...
