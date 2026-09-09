"""Extractor avanzado MercadoLibre mediante NORDIC JSON y fallback HTML."""
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

def _find_components_by_type(node, type_name):
    """Busca recursivamente dentro del JSON de MercadoLibre."""
    results = []
    if isinstance(node, dict):
        if node.get("type") == type_name:
            results.append(node)
        for v in node.values():
            results.extend(_find_components_by_type(v, type_name))
    elif isinstance(node, list):
        for item in node:
            results.extend(_find_components_by_type(item, type_name))
    return results

class MercadoLibreExtractor(BaseExtractor):
    portal_name = "mercadolibre"

    def parse(self, html: str, url: str) -> Property:
        soup = BeautifulSoup(html, 'html.parser')
        prop = Property(source=SourceInfo(url=url, portal="mercadolibre"))
        
        agency_name = None
        json_data = {}
        
        # --- 1. INTENTAR PARSEO NORDIC (DATOS JSON OCULTOS) ---
        match = re.search(r'<script id="__NORDIC_RENDERING_CTX__"[^>]*>_n\.ctx\.r\s*=\s*(\{.*?\});?</script>', html, re.DOTALL)
        if match:
            import chompjs
            try:
                json_data = chompjs.parse_js_object(match.group(1))
            except Exception as e:
                logger.error(f"Error parseando NORDIC JSON: {e}")

        if json_data:
            initial_state = json_data.get('appProps', {}).get('pageProps', {}).get('initialState', {})
            components_dict = initial_state.get('components', {})

            # A. Extraer Inmobiliaria para Sanitizar
            sellers = _find_components_by_type(components_dict, "seller_profile")
            if sellers:
                agency_name = sellers[0].get("seller_name", {}).get("title", {}).get("text")
                
            # B. Extraer Descripción
            descs = _find_components_by_type(components_dict, "description")
            if descs:
                prop.description = _sanitize_text(descs[0].get("content"), agency_name)
                
            # C. Extraer Título
            headers = _find_components_by_type(components_dict, "header")
            if headers:
                prop.title = headers[0].get("title")
                
            # D. Extraer Precio
            prices = _find_components_by_type(components_dict, "price")
            if prices:
                p_data = prices[0].get("price", {})
                prop.price = p_data.get("value")
                prop.currency = p_data.get("currency_id")
                
            # E. Extraer Ubicación
            locations = _find_components_by_type(components_dict, "location_and_points")
            if locations:
                loc = locations[0]
                prop.location.address = loc.get("item_address")
                prop.location.city = loc.get("item_location")

            # F. Extraer Características Exactas por Tablas
            tech_specs = _find_components_by_type(components_dict, "technical_specifications")
            categories = []
            features_list = []
            if tech_specs:
                for spec in tech_specs[0].get("specs", []):
                    cat_title = spec.get("title", "Características")
                    items = []
                    for attr in spec.get("attributes", []):
                        k = attr.get("id", "")
                        v = attr.get("text", "")
                        item_str = f"{k}: {v}"
                        item_clean = _sanitize_text(item_str, agency_name)
                        if item_clean:
                            items.append(item_clean)
                            features_list.append(item_clean)
                            
                            k_low = k.lower()
                            if 'superficie cubierta' in k_low:
                                try: prop.area_covered = float(v.replace('m²', '').replace('m2', '').replace('.', '').strip())
                                except ValueError: pass
                            elif 'superficie total' in k_low:
                                try: prop.area_total = float(v.replace('m²', '').replace('m2', '').replace('.', '').strip())
                                except ValueError: pass
                            elif 'dormitorios' in k_low:
                                try: prop.bedrooms = int(v)
                                except ValueError: pass
                            elif 'baños' in k_low:
                                try: prop.bathrooms = int(v)
                                except ValueError: pass
                            elif 'ambientes' in k_low:
                                try: prop.rooms = int(v)
                                except ValueError: pass
                            elif 'expensas' in k_low:
                                m = re.search(r'([\d\.]+)', v)
                                if m:
                                    try: prop.expenses = float(m.group(1).replace('.', ''))
                                    except ValueError: pass
                            elif 'tipo de departamento' in k_low or 'tipo de casa' in k_low:
                                prop.type = v

                    if items:
                        categories.append(FeatureCategory(title=cat_title, items=items))
            prop.feature_categories = categories
            prop.features = list(dict.fromkeys(features_list))

            # G. Extraer Fotos Reales en Alta Resolución
            galleries = _find_components_by_type(components_dict, "gallery_mosaic")
            images = []
            if galleries:
                gal = galleries[0]
                primary = gal.get("primary", {}).get("src")
                if primary: images.append(primary)
                for sec in gal.get("secondary", []):
                    src = sec.get("src")
                    if src: images.append(src)
            prop.images = list(dict.fromkeys(images))

        # --- 2. FALLBACK HTML (Por si el aviso es muy antiguo) ---
        if not prop.title:
            title_node = soup.find('h1', class_='ui-pdp-title')
            if title_node: prop.title = title_node.get_text(strip=True)
            
        if not prop.description:
            desc_node = soup.find('p', class_='ui-pdp-description__content')
            if desc_node: prop.description = _sanitize_text(desc_node.get_text(separator="\n"), agency_name)
            
        if not prop.images:
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
