from django.db import transaction
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Address
from cart.views import get_or_create_cart
from shipping.models import ShippingMethod

from .models import Order, OrderItem
from .serializers import OrderSerializer


class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).exclude(status="draft").prefetch_related("items")


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)


class OrderCreateFromCartView(APIView):
    """POST /api/v1/orders/create/ — snapshots the current cart (including any
    applied coupon) into a draft order. Address/shipping-method can be attached
    here or patched in later steps, matching the checkout wizard's per-step PATCH."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        from promotions.models import Coupon

        cart = get_or_create_cart(request)
        if not cart.items.exists():
            return Response({"detail": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        address = None
        address_id = request.data.get("address_id")
        if address_id:
            address = Address.objects.filter(id=address_id, user=request.user).first()
            if not address:
                return Response({"detail": "Address not found."}, status=status.HTTP_400_BAD_REQUEST)

        shipping_method = None
        shipping_method_id = request.data.get("shipping_method_id")
        if shipping_method_id:
            shipping_method = ShippingMethod.objects.filter(id=shipping_method_id, is_active=True).first()
            if not shipping_method:
                return Response({"detail": "Shipping method not found."}, status=status.HTTP_400_BAD_REQUEST)

        for item in cart.items.all():
            if item.product.stock < item.quantity:
                return Response(
                    {"detail": f"'{item.product.name_en}' no longer has enough stock."},
                    status=status.HTTP_409_CONFLICT,
                )

        discount_amount = 0
        coupon_code = ""
        if cart.coupon_code:
            coupon = Coupon.objects.filter(code__iexact=cart.coupon_code).first()
            if coupon and coupon.is_valid_now()[0]:
                discount_amount = coupon.calculate_discount(cart.subtotal)
                coupon_code = coupon.code

        order = Order.objects.create(
            user=request.user,
            shipping_address=address,
            shipping_method=shipping_method,
            payment_method=request.data.get("payment_method", "cod"),
            coupon_code=coupon_code,
            discount_amount=discount_amount,
        )
        for item in cart.items.all():
            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name_en,
                unit_price=item.unit_price,
                quantity=item.quantity,
            )
        order.recalculate_totals()
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderUpdateDraftView(APIView):
    """PATCH /api/v1/orders/{id}/ — per-step checkout updates (address, shipping
    method, payment method) on a still-draft order, each independently validated."""

    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        order = Order.objects.filter(id=pk, user=request.user, status="draft").first()
        if not order:
            return Response({"detail": "Draft order not found."}, status=status.HTTP_404_NOT_FOUND)

        if "address_id" in request.data:
            address = Address.objects.filter(id=request.data["address_id"], user=request.user).first()
            if not address:
                return Response({"detail": "Address not found."}, status=status.HTTP_400_BAD_REQUEST)
            order.shipping_address = address

        if "shipping_method_id" in request.data:
            method = ShippingMethod.objects.filter(id=request.data["shipping_method_id"], is_active=True).first()
            if not method:
                return Response({"detail": "Shipping method not found."}, status=status.HTTP_400_BAD_REQUEST)
            order.shipping_method = method

        if "payment_method" in request.data:
            if request.data["payment_method"] not in dict(Order.PAYMENT_METHODS):
                return Response({"detail": "Invalid payment method."}, status=status.HTTP_400_BAD_REQUEST)
            order.payment_method = request.data["payment_method"]

        order.save()
        order.recalculate_totals()
        return Response(OrderSerializer(order).data)


class OrderConfirmView(APIView):
    """POST /api/v1/orders/{id}/confirm/ — draft -> pending, decrements stock,
    processes payment (COD confirms instantly; card path is honest about not
    being wired to a real gateway yet), clears cart, increments coupon usage."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        from promotions.models import Coupon
        from payments.services import process_payment

        order = Order.objects.filter(id=pk, user=request.user, status="draft").first()
        if not order:
            return Response({"detail": "Draft order not found."}, status=status.HTTP_404_NOT_FOUND)

        if not order.shipping_address_id:
            return Response({"detail": "Shipping address is required."}, status=status.HTTP_400_BAD_REQUEST)

        for item in order.items.select_related("product"):
            product = item.product
            if product.stock < item.quantity:
                return Response(
                    {"detail": f"'{product.name_en}' sold out before order was confirmed."},
                    status=status.HTTP_409_CONFLICT,
                )
            product.stock -= item.quantity
            product.save(update_fields=["stock"])

        order.transition_to("pending")

        payment = process_payment(order)
        if order.payment_method == "card" and payment.status == "failed":
            # Roll back the whole confirm — stock, status, everything — since
            # a failed card charge means this order never actually happened.
            transaction.set_rollback(True)
            return Response(
                {"detail": "Payment failed. Card payments are not yet connected to a live gateway."},
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        if order.coupon_code:
            from django.db.models import F
            Coupon.objects.filter(code__iexact=order.coupon_code).update(times_used=F("times_used") + 1)

        cart = get_or_create_cart(request)
        cart.items.all().delete()
        cart.coupon_code = ""
        cart.save(update_fields=["coupon_code"])

        from notify.dispatch import enqueue
        from notify.tasks import send_order_confirmation_email
        enqueue(send_order_confirmation_email, order.id)

        return Response(OrderSerializer(order).data)
