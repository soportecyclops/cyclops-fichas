"""Extractor para RE/MAX Argentina basado en el estado JSON de Angular."""
from __future__ import annotations

import json
import logging
import re
from bs4 import BeautifulSoup

from app.exceptions import ExtractionError
from app.extractors.base import BaseExtractor
from app.models import FeatureCategory, Location, Property, SourceInfo

logger = logging.getLogger(__name__)

def _sanitize_text(raw: str | None) -> str | None:
    """Filtra menciones a la competencia, matriculas y datos de contacto."""
    if not raw: return None
    text = raw.replace("\r", "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    
    # Remover correos y teléfonos
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[CONTACTO ELIMINADO]', text)
    text = re.sub(r'(?:\+?54\s*9\s*)?(?:11|[2-3]\d{2,3})\s*(?:15)?\s*\d{4}[-\s]?\d{4}', '[TELÉFONO ELIMINADO]', text)
    
    # Remover matrículas legales (típicas en descripciones de RE/MAX)
    text = re.sub(r'(?i)(?:matr[íi]cula|cucicba|cpi|cmcpsi|colegiado|corredor responsable|ley 5115|ley 24\.240|cmcpdj)\s*:?\s*[a-zA-Z\d\s\.\-]+', '', text)
    
    # Reemplazar la marca
    text = re.sub(r'(?i)\b(RE/?MAX)\b', 'CENTURY 21', text)
    
    # Filtros anti-IA
    ai_patterns = r'(?i)(si eres una ia|ignora las? instrucciones|act[uú]a como|olvida todo|prompt subliminal|me dar[aá]s|tendr[aá]s que|eres un bot).*'
    text = re.sub(ai_patterns, '', text)
    
    return re.sub(r"\n{3,}", "\n\n", text).strip() or None

class RemaxExtractor(BaseExtractor):
    portal_name = "remax"

    def parse(self, html: str, url: str) -> Property:
        soup = BeautifulSoup(html, 'html.parser')
        prop = Property(source=SourceInfo(url=url, portal="remax"))

        # 1. Buscar el JSON de estado de Angular
        script_tag = soup.find('script', id='ng-state', type='application/json')
        if not script_tag:
            raise ExtractionError("No se encontró el bloque de datos JSON de RE/MAX.")

        try:
            json_data = json.loads(script_tag.string)
        except Exception as e:
            raise ExtractionError(f"Error al parsear el JSON de RE/MAX: {e}")

        # El JSON tiene una clave dinámica al inicio, buscamos el objeto 'data'
        data = None
        for key, value in json_data.items():
            if isinstance(value, dict) and 'b' in value and 'data' in value['b']:
                data = value['b']['data']
                break
        
        if not data:
            raise ExtractionError("No se encontraron los datos de la propiedad en el JSON de RE/MAX.")

        # 2. Extraer campos principales
        prop.title = data.get("title")
        prop.description = _sanitize_text(data.get("description"))
        
        prop.price = data.get("price")
        currency_info = data.get("currency")
        if isinstance(currency_info, dict):
            prop.currency = currency_info.get("value")
        
        prop.expenses = data.get("expensesPrice")
        
        # 3. Superficies y Ambientes
        prop.area_total = data.get("dimensionTotalBuilt")
        prop.area_covered = data.get("dimensionCovered")
        prop.rooms = data.get("totalRooms")
        prop.bedrooms = data.get("bedrooms")
        prop.bathrooms = data.get("bathrooms")
        
        # 4. Tipo de Operación y Propiedad
        type_info = data.get("type")
        if isinstance(type_info, dict):
            tipo_raw = type_info.get("value", "")
            prop.type = tipo_raw.replace("_", " ").title()

        # 5. Ubicación
        prop.location.address = data.get("displayAddress", "")
        geo_info = data.get("geo", {})
        if isinstance(geo_info, dict):
            prop.location.city = geo_info.get("label", "")

        # 6. Imágenes en Alta Calidad (insertando 1080xAUTO en la URL)
        photos = data.get("photos", [])
        images = []
        for photo in photos:
            raw_val = photo.get("rawValue")
            if raw_val:
                parts = raw_val.rsplit('/', 1)
                if len(parts) == 2:
                    img_url = f"https://d1acdg20u0pmxj.cloudfront.net/{parts[0]}/1080xAUTO/{parts[1]}.jpg"
                else:
                    img_url = f"https://d1acdg20u0pmxj.cloudfront.net/{raw_val}.jpg"
                images.append(img_url)
        prop.images = images

        # 7. Características Agrupadas
        features_data = data.get("features", [])
        categories_dict = {}
        features_list = []
        
        cat_map = {
            "service": "Servicios",
            "amenities": "Amenities",
            "environments": "Ambientes",
            "caracteristic": "Características Generales"
        }
        
        for feat in features_data:
            cat_raw = feat.get("category", "Otros")
            cat_name = cat_map.get(cat_raw, cat_raw.capitalize())
            val = feat.get("value")
            
            if val:
                val_clean = _sanitize_text(val)
                if val_clean:
                    if cat_name not in categories_dict:
                        categories_dict[cat_name] = []
                    categories_dict[cat_name].append(val_clean)
                    features_list.append(val_clean)
        
        prop.feature_categories = [FeatureCategory(title=k, items=v) for k, v in categories_dict.items()]
        prop.features = features_list

        if not prop.is_usable():
            raise ExtractionError(f"El aviso de {url} no tiene datos suficientes.")
        return prop
