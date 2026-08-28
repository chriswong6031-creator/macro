"""Pre-private-cutover guard on scripts.build_live_overlay.resolve_snapshot_url.

mastermindx-market-intelligence/macro is going PRIVATE. raw.githubusercontent.com,
*.github.io, and cdn.jsdelivr.net all keep serving a repo's tree via public planes
independent of the repo's visibility toggle, so a live-quotes snapshot URL pointed
at one of them would silently keep leaking (or silently break, once those planes
are retired) after the flip. resolve_snapshot_url() must reject those three host
families exactly like it already rejects a non-https scheme, while leaving a
same-origin relative path and any other https URL untouched.
"""
from __future__ import annotations

from scripts import build_live_overlay as blo


def _set(monkeypatch, url: str) -> None:
    monkeypatch.setenv("LIVE_QUOTES_SNAPSHOT_URL", url)


def test_same_origin_relative_path_passes_through(monkeypatch):
    _set(monkeypatch, "live/quotes.json")
    assert blo.resolve_snapshot_url() == "live/quotes.json"


def test_raw_githubusercontent_macro_url_rejected(monkeypatch):
    _set(monkeypatch,
         "https://raw.githubusercontent.com/mastermindx-market-intelligence/"
         "macro/live-data/live/quotes.json")
    assert blo.resolve_snapshot_url() == ""


def test_github_io_pages_url_rejected(monkeypatch):
    _set(monkeypatch,
         "https://mastermindx-market-intelligence.github.io/macro/live/quotes.json")
    assert blo.resolve_snapshot_url() == ""


def test_jsdelivr_url_rejected(monkeypatch):
    _set(monkeypatch,
         "https://cdn.jsdelivr.net/gh/mastermindx-market-intelligence/"
         "macro@live-data/live/quotes.json")
    assert blo.resolve_snapshot_url() == ""


def test_unrelated_https_url_passes_through(monkeypatch):
    # An approved public plane (e.g. an R2 origin) is untouched by this guard.
    _set(monkeypatch, "https://r2.example.com/live/quotes.json")
    assert blo.resolve_snapshot_url() == "https://r2.example.com/live/quotes.json"


def test_non_https_scheme_still_rejected(monkeypatch):
    # Pre-existing behavior (mixed-content guard) must survive the new host check.
    _set(monkeypatch, "http://insecure.example.com/quotes.json")
    assert blo.resolve_snapshot_url() == ""
