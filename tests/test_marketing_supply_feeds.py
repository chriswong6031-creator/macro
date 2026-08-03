"""tests/test_marketing_supply_feeds.py — PR-B supply side of the TrendSpider program.

Covers the three things PR-B widens and the one law that keeps the widening
honest:

  * engine/marketing/attention_source.py — six read-only candidate pools, their
    provenance shape, and the freshness gate (masterplan §3 PR-B.2);
  * engine/marketing/radar_internal.build_cashtag_tiers — the tier universe
    widened from S&P 500 + Nasdaq-100 to the ADV-liquid market (§3 PR-B.1);
  * engine/marketing/movers_source — the mover board widened from the 503-name
    heatmap to the hot-tape pack (§3 PR-B.3);
  * config/marketing.yml `supply:` — the diversity knobs PR-C consumes (§3 PR-B.4).

EVERY FIXTURE DATE IS RELATIVE TO TODAY, never a literal. A suite that pins
"2026-07-31" as fresh passes on the day it is written and silently inverts
weeks later when the wall clock walks past the freshness budget — the
fixture-date-plus-wall-clock trap. `_sessions_ago()` is the only source of
dates here, and the pool functions take an explicit `as_of` wherever one is
available so the assertion does not depend on when it runs at all.

::warning assertions check `line.startswith("::")`. That is the actual defect
the five-strike law is about: a logger-routed annotation emits
`WARNING ::warning ...`, which reads correct in review, runs clean, and is
silently dropped by Actions. Asserting on the message text alone would pass on
exactly that bug, so the position of the marker is what gets pinned.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

#: ONE time base for the whole suite, in UTC because that is what the modules
#: under test use. Mixing a local `date.today()` fixture with a UTC gate silently
#: shifts every session count by one for eight hours a day.
TODAY: date = datetime.now(timezone.utc).date()


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sessions_ago(n: int, *, ref: date | None = None) -> str:
    """ISO date *n* Mon–Fri sessions before *ref* (default TODAY)."""
    cur = ref or TODAY
    left = n
    while left > 0:
        cur -= timedelta(days=1)
        if cur.weekday() < 5:
            left -= 1
    return cur.isoformat()


def _annotation_lines(captured: str) -> list[str]:
    """Every line that is a GitHub annotation *at line start* — the whole point."""
    return [ln for ln in captured.splitlines() if ln.startswith("::")]


def _assert_one_annotation(capsys, needle: str) -> str:
    out = capsys.readouterr().out
    lines = _annotation_lines(out)
    assert len(lines) == 1, f"expected exactly one line-start annotation, got {lines!r}"
    line = lines[0]
    # The marker must START the line: a logger-prefixed "WARNING ::warning ..."
    # is invisible to Actions, and this is the assertion that can see that.
    assert line.startswith("::warning title="), line
    assert needle in line, f"{needle!r} not in {line!r}"
    return line


def _write_pack(root: Path, tickers: dict, *, trade_date: str) -> None:
    p = root / "data" / "marketing"
    p.mkdir(parents=True, exist_ok=True)
    (p / "hot_tape_pack.json").write_text(json.dumps({
        "schema": "marketing.hot_tape_pack/v1",
        "trade_date": trade_date,
        "n_tickers": len(tickers),
        "tickers": tickers,
    }), encoding="utf-8")


def _pack_record(ticker: str, *, adv: float, rank: int, last: float, prev: float,
                 last_date: str, suspect: bool = False, sector: str | None = None) -> dict:
    return {
        "ticker": ticker, "adv20_dollars": adv, "adv_rank": rank,
        "last_close": last, "prev_close": prev, "last_date": last_date,
        "suspect": suspect, "sector": sector,
    }


def _write_heatmap(root: Path, tiles: list[dict], asof: str) -> None:
    p = root / "site" / "marketdata"
    p.mkdir(parents=True, exist_ok=True)
    (p / "sp500_heatmap.json").write_text(
        json.dumps({"asof": asof, "tiles": tiles}), encoding="utf-8")


def _write_config(root: Path, supply: dict | None = None,
                  t1_always: list | None = None) -> None:
    import yaml
    p = root / "config"
    p.mkdir(parents=True, exist_ok=True)
    # NOT an empty list: `_load_t1_always` treats a falsy value as "unset" and
    # falls back to the 17 built-in megacaps, which would drag AAPL/GME/… into
    # every fixture universe. One throwaway name keeps the list truthy and the
    # universe legible.
    cfg: dict = {"radar": {"t1_always": t1_always if t1_always else ["ZZALWAYS"]}}
    if supply is not None:
        cfg["supply"] = supply
    (p / "marketing.yml").write_text(yaml.safe_dump(cfg), encoding="utf-8")


def _write_ndx(root: Path, tickers: list[str]) -> None:
    """The index half of the tier universe (build_cashtag_tiers reads this, not the heatmap)."""
    d = root / "data" / "finviz_screener"
    d.mkdir(parents=True, exist_ok=True)
    (d / "idx_ndx.json").write_text(
        json.dumps([{"ticker": t} for t in tickers]), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 1. sessions_since — the arithmetic every gate below stands on
# ─────────────────────────────────────────────────────────────────────────────

def test_sessions_since_counts_weekdays_only():
    from engine.marketing.attention_source import sessions_since
    # Fri 2026-07-31 → Mon 2026-08-03 is ONE session, not three calendar days.
    assert sessions_since("2026-07-31", "2026-08-03") == 1
    assert sessions_since("2026-07-27", "2026-07-31") == 4


def test_sessions_since_fails_soft_and_never_negative():
    from engine.marketing.attention_source import sessions_since
    assert sessions_since("not-a-date", "2026-08-03") is None
    assert sessions_since(None, "2026-08-03") is None
    # A stamp in the future is not stale; it is 0 sessions old.
    assert sessions_since("2026-08-10", "2026-08-03") == 0


# ─────────────────────────────────────────────────────────────────────────────
# 2. Config accessors — the knobs PR-C consumes, one owner
# ─────────────────────────────────────────────────────────────────────────────

def test_supply_defaults_when_config_absent(tmp_path):
    from engine.marketing import attention_source as A
    assert A.pool_cap(tmp_path, "dollar_volume") == 120
    assert A.long_tail_quota(tmp_path) == {"min_fresh_per_day": 3,
                                           "not_posted_within_days": 30}
    assert A.max_chart_posts_per_ticker_day(tmp_path) == 3
    assert A.max_stale_sessions(tmp_path) == 3
    assert A.pack_min_adv_dollars(tmp_path) == 25_000_000


def test_supply_block_is_present_and_readable_in_the_shipped_config():
    """The real config/marketing.yml carries the block PR-C will read."""
    from engine.marketing import attention_source as A
    root = _repo_root()
    cfg = A.supply_config(root)
    assert set(cfg) >= {"pool_caps", "long_tail_quota", "per_ticker_day",
                        "freshness", "tiers"}
    # §0 gate 6 numbers, defined here rather than invented by the selector.
    assert A.long_tail_quota(root)["min_fresh_per_day"] >= 3
    assert A.long_tail_quota(root)["not_posted_within_days"] == 30
    assert A.max_chart_posts_per_ticker_day(root) == 3
    for pool in ("dollar_volume", "options_volume", "retail_attention",
                 "earnings_this_week", "stage2_leaders", "stage_transitions"):
        assert A.pool_cap(root, pool) > 0, pool


def test_every_accessor_actually_reads_its_config_key(tmp_path):
    """Non-default values, because a default is perfect cover for a key typo.

    Each accessor falls back to a built-in default that EQUALS the shipped
    config value. So if an accessor's key name and the config's key name ever
    drift apart — which is exactly what happened when `pack_min_adv_dollars`
    was renamed out of the Hot Tape safety-stack guard's way — every assertion
    against the shipped numbers still passes, reading the default and never
    touching the file. Only a value the default cannot produce can see it.
    """
    from engine.marketing import attention_source as A
    _write_config(tmp_path, supply={
        "pool_caps": {"dollar_volume": 7},
        "long_tail_quota": {"min_fresh_per_day": 9, "not_posted_within_days": 11},
        "per_ticker_day": {"max_chart_posts": 6},
        "freshness": {"max_stale_sessions": 8},
        "tiers": {"pack_min_adv_dollars": 33_000_000},
    })
    assert A.pool_cap(tmp_path, "dollar_volume") == 7
    assert A.long_tail_quota(tmp_path) == {"min_fresh_per_day": 9,
                                           "not_posted_within_days": 11}
    assert A.max_chart_posts_per_ticker_day(tmp_path) == 6
    assert A.max_stale_sessions(tmp_path) == 8
    assert A.pack_min_adv_dollars(tmp_path) == 33_000_000


def test_config_marketing_yml_never_names_the_hot_tape_program(tmp_path):
    """The `supply:` block must stay clear of the safety-stack guard's invariant.

    config/marketing.yml is held READ-ONLY to the Hot Tape program by
    tests/test_marketing_hot_tape_radar.py::TestSafetyStack, and unlike the
    five source files it lists, the config file gets NO sanctioned-token
    exception. This suite pins the same rule from the supply side so the
    failure lands next to the block that would cause it.
    """
    text = (_repo_root() / "config" / "marketing.yml").read_text(encoding="utf-8")
    offenders = [ln.strip() for ln in text.splitlines() if "hot_tape" in ln]
    assert not offenders, (
        "config/marketing.yml must not name the hot-tape program — rename the "
        f"key/comment rather than widening the guard: {offenders[:3]}")


def test_per_pool_freshness_override(tmp_path):
    from engine.marketing import attention_source as A
    _write_config(tmp_path, supply={"freshness": {"max_stale_sessions": 3,
                                                  "per_pool": {"stage2_leaders": 12}}})
    assert A.max_stale_sessions(tmp_path) == 3
    assert A.max_stale_sessions(tmp_path, "stage2_leaders") == 12
    assert A.max_stale_sessions(tmp_path, "dollar_volume") == 3


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for cand in (p.parent, p.parent.parent, p.parent.parent.parent):
        if (cand / "engine").is_dir():
            return cand
    raise RuntimeError("repo root not found")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Pool — dollar volume
# ─────────────────────────────────────────────────────────────────────────────

def test_dollar_volume_pool_ranks_by_adv_rank(tmp_path, capsys):
    from engine.marketing.attention_source import top_by_dollar_volume
    fresh = _sessions_ago(1)
    _write_pack(tmp_path, {
        "BBB": _pack_record("BBB", adv=2e9, rank=2, last=10, prev=10, last_date=fresh),
        "AAA": _pack_record("AAA", adv=9e9, rank=1, last=10, prev=10, last_date=fresh),
        "CCC": _pack_record("CCC", adv=3e7, rank=3, last=10, prev=10, last_date=fresh),
    }, trade_date=fresh)

    rows = top_by_dollar_volume(tmp_path, 10, as_of=TODAY)
    assert [r["ticker"] for r in rows] == ["AAA", "BBB", "CCC"]
    assert [r["rank"] for r in rows] == [1, 2, 3]
    for r in rows:
        assert set(r) == {"ticker", "rank", "why", "asof", "source"}
        assert r["source"] == "hot_tape_pack"
        assert r["asof"] == fresh
    # `why` names the concrete driver, with its number — provenance, not a score.
    assert "dollar-volume rank #1" in rows[0]["why"]
    assert "$9.0B" in rows[0]["why"]
    assert not _annotation_lines(capsys.readouterr().out)


def test_dollar_volume_pool_respects_n(tmp_path):
    from engine.marketing.attention_source import top_by_dollar_volume
    fresh = _sessions_ago(1)
    _write_pack(tmp_path, {
        f"T{i}": _pack_record(f"T{i}", adv=1e9 - i, rank=i, last=10, prev=10,
                              last_date=fresh)
        for i in range(1, 11)
    }, trade_date=fresh)
    assert len(top_by_dollar_volume(tmp_path, 4, as_of=TODAY)) == 4


def test_dollar_volume_pool_is_empty_and_loud_when_stale(tmp_path, capsys):
    from engine.marketing.attention_source import top_by_dollar_volume
    old = _sessions_ago(9)
    _write_pack(tmp_path, {
        "AAA": _pack_record("AAA", adv=9e9, rank=1, last=10, prev=10, last_date=old),
    }, trade_date=old)

    assert top_by_dollar_volume(tmp_path, 10, as_of=TODAY) == []
    _assert_one_annotation(capsys, "marketing-supply-dollar-volume")


def test_dollar_volume_pool_is_empty_and_loud_when_absent(tmp_path, capsys):
    from engine.marketing.attention_source import top_by_dollar_volume
    assert top_by_dollar_volume(tmp_path, 10, as_of=TODAY) == []
    _assert_one_annotation(capsys, "marketing-supply-dollar-volume")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Pool — options volume
# ─────────────────────────────────────────────────────────────────────────────

def _write_options(root: Path, ticker: str, rows: list[tuple[str, float, float, float]]) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    d = root / "data" / "options_flow"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [{"volume": v, "premium_mn": p, "pc_ratio": pc} for _, v, p, pc in rows],
        index=pd.to_datetime([r[0] for r in rows]),
    )
    df.to_parquet(d / f"summary_{ticker}.parquet")


def test_options_volume_pool_ranks_by_latest_session_volume(tmp_path, capsys):
    from engine.marketing.attention_source import top_by_options_volume
    d1, d0 = _sessions_ago(1), _sessions_ago(2)
    _write_options(tmp_path, "AAA", [(d0, 10.0, 1.0, 0.5), (d1, 500.0, 12.0, 0.90)])
    _write_options(tmp_path, "BBB", [(d0, 900.0, 3.0, 1.0), (d1, 1500.0, 40.0, 1.25)])

    rows = top_by_options_volume(tmp_path, 10, as_of=TODAY)
    # BBB's LAST row is bigger; AAA's earlier 900 for BBB must not decide the order.
    assert [r["ticker"] for r in rows] == ["BBB", "AAA"]
    assert [r["rank"] for r in rows] == [1, 2]
    assert all(r["source"] == "options_flow" and r["asof"] == d1 for r in rows)
    assert "1,500 contracts" in rows[0]["why"]
    assert "put/call 1.25" in rows[0]["why"]
    assert not _annotation_lines(capsys.readouterr().out)


def test_options_volume_drops_the_stale_row_not_the_whole_pool(tmp_path, capsys):
    """Per-row freshness: one straggler must not delete the fresh majority."""
    from engine.marketing.attention_source import top_by_options_volume
    fresh, ancient = _sessions_ago(1), _sessions_ago(30)
    _write_options(tmp_path, "FRESH", [(fresh, 100.0, 1.0, 0.5)])
    _write_options(tmp_path, "STALE", [(ancient, 99999.0, 1.0, 0.5)])

    rows = top_by_options_volume(tmp_path, 10, as_of=TODAY)
    assert [r["ticker"] for r in rows] == ["FRESH"], "the stale giant must not rank"
    assert not _annotation_lines(capsys.readouterr().out)


def test_options_volume_pool_is_empty_and_loud_when_all_stale(tmp_path, capsys):
    from engine.marketing.attention_source import top_by_options_volume
    ancient = _sessions_ago(30)
    _write_options(tmp_path, "AAA", [(ancient, 100.0, 1.0, 0.5)])
    assert top_by_options_volume(tmp_path, 10, as_of=TODAY) == []
    _assert_one_annotation(capsys, "marketing-supply-options-volume")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Pool — retail attention
# ─────────────────────────────────────────────────────────────────────────────

def _write_wsb(root: Path, day: str, rows: list[tuple[str, int, float]]) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    d = root / "data" / "quiver"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"Ticker": t, "Count": c, "Sentiment": s, "_collected": day}
                  for t, c, s in rows]).to_parquet(d / "wallstreetbets.parquet")


def _write_wiki(root: Path, rows: dict[str, tuple[float, int, str]]) -> None:
    d = root / "site" / "factordata"
    d.mkdir(parents=True, exist_ok=True)
    (d / "attention.json").write_text(json.dumps(
        {t: {"z": z, "views": v, "asof": a} for t, (z, v, a) in rows.items()}),
        encoding="utf-8")


def test_retail_attention_blends_and_names_the_driver(tmp_path, capsys):
    from engine.marketing.attention_source import retail_attention
    day = _sessions_ago(1)
    # HOT tops WSB alone (1.00, 0.00 → 0.50); WIKI tops wiki alone (0.00, 1.00
    # → 0.50); MID is strong on BOTH (0.75, 0.75 → 0.75) and therefore wins.
    # That ordering is the whole reason the score is a blend and not a max.
    _write_wsb(tmp_path, day, [("HOT", 400, 0.3), ("MID", 300, 0.1)])
    _write_wiki(tmp_path, {"WIKI": (4.0, 900, day), "MID": (3.0, 300, day)})

    rows = retail_attention(tmp_path, 10, as_of=TODAY)
    by_ticker = {r["ticker"]: r for r in rows}
    assert rows[0]["ticker"] == "MID"
    assert set(by_ticker) == {"HOT", "MID", "WIKI"}
    # `why` names the leg that actually drove the row — a checkable fact.
    assert by_ticker["HOT"]["why"] == "WSB #1 by mentions (400 today)"
    assert by_ticker["HOT"]["source"] == "quiver_wsb"
    assert "search attention z 4.0" in by_ticker["WIKI"]["why"]
    assert by_ticker["WIKI"]["source"] == "wiki_attention"
    assert all(r["asof"] == day for r in rows)
    assert not _annotation_lines(capsys.readouterr().out)


def test_retail_attention_drops_only_the_stale_leg(tmp_path, capsys):
    from engine.marketing.attention_source import retail_attention
    fresh, ancient = _sessions_ago(1), _sessions_ago(30)
    _write_wsb(tmp_path, fresh, [("HOT", 400, 0.3)])
    _write_wiki(tmp_path, {"OLDWIKI": (9.0, 900, ancient)})

    rows = retail_attention(tmp_path, 10, as_of=TODAY)
    assert [r["ticker"] for r in rows] == ["HOT"]
    assert rows[0]["asof"] == fresh
    assert not _annotation_lines(capsys.readouterr().out)


def test_retail_attention_pool_is_empty_and_loud_when_every_leg_is_stale(tmp_path, capsys):
    from engine.marketing.attention_source import retail_attention
    ancient = _sessions_ago(30)
    _write_wsb(tmp_path, ancient, [("HOT", 400, 0.3)])
    _write_wiki(tmp_path, {"WIKI": (9.0, 900, ancient)})

    assert retail_attention(tmp_path, 10, as_of=TODAY) == []
    _assert_one_annotation(capsys, "marketing-supply-retail-attention")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Pool — earnings this week
# ─────────────────────────────────────────────────────────────────────────────

def _write_earnings(root: Path, rows: list[tuple[str, str, str, str]]) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    d = root / "data" / "earnings"
    d.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [{"next_date": nd, "next_time": nt, "as_of": ao} for _, nd, nt, ao in rows],
        index=[r[0] for r in rows],
    )
    df.index.name = "ticker"
    df.to_parquet(d / "earnings.parquet")


def _sessions_ahead(n: int) -> str:
    cur = TODAY
    left = n
    while left > 0:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            left -= 1
    return cur.isoformat()


def test_earnings_pool_windows_the_next_five_sessions(tmp_path, capsys):
    from engine.marketing.attention_source import earnings_this_week
    swept = _sessions_ago(1)
    _write_earnings(tmp_path, [
        ("SOON", _sessions_ahead(1), "time-pre-market", swept),
        ("LATER", _sessions_ahead(4), "time-after-hours", swept),
        ("FAROFF", _sessions_ahead(20), "time-not-supplied", swept),
        ("PAST", _sessions_ago(3), "time-pre-market", swept),
    ])
    rows = earnings_this_week(tmp_path, 10, as_of=TODAY)
    assert [r["ticker"] for r in rows] == ["SOON", "LATER"]
    assert rows[0]["why"].startswith(f"reports {_sessions_ahead(1)}")
    assert "before the open" in rows[0]["why"]
    assert rows[1]["why"].endswith("4 sessions away")
    assert all(r["source"] == "earnings_calendar" for r in rows)
    assert not _annotation_lines(capsys.readouterr().out)


def test_earnings_pool_drops_a_stale_sweep_row_on_its_own_stamp(tmp_path, capsys):
    """The real file mixes as_of sweeps; a row is judged by ITS sweep, not the file's."""
    from engine.marketing.attention_source import earnings_this_week
    _write_earnings(tmp_path, [
        ("FRESH", _sessions_ahead(2), "time-pre-market", _sessions_ago(1)),
        ("OLDSWEEP", _sessions_ahead(2), "time-pre-market", _sessions_ago(30)),
    ])
    rows = earnings_this_week(tmp_path, 10, as_of=TODAY)
    assert [r["ticker"] for r in rows] == ["FRESH"]
    assert not _annotation_lines(capsys.readouterr().out)


def test_earnings_pool_is_empty_and_loud_when_every_sweep_is_stale(tmp_path, capsys):
    from engine.marketing.attention_source import earnings_this_week
    _write_earnings(tmp_path, [
        ("OLDSWEEP", _sessions_ahead(2), "time-pre-market", _sessions_ago(30)),
    ])
    assert earnings_this_week(tmp_path, 10, as_of=TODAY) == []
    _assert_one_annotation(capsys, "marketing-supply-earnings")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Pools — Weinstein stage
# ─────────────────────────────────────────────────────────────────────────────

def _write_stage(root: Path, rows: list[dict]) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    d = root / "data" / "stage_analysis" / "backfill"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(d / "equitydesk_overview.parquet")


def _stage_row(ticker: str, *, flag: int, sata: float, asof: str,
               region: str = "USA", detailed: str = "2A", weeks: int = 6) -> dict:
    return {"ticker": ticker, "region": region, "stage_flag": flag,
            "stage_detailed": detailed, "sata_score": sata,
            "weeks_in_stage": weeks, "as_of_date": asof}


def test_stage2_leaders_ranks_usa_stage_two_by_sata(tmp_path, capsys):
    from engine.marketing.attention_source import stage2_leaders
    fresh = _sessions_ago(1)
    _write_stage(tmp_path, [
        _stage_row("LOW", flag=2, sata=40.0, asof=fresh),
        _stage_row("TOP", flag=2, sata=95.0, asof=fresh),
        _stage_row("STAGE4", flag=4, sata=99.0, asof=fresh),
        _stage_row("NOTUS", flag=2, sata=99.0, asof=fresh, region="EUROPE"),
    ])
    rows = stage2_leaders(tmp_path, 10, as_of=TODAY)
    assert [r["ticker"] for r in rows] == ["TOP", "LOW"]
    assert rows[0]["source"] == "stage_analysis"
    assert rows[0]["asof"] == fresh
    assert "SATA 95.0" in rows[0]["why"]
    assert not _annotation_lines(capsys.readouterr().out)


def test_stage2_leaders_is_empty_and_loud_when_the_snapshot_is_stale(tmp_path, capsys):
    from engine.marketing.attention_source import stage2_leaders
    _write_stage(tmp_path, [_stage_row("TOP", flag=2, sata=95.0, asof=_sessions_ago(20))])
    assert stage2_leaders(tmp_path, 10, as_of=TODAY) == []
    _assert_one_annotation(capsys, "marketing-supply-stage2")


def test_stage_transitions_detects_a_changed_flag_across_two_snapshots(tmp_path, capsys):
    """The shipped parquet keeps ONE snapshot, so this is the only place the diff runs.

    Without a two-snapshot fixture the function would be indistinguishable from
    `return []` — a test that only asserted the empty real-world result would
    pin the absence, not the logic.
    """
    from engine.marketing.attention_source import stage_transitions
    prior, latest = _sessions_ago(6), _sessions_ago(1)
    _write_stage(tmp_path, [
        _stage_row("MOVED", flag=1, sata=50.0, asof=prior),
        _stage_row("MOVED", flag=2, sata=88.0, asof=latest, detailed="2A"),
        _stage_row("STILL", flag=2, sata=99.0, asof=prior),
        _stage_row("STILL", flag=2, sata=99.0, asof=latest),
        _stage_row("BRANDNEW", flag=2, sata=97.0, asof=latest),
    ])
    rows = stage_transitions(tmp_path, 10, as_of=TODAY)
    # Only MOVED changed. STILL held its stage; BRANDNEW has no prior row to
    # differ from, and "absent last week" is not a transition.
    assert [r["ticker"] for r in rows] == ["MOVED"]
    assert "stage 1 to 2" in rows[0]["why"]
    assert prior in rows[0]["why"]
    assert rows[0]["asof"] == latest
    assert not _annotation_lines(capsys.readouterr().out)


def test_stage_transitions_says_so_when_only_one_snapshot_exists(tmp_path, capsys):
    """Structurally empty must not read as 'no transitions today'."""
    from engine.marketing.attention_source import stage_transitions
    _write_stage(tmp_path, [_stage_row("ONLY", flag=2, sata=95.0, asof=_sessions_ago(1))])
    assert stage_transitions(tmp_path, 10, as_of=TODAY) == []
    line = _assert_one_annotation(capsys, "marketing-supply-stage-transitions")
    assert "needs two" in line


# ─────────────────────────────────────────────────────────────────────────────
# 8. Tier widening (radar_internal.build_cashtag_tiers)
# ─────────────────────────────────────────────────────────────────────────────

def _tier_fixture(tmp_path: Path, *, trade_date: str) -> Path:
    """Index universe of one name; pack adds three non-index names."""
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    _write_config(tmp_path)
    _write_ndx(tmp_path, ["INDEXCO"])
    _write_heatmap(tmp_path, [
        {"t": "INDEXCO", "size": 0.20, "perf": {"1D": 0.4, "1W": 0.9}},
    ], asof=trade_date)
    _write_pack(tmp_path, {
        "INDEXCO": _pack_record("INDEXCO", adv=5e9, rank=1, last=100.4, prev=100.0,
                                last_date=trade_date),
        # Liquid, outside every index, and MOVING: must now be reachable.
        "ADVMOVER": _pack_record("ADVMOVER", adv=8e7, rank=2, last=106.0, prev=100.0,
                                 last_date=trade_date),
        # Liquid, outside every index, and quiet: tiered, but still T3.
        "ADVQUIET": _pack_record("ADVQUIET", adv=6e7, rank=3, last=100.1, prev=100.0,
                                 last_date=trade_date),
        # Moving hard, but the pack flags a split cliff: no price proxy at all.
        "SPLITSUS": _pack_record("SPLITSUS", adv=9e7, rank=4, last=50.0, prev=100.0,
                                 last_date=trade_date, suspect=True),
    }, trade_date=trade_date)
    return tmp_path


def test_adv_liquid_non_index_name_now_receives_a_tier(tmp_path):
    from engine.marketing.radar_internal import build_cashtag_tiers
    root = _tier_fixture(tmp_path, trade_date=_sessions_ago(1))
    tiers = build_cashtag_tiers(root)
    assert tiers is not None
    detail = tiers["tickers"]
    # The whole point: these names used to be invisible, not T3.
    for t in ("ADVMOVER", "ADVQUIET", "SPLITSUS"):
        assert t in detail, f"{t} never entered the tier universe"
        assert detail[t]["tier"] in {"T1", "T2", "T3"}
        assert detail[t]["proxies"]["in_index_universe"] is False
    assert tiers["universe_sources"]["hot_tape_pack_added_n"] == 3


def test_adv_liquid_mover_earns_t2_on_the_unchanged_threshold(tmp_path):
    from engine.marketing.radar_internal import build_cashtag_tiers
    root = _tier_fixture(tmp_path, trade_date=_sessions_ago(1))
    detail = build_cashtag_tiers(root)["tickers"]
    mover = detail["ADVMOVER"]
    assert mover["tier"] == "T2"
    # Same reason name and same 3.0 threshold as the index-era rule — the
    # LADDER did not move, only what it can see.
    assert "move_1d" in mover["reasons"]
    assert mover["proxies"]["pct_1d"] == pytest.approx(6.0)
    assert mover["proxies"]["pct_1d_source"] == "hot_tape_pack"
    assert mover["proxies"]["dollar_vol_source"] == "hot_tape_adv20"


def test_quiet_liquid_name_stays_t3_and_a_split_suspect_gets_no_price_proxy(tmp_path):
    from engine.marketing.radar_internal import build_cashtag_tiers
    root = _tier_fixture(tmp_path, trade_date=_sessions_ago(1))
    detail = build_cashtag_tiers(root)["tickers"]
    assert detail["ADVQUIET"]["tier"] == "T3"
    assert detail["ADVQUIET"]["reasons"] == []
    # A 50% "move" from a non-split-adjusted store must never become a tier
    # reason. Suspect ⇒ no pct_1d at all, so move_1d cannot fire.
    assert detail["SPLITSUS"]["proxies"]["pct_1d"] is None
    assert detail["SPLITSUS"]["proxies"]["pct_1d_source"] is None
    assert "move_1d" not in detail["SPLITSUS"]["reasons"]


def test_illiquid_name_below_the_adv_floor_is_not_tiered_at_all(tmp_path):
    """Widening the universe is not the same as admitting everything."""
    from engine.marketing.radar_internal import build_cashtag_tiers
    fresh = _sessions_ago(1)
    root = _tier_fixture(tmp_path, trade_date=fresh)
    _write_config(root, supply={"tiers": {"pack_min_adv_dollars": 25_000_000}})
    _write_pack(root, {
        "ADVMOVER": _pack_record("ADVMOVER", adv=8e7, rank=1, last=106.0, prev=100.0,
                                 last_date=fresh),
        "PENNYCO": _pack_record("PENNYCO", adv=1e5, rank=2, last=112.0, prev=100.0,
                                last_date=fresh),
    }, trade_date=fresh)
    detail = build_cashtag_tiers(root)["tickers"]
    assert "ADVMOVER" in detail
    assert "PENNYCO" not in detail, "a name under the ADV floor must stay out of the universe"


def test_stale_pack_falls_back_to_the_index_universe_and_says_so(tmp_path, capsys):
    from engine.marketing.radar_internal import build_cashtag_tiers
    root = _tier_fixture(tmp_path, trade_date=_sessions_ago(20))
    tiers = build_cashtag_tiers(root)
    detail = tiers["tickers"]
    assert "INDEXCO" in detail
    assert "ADVMOVER" not in detail, "a stale pack must not widen the universe"
    assert tiers["universe_sources"]["hot_tape_pack_n"] == 0
    line = _assert_one_annotation(capsys, "marketing-cashtag-tiers")
    assert "stale" in line


def test_missing_pack_falls_back_to_the_index_universe_and_says_so(tmp_path, capsys):
    from engine.marketing.radar_internal import build_cashtag_tiers
    pytest.importorskip("pandas")
    _write_config(tmp_path)
    _write_ndx(tmp_path, ["INDEXCO"])
    _write_heatmap(tmp_path, [{"t": "INDEXCO", "size": 0.2, "perf": {"1D": 0.4}}],
                   asof=_sessions_ago(1))
    tiers = build_cashtag_tiers(tmp_path)
    assert set(tiers["tickers"]) == {"INDEXCO", "ZZALWAYS"}
    assert tiers["universe_sources"]["hot_tape_pack_added_n"] == 0
    _assert_one_annotation(capsys, "marketing-cashtag-tiers")


def test_tier_contract_still_holds_after_widening(tmp_path):
    """T1/T2/T3 stay disjoint and still cover the whole (bigger) universe."""
    from engine.marketing.radar_internal import build_cashtag_tiers
    root = _tier_fixture(tmp_path, trade_date=_sessions_ago(1))
    tiers = build_cashtag_tiers(root)
    t1, t2, t3 = (set(tiers["tiers"][k]) for k in ("T1", "T2", "T3"))
    assert not (t1 & t2) and not (t1 & t3) and not (t2 & t3)
    assert (t1 | t2 | t3) == set(tiers["tickers"])
    assert tiers["schema"] == "marketing.cashtag_tiers/v1"


# ─────────────────────────────────────────────────────────────────────────────
# 9. Movers breadth (movers_source)
# ─────────────────────────────────────────────────────────────────────────────

def _movers_fixture(tmp_path: Path, *, trade_date: str) -> Path:
    _write_heatmap(tmp_path, [
        {"t": "INDEXUP", "name": "Index Up", "sector": "Tech",
         "perf": {"1D": 4.0, "1W": 9.0}},
        {"t": "INDEXFLAT", "name": "Index Flat", "sector": "Tech",
         "perf": {"1D": 0.2, "1W": 0.5}},
    ], asof=trade_date)
    _write_pack(tmp_path, {
        # Already on the index board: must not be duplicated.
        "INDEXUP": _pack_record("INDEXUP", adv=5e9, rank=1, last=104.0, prev=100.0,
                                last_date=trade_date),
        "WILDUP": _pack_record("WILDUP", adv=9e7, rank=2, last=120.0, prev=100.0,
                               last_date=trade_date),
        "WILDDOWN": _pack_record("WILDDOWN", adv=8e7, rank=3, last=85.0, prev=100.0,
                                 last_date=trade_date),
        "TINYMOVE": _pack_record("TINYMOVE", adv=7e7, rank=4, last=100.5, prev=100.0,
                                 last_date=trade_date),
        "SPLITSUS": _pack_record("SPLITSUS", adv=9e7, rank=5, last=50.0, prev=100.0,
                                 last_date=trade_date, suspect=True),
        "LAGGARD": _pack_record("LAGGARD", adv=9e7, rank=6, last=50.0, prev=100.0,
                                last_date=_sessions_ago(30)),
    }, trade_date=trade_date)
    return tmp_path


def test_top_movers_draws_from_the_pack_as_well_as_the_index(tmp_path):
    from engine.marketing.movers_source import load_movers, top_movers
    root = _movers_fixture(tmp_path, trade_date=_sessions_ago(1))
    data = load_movers(root)
    assert len(data["pack_tiles"]) >= 3

    res = top_movers(data, n=8, min_abs=3.0)
    gain = [m["ticker"] for m in res["gainers"]]
    loss = [m["ticker"] for m in res["losers"]]
    # The 20% pack name outranks the 4% index name — impossible before PR-B.
    assert gain == ["WILDUP", "INDEXUP"]
    assert loss == ["WILDDOWN"]
    src = {m["ticker"]: m["source"] for m in res["gainers"] + res["losers"]}
    assert src["WILDUP"] == "hot_tape_pack"
    assert src["INDEXUP"] == "sp500_heatmap"


def test_top_movers_pack_rows_obey_min_abs_and_the_pack_guards(tmp_path):
    from engine.marketing.movers_source import load_movers, top_movers
    root = _movers_fixture(tmp_path, trade_date=_sessions_ago(1))
    res = top_movers(load_movers(root), n=8, min_abs=3.0)
    seen = {m["ticker"] for m in res["gainers"] + res["losers"]}
    assert "TINYMOVE" not in seen, "min_abs must still gate pack rows"
    assert "SPLITSUS" not in seen, "a split-suspect name may not become a price claim"
    assert "LAGGARD" not in seen, "a record behind the pack tip has no 1-day move"


def test_top_movers_does_not_duplicate_a_name_on_both_boards(tmp_path):
    from engine.marketing.movers_source import load_movers, top_movers
    root = _movers_fixture(tmp_path, trade_date=_sessions_ago(1))
    data = load_movers(root)
    assert "INDEXUP" not in {t["t"] for t in data["pack_tiles"]}
    # Belt-and-braces: even a hand-built payload that duplicates must not double-count.
    data["pack_tiles"] = list(data["pack_tiles"]) + [
        {"t": "INDEXUP", "name": "dupe", "sector": "", "perf": {"1D": 99.0},
         "asof": "2026-01-01", "source": "hot_tape_pack"}]
    res = top_movers(data, n=8, min_abs=3.0)
    tickers = [m["ticker"] for m in res["gainers"]]
    assert tickers.count("INDEXUP") == 1
    # The INDEX tile won, so the 4% is what survived — not the fabricated 99%.
    assert next(m for m in res["gainers"] if m["ticker"] == "INDEXUP")["pct"] == 4.0


def test_top_movers_ignores_pack_tiles_for_non_daily_timeframes(tmp_path):
    """The pack carries one session; a 1W board must not be fed a 1D number."""
    from engine.marketing.movers_source import load_movers, top_movers
    root = _movers_fixture(tmp_path, trade_date=_sessions_ago(1))
    res = top_movers(load_movers(root), tf="1W", n=8, min_abs=3.0)
    assert [m["ticker"] for m in res["gainers"]] == ["INDEXUP"]


def test_top_movers_tier_map_still_drops_t3_on_pack_rows(tmp_path):
    from engine.marketing.movers_source import load_movers, top_movers
    root = _movers_fixture(tmp_path, trade_date=_sessions_ago(1))
    res = top_movers(load_movers(root), n=8, min_abs=3.0,
                     tier_map={"WILDUP": "T3", "INDEXUP": "T1", "WILDDOWN": "T2"})
    assert [m["ticker"] for m in res["gainers"]] == ["INDEXUP"]
    assert [m["ticker"] for m in res["losers"]] == ["WILDDOWN"]


def test_absent_pack_leaves_the_board_exactly_as_it_was(tmp_path):
    from engine.marketing.movers_source import load_movers, top_movers
    _write_heatmap(tmp_path, [
        {"t": "INDEXUP", "name": "Index Up", "sector": "Tech", "perf": {"1D": 4.0}},
    ], asof=_sessions_ago(1))
    data = load_movers(tmp_path)
    assert data["pack_tiles"] == []
    assert [m["ticker"] for m in top_movers(data, n=8, min_abs=3.0)["gainers"]] == ["INDEXUP"]


def test_mover_facts_scopes_the_index_claim_to_the_board_the_row_came_from(tmp_path):
    """A non-index name may not be called one of the biggest moves IN THE INDEX."""
    from engine.marketing.movers_source import mover_facts
    index_row = {"ticker": "INDEXDN", "name": "x", "pct": -8.0, "sector": "Tech",
                 "source": "sp500_heatmap"}
    pack_row = {"ticker": "WILDDOWN", "name": "y", "pct": -15.0, "sector": "",
                "source": "hot_tape_pack"}
    index_text = " ".join(f["text"] for f in mover_facts(index_row)["facts"])
    pack_text = " ".join(f["text"] for f in mover_facts(pack_row)["facts"])
    assert "in the index" in index_text
    assert "in the index" not in pack_text
    assert "on the tape" in pack_text
    # A row with no source at all keeps the historical wording (the heatmap is
    # the only thing that ever produced one).
    legacy = mover_facts({"ticker": "OLD", "name": "z", "pct": -9.0, "sector": ""})
    assert "in the index" in " ".join(f["text"] for f in legacy["facts"])


# ─────────────────────────────────────────────────────────────────────────────
# 10. Press desk — the citation must follow the row, not the payload
# ─────────────────────────────────────────────────────────────────────────────

def test_press_mover_facts_cite_the_artifact_the_row_actually_came_from(tmp_path):
    """A pack row cited to the heatmap points at a file without that ticker."""
    from engine.press import desk_planner
    root = _movers_fixture(tmp_path, trade_date=_sessions_ago(1))
    facts = {f["id"]: f for f in desk_planner.mover_facts(root, n=8)}

    index_fact = facts["mover_gainers_INDEXUP"]
    assert index_fact["ref"] == "artifact:site/marketdata/sp500_heatmap.json#INDEXUP"
    assert index_fact["source_name"] == "Mastermind S&P 500 heatmap"

    pack_fact = facts["mover_gainers_WILDUP"]
    assert pack_fact["ref"] == "artifact:data/marketing/hot_tape_pack.json#WILDUP"
    assert pack_fact["source_name"] == "Mastermind hot-tape pack"
    # Dated by its OWN session, and no "(WILDUP, )" placeholder parenthetical.
    assert pack_fact["dated"] == _sessions_ago(1)
    assert "(" not in pack_fact["text"]
    assert f"session of {_sessions_ago(1)}" in pack_fact["text"]
