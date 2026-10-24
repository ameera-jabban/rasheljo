from io import StringIO
from unittest import mock

import pytest
from django.core.files.storage import FileSystemStorage
from django.core.management import CommandError, call_command


@pytest.fixture
def media(tmp_path, settings):
    root = tmp_path / "media"
    (root / "products").mkdir(parents=True)
    (root / "products" / "a.jpg").write_bytes(b"a")
    (root / "site").mkdir()
    (root / "site" / "logo.png").write_bytes(b"logo")
    settings.MEDIA_ROOT = str(root)
    settings.MEDIA_S3_OPTIONS = {"bucket_name": "drrasheljo"}
    bucket = FileSystemStorage(location=str(tmp_path / "bucket"))
    with mock.patch("content.management.commands.upload_media_to_r2.bucket_storage", return_value=bucket):
        yield bucket


def test_uploads_then_skips_on_rerun(media):
    out = StringIO()
    call_command("upload_media_to_r2", stdout=out)
    assert media.exists("products/a.jpg") and media.exists("site/logo.png")
    assert "uploaded 2 file(s), 0 already" in out.getvalue()

    out = StringIO()
    call_command("upload_media_to_r2", stdout=out)
    assert "uploaded 0 file(s), 2 already" in out.getvalue()


def test_dry_run_uploads_nothing(media):
    out = StringIO()
    call_command("upload_media_to_r2", "--dry-run", stdout=out)
    assert not media.exists("products/a.jpg")
    assert "would upload 2 file(s)" in out.getvalue()


def test_requires_bucket(settings):
    settings.MEDIA_S3_OPTIONS = None
    with pytest.raises(CommandError):
        call_command("upload_media_to_r2")
