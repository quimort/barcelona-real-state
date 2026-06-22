"""
Idealista.com Barcelona listings scraper.

Transport: Playwright + playwright-stealth
==========================================
Idealista is protected by DataDome, which reliably blocks undetected-chromedriver.
This scraper uses Playwright + playwright-stealth to patch browser fingerprints
(navigator.webdriver, Canvas, WebGL, etc.) and simulate human behaviour.

If DataDome still blocks after stealth:
  Set PLAYWRIGHT_PROXY_SERVER / PLAYWRIGHT_PROXY_USERNAME / PLAYWRIGHT_PROXY_PASSWORD
  in the environment to route traffic through a residential proxy.
  See Task 5 (DataDome bypass spike) for the full investigation log.

Block markers checked in _is_blocked():
  - "geo.captcha-delivery.com"   (DataDome challenge endpoint)
  - "comprueba que eres humano"  (Spanish CAPTCHA prompt)

All CSS selectors below are marked # TODO: verify — run scripts/idealista_probe.py
against a live session to capture real HTML fixtures, then delete each TODO once confirmed.
"""

import logging
import os
import random
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from bs4 import BeautifulSoup
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, ProxySettings, ViewportSize, sync_playwright
from playwright_stealth import Stealth

from components.etl_components.property import Property
from components.etl_components.provider import Provider
from components.etl_components.utils import is_convertible_to_int

logger = logging.getLogger(__name__)

BASE_URL = "https://www.idealista.com/venta-viviendas/barcelona-barcelona/"

_BLOCK_MARKERS = (
    "access to this page has been denied",
    "pardon our interruption",
    "verify you are a human",
    "comprueba que eres humano",
    "unusual traffic from your computer",
    "geo.captcha-delivery.com",
    "please enable javascript and cookies to continue",
)
_BLOCK_TITLE_WORDS = ("captcha", "access denied", "blocked", "forbidden")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
]

_VIEWPORTS: list[ViewportSize] = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]


def _random_sleep(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


class IdealistaProvider(Provider):
    """Scraper for Idealista Barcelona residential sale listings.

    Uses Playwright + playwright-stealth. The selenium driver inherited from
    Provider is never started; all navigation runs through self._page.
    """

    def __init__(self) -> None:
        super().__init__(
            provider_name="idealista",
            base_url=BASE_URL,
            property_type="residential",
        )
        self._pw: Playwright | None = None
        self._pw_browser: Browser | None = None
        self._pw_context: BrowserContext | None = None
        self._pw_page: Page | None = None

    # ------------------------------------------------------------------
    # Playwright session lifecycle (overrides Provider's selenium start/stop)
    # ------------------------------------------------------------------

    def start(self) -> None:
        vp = random.choice(_VIEWPORTS)
        ua = random.choice(_USER_AGENTS)
        proxy = self._proxy_config()
        self._pw = sync_playwright().start()
        self._pw_browser = self._pw.chromium.launch(headless=False, proxy=proxy)
        self._pw_context = self._pw_browser.new_context(
            viewport=vp,
            user_agent=ua,
            locale="es-ES",
        )
        self._pw_page = self._pw_context.new_page()
        Stealth().apply_stealth_sync(self._pw_page)
        logger.debug("Playwright session started  vp=%s  proxy=%s", vp, bool(proxy))

    def stop(self) -> None:
        if self._pw_page:
            self._pw_page.close()
            self._pw_page = None
        if self._pw_context:
            self._pw_context.close()
            self._pw_context = None
        if self._pw_browser:
            self._pw_browser.close()
            self._pw_browser = None
        if self._pw:
            self._pw.stop()
            self._pw = None

    @staticmethod
    def _proxy_config() -> ProxySettings | None:
        """Read proxy settings from env. Returns None when not configured."""
        server = os.environ.get("PLAYWRIGHT_PROXY_SERVER")
        if not server:
            return None
        cfg: ProxySettings = {"server": server}
        username = os.environ.get("PLAYWRIGHT_PROXY_USERNAME")
        password = os.environ.get("PLAYWRIGHT_PROXY_PASSWORD")
        if username:
            cfg["username"] = username
        if password:
            cfg["password"] = password
        return cfg

    @property
    def _page(self) -> Page:
        if self._pw_page is None:
            raise RuntimeError("Playwright page not started — call start() first")
        return self._pw_page

    # ------------------------------------------------------------------
    # Anti-bot helpers
    # ------------------------------------------------------------------

    def _is_blocked(self) -> bool:
        content = self._page.content().lower()
        if any(marker in content for marker in _BLOCK_MARKERS):
            return True
        title = (self._page.title() or "").lower()
        return any(word in title for word in _BLOCK_TITLE_WORDS)

    def _get_with_retry(self, url: str, max_retries: int = 3) -> bool:
        for attempt in range(max_retries):
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                logger.warning("Navigation error on %s: %s", url, exc)
            _random_sleep(2.0, 4.5)
            if not self._is_blocked():
                return True
            backoff = (2**attempt) * random.uniform(3.0, 7.0)
            logger.warning(
                "Blocked on %s — retrying in %.1fs (attempt %d/%d)",
                url, backoff, attempt + 1, max_retries,
            )
            time.sleep(backoff)
        logger.error("Gave up loading %s after %d attempts", url, max_retries)
        return False

    def scroll_and_collect_urls(self, scroll_steps: int = 5) -> list[str]:
        collected: list[str] = []
        for _ in range(scroll_steps):
            soup = BeautifulSoup(self._page.content(), "html.parser")
            collected.extend(self.get_property_urls(soup))
            self._page.keyboard.press("PageDown")
            _random_sleep(2.5, 5.5)
        return list(set(collected))

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    def _accept_cookies(self) -> None:
        """Dismiss Idealista's cookie-consent dialog if present.

        TODO: verify selector against live HTML.
        """
        try:
            # TODO: verify selector against live HTML
            self._page.wait_for_selector("#didomi-notice-agree-button", timeout=8_000)
            self._page.click("#didomi-notice-agree-button")
            logger.debug("Cookie banner dismissed")
        except Exception:
            logger.debug("Cookie banner not found or already dismissed")

    # ------------------------------------------------------------------
    # Abstract-method implementations
    # ------------------------------------------------------------------

    def get_property_urls(self, soup: BeautifulSoup) -> list[str]:
        """Extract absolute listing URLs from a search-results page.

        TODO: verify selector against live HTML.
        """
        urls: list[str] = []
        for article in soup.find_all("article", class_="item"):  # TODO: verify selector against live HTML
            anchor = article.find("a", class_="item-link")  # TODO: verify selector against live HTML
            if anchor and anchor.get("href"):
                href = str(anchor["href"])
                if href.startswith("/"):
                    href = "https://www.idealista.com" + href
                urls.append(href)
        return urls

    def get_number_of_pages(self) -> int:
        """Determine total search-result pages from the pagination widget.

        TODO: verify selector against live HTML.
        """
        soup = BeautifulSoup(self._page.content(), "html.parser")
        numbers: list[int] = []
        pagination = soup.find("ul", class_="pagination")  # TODO: verify selector against live HTML
        if pagination:
            for tag in pagination.find_all("a"):
                value = tag.get_text(strip=True)
                if is_convertible_to_int(value):
                    numbers.append(int(value))
        return max(numbers, default=1)

    def get_property_data(self, url: str) -> Property:
        """Load a single listing page and return a Property record."""
        if not self._get_with_retry(url):
            raise RuntimeError(f"Could not load property page: {url}")
        soup = BeautifulSoup(self._page.content(), "html.parser")
        return _parse_property(soup, url, self.property_type, self.provider_name)

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    def run(self, max_properties: int | None = None) -> list[Property]:
        """Full scrape: open Playwright session, collect URLs page-by-page, parse each."""
        with self:
            if not self._get_with_retry(self.base_url):
                logger.error("Could not load idealista search page — aborting")
                return []
            self._accept_cookies()

            num_pages = self.get_number_of_pages()
            logger.info("Found %d pages on idealista", num_pages)

            all_urls: list[str] = []
            all_urls.extend(self.scroll_and_collect_urls())

            for page_num in range(2, num_pages + 1):
                page_url = f"{self.base_url}pagina-{page_num}.htm"
                if not self._get_with_retry(page_url):
                    logger.warning("Skipping page %d — blocked", page_num)
                    continue
                all_urls.extend(self.scroll_and_collect_urls())

            all_urls = list(set(all_urls))
            random.shuffle(all_urls)
            if max_properties is not None:
                all_urls = all_urls[:max_properties]
            logger.info("Collected %d unique property URLs (limit=%s)", len(all_urls), max_properties)

            properties: list[Property] = []
            for url in all_urls:
                try:
                    prop = self.get_property_data(url)
                    properties.append(prop)
                except Exception as exc:
                    logger.warning("Skipped %s: %s", url, exc)

            logger.info("Scraped %d properties from idealista", len(properties))
            return properties


# ------------------------------------------------------------------
# Pure HTML-parsing helper (testable without a browser)
# ------------------------------------------------------------------


def _parse_property(
    soup: BeautifulSoup,
    url: str,
    property_type: str,
    provider: str,
) -> Property:
    """Parse a single Idealista listing detail page into a Property.

    All selectors are best-effort; each TODO must be resolved against live HTML.
    Keep this function pure (soup in, Property out) so it stays unit-testable.
    """
    # Price — <span class="info-data-price">
    # TODO: verify selector against live HTML
    price_tag = soup.find("span", class_="info-data-price")
    price = price_tag.get_text(strip=True) if price_tag else ""

    # Title — <h1 class="main-info__title-main">
    # TODO: verify selector against live HTML
    title_tag = soup.find("h1", class_="main-info__title-main")
    name = title_tag.get_text(strip=True) if title_tag else ""

    # Location — <span class="main-info__title-minor">
    # TODO: verify selector against live HTML
    location_tag = soup.find("span", class_="main-info__title-minor")
    location = location_tag.get_text(strip=True) if location_tag else ""

    # Key stats (size, rooms, bathrooms) — <div class="info-features"> with inner <span>s
    # Order assumed: 0 → size (m²), 1 → rooms, 2 → bathrooms
    # TODO: verify selector and field order against live HTML
    features: list[str] = []
    info_features = soup.find("div", class_="info-features")
    if info_features:
        for span in info_features.find_all("span"):
            text = span.get_text(strip=True)
            if text:
                features.append(text)

    size = features[0] if len(features) > 0 else ""
    rooms = features[1] if len(features) > 1 else ""
    bathrooms = features[2] if len(features) > 2 else ""

    # Price per m² — <span class="price-per-meter">
    # TODO: verify selector against live HTML
    sqm_tag = soup.find("span", class_="price-per-meter")
    squere_meter_price = sqm_tag.get_text(strip=True) if sqm_tag else ""

    # Description — <div class="comment">
    # TODO: verify selector against live HTML
    desc_section = soup.find("div", class_="comment")
    description = desc_section.get_text(strip=True) if desc_section else ""

    return Property(
        price=price,
        name=name,
        size=size,
        rooms=rooms,
        bathrooms=bathrooms,
        squere_meter_price=squere_meter_price,
        location=location,
        description=description,
        prop_type=property_type,
        provider=provider,
        url=url,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = IdealistaProvider()
    results = scraper.run()
