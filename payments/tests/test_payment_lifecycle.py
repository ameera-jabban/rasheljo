import hashlib
import hmac
import json
import os

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from orders.models import Order
from payments.models import Payment, PaymentWebhookEvent
from payments.services import cancel_payment, get_provider, initiate_payment

pytestmark = pytest.mark.django_db
User = get_user_model()


class TestIdempotency:
    def test_repeated_initiate_on_paid_cod_does_not_double_charge(self):
        user = User.objects.create_user(username="idem@x.com", email="idem@x.com", password="pw12345678!")
        order = Order.objects.create(user=user, payment_method="cod", total="20.00")

        first = initiate_payment(order, idempotency_key="key-1")
        assert first.status == "paid"
        attempt_count_after_first = first.attempts.count()

        second = initiate_payment(order, idempotency_key="key-1")
        assert second.id == first.id
        assert second.attempts.count() == attempt_count_after_first  # no new attempt logged

    def test_idempotency_key_is_stored(self):
        user = User.objects.create_user(username="idem2@x.com", email="idem2@x.com", password="pw12345678!")
        order = Order.objects.create(user=user, payment_method="cod", total="10.00")
        payment = initiate_payment(order, idempotency_key="unique-key-abc")
        assert payment.idempotency_key == "unique-key-abc"


class TestCardGatewayHonesty:
    def test_card_initiate_fails_without_credentials(self):
        user = User.objects.create_user(username="card1@x.com", email="card1@x.com", password="pw12345678!")
        order = Order.objects.create(user=user, payment_method="card", total="10.00")
        payment = initiate_payment(order)
        assert payment.status == "failed"
        assert not payment.attempts.filter(success=True).exists()

    def test_card_provider_reports_unconfigured(self):
        provider = get_provider("card")
        assert provider.configured is False


class TestCancelPayment:
    def test_cancel_cod_payment(self):
        user = User.objects.create_user(username="cancel@x.com", email="cancel@x.com", password="pw12345678!")
        order = Order.objects.create(user=user, payment_method="cod", total="15.00")
        payment = initiate_payment(order)
        assert payment.status == "paid"

        cancelled = cancel_payment(payment)
        assert cancelled.status == "cancelled"
        assert cancelled.attempts.count() == 2  # initiate + cancel both logged


class TestWebhookEndpoint:
    def test_webhook_without_valid_signature_rejected(self):
        client = APIClient()
        resp = client.post(
            reverse("payment-webhook", kwargs={"provider": "card"}),
            data=json.dumps({"type": "payment.succeeded"}),
            content_type="application/json",
            HTTP_X_SIGNATURE="bogus",
        )
        assert resp.status_code == 400
        assert PaymentWebhookEvent.objects.filter(signature_valid=False).exists()

    def test_webhook_unknown_provider_rejected(self):
        client = APIClient()
        resp = client.post(
            reverse("payment-webhook", kwargs={"provider": "unknown_gateway"}),
            data=json.dumps({"type": "x"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        event = PaymentWebhookEvent.objects.filter(provider="unknown_gateway").first()
        assert event is not None
        assert event.signature_valid is False

    def test_webhook_event_always_logged_even_on_bad_signature(self):
        client = APIClient()
        before = PaymentWebhookEvent.objects.count()
        client.post(
            reverse("payment-webhook", kwargs={"provider": "card"}),
            data=json.dumps({"type": "payment.failed", "ref": "xyz"}),
            content_type="application/json",
            HTTP_X_SIGNATURE="invalid",
        )
        assert PaymentWebhookEvent.objects.count() == before + 1

    def test_webhook_with_valid_signature_when_configured(self, monkeypatch):
        secret = "test-webhook-secret"
        monkeypatch.setenv("PAYMENT_GATEWAY_WEBHOOK_SECRET", secret)

        body = json.dumps({"type": "payment.succeeded"}).encode()
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        client = APIClient()
        resp = client.post(
            reverse("payment-webhook", kwargs={"provider": "card"}),
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )
        assert resp.status_code == 200
        assert resp.data["processed"] is True
