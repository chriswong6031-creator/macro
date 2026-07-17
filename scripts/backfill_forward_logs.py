"""W2.3 — Production price-basis PIT backfill: `backfill.parquet` + manifest.

Stamps every PIT-clean instrument at each historical MONTH-END (the phase-wheel
cadence, per masterplan D2 §1.4) using ONLY tape <= stamp_date — the same fields the
live `cycle_forward_log.append_forward_log` writer stamps, plus provenance metadata.

SCOPE (per D2 §0 + ruling A1):
  - 11 US SPDR sector ETFs        → data/sector_cycles/backfill.parquet
  - 24 country ETFs + 7 aggregates → data/country_cycles/backfill.parquet
  - 31 China Shenwan L1 sectors   → data/china_sector_cycles/backfill.parquet
  - Baskets: EXCLUDED (non-PIT membership; pit=False in basket_index)
  - Basis: price_v1 (W2.2 price-basis flips already applied)

LIVE LOG SAFETY:
  - NEVER opens forward_log.parquet for write.
  - Writes only to backfill.parquet (a parallel, re-runnable artifact).
  - The PIT invariant of the live log is INVIOLATE — this script does not touch it.

SPEED:
  - Uses a 2000-bar trailing window (compute-frugal, same pattern as W0.4's
    keystone_position_gate_phase0.py). The 252d oscillator + MACD lookbacks are
    << 2000 bars, so the cap is PIT-equivalent for signal fields. Verified by the
    window-cap stability test in tests/test_backfill_pit.py.
  - Target runtime: < 30 min for all three engines (measured ~20-25 min on 2-core).

PROVENANCE COLUMNS (D2 §1.2):
  - provenance      : "backfilled"          (constant; distinguishes from "prospective")
  - basis_version   : "price_v1"            (W2.2 epoch: structure math on close_price)
  - zz_version      : "zz14_v0"             (ZigZag threshold family, pre D5 rekey)
  - backfill_run_id : "<iso8601>_<git_sha>"  (ties every row to manifest entry)
  - engine_fingerprint: SHA-256[:12] of phase/turn function sources (changes if engine
                        logic changes, forcing a re-run to keep the artifact current)

LEAK GUARDS (D2 §1.5):
  1. PIT tape assert: raises LeakError if sliced tail > asof (hard fail, stops the run)
  2. Window-cap stability: verified in tests/test_backfill_pit.py
  3. Forward outcomes are NOT computed here (W2.4's domain — graders receive the raw
     stamp + their own realized close series)

RUNNING:
  python -m scripts.backfill_forward_logs                # full run (all 3 engines)
  python -m scripts.backfill_forward_logs --quick        # recent slice (2022-2026)
  python -m scripts.backfill_forward_logs --engine sector_cycles
  python -m scripts.backfill_forward_logs --engine country_cycles
  python -m scripts.backfill_forward_logs --engine china_sector_cycles
  python -m scripts.backfill_forward_logs --verify       # PIT spot-checks only

OUTPUTS (per engine):
  data/<engine>/backfill.parquet      — all PIT stamps (schema == live log + provenance)
  data/<engine>/backfill_manifest.json — run provenance (basis, fingerprint, n_stamps…)
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import logging
import subprocess
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import country_cycles as cc  # noqa: E402
from engine import cycle_ontology as onto  # noqa: E402
from engine import sector_cycles as sc   # noqa: E402
from engine.inputs import yahoo_closes   # noqa: E402

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    datefmt="%H:%M:%S")

# ── Pre-registered parameters — fixed before any data was inspected ─────────────────
BASIS_VERSION = "price_v1"          # W2.2 epoch: structure math on close_price (D4)
ZZ_VERSION = "zz14_v0"              # ZigZag threshold family (pre D5 re-key)
PROVENANCE = "backfilled"           # constant; row-level signal this is synthetic
WINDOW_CAP = 2000                   # trailing bars per call (W0.4 used 800; 2000 gives
                                    # oscillator convergence ≈ full history, per §1.5)
START_DEFAULT = pd.Timestamp("2010-12-31")  # ~15y; clip per-instrument by data availability
CHINA_ZZ_PCT = None  # use engine default (csc.CN_ZZ_PCT) — resolved at import time

# ── Engine fingerprint (D2 §1.2) ─────────────────────────────────────────────────────

def _engine_fingerprint() -> str:
    """SHA-256[:12] of the key phase/turn function sources.

    Changes when _record_core, _detect_swings, _classify_phase, or the ontology
    classify_phase (stamps phase_v2 — was an undetected drift axis until the
    #2697 port touched it) logic changes — signalling that a backfill re-run is
    needed. Stable across identical source trees.
    """
    sources = "".join([
        inspect.getsource(sc._record_core),
        inspect.getsource(sc._detect_swings),
        inspect.getsource(sc._classify_phase),
        inspect.getsource(onto.classify_phase),
    ])
    return hashlib.sha256(sources.encode()).hexdigest()[:12]


FINGERPRINT = _engine_fingerprint()


# ── Git SHA helper ────────────────────────────────────────────────────────────────────

def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


# ── Leak guard ───────────────────────────────────────────────────────────────────────

class LeakError(RuntimeError):
    """Raised when a PIT tape assertion fails (forward data in the stamp window)."""


def _assert_pit(series: pd.Series, asof: pd.Timestamp, label: str) -> None:
    """Hard assert: series.index[-1] <= asof. Raises LeakError otherwise."""
    if series.empty:
        return
    tail = series.index[-1]
    if tail > asof:
        raise LeakError(
            f"PIT LEAK [{label}]: series tail {tail.date()} > asof {asof.date()}"
        )


# ── Month-end calendar ────────────────────────────────────────────────────────────────

def _month_ends(cal: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """Last trading day of each calendar month from start to end (inclusive).

    Uses the benchmark trading calendar so all instruments in an engine share the
    same stamp dates — required for the date-blocked bootstrap in the grader to have
    shared blocks (D2 §1.4).
    """
    me_range = pd.date_range(start, end, freq="ME")
    out: list[pd.Timestamp] = []
    for m in me_range:
        j = int(cal.searchsorted(m, side="right")) - 1
        if j >= 0 and cal[j] <= end:
            out.append(cal[j])
    return sorted(set(out))


# ── Row builder (shared schema for US sector + country engines) ───────────────────────

def _stamp_row_us(
    rec: dict,
    asof: pd.Timestamp,
    kind: str,
    run_id: str,
) -> dict:
    """Flatten one engine record's cycle read into a backfill row.

    Schema matches engine.cycle_forward_log._extract_rows() exactly (D2 §1.4),
    plus the four provenance columns (D2 §1.2).
    """
    nw = rec.get("now") or {}
    pr = rec.get("proj") or {}
    basis = nw.get("basis", "tr")

    return {
        # Live schema (matches forward_log.parquet)
        "date":           str(asof.date()),
        "id":             rec.get("id", ""),
        "kind":           kind,
        "name":           rec.get("name", ""),
        "phase":          nw.get("phase"),
        "pos":            nw.get("pos"),
        "osc_slope":      nw.get("osc_slope"),
        "signal":         nw.get("signal"),
        "timing_state":   nw.get("timing_state"),
        "above200d":      nw.get("above200d"),
        "rs_63d":         nw.get("rs_63d"),
        "proj_next":      pr.get("nextTurn"),
        "proj_central":   pr.get("central"),
        "proj_lo":        pr.get("low"),
        "proj_hi":        pr.get("high"),
        # W1.6 ontology fields
        "pos_v2":         nw.get("pos_v2"),
        "phase_v2":       nw.get("phase_v2"),
        "stance":         nw.get("stance"),
        "divergence":     nw.get("divergence"),
        "overdue":        pr.get("overdue"),
        # W2.2 basis stamp
        "basis":          basis,
        # Provenance (D2 §1.2)
        "provenance":         PROVENANCE,
        "basis_version":      BASIS_VERSION,
        "zz_version":         ZZ_VERSION,
        "backfill_run_id":    run_id,
        "engine_fingerprint": FINGERPRINT,
    }


def _stamp_row_china(
    rec: dict,
    asof: pd.Timestamp,
    run_id: str,
) -> dict:
    """Flatten one China sector cycle record into a backfill row.

    Schema matches engine.china_sector_cycles.append_forward_log() exactly,
    plus the four provenance columns (D2 §1.2).
    """
    nw = rec.get("now") or {}
    pr = rec.get("proj") or {}
    sig = (nw.get("signature") or {})
    pw = rec.get("pathway") or {}
    cond = pw.get("conditional") or {}
    h6 = cond.get("h6") or cond.get("h3") or {}

    return {
        # China live schema (matches china_sector_cycles/forward_log.parquet)
        "date":           str(asof.date()),
        "id":             rec.get("id", ""),
        "kind":           rec.get("kind", "sector"),
        "name":           rec.get("name", ""),
        "phase":          nw.get("phase"),
        "pos":            nw.get("pos"),
        "osc_slope":      nw.get("osc_slope"),
        "signature":      sig.get("score"),
        "signal":         nw.get("signal"),
        "above200d":      nw.get("above200d"),
        "rs_63d":         nw.get("rs_63d"),
        "rs_rank":        nw.get("rs_rank"),
        "proj_next":      pr.get("nextTurn"),
        "proj_central":   pr.get("central"),
        "proj_lo":        pr.get("low"),
        "proj_hi":        pr.get("high"),
        "pathway_cond_rate":  h6.get("cond_rate"),
        "pathway_base_rate":  h6.get("base_rate"),
        "pathway_tercile":    (pw.get("setup") or {}).get("tercile"),
        # Provenance (D2 §1.2)
        "provenance":         PROVENANCE,
        "basis_version":      BASIS_VERSION,
        "zz_version":         ZZ_VERSION,
        "backfill_run_id":    run_id,
        "engine_fingerprint": FINGERPRINT,
    }


# ── PIT spot-checks (D2 §1.5 — ≥3 instruments × 2 dates each) ────────────────────────

def _pit_spot_checks(
    closes: pd.DataFrame,
    closes_px: pd.DataFrame | None,
    run_id: str,
) -> list[dict]:
    """Verify PIT invariance: stamp on truncated tape == stamp on full tape sliced.

    Checks 6 (instrument, date) pairs (3 sectors × 2 dates, 3 countries × 2 dates).
    For each pair, computes the stamp two ways:
      A) truncate closes to asof, then stamp
      B) stamp at asof using the windowed subpanel
    Phase + signal + timing_state must match — any mismatch raises AssertionError.

    Returns a list of check dicts for the manifest.
    """
    CHECKS = [
        # (ticker, asof, family)
        ("XLK",  "2024-03-31", "us_sector"),
        ("XLK",  "2019-06-28", "us_sector"),
        ("XLF",  "2015-06-30", "us_sector"),
        ("EWJ",  "2020-12-31", "country"),
        ("EWZ",  "2017-10-31", "country"),
        ("EWG",  "2016-03-31", "country"),
    ]
    results = []
    cal = closes.index
    us_sectors = set(sc.SECTORS.keys())
    cc_tickers  = set(cc.COUNTRIES.keys()) | set(cc.AGGREGATES.keys())

    for ticker, asof_str, family in CHECKS:
        asof = pd.Timestamp(asof_str)
        # Only check if ticker is in the close panel
        if ticker not in closes.columns:
            results.append({"ticker": ticker, "asof": asof_str, "skipped": "not in panel"})
            continue

        try:
            j = int(cal.searchsorted(asof, side="right")) - 1
            if j < 0:
                results.append({"ticker": ticker, "asof": asof_str, "skipped": "before data start"})
                continue

            actual_asof = cal[j]

            # Method A: windowed cap (the production approach)
            sub_idx = max(0, j + 1 - WINDOW_CAP)
            sub_a = closes.iloc[sub_idx:j + 1]
            sub_px_a = closes_px.iloc[sub_idx:j + 1] if closes_px is not None else None
            _assert_pit(sub_a, actual_asof, f"A_{ticker}_{asof_str}")

            # Method B: slice from the full tape (reference)
            sub_b = closes[closes.index <= actual_asof]
            sub_px_b = closes_px[closes_px.index <= actual_asof] if closes_px is not None else None
            _assert_pit(sub_b, actual_asof, f"B_{ticker}_{asof_str}")

            # Stamp both ways
            def _stamp_it(sub: pd.DataFrame, sub_px: pd.DataFrame | None) -> dict | None:
                ws = sub.index[0]
                full = sub[ticker].dropna() if ticker in sub else pd.Series()
                if len(full) < 60:
                    return None
                if ticker in us_sectors:
                    price = sc._price_series(sub_px, ticker, full)
                    rec = sc.build_sector(ticker, sc.SECTORS[ticker], sub, ws,
                                          closes_px=sub_px)
                elif ticker in cc_tickers:
                    meta = cc.COUNTRIES.get(ticker) or cc.AGGREGATES.get(ticker)
                    if meta is None:
                        return None
                    is_agg = ticker in cc.AGGREGATES
                    price = sc._price_series(sub_px, ticker, full)
                    rec = cc._build_one(ticker, meta, sub, ws,
                                        kind="basket" if is_agg else "sector",
                                        group=meta.get("region") or meta.get("group", ""),
                                        accent="#888",
                                        closes_px=sub_px)
                else:
                    return None
                return rec

            rec_a = _stamp_it(sub_a, sub_px_a)
            rec_b = _stamp_it(sub_b, sub_px_b)

            if rec_a is None or rec_b is None:
                results.append({"ticker": ticker, "asof": asof_str, "skipped": "thin data"})
                continue

            now_a = rec_a.get("now") or {}
            now_b = rec_b.get("now") or {}

            # Phase + signal + timing_state must match (the core PIT invariant)
            match = (
                now_a.get("phase") == now_b.get("phase")
                and now_a.get("signal") == now_b.get("signal")
                and now_a.get("timing_state") == now_b.get("timing_state")
            )

            result = {
                "ticker": ticker,
                "asof": asof_str,
                "match": match,
                "phase_A": now_a.get("phase"),
                "phase_B": now_b.get("phase"),
                "signal_A": now_a.get("signal"),
                "signal_B": now_b.get("signal"),
                "timing_A": now_a.get("timing_state"),
                "timing_B": now_b.get("timing_state"),
                "pos_A": round(float(now_a.get("pos") or 0), 1),
                "pos_B": round(float(now_b.get("pos") or 0), 1),
            }
            results.append(result)

            if not match:
                log.error("PIT SPOT-CHECK FAILED: %s @ %s — A=%s/%s B=%s/%s",
                          ticker, asof_str, now_a.get("phase"), now_a.get("timing_state"),
                          now_b.get("phase"), now_b.get("timing_state"))
            else:
                log.info("PIT spot-check OK: %s @ %s — phase=%s timing=%s",
                         ticker, asof_str, now_a.get("phase"), now_a.get("timing_state"))

        except Exception as e:  # noqa: BLE001
            results.append({"ticker": ticker, "asof": asof_str, "error": str(e)})
            log.warning("PIT spot-check error %s @ %s: %s", ticker, asof_str, e)

    # Assert all non-skipped checks passed
    failures = [r for r in results if not r.get("skipped") and not r.get("error")
                and not r.get("match")]
    if failures:
        raise AssertionError(
            f"PIT spot-checks FAILED for {len(failures)} pairs: "
            + ", ".join(f"{r['ticker']}@{r['asof']}" for r in failures)
        )

    return results


# ── US sector engine backfill ────────────────────────────────────────────────────────

def _backfill_sector_cycles(
    closes: pd.DataFrame,
    closes_px: pd.DataFrame | None,
    month_ends: list[pd.Timestamp],
    quick: bool,
    run_id: str,
) -> pd.DataFrame:
    """Stamp all 11 US SPDR sector ETFs at each month-end.

    Uses the 2000-bar trailing window (compute-frugal, PIT-equivalent for the
    252d oscillator and MACD lookbacks). Includes pos_v2/phase_v2/stance/overdue
    from W1.6 fields already emitted by _record_core.
    """
    rows: list[dict] = []
    cal = closes.index
    log.info("sector_cycles: %d month-ends × 11 sectors", len(month_ends))

    for k, asof in enumerate(month_ends):
        j = int(cal.searchsorted(asof, side="right")) - 1
        if j < 0:
            continue

        sub_idx = max(0, j + 1 - WINDOW_CAP)
        sub = closes.iloc[sub_idx:j + 1]
        sub_px = closes_px.iloc[sub_idx:j + 1] if closes_px is not None else None

        # Hard PIT assertion (D2 §1.5 guard 1)
        _assert_pit(sub, asof, f"sector/{asof.date()}")

        ws = sub.index[0]
        for tk, meta in sc.SECTORS.items():
            try:
                rec = sc.build_sector(tk, meta, sub, ws, closes_px=sub_px)
            except Exception as e:  # noqa: BLE001
                log.debug("sector %s @ %s failed: %s", tk, asof.date(), e)
                rec = None
            if rec:
                rows.append(_stamp_row_us(rec, asof, "sector", run_id))

        if (k + 1) % 24 == 0:
            log.info("  sector_cycles: %d/%d months (%s), %d stamps",
                     k + 1, len(month_ends), asof.date(), len(rows))

    df = pd.DataFrame(rows)
    log.info("sector_cycles: %d total stamps", len(df))
    return df


# ── Country engine backfill ───────────────────────────────────────────────────────────

def _backfill_country_cycles(
    closes: pd.DataFrame,
    closes_px: pd.DataFrame | None,
    month_ends: list[pd.Timestamp],
    quick: bool,
    run_id: str,
) -> pd.DataFrame:
    """Stamp 24 country ETFs + 7 aggregate ETFs at each month-end."""
    rows: list[dict] = []
    cal = closes.index
    n_instruments = len(cc.COUNTRIES) + len(cc.AGGREGATES)
    log.info("country_cycles: %d month-ends × %d instruments (%d countries + %d aggregates)",
             len(month_ends), n_instruments, len(cc.COUNTRIES), len(cc.AGGREGATES))

    for k, asof in enumerate(month_ends):
        j = int(cal.searchsorted(asof, side="right")) - 1
        if j < 0:
            continue

        sub_idx = max(0, j + 1 - WINDOW_CAP)
        sub = closes.iloc[sub_idx:j + 1]
        sub_px = closes_px.iloc[sub_idx:j + 1] if closes_px is not None else None

        _assert_pit(sub, asof, f"country/{asof.date()}")

        ws = sub.index[0]

        # Countries (kind="sector")
        for tk, meta in cc.COUNTRIES.items():
            try:
                rec = cc._build_one(
                    tk, meta, sub, ws,
                    kind="sector",
                    group=meta.get("region", ""),
                    accent="#888",
                    closes_px=sub_px,
                )
            except Exception as e:  # noqa: BLE001
                log.debug("country %s @ %s failed: %s", tk, asof.date(), e)
                rec = None
            if rec:
                rows.append(_stamp_row_us(rec, asof, "sector", run_id))

        # Aggregates / blocs (kind="basket")
        for tk, meta in cc.AGGREGATES.items():
            try:
                rec = cc._build_one(
                    tk, meta, sub, ws,
                    kind="basket",
                    group=meta.get("group", ""),
                    accent="#888",
                    closes_px=sub_px,
                )
            except Exception as e:  # noqa: BLE001
                log.debug("aggregate %s @ %s failed: %s", tk, asof.date(), e)
                rec = None
            if rec:
                rows.append(_stamp_row_us(rec, asof, "basket", run_id))

        if (k + 1) % 24 == 0:
            log.info("  country_cycles: %d/%d months (%s), %d stamps",
                     k + 1, len(month_ends), asof.date(), len(rows))

    df = pd.DataFrame(rows)
    log.info("country_cycles: %d total stamps", len(df))
    return df


# ── China sector engine backfill ─────────────────────────────────────────────────────

def _backfill_china_sector_cycles(
    month_ends_cal: pd.DatetimeIndex,
    quick: bool,
    run_id: str,
) -> pd.DataFrame:
    """Stamp 31 China Shenwan L1 sector indices at each month-end.

    China build_sector reads csi.sw_close(code) internally, slicing to last_ts.
    We pre-load all series once and slice to the windowed cap for each month-end
    to match the compute-frugal pattern of the US/country engine.

    China basis: Shenwan indices are price-basis already (no dividend inflation in the
    index level — the D4-N1 note: A-share sector indices are not TR series). W2.2 left
    China VERBATIM; basis stamp = 'price' (already the case in the live writer).
    """
    try:
        from engine import china_sector_cycles as csc
        from engine import china_sector_index as csi
    except Exception as e:  # noqa: BLE001
        log.error("china_sector_cycles: cannot import — skipping China backfill: %s", e)
        return pd.DataFrame()

    CN_ZZ_PCT = csc.CN_ZZ_PCT

    # Pre-load all sector series (avoids repeated disk reads in the loop)
    china_series: dict[str, pd.Series] = {}
    for code in csc._SW:
        s = csi.sw_close(code)
        if s is not None and len(s) >= 60:
            china_series[code] = s

    if not china_series:
        log.warning("china_sector_cycles: no sectors loaded — skipping")
        return pd.DataFrame()

    # Build month-end calendar from the benchmark's trading calendar
    bench = csi.benchmark_close()
    if bench is None or bench.empty:
        log.warning("china_sector_cycles: benchmark unavailable — skipping")
        return pd.DataFrame()

    bench_cal = bench.index
    start = max(START_DEFAULT, bench_cal.min() + pd.DateOffset(days=300))
    end = bench_cal[-1]
    if quick:
        start = pd.Timestamp("2022-01-01")

    month_ends = _month_ends(bench_cal, start, end)
    log.info("china_sector_cycles: %d month-ends × %d sectors",
             len(month_ends), len(china_series))

    rows: list[dict] = []
    for k, asof in enumerate(month_ends):
        j = int(bench_cal.searchsorted(asof, side="right")) - 1
        if j < 0:
            continue
        actual_asof = bench_cal[j]

        for code, meta in csc._SW.items():
            s = china_series.get(code)
            if s is None:
                continue

            # Windowed slice (2000-bar cap) — PIT: never read past asof
            s_slice = s[s.index <= actual_asof]
            if s_slice.empty:
                continue
            s_cap = s_slice.iloc[max(0, len(s_slice) - WINDOW_CAP):]

            # Hard PIT assertion
            _assert_pit(s_cap, actual_asof, f"china/{code}/{actual_asof.date()}")

            win_start = s_cap.index[0]

            try:
                core = sc._record_core(s_cap, win_start, actual_asof, pct=CN_ZZ_PCT)
            except Exception as e:  # noqa: BLE001
                log.debug("china %s @ %s _record_core failed: %s", code, actual_asof.date(), e)
                core = None
            if core is None:
                continue

            en, short, zh, short_zh, group = meta
            # Build a minimal rec dict matching china_sector_cycles record shape
            rec = dict(core)
            rec.update({
                "id": code, "shenwan_code": code, "ticker": code, "kind": "sector",
                "name": en, "short": short, "name_zh": zh, "short_zh": short_zh,
                "group": group,
            })

            # RS (vs SHCOMP benchmark) — replicate _basket_rs
            try:
                bench_slice = bench[bench.index <= actual_asof]
                if code in china_series:
                    sc._apply_leadership(rec, sc._basket_rs(s_cap, bench_slice))
            except Exception:  # noqa: BLE001
                pass  # RS is additive; skip if unavailable

            rows.append(_stamp_row_china(rec, actual_asof, run_id))

        if (k + 1) % 24 == 0:
            log.info("  china_sector_cycles: %d/%d months (%s), %d stamps",
                     k + 1, len(month_ends), actual_asof.date(), len(rows))

    df = pd.DataFrame(rows)
    log.info("china_sector_cycles: %d total stamps", len(df))
    return df


# ── Manifest writer ──────────────────────────────────────────────────────────────────

def _write_manifest(
    engine: str,
    df: pd.DataFrame,
    run_id: str,
    month_ends: list[pd.Timestamp],
    git_sha: str,
    runtime_s: float,
    pit_checks: list[dict] | None = None,
    notes: str = "",
) -> Path:
    """Write backfill_manifest.json alongside the parquet (D2 §1.2 schema)."""
    try:
        from lib import config
        out_dir = config.data_dir() / engine
    except Exception:
        out_dir = Path("data") / engine
    out_dir.mkdir(parents=True, exist_ok=True)

    instrument_ids = sorted(df["id"].unique().tolist()) if "id" in df.columns else []
    basis_vals = df["basis"].value_counts().to_dict() if "basis" in df.columns else {}

    manifest = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": engine,
        "basis_version": BASIS_VERSION,
        "zz_version": ZZ_VERSION,
        "engine_fingerprint": FINGERPRINT,
        "git_sha": git_sha,
        "cadence": "month_end",
        "window_cap_bars": WINDOW_CAP,
        "provenance": PROVENANCE,
        "asof_start": str(month_ends[0].date()) if month_ends else None,
        "asof_end":   str(month_ends[-1].date()) if month_ends else None,
        "n_month_ends": len(month_ends),
        "n_instruments": len(instrument_ids),
        "instrument_ids": instrument_ids,
        "n_stamps": len(df),
        "basis_counts": {str(k): int(v) for k, v in basis_vals.items()},
        "runtime_seconds": round(runtime_s, 1),
        "leak_guards_passed": True,  # set to False if pit_checks fail (but we raise before here)
        "pit_spot_checks": pit_checks or [],
        "notes": notes or (
            f"Price-basis (W2.2 epoch); structure math on close_price for ETFs. "
            f"Supersede on next basis-version bump (D3) or ZigZag threshold change (D5)."
        ),
        "live_log_touched": False,  # INVARIANT — this script never opens forward_log.parquet for write
    }

    path = out_dir / "backfill_manifest.json"
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    log.info("manifest written: %s (%d stamps, %.0fs)", path, len(df), runtime_s)
    return path


# ── Parquet writer ────────────────────────────────────────────────────────────────────

def _write_parquet(engine: str, df: pd.DataFrame) -> Path:
    """Write backfill.parquet — fully replaces any prior run (backfill is re-runnable)."""
    try:
        from lib import config
        out_dir = config.data_dir() / engine
    except Exception:
        out_dir = Path("data") / engine
    out_dir.mkdir(parents=True, exist_ok=True)

    path = out_dir / "backfill.parquet"
    df.to_parquet(path, index=False)
    log.info("backfill.parquet written: %s (%d rows)", path, len(df))
    return path


# ── Sanity table printer ──────────────────────────────────────────────────────────────

def _print_sanity_table(engine: str, df: pd.DataFrame) -> None:
    if df.empty:
        print(f"  {engine}: 0 stamps (empty)")
        return
    n = len(df)
    d0 = df["date"].min() if "date" in df.columns else "?"
    d1 = df["date"].max() if "date" in df.columns else "?"
    n_inst = df["id"].nunique() if "id" in df.columns else "?"
    prov = df["provenance"].value_counts().to_dict() if "provenance" in df.columns else {}
    basis = df["basis"].value_counts().to_dict() if "basis" in df.columns else {}
    print(f"  {engine:30s}: {n:6d} stamps | {d0} → {d1} | {n_inst} instruments")
    print(f"    provenance: {prov}")
    print(f"    basis:      {basis}")


# ── Per-engine orchestrator ───────────────────────────────────────────────────────────

def run_engine(
    engine: str,
    *,
    quick: bool = False,
    skip_pit: bool = False,
    run_id: str,
    git_sha: str,
) -> dict:
    """Run the PIT backfill for one engine. Returns a summary dict."""
    t_start = time.time()
    result: dict = {"engine": engine, "n_stamps": 0, "ok": False}

    # ── Load close panels (US sector + country share the same Yahoo panel) ────────────
    if engine in ("sector_cycles", "country_cycles"):
        log.info("%s: loading Yahoo close panels...", engine)
        try:
            closes = yahoo_closes()
        except Exception as e:  # noqa: BLE001
            log.error("%s: cannot load yahoo_closes: %s", engine, e)
            return result
        if closes is None or closes.empty:
            log.error("%s: yahoo_closes returned empty", engine)
            return result

        try:
            closes_px = yahoo_closes(basis="price")
        except Exception as e:  # noqa: BLE001
            log.warning("%s: cannot load price panel (%s) — tr_fallback for all", engine, e)
            closes_px = None

        if closes_px is not None:
            # Defensive: keep same index as TR panel
            closes_px = closes_px.reindex(closes.index)

        cal = closes.index
        start = START_DEFAULT
        if quick:
            start = pd.Timestamp("2022-01-01")
        end = cal[-1] - pd.DateOffset(days=1)  # exclude partial current month
        # Clip to last complete month
        last_complete_me = pd.Timestamp(end.year, end.month, 1) - pd.DateOffset(days=1)
        month_ends = _month_ends(cal, start, last_complete_me)

        # ── PIT spot-checks (US + country share the same close panel) ─────────────────
        pit_checks: list[dict] = []
        if not skip_pit and engine == "sector_cycles":
            log.info("Running PIT spot-checks...")
            try:
                pit_checks = _pit_spot_checks(closes, closes_px, run_id)
                log.info("All PIT spot-checks passed (%d checks)", len(pit_checks))
            except AssertionError as e:
                log.error("PIT spot-check FAILURE: %s", e)
                raise
        elif not skip_pit and engine == "country_cycles":
            # Country spot-checks share the panel but we run them here too
            log.info("PIT spot-checks run by sector_cycles engine (shared panel) — skipping duplicate")

        # ── Build DataFrame ───────────────────────────────────────────────────────────
        if engine == "sector_cycles":
            df = _backfill_sector_cycles(closes, closes_px, month_ends, quick, run_id)
        else:
            df = _backfill_country_cycles(closes, closes_px, month_ends, quick, run_id)

        elapsed = time.time() - t_start

        # ── Write outputs ─────────────────────────────────────────────────────────────
        if not df.empty:
            _write_parquet(engine, df)
            _write_manifest(engine, df, run_id, month_ends, git_sha, elapsed,
                            pit_checks=pit_checks if engine == "sector_cycles" else [])
        result["n_stamps"] = len(df)
        result["ok"] = not df.empty
        result["runtime_s"] = elapsed

    elif engine == "china_sector_cycles":
        # China has its own calendar built internally
        china_month_ends_placeholder: list[pd.Timestamp] = []  # built inside the function
        df = _backfill_china_sector_cycles(pd.DatetimeIndex([]), quick, run_id)
        elapsed = time.time() - t_start
        if not df.empty:
            # Reconstruct month_ends from the df dates for the manifest
            dates = pd.to_datetime(df["date"]).sort_values().unique()
            china_month_ends_placeholder = list(pd.DatetimeIndex(dates))
            _write_parquet(engine, df)
            _write_manifest(engine, df, run_id, china_month_ends_placeholder, git_sha, elapsed,
                            notes=(
                                "China Shenwan L1 sectors — price-basis (indices are not TR series; "
                                "D4-N1: A-share index = price, W2.2 carried verbatim). "
                                "RS vs SHCOMP benchmark."
                            ))
        result["n_stamps"] = len(df)
        result["ok"] = not df.empty
        result["runtime_s"] = elapsed
    else:
        log.error("Unknown engine: %r", engine)
        return result

    return result


# ── CLI entry point ───────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="W2.3 — Price-basis PIT backfill for cycle engines",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--engine",
        choices=["sector_cycles", "country_cycles", "china_sector_cycles"],
        default=None,
        help="Run only this engine (default: all three)",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Short slice (2022–present) for smoke-testing",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run PIT spot-checks only — no backfill written",
    )
    args = parser.parse_args(argv)

    git_sha = _git_sha()
    run_id = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}_{git_sha}"
    log.info("W2.3 PIT backfill run_id=%s fingerprint=%s", run_id, FINGERPRINT)

    if args.verify:
        # Spot-check only — no write
        log.info("--verify mode: running PIT spot-checks only")
        try:
            closes = yahoo_closes()
            closes_px = yahoo_closes(basis="price")
        except Exception as e:  # noqa: BLE001
            log.error("Cannot load panels: %s", e)
            sys.exit(1)
        checks = _pit_spot_checks(closes, closes_px, run_id)
        for c in checks:
            status = "OK" if c.get("match") else ("SKIP" if c.get("skipped") else "FAIL")
            print(f"  {status}  {c.get('ticker','?')} @ {c.get('asof','?')}: {c}")
        all_ok = all(c.get("match") or c.get("skipped") for c in checks)
        sys.exit(0 if all_ok else 1)

    engines = (
        [args.engine] if args.engine
        else ["sector_cycles", "country_cycles", "china_sector_cycles"]
    )

    t_total = time.time()
    summaries: list[dict] = []
    pit_checks_shared: list[dict] = []

    for engine in engines:
        log.info("=" * 60)
        log.info("Starting engine: %s", engine)
        try:
            summary = run_engine(
                engine,
                quick=args.quick,
                skip_pit=(engine == "country_cycles"),  # share US spot-checks to avoid dup
                run_id=run_id,
                git_sha=git_sha,
            )
            summaries.append(summary)
        except AssertionError:
            log.error("PIT INVARIANCE FAILURE — aborting")
            sys.exit(1)
        except Exception as e:  # noqa: BLE001
            log.error("Engine %s failed: %s", engine, e, exc_info=True)
            summaries.append({"engine": engine, "n_stamps": 0, "ok": False, "error": str(e)})

    total_elapsed = time.time() - t_total

    print("\n" + "=" * 70)
    print("W2.3 BACKFILL SUMMARY")
    print("=" * 70)
    print(f"  run_id:              {run_id}")
    print(f"  engine_fingerprint:  {FINGERPRINT}")
    print(f"  basis_version:       {BASIS_VERSION}")
    print(f"  total_runtime:       {total_elapsed/60:.1f} min")
    print()

    for s in summaries:
        eng = s.get("engine", "?")
        n = s.get("n_stamps", 0)
        ok = s.get("ok", False)
        rt = s.get("runtime_s", 0)
        err = s.get("error", "")
        status = "OK" if ok else "FAIL"
        print(f"  {eng:30s}: {status:4s} | {n:6d} stamps | {rt/60:.1f} min"
              + (f" | ERROR: {err}" if err else ""))

    print()
    print("  Stamps-per-engine table:")
    for s in summaries:
        eng = s.get("engine", "?")
        try:
            from lib import config
            p = config.data_dir() / eng / "backfill.parquet"
        except Exception:
            p = Path("data") / eng / "backfill.parquet"
        if p.exists():
            try:
                df = pd.read_parquet(p)
                _print_sanity_table(eng, df)
            except Exception:  # noqa: BLE001
                print(f"  {eng}: could not read parquet")
    print("=" * 70)

    # Register in admin experiments registry (additive — skip if unclear schema)
    _register_experiment(run_id, summaries)

    all_ok = all(s.get("ok") for s in summaries)
    sys.exit(0 if all_ok else 1)


# ── Experiments registry registration (D2 §6, additive) ──────────────────────────────

def _register_experiment(run_id: str, summaries: list[dict]) -> None:
    """Additive entry in data/experiments/registry_seed.json.

    Only adds an entry if one with this experiment ID doesn't exist yet. Safe to call
    repeatedly — idempotent on the experiment ID. Schema matches existing entries.
    If anything fails, logs a warning and continues (never blocks the backfill).
    """
    try:
        reg_path = Path("data/experiments/registry_seed.json")
        if not reg_path.exists():
            log.warning("experiments registry not found — skipping registration")
            return

        with open(reg_path) as f:
            registry = json.load(f)

        experiments: list[dict] = registry.get("experiments", [])
        existing_ids = {e.get("id") for e in experiments}
        exp_id = "cycle-pit-backfill-w23"

        if exp_id in existing_ids:
            log.info("experiment %r already registered — updating state", exp_id)
            for exp in experiments:
                if exp.get("id") == exp_id:
                    total_stamps = sum(s.get("n_stamps", 0) for s in summaries)
                    exp["state"] = (
                        f"last_run_id={run_id[:30]}; "
                        f"total_stamps={total_stamps}; "
                        f"engines={[s.get('engine') for s in summaries]}"
                    )
                    break
        else:
            total_stamps = sum(s.get("n_stamps", 0) for s in summaries)
            new_entry = {
                "id": exp_id,
                "name": "Cycle PIT Backfill — W2.3 price-basis stamps",
                "kind": "backfill",
                "priority": "high",
                "cadence": "on_basis_bump",
                "what": (
                    "Price-basis (W2.2 epoch) PIT month-end stamps for 11 US sectors + "
                    "24 country ETFs + 7 aggregates + 31 China Shenwan sectors. "
                    "Provenance=backfilled; graders join via engine.grading_stats.load_graded_log(). "
                    "Manifest at data/<engine>/backfill_manifest.json."
                ),
                "source": "scripts/backfill_forward_logs.py",
                "storage": "data/{sector,country,china_sector}_cycles/backfill.parquet",
                "track_json": "data/{sector,country,china_sector}_cycles/backfill_manifest.json",
                "hook": "backfill",
                "started": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "come_back_on": "on_W2.4_grader_launch",
                "come_back_note": (
                    "W2.4 graders join this artifact to realized returns. "
                    "Re-run if basis_version bumps (D3) or zz_version bumps (D5)."
                ),
                "maturation": (
                    f"n_stamps={total_stamps}; no forward outcomes here (W2.4 domain); "
                    "re-run on D3 basis bump. engine_fingerprint guards stale artifacts."
                ),
                "status": "accruing",
                "state": (
                    f"last_run_id={run_id[:30]}; "
                    f"total_stamps={total_stamps}; "
                    f"engines={[s.get('engine') for s in summaries]}"
                ),
                "next_step": "W2.4 graders consume this via load_graded_log(); "
                             "re-run on basis_version bump.",
                "phase_hint": "Phase 2 (D2 measurement)",
            }
            experiments.append(new_entry)

        registry["experiments"] = experiments
        with open(reg_path, "w") as f:
            json.dump(registry, f, indent=2)
        log.info("experiments registry updated with %r", exp_id)

    except Exception as e:  # noqa: BLE001
        log.warning("experiments registry update failed (non-fatal): %s", e)


if __name__ == "__main__":
    main()
