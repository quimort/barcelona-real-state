"""
Idealista.com Barcelona listings scraper.

WARNING — Anti-bot reality check
=================================
Idealista runs **DataDome**, one of the most aggressive bot-detection systems
in production today.  Plain undetected-chromedriver (``uc.Chrome``) is
frequently insufficient: DataDome fingerprints the browser at the TLS/HTTP2
level, inspects Canvas/WebGL hashes, and uses behavioural analysis that goes
well beyond what UC patches.

Expected failure modes:
- Immediate 403 / "Comprueba que eres humano" CAPTCHA on first request.
- Soft-block: page loads but listing cards are empty / redirected.
- Session ban after a few successful pages.

Recommended fallback if this scraper fails in practice:
  Use **Playwright + playwright-stealth** (``pip install playwright
  playwright-stealth``), which patches more browser-fingerprint vectors.
  Even then, residential proxy rotation is likely required for sustained runs.

Do NOT assume this module will work reliably out-of-the-box on a bare machine.
Treat every selector marked ``# TODO: verify selector against live HTML`` as
requiring manual DOM inspection before a production run.
"""

import logging
import os
import random
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from components.etl_components.property import Property
from components.etl_components.provider import Provider
from components.etl_components.utils import is_convertible_to_int

logger = logging.getLogger(__name__)

BASE_URL = "https://www.idealista.com/venta-viviendas/barcelona-barcelona/"


class IdealistaProvider(Provider):
    """Scraper for Idealista Barcelona residential sale listings.

    See module docstring for DataDome / anti-bot caveats before running.
    """

    def __init__(self) -> None:
        super().__init__(
            provider_name="idealista",
            base_url=BASE_URL,
            property_type="residential",
        )

    # ------------------------------------------------------------------
    # Abstract-method implementations
    # ------------------------------------------------------------------

    def get_property_urls(self, soup: BeautifulSoup) -> list[str]:
        """Extract absolute listing URLs from a search-results page.

        Idealista renders listing cards inside ``<article>`` elements that
        carry the class ``item``.  The canonical link sits in the ``href``
        of the ``<a class="item-link">`` anchor inside each card.

        TODO: verify selector against live HTML — class names may change.
        """
        urls: list[str] = []
        # TODO: verify selector against live HTML
        for article in soup.find_all("article", class_="item"):
            anchor = article.find("a", class_="item-link")  # TODO: verify selector against live HTML
            if anchor and anchor.get("href"):
                href: str = anchor["href"]
                # Idealista hrefs are root-relative (/inmueble/12345/)
                if href.startswith("/"):
                    href = "https://www.idealista.com" + href
                urls.append(href)
        return urls

    def get_number_of_pages(self) -> int:
        """Determine total search-result pages from the pagination widget.

        Idealista's pagination bar is rendered as ``<ul class="pagination">``
        containing ``<li>`` / ``<a>`` elements whose text is the page number.

        TODO: verify selector against live HTML — pagination markup varies.
        """
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        numbers: list[int] = []
        # TODO: verify selector against live HTML
        pagination = soup.find("ul", class_="pagination")
        if pagination:
            for tag in pagination.find_all("a"):
                value = tag.get_text(strip=True)
                if is_convertible_to_int(value):
                    numbers.append(int(value))
        return max(numbers, default=1)

    def get_property_data(self, url: str) -> Property:
        """Load a single listing page and return a ``Property`` record."""
        if not self._get_with_retry(url):
            raise RuntimeError(f"Could not load property page: {url}")

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        return _parse_property(soup, url, self.property_type, self.provider_name)

    # ------------------------------------------------------------------
    # Cookie / consent banner
    # ------------------------------------------------------------------

    def _accept_cookies(self) -> None:
        """Dismiss Idealista's cookie-consent dialog if present.

        The consent button ID / class is subject to change.
        TODO: verify selector against live HTML.
        """
        try:
            # TODO: verify selector against live HTML
            btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.ID, "didomi-notice-agree-button"))
            )
            btn.click()
            logger.debug("Cookie banner dismissed")
        except Exception:
            logger.debug("Cookie banner not found or already dismissed")

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    def run(self) -> list[Property]:
        """Full scrape: open browser, collect URLs page-by-page, parse each."""
        with self:
            self.driver.get(self.base_url)
            self._accept_cookies()

            num_pages = self.get_number_of_pages()
            logger.info("Found %d pages on idealista", num_pages)

            all_urls: list[str] = []

            # Collect URLs from the first (already loaded) page
            all_urls.extend(self.scroll_and_collect_urls())

            # Navigate to subsequent pages and collect
            for page_num in range(2, num_pages + 1):
                page_url = f"{self.base_url}pagina-{page_num}.htm"
                if not self._get_with_retry(page_url):
                    logger.warning("Skipping page %d — blocked", page_num)
                    continue
                all_urls.extend(self.scroll_and_collect_urls())

            # Deduplicate and shuffle to avoid sequential access patterns
            all_urls = list(set(all_urls))
            random.shuffle(all_urls)
            logger.info("Collected %d unique property URLs", len(all_urls))

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
    """Parse a single Idealista listing detail page into a ``Property``.

    All selectors are best-effort based on publicly documented DOM patterns.
    Each one is annotated with a TODO for live verification.

    Defensive None-checks are used throughout so that a missing element
    produces an empty string rather than crashing the run.
    """
    # --- Price ---
    # Idealista wraps the price in <span class="info-data-price">
    # which lives inside <div class="price-features__container">
    # TODO: verify selector against live HTML
    price_tag = soup.find("span", class_="info-data-price")  # TODO: verify selector against live HTML
    price = price_tag.get_text(strip=True) if price_tag else ""

    # --- Title / name ---
    # The listing title is typically in <h1 class="main-info__title-main">
    # TODO: verify selector against live HTML
    title_tag = soup.find("h1", class_="main-info__title-main")  # TODO: verify selector against live HTML
    name = title_tag.get_text(strip=True) if title_tag else ""

    # --- Location ---
    # Address sits in <span class="main-info__title-minor">
    # TODO: verify selector against live HTML
    location_tag = soup.find("span", class_="main-info__title-minor")  # TODO: verify selector against live HTML
    location = location_tag.get_text(strip=True) if location_tag else ""

    # --- Key stats (size, rooms, bathrooms) ---
    # Idealista lists stats in <div class="info-features"> containing
    # multiple <span> elements.  The order is typically:
    #   0 → size (m²), 1 → rooms, 2 → bathrooms
    # TODO: verify selector against live HTML
    features: list[str] = []
    info_features = soup.find("div", class_="info-features")  # TODO: verify selector against live HTML
    if info_features:
        for span in info_features.find_all("span"):
            text = span.get_text(strip=True)
            if text:
                features.append(text)

    size = features[0] if len(features) > 0 else ""
    rooms = features[1] if len(features) > 1 else ""
    bathrooms = features[2] if len(features) > 2 else ""

    # --- Price per m² ---
    # Shown in <span class="price-per-meter"> or similar
    # TODO: verify selector against live HTML
    sqm_tag = soup.find("span", class_="price-per-meter")  # TODO: verify selector against live HTML
    squere_meter_price = sqm_tag.get_text(strip=True) if sqm_tag else ""

    # --- Description ---
    # Full description lives in <div class="comment"> inside
    # <section class="detail-info">
    # TODO: verify selector against live HTML
    desc_section = soup.find("div", class_="comment")  # TODO: verify selector against live HTML
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
