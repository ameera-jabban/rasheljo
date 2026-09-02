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

# --- Reference-data cache (shared Redis) ------------------------------------
# Brands / categories / skin types / site settings / homepage videos / policies
# change rarely but are read on nearly every page, and the DB is often a remote
# instance (~200ms/query). Cache the materialised objects in Redis
# (django.core.cache) for a minute so a page render isn't ~6 extra round-trips.
#
# Admin edits invalidate their key immediately via post_save/post_delete signals
# (storefront/signals.py) — Redis is shared, so every gunicorn worker sees the
# eviction at once. The _TTL is only a safety net if a signal never fires.
#
# Keys are prefixed `sf:ref:` to stay clear of the `sf:cat:` / `sf:catgen`
# catalog-cache keys in the same Redis DB. The cache is configured with
# IGNORE_EXCEPTIONS, so a Redis outage degrades to an uncached DB read.
_TTL = 60
_REF_PREFIX = "sf:ref:"


def _cached(key, producer):
    from django.core.cache import cache

    ckey = _REF_PREFIX + key
    try:
        hit = cache.get(ckey)
        if hit is not None:
            return hit
    except Exception:
        return producer()
    value = producer()
    if value is not None:
        try:
            cache.set(ckey, value, _TTL)
        except Exception:
            pass
    return value


def invalidate(*keys):
    """Evict cached reference data so the next call re-queries. Called from the
    signal handlers in storefront/signals.py when an admin edits it."""
    from django.core.cache import cache

    try:
        cache.delete_many([_REF_PREFIX + key for key in keys])
    except Exception:
        pass


# --- Redis-backed cache for catalog read paths ------------------------------
# Homepage rails and product-detail pages are the storefront's hottest reads and
# each is several DB round-trips (join brand/category, prefetch images, ratings
# aggregate). Cache the materialised objects in Redis (django.core.cache).
#
# Invalidation is generation-based: `sf:catgen` is one integer bumped on ANY
# catalog write (see catalog/signals.py) and embedded in every key, so a write
# instantly makes all prior entries unreachable — no key registry, no
# delete_pattern, identical behaviour on Redis and the locmem cache used in
# tests. Stale entries just age out via the TTL.
#
# The cache is configured with IGNORE_EXCEPTIONS, so if Redis is down every call
# here simply misses and hits the DB — same graceful degradation as `_cached`.
_CATALOG_TTL = 300  # 5 min ceiling; catalog writes invalidate sooner via the gen


def _catalog_gen() -> int:
    from django.core.cache import cache

    try:
        gen = cache.get("sf:catgen")
        if gen is None:
            cache.add("sf:catgen", 1, None)  # None timeout = never expire
            gen = cache.get("sf:catgen") or 1
        return int(gen)
    except Exception:
        return 0  # cache unavailable — stable sentinel so reads just miss


def bump_catalog_gen() -> None:
    """Invalidate every cached catalog read. Called from catalog signal handlers
    on Product / ProductImage / Brand / Category save + delete."""
    from django.core.cache import cache

    try:
        cache.incr("sf:catgen")
    except ValueError:  # key missing/expired
        cache.set("sf:catgen", 1, None)
    except Exception:
        pass


def _catalog_cached(suffix: str, producer):
    from django.core.cache import cache

    key = f"sf:cat:{_catalog_gen()}:{suffix}"
    try:
        hit = cache.get(key)
        if hit is not None:
            return hit
    except Exception:
        return producer()
    value = producer()
    if value is not None:  # don't cache misses (e.g. unknown product slug)
        try:
            cache.set(key, value, _CATALOG_TTL)
        except Exception:
            pass
    return value


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
    return _cached("site_settings", SiteSettings.load)


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


def existing_cart(request):
    """The current cart if one already exists, else None (no create, no session)."""
    from cart.models import Cart, CartItem

    _items = Prefetch(
        "items",
        queryset=CartItem.objects.select_related("product__brand").prefetch_related("product__images"),
    )
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return Cart.objects.filter(user=user).prefetch_related(_items).first()
    key = request.session.session_key
    return Cart.objects.filter(session_key=key).prefetch_related(_items).first() if key else None


def create_draft_order(request):
    """Snapshot the current cart into a fresh draft Order — mirrors
    orders.views.OrderCreateFromCartView. Clears any earlier abandoned draft for
    this user so we never accumulate them."""
    from django.db import transaction

    from orders.models import Order, OrderItem
    from promotions.models import Coupon

    cart = get_cart(request)
    if not cart.items.exists():
        return None, "empty"

    with transaction.atomic():
        Order.objects.filter(user=request.user, status="draft").delete()

        discount, coupon_code = 0, ""
        if cart.coupon_code:
            coupon = Coupon.objects.filter(code__iexact=cart.coupon_code).first()
            if coupon and coupon.is_valid_now()[0]:
                discount = coupon.calculate_discount(cart.subtotal)
                coupon_code = coupon.code

        order = Order.objects.create(
            user=request.user, payment_method="cod",
            coupon_code=coupon_code, discount_amount=discount,
        )
        for item in cart.items.select_related("product"):
            OrderItem.objects.create(
                order=order, product=item.product, product_name=item.product.name_en,
                unit_price=item.unit_price, quantity=item.quantity,
            )
        order.recalculate_totals()
    return order, None


def merge_guest_cart(request, user):
    """Move a pre-login guest cart's items onto the user's cart. Call right after
    django.contrib.auth.login() — that cycles the session key, orphaning the
    guest cart otherwise. Pass the session_key captured *before* login."""
    from cart.models import Cart, CartItem

    guest_key = getattr(request, "_pre_login_session_key", None)
    if not guest_key:
        return
    guest = Cart.objects.filter(session_key=guest_key, user=None).prefetch_related("items").first()
    if not guest or not guest.items.exists():
        if guest:
            guest.delete()
        return
    user_cart, _ = Cart.objects.get_or_create(user=user)
    for gi in guest.items.all():
        ui, created = CartItem.objects.get_or_create(
            cart=user_cart, product=gi.product, variant=gi.variant,
            defaults={"quantity": gi.quantity},
        )
        if not created:
            ui.quantity += gi.quantity
            ui.save(update_fields=["quantity"])
    if not user_cart.coupon_code and guest.coupon_code:
        user_cart.coupon_code = guest.coupon_code
        user_cart.save(update_fields=["coupon_code"])
    guest.delete()


def get_draft_order(request):
    from orders.models import Order

    oid = request.session.get("checkout_order_id")
    if oid:
        order = Order.objects.filter(id=oid, user=request.user, status="draft").first()
        if order:
            return order
    return Order.objects.filter(user=request.user, status="draft").order_by("-created_at").first()


def shipping_methods():
    from shipping.models import ShippingMethod

    return _cached("shipping_methods", lambda: list(ShippingMethod.objects.filter(is_active=True).order_by("cost")))


def cart_totals(cart):
    """subtotal / discount / total for a cart — mirrors CartSerializer (shipping is
    added later at checkout, not here)."""
    subtotal = cart.subtotal if cart else 0
    discount = 0
    if cart and cart.coupon_code:
        from promotions.models import Coupon

        coupon = Coupon.objects.filter(code__iexact=cart.coupon_code).first()
        if coupon and coupon.is_valid_now()[0]:
            discount = coupon.calculate_discount(subtotal)
    return {
        "subtotal": subtotal,
        "discount": discount,
        "total": subtotal - discount,
        "item_count": sum(i.quantity for i in cart.items.all()) if cart else 0,
    }


def cart_item_map(request):
    """{product_id: CartItem} for the current cart — lets product cards render the
    right add/stepper state without N queries. Memoised on the request so a page
    with several product rails doesn't refetch it."""
    if not hasattr(request, "_sf_cart_map"):
        cart = existing_cart(request)
        request._sf_cart_map = (
            {item.product_id: item for item in cart.items.all()} if cart else {}
        )
    return request._sf_cart_map


def wishlist_ids(request) -> set:
    if not hasattr(request, "_sf_wishlist_ids"):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            from wishlist.models import WishlistItem

            request._sf_wishlist_ids = set(
                WishlistItem.objects.filter(user=user).values_list("product_id", flat=True)
            )
        else:
            request._sf_wishlist_ids = set()
    return request._sf_wishlist_ids


def decorate_products(request, products):
    """Attach ``.cart_item`` and ``.in_wishlist`` to each product so templates and
    the {% include _product_card %} calls stay simple."""
    cmap = cart_item_map(request)
    wids = wishlist_ids(request)
    for p in products:
        p.cart_item = cmap.get(p.id)
        p.in_wishlist = p.id in wids
    return products


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
    return _catalog_cached(
        f"rail:{badge}:{limit}",
        lambda: list(products_base().filter(badge_type=badge).order_by("-created_at")[:limit]),
    )


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


_SHOP_FILTER_KEYS = (
    "q", "brand", "category", "skin_type", "badge",
    "min_price", "max_price", "in_stock", "ordering", "page",
)


def shop_products(query_params, *, landing=None, landing_slug=None):
    """Like `filtered_products`, but caches the *bare* landing pages — plain
    /shop and the brand / category / skin-type nav targets with no user filters
    or search, where the same key is requested over and over. Anything with a
    filter, a search term or a page number falls straight through to the DB
    (the combinatorial tail has a near-zero cache hit rate). Returns
    (list_or_queryset, applied) — a list is fine for Paginator."""
    qs, applied = filtered_products(query_params, landing=landing, landing_slug=landing_slug)
    bare = landing in ("brand", "category", "skin-type", "shop") and not any(
        k in query_params for k in _SHOP_FILTER_KEYS
    )
    if not bare:
        return qs, applied
    return _catalog_cached(f"shop:{landing}:{landing_slug}", lambda: list(qs)), applied


def brands():
    return _cached("brands", lambda: list(Brand.objects.filter(is_active=True).order_by("name_en")))


def categories():
    return _cached("categories", lambda: list(Category.objects.filter(is_active=True).order_by("name_en")))


def skin_types():
    return _cached(
        "skin_types",
        lambda: list(ProductAttribute.objects.filter(attribute_type="skin_type").order_by("value_en")),
    )


def get_brand(slug):
    return next((b for b in brands() if b.slug == slug), None)


def get_category(slug):
    return next((c for c in categories() if c.slug == slug), None)


def get_skin_type(slug):
    return next((s for s in skin_types() if s.slug == slug), None)


def get_product(slug):
    return _catalog_cached(
        f"pdp:{slug}",
        lambda: products_base().prefetch_related("attributes", "variants").filter(slug=slug).first(),
    )


def recommendations(product, limit=8):
    def _build():
        qs = products_base().exclude(id=product.id)
        if product.category_id:
            same_cat = qs.filter(category_id=product.category_id)
            if same_cat.exists():
                return list(same_cat[:limit])
        return list(qs.filter(brand_id=product.brand_id)[:limit])

    return _catalog_cached(f"recs:{product.id}:{limit}", _build)


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
    def _load():
        by_slot: dict[str, HomepageVideo] = {}
        for row in HomepageVideo.objects.filter(is_active=True).order_by("slot", "sort_order"):
            by_slot.setdefault(row.slot, row)
        return by_slot

    return _cached("homepage_videos", _load)


def video_src(video: HomepageVideo) -> str | None:
    if video is None:
        return None
    if video.video_file:
        return video.video_file.url
    return video.video_url or None


# --- Policies ----------------------------------------------------------

def active_policies():
    return _cached("policies", lambda: list(Policy.objects.filter(is_active=True)))


def get_policy(slug):
    return Policy.objects.filter(is_active=True, slug=slug).first()
