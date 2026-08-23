"""tests/test_topup_thetadata_legacy.py — AD-1T1 §G/§H characterization suite.

(F17) The legacy `scripts/topup_thetadata_day.py --roots [--date]` contract was
UNTESTED before AD-1T1 (zero repo tests referenced the topup writer). This
suite pins the exit-code triple, `_merge_day` date-replacement semantics, and
`_last_weekday_before` BEFORE trusting any of the new `--daily`/`@universe`/
writer-exclusion code added alongside it (spec
`research/AD1T1_INCREMENTAL_CADENCE_SPEC_2026-08-22.md` §G/§H).

Also covers: the additive flock (refusal -> existing exit-1 shape, §B/§G),
the F9 tmp-file rename, and `--roots @universe` (F10) compatibility.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

import scripts.topup_thetadata_day as topup


# ── fixtures ─────────────────────────────────────────────────────────────────
def _df(day: date, n: int = 2, **extra_cols) -> pd.DataFrame:
    data = {"date": [pd.Timestamp(day)] * n, "strike": list(range(n))}
    data.update({k: [v] * n for k, v in extra_cols.items()})
    return pd.DataFrame(data)


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame({"date": pd.Series([], dtype="datetime64[ns]"),
                         "strike": pd.Series([], dtype="float64")})


class FakeTd:
    """Fake `collectors.thetadata` surface for the legacy 3-tier pull."""

    def __init__(self, plan: dict[tuple[str, str], object] | None = None,
                reachable: bool = True):
        self.plan = plan or {}
        self._reachable = reachable
        self.calls: list[tuple] = []

    def reachable(self) -> bool:
        return self._reachable

    def _get(self, tier: str, root: str, day: date):
        self.calls.append((tier, root, day))
        key = (tier, root)
        if key in self.plan:
            v = self.plan[key]
            if callable(v):
                return v(day)
            return v
        return _df(day)

    def bulk_eod(self, root, exp, start, end):
        return self._get("eod", root, start)

    def bulk_open_interest(self, root, exp, start, end):
        return self._get("oi", root, start)

    def bulk_greeks(self, root, exp, start, end, order=3):
        return self._get("greeks", root, start)


@pytest.fixture()
def store(tmp_path):
    return tmp_path / "thetadata_eod"


def _install_fake_td(monkeypatch, fake):
    import collectors.thetadata as real_td
    monkeypatch.setattr(real_td, "reachable", fake.reachable)
    monkeypatch.setattr(real_td, "bulk_eod", fake.bulk_eod)
    monkeypatch.setattr(real_td, "bulk_open_interest", fake.bulk_open_interest)
    monkeypatch.setattr(real_td, "bulk_greeks", fake.bulk_greeks)


# ── _last_weekday_before ─────────────────────────────────────────────────────
def test_last_weekday_before_monday_returns_friday():
    assert topup._last_weekday_before(date(2026, 8, 24)) == date(2026, 8, 21)


def test_last_weekday_before_tuesday_returns_monday():
    assert topup._last_weekday_before(date(2026, 8, 19)) == date(2026, 8, 18)


def test_last_weekday_before_sunday_returns_friday():
    assert topup._last_weekday_before(date(2026, 8, 23)) == date(2026, 8, 21)


# ── _merge_day date-replacement semantics ────────────────────────────────────
def test_merge_day_appends_to_empty_store(tmp_path):
    store = tmp_path / "s"
    day = date(2026, 7, 30)
    n = topup._merge_day(store, "eod", "SPY", day, _df(day, n=3))
    assert n == 3
    out = pd.read_parquet(store / "eod" / "SPY" / "2026.parquet")
    assert len(out) == 3


def test_merge_day_replaces_only_the_target_date_exact(tmp_path):
    """The merge REPLACES rows for the target date and byte-preserves every
    other date in the same year parquet (§H writer: unrelated dates
    byte-preserved after a merge)."""
    store = tmp_path / "s"
    d1, d2 = date(2026, 7, 29), date(2026, 7, 30)
    topup._merge_day(store, "eod", "SPY", d1, _df(d1, n=2, tag="first"))
    topup._merge_day(store, "eod", "SPY", d2, _df(d2, n=2, tag="first"))
    # Re-merge d2 with DIFFERENT rows — d1 must be untouched.
    topup._merge_day(store, "eod", "SPY", d2, _df(d2, n=5, tag="second"))
    out = pd.read_parquet(store / "eod" / "SPY" / "2026.parquet")
    d1_rows = out[pd.to_datetime(out["date"]) == pd.Timestamp(d1)]
    d2_rows = out[pd.to_datetime(out["date"]) == pd.Timestamp(d2)]
    assert len(d1_rows) == 2
    assert (d1_rows["tag"] == "first").all()
    assert len(d2_rows) == 5
    assert (d2_rows["tag"] == "second").all()


def test_merge_day_empty_fresh_frame_is_a_noop(tmp_path):
    store = tmp_path / "s"
    day = date(2026, 7, 30)
    n = topup._merge_day(store, "eod", "SPY", day, _empty_df())
    assert n == 0
    assert not (store / "eod" / "SPY" / "2026.parquet").exists()


def test_merge_day_writes_to_the_fresh_row_year_not_the_call_year(tmp_path):
    """A Dec-session row lands in the SESSION's year parquet even if merged
    from a caller that thinks of `day` differently — §A4 year-boundary rule."""
    store = tmp_path / "s"
    day = date(2025, 12, 31)
    topup._merge_day(store, "eod", "SPY", day, _df(day))
    assert (store / "eod" / "SPY" / "2025.parquet").exists()
    assert not (store / "eod" / "SPY" / "2026.parquet").exists()


# ── F9: tmp file naming ──────────────────────────────────────────────────────
def test_write_atomic_tmp_suffix_does_not_match_the_parquet_glob(tmp_path):
    """(F9) `{YYYY}.parquet.tmp` must NOT match `*.parquet` — the shape the
    store readers glob on (`engine/thetadata_store.py`, `Path.glob`)."""
    dest = tmp_path / "eod" / "SPY" / "2026.parquet"
    tmp = topup._tmp_path(dest)
    assert tmp.name == "2026.parquet.tmp"
    assert not tmp.match("*.parquet")


def test_merge_day_leaves_no_tmp_file_behind(tmp_path):
    store = tmp_path / "s"
    day = date(2026, 7, 30)
    topup._merge_day(store, "eod", "SPY", day, _df(day))
    leftovers = list((store / "eod" / "SPY").glob("*.tmp"))
    assert leftovers == []


# ── _has_day ─────────────────────────────────────────────────────────────────
def test_has_day_false_when_file_absent(tmp_path):
    assert topup._has_day(tmp_path / "s", "eod", "SPY", date(2026, 7, 30)) is False


def test_has_day_true_after_merge(tmp_path):
    store = tmp_path / "s"
    day = date(2026, 7, 30)
    topup._merge_day(store, "eod", "SPY", day, _df(day))
    assert topup._has_day(store, "eod", "SPY", day) is True


def test_has_day_false_on_corrupt_parquet(tmp_path):
    store = tmp_path / "s"
    d = store / "eod" / "SPY"
    d.mkdir(parents=True)
    (d / "2026.parquet").write_bytes(b"not a parquet file")
    assert topup._has_day(store, "eod", "SPY", date(2026, 7, 30)) is False


# ── legacy exit-code triple (characterization, F17) ─────────────────────────
def test_legacy_exit_0_when_all_roots_complete(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup.main(["--roots", "SPY,QQQ", "--date", "2026-07-30"])
    assert rc == 0
    assert topup._has_day(store, "eod", "SPY", date(2026, 7, 30))
    assert topup._has_day(store, "greeks", "QQQ", date(2026, 7, 30))


def test_legacy_exit_2_when_all_roots_vendor_empty(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    fake = FakeTd(plan={
        ("eod", "SPY"): _empty_df(), ("oi", "SPY"): _empty_df(), ("greeks", "SPY"): _empty_df(),
    })
    _install_fake_td(monkeypatch, fake)
    rc = topup.main(["--roots", "SPY", "--date", "2026-07-30"])
    assert rc == 2


def test_legacy_exit_1_when_partial(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    fake = FakeTd(plan={("eod", "SPY"): _empty_df()})
    _install_fake_td(monkeypatch, fake)
    rc = topup.main(["--roots", "SPY", "--date", "2026-07-30"])
    assert rc == 1
    # oi/greeks did merge even though eod was empty for this root.
    assert topup._has_day(store, "oi", "SPY", date(2026, 7, 30))
    assert not topup._has_day(store, "eod", "SPY", date(2026, 7, 30))


def test_legacy_default_date_is_last_weekday_before_today(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    topup.main(["--roots", "SPY"])
    expected = topup._last_weekday_before(date.today())
    assert any(day == expected for _, _, day in fake.calls)


def test_legacy_backfill_running_refuses_exit_1(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: True)
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup.main(["--roots", "SPY", "--date", "2026-07-30"])
    assert rc == 1
    assert fake.calls == []


def test_legacy_terminal_unreachable_exit_2(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    fake = FakeTd(reachable=False)
    _install_fake_td(monkeypatch, fake)
    rc = topup.main(["--roots", "SPY", "--date", "2026-07-30"])
    assert rc == 2


def test_legacy_store_resolution_failure_exit_1(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("no store")
    monkeypatch.setattr(topup, "resolve_thetadata_store", _boom)
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    rc = topup.main(["--roots", "SPY", "--date", "2026-07-30"])
    assert rc == 1


def test_legacy_already_present_makes_zero_vendor_calls(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    day = date(2026, 7, 30)
    for tier in topup.TIERS:
        topup._merge_day(store, tier, "SPY", day, _df(day))
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup.main(["--roots", "SPY", "--date", "2026-07-30"])
    assert rc == 0
    assert fake.calls == []


# ── writer-lock refusal keeps the legacy exit-1 shape (§B/§G additive) ──────
def test_legacy_lock_refusal_exits_1_and_mutates_nothing(store, monkeypatch, capsys):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    store.mkdir(parents=True)
    with topup._writer_lock(store) as acquired:
        assert acquired is True
        rc = topup.main(["--roots", "SPY", "--date", "2026-07-30"])
    assert rc == 1
    assert fake.calls == []
    assert not (store / "eod" / "SPY").exists()
    out = capsys.readouterr().out
    assert json.loads(out.strip().splitlines()[-1]) == {"event": "writer_locked", "mode": "legacy"}


# ── @universe catch-up mode (F10) ───────────────────────────────────────────
def test_roots_at_universe_resolves_via_resolve_universe(store, monkeypatch):
    calls = {"n": 0}

    def _fake_resolve_universe():
        calls["n"] += 1
        return ["SPY", "QQQ", "AAPL"]

    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    monkeypatch.setattr("scripts.backfill_thetadata_eod._resolve_universe",
                        _fake_resolve_universe)
    fake = FakeTd()
    _install_fake_td(monkeypatch, fake)
    rc = topup.main(["--roots", "@universe", "--date", "2026-07-30"])
    assert rc == 0
    assert calls["n"] == 1
    pulled_roots = {root for _, root, _ in fake.calls}
    assert pulled_roots == {"SPY", "QQQ", "AAPL"}


def test_roots_at_universe_same_exit_code_triple_as_legacy(store, monkeypatch):
    monkeypatch.setattr(topup, "resolve_thetadata_store", lambda **kw: str(store))
    monkeypatch.setattr(topup, "_backfill_running", lambda: False)
    monkeypatch.setattr("scripts.backfill_thetadata_eod._resolve_universe",
                        lambda: ["SPY"])
    fake = FakeTd(reachable=False)
    _install_fake_td(monkeypatch, fake)
    rc = topup.main(["--roots", "@universe", "--date", "2026-07-30"])
    assert rc == 2


# ── CLI validation ───────────────────────────────────────────────────────────
def test_daily_and_roots_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        topup.main(["--daily", "--roots", "SPY"])


def test_roots_required_unless_daily():
    with pytest.raises(SystemExit):
        topup.main([])


def test_workers_above_hard_cap_rejected():
    with pytest.raises(SystemExit):
        topup.main(["--daily", "--workers", "7"])
