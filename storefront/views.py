"""Django-templates storefront — server-rendered views.

Parallel to the React app in ./frontend (untouched). These views talk to the
existing models / service functions directly; they never call the project's own
HTTP API.
"""
from __future__ import annotations

from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from storefront import services
from storefront.i18n import translate


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
    if product.stock < qty:
        return _cart_control_response(request, _reload_product(product.id),
                                      message=translate("cart.updateFailed"))
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, variant=None,
                                                   defaults={"quantity": qty})
    if not created:
        item.quantity += qty
        item.save()
    return _cart_control_response(request, _reload_product(product.id),
                                  message=translate("product.addedToCart"), bump=True)


@require_POST
def cart_update(request, item_id):
    from cart.models import CartItem

    cart = services.get_cart(request)
    item = CartItem.objects.filter(cart=cart, id=item_id).select_related("product").first()
    if not item:
        return HttpResponse(status=404)
    qty = int(request.POST.get("quantity", item.quantity))
    if qty < 1:
        item.delete()
        return _cart_control_response(request, _reload_product(item.product_id))
    if item.product.stock < qty:
        return _cart_control_response(request, _reload_product(item.product_id),
                                      message=translate("cart.updateFailed"))
    item.quantity = qty
    item.save()
    return _cart_control_response(request, _reload_product(item.product_id))


@require_POST
def cart_remove(request, item_id):
    from cart.models import CartItem

    cart = services.get_cart(request)
    item = CartItem.objects.filter(cart=cart, id=item_id).first()
    product_id = _int(request.POST.get("product_id"))
    if item:
        product_id = item.product_id
        item.delete()
    product = _reload_product(product_id)
    if not product:
        return HttpResponse(status=204)
    return _cart_control_response(request, product)


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


def shop(request):
    return _placeholder(request, "Shop")


def product_detail(request, slug):
    return _placeholder(request, f"Product · {slug}")


def brand_landing(request, slug):
    return _placeholder(request, f"Brand · {slug}")


def category_landing(request, slug):
    return _placeholder(request, f"Category · {slug}")


def skin_type_landing(request, slug):
    return _placeholder(request, f"Skin type · {slug}")


def search(request):
    return _placeholder(request, "Search")


def cart_page(request):
    return _placeholder(request, "Cart")


def checkout(request):
    return _placeholder(request, "Checkout")


def account(request):
    return _placeholder(request, "Account")


def login_view(request):
    return _placeholder(request, "Login")


def register_view(request):
    return _placeholder(request, "Register")


def skin_quiz(request):
    return _placeholder(request, "Skin Quiz")


def policy(request, slug):
    return _placeholder(request, f"Policy · {slug}")
