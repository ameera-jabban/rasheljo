# Imported only by pytest.ini's DJANGO_SETTINGS_MODULE override below —
# keeps tests from pushing real messages onto the dev Redis broker.
from .settings import *  # noqa

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
