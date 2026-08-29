"""Fill in blank Arabic names/descriptions on the catalog taxonomy by machine
translation, flagging each row so a human can review it later.

The live WooCommerce site never had Arabic category / brand / attribute names, so
~60 categories (and a few attributes) import with `name_ar` / `value_ar` empty.
This command translates the English value with `deep-translator`'s GoogleTranslator
(same approach used for product copy), writes it back, and sets
`ar_machine_translated=True`.

    python manage.py translate_missing_arabic --dry-run
    python manage.py translate_missing_arabic
    python manage.py translate_missing_arabic --models category,brand
    python manage.py translate_missing_arabic --include-products

Idempotent: only ever touches rows whose Arabic field is still blank.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError
from django.db import models as dj_models

from catalog.models import Brand, Category, Product, ProductAttribute

# (model, name-field pair, optional description-field pair)
TARGETS = {
    "category": (Category, ("name_en", "name_ar"), ("description_en", "description_ar")),
    "brand": (Brand, ("name_en", "name_ar"), ("description_en", "description_ar")),
    "attribute": (ProductAttribute, ("value_en", "value_ar"), None),
}
PRODUCT_TARGET = (Product, ("name_en", "name_ar"), ("description_en", "description_ar"))


class Command(BaseCommand):
    help = "Machine-translate blank Arabic catalog fields and flag them for review."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="List what would be translated; change nothing.")
        parser.add_argument("--models", default="category,brand,attribute",
                            help="Comma list of: category, brand, attribute (default: all three).")
        parser.add_argument("--include-products", action="store_true",
                            help="Also translate Product.name_ar/description_ar where blank.")
        parser.add_argument("--limit", type=int, default=None,
                            help="Stop after this many rows (across all models).")
        parser.add_argument("--sleep", type=float, default=0.3,
                            help="Delay between translation calls, seconds (default 0.3).")

    def handle(self, *args, **opt):
        self.dry_run = opt["dry_run"]
        self.sleep = opt["sleep"]
        self.limit = opt["limit"]

        chosen = [m.strip() for m in opt["models"].split(",") if m.strip()]
        unknown = [m for m in chosen if m not in TARGETS]
        if unknown:
            raise CommandError(f"Unknown model(s): {', '.join(unknown)}. Pick from {', '.join(TARGETS)}.")

        plan = [TARGETS[m] for m in chosen]
        if opt["include_products"]:
            plan.append(PRODUCT_TARGET)

        # GoogleTranslator is the primary engine; MyMemoryTranslator is a no-key
        # fallback for the short phrases Google's free endpoint intermittently
        # returns empty for ("face wash", "lip Mask", ...).
        self._engines = []
        if not self.dry_run:
            try:
                from deep_translator import GoogleTranslator, MyMemoryTranslator
            except ImportError as exc:
                raise CommandError("deep-translator is not installed - `pip install deep-translator`.") from exc
            self._engines = [
                GoogleTranslator(source="en", target="ar"),
                MyMemoryTranslator(source="en-GB", target="ar-SA"),
            ]

        if self.dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - nothing will be written.\n"))

        self.translated_fields = 0
        self.rows_touched = 0
        self.failures = []
        self._stop = False

        for model, name_pair, desc_pair in plan:
            if self._stop:
                break
            self._process_model(model, name_pair, desc_pair)

        self._report()

    # ------------------------------------------------------------------ core --
    def _process_model(self, model, name_pair, desc_pair):
        en_name, ar_name = name_pair
        label = model.__name__

        # A row qualifies if its Arabic name is blank, or (for models with a
        # description) the English description exists but its Arabic is blank.
        needs = dj_models.Q(**{ar_name: ""}) & ~dj_models.Q(**{en_name: ""})
        if desc_pair:
            en_desc, ar_desc = desc_pair
            needs |= dj_models.Q(**{ar_desc: ""}) & ~dj_models.Q(**{en_desc: ""})
        qs = model.objects.filter(needs).order_by("pk").distinct()

        self.stdout.write(self.style.MIGRATE_HEADING(f"=== {label} ==="))
        if not qs.exists():
            self.stdout.write("  nothing to translate")
            return

        for row in qs:
            if self.limit is not None and self.rows_touched >= self.limit:
                self._stop = True
                return

            changes = {}
            src_name = getattr(row, en_name)
            if src_name and not getattr(row, ar_name):
                new_name = self._translate(src_name, ident=f"{label}#{row.pk} name")
                if new_name:
                    changes[ar_name] = new_name

            if desc_pair:
                en_desc, ar_desc = desc_pair
                if getattr(row, en_desc) and not getattr(row, ar_desc):
                    new_desc = self._translate(getattr(row, en_desc), ident=f"{label}#{row.pk} desc")
                    if new_desc:
                        changes[ar_desc] = new_desc

            if not changes:
                continue

            preview = changes.get(ar_name, "(description only)")
            self.stdout.write(f"  {src_name!r} -> {preview!r}")

            if not self.dry_run:
                for field, value in changes.items():
                    setattr(row, field, value)
                row.ar_machine_translated = True
                row.save(update_fields=list(changes) + ["ar_machine_translated"])

            self.rows_touched += 1
            self.translated_fields += len(changes)

    def _translate(self, text: str, ident: str) -> str | None:
        text = (text or "").strip()
        if not text:
            return None
        if self.dry_run:
            return f"<ar of {text}>"

        last_exc = None
        for engine in self._engines:
            for attempt in range(2):
                try:
                    out = (engine.translate(text) or "").strip()
                    time.sleep(self.sleep)
                    if out and out.lower() != text.lower():
                        return out
                    break  # empty / unchanged — try the next engine
                except Exception as exc:  # noqa: BLE001 - fall through to the next engine
                    last_exc = exc
                    if attempt == 0:
                        time.sleep(1.5)
        self.failures.append((ident, repr(last_exc) if last_exc else "empty result"))
        self.stdout.write(self.style.ERROR(f"    translate failed for {ident}: {last_exc!r}"))
        return None

    # ---------------------------------------------------------------- output --
    def _report(self):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=== Summary ==="))
        self.stdout.write(f"Rows translated  : {self.rows_touched}")
        self.stdout.write(f"Fields written   : {self.translated_fields}")
        self.stdout.write(f"Failures         : {len(self.failures)}")
        for ident, err in self.failures[:20]:
            self.stdout.write(f"  - {ident}: {err}")

        if not self.dry_run:
            self.stdout.write("")
            for model in (Category, Brand, ProductAttribute, Product):
                total = model.objects.count()
                flagged = model.objects.filter(ar_machine_translated=True).count()
                self.stdout.write(f"  {model.__name__:16s}: {flagged}/{total} flagged ar_machine_translated")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done." + ("  (dry run)" if self.dry_run else "")))
