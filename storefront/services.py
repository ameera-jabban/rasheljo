"""Thin query/data layer for the Django-templates storefront.

Every function here talks to the existing models and the existing business logic
directly (``cart.views.get_or_create_cart``, ``Product.objects.with_ratings()``,
``promotions.models.Coupon`` …). Nothing here calls the project's own HTTP API.
The DRF serializers/viewsets stay untouched and parallel.
"""
from __future__ import annotations

from django.db.models import Prefetch

from catalog.filters import ProductFilter
from catalog.models import Brand, Category, Product, ProductAttribute, ProductImage
from content.models import HomepageVideo, Policy, SiteSettings

PAGE_SIZE = 24
BADGE_LABEL_KEYS = {
    "bestseller": "badge.bestseller",
    "new_arrival": "badge.new_arrival",
    "hot_offer": "badge.hot_offer",
    "last_chance": "badge.last_chance",
    "set": "badge.set",
}


# --- Global chrome ----------------------------------------------------------

def get_site_settings() -> SiteSettings:
    return SiteSettings.load()


def cart_badge_count(request) -> int:
    """Total item quantity for the header badge — WITHOUT creating a cart/session
    for a fresh anonymous visitor (matches the effect of the React header, which
    just shows 0 until the first add)."""
    from cart.models import Cart

    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        cart = Cart.objects.filter(user=user).first()
    else:
        session_key = request.session.session_key
        cart = Cart.objects.filter(session_key=session_key).first() if session_key else None
    if not cart:
        return 0
    return sum(item.quantity for item in cart.items.all())


def get_cart(request):
    """The real (create-if-missing) cart — use only on cart/checkout/add paths."""
    from cart.views import get_or_create_cart

    return get_or_create_cart(request)


# --- Catalog --------------------------------------------------------------

def products_base():
    return (
        Product.objects.filter(is_active=True)
        .with_ratings()
        .select_related("brand", "category")
        .prefetch_related(Prefetch("images", queryset=ProductImage.objects.order_by("sort_order")))
    )


def primary_image_url(product) -> str | None:
    images = list(product.images.all())
    if not images:
        return None
    first = min(images, key=lambda i: i.sort_order)
    return first.image.url


def rail_products(badge: str, limit: int = 4):
    return list(products_base().filter(badge_type=badge).order_by("-created_at")[:limit])


def filtered_products(query_params, *, landing=None, landing_slug=None):
    """Replicates catalog.views.ProductListView: ProductFilter + search + ordering.
    ``landing`` (one of brand/category/skin-type/search) pins one facet from the URL,
    exactly like the React Shop page. Returns (queryset, applied_filters_dict)."""
    data = {k: v for k, v in query_params.items() if v not in (None, "")}

    if landing == "brand":
        data["brand"] = landing_slug
    elif landing == "category":
        data["category"] = landing_slug
    elif landing == "skin-type":
        data["skin_type"] = landing_slug

    search = (query_params.get("q") or "").strip()

    fs = ProductFilter(data, queryset=products_base())
    qs = fs.qs

    if search:
        from django.db.models import Q

        qs = qs.filter(
            Q(name_en__icontains=search)
            | Q(name_ar__icontains=search)
            | Q(sku__icontains=search)
            | Q(description_en__icontains=search)
        )

    ordering = query_params.get("ordering") or "-created_at"
    allowed = {"price", "-price", "created_at", "-created_at", "name_en", "-name_en"}
    if ordering not in allowed:
        ordering = "-created_at"
    qs = qs.order_by(ordering)

    return qs, data


def brands():
    return Brand.objects.filter(is_active=True).order_by("name_en")


def categories():
    return Category.objects.filter(is_active=True).order_by("name_en")


def skin_types():
    return ProductAttribute.objects.filter(attribute_type="skin_type").order_by("value_en")


def get_brand(slug):
    return Brand.objects.filter(is_active=True, slug=slug).first()


def get_category(slug):
    return Category.objects.filter(is_active=True, slug=slug).first()


def get_skin_type(slug):
    return ProductAttribute.objects.filter(attribute_type="skin_type", slug=slug).first()


def get_product(slug):
    return products_base().prefetch_related("attributes", "variants").filter(slug=slug).first()


def recommendations(product, limit=8):
    qs = products_base().exclude(id=product.id)
    if product.category_id:
        same_cat = qs.filter(category_id=product.category_id)
        if same_cat.exists():
            return list(same_cat[:limit])
    return list(qs.filter(brand_id=product.brand_id)[:limit])


def search_everything(q: str):
    q = (q or "").strip()
    if not q:
        return {"products": [], "categories": [], "brands": []}
    from django.db.models import Q

    return {
        "products": list(
            products_base().filter(
                Q(name_en__icontains=q) | Q(name_ar__icontains=q) | Q(sku__icontains=q)
            )[:12]
        ),
        "categories": list(Category.objects.filter(is_active=True, name_en__icontains=q)[:5]),
        "brands": list(Brand.objects.filter(is_active=True, name_en__icontains=q)[:5]),
    }


# --- Homepage ------------------------------------------------------------

def homepage_videos_by_slot() -> dict:
    rows = HomepageVideo.objects.filter(is_active=True).order_by("slot", "sort_order")
    by_slot: dict[str, HomepageVideo] = {}
    for row in rows:
        by_slot.setdefault(row.slot, row)
    return by_slot


def video_src(video: HomepageVideo) -> str | None:
    if video is None:
        return None
    if video.video_file:
        return video.video_file.url
    return video.video_url or None


# --- Policies ----------------------------------------------------------

def active_policies():
    return Policy.objects.filter(is_active=True)


def get_policy(slug):
    return Policy.objects.filter(is_active=True, slug=slug).first()
