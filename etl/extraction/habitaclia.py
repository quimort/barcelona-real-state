import logging
import random
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from components.etl_components.property import Property
from components.etl_components.provider import Provider
from components.etl_components.utils import is_convertible_to_int

logger = logging.getLogger(__name__)

BASE_URL = "https://www.habitaclia.com/viviendas-barcelona.htm"


def _parse_property(soup: BeautifulSoup, url: str, property_type: str, provider: str) -> Property:
    """Pure parsing of a habitaclia detail page — no driver, unit-testable."""
    price_container = soup.find("div", class_="price")
    price = (
        price_container.find("span", itemprop="price").get_text(strip=True)
        if price_container and price_container.find("span", itemprop="price")
        else ""
    )

    summary = soup.find("div", class_="summary-left")
    name = summary.find("h1").get_text(strip=True) if summary and summary.find("h1") else ""
    location_anchor = (
        summary.find("article", class_="location").find("a")
        if summary and summary.find("article", class_="location")
        else None
    )
    location = location_anchor.get_text(strip=True) if location_anchor else ""

    features: list[str] = []
    feature_list = soup.find("ul", class_="feature-container")
    if feature_list:
        features = [
            li.find("strong").get_text(strip=True)
            for li in feature_list.find_all("li")
            if li.find("strong")
        ]
    # Verified against live HTML 2026-06-13: the first <strong> in the
    # feature-container is the price, so drop it to align size/rooms/bathrooms.
    if features and "€" in features[0]:
        features = features[1:]

    desc_tag = soup.find("p", id="js-detail-description")
    description = desc_tag.get_text(strip=True) if desc_tag else ""

    return Property(
        price=price,
        name=name,
        size=features[0] if len(features) > 0 else "",
        rooms=features[1] if len(features) > 1 else "",
        bathrooms=features[2] if len(features) > 2 else "",
        squere_meter_price="",
        location=location,
        description=description,
        prop_type=property_type,
        provider=provider,
        url=url,
    )


class HabitacliaProvider(Provider):

    def __init__(self) -> None:
        super().__init__(
            provider_name="habitaclia",
            base_url=BASE_URL,
            property_type="residential",
        )

    def get_property_urls(self, soup: BeautifulSoup) -> list[str]:
        urls: list[str] = []
        for item in soup.find_all("div", class_="list-item-info"):
            anchor = item.find("a")
            if anchor and anchor.get("href"):
                urls.append(anchor["href"])
        return urls

    def get_number_of_pages(self) -> int:
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        numbers: list[int] = []
        for ul in soup.find_all("ul", class_="f-right"):
            for tag in ul.find_all("a"):
                value = tag.get_text(strip=True)
                if is_convertible_to_int(value):
                    numbers.append(int(value))
        return max(numbers, default=1)

    def get_property_data(self, url: str) -> Property:
        if not self._get_with_retry(url):
            raise RuntimeError(f"Could not load property page: {url}")
        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        return _parse_property(soup, url, self.property_type, self.provider_name)

    def _accept_cookies(self) -> None:
        try:
            btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.ID, "didomi-notice-agree-button"))
            )
            btn.click()
        except Exception:
            logger.debug("Cookie banner not found or already dismissed")

    def run(self) -> list[Property]:
        with self:
            self.driver.get(self.base_url)
            self._accept_cookies()

            num_pages = self.get_number_of_pages()
            logger.info("Found %d pages on habitaclia", num_pages)

            all_urls = self.scroll_and_collect_urls()
            random.shuffle(all_urls)
            logger.info("Collected %d property URLs", len(all_urls))

            properties: list[Property] = []
            for url in all_urls:
                try:
                    prop = self.get_property_data(url)
                    properties.append(prop)
                except Exception as exc:
                    logger.warning("Skipped %s: %s", url, exc)

            logger.info("Scraped %d properties", len(properties))
            return properties


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = HabitacliaProvider()
    results = scraper.run()
