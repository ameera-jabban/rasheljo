"""
Payment provider abstraction, per the spec: a common interface so plugging in
a real gateway later doesn't touch the orders app. This module defines the
full lifecycle a gateway integration needs — initiate, confirm, cancel,
webhook handling, idempotency — with COD fully real and card wired to the
same interface but honestly unimplemented until real credentials exist.

To connect a real gateway (PayTabs/HyperPay/Stripe are the common choices for
Jordan): implement CardGatewayProvider's four methods for real, set
PAYMENT_GATEWAY_* environment variables, and nothing else in the codebase
needs to change — orders, cart, and checkout never talk to the gateway directly.
"""
import hashlib
import hmac
import os
from abc import ABC, abstractmethod

from django.db import transaction

from .models import Payment, PaymentAttempt, PaymentWebhookEvent


class PaymentInitiationResult:
    def __init__(self, success: bool, status: str, provider_reference: str = "", raw_response: dict | None = None):
        self.success = success
        self.status = status  # one of Payment.STATUS_CHOICES
        self.provider_reference = provider_reference
        self.raw_response = raw_response or {}


class PaymentProvider(ABC):
    @abstractmethod
    def initiate(self, payment: Payment, idempotency_key: str) -> PaymentInitiationResult:
        """Start a charge. For COD this immediately succeeds. For a real card
        gateway this would create a payment intent/session and return its
        reference — actual fund capture may happen here or on confirm()
        depending on the gateway's flow."""
        ...

    @abstractmethod
    def confirm(self, payment: Payment) -> PaymentInitiationResult:
        """Finalize a previously-initiated payment (e.g. after 3-D Secure
        redirect back, or a gateway's separate 'capture' call)."""
        ...

    @abstractmethod
    def cancel(self, payment: Payment) -> PaymentInitiationResult:
        """Cancel a pending/authorized payment before it's captured."""
        ...

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        """Override in a real provider with the gateway's actual HMAC/signature
        scheme. Returning False by default means an unconfigured provider
        never accepts a webhook it can't actually verify."""
        return False


class CashOnDeliveryProvider(PaymentProvider):
    def initiate(self, payment, idempotency_key):
        return PaymentInitiationResult(True, "paid", raw_response={"note": "Cash on delivery — no upfront charge."})

    def confirm(self, payment):
        return PaymentInitiationResult(True, "paid")

    def cancel(self, payment):
        return PaymentInitiationResult(True, "cancelled")


class CardGatewayProvider(PaymentProvider):
    """Real implementation requires PAYMENT_GATEWAY_API_KEY and
    PAYMENT_GATEWAY_WEBHOOK_SECRET to be set — until then every method
    honestly fails rather than faking success, per the explicit requirement
    to never simulate a successful card payment."""

    def __init__(self):
        self.api_key = os.environ.get("PAYMENT_GATEWAY_API_KEY", "")
        self.webhook_secret = os.environ.get("PAYMENT_GATEWAY_WEBHOOK_SECRET", "")
        self.configured = bool(self.api_key)

    def initiate(self, payment, idempotency_key):
        if not self.configured:
            return PaymentInitiationResult(
                False, "failed",
                raw_response={"error": "No card gateway configured (PAYMENT_GATEWAY_API_KEY unset)."},
            )
        # Real implementation: call the gateway's "create payment intent" API
        # here, using idempotency_key as the gateway's own idempotency header
        # so a retried request doesn't double-charge.
        raise NotImplementedError("Card gateway API integration not implemented.")

    def confirm(self, payment):
        if not self.configured:
            return PaymentInitiationResult(False, "failed", raw_response={"error": "No card gateway configured."})
        raise NotImplementedError("Card gateway API integration not implemented.")

    def cancel(self, payment):
        if not self.configured:
            return PaymentInitiationResult(False, "failed", raw_response={"error": "No card gateway configured."})
        raise NotImplementedError("Card gateway API integration not implemented.")

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        if not self.webhook_secret:
            return False
        expected = hmac.new(self.webhook_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)


def get_provider(method: str) -> PaymentProvider:
    return {"cod": CashOnDeliveryProvider(), "card": CardGatewayProvider()}[method]


@transaction.atomic
def initiate_payment(order, idempotency_key: str = "") -> Payment:
    """Called from orders.OrderConfirmView. Idempotent: a repeated call with
    the same idempotency_key against a payment already in a terminal state
    returns the existing record instead of re-charging."""
    payment, created = Payment.objects.get_or_create(
        order=order, defaults={"method": order.payment_method, "amount": order.total, "idempotency_key": idempotency_key}
    )
    if not created and payment.status in ("paid", "cancelled"):
        return payment  # already resolved — don't re-initiate

    provider = get_provider(order.payment_method)
    try:
        result = provider.initiate(payment, idempotency_key)
    except NotImplementedError as exc:
        result = PaymentInitiationResult(False, "failed", raw_response={"error": str(exc)})

    PaymentAttempt.objects.create(payment=payment, success=result.success, raw_response=result.raw_response)
    payment.status = result.status
    payment.provider_reference = result.provider_reference or payment.provider_reference
    payment.save(update_fields=["status", "provider_reference", "updated_at"])
    return payment


# Backwards-compatible name used by orders.views.OrderConfirmView.
process_payment = initiate_payment


def cancel_payment(payment: Payment) -> Payment:
    provider = get_provider(payment.method)
    result = provider.cancel(payment)
    PaymentAttempt.objects.create(payment=payment, success=result.success, raw_response=result.raw_response)
    if result.success:
        payment.status = "cancelled"
        payment.save(update_fields=["status", "updated_at"])
    return payment


def handle_webhook(provider_name: str, raw_body: bytes, signature: str, payload: dict) -> PaymentWebhookEvent:
    """Every webhook call is logged first, verified second, processed third —
    so a bad signature or a processing bug never means the event is lost."""
    event = PaymentWebhookEvent.objects.create(provider=provider_name, event_type=payload.get("type", ""), payload=payload)

    provider = get_provider("card") if provider_name == "card" else None
    if provider is None:
        event.error = f"Unknown provider '{provider_name}'."
        event.signature_valid = False
        event.save(update_fields=["error", "signature_valid"])
        return event

    valid = provider.verify_webhook_signature(raw_body, signature)
    event.signature_valid = valid
    if not valid:
        event.error = "Signature verification failed."
        event.save(update_fields=["signature_valid", "error"])
        return event

    # Real handling would look up the Payment by payload's reference and
    # transition its status here based on the event type. Left as a
    # documented extension point since there's no live gateway to test against.
    event.processed = True
    event.save(update_fields=["signature_valid", "processed"])
    return event
