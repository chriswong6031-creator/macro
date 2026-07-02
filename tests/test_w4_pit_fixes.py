"""tests/test_w4_pit_fixes.py — W4 integrator debt items 1 + 2 + re-backfill.

Covers:
  1. echo_stats asof filtering: a future corroborator (item crawled AFTER the
     scoring asof) must NOT count toward breadth (integrator debt item 1).
  2. tz-mixed seendate: _subject_daily_counts must parse both tz-AWARE and
     tz-NAIVE seendate strings without producing NaT (integrator debt item 2).
  3. Dateless rows: rows with empty seendate AND _crawled_at survive clean_df
     (dropped) without crashing novelty_z on a matched-subject NaT.
  4. Re-backfill idempotency: shadow_importance_v0_pit.run() registers _pit
     families and is idempotent (second run adds zero new claims).

No network, no real data, no ambient clock.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import qbus  # noqa: E402
from engine import importance_v0 as iv  # noqa: E402
from engine import qledger as q  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _row(**kw) -> dict:
    base = {
        "item_id": "idefault", "event_key": "ev1",
        "desk": "financial_news", "source": "reuters",
        "source_tier": 1, "lang": "en",
        "url": "", "title": "title", "body_sha256": "",
        "seendate": "2026-06-15T12:00:00+00:00",
        "_crawled_at": "2026-06-15T12:05:00+00:00",
        "timestamp_quality": "CRAWL_BOUNDED",
        "entities": "SPY", "themes": "monetary", "importance_raw": 0.5,
    }
    base.update(kw)
    return base


def _df(rows: list[dict]) -> pd.DataFrame:
    normed = [qbus.normalize_row(r) for r in rows]
    return pd.DataFrame(normed, columns=list(qbus.COLUMNS))


# --------------------------------------------------------------------------- #
# 1. echo_stats asof filter — future corroborators must be excluded
# --------------------------------------------------------------------------- #
class TestEchoStatsAsofFilter:
    def _setup(self) -> pd.DataFrame:
        """Event ev1: item_0 seen on 2026-06-10 (past),
                      item_1 seen on 2026-06-20 (future relative to asof=06-15).
        Without asof filter, breadth=2 (both count).
        With asof=06-15, breadth=1 (only item_0 counts)."""
        rows = [
            _row(item_id="item_0", event_key="ev1", desk="financial_news",
                 seendate="2026-06-10T12:00:00+00:00",
                 _crawled_at="2026-06-10T12:01:00+00:00",
                 url="https://reuters.com/a"),
            _row(item_id="item_1", event_key="ev1", desk="china_news_intel",
                 seendate="2026-06-20T08:00:00+00:00",
                 _crawled_at="2026-06-20T08:01:00+00:00",
                 url="https://cn.com/b"),
        ]
        return _df(rows)

    def test_without_asof_sees_both_items(self):
        df = self._setup()
        st = qbus.echo_stats("ev1", df=df)
        assert st is not None
        assert st["n_items"] == 2
        assert st["breadth"] == 2

    def test_with_asof_excludes_future_item(self):
        df = self._setup()
        # asof = 2026-06-15: item_0 (06-10) in, item_1 (06-20) out
        st = qbus.echo_stats("ev1", df=df, asof=date(2026, 6, 15))
        assert st is not None
        assert st["n_items"] == 1
        assert st["breadth"] == 1    # only financial_news desk counts
        assert st["n_desks"] == 1

    def test_asof_as_string(self):
        df = self._setup()
        st = qbus.echo_stats("ev1", df=df, asof="2026-06-15")
        assert st is not None and st["n_items"] == 1

    def test_asof_on_boundary_includes_same_day(self):
        """An item crawled on the SAME day as asof is included."""
        df = self._setup()
        # asof = 06-10 exactly: item_0's _crawled_at is 06-10 → included
        st = qbus.echo_stats("ev1", df=df, asof=date(2026, 6, 10))
        assert st is not None and st["n_items"] == 1

    def test_asof_before_all_items_returns_none(self):
        """If asof is before every item, the filtered sub is empty → None."""
        df = self._setup()
        st = qbus.echo_stats("ev1", df=df, asof=date(2026, 6, 1))
        assert st is None


# --------------------------------------------------------------------------- #
# 2. tz-mixed seendate → no NaT in _subject_daily_counts
# --------------------------------------------------------------------------- #
class TestTzMixedSeendate:
    def _make_mixed_df(self) -> pd.DataFrame:
        """Three rows:
          - tz-aware  ISO 8601 (CN lane style): 2026-06-20T09:00:00+00:00
          - tz-naive  datetime string (news_vector style): 2026-06-20 14:30:00
          - tz-aware  Z suffix: 2026-06-20T10:00:00Z
        All have the same entity 'AAPL' so they all feed the count.
        """
        rows = [
            _row(item_id="r_aware", entities="AAPL",
                 seendate="2026-06-20T09:00:00+00:00",
                 _crawled_at="2026-06-20T09:01:00+00:00",
                 url="https://a.com/1"),
            _row(item_id="r_naive", entities="AAPL",
                 seendate="2026-06-20 14:30:00",
                 _crawled_at="2026-06-20 14:31:00",
                 url="https://a.com/2"),
            _row(item_id="r_zulu", entities="AAPL",
                 seendate="2026-06-20T10:00:00Z",
                 _crawled_at="2026-06-20T10:01:00Z",
                 url="https://a.com/3"),
        ]
        return _df(rows)

    def test_all_three_rows_counted(self):
        """_subject_daily_counts must count all 3 rows on 2026-06-20, not just
        the tz-naive one (which is what the old code would do after NaT coercion)."""
        df = self._make_mixed_df()
        today, series = qbus._subject_daily_counts(
            df, "AAPL", date(2026, 6, 20), window_days=7
        )
        assert today == 3.0, f"expected 3 rows on asof, got {today}"

    def test_novelty_z_not_none_for_all_rows(self):
        """novelty_z must NOT return None just because some seendate strings are
        tz-aware and others are tz-naive (the bug was entire CN lane = NaT)."""
        df = self._make_mixed_df()
        z = qbus.novelty_z("AAPL", date(2026, 6, 20), window_days=7, df=df)
        # With only data on 06-20 (no trailing history), the z is the flat-window
        # maximal-novel case: today > mean(all-zero window) → returns 3.0, not None.
        assert z is not None, "novelty_z returned None for tz-mixed store"

    def test_cn_rows_survive_clean_df(self):
        """clean_df must normalise tz-mixed seendate without dropping CN rows."""
        df = self._make_mixed_df()
        clean = iv.clean_df(df)
        assert len(clean) == 3, f"expected 3 rows after clean_df, got {len(clean)}"
        # seendate is now a uniform date-only string
        dates = pd.to_datetime(clean["seendate"], errors="coerce")
        assert dates.notna().all(), "clean_df left NaT in seendate"


# --------------------------------------------------------------------------- #
# 3. Dateless rows — must be dropped by clean_df without crashing novelty_z
# --------------------------------------------------------------------------- #
class TestDatelessRows:
    def test_dateless_rows_dropped_not_crash(self):
        """Rows with empty seendate AND _crawled_at must be silently dropped by
        clean_df; novelty_z on a matched subject must not raise TypeError."""
        rows = [
            _row(item_id="good", entities="NVDA",
                 seendate="2026-06-15T00:00:00+00:00",
                 _crawled_at="2026-06-15T00:01:00+00:00",
                 url="https://x.com/good"),
            _row(item_id="dateless", entities="NVDA",
                 seendate="", _crawled_at="",  # no usable date
                 url="https://x.com/dead"),
        ]
        df = _df(rows)
        clean = iv.clean_df(df)
        assert "dateless" not in set(clean["item_id"])
        assert "good" in set(clean["item_id"])
        # novelty_z must not raise even though the dateless row shares the entity
        z = qbus.novelty_z("NVDA", date(2026, 6, 15), df=clean)
        assert z is not None or z is None   # either is fine; no exception

    def test_novelty_z_on_raw_mixed_df_does_not_raise(self):
        """novelty_z should not crash when the raw (un-cleaned) df has NaT rows."""
        rows = [
            _row(item_id="ok1", entities="TSLA",
                 seendate="2026-06-10T00:00:00+00:00",
                 _crawled_at="2026-06-10T00:01:00+00:00",
                 url="https://x.com/1"),
            _row(item_id="nat1", entities="TSLA",
                 seendate="", _crawled_at="",
                 url="https://x.com/2"),
        ]
        df = _df(rows)
        # passing raw (not cleaned) df: the tz-aware parse in qbus must handle NaT
        # without raising; it should return a float or None, never an exception.
        try:
            z = qbus.novelty_z("TSLA", date(2026, 6, 10), df=df)
        except Exception as exc:
            pytest.fail(f"novelty_z raised on dateless row: {exc}")


# --------------------------------------------------------------------------- #
# 4. Re-backfill idempotency — _pit families
# --------------------------------------------------------------------------- #
def _write_price(path: Path, start: str = "2026-01-01", n: int = 120, px: float = 10.0):
    idx = pd.bdate_range(start=start, periods=n)
    pd.DataFrame({"close": [px * (1.002 ** i) for i in range(n)]},
                 index=idx).to_parquet(path)


@pytest.fixture()
def pit_root(tmp_path: Path, monkeypatch):
    """tmp repo root with a synthetic qbus store + price parquets.  Mirrors the
    fake_root fixture in test_importance_v0.py."""
    root = tmp_path / "repo"
    # qbus store: two US items (AAPL spike day, one quiet AAPL day) + one CN item
    rows = []
    for d in range(1, 15):
        rows.append({
            "item_id": f"aapl{d}", "event_key": f"evA{d}",
            "desk": "financial_news", "source": "reuters", "source_tier": 1,
            "lang": "en", "url": f"https://r.com/{d}", "title": f"AAPL note {d}",
            "body_sha256": "",
            "seendate": f"2026-06-{d:02d}T12:00:00+00:00",   # tz-aware
            "_crawled_at": f"2026-06-{d:02d}T12:05:00+00:00",
            "timestamp_quality": "CRAWL_BOUNDED",
            "entities": "AAPL", "themes": "tech", "importance_raw": 0.5,
        })
    # CN row with tz-naive seendate (formerly coerced to NaT)
    rows.append({
        "item_id": "cn1", "event_key": "evCN1",
        "desk": "china_news_intel", "source": "jin10", "source_tier": 2,
        "lang": "zh", "url": "https://jin10.com/1", "title": "央行降准",
        "body_sha256": "",
        "seendate": "2026-06-10 09:00:00",   # tz-NAIVE
        "_crawled_at": "2026-06-10 09:01:00",
        "timestamp_quality": "CRAWL_BOUNDED",
        "entities": "600519.SS", "themes": "policy", "importance_raw": 0.7,
    })

    qbus_dir = root / "data" / "qbus"
    qbus_dir.mkdir(parents=True)
    pd.DataFrame(rows, columns=list(qbus.COLUMNS)).to_parquet(
        qbus_dir / "items.parquet", index=False
    )

    # Price data
    (root / "data" / "yahoo").mkdir(parents=True)
    for t in ("AAPL", "SPY"):
        _write_price(root / "data" / "yahoo" / f"{t}.parquet")
    (root / "data" / "china_stocks").mkdir(parents=True)
    _write_price(root / "data" / "china_stocks" / "600519.SS.parquet")
    (root / "data" / "china").mkdir(parents=True)
    _write_price(root / "data" / "china" / "510300.SS.parquet")

    monkeypatch.setattr(qbus, "_events_path",
                        lambda: root / "data" / "qbus" / "items.parquet")
    from lib import config
    monkeypatch.setattr(config, "ROOT", root)
    return root


def test_pit_backfill_registers_pit_families(pit_root):
    """shadow_importance_v0_pit.run() must register claims under the _pit families."""
    import scripts.shadow_importance_v0_pit as pit_script
    result = pit_script.run(pit_root, band_frac=0.5)
    claims = q.load_claims(pit_root)
    pit_families = {c.get("claim_family") for c in claims}
    assert "us_importance_v0_pit" in pit_families or "cn_importance_v0_pit" in pit_families
    # registered count > 0
    total_reg = result.get("us_registered", 0) + result.get("cn_registered", 0)
    assert total_reg > 0, f"expected >0 registered, got {result}"


def test_pit_backfill_idempotent(pit_root):
    """Running shadow_importance_v0_pit twice must not create duplicate claims."""
    import scripts.shadow_importance_v0_pit as pit_script
    first = pit_script.run(pit_root, band_frac=0.5)
    n_after_first = len(q.load_claims(pit_root))
    pit_script.run(pit_root, band_frac=0.5)
    n_after_second = len(q.load_claims(pit_root))
    assert n_after_second == n_after_first, (
        f"idempotency failed: {n_after_first} -> {n_after_second}"
    )
    assert first.get("us_registered", 0) + first.get("cn_registered", 0) > 0


def test_pit_claims_have_pit_corrected_flag(pit_root):
    """Every _pit claim must carry pit_corrected=True (audit field).

    Note: make_claim() calls claim.update(extra), so the extra dict is merged
    FLAT into the claim — pit_corrected is a top-level key, not nested under
    "extra".
    """
    import scripts.shadow_importance_v0_pit as pit_script
    pit_script.run(pit_root, band_frac=0.5)
    claims = [c for c in q.load_claims(pit_root)
              if c.get("claim_family") in ("us_importance_v0_pit", "cn_importance_v0_pit")]
    assert claims, "expected at least one _pit claim"
    for c in claims:
        # make_claim flattens extra into the top-level claim dict
        assert c.get("pit_corrected") is True, (
            f"claim {c.get('claim_id')} missing pit_corrected flag: {list(c.keys())}"
        )


def test_pit_and_w3_coexist_without_collision(pit_root):
    """Running both shadow_importance_v0 (W3) and shadow_importance_v0_pit (W4)
    must not produce any claim_id collision (distinct salt prefixes)."""
    import scripts.shadow_importance_v0 as w3_script
    import scripts.shadow_importance_v0_pit as pit_script

    w3_script.run(pit_root, band_frac=0.5)
    pit_script.run(pit_root, band_frac=0.5)

    claims = q.load_claims(pit_root)
    ids = [c.get("claim_id") for c in claims if c.get("claim_id")]
    assert len(ids) == len(set(ids)), "claim_id collision between W3 and _pit scripts"


def test_pit_echo_stats_no_look_ahead(pit_root):
    """With the W4 fix, echo_stats called at the item's own asof must not count
    corroborators that arrived later.  Validates the fix is end-to-end wired
    through score_components (which calls echo_stats with asof)."""
    import scripts.shadow_importance_v0_pit as pit_script
    # Build a df where ev1 has one item on day X and a corroborator on day X+5.
    rows_extra = [
        {
            "item_id": "early", "event_key": "evLeak",
            "desk": "financial_news", "source": "reuters", "source_tier": 1,
            "lang": "en", "url": "https://r.com/early", "title": "AAPL spike",
            "body_sha256": "",
            "seendate": "2026-06-01T12:00:00+00:00",
            "_crawled_at": "2026-06-01T12:05:00+00:00",
            "timestamp_quality": "CRAWL_BOUNDED",
            "entities": "AAPL", "themes": "tech", "importance_raw": 0.9,
        },
        {
            "item_id": "late_corrob", "event_key": "evLeak",
            "desk": "china_news_intel", "source": "jin10", "source_tier": 2,
            "lang": "en", "url": "https://cn.com/late", "title": "AAPL spike update",
            "body_sha256": "",
            "seendate": "2026-06-06T08:00:00+00:00",   # 5 days later
            "_crawled_at": "2026-06-06T08:01:00+00:00",
            "timestamp_quality": "CRAWL_BOUNDED",
            "entities": "AAPL", "themes": "tech", "importance_raw": 0.5,
        },
    ]
    df_extra = pd.DataFrame(rows_extra, columns=list(qbus.COLUMNS))
    clean = iv.clean_df(df_extra)

    # Score the EARLY item at its own asof (06-01).  With the PIT fix, the
    # late_corrob (06-06) must NOT count as a corroborator.
    early_row = clean[clean["item_id"] == "early"].to_dict("records")[0]
    comp = iv.score_components(early_row, asof="2026-06-01", df=clean)
    # breadth should be 0 or 1 (only "early" itself) — never 2.
    assert comp["breadth"] < 1.0, (
        f"look-ahead corroboration leaked: breadth={comp['breadth']}, "
        f"expected <1.0 (only early item should count at asof=06-01)"
    )
