"""Tests for engine/entity_resolver.py — layered v0 resolver precision.

Covers: Layer-1 CN code adjacency by exchange range, Layer-2/3 curated aliases +
the 机器人 GENERIC_NOUNS guard, longest-match-first / subsumed suppression, US
alias + token + name-span resolution, CUSIP promotion, and clear_cache().
Uses crafted in-memory maps (monkeypatched) so precision is deterministic and does
not depend on the live data files.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import entity_resolver as er  # noqa: E402


# --------------------------------------------------------------------------- #
# Layer 1 — CN 6-digit code → exchange by range
# --------------------------------------------------------------------------- #
def test_cn_code_to_ticker_ranges():
    assert er.cn_code_to_ticker("600519") == "600519.SS"   # Shanghai
    assert er.cn_code_to_ticker("000001") == "000001.SZ"   # Shenzhen main
    assert er.cn_code_to_ticker("300750") == "300750.SZ"   # ChiNext
    assert er.cn_code_to_ticker("830799") == "830799.BJ"   # Beijing
    assert er.cn_code_to_ticker("12345") is None           # not 6 digits
    assert er.cn_code_to_ticker("abcdef") is None


def test_resolve_cn_bare_code_high_confidence():
    hits = er.resolve_cn("机构增持 600519 贵州茅台")
    tickers = {h["ticker"] for h in hits}
    assert "600519.SS" in tickers
    codehit = next(h for h in hits if h["ticker"] == "600519.SS")
    assert codehit["method"] == "cn_code" and codehit["confidence"] >= 0.95


# --------------------------------------------------------------------------- #
# Layers 2/3 — curated aliases + the 机器人 guard
# --------------------------------------------------------------------------- #
def _patch_cn_names(monkeypatch, mapping: dict[str, str]):
    er.clear_cache()
    monkeypatch.setattr(er, "cn_name_to_ticker", lambda: dict(mapping))
    monkeypatch.setattr(
        er, "_cn_names_by_len",
        lambda: tuple(sorted(mapping.keys(), key=len, reverse=True)))


def test_resolve_cn_alias_match(monkeypatch):
    _patch_cn_names(monkeypatch, {"贵州茅台": "600519.SS", "宁德时代": "300750.SZ"})
    hits = er.resolve_cn("贵州茅台发布一季报")
    assert hits and hits[0]["ticker"] == "600519.SS"
    assert hits[0]["method"] == "cn_alias"


def test_generic_noun_guard_blocks_bare_robot(monkeypatch):
    # 机器人 as a common noun (no adjacent code) must NOT tag 300024.
    _patch_cn_names(monkeypatch, {"机器人": "300024.SZ"})
    hits = er.resolve_cn("全球机器人产业大会在京开幕")
    assert all(h["ticker"] != "300024.SZ" for h in hits)


def test_generic_noun_tags_with_adjacent_code(monkeypatch):
    # 机器人(300024) — the code sits adjacent, so the name IS allowed to tag.
    _patch_cn_names(monkeypatch, {"机器人": "300024.SZ"})
    hits = er.resolve_cn("机器人(300024)一季度净利大增")
    assert any(h["ticker"] == "300024.SZ" for h in hits)


def test_generic_noun_lifted_and_reexported():
    # entity_resolver is the canonical home; china_news_intel re-exports it.
    assert "机器人" in er.GENERIC_NOUNS
    from engine import china_news_intel as cni
    assert er.GENERIC_NOUNS <= cni._GENERIC_NOUN_NAMES or \
        cni._GENERIC_NOUN_NAMES == er.GENERIC_NOUNS


def test_longest_match_first_subsumed_suppression(monkeypatch):
    # 中国平安 (longer) should win; 平安 (subsumed) must not double-tag a 2nd ticker.
    _patch_cn_names(monkeypatch, {"中国平安": "601318.SS", "平安": "000001.SZ"})
    hits = er.resolve_cn("中国平安发布年报")
    tickers = [h["ticker"] for h in hits]
    assert "601318.SS" in tickers
    assert "000001.SZ" not in tickers   # 平安 is subsumed by 中国平安


# --------------------------------------------------------------------------- #
# US resolution
# --------------------------------------------------------------------------- #
def test_resolve_us_megacap_alias():
    hits = er.resolve_us("Nvidia unveils new AI chip")
    assert any(h["ticker"] == "NVDA" and h["method"] == "us_alias" for h in hits)


def test_resolve_us_bare_ticker_token(monkeypatch):
    er.clear_cache()
    monkeypatch.setattr(er, "_us_known_tickers", lambda: frozenset({"AMD", "NVDA"}))
    monkeypatch.setattr(er, "_us_aliases", lambda: {})
    hits = er.resolve_us("Traders pile into $AMD ahead of earnings")
    assert any(h["ticker"] == "AMD" and h["method"] == "us_token" for h in hits)


def test_resolve_us_stopwords_not_tagged(monkeypatch):
    er.clear_cache()
    monkeypatch.setattr(er, "_us_known_tickers", lambda: frozenset({"AI", "IT"}))
    monkeypatch.setattr(er, "_us_aliases", lambda: {})
    # AI / IT are stopwords even if present in the universe.
    hits = er.resolve_us("AI IT spending rises")
    assert hits == []


def test_resolve_us_sorted_by_confidence():
    hits = er.resolve_us("Nvidia and Apple report strong results")
    confs = [h["confidence"] for h in hits]
    assert confs == sorted(confs, reverse=True)


# --------------------------------------------------------------------------- #
# Layer 5 — CUSIP
# --------------------------------------------------------------------------- #
def test_resolve_cusip_exact_and_stem(monkeypatch):
    er.clear_cache()
    monkeypatch.setattr(er, "_cusip_map", lambda: {"67066G104": "NVDA"})
    assert er.resolve_cusip("67066G104") == "NVDA"
    assert er.resolve_cusip("67066G10") == "NVDA"    # 8-char issuer stem
    assert er.resolve_cusip("00000000") is None
    assert er.resolve_cusip("") is None


def test_clear_cache_runs():
    er.clear_cache()   # must not raise even with no data
