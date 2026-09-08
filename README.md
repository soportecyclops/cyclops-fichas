# Cyclops Fichas — Century 21 (Fase 1: esqueleto)

Convierte el link de un aviso de **cualquier** portal inmobiliario en una
ficha con membrete de Century 21.

## Instalación

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Correr

```bash
uvicorn app.main:app --reload
```

Abrir http://127.0.0.1:8000

## Tests

```bash
pytest
```

## Cómo funciona (fase 1)

1. Usuario pega un link en la web.
2. `GenericExtractor` intenta, en orden: JSON-LD → OpenGraph → heurística
   de texto (regex de precio/ambientes/m²).
3. El resultado se normaliza a `Property` (esquema fijo, agnóstico de portal).
4. `branding.py` renderiza `Property` + `AgentProfile` (hardcodeado en
   `config.py`) sobre la plantilla `ficha_century21.html`.
5. Se devuelve el HTML de la ficha.

## Qué falta (próximas fases)

- Fase 2: extractores dedicados por portal (ZonaProp, Argenprop,
  MercadoLibre) que reemplacen el fallback heurístico.
- Fase 3: registro de agentes reales (DB), logo/foto propios en vez de
  `DEFAULT_AGENT`.
- Fase 4: bot de WhatsApp como canal alternativo a la web.
- Fase 5: tracking + ficha de visita/feedback + dashboard.

## Estructura

```
app/
  models.py          Property, AgentProfile (esquema normalizado)
  exceptions.py       Excepciones propias (nunca error crudo hasta la API)
  extractors/
    base.py           fetch_html con timeout/retries + contrato BaseExtractor
    generic.py         JSON-LD / OpenGraph / heurística
    __init__.py         factory get_extractor(url) por dominio
  branding.py          Property + AgentProfile -> HTML
  templates/           plantilla Jinja2 de la ficha
  static/              CSS de marca C21
  main.py              FastAPI: POST /api/fichas, manejo de errores
frontend/index.html    formulario de subida de link
tests/                 pytest (modelos, extractor, branding, API)
```
