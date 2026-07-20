"""engine/prophet_stage_shadow.py — the live-Prophet × Stage forward-shadow.

This is the DEFINITIVE on-Prophet test the pre-registered backtest
(``research/PROPHET_STAGE_FUSION_PREREG.md`` §6) left open. The 2022-26 backtest
(``engine/prophet_stage_fusion.py``) was a MECHANISM test on the T1-T4 confluence
cascade as a PIT-replayable *proxy* for a Prophet-family timing entry — Prophet
itself has no backtestable history. This module tags Prophet's ACTUAL entries from
go-live with their stage-at-entry + last earnings-call context, then grades each
one at maturity, so the real on-Prophet answer accrues (the first 126-bar cohort
matures ~2026-12).

PURE ACCRUAL + MEASUREMENT. This module NEVER gates, ranks, or alters any Prophet
decision — every artifact it writes is display / shadow tier. The fusion
win-rate-gate construction is KILLED per ``research/DO_NOT_REBUILD.md``; this
shadow is a measurement, not a gate. A null here NEVER blocks or changes Prophet.

REUSE (measured identically to the backtest — nothing reinvented):
  * stage-at-entry  -> ``prophet_stage_fusion.stage_at_entry`` (PIT close[:entry]
      truncation → weinstein_stage.classify) and ``load_ticker_prices`` /
      ``load_bench_close``.
  * EC join         -> ``prophet_stage_fusion.load_ec_table`` / ``ec_index`` /
      ``ec_sent_at_entry`` (earnings_calls.parquet, most-recent call STRICTLY before
      entry).
  * grading         -> ``grading.terminal_state`` (clean15_126 & clean8_21) +
      ``grading.forward_metrics`` (21/63/126). Win = ``CLEAN_LIFTOFF``.

FORWARD LEDGER (house law): ``data/prophet_stage_shadow/ledger.jsonl`` is a
forward ledger; NIGHTLY IS THE SOLE ADVANCER of its grades. The grade advance is
gated on ``engine.ledger_lane.nightly_advance_enabled()`` (COLLECT_LANE=nightly) —
the same sentinel every other forward ledger uses. A non-nightly run TAGS entries
(PIT-fixed, idempotent) but does NOT advance grades. The tag itself is PIT-fixed at
entry, so an already-tagged id is NEVER re-tagged (idempotent).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from engine import grading, prophet_stage_fusion as psf
from engine.ledger_lane import nightly_advance_enabled

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Schema / constants                                                           #
# --------------------------------------------------------------------------- #
LEDGER_SCHEMA = "prophet_stage_shadow.ledger/v1"
SUMMARY_SCHEMA = "prophet_stage_shadow.v1"

# Grading parameterizations — the SAME two rulers the backtest uses (reused verbatim
# from prophet_stage_fusion so the shadow is graded identically to the mechanism test).
PARAM_CLEAN15_126 = psf.PARAM_CLEAN15_126   # liftoff 1.15, horizon 126 (positional)
PARAM_CLEAN8_21 = psf.PARAM_CLEAN8_21        # liftoff 1.08, horizon 21  (rotational)
FWD_HORIZONS = psf.FWD_HORIZONS              # (21, 63, 126)

# The longest horizon that must have elapsed (+ fill) before a horizon can grade.
FRESH_WEEKS_MAX = psf.FRESH_WEEKS_MAX        # fresh Stage-2 = weeks_in_stage <= 10
STAGE2 = psf.STAGE2

ACCRUAL_DISCLAIMER = (
    "accruing — first 126-day cohort matures ~2026-12; n is tiny until then; NOT "
    "yet decisive. The 2022-26 backtest on the T-cascade confluence proxy found no "
    "CI-clean win-rate edge (a quality right-shift only) — this forward-shadow is the "
    "definitive on-Prophet check, tagging Prophet's ACTUAL entries from go-live. "
    "Display / shadow tier only: it NEVER gates, ranks, or alters any Prophet decision."
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _shadow_dir(root: Path) -> Path:
    return Path(root) / "prophet_stage_shadow"


def ledger_path(root: Path) -> Path:
    return _shadow_dir(root) / "ledger.jsonl"


def summary_path(root: Path) -> Path:
    return _shadow_dir(root) / "summary.json"


# --------------------------------------------------------------------------- #
# Prophet entry enumeration — the canonical (asset, signal_date, id) list.     #
# --------------------------------------------------------------------------- #
def _clean_ec(v: float | None) -> float | None:
    return float(v) if (v is not None and pd.notna(v)) else None


def collect_prophet_entries(site_root: Path, data_root: Path) -> list[dict[str, Any]]:
    """Every Prophet entry (active + closed), de-duplicated by plan id.

    Sources (union, keyed by plan id — id = ``<TICKER>-<DIR>-<YYYYMMDD>``):
      * ``site/prophet/plans/*.json``   — per-plan trade_plan/v1 artifacts (signal_date)
      * ``site/prophet/index.json``     — active plans (``_signal_date``)
      * ``data/prophet/ledger.jsonl``   — closed outcome ledger (signal_date)

    Returns [{id, asset, signal_date, direction, source}]. The id is PIT-stable
    (never re-issued), so it is the idempotency key for the shadow ledger. Fail-open:
    an unreadable source is skipped with a warning, never raised.
    """
    site_root = Path(site_root)
    data_root = Path(data_root)
    entries: dict[str, dict[str, Any]] = {}

    def _add(pid: Any, asset: Any, signal_date: Any, direction: Any, source: str) -> None:
        if not pid or not asset or not signal_date:
            return
        pid = str(pid)
        if pid in entries:
            return  # keep-first (plans dir → index → ledger); id is PIT-stable
        entries[pid] = {
            "id": pid,
            "asset": str(asset),
            "signal_date": str(signal_date),
            "direction": str(direction or "BULL"),
            "source": source,
        }

    # 1. per-plan artifacts (the superset; includes closed plans still on disk)
    plans_dir = site_root / "prophet" / "plans"
    if plans_dir.exists():
        for p in sorted(plans_dir.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                log.warning("prophet_stage_shadow: unreadable plan %s (%s)", p, e)
                continue
            _add(d.get("id"), d.get("asset"),
                 d.get("signal_date") or d.get("_signal_date"),
                 d.get("direction"), "plan")

    # 2. active index entries
    idx_path = site_root / "prophet" / "index.json"
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            for p in idx.get("plans", []) or []:
                _add(p.get("id"), p.get("asset"),
                     p.get("_signal_date") or p.get("signal_date"),
                     p.get("direction"), "index")
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: unreadable index.json (%s)", e)

    # 3. closed ledger rows
    led = data_root / "prophet" / "ledger.jsonl"
    if led.exists():
        try:
            for line in led.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                r = json.loads(line)
                _add(r.get("id"), r.get("asset"), r.get("signal_date"),
                     r.get("direction"), "ledger")
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: unreadable prophet ledger (%s)", e)

    return list(entries.values())


# --------------------------------------------------------------------------- #
# Ledger I/O (atomic rewrite — temp + os.replace; keep-first per id).          #
# --------------------------------------------------------------------------- #
def _load_ledger(root: Path) -> dict[str, dict[str, Any]]:
    """{id -> row} from the shadow ledger, or {} when absent/unreadable (fail-open)."""
    p = ledger_path(root)
    out: dict[str, dict[str, Any]] = {}
    if not p.exists():
        return out
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            pid = r.get("id")
            if pid:
                out[str(pid)] = r  # keep-last on dupes (a re-write supersedes)
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_stage_shadow: ledger read failed (%s)", e)
    return out


def _write_ledger(root: Path, rows: dict[str, dict[str, Any]]) -> None:
    """Atomically rewrite the whole ledger (temp file + os.replace — never a partial
    truncation). Rows sorted by id for deterministic diffs."""
    d = _shadow_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = ledger_path(root)
    header = (
        "# prophet_stage_shadow forward ledger — schema " + LEDGER_SCHEMA + "\n"
        "# One row per Prophet entry: PIT stage-at-entry + last-EC tag (FIXED at entry,\n"
        "# never re-tagged) + grade fields (nightly-advanced at maturity). Display/shadow\n"
        "# tier — NEVER gates/ranks/alters Prophet. Nightly is the SOLE advancer of grades.\n"
    )
    body = "\n".join(json.dumps(rows[k], default=str) for k in sorted(rows))
    text = header + (body + "\n" if body else "")
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".ledger.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# --------------------------------------------------------------------------- #
# Tagging — PIT stage + last-EC at each entry's signal_date (idempotent).      #
# --------------------------------------------------------------------------- #
def _tag_one(entry: dict[str, Any], data_root: Path, bench: pd.Series | None,
             ec_by_ticker: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Compute the PIT tag for one Prophet entry. Fail-open: a missing OHLCV/EC never
    crashes — it records nulls + a ``tag_reason``. The stage is read via the audited
    truncating ``prophet_stage_fusion.stage_at_entry`` (close sliced to <= signal_date),
    so no post-entry price can leak into the tag."""
    asset = entry["asset"]
    sig = entry["signal_date"]
    row: dict[str, Any] = {
        "schema": LEDGER_SCHEMA,
        "id": entry["id"],
        "asset": asset,
        "signal_date": sig,
        "direction": entry.get("direction", "BULL"),
        "source": entry.get("source"),
        # tag fields (PIT-fixed at entry)
        "stage_at_entry": None,
        "weeks_in_stage": None,
        "fresh": None,
        "stage_detailed": None,
        "last_ec": None,
        "t_tier_at_entry": None,
        "tagged_asof": None,
        "tag_reason": None,
        # grade fields (nightly-advanced; null until matured)
        "graded": False,
        "graded_asof": None,
        "terminal_state_clean15_126": None,
        "terminal_state_clean8_21": None,
        "fwd": {},
    }

    close, vol = psf.load_ticker_prices(asset, Path(data_root))
    if close is None or close.empty:
        row["tag_reason"] = "no OHLCV in baskets/ohlcv or data/stocks — tagged null"
        return row

    # PIT stage (truncating classify — the look-ahead guard).
    try:
        st, wis, nwk = psf.stage_at_entry(close, vol, bench, sig)
    except Exception as e:  # noqa: BLE001
        row["tag_reason"] = f"stage classify failed ({e}) — tagged null"
        return row

    # weinstein classify gives fresh + stage_detailed too; re-derive via the truncated
    # classify for the richer fields (same PIT slice as stage_at_entry).
    fresh = None
    stage_detailed = None
    try:
        ed = pd.Timestamp(sig)
        c = close[close.index <= ed]
        v = vol[vol.index <= ed] if vol is not None and len(vol) else None
        b = bench[bench.index <= ed] if bench is not None and len(bench) else bench
        from engine import weinstein_stage
        res = weinstein_stage.classify(c, v, b)
        fresh = bool(res.get("fresh", False))
        stage_detailed = res.get("stage_detailed")
    except Exception as e:  # noqa: BLE001
        log.debug("prophet_stage_shadow: fresh/detailed lookup failed for %s (%s)", asset, e)

    # last EC strictly before entry.
    ec_val = psf.ec_sent_at_entry(ec_by_ticker, asset, sig)
    last_ec = None
    if ec_val is not None:
        g = ec_by_ticker.get(str(asset))
        call_date = None
        if g is not None and not g.empty:
            prior = g[g["call_date"] < pd.Timestamp(sig)]
            if not prior.empty:
                call_date = str(prior["call_date"].iloc[-1].date())
        last_ec = {"sent": ec_val, "call_date": call_date}

    # T-tier at entry (if the confluence cascade classifies it) — informational.
    t_tier = None
    try:
        stream = psf.confluence_tiers.tier_stream(close[close.index <= pd.Timestamp(sig)])
        if stream is not None and not stream.empty and "tier" in stream.columns:
            prior = stream[stream.index <= pd.Timestamp(sig)]
            if not prior.empty:
                t_tier = prior["tier"].iloc[-1]
    except Exception as e:  # noqa: BLE001
        log.debug("prophet_stage_shadow: t-tier lookup failed for %s (%s)", asset, e)

    row.update({
        "stage_at_entry": int(st) if st else 0,
        "weeks_in_stage": int(wis),
        "fresh": fresh,
        "stage_detailed": stage_detailed,
        "last_ec": last_ec,
        "t_tier_at_entry": t_tier,
        "tag_reason": "ok" if st else "too-young / unstageable at entry — stage=0",
    })
    return row


def tag_entries(root: str | Path | None = None, *, site_root: str | Path | None = None,
                ec_path: str | Path | None = None, asof: str | None = None) -> dict[str, Any]:
    """UPSERT a PIT tag for every Prophet entry into the shadow ledger, keyed by plan id.

    The tag is PIT-FIXED at the entry's signal_date (stage + last-EC), so an
    already-tagged id is NEVER re-tagged — a re-run does not change a prior tag
    (idempotent). New entries (plans that appeared since the last run) are tagged and
    appended. Fail-open per entry: a missing OHLCV/EC records nulls + a reason, never a
    crash. Runs in ANY lane (tagging is not a ledger *advance*; grading is).

    Returns a summary dict {n_entries, n_tagged_now, n_already, n_null}.
    """
    from lib import config
    data_root = Path(root) if root is not None else config.data_dir()
    site_root = Path(site_root) if site_root is not None else (_repo_root() / "site")
    asof = asof or pd.Timestamp.now("UTC").date().isoformat()

    entries = collect_prophet_entries(site_root, data_root)
    existing = _load_ledger(data_root)

    bench = psf.load_bench_close(data_root)
    ec_df = psf.load_ec_table(ec_path)
    ec_by_ticker = psf.ec_index(ec_df)

    n_tagged_now = 0
    n_null = 0
    for entry in entries:
        pid = entry["id"]
        if pid in existing:
            continue  # idempotent — the tag is PIT-fixed; never re-tag
        row = _tag_one(entry, data_root, bench, ec_by_ticker)
        row["tagged_asof"] = asof
        if row.get("stage_at_entry") in (None, 0) and row.get("tag_reason", "").startswith("no OHLCV"):
            n_null += 1
        existing[pid] = row
        n_tagged_now += 1

    if n_tagged_now:
        _write_ledger(data_root, existing)

    return {
        "n_entries": len(entries),
        "n_tagged_now": n_tagged_now,
        "n_already": len(entries) - n_tagged_now,
        "n_null": n_null,
        "n_ledger": len(existing),
    }


# --------------------------------------------------------------------------- #
# Grading — nightly-gated advance of matured entries.                          #
# --------------------------------------------------------------------------- #
def _horizon_elapsed(close: pd.Series, signal_date, horizon: int) -> bool:
    """True when ``horizon`` forward bars (after the next-bar fill) exist for the entry —
    i.e. the terminal_state/forward_metrics for that horizon can resolve, not freeze."""
    fill = grading.fill_index(close, signal_date)
    if fill is None:
        return False
    return (len(close) - 1 - fill) >= horizon


def _grade_one(row: dict[str, Any], data_root: Path) -> bool:
    """Grade one tagged entry through the SAME rulers the backtest uses, in-place.

    Only writes a terminal_state / fwd metric once its horizon has elapsed AND forward
    prices exist (frozen-until-matured — a not-yet-matured horizon stays null and is
    re-checked on a later nightly). Returns True if any grade field changed. Fail-open."""
    asset = row["asset"]
    sig = row["signal_date"]
    changed = False
    close, _ = psf.load_ticker_prices(asset, Path(data_root))
    if close is None or close.empty:
        # delisted / absent: try the dead-name-resolved grading series (survivorship).
        try:
            close = grading.resolve_series(asset, None)
        except Exception:  # noqa: BLE001
            close = None
        if close is None or close.empty:
            return False
    else:
        try:
            close = grading.resolve_series(asset, close)
        except Exception:  # noqa: BLE001
            pass

    # clean15_126 terminal state (only when the 126-bar horizon has elapsed).
    if row.get("terminal_state_clean15_126") is None and _horizon_elapsed(close, sig, 126):
        try:
            ts = grading.terminal_state(close, sig, **PARAM_CLEAN15_126)
            if ts.get("state") is not None:
                row["terminal_state_clean15_126"] = ts.get("state")
                changed = True
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: grade clean15_126 %s failed (%s)", asset, e)

    # clean8_21 terminal state (only when the 21-bar horizon has elapsed).
    if row.get("terminal_state_clean8_21") is None and _horizon_elapsed(close, sig, 21):
        try:
            ts = grading.terminal_state(close, sig, **PARAM_CLEAN8_21)
            if ts.get("state") is not None:
                row["terminal_state_clean8_21"] = ts.get("state")
                changed = True
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: grade clean8_21 %s failed (%s)", asset, e)

    # forward metrics per horizon (fill in each horizon as it matures).
    try:
        fwd = grading.forward_metrics(close, sig, horizons=FWD_HORIZONS)
        cur = row.get("fwd") or {}
        for h in FWD_HORIZONS:
            for k in (f"fwd_ret_{h}", f"fwd_mdd_{h}", f"fwd_mfe_{h}"):
                val = fwd.get(k)
                if val is not None and cur.get(k) is None:
                    cur[k] = val
                    changed = True
        row["fwd"] = cur
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_stage_shadow: forward_metrics %s failed (%s)", asset, e)

    if changed:
        row["graded"] = any(row.get(k) is not None for k in
                            ("terminal_state_clean15_126", "terminal_state_clean8_21")) or bool(row.get("fwd"))
    return changed


def grade_matured(root: str | Path | None = None, *, asof: str | None = None,
                  force: bool = False) -> dict[str, Any]:
    """Advance grades for tagged entries whose horizons have elapsed AND forward prices
    exist. NIGHTLY IS THE SOLE ADVANCER (house law): gated on
    ``ledger_lane.nightly_advance_enabled()`` (COLLECT_LANE=nightly). A non-nightly run
    is a no-op for grades (``force=True`` bypasses the gate for tests only).

    Idempotent: a horizon already graded is never re-graded; not-yet-matured horizons
    stay null and are re-checked on a later nightly. Fail-open per entry.

    Returns {advanced, gate_open, n_ledger}.
    """
    from lib import config
    data_root = Path(root) if root is not None else config.data_dir()
    asof = asof or pd.Timestamp.now("UTC").date().isoformat()

    if not (force or nightly_advance_enabled()):
        log.info("prophet_stage_shadow: grade_matured skipped (COLLECT_LANE != nightly — "
                 "nightly is the sole grade advancer)")
        return {"advanced": 0, "gate_open": False, "n_ledger": len(_load_ledger(data_root))}

    rows = _load_ledger(data_root)
    advanced = 0
    for pid, row in rows.items():
        try:
            if _grade_one(row, data_root):
                row["graded_asof"] = asof
                advanced += 1
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: grade_one %s failed (%s)", pid, e)

    if advanced:
        _write_ledger(data_root, rows)

    return {"advanced": advanced, "gate_open": True, "n_ledger": len(rows)}


# --------------------------------------------------------------------------- #
# Summarize — the accruing comparison (display-only; nulls printed).           #
# --------------------------------------------------------------------------- #
def _win_split(rows: list[dict[str, Any]], param_field: str) -> dict[str, Any]:
    """CLEAN_LIFTOFF win split over the matured subset for one ruler field.

    Returns {n_matured, n_win, win_rate} — win_rate is None until any entry matures
    (nulls printed, never a fabricated 0.0 rate on n=0)."""
    matured = [r for r in rows if r.get(param_field) is not None]
    n = len(matured)
    wins = sum(1 for r in matured if r.get(param_field) == grading.TerminalState.CLEAN_LIFTOFF)
    return {
        "n_matured": n,
        "n_win": wins,
        "win_rate": (wins / n) if n else None,
    }


def summarize(root: str | Path | None = None, *, asof: str | None = None) -> dict[str, Any]:
    """Emit ``data/prophet_stage_shadow/summary.json`` — the accruing Stage-2-vs-rest
    comparison ON ACTUAL PROPHET ENTRIES, with an honest accrual disclaimer.

    is_context_only + display_only. Prints nulls (no fabricated rate on n=0), no
    'validated', no trading verbs. Returns the summary dict (also written to disk)."""
    from lib import config
    data_root = Path(root) if root is not None else config.data_dir()
    asof = asof or pd.Timestamp.now("UTC").date().isoformat()

    rows = list(_load_ledger(data_root).values())
    n_entries = len(rows)
    n_tagged = sum(1 for r in rows if r.get("stage_at_entry") not in (None,))
    n_stageable = [r for r in rows if r.get("stage_at_entry")]  # stage in 1..4 (nonzero)

    # partitions ON PROPHET ENTRIES.
    stage2 = [r for r in n_stageable if r.get("stage_at_entry") == STAGE2]
    rest = [r for r in n_stageable if r.get("stage_at_entry") != STAGE2]
    fresh_stage2 = [r for r in stage2 if r.get("fresh")]
    pos_ec = [r for r in n_stageable
              if (r.get("last_ec") or {}).get("sent") is not None
              and (r.get("last_ec") or {}).get("sent") >= psf.EC_SENT_GATE]

    # per-horizon maturity counts (how many entries have each horizon graded).
    n_matured = {}
    for h in FWD_HORIZONS:
        n_matured[str(h)] = sum(
            1 for r in rows if (r.get("fwd") or {}).get(f"fwd_ret_{h}") is not None)
    n_matured["clean15_126"] = sum(
        1 for r in rows if r.get("terminal_state_clean15_126") is not None)
    n_matured["clean8_21"] = sum(
        1 for r in rows if r.get("terminal_state_clean8_21") is not None)

    def _both_params(subset: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(subset),
            "clean15_126": _win_split(subset, "terminal_state_clean15_126"),
            "clean8_21": _win_split(subset, "terminal_state_clean8_21"),
        }

    summary = {
        "schema": SUMMARY_SCHEMA,
        "is_context_only": True,
        "display_only": True,
        "authority_tier": "display",
        "generated_asof": asof,
        "generated_utc": pd.Timestamp.now("UTC").isoformat(),
        "spec": "research/PROPHET_STAGE_FUSION_PREREG.md",
        "accrual_disclaimer": ACCRUAL_DISCLAIMER,
        "n_entries": n_entries,
        "n_tagged": n_tagged,
        "n_stageable": len(n_stageable),
        "n_matured": n_matured,
        "split": {
            "stage2": _both_params(stage2),
            "rest": _both_params(rest),
            "fresh_stage2": _both_params(fresh_stage2),
            "positive_ec": _both_params(pos_ec),
        },
        "note": (
            "The Stage-2-vs-rest / fresh-Stage-2 / positive-EC outcome split on ACTUAL "
            "Prophet entries. win = CLEAN_LIFTOFF (same ruler as the backtest). win_rate "
            "is null until an entry matures — nulls printed, not hidden. This layer is "
            "context/measurement only: it NEVER gates, ranks, or alters any Prophet "
            "decision (the fusion win-rate-gate is killed per DO_NOT_REBUILD)."
        ),
    }

    d = _shadow_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    p = summary_path(data_root)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".summary.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return summary
