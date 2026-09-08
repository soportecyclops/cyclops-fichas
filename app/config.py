"""Configuración y datos por defecto."""
from pathlib import Path
from app.models import AgentProfile

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

DEFAULT_AGENT = AgentProfile(
    name="Juan Pérez",
    phone="+54 9 11 0000-0000",
    whatsapp="5491100000000",
    email="agente@century21.com.ar",
    agency_name="CENTURY 21",
    address="Av. Siempre Viva 123",
    website="www.century21.com.ar",
    social_media="@century21arg",
    logo_url="/static/c21-logo.svg",
    photo_url="/static/agent-placeholder.svg",
)
