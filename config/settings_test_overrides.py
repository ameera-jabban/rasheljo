# Imported only by pytest.ini's DJANGO_SETTINGS_MODULE override below —
# keeps tests from pushing real messages onto the dev Redis broker.
import tempfile

from .settings import *  # noqa

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Keep test file uploads (HomepageVideo / ProductImage fixtures) out of the real
# ./media tree — otherwise every run litters it with hashed dupes.
MEDIA_ROOT = tempfile.mkdtemp(prefix="drj-test-media-")

# Tests must not depend on a running Redis. Local-memory cache gives the same
# API (incr/add/get/set) so the storefront cache + invalidation paths are still
# exercised end to end.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "drj-test",
    }
}
