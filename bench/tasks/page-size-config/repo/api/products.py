from . import settings


def resolve_page_size(page_size=None):
    """Page size to use for a request."""
    if page_size is None:
        return settings.MAX_PAGE_SIZE
    return page_size


def list_products(all_products, page_size=None):
    return all_products[:resolve_page_size(page_size)]
