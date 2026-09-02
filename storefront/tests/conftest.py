import pytest
from django.core.cache import cache
from django.utils import translation


@pytest.fixture(autouse=True)
def _isolate_storefront_process_state():
    """Two bits of process-global state leak across storefront tests otherwise:

    * ``django.core.cache`` (locmem in tests) holds both the reference-data
      cache (``sf:ref:*`` — brands, categories, site settings, homepage
      videos…) and the catalog read cache (``sf:cat:*`` — rails, product
      detail, shop landings). Both outlive the per-test DB rollback.
    * ``django.utils.translation`` stays on whatever language the last request
      activated, so a later ``reverse()`` can pick the wrong ``/ar/`` vs ``/en/``
      URL prefix.

    Reset both around every test for determinism.
    """
    cache.clear()
    translation.activate("en")
    yield
    cache.clear()
    translation.deactivate_all()
