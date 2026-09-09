"""Factory de extractores."""
from __future__ import annotations

from urllib.parse import urlparse

from app.extractors.base import BaseExtractor
from app.extractors.generic import GenericExtractor
from app.extractors.zonaprop import ZonaPropExtractor
from app.extractors.argenprop import ArgenpropExtractor
from app.extractors.mercadolibre import MercadoLibreExtractor
from app.extractors.remax import RemaxExtractor

PORTAL_EXTRACTORS: dict[str, type[BaseExtractor]] = {
    "zonaprop": ZonaPropExtractor,
    "argenprop": ArgenpropExtractor,
    "mercadolibre": MercadoLibreExtractor,
    "remax": RemaxExtractor,
}

def get_extractor(url: str) -> BaseExtractor:
    host = urlparse(url).netloc.lower()
    for key, extractor_cls in PORTAL_EXTRACTORS.items():
        if key in host:
            return extractor_cls()
    return GenericExtractor()
