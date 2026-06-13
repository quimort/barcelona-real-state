from bs4 import BeautifulSoup

from etl.extraction.habitaclia import HabitacliaProvider, _parse_property

LISTING_HTML = """
<html><body>
  <div class="list-item-info"><a href="https://www.habitaclia.com/p1.htm">one</a></div>
  <div class="list-item-info"><a href="https://www.habitaclia.com/p2.htm">two</a></div>
  <div class="list-item-info"><span>no anchor here</span></div>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <div class="price"><span itemprop="price">350.000 €</span></div>
  <div class="summary-left">
    <h1>Piso en venta en Eixample</h1>
    <article class="location"><a>Eixample, Barcelona</a></article>
  </div>
  <ul class="feature-container">
    <li><strong>350.000 €</strong></li>
    <li><strong>90 m²</strong></li>
    <li><strong>3 hab.</strong></li>
    <li><strong>2 baños</strong></li>
  </ul>
  <p id="js-detail-description">Bright flat near the center.</p>
</body></html>
"""


def test_get_property_urls_extracts_only_valid_anchors():
    provider = HabitacliaProvider()
    soup = BeautifulSoup(LISTING_HTML, "html.parser")
    urls = provider.get_property_urls(soup)
    assert sorted(urls) == [
        "https://www.habitaclia.com/p1.htm",
        "https://www.habitaclia.com/p2.htm",
    ]


def test_parse_property_full_page():
    soup = BeautifulSoup(DETAIL_HTML, "html.parser")
    prop = _parse_property(soup, "https://www.habitaclia.com/p1.htm", "residential", "habitaclia")
    assert prop.price == "350.000 €"
    assert prop.name == "Piso en venta en Eixample"
    assert prop.location == "Eixample, Barcelona"
    assert prop.size == "90 m²"
    assert prop.rooms == "3 hab."
    assert prop.bathrooms == "2 baños"
    assert prop.description == "Bright flat near the center."
    assert prop.provider == "habitaclia"
    assert prop.url == "https://www.habitaclia.com/p1.htm"
    assert prop.scraped_at is not None


def test_parse_property_missing_elements_does_not_crash():
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    prop = _parse_property(soup, "https://x", "residential", "habitaclia")
    assert prop.price == ""
    assert prop.name == ""
    assert prop.location == ""
    assert prop.size == ""
    assert prop.url == "https://x"


def test_parse_property_partial_features():
    html = '<ul class="feature-container"><li><strong>75 m²</strong></li></ul>'
    soup = BeautifulSoup(html, "html.parser")
    prop = _parse_property(soup, "u", "residential", "habitaclia")
    assert prop.size == "75 m²"
    assert prop.rooms == ""
    assert prop.bathrooms == ""
