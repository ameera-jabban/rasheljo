from django.urls import path
from rest_framework.routers import DefaultRouter

from .viewsets import (
    AdminBrandViewSet,
    AdminCategoryViewSet,
    AdminCouponViewSet,
    AdminCustomerViewSet,
    AdminHomepageVideoViewSet,
    AdminNotificationViewSet,
    AdminOrderViewSet,
    AdminPolicyViewSet,
    AdminPaymentViewSet,
    AdminProductAttributeViewSet,
    AdminProductImageViewSet,
    AdminProductViewSet,
    AdminPromotionViewSet,
    AdminReviewViewSet,
    AdminShippingMethodViewSet,
    AdminShippingZoneViewSet,
    AdminSiteSettingsView,
)

router = DefaultRouter()
router.register("admin/products", AdminProductViewSet, basename="admin-product")
router.register("admin/product-images", AdminProductImageViewSet, basename="admin-product-image")
router.register("admin/product-attributes", AdminProductAttributeViewSet, basename="admin-product-attribute")
router.register("admin/brands", AdminBrandViewSet, basename="admin-brand")
router.register("admin/categories", AdminCategoryViewSet, basename="admin-category")
router.register("admin/homepage-videos", AdminHomepageVideoViewSet, basename="admin-homepage-video")
router.register("admin/policies", AdminPolicyViewSet, basename="admin-policy")
router.register("admin/orders", AdminOrderViewSet, basename="admin-order")
router.register("admin/customers", AdminCustomerViewSet, basename="admin-customer")
router.register("admin/reviews", AdminReviewViewSet, basename="admin-review")
router.register("admin/coupons", AdminCouponViewSet, basename="admin-coupon")
router.register("admin/promotions", AdminPromotionViewSet, basename="admin-promotion")
router.register("admin/shipping-methods", AdminShippingMethodViewSet, basename="admin-shipping-method")
router.register("admin/shipping-zones", AdminShippingZoneViewSet, basename="admin-shipping-zone")
router.register("admin/payments", AdminPaymentViewSet, basename="admin-payment")
router.register("admin/notifications", AdminNotificationViewSet, basename="admin-notification")

urlpatterns = router.urls + [
    path("admin/site-settings/", AdminSiteSettingsView.as_view(), name="admin-site-settings"),
]
