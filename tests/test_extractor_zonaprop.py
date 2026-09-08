from pathlib import Path

import pytest

from app.exceptions import ExtractionError
from app.extractors.zonaprop import ZonaPropExtractor, extract_aviso_info

FIXTURE = Path(__file__).parent / "fixtures_zonaprop_real.html"
REAL_HTML = FIXTURE.read_text(encoding="utf-8")
REAL_URL = (
    "https://www.zonaprop.com.ar/propiedades/clasificado/"
    "alclocin-oficinas-corporativas-en-alquiler-cecilia-grierson-49793701.html"
)


def test_extract_aviso_info_parses_real_block():
    info = extract_aviso_info(REAL_HTML)
    assert info["idAviso"] == "49793701"
    assert info["postingTitle"].startswith("Oficinas Corporativas")
    assert info["pricesData"][0]["prices"][0]["amount"] == 7536


def test_extract_aviso_info_raises_without_marker():
    with pytest.raises(ExtractionError):
        extract_aviso_info("<html><body>nada</body></html>")


def test_zonaprop_extractor_full_property():
    extractor = ZonaPropExtractor()
    prop = extractor.parse(REAL_HTML, REAL_URL)

    assert prop.title == (
        "Oficinas Corporativas en Alquiler - Cecilia Grierson 222 Piso 3 Oficina B"
    )
    assert prop.operation == "alquiler"
    assert prop.price == 7536
    assert prop.currency == "USD"
    assert prop.expenses == 2167430.0
    assert prop.type == "Oficina comercial"
    assert prop.location.neighborhood == "Puerto Madero"
    assert prop.location.city == "Capital Federal"
    assert prop.location.address == "Cecilia Grierson al 200"
    assert prop.area_total == 379.0
    assert prop.area_covered == 314.0
    assert prop.bathrooms == 3
    assert len(prop.images) == 2
    assert prop.images[0].endswith("1812851376.jpg?isFirstImage=true")
    assert "Miranda Bosch Real Estate & Art" in prop.features[0]
    assert prop.source.portal == "zonaprop"
    assert "Dique-Río" in prop.description
    # el apostrofe de "Río" (dentro de comillas dobles) no debe romper el parseo
    assert "próximo a Buquebus" in prop.description


def test_zonaprop_extractor_raises_when_no_avisoinfo():
    extractor = ZonaPropExtractor()
    with pytest.raises(ExtractionError):
        extractor.parse("<html><body>vacio</body></html>", REAL_URL)


def test_factory_routes_zonaprop_domain_to_dedicated_extractor():
    from app.extractors import get_extractor

    extractor = get_extractor(REAL_URL)
    assert isinstance(extractor, ZonaPropExtractor)
