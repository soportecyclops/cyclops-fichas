"""Extractor dedicado MercadoLibre con agrupación de características y escudo anti-IA."""
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

    return re.sub(r"\n{3,}", "\n\n", text).strip() or None


class MercadoLibreExtractor(BaseExtractor):
    portal_name = "mercadolibre"

    def parse(self, html: str, url: str) -> Property:
        soup = BeautifulSoup(html, 'html.parser')
        prop = Property(source=SourceInfo(url=url, portal="mercadolibre"))

        # 1. Publicador
        seller_node = soup.find('div', class_='ui-vip-profile-info__info-link')
        agency_name = seller_node.find('h3').get_text(strip=True) if seller_node and seller_node.find('h3') else None

        # 2. Descripción
        desc_node = soup.find('p', class_='ui-pdp-description__content')
        prop.description = _sanitize_text(desc_node.get_text(separator="\n") if desc_node else None, agency_name)

        # 3. Título
        title_node = soup.find('h1', class_='ui-pdp-title')
        prop.title = title_node.get_text(strip=True) if title_node else "Propiedad en MercadoLibre"

        # 4. Precio y Moneda
        price_container = soup.find('div', class_='ui-pdp-price__second-line')
        if price_container:
            frac = price_container.find('span', class_='andes-money-amount__fraction')
            if frac:
                try: prop.price = float(frac.get_text(strip=True).replace('.', '').replace(',', '.'))
                except ValueError: pass
            
            curr = price_container.find('span', class_='andes-money-amount__currency-symbol')
            if curr:
                val = curr.get_text(strip=True).upper()
                prop.currency = "USD" if "U" in val or "S$" in val else "ARS"

        # 5. Ubicación
        loc_node = soup.find('p', class_='ui-pdp-media__title') or soup.find('a', class_='ui-pdp-seller-validated__title')
        if loc_node:
            parts = [p.strip() for p in loc_node.get_text(strip=True).split(',')]
            prop.location.address = parts[0] if parts else ""
            if len(parts) > 1: prop.location.neighborhood = parts[1]
            if len(parts) > 2: prop.location.city = parts[2]

        # 6. Características Estructuradas
        categories: list[FeatureCategory] = []
        features_list = []
        
        tables = soup.find_all('div', class_='ui-vpp-striped-specs__table')
        for table in tables:
            header = table.find('h3', class_='ui-vpp-striped-specs__header')
            cat_title = header.get_text(strip=True) if header else "General"
            items = []
            
            for row in table.find_all('tr', class_='ui-vpp-striped-specs__row'):
                th = row.find('th')
                td = row.find('td')
                if th and td:
                    k = th.get_text(strip=True)
                    v = td.get_text(strip=True)
                    item_str = f"{k}: {v}"
                    item_clean = _sanitize_text(item_str, agency_name)
                    
                    if item_clean and item_clean not in items:
                        items.append(item_clean)
                        features_list.append(item_clean)
                        
                        k_low = k.lower()
                        if 'superficie cubierta' in k_low:
                            m = re.search(r'([\d\.]+)', v)
                            if m:
                                try: prop.area_covered = float(m.group(1).replace('.', ''))
                                except ValueError: pass
                        elif 'superficie total' in k_low:
                            m = re.search(r'([\d\.]+)', v)
                            if m:
                                try: prop.area_total = float(m.group(1).replace('.', ''))
                                except ValueError: pass
                        elif 'dormitorios' in k_low:
                            m = re.search(r'\d+', v)
                            if m: prop.bedrooms = int(m.group(0))
                        elif 'baños' in k_low:
                            m = re.search(r'\d+', v)
                            if m: prop.bathrooms = int(m.group(0))
                        elif 'ambientes' in k_low:
                            m = re.search(r'\d+', v)
                            if m: prop.rooms = int(m.group(0))
                        elif 'expensas' in k_low:
                            m = re.search(r'([\d\.]+)', v)
                            if m:
                                try: prop.expenses = float(m.group(1).replace('.', ''))
                                except ValueError: pass
                        elif 'tipo de casa' in k_low or 'tipo de unidad' in k_low:
                            prop.type = v

            if items:
                categories.append(FeatureCategory(title=cat_title, items=items))

        prop.feature_categories = categories
        prop.features = features_list

        # 7. Imágenes
        images = []
        for figure in soup.find_all('figure', class_='gallery-image'):
            img = figure.find('img')
            if img:
                src = img.get('src') or img.get('data-src')
                if src and 'data:image' not in src:
                    images.append(src)
        
        prop.images = list(dict.fromkeys(images))

        if not prop.is_usable():
            raise ExtractionError(f"El aviso de {url} no tiene datos suficientes.")
        return prop
