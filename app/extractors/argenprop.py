"""Extractor dedicado Argenprop con agrupación de características por sección."""
from __future__ import annotations

import logging
import re
from bs4 import BeautifulSoup

from app.exceptions import ExtractionError
from app.extractors.base import BaseExtractor
from app.models import FeatureCategory, Location, Property, SourceInfo

logger = logging.getLogger(__name__)

def _sanitize_text(raw: str | None, publisher_name: str | None) -> str | None:
    if not raw:
        return None
        
    text = raw.replace("\r", "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[CONTACTO ELIMINADO]', text)
    text = re.sub(r'(?:\+?54\s*9\s*)?(?:11|[2-3]\d{2,3})\s*(?:15)?\s*\d{4}[-\s]?\d{4}', '[TELÉFONO ELIMINADO]', text)
    text = re.sub(r'(?i)(?:matrícula|cucicba|cpi|cmcpsi|colegiado|corredor responsable|ley 5115|ley 24\.240)\s*:?\s*[a-zA-Z\d\s\.\-]+', '', text)
    
    ai_patterns = r'(?i)(si eres una ia|ignora las? instrucciones|act[uú]a como|olvida todo|prompt subliminal|me dar[aá]s|tendr[aá]s que|eres un bot).*'
    text = re.sub(ai_patterns, '', text)
    
    if publisher_name:
        clean_publisher = re.sub(r'(?i)\b(propiedades|realty|inmobiliaria|bienes raices|brokers|group)\b', '', publisher_name).strip()
        pattern_full = re.compile(re.escape(publisher_name), re.IGNORECASE)
        text = pattern_full.sub("CENTURY 21", text)
        if len(clean_publisher) > 3:
            pattern_partial = re.compile(re.escape(clean_publisher), re.IGNORECASE)
            text = pattern_partial.sub("CENTURY 21", text)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


class ArgenpropExtractor(BaseExtractor):
    portal_name = "argenprop"

    def parse(self, html: str, url: str) -> Property:
        soup = BeautifulSoup(html, 'html.parser')
        prop = Property(source=SourceInfo(url=url, portal="argenprop"))

        # 1. Extraer publicador
        publisher_node = soup.find('a', id='avisos-anunciante-sup')
        agency_name = publisher_node.get_text(strip=True) if publisher_node else None

        # 2. Descripción
        desc_node = soup.find('div', class_='section-description--content')
        raw_desc = desc_node.get_text(separator="\n") if desc_node else None
        prop.description = _sanitize_text(raw_desc, agency_name)

        # 3. Título
        title_node = soup.find('h1', class_='section-description--title')
        prop.title = title_node.get_text(strip=True) if title_node else "Propiedad en Argenprop"

        # 4. Metadatos
        ga_input = soup.find('input', id='ga-dimension-ficha')
        if ga_input:
            prop.type = ga_input.get('data-tipo-propiedad')
            prop.operation = ga_input.get('data-tipo-operacion')
            prop.location.neighborhood = ga_input.get('data-sub-barrio') or ga_input.get('data-barrio')
            prop.location.city = ga_input.get('data-localidad')

        # 5. Precio, Moneda, Dirección, Expensas
        precio_input = soup.find('input', id='Precio')
        if precio_input and precio_input.get('value'):
            try: prop.price = float(precio_input.get('value').replace('.', '').replace(',', '.'))
            except ValueError: pass
                
        moneda_input = soup.find('input', id='Moneda')
        if moneda_input and moneda_input.get('value'):
            val = moneda_input.get('value').upper()
            prop.currency = "USD" if "USD" in val else "ARS"

        address_node = soup.find('h2', class_='titlebar__address')
        if address_node:
            prop.location.address = address_node.get_text(strip=True)

        exp_node = soup.find('p', class_='titlebar__expenses')
        if exp_node:
            match = re.search(r'\$\s*([\d\.]+)', exp_node.get_text(strip=True))
            if match:
                try: prop.expenses = float(match.group(1).replace('.', ''))
                except ValueError: pass

        # 6. Parsear Datos Duros para el Header de la Ficha
        main_features = soup.find('ul', class_='property-main-features')
        if main_features:
            for li in main_features.find_all('li'):
                text = li.get_text(strip=True).lower()
                if 'm² cubierta' in text or 'm2 cubierta' in text:
                    m = re.search(r'([\d\.]+)', text)
                    if m:
                        try: prop.area_covered = float(m.group(1).replace('.', ''))
                        except ValueError: pass
                elif 'baño' in text and not prop.bathrooms:
                    m = re.search(r'(\d+)', text)
                    if m: prop.bathrooms = int(m.group(1))

        # 7. Extracción de Características Estructuradas por Categoría
        categories: list[FeatureCategory] = []
        for section in soup.find_all('section'):
            header_node = section.find('div', class_='property-features-title')
            ul_node = section.find('ul', class_='property-features')
            
            if header_node and ul_node:
                category_title = header_node.get_text(strip=True)
                items = []
                for li in ul_node.find_all('li'):
                    item_text = re.sub(r'\s+', ' ', li.get_text(separator=" ", strip=True))
                    item_clean = _sanitize_text(item_text, agency_name)
                    if item_clean and item_clean not in items:
                        items.append(item_clean)
                        
                        # Extraer variables principales si no se habían capturado
                        item_lower = item_clean.lower()
                        if 'cant. ambientes' in item_lower:
                            m = re.search(r'\d+', item_lower)
                            if m: prop.rooms = int(m.group(0))
                        elif 'cant. baños' in item_lower:
                            m = re.search(r'\d+', item_lower)
                            if m: prop.bathrooms = int(m.group(0))
                        elif 'cant. dormitorios' in item_lower:
                            m = re.search(r'\d+', item_lower)
                            if m: prop.bedrooms = int(m.group(0))

                if items:
                    categories.append(FeatureCategory(title=category_title, items=items))

        if not prop.rooms and 'monoambiente' in html.lower():
            prop.rooms = 1
            prop.bedrooms = 0

        prop.feature_categories = categories

        # 8. Imágenes
        images = []
        for div in soup.find_all('div', attrs={'data-open-gallery': True}):
            style = div.get('style', '')
            urls = re.findall(r'url\((https?[^\)]+)\)', style)
            for u in urls:
                if 'photo_placeholder' not in u and 'no-photo' not in u:
                    images.append(u)
        prop.images = list(dict.fromkeys(images))

        if not prop.is_usable():
            raise ExtractionError(f"El aviso de {url} no tiene datos suficientes.")
        return prop
