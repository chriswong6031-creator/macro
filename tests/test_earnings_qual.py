"""Tests for the earnings-call qualitative scorer (SGA W4).

Covers: score_text output schema (HTTP call mocked), tag taxonomy enforcement,
trading-verb post-filter, source_sha256 dedup skip, parquet upsert idempotency,
fail-open when no sources, R2 scripts no-op without creds, and the 8-K fallback
path selection.  No live network, no real LLM.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engine import earnings_qual as eq  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
_GOOD_JSON = {
    "sentiment": 0.7,
    "performance": 8.5,
    "confidence": 0.9,
    "tone_word": "confident",
    "positive_highlights": [
        "Revenue up 22% YoY, above the high end of guidance",
        "Gross margin expanded 180 bps to 46.2%",
    ],
    "negative_highlights": ["Cloud segment growth decelerated to 12%"],
    "tags": ["beat_and_raise", "guidance_raised", "margin_expansion"],
}


def _mock_reply(monkeypatch, obj_or_text):
    """Patch _dispatch to return a canned reply (dict -> json string, or raw)."""
    if isinstance(obj_or_text, (dict, list)):
        text = json.dumps(obj_or_text)
    else:
        text = obj_or_text

    def fake_dispatch(system, user, cfg, provider_cfg, *, max_tokens):
        return text, None, "openai_compat"

    monkeypatch.setattr(eq, "_dispatch", fake_dispatch)


# --------------------------------------------------------------------------- #
# 1. score_text output schema
# --------------------------------------------------------------------------- #
def test_score_text_schema(monkeypatch):
    _mock_reply(monkeypatch, _GOOD_JSON)
    row = eq.score_text("Some earnings call text.", "nvda", "Q1", 2026,
                        call_date="2026-05-28")
    # required keys present
    for k in ("ticker", "quarter", "year", "call_date", "source", "model",
              "sentiment", "performance", "confidence", "tone_word",
              "positive_highlights", "negative_highlights", "tags",
              "source_sha256", "scored_at", "is_context_only", "degraded_reason"):
        assert k in row, f"missing key {k}"
    assert row["ticker"] == "NVDA"           # upper-cased
    assert row["quarter"] == "Q1"
    assert row["year"] == 2026
    assert row["is_context_only"] is True    # SGA-R5 — ALWAYS
    assert row["degraded_reason"] is None
    assert -1.0 <= row["sentiment"] <= 1.0
    assert 0.0 <= row["performance"] <= 10.0
    assert 0.0 <= row["confidence"] <= 1.0
    assert row["tone_word"] == "confident"
    assert isinstance(row["positive_highlights"], list)
    assert isinstance(row["tags"], list)
    assert len(row["source_sha256"]) == 64   # sha256 hex


def test_score_text_clips_out_of_range(monkeypatch):
    _mock_reply(monkeypatch, {
        "sentiment": 5.0,        # out of [-1,1]
        "performance": -3.0,     # out of [0,10]
        "confidence": 2.0,       # out of [0,1]
        "tone_word": "bananas",  # not an allowed tone → dropped
        "positive_highlights": [],
        "negative_highlights": [],
        "tags": [],
    })
    row = eq.score_text("txt", "AAPL", 2, 2025)
    assert row["sentiment"] == 1.0
    assert row["performance"] == 0.0
    assert row["confidence"] == 1.0
    assert row["tone_word"] is None          # unknown tone dropped
    assert row["quarter"] == "Q2"            # int quarter normalized


# --------------------------------------------------------------------------- #
# 2. Tag taxonomy enforcement — unknown tags dropped
# --------------------------------------------------------------------------- #
def test_tag_taxonomy_drops_unknown(monkeypatch):
    obj = dict(_GOOD_JSON)
    obj["tags"] = ["beat_and_raise", "totally_made_up_tag", "MARGIN_EXPANSION",
                   "buyback_or_dividend", "beat_and_raise"]  # dup + case + unknown
    _mock_reply(monkeypatch, obj)
    row = eq.score_text("txt", "MSFT", "Q3", 2026)
    tags = row["tags"]
    assert "totally_made_up_tag" not in tags
    assert "beat_and_raise" in tags
    assert "margin_expansion" in tags        # lower-cased match
    assert "buyback_or_dividend" in tags
    assert tags.count("beat_and_raise") == 1  # de-duplicated
    assert all(t in eq.TAG_TAXONOMY for t in tags)


# --------------------------------------------------------------------------- #
# 3. Trading-verb post-filter
# --------------------------------------------------------------------------- #
def test_trading_verb_postfilter(monkeypatch):
    obj = dict(_GOOD_JSON)
    obj["positive_highlights"] = [
        "Accumulate shares on the pullback",         # trade call → rewritten/scrubbed
        "Revenue grew 30% with strong demand",       # clean, kept
        "Buy the dip here",                           # dominated by trade call → dropped or rewritten
    ]
    obj["negative_highlights"] = [
        "Investors should sell into strength",        # scrubbed
        "Margins compressed 200 bps on input costs",  # clean, kept
    ]
    _mock_reply(monkeypatch, obj)
    row = eq.score_text("txt", "TSLA", "Q4", 2025)
    joined = " ".join(row["positive_highlights"] + row["negative_highlights"]).lower()
    # No hard trade verbs survive anywhere.
    for banned in ("buy", "sell", "short", "accumulate", " long", "overweight"):
        assert banned not in joined, f"trading verb leaked: {banned!r} in {joined!r}"
    # The genuinely clean highlights survive.
    assert any("revenue grew 30%" in h.lower() for h in row["positive_highlights"])
    assert any("margins compressed" in h.lower() for h in row["negative_highlights"])


def test_scrub_trading_verbs_unit():
    # Direct unit coverage of the scrubber.
    assert eq._scrub_trading_verbs("Buy NVDA now") is None or \
        "buy" not in eq._scrub_trading_verbs("Buy NVDA now").lower()
    assert eq._scrub_trading_verbs("Revenue up 20% YoY") == "Revenue up 20% YoY"
    # empty / non-str
    assert eq._scrub_trading_verbs("") is None
    assert eq._scrub_trading_verbs(None) is None


def test_highlights_capped_at_three(monkeypatch):
    obj = dict(_GOOD_JSON)
    obj["positive_highlights"] = [f"Clean fact number {i}" for i in range(6)]
    _mock_reply(monkeypatch, obj)
    row = eq.score_text("txt", "AMD", "Q1", 2026)
    assert len(row["positive_highlights"]) <= 3


# --------------------------------------------------------------------------- #
# 4. Invalid-JSON retry then degrade
# --------------------------------------------------------------------------- #
def test_invalid_json_degrades(monkeypatch):
    calls = {"n": 0}

    def fake_dispatch(system, user, cfg, provider_cfg, *, max_tokens):
        calls["n"] += 1
        return "I cannot produce JSON, sorry.", None, "openai_compat"

    monkeypatch.setattr(eq, "_dispatch", fake_dispatch)
    row = eq.score_text("txt", "X", "Q1", 2026)
    assert row["degraded_reason"] == "invalid_json"
    assert row["sentiment"] is None
    assert calls["n"] == 2                    # first + one retry
    assert row["is_context_only"] is True     # still context-only


def test_no_provider_degrades(monkeypatch):
    def fake_dispatch(system, user, cfg, provider_cfg, *, max_tokens):
        return None, "no_provider", None

    monkeypatch.setattr(eq, "_dispatch", fake_dispatch)
    row = eq.score_text("txt", "X", "Q1", 2026)
    assert row["degraded_reason"] == "no_provider"
    assert row["model"] is None


def test_empty_text_degrades():
    row = eq.score_text("   ", "X", "Q1", 2026)
    assert row["degraded_reason"] == "empty_text"
    assert row["is_context_only"] is True


def test_json_inside_code_fence(monkeypatch):
    fenced = "```json\n" + json.dumps(_GOOD_JSON) + "\n```"
    _mock_reply(monkeypatch, fenced)
    row = eq.score_text("txt", "NVDA", "Q1", 2026)
    assert row["degraded_reason"] is None
    assert row["tone_word"] == "confident"


# --------------------------------------------------------------------------- #
# 5. sha dedup skip + parquet upsert idempotency
# --------------------------------------------------------------------------- #
def test_upsert_and_dedup_skip(monkeypatch, tmp_path):
    _mock_reply(monkeypatch, _GOOD_JSON)
    # transcript dir with one file
    tdir = tmp_path / "data" / "earnings_calls" / "transcripts"
    tdir.mkdir(parents=True)
    (tdir / "NVDA.json").write_text(json.dumps({
        "ticker": "NVDA", "quarter": "Q1", "year": 2026,
        "call_date": "2026-05-28", "text": "Some transcript body here.",
    }), encoding="utf-8")

    n1 = eq.score_new(root=tmp_path, source="transcript", limit=8)
    assert n1 == 1
    df = eq.load_scores(tmp_path)
    assert len(df) == 1
    assert df.iloc[0]["ticker"] == "NVDA"
    # tags/highlights round-trip as JSON strings in the store
    assert isinstance(df.iloc[0]["tags"], str)
    assert "beat_and_raise" in df.iloc[0]["tags"]

    # Second run: same sha → skipped, store unchanged.
    n2 = eq.score_new(root=tmp_path, source="transcript", limit=8)
    assert n2 == 0
    df2 = eq.load_scores(tmp_path)
    assert len(df2) == 1                       # no duplicate row


def test_upsert_replaces_same_key(tmp_path):
    root = tmp_path
    row_a = {
        "ticker": "AAPL", "quarter": "Q1", "year": 2026, "call_date": "2026-02-01",
        "source": "transcript", "model": "qwen", "sentiment": 0.1,
        "performance": 5.0, "confidence": 0.5, "tone_word": "steady",
        "positive_highlights": ["a"], "negative_highlights": [], "tags": ["macro_sensitivity"],
        "source_sha256": "sha_a", "scored_at": "2026-02-01T00:00:00Z",
    }
    assert eq.upsert_scores([row_a], root=root) == 1
    row_b = dict(row_a)
    row_b.update(sentiment=0.9, source_sha256="sha_b", scored_at="2026-02-02T00:00:00Z")
    assert eq.upsert_scores([row_b], root=root) == 1
    df = eq.load_scores(root)
    # same (ticker,quarter,year,source) → one row, the newer sentiment kept
    assert len(df) == 1
    assert float(df.iloc[0]["sentiment"]) == pytest.approx(0.9)


# --------------------------------------------------------------------------- #
# 6. Fail-open when no sources
# --------------------------------------------------------------------------- #
def test_score_new_no_sources(tmp_path):
    # no transcripts dir, no 8-K store → 0, no crash
    assert eq.score_new(root=tmp_path, source="auto", limit=8) == 0
    assert eq.score_new(root=tmp_path, source="transcript", limit=8) == 0
    assert eq.score_new(root=tmp_path, source="8k", limit=8) == 0


def test_score_new_cap_zero(tmp_path):
    assert eq.score_new(root=tmp_path, source="auto", limit=0) == 0


# --------------------------------------------------------------------------- #
# 7. R2 scripts no-op without creds (env-clean)
# --------------------------------------------------------------------------- #
def test_publish_r2_noop_without_creds(monkeypatch, tmp_path):
    for var in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    from scripts import publish_earnings_r2 as pub
    # even with a data dir present, no creds → exit 0 (no-op)
    d = tmp_path / "earnings_calls"
    d.mkdir(parents=True)
    (d / "scores.parquet").write_bytes(b"not-a-real-parquet")
    assert pub.publish(data_dir=tmp_path, dry_run=False) == 0


def test_fetch_r2_noop_without_creds(monkeypatch, tmp_path):
    for var in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    from scripts import fetch_earnings_scores as fet
    assert fet.fetch(data_dir=tmp_path, dry_run=False) == 0


# --------------------------------------------------------------------------- #
# 8. 8-K fallback path selection
# --------------------------------------------------------------------------- #
def test_8k_fallback_path_selected(monkeypatch, tmp_path):
    """With no transcripts present, auto source must route to the 8-K lane and
    tag rows source='8k'."""
    _mock_reply(monkeypatch, _GOOD_JSON)

    # Fake the 8-K iterator so no network is touched.
    def fake_8k(root, limit):
        yield ({"ticker": "IBM", "quarter": "Q4", "year": 2025,
                "call_date": "2026-01-28"}, "IBM press release text ...")

    monkeypatch.setattr(eq, "_iter_8k_inputs", fake_8k)

    # auto with NO transcripts dir → uses 8-K
    n = eq.score_new(root=tmp_path, source="auto", limit=8)
    assert n == 1
    df = eq.load_scores(tmp_path)
    assert df.iloc[0]["source"] == "8k"
    assert df.iloc[0]["ticker"] == "IBM"


def test_8k_explicit_source(monkeypatch, tmp_path):
    _mock_reply(monkeypatch, _GOOD_JSON)

    def fake_8k(root, limit):
        yield ({"ticker": "GE", "quarter": "Q3", "year": 2025,
                "call_date": "2025-10-20"}, "GE press release text ...")

    monkeypatch.setattr(eq, "_iter_8k_inputs", fake_8k)
    n = eq.score_new(root=tmp_path, source="8k", limit=5)
    assert n == 1
    assert eq.load_scores(tmp_path).iloc[0]["source"] == "8k"


def test_transcript_preferred_over_8k(monkeypatch, tmp_path):
    """auto with transcripts present must NOT fall to 8-K."""
    _mock_reply(monkeypatch, _GOOD_JSON)
    tdir = tmp_path / "data" / "earnings_calls" / "transcripts"
    tdir.mkdir(parents=True)
    (tdir / "AAPL.json").write_text(json.dumps({
        "ticker": "AAPL", "quarter": "Q1", "year": 2026, "text": "body"}),
        encoding="utf-8")

    called = {"8k": False}

    def fake_8k(root, limit):
        called["8k"] = True
        return
        yield  # pragma: no cover

    monkeypatch.setattr(eq, "_iter_8k_inputs", fake_8k)
    n = eq.score_new(root=tmp_path, source="auto", limit=8)
    assert n == 1
    assert eq.load_scores(tmp_path).iloc[0]["source"] == "transcript"
    assert called["8k"] is False               # 8-K lane not touched


# --------------------------------------------------------------------------- #
# 9. helpers
# --------------------------------------------------------------------------- #
def test_source_sha256_deterministic():
    a = eq.source_sha256("hello world")
    b = eq.source_sha256("hello world")
    c = eq.source_sha256("HELLO WORLD")
    assert a == b
    assert a != c
    assert len(a) == 64


def test_quarter_from_date():
    assert eq._quarter_from_date("2026-02-15") == "Q4"
    assert eq._quarter_from_date("2026-05-01") == "Q1"
    assert eq._quarter_from_date("2026-08-01") == "Q2"
    assert eq._quarter_from_date("2026-11-01") == "Q3"
    assert eq._quarter_from_date("garbage") is None


def test_html_to_text_strips_tags():
    html = "<html><body><p>Revenue <b>up 20%</b></p><script>window.evil=1</script></body></html>"
    txt = eq._html_to_text(html)
    assert "Revenue up 20%" in txt
    assert "<" not in txt              # all tags stripped
    assert "window.evil" not in txt    # script body removed entirely


# --------------------------------------------------------------------------- #
# 10. Every tone word the page can render has a real ZH twin (FIX 5).
# --------------------------------------------------------------------------- #
def test_every_tone_word_has_zh_twin():
    """For every tone word the LLM scorer can emit (engine.earnings_qual._TONE_WORDS)
    plus the deterministic stage-analysis tone words {upbeat, steady, downbeat},
    engine.i18n.tr(word) must return a real Chinese twin (tr(word) != word)."""
    from engine import i18n  # noqa: PLC0415

    words = set(eq._TONE_WORDS) | {"upbeat", "steady", "downbeat"}
    missing = [w for w in sorted(words) if i18n.tr(w) == w]
    assert not missing, f"tone words without a ZH twin in i18n.LEX: {missing}"
