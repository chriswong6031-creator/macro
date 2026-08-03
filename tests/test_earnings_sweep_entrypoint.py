"""The nightly earnings sweep must sweep the UNIVERSE, and its tripwire must see coverage.

OIP E8 / E5 diagnosis, 2026-07-29.  ``data/earnings/earnings.parquet`` held 1364 rows of
which exactly 3 were fresh — AAPL, NVDA, JPM.  Two independent defects, stacked:

1. **daily.yml ran the smoke test.**  ``collectors/equity_earnings.__main__`` was
   ``ts = sys.argv[1:] or ["AAPL", "NVDA", "JPM"]`` followed by
   ``fetch_earnings(force=True, max_new=len(ts), tickers=ts)`` — and daily.yml's
   collect_tail step invokes ``python -m collectors.equity_earnings`` bare.  Passing
   ``tickers=`` bypasses ``_universe()`` entirely, so the "~66 weekday, whole universe"
   sweep the step comment promises had never once run in production.  Nasdaq was never
   the problem: probed live the same day, the calendar endpoint returned HTTP 200 with
   305 / 61 / 132 rows for 2026-07-30 / 07-31 / 08-03.  After the fix a bare run swept
   1513 names and stamped 1066 of them today.
2. **The tripwire graded max(as_of).**  ``scripts/audit_earnings_freshness.audit()``
   returned ``ok: true, warnings: [], sla_ok: true`` over that store, because ONE fresh
   row satisfies a max-based SLA.  It was structurally incapable of catching (1) — the
   presence-vs-coverage class.  It now grades the SHARE of rows inside the SLA and
   escalates a stale-at-scale store to a line-start ``::error``.

These tests pin both.  Hermetic: no network (the collector's own network functions are
monkeypatched), no live stores.

Run: .venv/bin/python -m pytest tests/test_earnings_sweep_entrypoint.py -q
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import collectors.equity_earnings as ee  # noqa: E402
from lib import nyse_calendar  # noqa: E402

DAILY = (ROOT / ".github" / "workflows" / "daily.yml").read_text()
COLLECTOR_SRC = (ROOT / "collectors" / "equity_earnings.py").read_text()


# ─────────────────────────────────────────────────────────────── the entry point


def test_daily_invokes_the_collector_bare():
    """Premise of the whole bug: the nightly passes NO ticker arguments."""
    assert "python -m collectors.equity_earnings \\\n" in DAILY, (
        "daily.yml's invocation shape changed — re-check which code path it reaches"
    )
    step = DAILY.split("python -m collectors.equity_earnings", 1)[1].split("\n", 1)[0]
    assert step.strip() in ("\\", ""), (
        f"daily.yml now passes arguments to the collector ({step!r}); a ticker list "
        "switches it back to the SMOKE path"
    )


def test_no_hardcoded_ticker_list_in_collector_code():
    """A ticker-list literal in this module's CODE is the bug (docstrings exempt: the
    postmortem above quotes the old line on purpose)."""
    import ast
    tree = ast.parse(COLLECTOR_SRC)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)) or len(node.elts) < 2:
            continue
        vals = [e.value for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if len(vals) != len(node.elts):
            continue
        # a ticker list looks like short ALL-CAPS alphabetic symbols
        if all(1 <= len(v) <= 5 and v.isalpha() and v.isupper() for v in vals):
            offenders.append(vals)
    assert not offenders, (
        f"hardcoded ticker list(s) in collector code: {offenders} — a bare "
        "`python -m collectors.equity_earnings` must sweep _universe(), never a fixed list"
    )


def _stub_network(monkeypatch, tmp_path, universe, cal_rows):
    """Replace the two network functions + the cache path; return the calls seen."""
    seen = {"calendar": 0, "surprises": []}

    def fake_calendar_sweep(session, uni):
        seen["calendar"] += 1
        seen["universe"] = set(uni)
        return {t: dict(cal_rows[t]) for t in cal_rows if t in uni}, False

    def fake_surprises(session, sym):
        seen["surprises"].append(sym)
        return [{"qtr": "Jun 2026", "reported": "7/1/2026", "eps": 1.0,
                 "consensus": 0.9, "surprise_pct": 11.1}]

    monkeypatch.setattr(ee, "_calendar_sweep", fake_calendar_sweep)
    monkeypatch.setattr(ee, "_surprises", fake_surprises)
    monkeypatch.setattr(ee, "_universe", lambda: set(universe))
    monkeypatch.setattr(ee, "_cache_path", lambda: tmp_path / "earnings.parquet")
    # the drip's politeness sleep is real wall-clock; 120 names × 0.25s per test is
    # 30s of CI for nothing when the network calls are already stubbed
    monkeypatch.setattr(ee.time, "sleep", lambda *_a, **_k: None)
    return seen


def test_bare_main_sweeps_the_whole_universe(monkeypatch, tmp_path):
    universe = {f"TK{i:03d}" for i in range(200)}
    cal = {t: {"next_date": "2026-08-14", "next_time": "time-after-hours",
               "eps_forecast": 1.23} for t in sorted(universe)[:150]}
    seen = _stub_network(monkeypatch, tmp_path, universe, cal)

    assert ee.main([]) == 0
    assert seen["universe"] == universe, "bare main() must sweep _universe()"

    out = pd.read_parquet(tmp_path / "earnings.parquet")
    assert len(out) == 150, f"expected the whole calendar hit persisted, got {len(out)}"
    today = datetime.now(timezone.utc).date().isoformat()
    assert (out["as_of"].astype(str).str.startswith(today)).sum() == 150


def test_bare_main_caps_the_surprise_drip(monkeypatch, tmp_path):
    """The expensive per-name call stays capped — the calendar is what must be whole."""
    universe = {f"TK{i:03d}" for i in range(400)}
    cal = {t: {"next_date": "2026-08-14", "next_time": None, "eps_forecast": None}
           for t in sorted(universe)}
    seen = _stub_network(monkeypatch, tmp_path, universe, cal)

    ee.main([])
    assert len(seen["surprises"]) == ee.DEFAULT_MAX_NEW == 120
    # ...but every calendar hit is persisted, not just the dripped batch
    assert len(pd.read_parquet(tmp_path / "earnings.parquet")) == 400


def test_explicit_tickers_still_run_the_smoke_path(monkeypatch, tmp_path):
    universe = {f"TK{i:03d}" for i in range(200)}
    cal = {"AAPL": {"next_date": "2026-08-14", "next_time": None, "eps_forecast": None},
           "NVDA": {"next_date": "2026-08-26", "next_time": None, "eps_forecast": None}}
    seen = _stub_network(monkeypatch, tmp_path, universe, cal)

    assert ee.main(["AAPL", "NVDA"]) == 0
    assert seen["universe"] == {"AAPL", "NVDA"}, "named tickers must not sweep the universe"

    seen["universe"] = None
    assert ee.main(["--tickers", "aapl,nvda"]) == 0
    assert seen["universe"] == {"AAPL", "NVDA"}, "--tickers is the same smoke path"


def test_a_bot_walled_sweep_keeps_the_cache_and_annotates(monkeypatch, tmp_path, capsys):
    """The Akamai-wall path must stay non-destructive AND visible."""
    cache = tmp_path / "earnings.parquet"
    pd.DataFrame([{"ticker": "AAPL", "next_date": "2026-08-01", "next_time": None,
                   "eps_forecast": None, "surprises_json": "[]",
                   "as_of": "2026-06-19T00:00:00+00:00"}]).set_index("ticker").to_parquet(cache)

    monkeypatch.setattr(ee, "_universe", lambda: {"AAPL", "MSFT"})
    monkeypatch.setattr(ee, "_cache_path", lambda: cache)
    monkeypatch.setattr(ee, "_calendar_sweep", lambda s, u: ({}, True))

    assert ee.main([]) == 0
    out = pd.read_parquet(cache)
    assert len(out) == 1 and out.loc["AAPL", "as_of"].startswith("2026-06-19"), (
        "a blocked sweep must leave the cache byte-identical"
    )
    # nothing was written, so the run reports the empty result loudly
    assert len(pd.read_parquet(cache)) == 1


def test_empty_sweep_annotation_starts_the_line(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(ee, "_universe", lambda: {"AAPL"})
    monkeypatch.setattr(ee, "_cache_path", lambda: tmp_path / "absent.parquet")
    monkeypatch.setattr(ee, "_calendar_sweep", lambda s, u: ({}, False))
    ee.main([])
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "::" in ln]
    assert lines, "an empty production sweep must annotate"
    for ln in lines:
        assert ln.startswith("::"), f"annotation not at line start: {ln!r}"
    assert any("earnings-sweep-empty" in ln for ln in lines)


# ───────────────────────────────────────────────────── the coverage-aware tripwire


def _write_store(tmp_path: Path, fresh_n: int, stale_n: int) -> Path:
    d = tmp_path / "earnings"
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=40)).isoformat()
    rows = []
    for i in range(fresh_n):
        rows.append({"ticker": f"FR{i:04d}", "next_date": "2026-08-14", "next_time": None,
                     "eps_forecast": None, "surprises_json": "[]", "as_of": now.isoformat()})
    for i in range(stale_n):
        rows.append({"ticker": f"ST{i:04d}", "next_date": "2026-09-14", "next_time": None,
                     "eps_forecast": None, "surprises_json": "[]", "as_of": old})
    pd.DataFrame(rows).set_index("ticker").to_parquet(d / "earnings.parquet")
    return d / "earnings.parquet"


def _audit(monkeypatch, tmp_path):
    import lib.config as cfg
    import scripts.audit_earnings_freshness as af
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    return af, af.audit()


def test_three_fresh_rows_in_a_big_store_is_an_error_not_a_green(monkeypatch, tmp_path):
    """THE regression: the exact 2026-07-29 store shape must no longer read green."""
    _write_store(tmp_path, fresh_n=3, stale_n=1361)
    af, result = _audit(monkeypatch, tmp_path)
    assert result["errors"], "a 3-of-1364 store must escalate, not pass"
    assert result["detail"]["fresh_rows"] == 3
    assert result["detail"]["fresh_share"] < 0.01
    # the OLD check still reports fresh — which is precisely why it was not enough
    assert result["detail"]["sla_ok"] is True
    assert "coverage_ok" not in result["detail"]


def test_a_real_sweep_passes_coverage(monkeypatch, tmp_path):
    """70% fresh is the measured shape of a healthy sweep (1066 of 1513)."""
    _write_store(tmp_path, fresh_n=1066, stale_n=447)
    af, result = _audit(monkeypatch, tmp_path)
    assert not result["errors"] and not result["warnings"]
    assert result["detail"]["coverage_ok"] is True
    assert result["detail"]["fresh_share"] > ee_min_share(af)


def ee_min_share(af) -> float:
    return af.MIN_FRESH_SHARE


def test_the_sla_was_not_widened(monkeypatch, tmp_path):
    """A wholly-stale store must still say stale — coverage is an ADDITION."""
    import scripts.audit_earnings_freshness as af
    assert af.DEFAULT_MAX_AGE_TD == 2, "the 2-trading-day SLA is not negotiable here"
    _write_store(tmp_path, fresh_n=0, stale_n=800)
    _, result = _audit(monkeypatch, tmp_path)
    assert any("stale" in w.lower() for w in result["warnings"]), "age check must still fire"
    assert result["errors"], "and coverage must fire too"


def test_small_store_stays_a_warning(monkeypatch, tmp_path):
    """Below the plausibility floor the share is not meaningful — don't cry ::error."""
    _write_store(tmp_path, fresh_n=1, stale_n=20)
    _, result = _audit(monkeypatch, tmp_path)
    assert not result["errors"]
    assert any("suspiciously small" in w for w in result["warnings"])
    assert any("stale AT SCALE" in w for w in result["warnings"])


def test_stale_at_scale_annotation_starts_the_line(monkeypatch, tmp_path, capsys):
    _write_store(tmp_path, fresh_n=3, stale_n=1361)
    import lib.config as cfg
    import scripts.audit_earnings_freshness as af
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    rc = af.run_as_main(strict=False)
    assert rc == 0, "the nightly step is non-fatal by design"
    out = capsys.readouterr().out
    ann = [ln for ln in out.splitlines() if "::" in ln]
    assert ann
    for ln in ann:
        assert ln.startswith("::"), f"annotation not at line start: {ln!r}"
    assert any(ln.startswith("::error title=earnings-stale::") for ln in ann), (
        "a stale-at-scale store must emit a line-start ::error"
    )


def test_strict_mode_fails_on_a_coverage_error(monkeypatch, tmp_path):
    _write_store(tmp_path, fresh_n=3, stale_n=1361)
    import lib.config as cfg
    import scripts.audit_earnings_freshness as af
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path)
    assert af.run_as_main(strict=True) == 1


@pytest.mark.parametrize("keys", [
    ("fresh_rows", "fresh_share", "min_fresh_share"),
])
def test_detail_publishes_the_denominator(monkeypatch, tmp_path, keys):
    """The artifact must carry the numbers, not just a verdict — nulls printed."""
    _write_store(tmp_path, fresh_n=60, stale_n=60)
    _, result = _audit(monkeypatch, tmp_path)
    for k in keys:
        assert k in result["detail"], f"detail missing {k}"


# ═══════════ review minors: drip cadence, denominator, ok-semantics, calendar ══════


def test_the_surprise_drip_actually_backfills_across_nights(monkeypatch, tmp_path):
    """MINOR 2. `stale()` used to grade `as_of`, which the CALENDAR sweep bumps for every
    name it finds. Once the sweep really covered the universe (the E5 fix), every swept
    name looked fresh the next night, so the 120/night surprise drip selected NOTHING and
    4 of 1364 names had history forever. Freshness of the two facts is tracked separately."""
    universe = {f"TK{i:04d}" for i in range(400)}
    cal = {t: {"next_date": "2026-08-14", "next_time": None, "eps_forecast": 1.0}
           for t in sorted(universe)}
    seen = _stub_network(monkeypatch, tmp_path, universe, cal)

    counts = []
    for _ in range(3):
        seen["surprises"].clear()
        ee.main([])
        df = pd.read_parquet(tmp_path / "earnings.parquet")
        with_hist = int(df["surprises_json"].fillna("[]").apply(
            lambda s: bool(json.loads(s or "[]"))).sum())
        counts.append((len(seen["surprises"]), with_hist))

    assert [c[0] for c in counts] == [120, 120, 120], (
        f"each night must drip a full batch, got {[c[0] for c in counts]}"
    )
    assert [c[1] for c in counts] == [120, 240, 360], (
        f"history must ACCUMULATE, got {[c[1] for c in counts]} — a flat series means the "
        "drip is selecting the same names (or none) every night"
    )


def test_a_calendar_refresh_does_not_reset_the_surprise_clock(monkeypatch, tmp_path):
    """The two stamps must be independent: sweeping the calendar again must not make a
    name with 8-day-old surprise history look freshly dripped."""
    universe = {"AAA", "BBB"}
    cal = {t: {"next_date": "2026-08-14", "next_time": None, "eps_forecast": 1.0}
           for t in universe}
    _stub_network(monkeypatch, tmp_path, universe, cal)
    ee.main([])
    df = pd.read_parquet(tmp_path / "earnings.parquet")
    assert "surprises_as_of" in df.columns, "the surprise stamp must be its own column"
    assert df["surprises_as_of"].notna().all()

    # age the SURPRISE stamp only, leave as_of fresh, and confirm the name is re-selected
    old = (datetime.now(timezone.utc) - timedelta(days=ee.REFRESH_DAYS + 3)).isoformat()
    df["surprises_as_of"] = old
    df.to_parquet(tmp_path / "earnings.parquet")
    seen2 = _stub_network(monkeypatch, tmp_path, universe, cal)
    ee.main([])
    assert set(seen2["surprises"]) == universe, (
        f"stale surprise history must be re-dripped even when as_of is fresh; "
        f"got {seen2['surprises']}"
    )


class TestAuditDenominatorAndSemantics:
    def test_ok_reflects_the_errors_channel(self, monkeypatch, tmp_path):
        """MINOR 8: the artifact published ok:true beside errors:[...]."""
        _write_store(tmp_path, fresh_n=3, stale_n=1361)
        _, result = _audit(monkeypatch, tmp_path)
        assert result["errors"]
        assert result["ok"] is False, "ok must mean 'nothing in this audit is wrong'"

    def test_ok_is_true_on_a_genuinely_clean_store(self, monkeypatch, tmp_path):
        _write_store(tmp_path, fresh_n=1066, stale_n=447)
        _, result = _audit(monkeypatch, tmp_path)
        assert not result["errors"] and not result["warnings"]
        assert result["ok"] is True

    def test_the_denominator_is_the_sweep_window_not_the_whole_store(
            self, monkeypatch, tmp_path):
        """MINOR 3: the store grows monotonically and keeps every name it has ever seen,
        while the sweep only reaches ~66 weekdays ahead. Names reporting beyond that
        window cannot be refreshed by a sweep and must not dilute its score."""
        import pandas as pd
        d = tmp_path / "earnings"
        d.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        far = (date.today() + timedelta(days=300)).isoformat()   # beyond the window
        near = (date.today() + timedelta(days=10)).isoformat()   # inside it
        rows = [{"ticker": f"IN{i:04d}", "next_date": near, "next_time": None,
                 "eps_forecast": None, "surprises_json": "[]", "as_of": now}
                for i in range(80)]
        rows += [{"ticker": f"OUT{i:04d}", "next_date": far, "next_time": None,
                  "eps_forecast": None, "surprises_json": "[]",
                  "as_of": "2026-01-02T00:00:00+00:00"} for i in range(900)]
        pd.DataFrame(rows).set_index("ticker").to_parquet(d / "earnings.parquet")

        _, result = _audit(monkeypatch, tmp_path)
        det = result["detail"]
        assert det["denominator_basis"] == "sweep_window"
        assert det["fresh_denominator"] == 80, (
            f"denominator {det['fresh_denominator']} — the 900 far-dated names must not "
            "count against a sweep that cannot reach them"
        )
        assert det["fresh_share"] == 1.0
        assert not result["errors"], (
            "graded against the whole store this would read 80/980 = 8% and cry stale"
        )

    def test_the_denominator_falls_back_when_next_date_is_unusable(
            self, monkeypatch, tmp_path):
        _write_store(tmp_path, fresh_n=60, stale_n=60)   # next_date present but far/near mix
        _, result = _audit(monkeypatch, tmp_path)
        assert result["detail"]["denominator_basis"] in ("sweep_window", "whole_store")
        assert result["detail"]["fresh_denominator"] > 0

    def test_the_message_quotes_the_denominator_it_actually_used(
            self, monkeypatch, tmp_path):
        _write_store(tmp_path, fresh_n=3, stale_n=1361)
        _, result = _audit(monkeypatch, tmp_path)
        det = result["detail"]
        assert str(det["fresh_denominator"]) in result["errors"][0]


class TestAuditUsesTheSessionCalendar:
    def test_a_holiday_week_is_not_counted_as_extra_staleness(self):
        """MINOR 9: pd.bdate_range counts exchange HOLIDAYS as business days, so a store
        spanning one read staler than it is — the opposite of the old docstring's claim."""
        import scripts.audit_earnings_freshness as af
        # 2026-07-03 is the observed Independence Day holiday (July 4 is a Saturday)
        assert not nyse_calendar.is_session(date(2026, 7, 3))
        import pandas as pd
        naive = max(0, len(pd.bdate_range(date(2026, 7, 2), date(2026, 7, 6))) - 1)
        exact = af._bdate_range_age(date(2026, 7, 2), date(2026, 7, 6))
        # the window spans exactly one holiday, so the two measures must differ by 1
        assert naive - exact == 1, (
            f"holiday-blind distance {naive} vs session-exact {exact} — the 2026-07-03 "
            "closure must account for the whole difference"
        )
        assert exact is not None and exact < naive, (
            f"session-calendar age {exact} must be below the holiday-blind {naive}"
        )

    def test_age_is_anchored_on_the_last_COMPLETED_session(self):
        """The audit anchors on datetime.now(timezone.utc).date(), which rolls over at
        20:00 ET the evening before — a to_date distance therefore reported every store as
        a session staler than it was for the first four hours of each UTC day."""
        import scripts.audit_earnings_freshness as af
        last = nyse_calendar.expected_last_session()
        assert af._session_age(last) == 0, (
            "a store holding the last COMPLETED session must read 0 trading days old"
        )
        # ...and the UTC calendar date is NOT the anchor: at 00:00-04:00 UTC the ET session
        # of the previous day is the newest completed one, and a from->to distance would
        # have called that store a session stale.
        assert af._session_age(date.today()) == 0


# ═══════════════════════════════════════════════════════════════════════════
# F. The 07-29→08-02 starvation cancel + the single-stamp as_of contract
#
# Second freeze, same store, new mechanism.  #3979 fixed the smoke-path bug on
# 07-29 — and the fixed sweep then never ran once: collect_tail's two
# shadow-importance scorers had outgrown their "~13-14m combined" estimate to
# 80-120m+ (they re-score the full, nightly-accruing qbus store), the job died
# at its 150m cap five nights running, and every step behind the scorers — the
# earnings sweep, its tripwire, qledger, CCW, and "commit tail data" — was
# SKIPPED.  On 2026-08-02 the store still carried the pre-fix two-stamp shape
# (1361 rows at 06-19 beside the 3 smoke rows at 07-28).
#
# These tests pin the three workflow defenses (earnings before the scorer band;
# the scorers step-bounded; the commit reachable on cancel) and the collector's
# single-stamp contract (one certified sweep → one as_of for the whole file;
# mixed stamps only ever mean a partial refresh).
# ═══════════════════════════════════════════════════════════════════════════

import yaml as _yaml


def _collect_tail_steps():
    wf = _yaml.safe_load(DAILY)
    return wf["jobs"]["collect_tail"]["steps"]


def _step_index(steps, fragment):
    for i, s in enumerate(steps):
        if fragment in (s.get("name") or ""):
            return i, s
    raise AssertionError(f"no collect_tail step named like {fragment!r}")


class TestCollectTailStarvationDefenses:
    def test_earnings_sweep_runs_before_the_shadow_importance_band(self):
        """The cheap ~4m sweep must never queue behind the unbudgeted scorers."""
        steps = _collect_tail_steps()
        i_sweep, _ = _step_index(steps, "US earnings calendar sweep")
        i_trip, _ = _step_index(steps, "earnings freshness tripwire")
        i_w3, _ = _step_index(steps, "W3 scorer")
        i_w4, _ = _step_index(steps, "W4 PIT-correct scorer")
        assert i_sweep < i_trip < i_w3 < i_w4, (
            f"order sweep={i_sweep} tripwire={i_trip} W3={i_w3} W4={i_w4} — the "
            "earnings band moved back behind the scorers; that is the 07-29→08-02 "
            "starvation shape (five nights of job-timeout cancels, sweep SKIPPED)"
        )

    def test_shadow_importance_scorers_are_step_bounded(self):
        """Each scorer needs timeout-minutes + continue-on-error so a blowout is
        truncated loudly instead of cancelling the job and starving the tail band."""
        steps = _collect_tail_steps()
        job = _yaml.safe_load(DAILY)["jobs"]["collect_tail"]
        bound_sum = 0
        for frag in ("W3 scorer", "W4 PIT-correct scorer"):
            _, step = _step_index(steps, frag)
            assert step.get("timeout-minutes"), f"{frag}: no step timeout — unbounded again"
            assert step.get("continue-on-error") is True, (
                f"{frag}: a step timeout without continue-on-error fails the job "
                "and still skips every later step"
            )
            bound_sum += step["timeout-minutes"]
        # the two bounds together must leave the rest of the band real headroom
        assert bound_sum <= job["timeout-minutes"] - 60, (
            f"scorer bounds sum {bound_sum}m leave <60m of the job's "
            f"{job['timeout-minutes']}m for tape-flow/census/earnings/commit"
        )

    def test_commit_tail_data_runs_on_cancel(self):
        """if: always() — the grace-window backstop.  Five nights of completed
        accrual evaporated because the commit was skipped on cancel and the next
        night's clean checkout discarded the uncommitted writes."""
        _, step = _step_index(_collect_tail_steps(), "commit tail data")
        assert str(step.get("if", "")).strip() == "always()"


class TestSingleStampAsOfContract:
    """One certified full sweep → ONE as_of for the whole file (standing law:
    one freshness anchor key, one writer, one stamp)."""

    OLD = "2026-06-19T00:00:00+00:00"

    def _seed_cache(self, tmp_path, names):
        rows = [{"ticker": t, "next_date": "2026-05-01", "next_time": None,
                 "eps_forecast": None, "surprises_json": "[]",
                 "surprises_as_of": self.OLD, "as_of": self.OLD} for t in names]
        pd.DataFrame(rows).set_index("ticker").to_parquet(tmp_path / "earnings.parquet")

    def test_full_sweep_single_stamps_every_row(self, monkeypatch, tmp_path):
        """Carried-forward names (no calendar row in the 66-weekday window) get the
        SAME stamp as swept names: their absence from the whole forward calendar is
        itself an observation made by this sweep."""
        universe = {f"TK{i:03d}" for i in range(100)}
        cal = {t: {"next_date": "2026-08-14", "next_time": None, "eps_forecast": 1.0}
               for t in sorted(universe)[:80]}                       # 80% >= floor
        self._seed_cache(tmp_path, [f"OLD{i}" for i in range(10)])   # not in tonight's cal
        _stub_network(monkeypatch, tmp_path, universe, cal)

        assert ee.main([]) == 0
        out = pd.read_parquet(tmp_path / "earnings.parquet")
        assert len(out) == 90
        stamps = set(out["as_of"].astype(str))
        assert len(stamps) == 1, (
            f"a certified full sweep left {len(stamps)} distinct as_of stamps — "
            "mixed-asof files force every consumer to gate per row"
        )
        assert next(iter(stamps)).startswith(
            datetime.now(timezone.utc).date().isoformat())

    def test_below_floor_sweep_keeps_old_stamps_honest(self, monkeypatch, tmp_path):
        """A broken sweep (coverage < MIN_SWEEP_COVERAGE) must NOT certify the file:
        uniform-stamping a partial refresh is how the 06-19 freeze hid behind a
        max()-based tripwire."""
        universe = {f"TK{i:03d}" for i in range(100)}
        cal = {t: {"next_date": "2026-08-14", "next_time": None, "eps_forecast": 1.0}
               for t in sorted(universe)[:20]}                       # 20% < 50% floor
        self._seed_cache(tmp_path, [f"OLD{i}" for i in range(10)])
        _stub_network(monkeypatch, tmp_path, universe, cal)

        assert ee.main([]) == 0
        out = pd.read_parquet(tmp_path / "earnings.parquet")
        old = out.loc[[f"OLD{i}" for i in range(10)], "as_of"].astype(str)
        assert (old == self.OLD).all(), (
            "a below-floor sweep re-stamped carried-forward rows — rot certified "
            "as freshness"
        )

    def test_smoke_run_never_restamps_untouched_rows(self, monkeypatch, tmp_path):
        """--tickers touches its named subset only; every other row keeps its
        honest old stamp (a smoke run must never look like a full sweep)."""
        self._seed_cache(tmp_path, ["OLD0", "OLD1", "OLD2"])
        cal = {"AAPL": {"next_date": "2026-08-14", "next_time": None,
                        "eps_forecast": 1.0}}
        _stub_network(monkeypatch, tmp_path, {"AAPL"}, cal)

        assert ee.main(["--tickers", "AAPL"]) == 0
        out = pd.read_parquet(tmp_path / "earnings.parquet")
        assert out.loc["AAPL", "as_of"].startswith(
            datetime.now(timezone.utc).date().isoformat())
        old = out.loc[["OLD0", "OLD1", "OLD2"], "as_of"].astype(str)
        assert (old == self.OLD).all(), "smoke run restamped rows it never touched"


class TestUniverseUnionsHotTapePack:
    """TrendSpider supply widening: the sweep universe = breadth union ∪ Hot Tape
    liquid names.  The calendar sweep is date-keyed, so the wider set costs zero
    extra requests — membership only decides which returned rows are kept."""

    def _seed_breadth(self, root, names):
        d = root / "breadth"
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"x": [1] * len(names)}, index=pd.Index(names, name="ticker")
                     ).to_parquet(d / "constituents.parquet")

    def test_pack_tickers_join_the_universe(self, monkeypatch, tmp_path):
        self._seed_breadth(tmp_path, ["AAA", "BBB"])
        mk = tmp_path / "marketing"
        mk.mkdir()
        (mk / "hot_tape_pack.json").write_text(json.dumps(
            {"tickers": {"CCC": {}, "ddd": {}}}))
        monkeypatch.setattr(ee.config, "data_dir", lambda: tmp_path)
        assert ee._universe() == {"AAA", "BBB", "CCC", "DDD"}

    def test_absent_pack_fails_open_to_the_breadth_union(self, monkeypatch, tmp_path):
        self._seed_breadth(tmp_path, ["AAA", "BBB"])
        monkeypatch.setattr(ee.config, "data_dir", lambda: tmp_path)
        assert ee._universe() == {"AAA", "BBB"}

    def test_corrupt_pack_fails_open_too(self, monkeypatch, tmp_path):
        self._seed_breadth(tmp_path, ["AAA"])
        mk = tmp_path / "marketing"
        mk.mkdir()
        (mk / "hot_tape_pack.json").write_text("{not json")
        monkeypatch.setattr(ee.config, "data_dir", lambda: tmp_path)
        assert ee._universe() == {"AAA"}
