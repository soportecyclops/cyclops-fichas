from __future__ import annotations
import logging
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from typing import Optional

from app.branding import render_ficha
from app.config import DEFAULT_AGENT, STATIC_DIR
from app.exceptions import BrandingError, ExtractionError, FetchError, InvalidURLError
from app.extractors import get_extractor
from app.models import AgentProfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Cyclops Fichas", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class FichaRequest(BaseModel):
    url: str
    agent: Optional[dict] = None

    @field_validator("url")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url vacía")
        return v

class FichaResponse(BaseModel):
    html: str
    property: dict

@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse("frontend/index.html")

@app.post("/api/fichas", response_model=FichaResponse)
def crear_ficha(payload: FichaRequest) -> FichaResponse:
    extractor = get_extractor(payload.url)
    prop = extractor.run(payload.url)
    
    # Combinar agente por defecto con los datos ingresados en el formulario
    agent_data = DEFAULT_AGENT.model_dump()
    if payload.agent:
        for key, value in payload.agent.items():
            if value and str(value).strip():
                agent_data[key] = value
                
    current_agent = AgentProfile(**agent_data)
    html = render_ficha(prop, current_agent)
    return FichaResponse(html=html, property=prop.model_dump())

@app.exception_handler(InvalidURLError)
def handle_invalid_url(request: Request, exc: InvalidURLError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": "url_invalida", "detail": str(exc)})
@app.exception_handler(FetchError)
def handle_fetch_error(request: Request, exc: FetchError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "fetch_error", "detail": str(exc)})
@app.exception_handler(ExtractionError)
def handle_extraction_error(request: Request, exc: ExtractionError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "extraction_error", "detail": str(exc)})
@app.exception_handler(BrandingError)
def handle_branding_error(request: Request, exc: BrandingError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": "branding_error", "detail": str(exc)})
@app.exception_handler(Exception)
def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error no controlado")
    return JSONResponse(status_code=500, content={"error": "internal_error", "detail": "Error interno"})
