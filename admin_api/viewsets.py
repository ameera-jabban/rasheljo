from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from catalog.models import Brand, Category, Product, ProductAttribute, ProductImage
from content.models import HomepageVideo, Policy, SiteSettings
from content.serializers import SiteSettingsSerializer
from notify.models import Notification
from orders.models import Order
from payments.models import Payment
from promotions.models import Coupon, Promotion
from reviews.models import Review
from shipping.models import ShippingMethod, ShippingZone

from .permissions import IsStaffUser
from .serializers import (
    AdminBrandSerializer,
    AdminCategorySerializer,
    AdminCouponSerializer,
    AdminCustomerSerializer,
    AdminHomepageVideoSerializer,
    AdminNotificationSerializer,
    AdminPolicySerializer,
    AdminOrderSerializer,
    AdminOrderStatusUpdateSerializer,
    AdminPaymentSerializer,
    AdminProductAttributeSerializer,
    AdminProductImageSerializer,
    AdminProductSerializer,
    AdminPromotionSerializer,
    AdminReviewSerializer,
    AdminShippingMethodSerializer,
    AdminShippingZoneSerializer,
)

User = get_user_model()


class AdminPolicyViewSet(viewsets.ModelViewSet):
    """Full CRUD on policy pages. The four default slugs are seeded by a data
    migration, but staff can add more (e.g. a cookie policy) — not hard-capped."""

    queryset = Policy.objects.all().order_by("slug")
    serializer_class = AdminPolicySerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["is_active"]
    search_fields = ["slug", "title_en", "title_ar"]


class AdminHomepageVideoViewSet(viewsets.ModelViewSet):
    queryset = HomepageVideo.objects.all().order_by("slot", "sort_order")
    serializer_class = AdminHomepageVideoSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["slot", "is_active"]


class AdminSiteSettingsView(generics.RetrieveUpdateAPIView):
    """Singleton — GET/PATCH only, no list/create/delete. Multipart upload for
    `logo` works via DRF's default parsers, same as AdminProductImageViewSet."""

    serializer_class = SiteSettingsSerializer
    permission_classes = [IsStaffUser]
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self):
        return SiteSettings.load()


class AdminProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("brand", "category").prefetch_related("images").order_by("-created_at")
    serializer_class = AdminProductSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["brand", "category", "is_active", "badge_type", "ar_machine_translated"]
    search_fields = ["sku", "name_en", "name_ar"]


class AdminProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = AdminProductImageSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["product"]


class AdminProductAttributeViewSet(viewsets.ModelViewSet):
    queryset = ProductAttribute.objects.all()
    serializer_class = AdminProductAttributeSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["attribute_type", "ar_machine_translated"]


class AdminBrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all().order_by("name_en")
    serializer_class = AdminBrandSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["is_active", "ar_machine_translated"]


class AdminCategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by("name_en")
    serializer_class = AdminCategorySerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["is_active", "ar_machine_translated", "parent"]


class AdminOrderViewSet(viewsets.ReadOnlyModelViewSet):
    """Read + a dedicated status-transition action — never a raw field PATCH,
    so every status change still goes through Order.transition_to() and its
    validation, matching the enforced state machine from the core app."""

    queryset = Order.objects.exclude(status="draft").select_related("user", "shipping_address", "shipping_method").prefetch_related("items").order_by("-created_at")
    serializer_class = AdminOrderSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["status", "payment_method"]
    search_fields = ["id", "user__email"]

    @action(detail=True, methods=["post"])
    def update_status(self, request, pk=None):
        order = self.get_object()
        serializer = AdminOrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            order.transition_to(serializer.validated_data["status"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(AdminOrderSerializer(order).data)


class AdminCustomerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.filter(is_staff=False).order_by("-date_joined")
    serializer_class = AdminCustomerSerializer
    permission_classes = [IsStaffUser]
    search_fields = ["email", "first_name", "last_name"]

    @action(detail=True, methods=["post"])
    def toggle_active(self, request, pk=None):
        customer = self.get_object()
        customer.is_active = not customer.is_active
        customer.save(update_fields=["is_active"])
        return Response(AdminCustomerSerializer(customer).data)


class AdminReviewViewSet(viewsets.ModelViewSet):
    """Moderation only — rating/body/product are read-only in the serializer,
    admins can only approve/reject or delete, never rewrite a customer's review."""

    queryset = Review.objects.select_related("product", "user").order_by("-created_at")
    serializer_class = AdminReviewSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["is_approved", "rating"]
    http_method_names = ["get", "patch", "delete", "head", "options"]


class AdminCouponViewSet(viewsets.ModelViewSet):
    queryset = Coupon.objects.all().order_by("-id")
    serializer_class = AdminCouponSerializer
    permission_classes = [IsStaffUser]


class AdminPromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.all().order_by("-id")
    serializer_class = AdminPromotionSerializer
    permission_classes = [IsStaffUser]


class AdminShippingMethodViewSet(viewsets.ModelViewSet):
    queryset = ShippingMethod.objects.all().order_by("cost")
    serializer_class = AdminShippingMethodSerializer
    permission_classes = [IsStaffUser]


class AdminShippingZoneViewSet(viewsets.ModelViewSet):
    queryset = ShippingZone.objects.all().order_by("city")
    serializer_class = AdminShippingZoneSerializer
    permission_classes = [IsStaffUser]


class AdminPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.select_related("order", "order__user").order_by("-created_at")
    serializer_class = AdminPaymentSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["status", "method"]


class AdminNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Notification.objects.select_related("user").order_by("-created_at")
    serializer_class = AdminNotificationSerializer
    permission_classes = [IsStaffUser]
    filterset_fields = ["notification_type", "is_read"]
