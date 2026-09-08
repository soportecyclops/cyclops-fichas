from app.models import Property, SourceInfo


def _base_source():
    return SourceInfo(url="https://example.com/aviso/1", portal="example")


def test_property_defaults_are_none_or_empty():
    p = Property(source=_base_source())
    assert p.price is None
    assert p.images == []
    assert p.features == []


def test_currency_normalizes_to_uppercase():
    p = Property(source=_base_source(), currency="usd")
    assert p.currency == "USD"


def test_is_usable_false_without_data():
    p = Property(source=_base_source())
    assert p.is_usable() is False


def test_is_usable_true_with_title_and_price():
    p = Property(source=_base_source(), title="Depto 2 amb", price=100000)
    assert p.is_usable() is True


def test_is_usable_true_with_description_and_image():
    p = Property(
        source=_base_source(),
        description="Lindo depto",
        images=["https://x.com/foto.jpg"],
    )
    assert p.is_usable() is True


def test_is_usable_false_with_only_price_no_title_or_desc():
    p = Property(source=_base_source(), price=100000)
    assert p.is_usable() is False
