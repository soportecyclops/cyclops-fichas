"""Convierte un Property + AgentProfile en HTML de ficha con marca C21."""
from __future__ import annotations

import logging

from jinja2 import Environment, FileSystemLoader, TemplateError, select_autoescape

from app.config import TEMPLATES_DIR
from app.exceptions import BrandingError
from app.models import AgentProfile, Property

logger = logging.getLogger(__name__)

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_ficha(prop: Property, agent: AgentProfile) -> str:
    try:
        template = _env.get_template("ficha_century21.html")
        return template.render(p=prop, agent=agent)
    except TemplateError as e:
        logger.exception("Error renderizando ficha")
        raise BrandingError(f"No se pudo renderizar la ficha: {e}") from e
