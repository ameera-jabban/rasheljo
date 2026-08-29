from django.core.management.base import BaseCommand

from catalog.models import Brand, Category, Product, ProductAttribute


class Command(BaseCommand):
    """Seeds real (crawl-confirmed) product data from dr-rasheljo.com so the
    API and frontend can be demoed against something real, not lorem ipsum."""

    help = "Seed demo catalog data confirmed from the live site crawl."

    def handle(self, *args, **options):
        dr_rashel, _ = Brand.objects.get_or_create(
            slug="dr-rashel", defaults={"name_en": "DR.RASHEL", "name_ar": "دكتور راشيل"}
        )
        estelin, _ = Brand.objects.get_or_create(
            slug="estelin", defaults={"name_en": "ESTELIN", "name_ar": "استيلين"}
        )

        categories = {}
        for slug, name in [
            ("hyaluronic-acid", "Hyaluronic Series"),
            ("turmeric-series", "Turmeric Series"),
            ("retinol-series", "Retinol Series"),
            ("snail-series", "Snail Series"),
            # Additional categories confirmed present in the live site's tag
            # cloud during the final parity audit crawl — added to close the
            # taxonomy-breadth gap identified there, not fabricated.
            ("vitamin-c", "Vitamin C"),
            ("vitamin-e", "Vitamin E"),
            ("collagen", "Collagen"),
            ("24k-gold", "24K Gold"),
            ("niacinamide", "Niacinamide"),
            ("toner", "Toner"),
            ("cleanser", "Cleanser"),
            ("sunscreen", "Sunscreen"),
            ("lip-balm", "Lip Balm"),
            ("hair-care", "Hair Care"),
            ("body-care", "Body Care"),
            ("baby-care", "Baby Care"),
            ("serum", "Serum"),
            ("scrubs", "Scrubs"),
            ("face-mask", "Face Mask"),
            ("whitening", "Whitening"),
            ("gifts", "Gifts"),
        ]:
            categories[slug], _ = Category.objects.get_or_create(slug=slug, defaults={"name_en": name})

        skin_types = {}
        for slug, name in [
            ("oily-skin", "Oily Skin"),
            ("dry-skin", "Dry Skin"),
            ("sensitive-skin", "All Types"),
            ("uneven-skin", "Normal Skin"),
            ("combination-skin", "Combination Skin"),
        ]:
            skin_types[slug], _ = ProductAttribute.objects.get_or_create(
                attribute_type="skin_type", slug=slug, defaults={"value_en": name}
            )

        products = [
            dict(sku="DRL-1842", name_en="DR.RASHEL Vitamin C Brightening & Anti-Aging Facial Massage Cream",
                 brand=dr_rashel, price="8.80", badge_type="bestseller", category="hyaluronic-acid", stock=120,
                 description_en="A nourishing facial massage cream enriched with Vitamin C to brighten skin, "
                                 "improve elasticity, and support anti-aging care during facial massage routines.",
                 description_ar="كريم مغذي لتدليك الوجه غني بفيتامين C لتفتيح البشرة وتحسين مرونتها ودعم "
                                 "العناية بمكافحة الشيخوخة أثناء جلسات تدليك الوجه.",
                 benefits_en="Brightens and revitalizes dull skin\nImproves skin elasticity\n"
                              "Nourishes deeply\nHelps reduce fine lines appearance\nIdeal for facial massage sessions",
                 benefits_ar="يمنح إشراقة وحيوية للبشرة\nيعزز مرونة الجلد\nيغذي البشرة بعمق\n"
                              "يساعد على تقليل مظهر الخطوط الدقيقة\nمثالي لجلسات مساج الوجه"),
            dict(sku="DRL-1674", name_en="DR.RASHEL Honey & Shea Butter Lip Balm",
                 brand=dr_rashel, price="3.00", badge_type="bestseller", category="turmeric-series", stock=200),
            dict(sku="DRL-1436", name_en="DR.RASHEL White Skin Whitening Day Cream SPF20",
                 brand=dr_rashel, price="8.80", badge_type="bestseller", category="retinol-series", stock=90),
            dict(sku="DRL-1511", name_en="DR.RASHEL Vitamin C Face Cream (with Hyaluronic Acid)",
                 brand=dr_rashel, price="8.50", badge_type="bestseller", category="hyaluronic-acid", stock=75),
            dict(sku="DRL-1787", name_en="DR.RASHEL Baby Liquid Powder",
                 brand=dr_rashel, price="5.80", sale_price="4.35", badge_type="hot_offer",
                 category="snail-series", stock=60),
            dict(sku="DRL-1786", name_en="DR.RASHEL Baby After Bites Natural Soothing Gel",
                 brand=dr_rashel, price="4.80", sale_price="3.60", badge_type="hot_offer",
                 category="snail-series", stock=45),
            dict(sku="DRL-1511B", name_en="DR.RASHEL Vitamin C Brightening Night Cream",
                 brand=dr_rashel, price="8.50", badge_type="last_chance", category="hyaluronic-acid", stock=15,
                 slug="dr-rashel-vitamin-c-brightening-night-cream"),
            dict(sku="DRL-1750", name_en="DR.RASHEL Hyaluronic Acid Skin Care Set (3 PCS)",
                 brand=dr_rashel, price="24.00", badge_type="set", category="hyaluronic-acid",
                 pack_size="3 PCS", stock=30),
            dict(sku="ES-0140", name_en="ESTELIN Vitamin E Coconut Oil – Body Cleansing Set (4 PCS)",
                 brand=estelin, price="36.00", badge_type="set", category="turmeric-series",
                 pack_size="4 PCS", stock=25),
            dict(sku="ES-0245", name_en="ESTELIN Water Bank Hyaluronic Acid Travel Bag Set – 5 PCS",
                 brand=estelin, price="35.80", badge_type="set", category="hyaluronic-acid",
                 pack_size="5 PCS", stock=20),
            dict(sku="ES-0108", name_en="ESTELIN Vitamin E Coconut Oil – Body Oil",
                 brand=estelin, price="8.50", badge_type="last_chance", category="turmeric-series", stock=10),
        ]

        created = 0
        for p in products:
            category = categories[p.pop("category")]
            defaults = {**p, "category": category}
            slug = defaults.pop("slug", None)
            obj, was_created = Product.objects.get_or_create(
                sku=defaults["sku"], defaults={**defaults, **({"slug": slug} if slug else {})}
            )
            if was_created:
                obj.attributes.add(skin_types["combination-skin"])
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {created} products, {Brand.objects.count()} brands, "
            f"{Category.objects.count()} categories, {ProductAttribute.objects.count()} attributes."
        ))
