"""Seed the storefront logo on the SiteSettings singleton from the live site.

The original store at https://dr-rasheljo.com/ serves its header logo from
`/wp-content/uploads/.../Untitled-design-*.png`. This command downloads the
current one and stores it on `SiteSettings.logo` so the rebuilt storefront shows
the real wordmark instead of the text fallback.

Idempotent: does nothing if a logo is already set unless `--force` is passed.

    python manage.py seed_site_logo
    python manage.py seed_site_logo --force
    python manage.py seed_site_logo --url https://dr-rasheljo.com/wp-content/uploads/2025/12/Untitled-design-....png
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from content.models import SiteSettings

LIVE_ROOT = "https://dr-rasheljo.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 drrasheljo-logo-seed/1.0"
)
# The live header logo lives under wp-content/uploads and is named like
# "Untitled-design-2025-12-11T180800.310-scaled.png". The exact filename changes
# whenever the store owner re-uploads, so discover it from the homepage HTML
# rather than hard-coding it.
LOGO_SRC_RE = re.compile(
    r'<img[^>]+src="([^"]*wp-content/uploads/[^"]*Untitled-design[^"]*\.png)"',
    re.IGNORECASE,
)


class Command(BaseCommand):
    help = "Download the real storefront logo from the live site onto SiteSettings.logo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace the logo even if one is already set.",
        )
        parser.add_argument(
            "--url",
            default="",
            help="Explicit logo image URL (skips homepage discovery).",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=20.0,
            help="Per-request timeout in seconds (default: 20).",
        )

    def handle(self, *args, **options):
        settings_row = SiteSettings.load()
        if settings_row.logo and not options["force"]:
            self.stdout.write(
                self.style.WARNING(
                    f"SiteSettings already has a logo ({settings_row.logo.name}). "
                    "Pass --force to replace it."
                )
            )
            return

        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        timeout = options["timeout"]

        logo_url = options["url"] or self._discover_logo_url(session, timeout)
        if not logo_url:
            raise CommandError(
                "Could not find the logo URL on the live homepage. "
                "Inspect the site's header <img> and pass it via --url."
            )

        self.stdout.write(f"Downloading logo: {logo_url}")
        try:
            resp = session.get(logo_url, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Logo download failed: {exc!r}") from exc

        content = resp.content
        if not content or len(content) < 100:
            raise CommandError("Logo download returned an empty / implausibly small file.")

        filename = urlparse(logo_url).path.rsplit("/", 1)[-1] or "logo.png"
        settings_row.logo.save(filename, ContentFile(content), save=True)
        self.stdout.write(
            self.style.SUCCESS(
                f"Saved logo to SiteSettings.logo as {settings_row.logo.name} "
                f"({len(content):,} bytes)"
            )
        )

    def _discover_logo_url(self, session: requests.Session, timeout: float) -> str:
        try:
            resp = session.get(LIVE_ROOT, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CommandError(f"Could not load {LIVE_ROOT}: {exc!r}") from exc

        match = LOGO_SRC_RE.search(resp.text)
        if not match:
            return ""
        return urljoin(LIVE_ROOT, match.group(1))
