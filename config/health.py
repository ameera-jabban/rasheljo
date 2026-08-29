"""Health check — actually probes the database and cache/broker, not just a
static 200. A load balancer / orchestrator should treat a non-200 here as
'take this instance out of rotation', so it needs to be a real check."""
import redis as redis_lib
from django.conf import settings
from django.db import connections
from django.http import JsonResponse


def health_check(request):
    checks = {}
    overall_ok = True

    try:
        connections["default"].cursor().execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        overall_ok = False

    try:
        client = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"
        overall_ok = False

    return JsonResponse({"status": "ok" if overall_ok else "unhealthy", "checks": checks}, status=200 if overall_ok else 503)
