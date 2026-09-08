"""Excepciones propias. Nunca dejar que un error crudo (httpx, bs4, etc.)
llegue sin traducir a la capa API."""


class FichaError(Exception):
    """Base de todas las excepciones del dominio."""


class InvalidURLError(FichaError):
    """La URL no tiene formato válido o esquema no soportado."""


class FetchError(FichaError):
    """No se pudo descargar la página (timeout, DNS, status >= 400, etc.)."""


class ExtractionError(FichaError):
    """Se descargó la página pero no se pudo extraer info suficiente."""


class BrandingError(FichaError):
    """Falló el renderizado de la ficha (template, datos faltantes)."""
