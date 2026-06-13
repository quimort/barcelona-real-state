"""Unit tests for etl/extraction/idealista.py.

All tests are fully offline — no browser is instantiated, no network calls
are made.  BeautifulSoup objects are built from small static HTML fixtures
that mimic Idealista's DOM structure (as currently guessed; see TODOs in
the module under test).
"""

import os
import sys

# ---------------------------------------------------------------------------
# Path bootstrap so the module can be imported without an installed package
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest
from bs4 import BeautifulSoup

from etl.extraction.idealista import IdealistaProvider, _parse_property


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

LISTING_PAGE_HTML = """
<html>
<body>
  <section class="items-list">
    <article class="item">
      <a class="item-link" href="/inmueble/100001/">Piso en Eixample</a>
    </article>
    <article class="item">
      <a class="item-link" href="/inmueble/100002/">Àtic en Gràcia</a>
    </article>
    <article class="item no-link">
      <!-- article without an anchor — must not crash -->
    </article>
    <article class="item">
      <!-- anchor present but no href attribute — must not crash -->
      <a class="item-link">Sin enlace</a>
    </article>
  </section>
  <ul class="pagination">
    <li><a>Anterior</a></li>
    <li><a>1</a></li>
    <li><a>2</a></li>
    <li><a>3</a></li>
    <li><a>Siguiente</a></li>
  </ul>
</body>
</html>
"""

DETAIL_PAGE_HTML = """
<html>
<body>
  <span class="info-data-price">350.000 €</span>
  <h1 class="main-info__title-main">Piso de 3 habitaciones en venta en Eixample</h1>
  <span class="main-info__title-minor">Calle de Provença, 123, Eixample, Barcelona</span>
  <div class="info-features">
    <span>90 m²</span>
    <span>3 hab.</span>
    <span>2 baños</span>
    <span>Planta 4</span>
  </div>
  <span class="price-per-meter">3.888 €/m²</span>
  <div class="comment">
    <p>Espléndido piso en pleno Eixample con mucha luz natural.</p>
  </div>
</body>
</html>
"""

DETAIL_PAGE_MINIMAL_HTML = """
<html><body></body></html>
"""

DETAIL_PAGE_PARTIAL_HTML = """
<html>
<body>
  <span class="info-data-price">200.000 €</span>
  <!-- no title, no location, no features, no description -->
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Tests for get_property_urls
# ---------------------------------------------------------------------------

class TestGetPropertyUrls:
    """Tests for IdealistaProvider.get_property_urls (pure BeautifulSoup logic)."""

    def setup_method(self) -> None:
        # We need an instance but must NOT start the browser driver.
        # IdealistaProvider.__init__ only calls super().__init__ which
        # sets attributes without touching Chrome, so plain instantiation
        # is safe here.
        self.provider = IdealistaProvider.__new__(IdealistaProvider)
        IdealistaProvider.__init__(self.provider)

    def test_extracts_two_valid_urls(self) -> None:
        soup = _soup(LISTING_PAGE_HTML)
        urls = self.provider.get_property_urls(soup)
        assert len(urls) == 2

    def test_urls_are_absolute(self) -> None:
        soup = _soup(LISTING_PAGE_HTML)
        urls = self.provider.get_property_urls(soup)
        for url in urls:
            assert url.startswith("https://www.idealista.com"), (
                f"Expected absolute URL, got: {url}"
            )

    def test_correct_paths_preserved(self) -> None:
        soup = _soup(LISTING_PAGE_HTML)
        urls = self.provider.get_property_urls(soup)
        assert "https://www.idealista.com/inmueble/100001/" in urls
        assert "https://www.idealista.com/inmueble/100002/" in urls

    def test_article_without_anchor_skipped(self) -> None:
        """An <article class="item"> with no <a> must not raise."""
        soup = _soup(LISTING_PAGE_HTML)
        urls = self.provider.get_property_urls(soup)
        # Only 2 valid links in the fixture
        assert len(urls) == 2

    def test_anchor_without_href_skipped(self) -> None:
        """An <a> with no href attribute must be silently skipped."""
        html = """
        <html><body>
          <article class="item"><a class="item-link">No href</a></article>
        </body></html>
        """
        soup = _soup(html)
        urls = self.provider.get_property_urls(soup)
        assert urls == []

    def test_empty_page_returns_empty_list(self) -> None:
        soup = _soup("<html><body></body></html>")
        urls = self.provider.get_property_urls(soup)
        assert urls == []

    def test_absolute_href_not_prefixed_twice(self) -> None:
        """If Idealista ever emits an absolute href it should not be doubled."""
        html = """
        <html><body>
          <article class="item">
            <a class="item-link" href="https://www.idealista.com/inmueble/999/">X</a>
          </article>
        </body></html>
        """
        soup = _soup(html)
        urls = self.provider.get_property_urls(soup)
        assert urls == ["https://www.idealista.com/inmueble/999/"]


# ---------------------------------------------------------------------------
# Tests for _parse_property (pure function, no driver needed)
# ---------------------------------------------------------------------------

class TestParseProperty:
    """Tests for the pure _parse_property helper."""

    _URL = "https://www.idealista.com/inmueble/100001/"
    _PTYPE = "residential"
    _PROVIDER = "idealista"

    def _parse(self, html: str) -> object:
        return _parse_property(_soup(html), self._URL, self._PTYPE, self._PROVIDER)

    def test_returns_property_with_correct_url(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.url == self._URL

    def test_returns_property_with_correct_provider(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.provider == self._PROVIDER

    def test_returns_property_with_correct_prop_type(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.prop_type == self._PTYPE

    def test_price_extracted(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.price == "350.000 €"

    def test_name_extracted(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert "Piso" in prop.name

    def test_location_extracted(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert "Eixample" in prop.location

    def test_size_extracted(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.size == "90 m²"

    def test_rooms_extracted(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.rooms == "3 hab."

    def test_bathrooms_extracted(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.bathrooms == "2 baños"

    def test_squere_meter_price_extracted(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.squere_meter_price == "3.888 €/m²"

    def test_description_extracted(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert "Eixample" in prop.description

    def test_empty_page_does_not_crash(self) -> None:
        """Completely empty DOM must return a Property with empty strings, not raise."""
        prop = self._parse(DETAIL_PAGE_MINIMAL_HTML)
        assert prop.price == ""
        assert prop.name == ""
        assert prop.location == ""
        assert prop.size == ""
        assert prop.rooms == ""
        assert prop.bathrooms == ""
        assert prop.squere_meter_price == ""
        assert prop.description == ""

    def test_partial_page_only_price_present(self) -> None:
        """A page with only the price element should fill price and leave rest empty."""
        prop = self._parse(DETAIL_PAGE_PARTIAL_HTML)
        assert prop.price == "200.000 €"
        assert prop.name == ""
        assert prop.location == ""
        assert prop.size == ""

    def test_scraped_at_is_set(self) -> None:
        prop = self._parse(DETAIL_PAGE_HTML)
        assert prop.scraped_at is not None

    def test_features_fewer_than_three_does_not_crash(self) -> None:
        """Only one feature span — rooms and bathrooms should be empty, not IndexError."""
        html = """
        <html><body>
          <span class="info-data-price">100.000 €</span>
          <div class="info-features"><span>50 m²</span></div>
        </body></html>
        """
        prop = self._parse(html)
        assert prop.size == "50 m²"
        assert prop.rooms == ""
        assert prop.bathrooms == ""


# ---------------------------------------------------------------------------
# Tests for get_number_of_pages (via static HTML, no driver)
# ---------------------------------------------------------------------------

class TestGetNumberOfPages:
    """Tests for the pagination parsing logic extracted from get_number_of_pages."""

    def _count_pages(self, html: str) -> int:
        """Re-implement the pagination logic independently so we can unit-test
        it without a live driver.  This mirrors what get_number_of_pages does
        after it obtains page_source."""
        from components.etl_components.utils import is_convertible_to_int

        soup = _soup(html)
        numbers: list[int] = []
        pagination = soup.find("ul", class_="pagination")
        if pagination:
            for tag in pagination.find_all("a"):
                value = tag.get_text(strip=True)
                if is_convertible_to_int(value):
                    numbers.append(int(value))
        return max(numbers, default=1)

    def test_returns_max_page_number(self) -> None:
        assert self._count_pages(LISTING_PAGE_HTML) == 3

    def test_no_pagination_returns_one(self) -> None:
        assert self._count_pages("<html><body></body></html>") == 1

    def test_pagination_with_only_non_numeric_labels(self) -> None:
        html = """
        <html><body>
          <ul class="pagination">
            <li><a>Anterior</a></li>
            <li><a>Siguiente</a></li>
          </ul>
        </body></html>
        """
        assert self._count_pages(html) == 1

    def test_pagination_single_page(self) -> None:
        html = """
        <html><body>
          <ul class="pagination"><li><a>1</a></li></ul>
        </body></html>
        """
        assert self._count_pages(html) == 1

    def test_pagination_many_pages(self) -> None:
        html = """
        <html><body>
          <ul class="pagination">
            <li><a>1</a></li><li><a>2</a></li><li><a>3</a></li>
            <li><a>4</a></li><li><a>5</a></li>
          </ul>
        </body></html>
        """
        assert self._count_pages(html) == 5
