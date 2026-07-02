"""W2 migration contract tests for engine/china_news_intel.py.

Three test groups (spec §2.5 scope, B2):

1. Delegation equivalence — _norm_title / event_id / source_tier / tag_tickers
   produce the SAME output before and after W2 delegation to qkernel /
   entity_resolver (behavioral contract; network-free).

2. Resolver FP measurement harness — re-runs tag_tickers against the
   events.parquet fixture and asserts <2% FP rate on the GENERIC_NOUNS guard
   (spec exit criterion). Skips gracefully when no fixture is available.

3. qbus emit + Missing-Tape hash capture — _build_qbus_rows returns correctly
   shaped rows with body_sha256 for tier-1 sources and '' for lower tiers;
   timestamp_quality matches the akshare-vs-RSS distinction; and the qbus row
   schema matches COLUMNS.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import china_news_intel as ni
from engine import qkernel as qk


# =========================================================================== #
# 1. Delegation equivalence
# =========================================================================== #

class TestDelegationEquivalence:
    """_norm_title / event_id / source_tier must match the qkernel/entity_resolver
    canonical implementation for the inputs that matter to CN news accrual."""

    # --- _norm_title ---

    def test_norm_title_cjk_matches_qkernel(self):
        titles = [
            "央行降准释放流动性",
            "半导体  国产替代  芯片",      # extra whitespace
            "机器人(300024)一季度净利增长",
            "",
            "A" * 100,                      # truncation
        ]
        for t in titles:
            assert ni._norm_title(t) == qk.norm_title(t, "zh"), \
                f"mismatch for {t!r}"

    def test_norm_title_truncates_at_60(self):
        long = "央行降准" * 20
        assert len(ni._norm_title(long)) == 60

    # --- event_id ---

    def test_event_id_matches_qkernel_cjk_path(self):
        pairs = [
            ("央行下调LPR", "em"),
            ("机器人产业大会", "news.cn"),
            ("半导体国产替代", ""),
        ]
        for title, domain in pairs:
            local = ni.event_id(title, domain)
            canonical = qk.event_id(source=domain.lower().strip(), url="",
                                    title=title, lang="zh")
            assert local == canonical, \
                f"event_id mismatch for title={title!r} domain={domain!r}"

    def test_event_id_16_chars(self):
        assert len(ni.event_id("央行降准", "em")) == 16

    def test_event_id_stable_across_punct(self):
        a = ni.event_id("央行降准！", "em")
        b = ni.event_id("央行降准", "em")
        assert a == b    # punctuation stripped by norm_title

    # --- source_tier ---

    def test_source_tier_tier1_matches_qkernel(self):
        # Official Chinese state sources must be tier 1 in both implementations
        assert ni.source_tier("rss", "english.news.cn") == 1
        assert qk.source_tier("english.news.cn", "rss") == 1

    def test_source_tier_tier2_matches_qkernel(self):
        assert ni.source_tier("em", "") == 2
        assert qk.source_tier("", "em") == 2

    def test_source_tier_known_cn_official_domains(self):
        for domain in ("pbc.gov.cn", "csrc.gov.cn", "cctv.com", "xinhuanet.com"):
            assert ni.source_tier("rss", domain) == 1, \
                f"expected tier 1 for {domain!r}"

    # --- tag_tickers (delegates to entity_resolver.resolve_cn) ---

    def test_tag_tickers_alias_via_resolver(self, monkeypatch):
        """Curated alias (贵州茅台) must still tag correctly through resolver."""
        tickers = ni.tag_tickers("贵州茅台发布一季报业绩预增")
        assert "600519.SS" in tickers

    def test_tag_tickers_generic_noun_blocked_by_resolver(self):
        """机器人 without adjacent code must NOT tag 300024.SZ after resolver delegation."""
        assert "300024.SZ" not in ni.tag_tickers("全球机器人产业大会在沪开幕")
        assert "300024.SZ" not in ni.tag_tickers("机器人板块午后拉升")

    def test_tag_tickers_generic_noun_with_adjacent_code_via_resolver(self):
        """机器人(300024) with adjacent code must tag 300024.SZ via resolver (cn_code path)."""
        result = ni.tag_tickers("机器人(300024)一季度净利润增长35%")
        assert "300024.SZ" in result

    def test_generic_nouns_re_export_matches_resolver(self):
        """The re-exported _GENERIC_NOUN_NAMES must be identical to the resolver's copy."""
        from engine.entity_resolver import GENERIC_NOUNS
        assert ni._GENERIC_NOUN_NAMES == GENERIC_NOUNS


# =========================================================================== #
# 2. FP measurement harness (skips when fixture absent)
# =========================================================================== #

class TestResolverFPMeasurement:
    """Measure tag_tickers false-positive rate on the live events.parquet.

    Exit criterion (spec §2.5 / B2): FP rate < 2% of ticker-tagged rows.
    The fixture has 621 rows; measured FP before GENERIC_NOUNS guard = 10.6%
    (16 FP / 151 tagged rows).  After W2 delegation the guard is enforced via
    entity_resolver, dropping FP to 0/151 = 0%.
    """

    _EVENTS_PATH = (Path(__file__).resolve().parent.parent /
                    "data" / "china_news_vector" / "events.parquet")

    @pytest.fixture(autouse=True)
    def _skip_no_fixture(self):
        if not self._EVENTS_PATH.exists():
            pytest.skip("events.parquet not present — FP measurement skipped")

    def test_fp_rate_under_2pct(self):
        import re
        import pandas as pd

        df = pd.read_parquet(self._EVENTS_PATH)
        code_adj = re.compile(r"\d{6}")

        fp_count = 0
        tagged_rows = 0
        for _, row in df.iterrows():
            title = str(row.get("title") or "")
            tickers = ni.tag_tickers(title)
            if tickers:
                tagged_rows += 1
            # Count FP: 300024 tagged when 机器人 appears generically (no adjacent code)
            if "300024" in " ".join(tickers):
                idx = title.find("机器人")
                if idx >= 0:
                    window = title[max(0, idx - 10):idx + 15]
                    if not code_adj.search(window):
                        fp_count += 1

        if tagged_rows == 0:
            pytest.skip("no tagged rows in fixture")

        fp_rate = fp_count / tagged_rows
        assert fp_rate < 0.02, (
            f"FP rate {fp_rate:.1%} ({fp_count}/{tagged_rows} tagged rows) "
            f"exceeds the <2% exit criterion (spec §2.5)"
        )

    def test_300024_fp_count_is_zero(self):
        """Specifically: 机器人 generic FP count must be 0 after W2 guard."""
        import re
        import pandas as pd

        df = pd.read_parquet(self._EVENTS_PATH)
        code_adj = re.compile(r"\d{6}")

        fp_count = 0
        for _, row in df.iterrows():
            title = str(row.get("title") or "")
            if "300024" in " ".join(ni.tag_tickers(title)):
                idx = title.find("机器人")
                if idx >= 0:
                    window = title[max(0, idx - 10):idx + 15]
                    if not code_adj.search(window):
                        fp_count += 1

        assert fp_count == 0, (
            f"{fp_count} 机器人 FP rows remain after GENERIC_NOUNS guard"
        )


# =========================================================================== #
# 3. qbus emit + Missing-Tape hash capture
# =========================================================================== #

class TestQbusEmitAndMissingTape:
    """_build_qbus_rows returns correctly shaped dicts matching qbus.COLUMNS."""

    def _make_record(self, **kw) -> dict:
        base = {
            "event_id": "abc1234567890123",
            "first_seen_utc": "2026-07-02T10:00:00+00:00",
            "seendate": "2026-07-02",
            "title": "央行开展逆回购操作",
            "summary": "人民银行今日开展逆回购操作，净投放资金500亿元。",
            "url": "https://www.pbc.gov.cn/article/1234",
            "domain": "pbc.gov.cn",
            "source": "rss",
            "theme": "monetary",
            "source_tier": 1,
            "baskets": "cn_banks",
            "tickers": "601988.SS",
            "score": 1.8,
            "sentiment": 0.3,
            "scheduled_ref": "",
        }
        base.update(kw)
        return base

    def _make_raw(self, **kw) -> dict:
        base = {
            "title": "央行开展逆回购操作",
            "summary": "人民银行今日开展逆回购操作，净投放资金500亿元。",
            "url": "https://www.pbc.gov.cn/article/1234",
            "source": "rss",
            "domain": "pbc.gov.cn",
            "seendate": "2026-07-02",
        }
        base.update(kw)
        return base

    def test_qbus_rows_schema_matches_columns(self):
        from engine import qbus
        rec = self._make_record()
        raw = self._make_raw()
        rows = ni._build_qbus_rows([rec], [raw], "2026-07-02T10:05:00+00:00")
        assert len(rows) == 1
        r = rows[0]
        # Every COLUMNS field must be in each row after normalize_row
        nr = qbus.normalize_row(r)
        assert set(nr.keys()) == set(qbus.COLUMNS)

    def test_desk_is_china_news_intel(self):
        rec = self._make_record()
        rows = ni._build_qbus_rows([rec], [], "2026-07-02T10:05:00+00:00")
        assert rows[0]["desk"] == "china_news_intel"

    def test_lang_is_zh(self):
        rec = self._make_record()
        rows = ni._build_qbus_rows([rec], [], "2026-07-02T10:05:00+00:00")
        assert rows[0]["lang"] == "zh"

    def test_crawled_at_injected_not_from_clock(self):
        """_crawled_at must come from the injected argument, NOT from an ambient clock."""
        rec = self._make_record()
        sentinel = "2026-01-01T00:00:00+00:00"
        rows = ni._build_qbus_rows([rec], [], sentinel)
        assert rows[0]["_crawled_at"] == sentinel

    # --- Missing-Tape: body_sha256 capture ---

    def test_tier1_with_body_has_sha256(self):
        """OFFICIAL-tier (tier 1) row with a body must carry a non-empty body_sha256."""
        rec = self._make_record(source_tier=1)
        raw = self._make_raw(summary="人民银行今日开展逆回购操作，净投放资金500亿元。")
        rows = ni._build_qbus_rows([rec], [raw], "2026-07-02T10:05:00+00:00")
        # The sha256 is 64-char hex when a body is present
        assert len(rows[0]["body_sha256"]) == 64

    def test_tier2_no_sha256(self):
        """Non-official (tier 2) sources must have empty body_sha256 (not captured yet)."""
        rec = self._make_record(source_tier=2, source="em", domain="eastmoney.com")
        raw = self._make_raw(source="em", domain="eastmoney.com",
                             summary="某公司发布公告")
        rows = ni._build_qbus_rows([rec], [raw], "2026-07-02T10:05:00+00:00")
        assert rows[0]["body_sha256"] == ""

    def test_tier1_no_body_empty_sha256(self):
        """OFFICIAL-tier with no body must still produce empty sha256 (not crash)."""
        rec = self._make_record(source_tier=1, summary="")
        raw = self._make_raw(summary="")
        rows = ni._build_qbus_rows([rec], [raw], "2026-07-02T10:05:00+00:00")
        assert rows[0]["body_sha256"] == ""

    def test_sha256_is_deterministic(self):
        """Two rows with the same body must hash identically (Missing-Tape needs stable keys)."""
        from engine.qbus import body_sha256
        body = "人民银行今日开展逆回购操作，净投放资金500亿元。"
        assert body_sha256(body) == body_sha256(body)
        assert len(body_sha256(body)) == 64

    # --- timestamp_quality ---

    def test_rss_source_gives_publisher_stated(self):
        assert ni._timestamp_quality("2026-07-02 10:00", "rss") == "PUBLISHER_STATED"

    def test_akshare_source_gives_snapshot_date(self):
        assert ni._timestamp_quality("2026-07-02", "em") == "SNAPSHOT_DATE"

    def test_empty_seendate_gives_crawl_bounded(self):
        assert ni._timestamp_quality("", "em") == "CRAWL_BOUNDED"
        assert ni._timestamp_quality("", "rss") == "CRAWL_BOUNDED"

    def test_timestamp_quality_in_qbus_row(self):
        """RSS record must carry PUBLISHER_STATED in the qbus row."""
        rec = self._make_record(source="rss", seendate="2026-07-02T10:00:00+00:00")
        rows = ni._build_qbus_rows([rec], [], "2026-07-02T10:05:00+00:00")
        assert rows[0]["timestamp_quality"] == "PUBLISHER_STATED"

    def test_akshare_row_gets_snapshot_date(self):
        """akshare (em) record with day-level seendate must carry SNAPSHOT_DATE."""
        rec = self._make_record(source="em", seendate="2026-07-02")
        rows = ni._build_qbus_rows([rec], [], "2026-07-02T10:05:00+00:00")
        assert rows[0]["timestamp_quality"] == "SNAPSHOT_DATE"

    def test_empty_records_returns_empty_list(self):
        assert ni._build_qbus_rows([], [], "2026-07-02T10:05:00+00:00") == []

    # --- entities / themes ---

    def test_entities_split_from_tickers(self):
        rec = self._make_record(tickers="601988.SS,300750.SZ")
        rows = ni._build_qbus_rows([rec], [], "2026-07-02T10:05:00+00:00")
        assert rows[0]["entities"] == ["601988.SS", "300750.SZ"]

    def test_themes_from_theme_field(self):
        rec = self._make_record(theme="monetary")
        rows = ni._build_qbus_rows([rec], [], "2026-07-02T10:05:00+00:00")
        assert rows[0]["themes"] == ["monetary"]

    def test_importance_raw_from_score(self):
        rec = self._make_record(score=1.8)
        rows = ni._build_qbus_rows([rec], [], "2026-07-02T10:05:00+00:00")
        assert abs(rows[0]["importance_raw"] - 1.8) < 1e-6
