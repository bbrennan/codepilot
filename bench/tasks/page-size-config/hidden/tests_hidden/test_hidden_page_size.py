import pytest

from api import settings
from api.products import list_products, resolve_page_size


def test_default_from_settings():
    assert resolve_page_size() == settings.DEFAULT_PAGE_SIZE == 20
    assert len(list_products(list(range(500)))) == 20


def test_capped():
    assert resolve_page_size(500) == 100
    assert resolve_page_size(100) == 100


def test_rejects_small():
    for bad in (0, -1):
        with pytest.raises(ValueError):
            resolve_page_size(bad)
