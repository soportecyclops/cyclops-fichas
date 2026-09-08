import httpx
import pytest

from app.exceptions import ExtractionError, FetchError, InvalidURLError
from app.extractors.base import fetch_html
from app.extractors.generic import GenericExtractor

JSON_LD_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@type": "Product",
  "name": "Depto 3 amb Villa Devoto",
  "description": "Excelente departamento con balcon",
  "image": ["https://cdn.example.com/foto1.jpg"],
  "offers": {"price": "125000", "priceCurrency": "USD"}
}
</script>
</head><body><h1>Depto 3 amb Villa Devoto</h1></body></html>
"""

OG_ONLY_HTML = """
<html><head>
<meta property="og:title" content="Casa en Palermo">
<meta property="og:description" content="Casa 4 ambientes con jardin">
<meta property="og:image" content="https://cdn.example.com/casa.jpg">
</head><body></body></html>
"""

HEURISTIC_HTML = """
<html><head><title>Aviso sin metadata</title></head>
<body><h1>PH en Caballito</h1>
<p>Excelente PH de 3 ambientes, 2 dormitorios, 1 baño, 65 m2. Precio USD 95.000</p>
</body></html>
"""

EMPTY_HTML = "<html><head></head><body><p>" + ("x" * 250) + "</p></body></html>"


def test_parse_json_ld_extracts_full_data():
    extractor = GenericExtractor()
    prop = extractor.parse(JSON_LD_HTML, "https://www.zonaprop.com.ar/aviso-1")
    assert prop.title == "Depto 3 amb Villa Devoto"
    assert prop.price == 125000.0
    assert prop.currency == "USD"
    assert prop.images == ["https://cdn.example.com/foto1.jpg"]
    assert prop.source.portal == "zonaprop"


def test_parse_opengraph_fallback():
    extractor = GenericExtractor()
    prop = extractor.parse(OG_ONLY_HTML, "https://www.argenprop.com/aviso-2")
    assert prop.title == "Casa en Palermo"
    assert "jardin" in prop.description
    assert prop.images == ["https://cdn.example.com/casa.jpg"]


def test_parse_heuristics_fallback_extracts_rooms_and_price():
    extractor = GenericExtractor()
    prop = extractor.parse(HEURISTIC_HTML, "https://www.otroportal.com/aviso-3")
    assert prop.rooms == 3
    assert prop.bedrooms == 2
    assert prop.bathrooms == 1
    assert prop.area_total == 65.0
    assert prop.price == 95000.0
    assert prop.currency == "USD"


def test_parse_raises_extraction_error_when_no_usable_data():
    extractor = GenericExtractor()
    with pytest.raises(ExtractionError):
        extractor.parse(EMPTY_HTML, "https://www.vacio.com/nada")


def test_fetch_html_rejects_invalid_url():
    with pytest.raises(InvalidURLError):
        fetch_html("no-es-una-url")


def test_fetch_html_wraps_network_errors(monkeypatch):
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            raise httpx.ConnectTimeout("timeout simulado")

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: FakeClient())
    with pytest.raises(FetchError):
        fetch_html("https://portal-caido.com/aviso")
