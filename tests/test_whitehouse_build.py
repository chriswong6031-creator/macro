"""scripts/build_whitehouse.py + scripts/inject_wh_banner.py tests — banner expiry,
idempotent writes, ledger supersede, page render (no network/LLM), and banner
injection idempotency.

Run: python -m tests.test_whitehouse_build
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from scripts import build_whitehouse as bw  # noqa: E402
from scripts import inject_wh_banner as inj  # noqa: E402


def _rec(rid, pub_days_ago, banner_days, importance, activated=True):
    pub = datetime.now(timezone.utc) - timedelta(days=pub_days_ago)
    return {
        "schema": "wh_alert.v1", "id": rid, "activated": activated,
        "source_title": rid, "source_url": "https://wh/x", "section": "news",
        "published": pub.isoformat(), "generated_at": pub.isoformat(),
        "importance": importance, "banner_days": banner_days, "tone": "tailwind",
        "banner_title": f"title {rid}", "banner_title_zh": None,
        "summary": "s", "summary_zh": None, "analysis": "p1\np2",
        "sectors": [{"name": "Tech", "impact": "tailwind", "rationale": "r"}],
        "tickers": [{"symbol": "NVDA", "direction": "benefit", "rationale": "r", "chg_pct": 1.5},
                    {"symbol": "INTC", "direction": "hurt", "rationale": "r", "chg_pct": -2.0}],
        "confidence": "high",
    }


def test_banner_payload_filters_expired_and_sorts() -> None:
    now = datetime.now(timezone.utc)
    rows = [
        _rec("wh-live-low", 1, 5, 65),     # live, expires in 4d
        _rec("wh-live-high", 0, 7, 90),    # live, most important
        _rec("wh-expired", 10, 3, 80),     # published 10d ago, 3d banner → expired
    ]
    payload = bw._banner_payload(rows, now)
    ids = [a["id"] for a in payload["alerts"]]
    assert "wh-expired" not in ids
    assert ids == ["wh-live-high", "wh-live-low"]   # importance desc
    a = payload["alerts"][0]
    assert a["href"] == "whitehouse.html#wh-live-high"
    assert a["tickers"][0]["symbol"] == "NVDA"
    assert "expires_at" in a and a["schema"] if "schema" in a else True
    assert payload["schema"] == "wh_banner.v1"


def test_expires_at_math() -> None:
    r = _rec("wh-x", 2, 5, 70)
    exp = bw._expires_at(r)
    gen = datetime.fromisoformat(r["generated_at"])
    assert exp == gen + timedelta(days=5)               # anchored on generated_at
    assert bw._expires_at({"published": "", "banner_days": 0}) is None


def test_expiry_anchored_on_activation_not_stale_publish() -> None:
    # an item PUBLISHED 4 days ago but only just ACTIVATED (generated_at=now) with a
    # short 1-day banner must still be LIVE — anchoring on published would mis-expire it
    now = datetime.now(timezone.utc)
    r = _rec("wh-stale-pub", 4, 1, 80)
    r["generated_at"] = now.isoformat()                 # activated just now
    exp = bw._expires_at(r)
    assert exp > now                                     # not born-expired
    payload = bw._banner_payload([r], now)
    assert [a["id"] for a in payload["alerts"]] == ["wh-stale-pub"]


def test_parse_dt_is_tz_aware_and_compares() -> None:
    naive = bw._parse_dt("2026-06-23")                  # date-only → naive source
    assert naive is not None and naive.tzinfo is not None
    # comparing against an aware now must not raise
    assert (datetime.now(timezone.utc) > naive) in (True, False)
    assert bw._parse_dt(None) is None and bw._parse_dt("garbage") is None


def test_banner_payload_caps_to_max() -> None:
    now = datetime.now(timezone.utc)
    rows = [_rec(f"wh-{i}", 0, 7, 60 + i) for i in range(10)]  # 10 live, distinct importance
    payload = bw._banner_payload(rows, now, max_alerts=6)
    assert len(payload["alerts"]) == 6
    # kept the most important (importance 69..64), dropped the lowest
    assert payload["alerts"][0]["importance"] == 69
    assert min(a["importance"] for a in payload["alerts"]) == 64


def test_bad_row_skipped_not_fatal() -> None:
    now = datetime.now(timezone.utc)
    good = _rec("wh-good", 0, 5, 70)
    bad = {"id": "wh-bad", "banner_days": 5, "published": None, "generated_at": None}
    payload = bw._banner_payload([good, bad], now)      # must not raise
    assert [a["id"] for a in payload["alerts"]] == ["wh-good"]


def test_write_if_changed_idempotent() -> None:
    d = Path(tempfile.mkdtemp())
    p = d / "x.json"
    assert bw._write_if_changed(p, "hello") is True       # first write
    assert bw._write_if_changed(p, "hello") is False      # identical → no write
    assert bw._write_if_changed(p, "world") is True       # changed → write


def test_ledger_append_load_supersede() -> None:
    d = Path(tempfile.mkdtemp())
    bw._append_ledger(d, _rec("wh-a", 1, 5, 70))
    bw._append_ledger(d, _rec("wh-b", 0, 5, 80))
    bw._append_ledger(d, {**_rec("wh-a", 1, 5, 99), "tone": "headwind"})  # supersede wh-a
    rows = bw._load_ledger(d)
    ids = sorted(r["id"] for r in rows)
    assert ids == ["wh-a", "wh-b"]                        # deduped by id
    a = next(r for r in rows if r["id"] == "wh-a")
    assert a["importance"] == 99 and a["tone"] == "headwind"   # latest row wins
    # inactive rows are excluded
    bw._append_ledger(d, _rec("wh-c", 0, 5, 50, activated=False))
    assert "wh-c" not in {r["id"] for r in bw._load_ledger(d)}


def test_render_page_escapes_and_links() -> None:
    # render against the real templates dir; inject a hostile title to prove escaping
    rows = [_rec("wh-xss", 0, 5, 80)]
    rows[0]["banner_title"] = "<script>alert(1)</script> tariffs"
    html = bw._render_page(config.ROOT, rows)
    assert 'id="wh-xss"' in html
    assert "<script>alert(1)</script> tariffs" not in html          # raw not present
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html          # escaped
    assert "whitehouse.gov" not in html or "wh/x" in html
    assert inj._MARKER in html                                       # self-includes banner


def test_render_empty_page_ok() -> None:
    html = bw._render_page(config.ROOT, [])
    assert "White House" in html
    assert inj._MARKER in html


def test_render_page_emits_current_asset_stamps() -> None:
    # The hourly sentinel (whitehouse-sentinel.yml) commits this page straight to
    # main with NO post-render optimize_assets pass, so the render itself must
    # carry the ?v= stamps: before 2026-07-29 every alert update regressed the
    # page to bare refs — the edge re-validated theme.css & co on every nav, and
    # the page sat dirty under `python -m scripts.optimize_assets` in every clean
    # checkout. Asserted against the real site/ tree, same as the render tests
    # above use the real templates/ dir.
    import re
    html = bw._render_page(config.ROOT, [_rec("wh-stamp", 0, 5, 80)])
    for asset in ("theme.css", "theme.js", "wh_banner.js"):
        assert re.search(re.escape(asset) + r"\?v=[0-9a-f]{8}", html), (
            f"{asset} rendered without a ?v= stamp — the sentinel would commit it bare")


def test_render_page_is_a_fixpoint_of_the_sitewide_sweep() -> None:
    # Builder-side stamping and the render lanes' site-wide sweep must produce
    # the SAME bytes, or the two lanes rewrite each other's output and
    # site/whitehouse.html oscillates on main (hourly sentinel vs daily sweep).
    # NOTE deliberately NOT a fixpoint test over the COMMITTED page: committed
    # stamps go legitimately stale whenever a shared asset changes in a PR that
    # doesn't re-render this page (the sweep lanes re-hash them post-merge), so
    # that variant reds unrelated PRs. The render-time contract is the invariant.
    from scripts.optimize_assets import make_optimizer
    site = config.ROOT / "site"
    html = bw._render_page(config.ROOT, [_rec("wh-fix", 0, 5, 80)])
    assert make_optimizer(site)(html, site) == html


def test_sector_mixed_not_rendered_as_headwind() -> None:
    # a sector normalised to 'mixed' (or any non-binary impact) must show a neutral
    # label, NOT a red Headwind that misrepresents the read
    r = _rec("wh-mix", 0, 5, 80)
    r["sectors"] = [{"name": "Banks", "impact": "mixed", "rationale": "ambiguous"}]
    html = bw._render_page(config.ROOT, [r])
    assert "wh-dir neutral" in html
    # the Banks row must not be tagged hurt/Headwind
    import re
    row = re.search(r"Banks.*?</tr>", html, re.S).group(0)
    assert "Headwind" not in row and "wh-dir hurt" not in row


def test_inject_text_idempotent() -> None:
    base = "<html><body><h1>hi</h1></body></html>"
    once = inj.inject_text(base, "")
    assert inj._MARKER in once and once.count("wh_banner.js") == 1
    twice = inj.inject_text(once, "")
    assert twice == once                                  # idempotent
    deep = inj.inject_text(base, "../")
    assert 'src="../wh_banner.js"' in deep and 'data-root="../"' in deep


def test_inject_no_body_appends() -> None:
    out = inj.inject_text("<div>no body tag</div>", "")
    assert inj._MARKER in out


def _run() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")


if __name__ == "__main__":
    _run()
    print("all whitehouse_build tests passed")
