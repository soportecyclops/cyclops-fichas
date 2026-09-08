import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.exceptions import ExtractionError, FetchError
from app.models import Property, SourceInfo

client = TestClient(main_module.app)


class _FakeExtractor:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def run(self, url: str) -> Property:
        if self._error:
            raise self._error
        return self._result


def _sample_property(url: str) -> Property:
    return Property(
        source=SourceInfo(url=url, portal="fake"),
        title="Depto de prueba",
        price=100000,
        currency="USD",
    )


def test_index_serves_html():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_crear_ficha_success(monkeypatch):
    url = "https://portal-falso.com/aviso-1"
    fake = _FakeExtractor(result=_sample_property(url))
    monkeypatch.setattr(main_module, "get_extractor", lambda u: fake)

    resp = client.post("/api/fichas", json={"url": url})
    assert resp.status_code == 200
    data = resp.json()
    assert "CENTURY 21" in data["html"]
    assert data["property"]["price"] == 100000


def test_crear_ficha_rechaza_url_vacia():
    resp = client.post("/api/fichas", json={"url": "   "})
    assert resp.status_code == 422  # validación de pydantic


def test_crear_ficha_maneja_fetch_error(monkeypatch):
    fake = _FakeExtractor(error=FetchError("portal caído"))
    monkeypatch.setattr(main_module, "get_extractor", lambda u: fake)

    resp = client.post("/api/fichas", json={"url": "https://caido.com/x"})
    assert resp.status_code == 502
    assert resp.json()["error"] == "fetch_error"


def test_crear_ficha_maneja_extraction_error(monkeypatch):
    fake = _FakeExtractor(error=ExtractionError("sin datos suficientes"))
    monkeypatch.setattr(main_module, "get_extractor", lambda u: fake)

    resp = client.post("/api/fichas", json={"url": "https://vacio.com/x"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "extraction_error"
