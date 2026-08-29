from rest_framework import permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cart, CartItem
from .serializers import CartSerializer


def get_or_create_cart(request):
    """Logged-in users get a persistent cart; guests get one keyed by session.
    This is the merge point described in Part 2's cart app note."""
    if request.user and request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    cart, _ = Cart.objects.get_or_create(session_key=session_key, user=None)
    return cart


class CartDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        cart = get_or_create_cart(request)
        return Response(CartSerializer(cart, context={"request": request}).data)


class CartItemListCreateView(GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from catalog.models import Product

        cart = get_or_create_cart(request)
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        if quantity < 1:
            return Response({"detail": "Quantity must be at least 1."}, status=status.HTTP_400_BAD_REQUEST)
        if product.stock < quantity:
            return Response({"detail": "Not enough stock available."}, status=status.HTTP_400_BAD_REQUEST)

        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, variant=None, defaults={"quantity": quantity}
        )
        if not created:
            item.quantity += quantity
            item.save()

        return Response(CartSerializer(cart, context={"request": request}).data, status=status.HTTP_201_CREATED)


class CartItemDetailView(GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def get_item(self, request, pk):
        cart = get_or_create_cart(request)
        return cart, CartItem.objects.filter(cart=cart, pk=pk).first()

    def patch(self, request, pk):
        cart, item = self.get_item(request, pk)
        if not item:
            return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)
        quantity = int(request.data.get("quantity", item.quantity))
        if quantity < 1:
            return Response({"detail": "Quantity must be at least 1."}, status=status.HTTP_400_BAD_REQUEST)
        if item.product.stock < quantity:
            return Response({"detail": "Not enough stock available."}, status=status.HTTP_400_BAD_REQUEST)
        item.quantity = quantity
        item.save()
        return Response(CartSerializer(cart, context={"request": request}).data)

    def delete(self, request, pk):
        cart, item = self.get_item(request, pk)
        if not item:
            return Response({"detail": "Item not found."}, status=status.HTTP_404_NOT_FOUND)
        item.delete()
        return Response(CartSerializer(cart, context={"request": request}).data)


class CartApplyCouponView(APIView):
    """POST /api/v1/cart/apply-coupon/ — validates against promotions.Coupon
    and stores the code on the cart; discount is computed in CartSerializer
    so it's always derived, never stored stale."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from promotions.models import Coupon

        cart = get_or_create_cart(request)
        code = (request.data.get("code") or "").strip().upper()
        if not code:
            return Response({"detail": "Coupon code is required."}, status=status.HTTP_400_BAD_REQUEST)

        coupon = Coupon.objects.filter(code__iexact=code).first()
        if not coupon:
            return Response({"detail": "Coupon not found."}, status=status.HTTP_404_NOT_FOUND)

        valid, message = coupon.is_valid_now()
        if not valid:
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        if cart.subtotal < coupon.min_order_value:
            return Response(
                {"detail": f"This coupon requires a minimum order of {coupon.min_order_value} JOD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart.coupon_code = coupon.code
        cart.save(update_fields=["coupon_code"])
        return Response(CartSerializer(cart, context={"request": request}).data)

    def delete(self, request):
        cart = get_or_create_cart(request)
        cart.coupon_code = ""
        cart.save(update_fields=["coupon_code"])
        return Response(CartSerializer(cart, context={"request": request}).data)
