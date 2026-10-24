"""Copy everything under MEDIA_ROOT up to the R2 bucket (settings.MEDIA_S3_OPTIONS).

Run once on the live server *before* switching MEDIA_STORAGE_BACKEND=s3, so the
site never points at images that aren't in the bucket yet. Works while the site
still serves from disk because it talks to the bucket directly, not through the
default storage. Files already in the bucket are skipped, so it's safe to re-run.

    python manage.py upload_media_to_r2 --dry-run
    python manage.py upload_media_to_r2
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError


def bucket_storage():
    from storages.backends.s3 import S3Storage

    return S3Storage(**settings.MEDIA_S3_OPTIONS)


class Command(BaseCommand):
    help = "Upload MEDIA_ROOT to the configured R2/S3 bucket (skips files already there)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List what would be uploaded.")

    def handle(self, *args, dry_run=False, **options):
        if not settings.MEDIA_S3_OPTIONS:
            raise CommandError("No bucket configured — set AWS_STORAGE_BUCKET_NAME and the other AWS_* vars.")
        root = Path(settings.MEDIA_ROOT)
        if not root.is_dir():
            raise CommandError(f"MEDIA_ROOT {root} does not exist.")

        storage = bucket_storage()
        uploaded = skipped = 0
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            name = path.relative_to(root).as_posix()
            if storage.exists(name):
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(f"would upload {name}")
            else:
                with path.open("rb") as fh:
                    saved = storage.save(name, File(fh))
                if saved != name:  # the DB stores `name`; a renamed copy would be unreachable
                    raise CommandError(f"{name} was stored as {saved} — aborting.")
                self.stdout.write(f"uploaded {name}")
            uploaded += 1

        verb = "would upload" if dry_run else "uploaded"
        self.stdout.write(self.style.SUCCESS(f"{verb} {uploaded} file(s), {skipped} already in the bucket."))
