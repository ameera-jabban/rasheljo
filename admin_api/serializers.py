from django.contrib.auth import get_user_model
from rest_framework import serializers

from catalog.models import Brand, Category, Product, ProductAttribute, ProductImage
from content.models import HomepageVideo, Policy
from notify.models import Notification
from orders.models import Order, OrderItem
from payments.models import Payment
from promotions.models import Coupon, Promotion
from reviews.models import Review
from shipping.models import ShippingMethod, ShippingZone

User = get_user_model()


# --- Content: policies (writable) ---

class AdminPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Policy
        fields = [
            "id", "slug", "title_en", "title_ar",
            "body_en", "body_ar", "is_active", "updated_at",
        ]
        read_only_fields = ["updated_at"]
        extra_kwargs = {"title_ar": {"required": False}}


# --- Content: homepage videos (writable) ---

class AdminHomepageVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomepageVideo
        fields = [
            "id", "slot", "video_file", "video_url", "poster_image",
            "title_en", "title_ar", "subtitle_en", "subtitle_ar",
            "link_url", "sort_order", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        """An active row must resolve to exactly one playable source — mirrors
        HomepageVideo.clean() so the API returns 400 instead of a later 500.
        Setting one source in an update clears the other (see update())."""
        setting_file = bool(attrs.get("video_file"))
        setting_url = bool(attrs.get("video_url"))
        if setting_file and setting_url:
            raise serializers.ValidationError("Set either video_file or video_url, not both.")

        if setting_file:
            final_has_file, final_has_url = True, False
        elif setting_url:
            final_has_file, final_has_url = False, True
        elif self.instance is not None:
            final_has_file = bool(self.instance.video_file)
            final_has_url = bool(self.instance.video_url)
        else:
            final_has_file = final_has_url = False

        is_active = attrs.get("is_active", getattr(self.instance, "is_active", True))
        if not is_active:
            return attrs
        if final_has_file and final_has_url:
            raise serializers.ValidationError(
                "This video has both an uploaded file and an external URL — remove one before activating it."
            )
        if not final_has_file and not final_has_url:
            raise serializers.ValidationError(
                "An active homepage video needs either video_file or video_url."
            )
        return attrs

    def update(self, instance, validated_data):
        # Whichever source the admin just set wins; the other is cleared so a row
        # never carries a stale file + URL at the same time.
        if validated_data.get("video_file"):
            validated_data["video_url"] = ""
        elif validated_data.get("video_url"):
            validated_data["video_file"] = None
        return super().update(instance, validated_data)


# --- Catalog (writable) ---

class AdminProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "product", "image", "sort_order", "alt_text_en", "alt_text_ar"]


class AdminBrandSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Brand
        fields = ["id", "name_en", "name_ar", "slug", "description_en", "description_ar", "logo", "banner", "is_active", "ar_machine_translated", "product_count"]
        extra_kwargs = {"slug": {"required": False}}


class AdminCategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(source="products.count", read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name_en", "name_ar", "slug", "parent", "image", "description_en", "description_ar", "is_active", "ar_machine_translated", "product_count"]
        extra_kwargs = {"slug": {"required": False}}


class AdminProductAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAttribute
        fields = ["id", "attribute_type", "value_en", "value_ar", "slug", "ar_machine_translated"]
        extra_kwargs = {"slug": {"required": False}}


class AdminProductSerializer(serializers.ModelSerializer):
    images = AdminProductImageSerializer(many=True, read_only=True)
    brand_name = serializers.CharField(source="brand.name_en", read_only=True)
    category_name = serializers.CharField(source="category.name_en", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "sku", "name_en", "name_ar", "slug", "description_en", "description_ar",
            "benefits_en", "benefits_ar",
            "how_to_use_en", "how_to_use_ar", "brand", "brand_name", "category", "category_name",
            "attributes", "price", "sale_price", "stock", "pack_size", "badge_type", "is_active",
            "ar_machine_translated", "images", "created_at", "updated_at",
        ]
        extra_kwargs = {"slug": {"required": False}}


# --- Orders (status transition, not free-form write) ---

class AdminOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "unit_price", "quantity"]


class AdminOrderSerializer(serializers.ModelSerializer):
    items = AdminOrderItemSerializer(many=True, read_only=True)
    customer_email = serializers.CharField(source="user.email", read_only=True)
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id", "status", "customer_email", "customer_name", "shipping_address", "shipping_method",
            "payment_method", "coupon_code", "discount_amount", "shipping_cost", "subtotal", "total",
            "items", "created_at", "updated_at",
        ]

    def get_customer_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email


class AdminOrderStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)


# --- Customers ---

class AdminCustomerSerializer(serializers.ModelSerializer):
    order_count = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "is_active", "date_joined", "order_count", "total_spent"]

    def get_order_count(self, obj):
        return obj.orders.exclude(status="draft").count()

    def get_total_spent(self, obj):
        from django.db.models import Sum
        total = obj.orders.filter(status__in=["confirmed", "processing", "shipped", "delivered"]).aggregate(s=Sum("total"))["s"]
        return str(total or 0)


# --- Reviews moderation ---

class AdminReviewSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name_en", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = Review
        fields = ["id", "product", "product_name", "user_email", "rating", "title", "body", "is_approved", "created_at"]
        read_only_fields = ["product", "rating", "title", "body", "created_at"]


# --- Promotions / coupons ---

class AdminCouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = [
            "id", "code", "discount_type", "discount_value", "min_order_value",
            "max_uses", "times_used", "valid_from", "valid_until", "is_active",
        ]
        read_only_fields = ["times_used"]


class AdminPromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = ["id", "name", "slug", "description", "products", "starts_at", "ends_at", "is_active"]
        extra_kwargs = {"slug": {"required": False}}


# --- Shipping ---

class AdminShippingMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = ["id", "name_en", "name_ar", "cost", "estimated_days_min", "estimated_days_max", "is_active"]


class AdminShippingZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingZone
        fields = ["id", "city", "method", "cost_override"]


# --- Payments (read-only) ---

class AdminPaymentSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source="order.id", read_only=True)
    customer_email = serializers.CharField(source="order.user.email", read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "order_id", "customer_email", "method", "status", "amount", "provider_reference", "created_at"]


# --- Notifications (read-only log for admin) ---

class AdminNotificationSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "user_email", "notification_type", "title", "body", "is_read", "created_at"]
