import pytest
from django.utils import translation

from storefront import services


@pytest.fixture(autouse=True)
def _isolate_storefront_process_state():
    """Two bits of process-global state leak across storefront tests otherwise:

    * ``services._cached`` keeps a 60s in-process TTL cache of reference data
      (brands, categories, skin types, site settings…) that outlives the
      per-test DB rollback.
    * ``django.utils.translation`` stays on whatever language the last request
      activated, so a later ``reverse()`` can pick the wrong ``/ar/`` vs ``/en/``
      URL prefix.

    Reset both around every test for determinism.
    """
    services._cache.clear()
    translation.activate("en")
    yield
    services._cache.clear()
    translation.deactivate_all()
