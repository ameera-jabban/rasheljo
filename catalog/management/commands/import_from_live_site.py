"""Import the real product catalog from the live site https://dr-rasheljo.com/.

Three strategies are tried in order, each falling back to the next if it yields
no usable products:

    1. WooCommerce Store API   /wp-json/wc/store/v1/products      (richest, no auth)
    2. WordPress REST API      /wp-json/wp/v2/product             (no prices/brand meta)
    3. Sitemap + HTML scrape   /post-type-product-sitemap-N.xml   (last resort)

Usage:
    python manage.py import_from_live_site --dry-run --limit 5
    python manage.py import_from_live_site
    python manage.py import_from_live_site --strategy store_api --skip-images
"""

from __future__ import annotations

import re
import time
from decimal import Decimal, InvalidOperation
from html import unescape
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Brand, Category, Product, ProductAttribute, ProductImage

LIVE_ROOT = "https://dr-rasheljo.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 drrasheljo-catalog-import/1.0"
)

# Known brands on the live store, keyed by the WooCommerce brand slug, with the
# SKU prefixes that also identify them when the brand taxonomy is missing.
BRAND_MAP = {
    "dr-rashel": {"name_en": "DR.RASHEL", "name_ar": "دكتور راشيل", "sku_prefixes": ("DRL",)},
    "estelin": {"name_en": "ESTELIN", "name_ar": "استيلين", "sku_prefixes": ("ES", "EST")},
}
# Fallback: match the brand name the API returns ("Dr Rashel", "Estelin").
BRAND_NAME_TO_SLUG = {"dr rashel": "dr-rashel", "estelin": "estelin"}

# Category slugs that really describe a merchandising bucket / badge, not a
# product line — used to pick a "real" category and to derive the badge.
BADGE_CATEGORY_SLUGS = {
    "best-sellers": "bestseller",
    "bestsellers": "bestseller",
    "hot-offers": "hot_offer",
    "hot-offer": "hot_offer",
    "last-chance": "last_chance",
    "packages": "set",
    "gifts": "set",
    "va-set": "set",
    "new-arrivals": "new_arrival",
}

# Map the live site's skin-type product tags onto the ProductAttribute slugs the
# storefront's Shop filter already uses (see frontend Shop.tsx SKIN_TYPES and
# seed_demo.py) — value on the left is the live tag slug, tuple is (slug, label).
SKIN_TYPE_TAGS = {
    "oily-skin": ("oily-skin", "Oily Skin"),
    "dry-skin": ("dry-skin", "Dry Skin"),
    "combination-skin": ("combination-skin", "Combination Skin"),
    "normal-skin": ("uneven-skin", "Normal Skin"),
    "all-type": ("sensitive-skin", "All Types"),
    "all-types": ("sensitive-skin", "All Types"),
    "all-skin-types": ("sensitive-skin", "All Types"),
}

# SKU looks like "DRL-1750" / "ES-0182", sometimes glued to the name
# ("(3 PCS)DRL-1750"), spaced ("DRL- 1623"), or mis-cased ("DRl-1770").
SKU_RE = re.compile(r"\bB?(DRL|EST|ES)\s*[-–—]?\s*(\d{3,5})\b", re.IGNORECASE)
PACK_SIZE_RE = re.compile(r"\(\s*(\d+\s*(?:PCS|PC|PIECE[S]?|SET)[^)]*)\)", re.IGNORECASE)


class Command(BaseCommand):
    help = "Import the real product catalog from the live site dr-rasheljo.com."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Parse and report only; write nothing to the database.")
        parser.add_argument("--limit", type=int, default=None,
                            help="Stop after importing this many products (per strategy).")
        parser.add_argument("--strategy", choices=["store_api", "wp_api", "scrape"], default=None,
                            help="Force one strategy instead of trying all three in order.")
        parser.add_argument("--skip-images", action="store_true",
                            help="Do not download product images.")
        parser.add_argument("--refresh-images", action="store_true",
                            help="Re-download images even for products that already have some.")
        parser.add_argument("--brand", default=None,
                            help="Only import products for this brand slug (dr-rashel / estelin).")
        parser.add_argument("--timeout", type=int, default=30, help="Per-request timeout, seconds.")

    # ------------------------------------------------------------------ setup --
    def handle(self, *args, **opt):
        self.dry_run = opt["dry_run"]
        self.limit = opt["limit"]
        self.skip_images = opt["skip_images"]
        self.refresh_images = opt["refresh_images"]
        self.brand_filter = opt["brand"]
        self.timeout = opt["timeout"]
        self.verbosity = opt["verbosity"]

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, */*"})

        self.skipped: list[tuple[str, str]] = []   # (identifier, reason)
        self.review: list[tuple[str, str]] = []     # (sku/name, note)
        self.created = 0
        self.updated = 0
        self.images_attached = 0

        strategies = {
            "store_api": self.strategy_store_api,
            "wp_api": self.strategy_wp_api,
            "scrape": self.strategy_scrape,
        }
        order = [opt["strategy"]] if opt["strategy"] else ["store_api", "wp_api", "scrape"]

        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no database changes will be made.\n"))

        products = []
        used = None
        for name in order:
            self.stdout.write(f"-> Trying strategy: {name} ...")
            try:
                products = strategies[name]()
            except Exception as exc:  # noqa: BLE001 - report and fall through
                self.stdout.write(self.style.ERROR(f"  strategy {name} raised: {exc!r}"))
                products = []
            if products:
                used = name
                self.stdout.write(self.style.SUCCESS(
                    f"  strategy {name} returned {len(products)} raw products."))
                break
            self.stdout.write(self.style.WARNING(f"  strategy {name} yielded nothing; falling back."))

        if not products:
            raise CommandError("All three import strategies failed to return any products.")

        if self.brand_filter:
            products = [p for p in products if p.get("brand_slug") == self.brand_filter]
        if self.limit:
            products = products[: self.limit]

        self._ensure_brands()
        for raw in products:
            self._import_one(raw)

        self._report(used)

    # ------------------------------------------------------- strategy: Store --
    def strategy_store_api(self) -> list[dict]:
        base = urljoin(LIVE_ROOT, "wp-json/wc/store/v1/products")
        out, page, per_page = [], 1, 100
        while True:
            data = self._get_json(base, params={"per_page": per_page, "page": page})
            if not isinstance(data, list) or not data:
                break
            for item in data:
                parsed = self._parse_store_item(item)
                if parsed:
                    out.append(parsed)
            if len(data) < per_page:
                break
            page += 1
            time.sleep(0.3)
        return out

    def _parse_store_item(self, item: dict) -> dict | None:
        raw_name = unescape(item.get("name") or "").strip()
        if not raw_name:
            return None

        prices = item.get("prices") or {}
        try:
            minor = int(prices.get("currency_minor_unit", 2))
        except (TypeError, ValueError):
            minor = 2
        divisor = Decimal(10) ** minor

        def money(key):
            val = prices.get(key)
            if val in (None, ""):
                return None
            try:
                return (Decimal(str(val)) / divisor).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError):
                return None

        regular = money("regular_price") or money("price")
        sale = money("sale_price")
        on_sale = bool(item.get("on_sale")) and sale is not None and regular is not None and sale < regular

        brands = item.get("brands") or []
        brand_slug = None
        if brands:
            brand_slug = brands[0].get("slug") or BRAND_NAME_TO_SLUG.get(
                (brands[0].get("name") or "").strip().lower())

        categories = [
            {"name": unescape(c.get("name", "")).strip(), "slug": c.get("slug", "")}
            for c in (item.get("categories") or [])
        ]
        tags = [t.get("slug", "") for t in (item.get("tags") or [])]

        images, seen_src = [], set()
        for img in item.get("images") or []:
            src = img.get("src")
            if src and src not in seen_src:
                seen_src.add(src)
                images.append({"src": src, "alt": unescape(img.get("alt") or "").strip()})

        desc_en, benefits_en, benefits_ar = self._parse_description(
            item.get("short_description") or item.get("description") or "")

        return {
            "source_id": item.get("id"),
            "raw_name": raw_name,
            "api_sku": (item.get("sku") or "").strip(),
            "api_slug": item.get("slug") or "",
            "brand_slug": brand_slug,
            "price": regular,
            "sale_price": sale if on_sale else None,
            "in_stock": bool(item.get("is_in_stock", True)),
            "categories": categories,
            "tags": tags,
            "images": images,
            "description_en": desc_en,
            "benefits_en": benefits_en,
            "benefits_ar": benefits_ar,
        }

    # --------------------------------------------------------- strategy: WP ---
    def strategy_wp_api(self) -> list[dict]:
        base = urljoin(LIVE_ROOT, "wp-json/wp/v2/product")
        out, page = [], 1
        while True:
            data = self._get_json(base, params={"per_page": 100, "page": page, "_embed": 1})
            if not isinstance(data, list) or not data:
                break
            for item in data:
                raw_name = unescape((item.get("title") or {}).get("rendered", "")).strip()
                if not raw_name:
                    continue
                content = (item.get("content") or {}).get("rendered", "")
                desc_en, ben_en, ben_ar = self._parse_description(content)
                img_src = None
                try:
                    media = item["_embedded"]["wp:featuredmedia"][0]
                    img_src = media.get("source_url")
                except (KeyError, IndexError, TypeError):
                    pass
                out.append({
                    "source_id": item.get("id"),
                    "raw_name": raw_name,
                    "api_sku": "",
                    "api_slug": item.get("slug") or "",
                    "brand_slug": None,           # not exposed by the core WP route
                    "price": None,                # not exposed; needs manual review
                    "sale_price": None,
                    "in_stock": True,
                    "categories": [],
                    "tags": [],
                    "images": [{"src": img_src, "alt": ""}] if img_src else [],
                    "description_en": desc_en,
                    "benefits_en": ben_en,
                    "benefits_ar": ben_ar,
                })
            if len(data) < 100:
                break
            page += 1
            time.sleep(0.3)
        return out

    # ----------------------------------------------------- strategy: scrape ---
    def strategy_scrape(self) -> list[dict]:
        urls = self._collect_scrape_urls()
        if not urls:
            return []
        out = []
        for i, url in enumerate(urls, 1):
            try:
                parsed = self._scrape_product_page(url)
            except Exception as exc:  # noqa: BLE001
                self._vlog(f"  scrape failed for {url}: {exc!r}")
                parsed = None
            if parsed:
                out.append(parsed)
            if self.limit and len(out) >= self.limit:
                break
            if i % 20 == 0:
                self._vlog(f"  scraped {i}/{len(urls)} pages")
            time.sleep(0.2)
        return out

    def _collect_scrape_urls(self) -> list[str]:
        index = self._get_text(urljoin(LIVE_ROOT, "sitemap_index.xml"))
        maps = re.findall(r"<loc>\s*([^<]+product-sitemap[^<]*)\s*</loc>", index or "")
        if not maps:
            maps = re.findall(r"<loc>\s*([^<]*product[^<]*\.xml)\s*</loc>", index or "")
        urls: list[str] = []
        for m in maps:
            body = self._get_text(m.strip())
            urls += [u.strip() for u in re.findall(r"<loc>\s*([^<]+/product/[^<]+)\s*</loc>", body or "")]
        return list(dict.fromkeys(urls))

    def _scrape_product_page(self, url: str) -> dict | None:
        html = self._get_text(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        def meta(prop):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            return unescape(tag["content"].strip()) if tag and tag.get("content") else None

        raw_name = meta("og:title") or (soup.title.string if soup.title else "")
        raw_name = re.sub(r"\s*[-|]\s*Dr Rashel\s*$", "", unescape(raw_name or "")).strip()
        if not raw_name:
            return None

        price = sale = None
        price_wrap = soup.select_one("p.price, span.price, .vamtam-product-price, .woolentor-product-price")
        if price_wrap:
            nums = re.findall(r"(\d+(?:[.,]\d{1,2})?)", price_wrap.get_text(" ", strip=True))
            vals = []
            for n in nums:
                try:
                    vals.append(Decimal(n.replace(",", ".")))
                except InvalidOperation:
                    pass
            if len(vals) >= 2:
                sale, price = min(vals), max(vals)
            elif vals:
                price = vals[0]

        img = meta("og:image")
        desc_en, ben_en, ben_ar = self._parse_description(
            str(soup.select_one(".woocommerce-product-details__short-description") or ""))

        return {
            "source_id": None,
            "raw_name": raw_name,
            "api_sku": "",
            "api_slug": urlparse(url).path.rstrip("/").rsplit("/", 1)[-1],
            "brand_slug": None,
            "price": price,
            "sale_price": sale,
            "in_stock": "out of stock" not in html.lower(),
            "categories": [],
            "tags": [],
            "images": [{"src": img, "alt": ""}] if img else [],
            "description_en": desc_en,
            "benefits_en": ben_en,
            "benefits_ar": ben_ar,
        }

    # -------------------------------------------------------------- import ----
    def _import_one(self, raw: dict):
        name_no_sku, sku = self._split_name_and_sku(raw["raw_name"], raw["api_sku"], raw["api_slug"])
        brand_slug = raw.get("brand_slug") or self._brand_from_sku(sku)

        ident = sku or raw["raw_name"][:60]

        if not brand_slug:
            self.skipped.append((ident, "brand prefix not recognized"))
            return
        if brand_slug not in BRAND_MAP:
            self.skipped.append((ident, f"unknown brand slug {brand_slug!r}"))
            return
        if raw["price"] is None:
            self.skipped.append((ident, "no price found (strategy did not expose one)"))
            return
        if not sku:
            sku = f"LIVE-{raw['source_id'] or slugify(raw['api_slug'])[:20]}"
            self.review.append((f"{sku} — {name_no_sku}", "SKU could not be parsed; synthesised from source id"))

        brand = self.brands[brand_slug]
        category = self._resolve_category(raw["categories"])
        badge = self._resolve_badge(raw["categories"], name_no_sku)
        pack = self._resolve_pack_size(raw["raw_name"])
        slug = self._unique_slug(raw["api_slug"] or slugify(name_no_sku), sku)

        if self.dry_run:
            self._vlog(
                f"  [{brand.name_en}] {sku}  {name_no_sku[:70]!r}  "
                f"price={raw['price']} sale={raw['sale_price']} "
                f"cat={category.name_en if category else '-'} badge={badge or '-'} "
                f"imgs={len(raw['images'])}")
            # Count as created/updated for the summary without touching the DB.
            if Product.objects.filter(sku=sku).exists():
                self.updated += 1
            else:
                self.created += 1
            if raw["images"]:
                self.images_attached += 1
            return

        with transaction.atomic():
            defaults = {
                "name_en": name_no_sku,
                "slug": slug,
                "brand": brand,
                "category": category,
                "price": raw["price"],
                "sale_price": raw["sale_price"],
                "stock": 100 if raw["in_stock"] else 0,
                "pack_size": pack,
                "badge_type": badge or "",
                "description_en": raw["description_en"],
                "benefits_en": raw["benefits_en"],
                "benefits_ar": raw["benefits_ar"],
                "is_active": True,
            }
            product, created = Product.objects.update_or_create(sku=sku, defaults=defaults)
            self.created += int(created)
            self.updated += int(not created)

            self._sync_skin_types(product, raw["tags"])

            if not self.skip_images:
                had = product.images.exists()
                if not had or self.refresh_images:
                    if self.refresh_images:
                        product.images.all().delete()
                    n = self._download_images(product, raw["images"])
                    if n:
                        self.images_attached += 1
                elif had:
                    self.images_attached += 1

    # --------------------------------------------------------- name / sku ----
    @staticmethod
    def _split_name_and_sku(raw_name: str, api_sku: str, api_slug: str) -> tuple[str, str]:
        sku = ""
        if api_sku:
            sku = api_sku.upper().replace(" ", "-")
        m = SKU_RE.search(raw_name)
        if m:
            if not sku:
                sku = f"{m.group(1).upper()}-{m.group(2)}"
            # strip the SKU token (and any trailing separators) off the display name
            name = (raw_name[: m.start()] + raw_name[m.end():]).strip()
        else:
            name = raw_name
        if not sku:
            ms = SKU_RE.search(api_slug.upper().replace("_", "-"))
            if ms:
                sku = f"{ms.group(1).upper()}-{ms.group(2)}"
        name = re.sub(r"\s{2,}", " ", name).strip(" -–—")
        return name, sku

    @staticmethod
    def _brand_from_sku(sku: str) -> str | None:
        if not sku:
            return None
        prefix = sku.split("-")[0].upper()
        for slug, meta in BRAND_MAP.items():
            if prefix in meta["sku_prefixes"]:
                return slug
        return None

    def _unique_slug(self, base: str, sku: str) -> str:
        base = (slugify(base) or slugify(sku))[:210]
        slug = base
        i = 2
        qs = Product.objects.exclude(sku=sku)
        while qs.filter(slug=slug).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug

    # ------------------------------------------------------- taxonomy work ----
    def _ensure_brands(self):
        self.brands = {}
        for slug, meta in BRAND_MAP.items():
            if self.dry_run:
                self.brands[slug] = Brand.objects.filter(slug=slug).first() or Brand(
                    slug=slug, name_en=meta["name_en"], name_ar=meta["name_ar"])
            else:
                self.brands[slug], _ = Brand.objects.get_or_create(
                    slug=slug, defaults={"name_en": meta["name_en"], "name_ar": meta["name_ar"]})

    def _resolve_category(self, categories: list[dict]):
        real = [c for c in categories if c["slug"] and c["slug"] not in BADGE_CATEGORY_SLUGS]
        chosen = (real or categories or [None])[0]
        if not chosen or not chosen.get("slug"):
            return None
        if self.dry_run:
            return Category.objects.filter(slug=chosen["slug"]).first() or Category(
                slug=chosen["slug"], name_en=chosen["name"] or chosen["slug"])
        obj, _ = Category.objects.get_or_create(
            slug=chosen["slug"], defaults={"name_en": chosen["name"] or chosen["slug"]})
        return obj

    @staticmethod
    def _resolve_badge(categories: list[dict], name: str) -> str | None:
        for c in categories:
            if c["slug"] in BADGE_CATEGORY_SLUGS:
                return BADGE_CATEGORY_SLUGS[c["slug"]]
        if PACK_SIZE_RE.search(name) or re.search(r"\bset\b", name, re.IGNORECASE):
            return "set"
        return None

    @staticmethod
    def _resolve_pack_size(raw_name: str) -> str:
        m = PACK_SIZE_RE.search(raw_name)
        return m.group(1).strip().upper() if m else ""

    def _sync_skin_types(self, product: Product, tags: list[str]):
        wanted = []
        for tag in tags:
            if tag in SKIN_TYPE_TAGS:
                slug, label = SKIN_TYPE_TAGS[tag]
                attr, _ = ProductAttribute.objects.get_or_create(
                    attribute_type="skin_type", slug=slug,
                    defaults={"value_en": label})
                wanted.append(attr)
        if wanted:
            product.attributes.add(*wanted)

    # ----------------------------------------------------------- images ------
    def _download_images(self, product: Product, images: list[dict]) -> int:
        attached = 0
        for order, img in enumerate(images):
            src = img.get("src")
            if not src:
                continue
            try:
                resp = self.session.get(src, timeout=self.timeout)
                resp.raise_for_status()
                content = resp.content
                if not content or len(content) < 100:
                    raise ValueError("empty/too-small image response")
            except Exception as exc:  # noqa: BLE001
                self._vlog(f"    image download failed ({src}): {exc!r}")
                continue
            name = urlparse(src).path.rsplit("/", 1)[-1] or f"{product.sku}-{order}.jpg"
            pi = ProductImage(product=product, sort_order=order,
                              alt_text_en=img.get("alt") or product.name_en)
            pi.image.save(f"{product.sku}-{order}-{name}", ContentFile(content), save=True)
            attached += 1
        return attached

    # --------------------------------------------------------- description ---
    @staticmethod
    def _parse_description(html: str) -> tuple[str, str, str]:
        """Return (description_en, benefits_en, benefits_ar) from a WooCommerce
        short-description blob that follows the live site's
        'Benefits (EN):' / 'الفوائد (AR):' heading + <ul> convention."""
        if not html:
            return "", "", ""
        soup = BeautifulSoup(unescape(html), "html.parser")

        def list_after(*needles) -> str:
            for hd in soup.find_all(["h1", "h2", "h3", "h4", "strong", "p", "b"]):
                text = hd.get_text(" ", strip=True).lower()
                if any(n in text for n in needles):
                    ul = hd.find_next(["ul", "ol"])
                    if ul:
                        items = [li.get_text(" ", strip=True) for li in ul.find_all("li")]
                        return "\n".join(i for i in items if i)
            return ""

        benefits_en = list_after("benefits (en)", "key benefits", "benefits:")
        benefits_ar = list_after("الفوائد", "الفوائد (ar)", "فوائد")

        # Description = the first paragraph(s) before any "benefits" heading.
        desc_parts = []
        for p in soup.find_all("p"):
            t = p.get_text(" ", strip=True)
            if not t or t == "\xa0":
                continue
            low = t.lower()
            if "benefit" in low or "الفوائد" in low:
                break
            desc_parts.append(t)
        description = " ".join(desc_parts).strip()
        if not description:
            description = soup.get_text(" ", strip=True)[:800]
        return description, benefits_en, benefits_ar

    # -------------------------------------------------------------- http -----
    def _get_json(self, url: str, params: dict | None = None):
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 400 and params and params.get("page", 1) > 1:
                    return []  # WP returns 400 for pages past the last one
                resp.raise_for_status()
                return resp.json()
            except (requests.RequestException, ValueError) as exc:
                self._vlog(f"    GET {url} params={params} failed ({attempt + 1}/3): {exc!r}")
                time.sleep(1.5 * (attempt + 1))
        return None

    def _get_text(self, url: str) -> str | None:
        for attempt in range(3):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.text
            except requests.RequestException as exc:
                self._vlog(f"    GET {url} failed ({attempt + 1}/3): {exc!r}")
                time.sleep(1.5 * (attempt + 1))
        return None

    # ------------------------------------------------------------ output ----
    def _vlog(self, msg: str):
        if self.verbosity >= 2:
            self.stdout.write(msg)

    def _report(self, strategy: str | None):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=== Import summary ==="))
        self.stdout.write(f"Strategy used         : {strategy}")
        self.stdout.write(f"Products created      : {self.created}")
        self.stdout.write(f"Products updated       : {self.updated}")
        self.stdout.write(f"Products with image(s): {self.images_attached}")
        self.stdout.write(f"Skipped               : {len(self.skipped)}")
        self.stdout.write(f"Needs manual review   : {len(self.review)}")

        if self.skipped:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Skipped products:"))
            for ident, reason in self.skipped[:40]:
                self.stdout.write(f"  - {ident}  ({reason})")
            if len(self.skipped) > 40:
                self.stdout.write(f"  ... and {len(self.skipped) - 40} more")

        if self.review:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Products needing manual review:"))
            for ident, note in self.review[:40]:
                self.stdout.write(f"  - {ident}  ({note})")

        if not self.dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("=== Database totals ==="))
            self.stdout.write(f"Brands     : {Brand.objects.count()}")
            self.stdout.write(f"Categories : {Category.objects.count()}")
            self.stdout.write(f"Products   : {Product.objects.count()}")
            for b in Brand.objects.all():
                self.stdout.write(f"  {b.name_en:12s}: {b.products.count()}")
            self.stdout.write(f"ProductImages: {ProductImage.objects.count()}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done." + ("  (dry run — nothing written)" if self.dry_run else "")))
