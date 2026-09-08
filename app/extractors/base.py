"""Contrato común para todos los extractores de portal."""
from __future__ import annotations

import logging
import traceback
from abc import ABC, abstractmethod
from urllib.parse import urlparse

# Usamos curl_cffi para suplantar la huella TLS de un navegador real
from curl_cffi import requests

from app.exceptions import FetchError, InvalidURLError
from app.models import Property

# Configuración de control y registro detallado de errores
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Crea un archivo errores.log en la raíz para auditoría
file_handler = logging.FileHandler("errores.log", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")
file_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)

MAX_RETRIES = 2

def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        logger.error(f"Validación fallida para URL: {url}")
        raise InvalidURLError(f"URL inválida: {url!r}")
    return url

def fetch_html(url: str) -> str:
    """Descarga HTML evadiendo WAF y registrando errores a nivel de red."""
    validate_url(url)
    last_exc: Exception | None = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Intentando descargar (Intento {attempt}/{MAX_RETRIES}): {url}")
            
            # impersonate="chrome110" simula criptográficamente a Google Chrome
            response = requests.get(
                url, 
                impersonate="chrome110",
                timeout=15.0
            )
            
            if response.status_code != 200:
                logger.warning(f"HTTP {response.status_code} recibido de {url}")
                raise FetchError(f"HTTP {response.status_code}")
                
            if not response.text or len(response.text) < 200:
                logger.warning(f"Respuesta anómala o vacía de {url}")
                raise FetchError(f"Respuesta demasiado corta de {url}")
                
            logger.info(f"Descarga exitosa de {url}")
            return response.text
            
        except Exception as e:
            last_exc = e
            # Registramos el error y el traceback completo en el archivo log
            logger.error(f"Fallo en intento {attempt} para {url}: {e}\n{traceback.format_exc()}")
            
    logger.critical(f"Fallo definitivo al descargar {url}. Último error: {last_exc}")
    raise FetchError(f"No se pudo descargar {url}: {last_exc}") from last_exc

class BaseExtractor(ABC):
    """Cada extractor de portal implementa parse(); fetch queda centralizado."""

    portal_name: str = "desconocido"

    def run(self, url: str) -> Property:
        html = fetch_html(url)
        return self.parse(html, url)

    @abstractmethod
    def parse(self, html: str, url: str) -> Property:
        ...
