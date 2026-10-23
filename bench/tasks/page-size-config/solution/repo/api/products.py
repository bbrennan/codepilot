from . import settings


def resolve_page_size(page_size=None):
    """Page size to use for a request."""
    if page_size is None:
        return settings.DEFAULT_PAGE_SIZE
    if page_size < 1:
        raise ValueError("page_size must be >= 1")
    return min(page_size, settings.MAX_PAGE_SIZE)


def list_products(all_products, page_size=None):
    return all_products[:resolve_page_size(page_size)]
