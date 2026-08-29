"""Download the real homepage videos from the live site into HomepageVideo rows.

The live store at https://dr-rasheljo.com/ uses one hero video plus three shorter
"divider" videos between the merchandising rails. This command reads the live
homepage HTML, extracts the `<video src>` URLs in document order, maps them to the
four slots (hero, section_1, section_2, section_3), streams each file down and
attaches it to the matching HomepageVideo row.

    python manage.py import_homepage_videos --dry-run
    python manage.py import_homepage_videos
    python manage.py import_homepage_videos --force        # re-download even if present

Idempotent: keyed on `slot` via update_or_create; an existing row whose file is
already the same source filename is left alone unless --force is given.
"""

from __future__ import annotations

import os
import re
import tempfile
from urllib.parse import unquote, urlsplit, urlunsplit, quote

import requests
from django.core.files import File
from django.core.management.base import BaseCommand

from content.models import HomepageVideo

LIVE_HOME = "https://dr-rasheljo.com/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 drrasheljo-video-import/1.0"
)
# DOM order on the homepage → slot. The hero is first, then the three dividers.
SLOT_ORDER = [
    HomepageVideo.HERO,
    HomepageVideo.SECTION_1,
    HomepageVideo.SECTION_2,
    HomepageVideo.SECTION_3,
]
VIDEO_SRC_RE = re.compile(rb'<video[^>]*\ssrc="([^"]+\.mp4[^"]*)"', re.IGNORECASE)
LARGE_FILE_WARN_BYTES = 30 * 1024 * 1024


def _encode_url(raw: str) -> str:
    """The live HTML carries literal (already UTF-8) bytes in some filenames.
    Percent-encode the path so requests sends a valid URL, without double-encoding
    an already-encoded one."""
    parts = urlsplit(raw)
    path = quote(unquote(parts.path), safe="/%:")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def _human(nbytes: int) -> str:
    mb = nbytes / (1024 * 1024)
    return f"{mb:.1f} MB"


class Command(BaseCommand):
    help = "Import the real homepage videos from dr-rasheljo.com into HomepageVideo."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="List the videos found; download nothing, write nothing.")
        parser.add_argument("--force", action="store_true",
                            help="Re-download and replace even if the slot already has that file.")
        parser.add_argument("--timeout", type=int, default=60)

    def handle(self, *args, **opt):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        timeout = opt["timeout"]

        self.stdout.write("Fetching live homepage HTML ...")
        try:
            resp = self.session.get(LIVE_HOME, timeout=timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            self.stderr.write(self.style.ERROR(f"Could not fetch {LIVE_HOME}: {exc!r}"))
            return

        raw_urls = [m.group(1).decode("utf-8", "surrogateescape") for m in VIDEO_SRC_RE.finditer(resp.content)]
        # de-dupe preserving order
        seen, urls = set(), []
        for u in raw_urls:
            if u not in seen:
                seen.add(u)
                urls.append(u)

        if not urls:
            self.stderr.write(self.style.ERROR("No <video src=\"…mp4\"> found on the homepage."))
            return

        self.stdout.write(self.style.SUCCESS(f"Found {len(urls)} video(s) on the homepage:"))
        plan = []
        for i, url in enumerate(urls):
            slot = SLOT_ORDER[i] if i < len(SLOT_ORDER) else f"(no slot #{i})"
            encoded = _encode_url(url)
            self.stdout.write(f"  [{slot}] {url}")
            if encoded != url:
                self.stdout.write(f"           -> {encoded}")
            if i < len(SLOT_ORDER):
                plan.append((slot, url, encoded))

        if opt["dry_run"]:
            self.stdout.write("")
            for slot, url, encoded in plan:
                try:
                    head = self.session.head(encoded, timeout=timeout, allow_redirects=True)
                    size = int(head.headers.get("content-length", 0))
                    note = "  ⚠ large" if size > LARGE_FILE_WARN_BYTES else ""
                    self.stdout.write(f"  {slot}: {head.status_code} {_human(size)}{note}")
                except requests.RequestException as exc:
                    self.stderr.write(self.style.WARNING(f"  {slot}: HEAD failed — {exc!r}"))
            self.stdout.write(self.style.WARNING("\nDRY RUN — nothing downloaded or written."))
            return

        ok, failed, large = 0, [], []
        for slot, url, encoded in plan:
            basename = encoded.rsplit("/", 1)[-1]
            existing = HomepageVideo.objects.filter(slot=slot).first()
            if (
                existing
                and existing.video_file
                and existing.video_file.name.endswith(basename)
                and not opt["force"]
            ):
                self.stdout.write(f"  {slot}: already imported ({basename}) — skipping (use --force to replace)")
                ok += 1
                continue

            self.stdout.write(f"  {slot}: downloading {basename} ...")
            try:
                size = self._download_into_slot(slot, encoded, basename, timeout)
            except Exception as exc:  # noqa: BLE001 — one failure must not abort the rest
                self.stderr.write(self.style.ERROR(f"  {slot}: FAILED — {exc!r}"))
                failed.append(slot)
                continue

            ok += 1
            flag = ""
            if size > LARGE_FILE_WARN_BYTES:
                large.append((slot, size))
                flag = self.style.WARNING("  ⚠ exceeds ~30 MB — consider re-encoding before production")
            self.stdout.write(self.style.SUCCESS(f"  {slot}: saved {_human(size)}{flag}"))

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=== Summary ==="))
        self.stdout.write(f"Imported/kept : {ok}/{len(plan)}")
        if failed:
            self.stdout.write(self.style.ERROR(f"Failed slots  : {', '.join(failed)}"))
        for slot, size in large:
            self.stdout.write(self.style.WARNING(f"Oversized     : {slot} = {_human(size)} (compress/re-encode for prod)"))
        for v in HomepageVideo.objects.filter(slot__in=SLOT_ORDER).order_by("slot"):
            has = bool(v.video_file)
            self.stdout.write(f"  {v.slot:10s} file={'yes' if has else 'NO'} active={v.is_active}")

    def _download_into_slot(self, slot, url, basename, timeout) -> int:
        with self.session.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            written = 0
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        tmp.write(chunk)
                        written += len(chunk)
                tmp_path = tmp.name

        video, _ = HomepageVideo.objects.update_or_create(
            slot=slot,
            defaults={"video_url": "", "is_active": True},
        )
        with open(tmp_path, "rb") as fh:
            # replace any previous file for this slot
            video.video_file.save(basename, File(fh), save=True)

        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return written
