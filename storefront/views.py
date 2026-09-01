"""Django-templates storefront — server-rendered views.

Parallel to the React app in ./frontend (untouched). These views talk to the
existing models / service functions directly; they never call the project's own
HTTP API.
"""
from __future__ import annotations

import functools
import json

from django.core.paginator import Paginator
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from storefront import services
from storefront.i18n import translate


def _login_required(view):
    """Storefront session-auth gate — bounces to /<lang>/login/?next=… for a page
    request, or 401 for an htmx POST (the client shows the message inline)."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view(request, *args, **kwargs)
        if request.headers.get("HX-Request"):
            resp = HttpResponse(status=401)
            resp["HX-Redirect"] = f"/{request.LANGUAGE_CODE}/login/?next={request.path}"
            return resp
        return redirect(f"/{request.LANGUAGE_CODE}/login/?next={request.get_full_path()}")

    return wrapper


# --- Home ----------------------------------------------------------------

def home(request):
    by_slot = services.homepage_videos_by_slot()
    hero = by_slot.get("hero")
    section_1 = by_slot.get("section_1")
    section_2 = by_slot.get("section_2")
    section_3 = by_slot.get("section_3")

    hero_link = f"/{request.LANGUAGE_CODE}/shop"
    if hero and hero.link_url:
        hero_link = hero.link_url if hero.link_url.startswith("http") else f"/{request.LANGUAGE_CODE}{hero.link_url}"

    ctx = {
        "hero": hero,
        "hero_src": services.video_src(hero),
        "hero_link": hero_link,
        "section_1": section_1, "section_1_src": services.video_src(section_1),
        "section_2": section_2, "section_2_src": services.video_src(section_2),
        "section_3": section_3, "section_3_src": services.video_src(section_3),
        "trust_items": [
            translate("home.trustAuthentic"),
            translate("home.trustDelivery"),
            translate("home.trustCod"),
        ],
        "t_hot_offers": translate("home.hotOffers"),
        "t_bestsellers": translate("home.bestsellers"),
        "t_last_chance": translate("home.lastChance"),
        "hot_offers": services.decorate_products(request, services.rail_products("hot_offer")),
        "bestsellers": services.decorate_products(request, services.rail_products("bestseller")),
        "last_chance": services.decorate_products(request, services.rail_products("last_chance")),
    }
    return render(request, "storefront/home.html", ctx)


# --- Cart (htmx fragments) ---------------------------------------------

def _cart_control_response(request, product, *, message=None, bump=False):
    """Re-render the add-to-cart control for `product` + OOB header badge, and
    (optionally) fire the toast via an HX-Trigger header. Shared by add/update/
    remove so the card, badge and toast never drift — the htmx equivalent of the
    React ['cart'] query cache being the single source of truth."""
    cart_item = services.cart_item_map(request).get(product.id)
    ctx = {
        "product": product,
        "cart_item": cart_item,
        "cart_count": services.cart_badge_count(request),
        "bump": bump,
    }
    html = render(request, "storefront/partials/_add_to_cart_control.html", ctx).content.decode()
    html += render(request, "storefront/partials/_cart_badge.html", {**ctx, "oob": True}).content.decode()
    resp = HttpResponse(html)
    if message:
        import json

        resp["HX-Trigger"] = json.dumps({"toast": message})
    return resp


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@require_POST
def cart_add(request):
    from catalog.models import Product

    pid = _int(request.POST.get("product_id"))
    product = Product.objects.filter(id=pid, is_active=True).first() if pid else None
    if not product:
        return HttpResponse(status=404)

    cart = services.get_cart(request)
    from cart.models import CartItem

    qty = max(1, int(request.POST.get("quantity", 1)))
    fresh = _reload_product(product.id)
    if product.stock < qty:
        return _cart_control_response(request, fresh, message=translate("cart.updateFailed"))
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, variant=None,
                                                   defaults={"quantity": qty})
    if not created:
        item.quantity += qty
        item.save()

    if not request.POST.get("control"):
        # Product-detail page: keep the qty picker + button, just confirm + update badge.
        in_cart = services.cart_item_map(request).get(product.id)
        ctx = {"product": fresh, "cart_item": in_cart, "cart_count": services.cart_badge_count(request),
               "in_cart_qty": in_cart.quantity if in_cart else qty}
        html = render(request, "storefront/partials/_pdp_cart_msg.html", ctx).content.decode()
        html += render(request, "storefront/partials/_cart_badge.html", {**ctx, "oob": True}).content.decode()
        resp = HttpResponse(html)
        import json
        resp["HX-Trigger"] = json.dumps({"toast": translate("product.addedToCart")})
        return resp

    return _cart_control_response(request, fresh, message=translate("product.addedToCart"), bump=True)


def _cart_page_response(request, *, message=None):
    """Re-render the whole cart body (lines + summary) + OOB badge — used by the
    cart page's own qty/remove/coupon controls."""
    ctx = _cart_context(request)
    html = render(request, "storefront/partials/_cart_body.html", ctx).content.decode()
    html += render(request, "storefront/partials/_cart_badge.html",
                   {"cart_count": ctx["totals"]["item_count"], "oob": True}).content.decode()
    resp = HttpResponse(html)
    if message:
        import json
        resp["HX-Trigger"] = json.dumps({"toast": message})
    return resp


def _from_cart_page(request):
    return request.POST.get("page") == "cart" or request.GET.get("page") == "cart"


@require_POST
def cart_update(request, item_id):
    from cart.models import CartItem

    cart = services.get_cart(request)
    item = CartItem.objects.filter(cart=cart, id=item_id).select_related("product").first()
    if not item:
        return _cart_page_response(request) if _from_cart_page(request) else HttpResponse(status=404)
    pid = item.product_id
    qty = int(request.POST.get("quantity", item.quantity))
    msg = None
    if qty < 1:
        item.delete()
    elif item.product.stock < qty:
        msg = translate("cart.updateFailed")
    else:
        item.quantity = qty
        item.save()
    if _from_cart_page(request):
        return _cart_page_response(request, message=msg)
    return _cart_control_response(request, _reload_product(pid), message=msg)


@require_POST
def cart_remove(request, item_id):
    from cart.models import CartItem

    cart = services.get_cart(request)
    item = CartItem.objects.filter(cart=cart, id=item_id).first()
    product_id = _int(request.POST.get("product_id"))
    removed = False
    if item:
        product_id = item.product_id
        item.delete()
        removed = True
    # Success toast only once the row is actually gone — reuses the same
    # HX-Trigger `toast` mechanism as add-to-cart. No message → no toast.
    msg = translate("cart.removedToast") if removed else None
    if _from_cart_page(request):
        return _cart_page_response(request, message=msg)
    product = _reload_product(product_id)
    if not product:
        resp = HttpResponse(status=204)
        if msg:
            import json
            resp["HX-Trigger"] = json.dumps({"toast": msg})
        return resp
    return _cart_control_response(request, product, message=msg)


# --- Cart page + coupon ------------------------------------------------

def _cart_context(request):
    cart = services.existing_cart(request)
    totals = services.cart_totals(cart)
    return {"cart": cart, "items": list(cart.items.all()) if cart else [], "totals": totals}


def cart_page(request):
    return render(request, "storefront/cart.html", _cart_context(request))


@require_POST
def coupon_apply(request):
    from promotions.models import Coupon

    cart = services.get_cart(request)
    code = (request.POST.get("code") or "").strip().upper()
    error = None
    if not code:
        error = translate("cart.invalidCoupon")
    else:
        coupon = Coupon.objects.filter(code__iexact=code).first()
        valid = coupon.is_valid_now() if coupon else (False, "")
        if not coupon or not valid[0]:
            error = translate("cart.invalidCoupon")
        elif cart.subtotal < coupon.min_order_value:
            error = translate("cart.invalidCoupon")
        else:
            cart.coupon_code = coupon.code
            cart.save(update_fields=["coupon_code"])
    ctx = _cart_context(request)
    ctx["coupon_error"] = error
    return render(request, "storefront/partials/_cart_summary.html", ctx)


@require_POST
def coupon_remove(request):
    cart = services.get_cart(request)
    cart.coupon_code = ""
    cart.save(update_fields=["coupon_code"])
    return render(request, "storefront/partials/_cart_summary.html", _cart_context(request))


def _reload_product(product_id):
    return services.products_base().filter(id=product_id).first()


# --- Wishlist (htmx fragment) ----------------------------------------

@require_POST
def wishlist_toggle(request, product_id):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    from catalog.models import Product
    from wishlist.models import WishlistItem

    product = Product.objects.filter(id=product_id, is_active=True).first()
    if not product:
        return HttpResponse(status=404)
    item = WishlistItem.objects.filter(user=request.user, product=product).first()
    if item:
        item.delete()
        in_wishlist = False
    else:
        WishlistItem.objects.create(user=request.user, product=product)
        in_wishlist = True
    return render(request, "storefront/partials/_wishlist_button.html", {
        "product": product, "in_wishlist": in_wishlist,
        "size": request.GET.get("size", "md"), "variant": request.GET.get("variant", "default"),
    })


# --- Placeholders (built later in Phase 1) ----------------------------

def _placeholder(request, page):
    return render(request, "storefront/_placeholder.html", {"page": page})


# --- Shop / brand / category / skin-type / search --------------------

def _shop_identity(landing, is_ar, brand, category, skin_type, q):
    """h1 + intro copy — ports the useMemo block in Shop.tsx."""
    from storefront.templatetags.storefront import localized

    if landing == "brand" and brand:
        name = localized(brand)
        return {"h1": name, "intro": (brand.description_ar if is_ar else brand.description_en) or ""}
    if landing == "category" and category:
        name = localized(category)
        return {"h1": name, "intro": (category.description_ar if is_ar else category.description_en) or ""}
    if landing == "skin-type" and skin_type:
        name = localized(skin_type, "value")
        return {"h1": (f"العناية بالبشرة — {name}" if is_ar else f"{name} Skincare"), "intro": ""}
    if landing == "search":
        return {"h1": (f'نتائج البحث عن "{q}"' if is_ar else f"Search results for “{q}”"), "intro": ""}
    return {"h1": ("جميع المنتجات" if is_ar else "All Products"), "intro": ""}


def _shop(request, *, landing, slug=None):
    lang = request.LANGUAGE_CODE
    is_ar = lang == "ar"

    brand = category = skin_type = None
    if landing == "brand":
        brand = services.get_brand(slug) or _raise404()
    elif landing == "category":
        category = services.get_category(slug) or _raise404()
    elif landing == "skin-type":
        skin_type = services.get_skin_type(slug) or _raise404()

    q = (request.GET.get("q") or "").strip()
    qs, applied = services.shop_products(request.GET, landing=landing, landing_slug=slug)

    paginator = Paginator(qs, services.PAGE_SIZE)
    try:
        page_num = max(1, int(request.GET.get("page") or 1))
    except ValueError:
        page_num = 1
    page_obj = paginator.get_page(page_num)
    products = services.decorate_products(request, list(page_obj.object_list))

    # Active-facet chips (only on the plain /shop landing, matching Shop.tsx)
    chips = []
    if landing == "shop":
        if applied.get("brand"):
            b = services.get_brand(applied["brand"])
            chips.append({"key": "brand", "label": _lbl(b) if b else applied["brand"]})
        if applied.get("category"):
            c = services.get_category(applied["category"])
            chips.append({"key": "category", "label": _lbl(c) if c else applied["category"]})
        if applied.get("skin_type"):
            st = services.get_skin_type(applied["skin_type"])
            chips.append({"key": "skin_type", "label": _lbl(st, "value") if st else applied["skin_type"]})

    identity = _shop_identity(landing, is_ar, brand, category, skin_type, q)
    base_crumb = {"name": "الرئيسية" if is_ar else "Home", "url": f"/{lang}/"}
    shop_url = f"/{lang}/shop/"
    if landing == "shop":
        crumbs = [base_crumb, {"name": identity["h1"]}]
    elif landing == "search":
        crumbs = [base_crumb, {"name": "البحث" if is_ar else "Search"}]
    else:
        crumbs = [base_crumb, {"name": "المتجر" if is_ar else "Shop", "url": shop_url}, {"name": identity["h1"]}]

    ctx = {
        "landing": landing,
        "identity": identity,
        "crumbs": crumbs,
        "q": q,
        "page_obj": page_obj,
        "products": products,
        "total_count": paginator.count,
        "num_pages": paginator.num_pages,
        "brands": None if landing == "brand" else services.brands(),
        "categories": None if landing == "category" else services.categories(),
        "skin_types": None if landing == "skin-type" else services.skin_types(),
        "applied": applied,
        "chips": chips,
        "shop_action": request.path,
    }
    template = (
        "storefront/partials/_shop_results.html"
        if request.headers.get("HX-Request")
        else "storefront/shop.html"
    )
    return render(request, template, ctx)


def _raise404():
    raise Http404


def _lbl(entity, field="name"):
    from storefront.templatetags.storefront import localized

    return localized(entity, field)


def shop(request):
    return _shop(request, landing="shop")


def brand_landing(request, slug):
    return _shop(request, landing="brand", slug=slug)


def category_landing(request, slug):
    return _shop(request, landing="category", slug=slug)


def skin_type_landing(request, slug):
    return _shop(request, landing="skin-type", slug=slug)


def search(request):
    return _shop(request, landing="search")


LOW_STOCK_THRESHOLD = 10


def _reviews_for(product):
    from reviews.models import Review

    return list(Review.objects.filter(product=product, is_approved=True).select_related("user"))


def _review_ctx(request, product, reviews=None):
    reviews = _reviews_for(product) if reviews is None else reviews
    for r in reviews:
        r.display_name = r.user.first_name or r.user.email.split("@")[0]
    count = len(reviews)
    avg = round(sum(r.rating for r in reviews) / count, 1) if count else None
    can_review = request.user.is_authenticated and not any(r.user_id == request.user.id for r in reviews)
    return {
        "product": product,
        "reviews": reviews,
        "review_count": count,
        "review_avg": avg,
        "can_review": can_review,
        "already_reviewed": request.user.is_authenticated and any(r.user_id == request.user.id for r in reviews),
    }


def product_detail(request, slug):
    product = services.get_product(slug)
    if not product:
        raise Http404
    services.decorate_products(request, [product])
    lang = request.LANGUAGE_CODE
    is_ar = lang == "ar"

    reviews = _reviews_for(product)
    recs = services.decorate_products(request, services.recommendations(product, 4))

    category = product.category
    crumbs = [
        {"name": "الرئيسية" if is_ar else "Home", "url": f"/{lang}/"},
        {"name": "المتجر" if is_ar else "Shop", "url": f"/{lang}/shop/"},
    ]
    if category:
        crumbs.append({"name": _lbl(category), "url": f"/{lang}/category/{category.slug}/"})
    crumbs.append({"name": _lbl(product)})

    ctx = {
        "product": product,
        "crumbs": crumbs,
        "benefits": product.benefits_list("ar" if is_ar else "en"),
        "description": (product.description_ar if is_ar else product.description_en),
        "how_to_use": (product.how_to_use_ar if is_ar else product.how_to_use_en),
        "low_stock": 0 < product.stock <= LOW_STOCK_THRESHOLD,
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
        "recommendations": recs,
        "trust_rows": [
            translate("product.authentic"),
            translate("product.deliveryInfo"),
            translate("product.codInfo"),
        ],
        **_review_ctx(request, product, reviews),
    }
    return render(request, "storefront/product_detail.html", ctx)


@require_POST
def review_create(request, product_id):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)
    from catalog.models import Product
    from orders.models import OrderItem
    from reviews.models import Review

    product = Product.objects.filter(id=product_id, is_active=True).first()
    if not product:
        return HttpResponse(status=404)

    try:
        rating = int(request.POST.get("rating", 5))
    except (TypeError, ValueError):
        rating = 5
    rating = max(1, min(5, rating))
    body = (request.POST.get("body") or "").strip()

    ctx_extra = {}
    if Review.objects.filter(user=request.user, product=product).exists():
        ctx_extra["form_error"] = translate("auth.genericError")
    else:
        order_item = (
            OrderItem.objects.filter(order__user=request.user, order__status="delivered", product=product)
            .order_by("-order__created_at")
            .first()
        )
        Review.objects.create(user=request.user, product=product, rating=rating, body=body, order_item=order_item)

    ctx = _review_ctx(request, product)
    ctx.update(ctx_extra)
    return render(request, "storefront/partials/_reviews.html", ctx)


CHECKOUT_STEPS = ["address", "shipping", "payment", "review"]


def _order_total(order, cart_totals):
    shipping = order.shipping_method.cost if order.shipping_method_id else 0
    return cart_totals["subtotal"] + shipping - cart_totals["discount"]


def _checkout_ctx(request, order, step, *, error=None):
    from accounts.models import Address

    cart = services.existing_cart(request)
    totals = services.cart_totals(cart)
    return {
        "order": order,
        "step": step,
        "is_htmx": bool(request.headers.get("HX-Request")),
        "step_index": CHECKOUT_STEPS.index(step),
        "steps": CHECKOUT_STEPS,
        "step_labels": {
            "address": translate("checkout.stepAddress"),
            "shipping": translate("checkout.stepShipping"),
            "payment": translate("checkout.stepPayment"),
            "review": translate("checkout.stepReview"),
        },
        "error": error,
        "addresses": list(Address.objects.filter(user=request.user)),
        "shipping_methods": services.shipping_methods(),
        "items": list(cart.items.all()) if cart else [],
        "totals": totals,
        "shipping_cost": order.shipping_method.cost if order and order.shipping_method_id else None,
        "grand_total": _order_total(order, totals) if order else totals["total"],
    }


@_login_required
def checkout(request):
    cart = services.existing_cart(request)
    if not cart or not cart.items.exists():
        return render(request, "storefront/checkout.html", {"empty": True})

    order, err = services.create_draft_order(request)
    if err:
        return render(request, "storefront/checkout.html", {"empty": True})
    request.session["checkout_order_id"] = order.id
    return render(request, "storefront/checkout.html", _checkout_ctx(request, order, "address"))


@require_POST
@_login_required
def checkout_step(request):
    from accounts.models import Address
    from shipping.models import ShippingMethod

    order = services.get_draft_order(request)
    if not order:
        resp = HttpResponse(status=409)
        resp["HX-Redirect"] = f"/{request.LANGUAGE_CODE}/cart/"
        return resp

    to = request.POST.get("to", "address")
    if to not in CHECKOUT_STEPS:
        to = "address"
    error = None

    # Apply the patch for the step we're leaving.
    if "address_id" in request.POST:
        addr = Address.objects.filter(id=_int(request.POST["address_id"]), user=request.user).first()
        if not addr:
            error = translate("checkout.genericError")
        else:
            order.shipping_address = addr
    if "shipping_method_id" in request.POST:
        m = ShippingMethod.objects.filter(id=_int(request.POST["shipping_method_id"]), is_active=True).first()
        if not m:
            error = translate("checkout.genericError")
        else:
            order.shipping_method = m
    if request.POST.get("payment_method") in ("cod", "card"):
        order.payment_method = request.POST["payment_method"]

    if error:
        # stay on the current step
        current = request.POST.get("from", "address")
        return render(request, "storefront/partials/_checkout_panel.html",
                      _checkout_ctx(request, order, current if current in CHECKOUT_STEPS else "address", error=error))

    order.save()
    order.recalculate_totals()
    return render(request, "storefront/partials/_checkout_panel.html", _checkout_ctx(request, order, to))


@require_POST
@_login_required
def checkout_add_address(request):
    from accounts.models import Address

    order = services.get_draft_order(request)
    name = (request.POST.get("name") or "").strip()
    phone = (request.POST.get("phone") or "").strip()
    line = (request.POST.get("address_line") or "").strip()
    city = (request.POST.get("city") or "Amman").strip()
    if name and phone and line:
        addr = Address.objects.create(user=request.user, name=name, phone=phone,
                                      city=city, address_line=line,
                                      is_default=not Address.objects.filter(user=request.user).exists())
        if order:
            order.shipping_address = addr
            order.save(update_fields=["shipping_address"])
    ctx = _checkout_ctx(request, order, "address")
    return render(request, "storefront/partials/_checkout_panel.html", ctx)


@require_POST
@_login_required
def checkout_confirm(request):
    from django.db import transaction

    from notify.dispatch import enqueue
    from notify.tasks import send_order_confirmation_email
    from payments.services import process_payment
    from promotions.models import Coupon
    from django.db.models import F

    order = services.get_draft_order(request)
    lang = request.LANGUAGE_CODE
    if not order:
        resp = HttpResponse(status=409)
        resp["HX-Redirect"] = f"/{lang}/cart/"
        return resp

    if not order.shipping_address_id:
        return render(request, "storefront/partials/_checkout_panel.html",
                      _checkout_ctx(request, order, "review", error=translate("checkout.genericError")))

    try:
        with transaction.atomic():
            for item in order.items.select_related("product"):
                if item.product.stock < item.quantity:
                    raise ValueError(translate("checkout.genericError"))
                item.product.stock -= item.quantity
                item.product.save(update_fields=["stock"])
            order.transition_to("pending")
            payment = process_payment(order)
            if order.payment_method == "card" and payment.status == "failed":
                transaction.set_rollback(True)
                raise ValueError(translate("checkout.paymentError"))
            if order.coupon_code:
                Coupon.objects.filter(code__iexact=order.coupon_code).update(times_used=F("times_used") + 1)
            cart = services.get_cart(request)
            cart.items.all().delete()
            cart.coupon_code = ""
            cart.save(update_fields=["coupon_code"])
    except ValueError as exc:
        return render(request, "storefront/partials/_checkout_panel.html",
                      _checkout_ctx(request, order, "review", error=str(exc)))

    enqueue(send_order_confirmation_email, order.id)
    request.session.pop("checkout_order_id", None)
    resp = HttpResponse(status=204)
    resp["HX-Redirect"] = f"/{lang}/account/orders/?placed={order.id}"
    return resp


def _orders_qs(request):
    from orders.models import Order

    return (
        Order.objects.filter(user=request.user)
        .exclude(status="draft")
        .prefetch_related("items")
        .order_by("-created_at")
    )


@_login_required
def account(request):
    orders = list(_orders_qs(request)[:3])
    return render(request, "storefront/account/dashboard.html",
                  {"section": "dashboard", "recent_orders": orders})


@_login_required
def account_profile(request):
    saved = False
    if request.method == "POST":
        u = request.user
        u.first_name = (request.POST.get("first_name") or "").strip()
        u.last_name = (request.POST.get("last_name") or "").strip()
        u.phone = (request.POST.get("phone") or "").strip()
        u.save(update_fields=["first_name", "last_name", "phone", "updated_at"])
        saved = True
    return render(request, "storefront/account/profile.html", {"section": "profile", "saved": saved})


@_login_required
def account_addresses(request):
    from accounts.models import Address

    return render(request, "storefront/account/addresses.html", {
        "section": "addresses",
        "addresses": list(Address.objects.filter(user=request.user)),
    })


@require_POST
@_login_required
def account_address_create(request):
    from accounts.models import Address

    fields = {k: (request.POST.get(k) or "").strip()
              for k in ("name", "phone", "city", "area", "address_line", "building", "apartment")}
    if fields["name"] and fields["phone"] and fields["city"] and fields["address_line"]:
        Address.objects.create(
            user=request.user,
            is_default=not Address.objects.filter(user=request.user).exists(),
            **fields,
        )
    return render(request, "storefront/account/_address_list.html",
                  {"addresses": list(Address.objects.filter(user=request.user))})


@require_POST
@_login_required
def account_address_delete(request, address_id):
    from accounts.models import Address

    Address.objects.filter(user=request.user, id=address_id).delete()
    return render(request, "storefront/account/_address_list.html",
                  {"addresses": list(Address.objects.filter(user=request.user))})


@_login_required
def account_orders(request):
    return render(request, "storefront/account/orders.html",
                  {"section": "orders", "orders": list(_orders_qs(request)),
                   "just_placed": _int(request.GET.get("placed"))})


ORDER_STATUS_FLOW = ["pending", "confirmed", "processing", "shipped", "delivered"]


@_login_required
def account_order_detail(request, order_id):
    from orders.models import Order

    order = (
        Order.objects.filter(user=request.user, id=order_id)
        .exclude(status="draft")
        .prefetch_related("items")
        .select_related("shipping_address", "shipping_method")
        .first()
    )
    if not order:
        raise Http404
    idx = ORDER_STATUS_FLOW.index(order.status) if order.status in ORDER_STATUS_FLOW else -1
    return render(request, "storefront/account/order_detail.html", {
        "section": "orders", "order": order,
        "status_flow": ORDER_STATUS_FLOW, "status_index": idx,
    })


@_login_required
def account_wishlist(request):
    from wishlist.models import WishlistItem

    ids = list(WishlistItem.objects.filter(user=request.user).values_list("product_id", flat=True))
    products = services.decorate_products(request, list(services.products_base().filter(id__in=ids)))
    return render(request, "storefront/account/wishlist.html",
                  {"section": "wishlist", "products": products})


def _safe_next(request):
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else f"/{request.LANGUAGE_CODE}/account/"


def login_view(request):
    from django.contrib.auth import authenticate, get_user_model, login

    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    error = None
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        User = get_user_model()
        username = email
        row = User.objects.filter(email__iexact=email).first()
        if row:
            username = row.username
        user = authenticate(request, username=username, password=password)
        if user is None:
            error = translate("auth.invalidCredentials")
        else:
            request._pre_login_session_key = request.session.session_key
            login(request, user)
            services.merge_guest_cart(request, user)
            return redirect(_safe_next(request))
    return render(request, "storefront/auth/login.html", {"error": error, "next": request.GET.get("next", "")})


def register_view(request):
    from django.contrib.auth import get_user_model, login
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    errors = {}
    data = {}
    if request.method == "POST":
        data = {
            "email": (request.POST.get("email") or "").strip(),
            "first_name": (request.POST.get("first_name") or "").strip(),
            "phone": (request.POST.get("phone") or "").strip(),
        }
        password = request.POST.get("password") or ""
        User = get_user_model()
        if not data["email"] or "@" not in data["email"]:
            errors["email"] = translate("auth.emailRequired")
        elif User.objects.filter(email__iexact=data["email"]).exists():
            errors["email"] = translate("auth.registrationFailed")
        if not data["first_name"]:
            errors["first_name"] = translate("auth.firstNameRequired")
        try:
            validate_password(password)
        except ValidationError:
            errors["password"] = translate("auth.passwordMin")
        if not errors:
            user = User(username=data["email"], email=data["email"],
                        first_name=data["first_name"], phone=data["phone"],
                        preferred_language=request.LANGUAGE_CODE)
            user.set_password(password)
            user.save()
            request._pre_login_session_key = request.session.session_key
            login(request, user)
            services.merge_guest_cart(request, user)
            return redirect(_safe_next(request))
    return render(request, "storefront/auth/register.html",
                  {"errors": errors, "data": data, "next": request.GET.get("next", "")})


def logout_view(request):
    from django.contrib.auth import logout

    logout(request)
    return redirect(f"/{request.LANGUAGE_CODE}/")


def forgot_password(request):
    import logging

    from django.contrib.auth import get_user_model
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    from notify.tasks import send_password_reset_email

    log = logging.getLogger("storefront.auth")
    sent = False
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        lang = request.LANGUAGE_CODE
        # Mirror Django's own PasswordResetForm: only active accounts with a
        # usable password and a real email address get a link.
        user = (get_user_model().objects
                .filter(email__iexact=email, is_active=True)
                .first())
        if user and user.email and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = request.build_absolute_uri(
                f"/{lang}/reset-password/?uid={uid}&token={token}"
            )
            try:
                # Sent synchronously (not .delay) so delivery doesn't depend on a
                # running Celery worker — password reset is do-or-die. The task
                # raises on SMTP failure; we log it and still show the neutral
                # response so the form can't be used to probe for accounts.
                send_password_reset_email(user.id, reset_url, lang)
            except Exception:
                log.exception("Password-reset email failed to send for user id=%s", user.id)
        sent = True  # always, to avoid account enumeration
    return render(request, "storefront/auth/forgot_password.html", {"sent": sent})


def reset_password(request):
    from django.contrib.auth import get_user_model, login
    from django.contrib.auth.password_validation import validate_password
    from django.contrib.auth.tokens import default_token_generator
    from django.core.exceptions import ValidationError
    from django.utils.encoding import force_str
    from django.utils.http import urlsafe_base64_decode

    uid = request.POST.get("uid") or request.GET.get("uid") or ""
    token = request.POST.get("token") or request.GET.get("token") or ""
    user = None
    try:
        user = get_user_model().objects.filter(pk=force_str(urlsafe_base64_decode(uid))).first()
    except Exception:
        user = None
    valid = bool(user and user.is_active and default_token_generator.check_token(user, token))

    error = None
    if request.method == "POST" and valid:
        password = request.POST.get("password") or ""
        try:
            validate_password(password, user)
            user.set_password(password)
            user.save()
            login(request, user)
            return redirect(f"/{request.LANGUAGE_CODE}/account/")
        except ValidationError:
            error = translate("auth.passwordMin")
    return render(request, "storefront/auth/reset_password.html",
                  {"valid": valid, "uid": uid, "token": token, "error": error})


# Skin Quiz — ports frontend/src/pages/SkinQuiz.tsx. Every question offers the same
# four archetype answers in the same order; the option key alone points at a skin type.
QUIZ_QUESTION_KEYS = ("q1", "q2", "q3", "q4")
QUIZ_OPTION_KEYS = ("tight", "shiny", "tzone", "balanced")
QUIZ_BUCKET_BY_OPTION = {
    "tight": "dry-skin",
    "shiny": "oily-skin",
    "tzone": "combination-skin",
    "balanced": "uneven-skin",
}
# Tie-break priority — the balanced/combination reads win a dead heat (matches PRIORITY in the .tsx).
QUIZ_PRIORITY = ("combination-skin", "uneven-skin", "oily-skin", "dry-skin")


def skin_quiz(request):
    lang = request.LANGUAGE_CODE
    is_ar = lang == "ar"
    result_slug = request.GET.get("result")

    if result_slug:
        # Guard against a hand-typed slug: fall back to the tie-break winner.
        if result_slug not in QUIZ_BUCKET_BY_OPTION.values():
            result_slug = QUIZ_PRIORITY[0]
        skin_type = services.get_skin_type(result_slug)
        picks = []
        if skin_type:
            qs, _ = services.filtered_products(
                {"ordering": "-created_at"}, landing="skin-type", landing_slug=result_slug
            )
            picks = services.decorate_products(request, list(qs[:4]))
        type_label = translate(f"skinQuiz.types.{result_slug}", lang)
        return render(request, "storefront/partials/_skin_quiz_result.html", {
            "result_slug": result_slug,
            "skin_type": skin_type,
            "type_label": type_label,
            "picks": picks,
        })

    questions = [
        {
            "key": qk,
            "title_key": f"skinQuiz.q.{qk}.title",
            "options": [{"key": ok, "label_key": f"skinQuiz.q.{qk}.{ok}"} for ok in QUIZ_OPTION_KEYS],
        }
        for qk in QUIZ_QUESTION_KEYS
    ]
    crumbs = [
        {"name": "الرئيسية" if is_ar else "Home", "url": f"/{lang}/"},
        {"name": translate("skinQuiz.eyebrow", lang)},
    ]
    return render(request, "storefront/skin_quiz.html", {
        "questions": questions,
        "crumbs": crumbs,
        "quiz_config": {
            "total": len(questions),
            "bucketByOption": QUIZ_BUCKET_BY_OPTION,
            "priority": list(QUIZ_PRIORITY),
            "resultUrl": request.path,
            "progressTemplate": translate("skinQuiz.progress", lang),
        },
    })


def policy(request, slug):
    row = services.get_policy(slug)
    if not row:
        raise Http404
    is_ar = request.LANGUAGE_CODE == "ar"
    title = (row.title_ar if is_ar else row.title_en) or row.title_en
    body = ((row.body_ar if is_ar else row.body_en) or "").strip()
    return render(request, "storefront/policy.html", {
        "title": title,
        "body": body,
        "updated": row.updated_at,
        "crumbs": [
            {"name": "الرئيسية" if is_ar else "Home", "url": f"/{request.LANGUAGE_CODE}/"},
            {"name": title},
        ],
    })
