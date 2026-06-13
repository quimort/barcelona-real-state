"""Unit tests for etl/extraction/fotocasa.py.

All tests are fully offline — no browser is started, no network calls are made.
The HTML fixtures below are minimal representations that mimic Fotocasa's known
DOM structure.  Because the selectors in fotocasa.py are best-effort (marked
TODO), these tests also serve as living documentation of what the parser expects.
"""

import sys
import os
import types

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the module under test.
# undetected_chromedriver and selenium are not available in CI test runners,
# so we inject lightweight stubs into sys.modules.
# ---------------------------------------------------------------------------

def _make_stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _ensure_stubs() -> None:
    """Create minimal stubs for selenium / undetected_chromedriver."""
    if "undetected_chromedriver" not in sys.modules:
        uc = _make_stub_module("undetected_chromedriver")
        uc.Chrome = object  # type: ignore[attr-defined]
        uc.ChromeOptions = object  # type: ignore[attr-defined]

    selenium_mods = [
        "selenium",
        "selenium.webdriver",
        "selenium.webdriver.common",
        "selenium.webdriver.common.by",
        "selenium.webdriver.common.action_chains",
        "selenium.webdriver.common.keys",
        "selenium.webdriver.support",
        "selenium.webdriver.support.expected_conditions",
        "selenium.webdriver.support.ui",
    ]
    for mod_name in selenium_mods:
        if mod_name not in sys.modules:
            _make_stub_module(mod_name)

    # Provide the actual names the modules use
    by_mod = sys.modules["selenium.webdriver.common.by"]
    if not hasattr(by_mod, "By"):
        class _By:
            ID = "id"
            CSS_SELECTOR = "css selector"
            XPATH = "xpath"
        by_mod.By = _By  # type: ignore[attr-defined]

    keys_mod = sys.modules["selenium.webdriver.common.keys"]
    if not hasattr(keys_mod, "Keys"):
        class _Keys:
            PAGE_DOWN = ""
        keys_mod.Keys = _Keys  # type: ignore[attr-defined]

    ac_mod = sys.modules["selenium.webdriver.common.action_chains"]
    if not hasattr(ac_mod, "ActionChains"):
        class _ActionChains:
            def __init__(self, driver: object) -> None: ...
            def key_down(self, key: str) -> "_ActionChains": return self
            def key_up(self, key: str) -> "_ActionChains": return self
            def perform(self) -> None: ...
        ac_mod.ActionChains = _ActionChains  # type: ignore[attr-defined]

    ec_mod = sys.modules["selenium.webdriver.support.expected_conditions"]
    if not hasattr(ec_mod, "element_to_be_clickable"):
        ec_mod.element_to_be_clickable = lambda *a, **k: None  # type: ignore[attr-defined]

    ui_mod = sys.modules["selenium.webdriver.support.ui"]
    if not hasattr(ui_mod, "WebDriverWait"):
        class _WebDriverWait:
            def __init__(self, driver: object, timeout: float) -> None: ...
            def until(self, condition: object) -> object: return object()
        ui_mod.WebDriverWait = _WebDriverWait  # type: ignore[attr-defined]

    wd_mod = sys.modules["selenium.webdriver"]
    if not hasattr(wd_mod, "Chrome"):
        wd_mod.Chrome = object  # type: ignore[attr-defined]


_ensure_stubs()

# Now safe to import project code
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from bs4 import BeautifulSoup

from etl.extraction.fotocasa import FotocasaProvider, _parse_property


# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

LISTING_PAGE_HTML_DATA_HREF = """
<html><body>
  <article data-href="/es/comprar/viviendas/barcelona-capital/piso-123456">
    <div class="re-CardPackMinimalist-title">Piso en Eixample</div>
  </article>
  <article data-href="/es/comprar/viviendas/barcelona-capital/piso-789012">
    <div class="re-CardPackMinimalist-title">Piso en Gràcia</div>
  </article>
</body></html>
"""

LISTING_PAGE_HTML_ANCHOR = """
<html><body>
  <a class="re-CardPackMinimalist-info" href="/es/comprar/viviendas/barcelona-capital/piso-111">Card 1</a>
  <a class="re-CardPackMinimalist-info" href="https://www.fotocasa.es/es/comprar/viviendas/barcelona-capital/piso-222">Card 2</a>
</body></html>
"""

LISTING_PAGE_HTML_FALLBACK = """
<html><body>
  <a href="/es/comprar/viviendas/barcelona-capital/piso-aaa">Link A</a>
  <a href="/es/comprar/viviendas/barcelona-capital/piso-bbb">Link B</a>
  <a href="/about">Ignore me</a>
</body></html>
"""

LISTING_PAGE_HTML_NO_URLS = """
<html><body><p>No listings found</p></body></html>
"""

DETAIL_PAGE_FULL = """
<html><body>
  <h1 class="re-DetailHeader-propertyTitle">Espectacular piso en Eixample</h1>
  <span class="re-DetailHeader-price">450.000 €</span>
  <span class="re-DetailHeader-priceByArea">4.500 €/m²</span>
  <span class="re-DetailHeader-location">Eixample, Barcelona</span>
  <ul class="re-DetailFeaturesList">
    <li>
      <span class="re-DetailFeaturesList-featureLabel">Superficie</span>
      <span class="re-DetailFeaturesList-featureValue">100 m²</span>
    </li>
    <li>
      <span class="re-DetailFeaturesList-featureLabel">Habitaciones</span>
      <span class="re-DetailFeaturesList-featureValue">3</span>
    </li>
    <li>
      <span class="re-DetailFeaturesList-featureLabel">Baños</span>
      <span class="re-DetailFeaturesList-featureValue">2</span>
    </li>
  </ul>
  <div class="re-DetailDescription-text">Piso reformado con vistas al patio de manzana.</div>
</body></html>
"""

DETAIL_PAGE_DATA_TESTID = """
<html><body>
  <h1>Piso en Gràcia</h1>
  <span itemprop="price">320.000 €</span>
  <span itemprop="addressLocality">Gràcia, Barcelona</span>
  <span data-testid="feature-surface">75 m²</span>
  <span data-testid="feature-rooms">2</span>
  <span data-testid="feature-bathrooms">1</span>
  <div data-testid="description">Bonito piso en barrio tranquilo.</div>
</body></html>
"""

DETAIL_PAGE_MINIMAL = """
<html><body>
  <h1>Estudio en el Raval</h1>
</body></html>
"""

PAGINATION_HTML = """
<html><body>
  <ul class="sui-MoleculePagination-list">
    <li><a>1</a></li>
    <li><a>2</a></li>
    <li><a>3</a></li>
    <li><a>4</a></li>
    <li><a>5</a></li>
    <li><a>Siguiente</a></li>
  </ul>
</body></html>
"""

PAGINATION_HTML_NO_LIST = """
<html><body>
  <button>1</button>
  <button>2</button>
  <button>3</button>
  <button>Siguiente</button>
</body></html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _provider() -> FotocasaProvider:
    """Return a provider instance without starting the browser."""
    return FotocasaProvider()


# ---------------------------------------------------------------------------
# Tests — get_property_urls
# ---------------------------------------------------------------------------

class TestGetPropertyUrls:
    def test_extracts_urls_from_data_href(self) -> None:
        provider = _provider()
        urls = provider.get_property_urls(_soup(LISTING_PAGE_HTML_DATA_HREF))
        assert len(urls) == 2
        assert all("fotocasa.es" in u or u.startswith("https://") for u in urls)
        assert any("piso-123456" in u for u in urls)
        assert any("piso-789012" in u for u in urls)

    def test_extracts_urls_from_anchor_class(self) -> None:
        provider = _provider()
        urls = provider.get_property_urls(_soup(LISTING_PAGE_HTML_ANCHOR))
        assert len(urls) == 2
        assert any("piso-111" in u for u in urls)
        assert any("piso-222" in u for u in urls)

    def test_absolute_urls_not_doubled(self) -> None:
        """An href that already starts with https:// must not be prefixed again."""
        provider = _provider()
        urls = provider.get_property_urls(_soup(LISTING_PAGE_HTML_ANCHOR))
        for u in urls:
            assert u.count("https://") == 1, f"Double-prefix found: {u}"

    def test_fallback_path_used_when_primary_selectors_absent(self) -> None:
        provider = _provider()
        urls = provider.get_property_urls(_soup(LISTING_PAGE_HTML_FALLBACK))
        # Should capture /es/comprar/ hrefs but not /about
        assert any("piso-aaa" in u for u in urls)
        assert any("piso-bbb" in u for u in urls)
        assert not any("/about" in u for u in urls)

    def test_returns_empty_list_for_no_listings(self) -> None:
        provider = _provider()
        urls = provider.get_property_urls(_soup(LISTING_PAGE_HTML_NO_URLS))
        assert urls == []

    def test_deduplicates_urls(self) -> None:
        """Duplicate hrefs in the page must not produce duplicate entries."""
        html = """
        <html><body>
          <article data-href="/es/comprar/viviendas/barcelona-capital/piso-dup"></article>
          <a class="re-CardPackMinimalist-info" href="/es/comprar/viviendas/barcelona-capital/piso-dup"></a>
        </body></html>
        """
        provider = _provider()
        urls = provider.get_property_urls(_soup(html))
        assert len(urls) == 1


# ---------------------------------------------------------------------------
# Tests — _parse_property (detail-page parsing)
# ---------------------------------------------------------------------------

class TestParseProperty:
    _URL = "https://www.fotocasa.es/es/comprar/viviendas/barcelona-capital/piso-123456"
    _PTYPE = "residential"
    _PROV = "fotocasa"

    def _parse(self, html: str) -> object:
        return _parse_property(_soup(html), self._URL, self._PTYPE, self._PROV)

    def test_full_page_price(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert prop.price == "450.000 €"

    def test_full_page_name(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert prop.name == "Espectacular piso en Eixample"

    def test_full_page_location(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert prop.location == "Eixample, Barcelona"

    def test_full_page_size(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert prop.size == "100 m²"

    def test_full_page_rooms(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert prop.rooms == "3"

    def test_full_page_bathrooms(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert prop.bathrooms == "2"

    def test_full_page_squere_meter_price(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert prop.squere_meter_price == "4.500 €/m²"

    def test_full_page_description(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert "Piso reformado" in prop.description

    def test_full_page_metadata(self) -> None:
        prop = self._parse(DETAIL_PAGE_FULL)
        assert prop.url == self._URL
        assert prop.provider == self._PROV
        assert prop.prop_type == self._PTYPE

    def test_data_testid_fallback_price(self) -> None:
        prop = self._parse(DETAIL_PAGE_DATA_TESTID)
        assert prop.price == "320.000 €"

    def test_data_testid_fallback_location(self) -> None:
        prop = self._parse(DETAIL_PAGE_DATA_TESTID)
        assert prop.location == "Gràcia, Barcelona"

    def test_data_testid_fallback_size(self) -> None:
        prop = self._parse(DETAIL_PAGE_DATA_TESTID)
        assert prop.size == "75 m²"

    def test_data_testid_fallback_rooms(self) -> None:
        prop = self._parse(DETAIL_PAGE_DATA_TESTID)
        assert prop.rooms == "2"

    def test_data_testid_fallback_bathrooms(self) -> None:
        prop = self._parse(DETAIL_PAGE_DATA_TESTID)
        assert prop.bathrooms == "1"

    def test_data_testid_fallback_description(self) -> None:
        prop = self._parse(DETAIL_PAGE_DATA_TESTID)
        assert "Bonito piso" in prop.description

    def test_minimal_page_does_not_crash(self) -> None:
        """A page with almost no data must return a Property with empty strings."""
        prop = self._parse(DETAIL_PAGE_MINIMAL)
        assert prop.name == "Estudio en el Raval"
        assert prop.price == ""
        assert prop.size == ""
        assert prop.rooms == ""
        assert prop.bathrooms == ""
        assert prop.location == ""
        assert prop.description == ""
        assert prop.squere_meter_price == ""

    def test_url_always_passed_through(self) -> None:
        prop = self._parse(DETAIL_PAGE_MINIMAL)
        assert prop.url == self._URL

    def test_returns_property_instance(self) -> None:
        from components.etl_components.property import Property as PropertyClass
        prop = self._parse(DETAIL_PAGE_FULL)
        assert isinstance(prop, PropertyClass)


# ---------------------------------------------------------------------------
# Tests — provider constructor
# ---------------------------------------------------------------------------

class TestFotocasaProviderInit:
    def test_provider_name(self) -> None:
        assert _provider().provider_name == "fotocasa"

    def test_base_url_contains_barcelona(self) -> None:
        assert "barcelona" in _provider().base_url.lower()

    def test_property_type(self) -> None:
        assert _provider().property_type == "residential"

    def test_driver_not_started_on_init(self) -> None:
        assert _provider()._driver is None
