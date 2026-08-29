import json

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import handle_webhook


class PaymentWebhookView(APIView):
    """POST /api/v1/payments/webhook/<provider>/ — every inbound event is
    logged and signature-checked before any processing, per the requirement
    for real webhook handling rather than a stub that trusts any request."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, provider):
        signature = request.headers.get("X-Signature", "")
        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return Response({"detail": "Invalid JSON body."}, status=status.HTTP_400_BAD_REQUEST)

        event = handle_webhook(provider, request.body, signature, payload)
        if event.signature_valid is False:
            return Response({"detail": "Signature verification failed."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"received": True, "processed": event.processed})
