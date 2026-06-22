"""Fotocasa Barcelona listings scraper.

Module notes
------------
Cookie consent
    Fotocasa displays a TCF/IAB cookie-consent banner on first visit, typically
    rendered by a third-party CMP (OneTrust or similar). The ``_accept_cookies``
    method targets the most common button selector; if Fotocasa switches CMP
    provider the selector will need updating.

Lazy-loaded / infinite-scroll content
    Fotocasa listing pages load cards incrementally as the user scrolls. Static
    page fetches therefore return only the first batch of cards. The inherited
    ``scroll_and_collect_urls`` helper handles this by repeatedly scrolling and
    re-parsing, but the number of ``scroll_steps`` may need tuning depending on
    how many listings are visible per viewport.

Playwright fallback
    Fotocasa deploys aggressive bot-detection (Datadome) that can block
    Selenium-based scrapers even with ``undetected_chromedriver``. If blocked
    consistently, consider migrating to Playwright + ``playwright-stealth`` as
    described in CLAUDE.md.
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

logger = logging.getLogger(__name__)

BASE_URL = "https://www.fotocasa.es/es/comprar/viviendas/barcelona-capital/todas-las-zonas/l"


class FotocasaProvider(Provider):
    """Scraper for fotocasa.es Barcelona residential-purchase listings."""

    def __init__(self) -> None:
        super().__init__(
            provider_name="fotocasa",
            base_url=BASE_URL,
            property_type="residential",
        )

    # ------------------------------------------------------------------
    # Abstract method implementations
    # ------------------------------------------------------------------

    def get_property_urls(self, soup: BeautifulSoup) -> list[str]:
        """Extract property detail-page URLs from a listing-page soup.

        Fotocasa wraps each card in an ``<article>`` element.  The canonical
        link lives either in a ``data-href`` attribute on the article itself or
        inside a nested ``<a>`` anchor with class ``re-CardPackMinimalist-info``
        (or a similar variant).  Both paths are tried so the method degrades
        gracefully if one changes.

        # TODO: verify selector against live HTML
        """
        urls: list[str] = []
        base = "https://www.fotocasa.es"

        # Path 1 — article with data-href (observed in some Fotocasa layouts)
        # TODO: verify selector against live HTML
        for article in soup.find_all("article", attrs={"data-href": True}):
            href = str(article.get("data-href", ""))
            if href:
                full = href if href.startswith("http") else base + href
                urls.append(full)

        # Path 2 — anchor inside the card info block
        # TODO: verify selector against live HTML
        for anchor in soup.find_all("a", class_="re-CardPackMinimalist-info"):
            href = str(anchor.get("href", ""))
            if href:
                full = href if href.startswith("http") else base + href
                urls.append(full)

        # Path 3 — fallback: any anchor whose href contains "/es/comprar/"
        # TODO: verify selector against live HTML
        if not urls:
            for anchor in soup.find_all("a", href=True):
                href = str(anchor["href"])
                if "/es/comprar/" in href and href not in urls:
                    full = href if href.startswith("http") else base + href
                    urls.append(full)

        return list(set(urls))

    def get_number_of_pages(self) -> int:
        """Return the total number of listing pages for the current search.

        Fotocasa renders pagination as a ``<ul>`` with numbered ``<button>``
        or ``<a>`` children.  We grab every element whose text is a pure integer
        and return the maximum.

        # TODO: verify selector against live HTML
        """
        soup = BeautifulSoup(self.driver.page_source, "html.parser")

        numbers: list[int] = []

        # Primary: pagination list
        # TODO: verify selector against live HTML
        pagination = soup.find("ul", class_="sui-MoleculePagination-list")
        if pagination:
            for item in pagination.find_all(["a", "button", "li"]):
                text = item.get_text(strip=True)
                if text.isdigit():
                    numbers.append(int(text))

        # Fallback: scan all anchors/buttons for numeric text
        # TODO: verify selector against live HTML
        if not numbers:
            for tag in soup.find_all(["a", "button"]):
                text = tag.get_text(strip=True)
                if text.isdigit():
                    numbers.append(int(text))

        return max(numbers, default=1)

    def get_property_data(self, url: str) -> Property:
        """Load a Fotocasa property detail page and return a ``Property``.

        Parsing is delegated to the pure helper ``_parse_property`` so it can
        be unit-tested without a live browser.
        """
        if not self._get_with_retry(url):
            raise RuntimeError(f"Could not load property page: {url}")

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        return _parse_property(soup, url, self.property_type, self.provider_name)

    # ------------------------------------------------------------------
    # Cookie consent
    # ------------------------------------------------------------------

    def _accept_cookies(self) -> None:
        """Dismiss the cookie-consent banner if present.

        Fotocasa uses a CMP overlay.  Common button IDs/classes are tried in
        order; failure is silently swallowed so a missing banner never blocks
        the run.

        # TODO: verify cookie-button selector against live HTML
        """
        selectors = [
            (By.ID, "didomi-notice-agree-button"),  # Didomi CMP
            (By.CSS_SELECTOR, "button[data-testid='TcfAccept']"),  # Fotocasa-specific
            (By.CSS_SELECTOR, "button.sui-AtomButton--primary"),  # generic primary btn
        ]
        for by, value in selectors:
            try:
                btn = WebDriverWait(self.driver, 6).until(EC.element_to_be_clickable((by, value)))
                btn.click()
                logger.debug("Accepted cookies via selector (%s, %s)", by, value)
                return
            except Exception:
                continue
        logger.debug("Cookie banner not found or already dismissed")

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self, max_properties: int | None = None) -> list[Property]:
        """Full extraction run: open browser, collect URLs, scrape detail pages."""
        with self:
            self.driver.get(self.base_url)
            self._accept_cookies()

            num_pages = self.get_number_of_pages()
            logger.info("Found %d pages on fotocasa", num_pages)

            all_urls = self.scroll_and_collect_urls()
            random.shuffle(all_urls)
            logger.info("Collected %d property URLs from page 1", len(all_urls))

            # Iterate additional pages
            for page in range(2, num_pages + 1):
                page_url = f"{self.base_url}?pagina={page}"
                if not self._get_with_retry(page_url):
                    logger.warning("Skipping page %d — blocked", page)
                    continue
                page_urls = self.scroll_and_collect_urls()
                all_urls.extend(page_urls)
                logger.info("Page %d: +%d URLs (total %d)", page, len(page_urls), len(all_urls))

            all_urls = list(set(all_urls))
            random.shuffle(all_urls)
            logger.info("Total unique property URLs: %d", len(all_urls))

            properties: list[Property] = []
            for url in all_urls:
                try:
                    prop = self.get_property_data(url)
                    properties.append(prop)
                except Exception as exc:
                    logger.warning("Skipped %s: %s", url, exc)

            logger.info("Scraped %d properties from fotocasa", len(properties))
            return properties


# ------------------------------------------------------------------
# Pure parsing helper (testable without a browser)
# ------------------------------------------------------------------


def _parse_property(
    soup: BeautifulSoup,
    url: str,
    property_type: str,
    provider: str,
) -> Property:
    """Extract structured fields from a Fotocasa property detail-page soup.

    All selectors are best-effort based on Fotocasa's known DOM patterns.
    Every field has a defensive fallback so a missing element yields an empty
    string rather than raising an AttributeError.

    # TODO: verify ALL selectors against live HTML before relying on output.
    """

    # --- Price ---
    # Fotocasa renders price in a <span> with class "re-DetailHeader-price"
    # or inside a container with class "re-DetailPrice"
    # TODO: verify selector against live HTML
    price = ""
    price_tag = soup.find("span", class_="re-DetailHeader-price")
    if price_tag is None:
        price_tag = soup.find("span", class_="re-DetailPrice-price")
    if price_tag is None:
        # Fallback: any element with itemprop="price"
        price_tag = soup.find(itemprop="price")
    if price_tag is not None:
        price = price_tag.get_text(strip=True)

    # --- Name / title ---
    # Main heading is an <h1> with class "re-DetailHeader-propertyTitle"
    # TODO: verify selector against live HTML
    name = ""
    name_tag = soup.find("h1", class_="re-DetailHeader-propertyTitle")
    if name_tag is None:
        name_tag = soup.find("h1")
    if name_tag is not None:
        name = name_tag.get_text(strip=True)

    # --- Location ---
    # Address breadcrumb is in a <span> with class "re-DetailHeader-location"
    # or inside an anchor with itemprop="addressLocality"
    # TODO: verify selector against live HTML
    location = ""
    location_tag = soup.find("span", class_="re-DetailHeader-location")
    if location_tag is None:
        location_tag = soup.find(itemprop="addressLocality")
    if location_tag is not None:
        location = location_tag.get_text(strip=True)

    # --- Features (size / rooms / bathrooms) ---
    # Fotocasa lists features in a <ul class="re-DetailFeaturesList"> or
    # individual <li> elements with data-testid attributes.
    # TODO: verify selector against live HTML
    size = ""
    rooms = ""
    bathrooms = ""

    feature_list = soup.find("ul", class_="re-DetailFeaturesList")
    if feature_list:
        items = feature_list.find_all("li")
        # Typical ordering: surface m², rooms, bathrooms — but we try label matching
        for item in items:
            text = item.get_text(strip=True).lower()
            value_tag = item.find("span", class_="re-DetailFeaturesList-featureValue")
            raw_value = value_tag.get_text(strip=True) if value_tag else item.get_text(strip=True)
            if "m²" in text or "superficie" in text:
                size = raw_value
            elif "habit" in text or "dormitorio" in text:
                rooms = raw_value
            elif "baño" in text or "aseo" in text:
                bathrooms = raw_value

    # Fallback: data-testid attributes used in newer Fotocasa layouts
    # TODO: verify selector against live HTML
    if not size:
        size_tag = soup.find(attrs={"data-testid": "feature-surface"})  # type: ignore[call-overload]
        if size_tag:
            size = size_tag.get_text(strip=True)
    if not rooms:
        rooms_tag = soup.find(attrs={"data-testid": "feature-rooms"})  # type: ignore[call-overload]
        if rooms_tag:
            rooms = rooms_tag.get_text(strip=True)
    if not bathrooms:
        baths_tag = soup.find(attrs={"data-testid": "feature-bathrooms"})  # type: ignore[call-overload]
        if baths_tag:
            bathrooms = baths_tag.get_text(strip=True)

    # --- Price per m² ---
    # TODO: verify selector against live HTML
    squere_meter_price = ""
    sqm_tag = soup.find("span", class_="re-DetailHeader-priceByArea")
    if sqm_tag is None:
        sqm_tag = soup.find("span", class_="re-DetailPrice-pricePerSquareMeter")
    if sqm_tag is not None:
        squere_meter_price = sqm_tag.get_text(strip=True)

    # --- Description ---
    # TODO: verify selector against live HTML
    description = ""
    desc_tag = soup.find("div", class_="re-DetailDescription-text")
    if desc_tag is None:
        desc_tag = soup.find("div", attrs={"data-testid": "description"})
    if desc_tag is None:
        desc_tag = soup.find("p", class_="re-DetailDescription-description")
    if desc_tag is not None:
        description = desc_tag.get_text(strip=True)

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
    scraper = FotocasaProvider()
    results = scraper.run()
