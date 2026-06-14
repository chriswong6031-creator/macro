"""Tests for engine/catalyst_stock.py — the single-stock research-brief leaf (LLM "Option 2").

No network / no API key needed: the model call is stubbed and the context is read
from a temp dir. The safety properties exercised: PUBLIC-only context assembly
(firewall — no holdings/positions/watchlist), brief validation/clamping,
degrade-never-raise, default-off, news-optional, and the per-day precompute cache.
Run as a plain script:  python tests/test_catalyst_stock.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from engine import catalyst_stock as cs  # noqa: E402

# A minimal but realistic nightly stockdata record (the shape build_stock_library writes).
STOCKDATA = {
    "ticker": "AAPL", "name": "Apple Inc", "sector": "Technology", "asof": "2026-06-12",
    "history_days": 11467,
    "tech": {"price": 291.13, "above50": True, "above200": True, "pct_vs_50dma": 2.0,
             "pct_vs_200dma": 9.3, "rsi14": 44.0, "macd_pos": False, "off_52w_high_pct": -7.6},
    "season_this": "Jun: -1.9% avg", "season_next": "Jul: +3.1% avg",
    "cycle": {"dc_phase": "stretched", "ic_phase": "mid", "translation": "left",
              "failed_cycle": False},
    "ladder": {"state": "BOTTOM WATCH", "label": "NEARING A LOW", "action": "GET READY",
               "summary_line": "Short-term: nearing a low.", "regime_label": "MIXED",
               "why": "Day 52 of a 36-42 day cycle.", "points": ["a", "b", "c"],
               "entry": {"tag": "WATCH", "urgency": "soon", "days_hi": 2}},
}
FACTORS = {"as_of": "2026-06-12", "table": [
    {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Information Technology",
     "mktcap_bn": 4280.4, "value": -1.021, "quality": 0.39, "low_vol": 1.016,
     "composite": 0.151, "profitability": float("nan")}]}   # NaN must be dropped


def _make_root(stockdata=STOCKDATA, factors=FACTORS):
    """A temp project root with site/stockdata + site/factordata laid out."""
    d = tempfile.mkdtemp()
    root = pathlib.Path(d)
    (root / "site" / "stockdata").mkdir(parents=True)
    (root / "site" / "factordata").mkdir(parents=True)
    if stockdata is not None:
        (root / "site" / "stockdata" / "AAPL.json").write_text(json.dumps(stockdata))
    if factors is not None:
        (root / "site" / "factordata" / "factors.json").write_text(json.dumps(factors))
    return root


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def test_safe_name():
    assert cs.safe_name("AAPL") == "AAPL"
    assert cs.safe_name("GC=F") == "GC_F"
    assert cs.safe_name("^VIX") == "_VIX"
    assert cs.safe_name("BRK-B") == "BRK-B"


def test_validate_brief_coerces_and_enums():
    v = cs._validate_brief({
        "summary": "  ok  ", "drivers": ["d1", "", 7, {"x": 1}], "risks": "nope",
        "catalysts": ["c1"], "confidence": "HIGH"})
    assert v["summary"] == "ok"
    assert v["drivers"] == ["d1", "7"]          # blanks dropped, dict dropped, num stringified
    assert v["risks"] == []                      # non-list -> []
    assert v["catalysts"] == ["c1"]
    assert v["confidence"] == "high"             # lowercased enum


def test_validate_brief_bad_confidence():
    v = cs._validate_brief({"confidence": "wat"})
    assert v["confidence"] == "low"              # invalid enum -> low
    assert v["summary"] is None and v["drivers"] == []


def test_validate_brief_caps_lengths():
    v = cs._validate_brief({"drivers": ["x"] * 50, "summary": "y" * 5000})
    assert len(v["drivers"]) <= cs._MAX_ITEMS
    assert len(v["summary"]) <= cs._MAX_STR


# --------------------------------------------------------------------------- #
# context assembly + FIREWALL (public-only, no holdings)
# --------------------------------------------------------------------------- #
def test_assemble_context_pulls_public_fields():
    root = _make_root()
    ctx = cs.assemble_context("AAPL", root)
    assert ctx["ticker"] == "AAPL"
    assert ctx["identity"]["name"] == "Apple Inc"
    assert ctx["signal"]["ladder_state"] == "BOTTOM WATCH"
    assert ctx["signal"]["technical"]["rsi14"] == 44.0
    assert ctx["factors"]["value"] == -1.021
    assert "profitability" not in ctx["factors"]    # NaN dropped by _round/_num


def test_assemble_context_firewall_no_private_data():
    """The assembled context must never carry holdings/positions/watchlist info —
    even if a future stockdata field tried to smuggle it in, the whitelist drops it."""
    sneaky = dict(STOCKDATA)
    sneaky["holdings"] = [{"ticker": "SECRET", "weight_pct": 12.3}]
    sneaky["watchlist"] = ["PRIVATE1", "PRIVATE2"]
    sneaky["position"] = {"shares": 100, "cost_basis": 150.0}
    root = _make_root(stockdata=sneaky)
    blob = json.dumps(cs.assemble_context("AAPL", root)).lower()
    for bad in ("holding", "position", "watchlist", "weight_pct", "secret",
                "private1", "cost_basis", "shares"):
        assert bad not in blob, f"firewall leak: {bad}"


def test_assemble_context_missing_returns_none():
    root = _make_root(stockdata=None)           # no stockdata json at all
    assert cs.assemble_context("AAPL", root) is None
    # present file but no ladder => also nothing to brief on
    root2 = _make_root(stockdata={"ticker": "AAPL", "name": "X"})
    assert cs.assemble_context("AAPL", root2) is None


def test_assemble_context_factors_optional():
    root = _make_root(factors=None)             # factors.json absent
    ctx = cs.assemble_context("AAPL", root)
    assert ctx is not None and "factors" not in ctx   # degrades gracefully


# --------------------------------------------------------------------------- #
# default-off
# --------------------------------------------------------------------------- #
def test_brief_disabled_returns_none():
    orig = cs._cfg
    cs._cfg = lambda: {"enabled": False}
    try:
        assert cs.enabled() is False
        assert cs.brief_for_ticker("AAPL") is None
    finally:
        cs._cfg = orig


def test_precompute_disabled_returns_empty():
    orig = cs._cfg
    cs._cfg = lambda: {"enabled": False}
    try:
        assert cs.precompute_briefs(["AAPL"]) == []
    finally:
        cs._cfg = orig


# --------------------------------------------------------------------------- #
# degrade-never-raise
# --------------------------------------------------------------------------- #
def test_brief_degrades_without_key():
    root = _make_root()
    oc, ocall = cs._cfg, cs._call_model
    cs._cfg = lambda: {"enabled": True, "news_enabled": False}
    cs._call_model = lambda *a, **k: (None, "no_client_or_key")
    try:
        rec = cs.brief_for_ticker("AAPL", root=root)
        assert rec is not None
        assert rec["degraded_reason"] == "no_client_or_key"
        assert rec["is_context_only"] is True
        assert rec["summary"] is None and rec["drivers"] == []
        assert rec["name"] == "Apple Inc"       # context still attached pre-call
    finally:
        cs._cfg, cs._call_model = oc, ocall


def test_brief_no_context_degrades():
    root = _make_root(stockdata=None)
    oc = cs._cfg
    cs._cfg = lambda: {"enabled": True, "news_enabled": False}
    try:
        rec = cs.brief_for_ticker("AAPL", root=root)
        assert rec["degraded_reason"] == "no_context"
        assert rec["is_context_only"] is True
    finally:
        cs._cfg = oc


def test_brief_unparseable_reply_degrades():
    root = _make_root()
    oc, ocall = cs._cfg, cs._call_model
    cs._cfg = lambda: {"enabled": True, "news_enabled": False}
    cs._call_model = lambda *a, **k: ("this is not json", None)
    try:
        rec = cs.brief_for_ticker("AAPL", root=root)
        assert rec["degraded_reason"] == "unparseable_reply"
        assert rec["is_context_only"] is True
    finally:
        cs._cfg, cs._call_model = oc, ocall


# --------------------------------------------------------------------------- #
# full path with stubbed model (no network)
# --------------------------------------------------------------------------- #
def test_brief_full_path_stubbed_model():
    root = _make_root()
    oc, ocall = cs._cfg, cs._call_model
    cs._cfg = lambda: {"enabled": True, "news_enabled": False, "llm_model": "deepseek-v4-pro"}
    captured = {}

    def _stub(system, user, cfg):
        captured["user"] = user
        reply = json.dumps({
            "summary": "Mid-cycle pause in an uptrend; fundamentals strong.",
            "drivers": ["above both moving averages", "high profitability factor"],
            "risks": ["left-translated last cycle", "rich valuation (value z -1.0)"],
            "catalysts": ["next earnings", "Fed path"],
            "confidence": "medium", "ignored_extra": "x"})
        return reply, None
    cs._call_model = _stub
    try:
        rec = cs.brief_for_ticker("AAPL", root=root)
        assert rec["summary"].startswith("Mid-cycle")
        assert rec["drivers"] == ["above both moving averages", "high profitability factor"]
        assert rec["confidence"] == "medium"
        assert rec["degraded_reason"] is None
        assert rec["is_context_only"] is True
        assert rec["ticker"] == "AAPL" and rec["name"] == "Apple Inc"
        # FIREWALL: the JSON context payload sent to the model carries no private data.
        # (Check the <context>...</context> block, not the framing prose — that prose
        # legitimately states "no holdings/positions are included".)
        ctx_blob = captured["user"].split("<context>", 1)[1].split("</context>", 1)[0].lower()
        for bad in ("holding", "position", "watchlist", "weight_pct"):
            assert bad not in ctx_blob, f"firewall leak in prompt: {bad}"
    finally:
        cs._cfg, cs._call_model = oc, ocall


def test_brief_truncation_flagged():
    root = _make_root()
    oc, ocall = cs._cfg, cs._call_model
    cs._cfg = lambda: {"enabled": True, "news_enabled": False}
    cs._call_model = lambda *a, **k: (json.dumps({"summary": "ok", "confidence": "low"}), "truncated")
    try:
        rec = cs.brief_for_ticker("AAPL", root=root)
        assert rec["summary"] == "ok"                 # parsed what completed
        assert rec["degraded_reason"] == "truncated"  # but truncation is flagged
    finally:
        cs._cfg, cs._call_model = oc, ocall


# --------------------------------------------------------------------------- #
# news leg — optional, reuses the Tier-A digest, degrades to no-news
# --------------------------------------------------------------------------- #
def test_news_digest_disabled_flag():
    assert cs.news_digest("AAPL", "Apple Inc", {"news_enabled": False}) is None


def test_news_digest_no_headlines():
    cfg = {"news_enabled": True}
    assert cs.news_digest("AAPL", "Apple Inc", cfg, headlines=[]) is None


def test_news_digest_reuses_tier_a():
    """When headlines exist, the news leg delegates to catalyst_tone.digest_document
    (so all five Tier-A gates apply). Stub it to confirm the wiring + compaction."""
    from engine import catalyst_tone
    orig = catalyst_tone.digest_document
    catalyst_tone.digest_document = lambda text, **k: {
        "tone_score": 0.2, "guidance_direction": "unknown", "risk_delta": 0.1,
        "confidence": "medium", "confidence_gated": False, "evidence": [],
        "degraded_reason": None, "disclaimer": "x", "extra": "stripped"}
    try:
        nd = cs.news_digest("AAPL", "Apple Inc", {"news_enabled": True},
                            headlines=["Apple beats on earnings"])
        assert nd["tone_score"] == 0.2 and nd["confidence"] == "medium"
        assert "disclaimer" not in nd and "extra" not in nd   # compacted to model-facing keys
    finally:
        catalyst_tone.digest_document = orig


def test_news_attached_to_brief():
    root = _make_root()
    oc, ocall, onews = cs._cfg, cs._call_model, cs.news_digest
    cs._cfg = lambda: {"enabled": True, "news_enabled": True}
    cs.news_digest = lambda ticker, name, cfg: {"tone_score": -0.3, "confidence": "high"}
    cs._call_model = lambda *a, **k: (json.dumps({"summary": "s", "confidence": "low"}), None)
    try:
        rec = cs.brief_for_ticker("AAPL", root=root)
        assert rec["news"] == {"tone_score": -0.3, "confidence": "high"}
    finally:
        cs._cfg, cs._call_model, cs.news_digest = oc, ocall, onews


# --------------------------------------------------------------------------- #
# precompute (static-site delivery) — per-day cache, cap, file output
# --------------------------------------------------------------------------- #
def test_precompute_writes_and_caches(tmp_path=None):
    root = _make_root()
    site = root / "site"
    oc, obrief = cs._cfg, cs.brief_for_ticker
    calls = {"n": 0}
    cs._cfg = lambda: {"enabled": True, "precompute_max": 30,
                       "brief_cache_dir": "data/catalyst/stockbrief_cache"}

    def _fake_brief(ticker, root=None, include_news=True):
        calls["n"] += 1
        return {"schema": "catalyst_stock.v1", "ticker": ticker, "name": "Apple Inc",
                "summary": "s", "drivers": ["d"], "risks": [], "catalysts": [],
                "confidence": "medium", "is_context_only": True, "degraded_reason": None}
    cs.brief_for_ticker = _fake_brief
    try:
        out = cs.precompute_briefs(["AAPL", "AAPL"], root=root, site=site)   # dup collapses
        assert len(out) == 1
        f = site / "stockbrief" / "AAPL.json"
        assert f.exists()
        assert json.loads(f.read_text())["ticker"] == "AAPL"
        assert calls["n"] == 1
        # second run same day -> served from the per-day cache, model not re-called
        cs.precompute_briefs(["AAPL"], root=root, site=site)
        assert calls["n"] == 1
    finally:
        cs._cfg, cs.brief_for_ticker = oc, obrief


def test_precompute_caps_set():
    root = _make_root()
    site = root / "site"
    oc, obrief = cs._cfg, cs.brief_for_ticker
    cs._cfg = lambda: {"enabled": True, "precompute_max": 2,
                       "brief_cache_dir": "data/catalyst/stockbrief_cache"}
    cs.brief_for_ticker = lambda t, root=None, include_news=True: {
        "ticker": t, "summary": "s", "drivers": [], "risks": [], "catalysts": [],
        "confidence": "low", "is_context_only": True, "degraded_reason": None}
    try:
        out = cs.precompute_briefs(["A", "B", "C", "D"], root=root, site=site)
        assert len(out) == 2                       # capped at precompute_max
    finally:
        cs._cfg, cs.brief_for_ticker = oc, obrief


def test_precompute_degraded_not_cached():
    """A degraded brief is still written to site (panel hides it) but is NOT cached,
    so the next build retries instead of pinning the failure for the day."""
    root = _make_root()
    site = root / "site"
    oc, obrief = cs._cfg, cs.brief_for_ticker
    cs._cfg = lambda: {"enabled": True, "precompute_max": 30,
                       "brief_cache_dir": "data/catalyst/stockbrief_cache"}
    cs.brief_for_ticker = lambda t, root=None, include_news=True: {
        "ticker": t, "summary": None, "drivers": [], "risks": [], "catalysts": [],
        "confidence": "low", "is_context_only": True, "degraded_reason": "no_client_or_key"}
    try:
        cs.precompute_briefs(["AAPL"], root=root, site=site)
        cache_dir = root / "data" / "catalyst" / "stockbrief_cache"
        assert not list(cache_dir.glob("AAPL_*.json"))   # nothing cached
        assert (site / "stockbrief" / "AAPL.json").exists()  # but written for the page
    finally:
        cs._cfg, cs.brief_for_ticker = oc, obrief


def test_render_markdown():
    md = cs.render_markdown({"ticker": "AAPL", "name": "Apple Inc", "model": "deepseek-v4-pro",
                             "summary": "TL;DR", "drivers": ["d1"], "risks": ["r1"],
                             "catalysts": [], "confidence": "medium"})
    assert "Apple Inc" in md and "TL;DR" in md and "- d1" in md and "confidence: medium" in md
    assert cs.render_markdown({"degraded_reason": "no_client_or_key"}).startswith(
        "_stock brief unavailable")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
