"""tests/test_marketing_media_publish.py — R2 chart-PNG publish (fail-soft).

media_publish.publish_chart_png uploads a rendered PNG to the existing public R2
data plane and returns the public https URL, or None when creds are absent. ZERO
live network: the S3 client is injected as a stub. Covers env-absent → None,
empty bytes → None, the key/url construction on the public data plane, and the
happy-path put_object args.
"""
from __future__ import annotations

import pytest

_R2_ENV = ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


def _clear_r2_env(monkeypatch):
    for e in _R2_ENV:
        monkeypatch.delenv(e, raising=False)


def test_chart_key_shape():
    from engine.marketing.media_publish import chart_key
    assert chart_key("2026-07-23", "chart-001") == "marketing/charts/2026-07-23/chart-001.png"
    # slashes in inputs are neutralized (no key traversal)
    assert "/" not in chart_key("a/b", "c/d").rsplit("/", 2)[-2]


def test_public_url_on_the_data_plane():
    from engine.marketing.media_publish import public_url_for_key, chart_key
    url = public_url_for_key(chart_key("2026-07-23", "chart-9"))
    assert url.startswith("https://pub-") and ".r2.dev/" in url
    assert url.endswith("/marketing/charts/2026-07-23/chart-9.png")


def test_publish_env_absent_returns_none(monkeypatch):
    from engine.marketing.media_publish import publish_chart_png, chart_key
    _clear_r2_env(monkeypatch)
    # No creds → no client → None (fail-soft, no raise).
    assert publish_chart_png(b"\x89PNG-fake-bytes", chart_key("2026-07-23", "c1")) is None


def test_publish_empty_bytes_returns_none():
    from engine.marketing.media_publish import publish_chart_png

    class _NeverCalled:
        def put_object(self, **kw):  # pragma: no cover - must not be reached
            raise AssertionError("put_object called for empty bytes")

    assert publish_chart_png(b"", "marketing/charts/x/y.png", s3=_NeverCalled()) is None


def test_publish_stub_uploads_and_returns_public_url(monkeypatch):
    from engine.marketing.media_publish import publish_chart_png, chart_key
    monkeypatch.setenv("R2_BUCKET", "research")
    calls: dict = {}

    class _StubS3:
        def put_object(self, **kw):
            calls.update(kw)

    url = publish_chart_png(b"\x89PNG payload", chart_key("2026-07-23", "chart-7"), s3=_StubS3())
    assert url is not None
    assert url.endswith("/marketing/charts/2026-07-23/chart-7.png")
    assert calls["Bucket"] == "research"
    assert calls["Key"] == "marketing/charts/2026-07-23/chart-7.png"
    assert calls["ContentType"] == "image/png"
    assert calls["Body"] == b"\x89PNG payload"


def test_publish_bucket_missing_returns_none(monkeypatch):
    from engine.marketing.media_publish import publish_chart_png

    class _StubS3:
        def put_object(self, **kw):  # pragma: no cover
            raise AssertionError("must not upload without a bucket")

    monkeypatch.delenv("R2_BUCKET", raising=False)
    # A client is injected (so creds-check is bypassed) but R2_BUCKET is unset.
    assert publish_chart_png(b"\x89PNG", "marketing/charts/x/y.png", s3=_StubS3()) is None


def test_publish_upload_error_returns_none():
    from engine.marketing.media_publish import publish_chart_png
    import os

    class _BoomS3:
        def put_object(self, **kw):
            raise RuntimeError("network down")

    os.environ["R2_BUCKET"] = "research"
    try:
        assert publish_chart_png(b"\x89PNG", "marketing/charts/x/y.png", s3=_BoomS3()) is None
    finally:
        os.environ.pop("R2_BUCKET", None)
