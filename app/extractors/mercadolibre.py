"""Extractor avanzado MercadoLibre mediante NORDIC JSON, API externa y fallback HTML."""
from __future__ import annotations

import logging
import re
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.exceptions import ExtractionError
from app.extractors.base import BaseExtractor
from app.models import FeatureCategory, Location, Property, SourceInfo

logger = logging.getLogger(__name__)

def _sanitize_text(raw: str | None, publisher_name: str | None) -> str | None:
    if not raw: return None
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
    results = []
    if isinstance(node, dict):
        if node.get("type") == type_name: results.append(node)
        for v in node.values(): results.extend(_find_components_by_type(v, type_name))
    elif isinstance(node, list):
        for item in node: results.extend(_find_components_by_type(item, type_name))
    return results

class MercadoLibreExtractor(BaseExtractor):
    portal_name = "mercadolibre"

    def parse(self, html: str, url: str) -> Property:
        soup = BeautifulSoup(html, 'html.parser')
        prop = Property(source=SourceInfo(url=url, portal="mercadolibre"))
        agency_name = None
        json_data = {}
        
        # 1. PARSEO NORDIC JSON (Textos y Características)
        script_match = re.search(r'<script id="__NORDIC_RENDERING_CTX__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if script_match:
            js_code = script_match.group(1)
            obj_str = re.sub(r'^_n\.ctx\.r\s*=\s*', '', js_code.split(';_n.ctx.r')[0]).strip()
            if obj_str.endswith(';'): obj_str = obj_str[:-1]
            import chompjs
            try: json_data = chompjs.parse_js_object(obj_str)
            except Exception: pass

        if json_data:
            comps = json_data.get('appProps', {}).get('pageProps', {}).get('initialState', {}).get('components', {})
            
            sellers = _find_components_by_type(comps, "seller_profile")
            if sellers: agency_name = sellers[0].get("seller_name", {}).get("title", {}).get("text")
                
            descs = _find_components_by_type(comps, "description")
            if descs: prop.description = _sanitize_text(descs[0].get("content"), agency_name)
                
            headers = _find_components_by_type(comps, "header")
            if headers: prop.title = headers[0].get("title")
                
            prices = _find_components_by_type(comps, "price")
            if prices:
                prop.price = prices[0].get("price", {}).get("value")
                prop.currency = prices[0].get("price", {}).get("currency_id")
                
            locs = _find_components_by_type(comps, "location_and_points")
            if locs:
                prop.location.address = locs[0].get("item_address")
                prop.location.city = locs[0].get("item_location")

            tech_specs = _find_components_by_type(comps, "technical_specifications")
            cats, feat_list = [], []
            if tech_specs:
                for spec in tech_specs[0].get("specs", []):
                    items = []
                    for attr in spec.get("attributes", []):
                        item_clean = _sanitize_text(f"{attr.get('id', '')}: {attr.get('text', '')}", agency_name)
                        if item_clean:
                            items.append(item_clean)
                            feat_list.append(item_clean)
                            k_low, v = attr.get('id', '').lower(), attr.get('text', '')
                            if 'cubierta' in k_low:
                                try: prop.area_covered = float(v.replace('m²','').replace('.','').strip())
                                except ValueError: pass
                            elif 'total' in k_low:
                                try: prop.area_total = float(v.replace('m²','').replace('.','').strip())
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
                    if items: cats.append(FeatureCategory(title=spec.get("title", "Info"), items=items))
            prop.feature_categories = cats
            prop.features = list(dict.fromkeys(feat_list))

        # 2. FALLBACK HTML BÁSICO
        if not prop.title:
            t_node = soup.find('h1', class_='ui-pdp-title')
            if t_node: prop.title = t_node.get_text(strip=True)
        if not prop.description:
            d_node = soup.find('p', class_='ui-pdp-description__content')
            if d_node: prop.description = _sanitize_text(d_node.get_text(separator="\n"), agency_name)

        # 3. EXTRACCIÓN MASIVA DE IMÁGENES VÍA API PÚBLICA
        item_id_match = re.search(r'MLA-?(\d+)', url, re.IGNORECASE)
        if item_id_match:
            item_id = f"MLA{item_id_match.group(1)}"
            try:
                response = cffi_requests.get(f"https://api.mercadolibre.com/items/{item_id}", impersonate="chrome110", timeout=10)
                if response.status_code == 200:
                    api_pics = response.json().get("pictures", [])
                    images = []
                    for pic in api_pics:
                        img_url = pic.get("secure_url") or pic.get("url")
                        if img_url:
                            images.append(img_url.replace("-O.jpg", "-F.jpg").replace("-O.webp", "-F.webp"))
                    if images: prop.images = list(dict.fromkeys(images))
            except Exception as e:
                logger.warning(f"Error API ML {item_id}: {e}")

        # Fallback de imágenes
        if not prop.images:
            images = []
            for fig in soup.find_all('figure', class_='gallery-image'):
                img = fig.find('img')
                if img and (img.get('src') or img.get('data-src')):
                    images.append(img.get('src') or img.get('data-src'))
            prop.images = list(dict.fromkeys(images))

        if not prop.is_usable(): raise ExtractionError(f"Datos insuficientes en {url}")
        return prop
