"""Extractor universal: sirve como fallback para 'cualquier portal'.

Orden de intento (de más confiable a menos):
1. JSON-LD (schema.org Product / Offer / RealEstateListing)
2. OpenGraph meta tags
3. Heurística sobre <title>/<h1>/texto plano (regex de precio)
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.exceptions import ExtractionError
from app.extractors.base import BaseExtractor
from app.models import Location, Property, SourceInfo

logger = logging.getLogger(__name__)

PRICE_RE = re.compile(
    r"(USD|US\$|U\$S|\$)\s*([\d\.,]{4,})", re.IGNORECASE
)
ROOMS_RE = re.compile(r"(\d+)\s*amb", re.IGNORECASE)
BEDROOMS_RE = re.compile(r"(\d+)\s*dorm", re.IGNORECASE)
BATHROOMS_RE = re.compile(r"(\d+)\s*ba(ñ|n)os?", re.IGNORECASE)
AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m2|m²", re.IGNORECASE)


def _portal_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for known in ("zonaprop", "argenprop", "mercadolibre", "remax", "tokko"):
        if known in host:
            return known
    return host or "desconocido"


def _parse_price(raw: str) -> tuple[float | None, str | None]:
    m = PRICE_RE.search(raw)
    if not m:
        return None, None
    currency_raw, number_raw = m.group(1), m.group(2)
    currency = "USD" if currency_raw.upper() in ("USD", "US$", "U$S") else "ARS"
    number = number_raw.replace(".", "").replace(",", ".")
    try:
        return float(number), currency
    except ValueError:
        return None, currency


class GenericExtractor(BaseExtractor):
    portal_name = "generic"

    def parse(self, html: str, url: str) -> Property:
        soup = BeautifulSoup(html, "lxml")
        prop = Property(source=SourceInfo(url=url, portal=_portal_from_url(url)))

        self._apply_json_ld(soup, prop)
        self._apply_opengraph(soup, prop)
        self._apply_heuristics(soup, prop)

        if not prop.is_usable():
            raise ExtractionError(
                f"No se pudo extraer info suficiente de {url} "
                "(sin precio, sin título/descripción, sin imágenes)"
            )
        return prop

    # -- nivel 1: JSON-LD -------------------------------------------------
    def _apply_json_ld(self, soup: BeautifulSoup, prop: Property) -> None:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                self._merge_json_ld_item(item, prop)

    def _merge_json_ld_item(self, item: dict, prop: Property) -> None:
        name = item.get("name")
        if name and not prop.title:
            prop.title = str(name)

        desc = item.get("description")
        if desc and not prop.description:
            prop.description = str(desc)

        offers = item.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price")
            currency = offers.get("priceCurrency")
            if price is not None and prop.price is None:
                try:
                    prop.price = float(str(price).replace(",", ""))
                except ValueError:
                    pass
            if currency and not prop.currency:
                prop.currency = str(currency)

        images = item.get("image")
        if images and not prop.images:
            if isinstance(images, str):
                prop.images = [images]
            elif isinstance(images, list):
                prop.images = [str(i) for i in images if isinstance(i, (str,))]

        address = item.get("address")
        if isinstance(address, dict):
            prop.location.city = prop.location.city or address.get("addressLocality")
            prop.location.address = prop.location.address or address.get("streetAddress")

    # -- nivel 2: OpenGraph -------------------------------------------------
    def _apply_opengraph(self, soup: BeautifulSoup, prop: Property) -> None:
        def og(prop_name: str) -> str | None:
            tag = soup.find("meta", property=f"og:{prop_name}")
            return tag.get("content") if tag else None

        if not prop.title:
            prop.title = og("title")
        if not prop.description:
            prop.description = og("description")
        if not prop.images:
            img = og("image")
            if img:
                prop.images = [img]

    # -- nivel 3: heurística sobre texto plano ------------------------------
    def _apply_heuristics(self, soup: BeautifulSoup, prop: Property) -> None:
        text = soup.get_text(" ", strip=True)

        if prop.price is None:
            price, currency = _parse_price(text)
            prop.price = price
            prop.currency = prop.currency or currency

        if prop.rooms is None:
            m = ROOMS_RE.search(text)
            if m:
                prop.rooms = int(m.group(1))

        if prop.bedrooms is None:
            m = BEDROOMS_RE.search(text)
            if m:
                prop.bedrooms = int(m.group(1))

        if prop.bathrooms is None:
            m = BATHROOMS_RE.search(text)
            if m:
                prop.bathrooms = int(m.group(1))

        if prop.area_total is None:
            m = AREA_RE.search(text)
            if m and m.group(1):
                try:
                    prop.area_total = float(m.group(1).replace(",", "."))
                except ValueError:
                    pass

        if not prop.title:
            h1 = soup.find("h1")
            if h1:
                prop.title = h1.get_text(strip=True)

        if not prop.title and soup.title:
            prop.title = soup.title.get_text(strip=True)
