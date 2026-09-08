from app.branding import render_ficha
from app.config import DEFAULT_AGENT
from app.models import Property, SourceInfo


def test_render_ficha_includes_century21_and_price():
    prop = Property(
        source=SourceInfo(url="https://x.com/a", portal="x"),
        title="Depto en Belgrano",
        price=150000,
        currency="USD",
    )
    html = render_ficha(prop, DEFAULT_AGENT)
    assert "CENTURY 21" in html
    assert "Depto en Belgrano" in html
    assert "150,000" in html
    assert DEFAULT_AGENT.name in html


def test_render_ficha_omits_price_block_when_no_price():
    prop = Property(
        source=SourceInfo(url="https://x.com/a", portal="x"),
        title="Depto sin precio publicado",
    )
    html = render_ficha(prop, DEFAULT_AGENT)
    assert 'class="price"' not in html
