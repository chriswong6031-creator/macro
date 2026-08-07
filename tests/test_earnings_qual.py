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


def test_openai_compat_disables_thinking_for_qwen3_only(monkeypatch):
    payloads: list[dict] = []

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "{}"}}]}

    class _Requests:
        @staticmethod
        def post(_url, *, headers, json, timeout):
            assert headers["Content-Type"] == "application/json"
            assert timeout == (5.0, 120.0)
            payloads.append(json)
            return _Response()

    monkeypatch.setitem(sys.modules, "requests", _Requests)
    for model in ("qwen3:14b", "registry.local/Qwen3-14B"):
        text, reason = eq._call_openai_compat(
            "system",
            "return json",
            {"base_url": "http://127.0.0.1:11435/v1", "model": model},
            max_tokens=32,
        )
        assert text == "{}" and reason is None
        assert payloads[-1]["messages"][1]["content"].endswith("\n\n/no_think")
        assert payloads[-1]["reasoning_effort"] == "none"

    eq._call_openai_compat(
        "system",
        "return json /no_think",
        {"base_url": "http://127.0.0.1:11435/v1", "model": "qwen3:14b"},
        max_tokens=32,
    )
    assert payloads[-1]["messages"][1]["content"].count("/no_think") == 1

    eq._call_openai_compat(
        "system",
        "return json",
        {"base_url": "http://127.0.0.1:11435/v1", "model": "other-model"},
        max_tokens=32,
    )
    assert payloads[-1]["messages"][1]["content"] == "return json"
    assert "reasoning_effort" not in payloads[-1]


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


def test_score_text_persists_source_and_prompt_lineage(monkeypatch):
    obj = dict(_GOOD_JSON)
    obj["summary"] = "Revenue grew while management maintained guidance."
    _mock_reply(monkeypatch, obj)
    row = eq.score_text(
        "Some earnings call text.",
        "AAPL",
        "Q3",
        2026,
        call_date="2026-07-30",
        source_record_id="defeatbeta:AAPL:2026Q3",
        source_updated_at="2026-08-01T00:00:00Z",
        source_url="https://app.mastermind-x.com/data/tx/AAPL/2026Q3.json.gz",
        source_revision_sha256="revision-123",
    )
    assert row["source_record_id"] == "defeatbeta:AAPL:2026Q3"
    assert row["source_updated_at"] == "2026-08-01T00:00:00Z"
    assert row["source_url"] == (
        "https://app.mastermind-x.com/data/tx/AAPL/2026Q3.json.gz"
    )
    assert row["source_revision_sha256"] == "revision-123"
    assert row["prompt_version"]
    assert row["analysis_schema_version"]
    assert row["summary"].startswith("Revenue grew")


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
    row = eq.score_text(
        "txt",
        "X",
        "Q1",
        2026,
        provider_cfg={"provider_order": ["openai_compat"]},
    )
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


def test_incomplete_local_reply_falls_through_to_deepseek(monkeypatch):
    calls: list[str] = []

    def fake_dispatch(system, user, cfg, provider_cfg, *, max_tokens):
        provider = provider_cfg["provider_order"][0]
        calls.append(provider)
        if provider == "openai_compat":
            return "{}", None, provider
        return json.dumps(_GOOD_JSON), None, provider

    monkeypatch.setattr(eq, "_dispatch", fake_dispatch)
    row = eq.score_text(
        "txt",
        "NVDA",
        "Q1",
        2026,
        provider_cfg={"provider_order": ["openai_compat", "deepseek"]},
    )
    assert calls == ["openai_compat", "openai_compat", "deepseek"]
    assert row["model"] == "deepseek"
    assert row["degraded_reason"] is None
    assert row["performance"] == pytest.approx(8.5)
    # The rung that answered with unusable JSON is a failed rung: the row is
    # healthy, but it was NOT produced locally.
    assert row["provider_fallback_reason"] == "openai_compat:incomplete_schema"


# --------------------------------------------------------------------------- #
# R0-A: a successful fallback must not look like a healthy primary-rung run.
#
# The live defect: the launchd plist exported EARNINGS_LLM_MODEL=qwen3:14b while
# http://127.0.0.1:11435/v1 served only qwen3.5:9b, so every openai_compat call
# 404'd and DeepSeek quietly answered instead.  Because the earlier rung's reason
# was dropped the moment a later rung succeeded, 741 rows recorded
# model=deepseek and were byte-identical to a clean run.
# --------------------------------------------------------------------------- #
def test_transport_failure_then_success_records_the_first_failing_rung(monkeypatch):
    calls: list[str] = []

    def fake_dispatch(system, user, cfg, provider_cfg, *, max_tokens):
        provider = provider_cfg["provider_order"][0]
        calls.append(provider)
        if provider == "openai_compat":
            # Exactly what a served-model mismatch produces upstream.
            return None, "openai_compat_http_404", None
        return json.dumps(_GOOD_JSON), None, provider

    monkeypatch.setattr(eq, "_dispatch", fake_dispatch)
    row = eq.score_text(
        "txt",
        "AAPL",
        "Q3",
        2026,
        provider_cfg={"provider_order": ["openai_compat", "deepseek"]},
    )

    assert calls == ["openai_compat", "deepseek"]
    # The row scored, so it is NOT degraded — degraded_reason keeps its meaning.
    assert row["degraded_reason"] is None
    assert row["sentiment"] == pytest.approx(0.7)
    # ...but the receipt now names the rung that failed AND why, next to the
    # rung that actually answered.
    assert row["provider_fallback_reason"] == "openai_compat:openai_compat_http_404"
    assert row["model"] == "deepseek"


def test_first_rung_success_records_no_fallback_reason(monkeypatch):
    _mock_reply(monkeypatch, _GOOD_JSON)
    row = eq.score_text(
        "txt",
        "AAPL",
        "Q3",
        2026,
        provider_cfg={"provider_order": ["openai_compat", "deepseek"]},
    )
    # No false alarm: nothing fell back, so the field stays empty.
    assert row["provider_fallback_reason"] is None
    assert row["model"] == "openai_compat"
    assert row["degraded_reason"] is None


def test_only_the_first_failing_rung_is_recorded(monkeypatch):
    """Two failures before a success still name the FIRST one."""

    def fake_dispatch(system, user, cfg, provider_cfg, *, max_tokens):
        provider = provider_cfg["provider_order"][0]
        if provider == "openai_compat":
            return None, "openai_compat_http_404", None
        if provider == "kimi":
            return None, "kimi_http_401", None
        return json.dumps(_GOOD_JSON), None, provider

    monkeypatch.setattr(eq, "_dispatch", fake_dispatch)
    row = eq.score_text(
        "txt",
        "AAPL",
        "Q3",
        2026,
        provider_cfg={"provider_order": ["openai_compat", "kimi", "deepseek"]},
    )
    assert row["provider_fallback_reason"] == "openai_compat:openai_compat_http_404"
    assert row["model"] == "deepseek"
    assert row["degraded_reason"] is None


def test_all_rungs_failed_keeps_prior_degraded_semantics(monkeypatch):
    """The all-failed path is unchanged; the receipt is purely additive."""

    def fake_dispatch(system, user, cfg, provider_cfg, *, max_tokens):
        provider = provider_cfg["provider_order"][0]
        return None, f"{provider}_http_404", None

    monkeypatch.setattr(eq, "_dispatch", fake_dispatch)
    row = eq.score_text(
        "txt",
        "AAPL",
        "Q3",
        2026,
        provider_cfg={"provider_order": ["openai_compat", "deepseek"]},
    )
    # Same contract as before R0-A: last reason wins, no model, no scores.
    assert row["degraded_reason"] == "deepseek_http_404"
    assert row["model"] is None
    assert row["sentiment"] is None
    assert row["provider_fallback_reason"] == "openai_compat:openai_compat_http_404"


def test_fallback_reason_is_stored_and_absent_column_still_loads(tmp_path):
    """Additive column: a pre-R0-A parquet must still load, merge and upsert."""

    import pandas as pd

    assert "provider_fallback_reason" in eq._STORE_COLUMNS

    legacy_columns = [
        c for c in eq._STORE_COLUMNS if c != "provider_fallback_reason"
    ]
    legacy = {
        "ticker": "MSFT", "quarter": "Q3", "year": 2026,
        "call_date": "2026-07-30", "source": "transcript", "model": "qwen",
        "sentiment": 0.4, "performance": 7.0, "confidence": 0.8,
        "tone_word": "steady", "positive_highlights": "[]",
        "negative_highlights": "[]", "tags": "[]",
        "source_sha256": "legacy-sha", "scored_at": "2026-08-01T00:00:00Z",
        "source_record_id": "defeatbeta:MSFT:2026Q3",
        "is_context_only": True, "degraded_reason": None,
    }
    store = eq.store_path(tmp_path)
    store.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{c: legacy.get(c) for c in legacy_columns}], columns=legacy_columns
    ).to_parquet(store, index=False)

    fresh = {
        "ticker": "AAPL", "quarter": "Q3", "year": 2026,
        "call_date": "2026-07-30", "source": "transcript", "model": "deepseek",
        "sentiment": 0.4, "performance": 7.0, "confidence": 0.8,
        "tone_word": "steady", "positive_highlights": [],
        "negative_highlights": [], "tags": [], "source_sha256": "fresh-sha",
        "scored_at": "2026-08-02T00:00:00Z",
        "source_record_id": "defeatbeta:AAPL:2026Q3",
        "is_context_only": True, "degraded_reason": None,
        "provider_fallback_reason": "openai_compat:openai_compat_http_404",
    }
    assert eq.upsert_scores([fresh], root=tmp_path) == 1

    stored = eq.load_scores(tmp_path)
    assert set(stored["ticker"]) == {"MSFT", "AAPL"}
    by_ticker = stored.set_index("ticker")["provider_fallback_reason"]
    assert by_ticker["AAPL"] == "openai_compat:openai_compat_http_404"
    # The legacy row backfills to null rather than failing the read.
    assert pd.isna(by_ticker["MSFT"]) or by_ticker["MSFT"] is None


def test_llm_auth_rung_disables_implicit_codex(monkeypatch):
    from engine import llm_auth

    captured: dict = {}

    def fake_build(cfg, **_kwargs):
        captured.update(cfg)
        return []

    monkeypatch.setattr(llm_auth, "build_providers", fake_build)
    text, reason = eq._call_llm_auth(
        "system", "user", {}, "deepseek", max_tokens=100
    )
    assert text is None and reason == "no_provider"
    assert captured["provider_order"] == ["deepseek"]
    assert captured["codex_provider"] is False


def test_codex_subscription_is_available_only_as_explicit_rung(monkeypatch):
    calls: list[str] = []

    def fake_llm(system, user, cfg, provider_name, *, max_tokens):
        calls.append(provider_name)
        return json.dumps(_GOOD_JSON), None

    monkeypatch.setattr(eq, "_call_llm_auth", fake_llm)
    row = eq.score_text(
        "txt",
        "AAPL",
        "Q3",
        2026,
        provider_cfg={"provider_order": ["codex"]},
    )
    assert calls == ["codex"]
    assert row["model"] == "codex"
    assert row["degraded_reason"] is None


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


def test_upsert_uses_source_record_id_before_legacy_quarter_key(tmp_path):
    base = {
        "ticker": "CLS", "quarter": "Q2", "year": 2026,
        "call_date": "2026-07-01", "source": "transcript", "model": "qwen",
        "sentiment": 0.1, "performance": 5.0, "confidence": 0.5,
        "tone_word": "steady", "positive_highlights": [],
        "negative_highlights": [], "tags": [], "scored_at": "2026-07-01T00:00:00Z",
        "is_context_only": True, "degraded_reason": None,
    }
    first = dict(base, source_record_id="source:CLS:first", source_sha256="sha-first")
    second = dict(base, source_record_id="source:CLS:second", source_sha256="sha-second")
    assert eq.upsert_scores([first, second], root=tmp_path) == 2
    df = eq.load_scores(tmp_path)
    assert len(df) == 2
    assert set(df["source_record_id"]) == {"source:CLS:first", "source:CLS:second"}


def test_completion_ledger_is_record_scoped_not_global_text_scoped(tmp_path):
    base = {
        "quarter": "Q2", "year": 2026, "call_date": "2026-07-01",
        "source": "transcript", "model": "qwen", "sentiment": 0.1,
        "performance": 5.0, "confidence": 0.5, "tone_word": "steady",
        "positive_highlights": [], "negative_highlights": [], "tags": [],
        "source_sha256": "identical-rendered-text",
        "scored_at": "2026-07-01T00:00:00Z", "is_context_only": True,
        "degraded_reason": None,
    }
    eq.upsert_scores([
        dict(base, ticker="AAA", source_record_id="source:AAA:2026Q2"),
        dict(base, ticker="BBB", source_record_id="source:BBB:2026Q2"),
    ], root=tmp_path)
    assert eq._completed_record_shas(tmp_path) == {
        "source:AAA:2026Q2": "identical-rendered-text",
        "source:BBB:2026Q2": "identical-rendered-text",
    }


def test_completion_ledger_prefers_upstream_revision_hash(tmp_path):
    row = {
        "ticker": "AAPL", "quarter": "Q3", "year": 2026,
        "call_date": "2026-07-30", "source": "transcript", "model": "qwen",
        "sentiment": 0.4, "performance": 7.0, "confidence": 0.8,
        "tone_word": "steady", "positive_highlights": [],
        "negative_highlights": [], "tags": [],
        "source_sha256": "same-rendered-text",
        "source_revision_sha256": "metadata-aware-revision",
        "scored_at": "2026-08-01T00:00:00Z",
        "source_record_id": "defeatbeta:AAPL:2026Q3",
        "is_context_only": True, "degraded_reason": None,
    }
    eq.upsert_scores([row], root=tmp_path)
    assert eq._completed_record_shas(tmp_path) == {
        "defeatbeta:AAPL:2026Q3": "metadata-aware-revision"
    }


def test_degraded_sha_is_not_marked_seen(tmp_path):
    row = {
        "ticker": "AAPL", "quarter": "Q3", "year": 2026,
        "call_date": "2026-07-30", "source": "transcript", "model": None,
        "sentiment": None, "performance": None, "confidence": None,
        "tone_word": None, "positive_highlights": [], "negative_highlights": [],
        "tags": [], "source_sha256": "retry-me", "scored_at": "2026-08-01T00:00:00Z",
        "source_record_id": "defeatbeta:AAPL:2026Q3", "is_context_only": True,
        "degraded_reason": "openai_compat_error",
    }
    eq.upsert_scores([row], root=tmp_path)
    assert "retry-me" not in eq._seen_shas(tmp_path)


def test_degraded_revision_cannot_replace_healthy_source_record(tmp_path):
    healthy = {
        "ticker": "AAPL", "quarter": "Q3", "year": 2026,
        "call_date": "2026-07-30", "source": "transcript", "model": "qwen",
        "sentiment": 0.4, "performance": 7.0, "confidence": 0.8,
        "tone_word": "steady", "positive_highlights": [],
        "negative_highlights": [], "tags": [], "source_sha256": "old-good",
        "scored_at": "2026-08-01T00:00:00Z",
        "source_record_id": "defeatbeta:AAPL:2026Q3",
        "is_context_only": True, "degraded_reason": None,
    }
    failed_revision = dict(
        healthy,
        source_sha256="new-failed",
        sentiment=None,
        performance=None,
        confidence=None,
        tone_word=None,
        degraded_reason="openai_compat_error",
    )
    eq.upsert_scores([healthy], root=tmp_path)
    eq.upsert_scores([failed_revision], root=tmp_path)
    stored = eq.load_scores(tmp_path)
    assert len(stored) == 1
    assert stored.iloc[0]["source_sha256"] == "old-good"
    assert float(stored.iloc[0]["performance"]) == pytest.approx(7.0)


def test_multiple_producer_upserts_survive_stale_transport_manifest(tmp_path):
    from scripts.publish_earnings_r2 import _synth_manifest

    first = {
        "ticker": "AAPL", "quarter": "Q3", "year": 2026,
        "call_date": "2026-07-30", "source": "transcript", "model": "qwen",
        "sentiment": 0.4, "performance": 7.0, "confidence": 0.8,
        "tone_word": "steady", "positive_highlights": [],
        "negative_highlights": [], "tags": [], "source_sha256": "first",
        "scored_at": "2026-08-01T00:00:00Z",
        "source_record_id": "defeatbeta:AAPL:2026Q3",
        "is_context_only": True, "degraded_reason": None,
    }
    second = dict(
        first,
        ticker="MSFT",
        source_sha256="second",
        source_record_id="defeatbeta:MSFT:2026Q3",
        scored_at="2026-08-01T00:01:00Z",
    )
    eq.upsert_scores([first], root=tmp_path)
    scores_path = eq.store_path(tmp_path)
    manifest_path = scores_path.parent / "manifest.json"
    manifest_path.write_text(json.dumps(_synth_manifest(scores_path)), encoding="utf-8")

    # The next producer write reads the mutable parquet directly, then removes
    # the now-stale commit marker until the publisher regenerates it.
    eq.upsert_scores([second], root=tmp_path)
    assert not manifest_path.exists()
    stored = eq.load_scores(tmp_path)
    assert set(stored["ticker"]) == {"AAPL", "MSFT"}


def test_parseable_but_incomplete_json_is_retryable(monkeypatch):
    monkeypatch.setattr(
        eq,
        "_dispatch",
        lambda *a, **k: ('{"sentiment": 0.2}', None, "test-model"),
    )
    row = eq.score_text("Revenue rose.", "AAPL", "Q3", 2026)
    assert row["degraded_reason"] == "incomplete_schema"
    assert row["source_sha256"]


def test_bounded_transcript_keeps_head_and_qa_tail():
    text = "HEAD-FACT\n" + ("middle " * 100) + "\nQ&A-TAIL-FACT"
    bounded = eq._bounded_transcript_text(text, max_chars=120, tail_chars=30)
    assert bounded.startswith("HEAD-FACT")
    assert bounded.endswith("Q&A-TAIL-FACT")
    assert "middle of transcript omitted" in bounded
    assert len(bounded) <= 120


# --------------------------------------------------------------------------- #
# 5b. Per-rung prompt bounds (R0-A2)
#
# The rungs need not share a context window, so the prompt is built PER RUNG.
# A rung whose provider block carries its own max_chars/tail_chars gets that
# bound; every other rung inherits the global 24,000/8,000 and must NOT be
# degraded to the smallest window on the ladder.  This is the lever for an
# endpoint configured below the global transcript budget: such a server answers
# HTTP 200 with prose instead of JSON rather than erroring, so a prompt built
# ONCE before the waterfall falls through to a metered cloud provider on every
# real transcript.
#
# NO rung ships with a per-rung bound.  #4784 capped openai_compat at 8,000
# chars while the host ran Ollama's 4,096-token default; OLLAMA_CONTEXT_LENGTH
# is now 32,768 there and the local rung reads the full global budget (measured
# 2026-08-06: 24,000 chars -> 8,797 prompt_tokens on prose / 14,156 token-dense,
# finish_reason stop, usable JSON).  The tests below therefore configure the
# per-rung bound EXPLICITLY to exercise the mechanism, and pin separately that
# the shipped config restates no local default.
# --------------------------------------------------------------------------- #
_PROMPT_ENVELOPE = len(eq._build_user_prompt("NVDA", "Q3", 2026, "transcript", ""))


def _prompt_body_chars(prompt: str) -> int:
    """Recover the transcript-body length from a built user prompt."""
    return len(prompt.removesuffix(eq._RETRY_SUFFIX)) - _PROMPT_ENVELOPE


def _long_transcript() -> str:
    text = (
        "HEAD-FACT: revenue of $12.4B.\n"
        + ("Prepared remarks filler about the quarter. " * 2000)
        + "\nOperator: We will now begin the question-and-answer session.\n"
        "ANALYST-TAIL-FACT: what is the FY27 margin bridge?"
    )
    assert len(text) > 24000
    return text


def _cfg_with_local_bound(max_chars: int, tail_chars: int) -> dict:
    """Shipped config + an EXPLICIT per-rung bound on openai_compat.

    The shipped config carries no local bound (the endpoint reads the full
    global budget), so a test of the per-rung mechanism must configure one
    itself rather than lean on a default that is no longer there.
    """
    cfg = eq.load_config()
    cfg["openai_compat"] = {
        **cfg["openai_compat"],
        "max_chars": max_chars,
        "tail_chars": tail_chars,
    }
    return cfg


def _capture_rung_prompts(monkeypatch) -> list[tuple[str, str]]:
    """Record (provider, user prompt) for every rung dispatch of a scoring call.

    The local rung answers the way an under-configured server does over its
    window: HTTP 200, finish_reason "stop", a markdown summary and no JSON.
    """
    seen: list[tuple[str, str]] = []

    def fake_dispatch(system, user, cfg, provider_cfg, *, max_tokens):
        provider = provider_cfg["provider_order"][0]
        seen.append((provider, user))
        if provider == "openai_compat":
            return (
                "### Q3 Financial Highlights\n\n- Revenue grew year over year.",
                None,
                provider,
            )
        return json.dumps(_GOOD_JSON), None, provider

    monkeypatch.setattr(eq, "_dispatch", fake_dispatch)
    return seen


def test_configured_rung_bound_applies_while_cloud_rung_keeps_full_text(monkeypatch):
    """THE contract: one scoring call, two prompt sizes, chosen per rung.

    The bound is configured HERE, not inherited from a shipped local default —
    that default is gone, but the mechanism it used must still work, because it
    is what makes a future server misconfiguration a config change.
    """
    seen = _capture_rung_prompts(monkeypatch)
    cfg = _cfg_with_local_bound(8000, 3000)
    local_max = int(cfg["openai_compat"]["max_chars"])
    global_max = int(cfg["max_chars"])
    assert local_max < global_max

    row = eq.score_text(
        _long_transcript(),
        "NVDA",
        "Q3",
        2026,
        cfg=cfg,
        provider_cfg={"provider_order": ["openai_compat", "deepseek"]},
    )

    local_prompts = [u for name, u in seen if name == "openai_compat"]
    cloud_prompts = [u for name, u in seen if name == "deepseek"]
    assert local_prompts and cloud_prompts

    # The local rung is bounded to ITS window...
    for prompt in local_prompts:
        assert _prompt_body_chars(prompt) == local_max
    # ...and the cloud rung in the SAME call still gets the full budget.
    for prompt in cloud_prompts:
        assert _prompt_body_chars(prompt) == global_max

    # Waterfall behavior is unchanged: local prose -> retry -> cloud JSON.
    assert [name for name, _ in seen] == [
        "openai_compat",
        "openai_compat",
        "deepseek",
    ]
    assert row["model"] == "deepseek"
    assert row["degraded_reason"] is None


def test_configured_rung_bound_preserves_the_qa_tail(monkeypatch):
    """A narrowed rung bound must still carry the Q&A tail — that is its point."""
    seen = _capture_rung_prompts(monkeypatch)
    cfg = _cfg_with_local_bound(8000, 3000)
    local_max = int(cfg["openai_compat"]["max_chars"])
    local_tail = int(cfg["openai_compat"]["tail_chars"])
    # tail_chars must not be silently clamped by _bounded_transcript_text's
    # max_chars//2 ceiling, or the config would state a bound it does not use.
    assert 0 < local_tail <= local_max // 2

    eq.score_text(
        _long_transcript(),
        "NVDA",
        "Q3",
        2026,
        cfg=cfg,
        provider_cfg={"provider_order": ["openai_compat"]},
    )

    local_prompt = next(u for name, u in seen if name == "openai_compat")
    assert _prompt_body_chars(local_prompt) == local_max
    assert "HEAD-FACT: revenue of $12.4B." in local_prompt
    assert "middle of transcript omitted" in local_prompt
    assert "question-and-answer session" in local_prompt
    assert "ANALYST-TAIL-FACT: what is the FY27 margin bridge?" in local_prompt


def test_rung_text_bounds_are_config_driven_with_global_fallback():
    cfg = {
        "max_chars": 24000,
        "tail_chars": 8000,
        "openai_compat": {"max_chars": 8000, "tail_chars": 3000},
        "kimi": {"model": "kimi-k2.6"},
    }
    # a provider block with its own bound uses it
    assert eq._rung_text_bounds(cfg, {}, "openai_compat") == (8000, 3000)
    # a provider block without one, and a provider with no block at all, both
    # inherit the global bound — cloud rungs are untouched by this mechanism
    assert eq._rung_text_bounds(cfg, {}, "kimi") == (24000, 8000)
    assert eq._rung_text_bounds(cfg, {}, "deepseek") == (24000, 8000)
    assert eq._rung_text_bounds(cfg, {}, "anthropic") == (24000, 8000)
    # the worker's per-run override beats the config file, as in _dispatch
    assert eq._rung_text_bounds(
        cfg, {"openai_compat": {"max_chars": 6000}}, "openai_compat"
    ) == (6000, 3000)
    # partial/garbage config falls back instead of raising
    assert eq._rung_text_bounds({}, {}, "openai_compat") == (24000, 8000)
    assert eq._rung_text_bounds(
        {"max_chars": 24000, "tail_chars": 8000, "openai_compat": {"max_chars": "x"}},
        {},
        "openai_compat",
    ) == (24000, 8000)


def test_shipped_config_lets_the_local_rung_inherit_the_global_bound():
    """No rung ships narrowed — the local endpoint reads the full budget.

    #4784 capped openai_compat at 8,000 chars for a 4,096-token Ollama default.
    The host now sets OLLAMA_CONTEXT_LENGTH=32768 and serves 24,000 chars at
    finish_reason "stop" with usable JSON (8,797 prompt_tokens on prose, 14,156
    token-dense), so a local cap would truncate transcripts for no reason.
    Re-introducing one — in the YAML or in _DEFAULT_CFG — fails here.
    """
    cfg = eq.load_config()
    assert int(cfg["max_chars"]) == 24000
    assert int(cfg["tail_chars"]) == 8000
    assert eq._rung_text_bounds(cfg, {}, "openai_compat") == (24000, 8000)
    for cloud in ("deepseek", "kimi", "anthropic", "codex"):
        assert eq._rung_text_bounds(cfg, {}, cloud) == (24000, 8000)

    # ...and the bound must be INHERITED, not restated at the global value:
    # a restated copy silently drifts the next time the global moves.
    import yaml

    raw = yaml.safe_load(
        (eq._REPO_ROOT / "config" / "earnings_qual.yml").read_text(encoding="utf-8")
    )
    for source, block in (
        ("config/earnings_qual.yml", raw.get("openai_compat") or {}),
        ("engine.earnings_qual._DEFAULT_CFG", eq._DEFAULT_CFG["openai_compat"]),
    ):
        for key in ("max_chars", "tail_chars"):
            assert key not in block, f"{source} restates openai_compat.{key}"


def test_shipped_config_sends_the_full_global_budget_to_the_local_rung(monkeypatch):
    """End-to-end proof, on the SHIPPED config: no silent local truncation.

    The unit assertion above resolves bounds; this one checks the prompt that
    actually reaches the local endpoint, so a bound re-introduced anywhere on
    the resolution path is caught by the bytes on the wire.
    """
    seen = _capture_rung_prompts(monkeypatch)
    cfg = eq.load_config()

    eq.score_text(
        _long_transcript(),
        "NVDA",
        "Q3",
        2026,
        cfg=cfg,
        provider_cfg={"provider_order": ["openai_compat", "deepseek"]},
    )

    local_prompts = [u for name, u in seen if name == "openai_compat"]
    cloud_prompts = [u for name, u in seen if name == "deepseek"]
    assert local_prompts and cloud_prompts
    for prompt in local_prompts + cloud_prompts:
        assert _prompt_body_chars(prompt) == int(cfg["max_chars"]) == 24000


def test_server_side_prompt_truncation_is_logged(caplog):
    """A prompt_tokens count the sent prompt cannot explain must be surfaced."""
    caplog.set_level("WARNING", logger=eq.log.name)
    # 25,600 chars reported as 2,050 prompt_tokens — the measured signature.
    eq._log_prompt_truncation(25600, {"usage": {"prompt_tokens": 2050}}, "qwen3.5:9b")
    assert "TRUNCATED" in caplog.text
    assert "2050" in caplog.text
    caplog.clear()
    # A prompt that fit (10,000 chars -> 3,932 tokens) must NOT warn, nor must
    # a response that reports no usage at all.
    eq._log_prompt_truncation(10000, {"usage": {"prompt_tokens": 3932}}, "qwen3.5:9b")
    eq._log_prompt_truncation(10000, {}, "qwen3.5:9b")
    eq._log_prompt_truncation(10000, {"usage": {"prompt_tokens": None}}, "qwen3.5:9b")
    assert caplog.text == ""


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
