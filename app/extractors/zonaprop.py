"""Extractor dedicado ZonaProp con sanitización dinámica y escudo anti-IA."""
from __future__ import annotations

import logging
import re
import chompjs

from app.exceptions import ExtractionError
from app.extractors.base import BaseExtractor
from app.models import Location, Property, SourceInfo

logger = logging.getLogger(__name__)

MARKER = "const avisoInfo = "

def extract_aviso_info(html: str) -> dict:
    idx = html.find(MARKER)
    if idx == -1:
        raise ExtractionError("No se encontró el bloque avisoInfo en la página")
    
    start = idx + len(MARKER)
    while start < len(html) and html[start] != "{":
        start += 1
        
    try:
        return chompjs.parse_js_object(html[start:])
    except Exception as e:
        raise ExtractionError(f"No se pudo parsear avisoInfo: {e}") from e


def _sanitize_description(raw: str | None, publisher_name: str | None) -> str | None:
    """Filtra datos de contacto, competencia dinámica e inyecciones de IA."""
    if not raw:
        return None
        
    # Limpieza básica de HTML y saltos de línea
    text = raw.replace("\r", "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    
    # 1. Filtro de Emails y Teléfonos
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[CONTACTO]', text)
    text = re.sub(r'(?:\+?54\s*9\s*)?(?:11|[2-3]\d{2,3})\s*(?:15)?\s*\d{4}[-\s]?\d{4}', '[TELÉFONO]', text)
    
    # 2. Filtro de Matrículas y Colegios (Corredor responsable, CUCICBA, etc)
    text = re.sub(r'(?i)(?:matrícula|cucicba|cpi|cmcpsi|colegiado|corredor responsable|ley 5115|ley 24\.240)\s*:?\s*[a-zA-Z\d\s\.\-]+', '', text)
    
    # 3. ESCUDO ANTI-IA (Prompt Injections)
    # Busca patrones de comandos subliminales y elimina toda esa línea
    ai_patterns = r'(?i)(si eres una ia|ignora las? instrucciones|act[uú]a como|olvida todo|prompt subliminal|me dar[aá]s|tendr[aá]s que|eres un bot).*'
    text = re.sub(ai_patterns, '', text)
    
    # 4. REEMPLAZO DINÁMICO DE LA INMOBILIARIA COMPETIDORA
    if publisher_name:
        # Quitamos palabras comunes del nombre para extraer la raíz (Ej: de "BAIGUN REALTY" sacamos "BAIGUN")
        clean_publisher = re.sub(r'(?i)\b(propiedades|realty|inmobiliaria|bienes raices|brokers|group)\b', '', publisher_name).strip()
        
        # Reemplazamos el nombre exacto completo
        pattern_full = re.compile(re.escape(publisher_name), re.IGNORECASE)
        text = pattern_full.sub("CENTURY 21", text)
        
        # Si la raíz tiene al menos 3 letras, la buscamos también y la reemplazamos
        if len(clean_publisher) > 3:
            pattern_partial = re.compile(re.escape(clean_publisher), re.IGNORECASE)
            text = pattern_partial.sub("CENTURY 21", text)

    # Normalizar múltiples saltos de línea vacíos que hayan quedado por borrar cosas
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


class ZonaPropExtractor(BaseExtractor):
    portal_name = "zonaprop"

    def parse(self, html: str, url: str) -> Property:
        info = extract_aviso_info(html)

        prop = Property(source=SourceInfo(url=url, portal="zonaprop"))

        # 1. Extraemos PRIMERO el publicador para usarlo como filtro
        publisher = info.get("publisher") or {}
        agency_name = publisher.get("name")

        # 2. Pasamos el nombre del competidor al sanitizador
        prop.title = info.get("postingTitle") or info.get("generatedTitle")
        prop.description = _sanitize_description(info.get("description"), agency_name)

        prices = info.get("pricesData") or []
        if prices:
            first = prices[0]
            prop.operation = (first.get("operationType") or {}).get("name")
            offer_prices = first.get("prices") or []
            if offer_prices:
                prop.price = offer_prices[0].get("amount")
                prop.currency = offer_prices[0].get("isoCode") or offer_prices[0].get("currency")

        expenses = info.get("expenses")
        if expenses not in (None, ""):
            try:
                prop.expenses = float(expenses)
            except (TypeError, ValueError):
                pass

        real_estate_type = info.get("realEstateType") or {}
        prop.type = real_estate_type.get("name")

        location = info.get("location") or {}
        prop.location.neighborhood = location.get("name")
        parent = location.get("parent") or {}
        prop.location.city = parent.get("name")
        address = info.get("address") or {}
        prop.location.address = address.get("name")

        main_features = info.get("mainFeatures") or {}
        area_total = main_features.get("CFT100")
        if area_total and area_total.get("value"):
            try:
                prop.area_total = float(str(area_total["value"]).replace(",", "."))
            except ValueError:
                pass
        area_cub = main_features.get("CFT101")
        if area_cub and area_cub.get("value"):
            try:
                prop.area_covered = float(str(area_cub["value"]).replace(",", "."))
            except ValueError:
                pass
        bathrooms = main_features.get("CFT3")
        if bathrooms and bathrooms.get("value"):
            try:
                prop.bathrooms = int(bathrooms["value"])
            except ValueError:
                pass
        bedrooms = main_features.get("CFT2")
        if bedrooms and bedrooms.get("value"):
            try:
                prop.bedrooms = int(bedrooms["value"])
            except ValueError:
                pass
        rooms = main_features.get("CFT1") or main_features.get("CFT6")
        if rooms and rooms.get("value"):
            try:
                prop.rooms = int(rooms["value"])
            except ValueError:
                pass

        pictures = info.get("pictures") or []
        images: list[str] = []
        for pic in pictures:
            img = pic.get("url1200x1200") or pic.get("url730x532")
            if img:
                images.append(img)
        prop.images = images

        if not prop.is_usable():
            raise ExtractionError(f"avisoInfo de {url} no tiene datos suficientes")
        return prop
