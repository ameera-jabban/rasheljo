"""Best-effort task enqueueing for code that runs inside a web request.

Handing a job to Celery is a *side effect* of a customer action, never the
point of it. Placing an order, changing its status, etc. must still succeed
when the broker is unreachable — the notification email is allowed to be
lost, the order is not.

`task.delay(...)` opens a broker connection and raises
`kombu.exceptions.OperationalError` (and friends) when that fails. Call sites
in request paths should go through `enqueue()` so that failure is logged and
swallowed instead of turning into a 500. Background workers and management
commands should keep calling `.delay()` / `.apply_async()` directly — there a
broker failure *should* surface.
"""
import logging

from kombu.exceptions import OperationalError as BrokerOperationalError

try:  # redis is the configured broker; its errors can surface through kombu
    from redis.exceptions import RedisError
except ImportError:  # pragma: no cover - redis is always installed here
    RedisError = ()

logger = logging.getLogger(__name__)

# Broker is down / unreachable / speaking an incompatible protocol.
# (OSError covers the builtin ConnectionError / ConnectionRefusedError.)
BROKER_ERRORS = (BrokerOperationalError, RedisError, OSError)


def enqueue(task, *args, **kwargs):
    """Fire-and-forget `task.delay(*args, **kwargs)`; return the AsyncResult,
    or None if the broker could not be reached."""
    try:
        return task.delay(*args, **kwargs)
    except BROKER_ERRORS as exc:
        logger.warning(
            "Could not enqueue task %s - broker unavailable (%s: %s). "
            "The job was dropped.",
            getattr(task, "name", task),
            type(exc).__name__,
            exc,
        )
        return None
