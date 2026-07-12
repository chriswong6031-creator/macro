"""A1 Falsifier Packet builder — off-render one-shot.

Program: Long-Hold Thesis lobe — LHB-W3 (A1 Falsifier Packet + A6 hard-stop bus).
Adjudication: research/LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md §LHB-R2, R3.
              research/FALSIFIER_FIELD_BOOK_ADJUDICATION_BY_FABLE.md §FFB-R2.

Reads committed artifacts only (no engine re-computation, no subprocess):
  data/research/thesis_funnel_states.parquet      — funnel population + states
  data/research/delivery_waterfall.parquet        — A3 waterfall rows (residual leg)
  data/edgar/material_8k_events.parquet           — 8-K item routing
  data/edgar/statements.parquet                   — EV/sales vs own history

Outputs (this script is the SOLE writer of both):
  data/research/falsifier_packets.json            — per-ticker packets + summary
  data/research/falsifier_packets_manifest.json   — build manifest

FIREWALL: horizon_role=hold_thesis. These artifacts MUST NOT feed board
ordering, alert triage, top-setups gates, or push floor (LHB-R2 / LH-R1).

CRITICAL: This script reads parquet — exit via lib.procutil.hard_exit()
to avoid Arrow ThreadPool static-destructor deadlock (#2196).

Usage:
    python scripts/research/build_falsifier_packets.py
    python scripts/research/build_falsifier_packets.py --smoke
    python scripts/research/build_falsifier_packets.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Repo root bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib import config  # noqa: E402
from lib.procutil import hard_exit  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths (all via config.data_dir() — env-overridable)
# ---------------------------------------------------------------------------

def _data() -> Path:
    return config.data_dir()


def _funnel_path() -> Path:
    return _data() / "research" / "thesis_funnel_states.parquet"


def _waterfall_path() -> Path:
    return _data() / "research" / "delivery_waterfall.parquet"


def _events_path() -> Path:
    return _data() / "edgar" / "material_8k_events.parquet"


def _statements_path() -> Path:
    return _data() / "edgar" / "statements.parquet"


def _out_packets() -> Path:
    return _data() / "research" / "falsifier_packets.json"


def _out_manifest() -> Path:
    return _data() / "research" / "falsifier_packets_manifest.json"


# ---------------------------------------------------------------------------
# Data loaders (each fail-open)
# ---------------------------------------------------------------------------

def _load_funnel() -> "pd.DataFrame | None":
    import pandas as pd
    p = _funnel_path()
    if not p.exists():
        log.warning("thesis_funnel_states not found: %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        if "ticker" not in df.columns or "state" not in df.columns:
            log.warning("thesis_funnel_states missing required columns")
            return None
        log.info("Loaded thesis_funnel_states: %d rows, %d tickers", len(df), df["ticker"].nunique())
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("thesis_funnel_states load fail: %s", exc)
        return None


def _load_waterfall() -> "pd.DataFrame | None":
    import pandas as pd
    p = _waterfall_path()
    if not p.exists():
        log.warning("delivery_waterfall not found: %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        if "ticker" not in df.columns:
            return None
        log.info("Loaded delivery_waterfall: %d rows", len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("delivery_waterfall load fail: %s", exc)
        return None


def _load_events() -> "pd.DataFrame | None":
    import pandas as pd
    p = _events_path()
    if not p.exists():
        log.warning("material_8k_events not found: %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        if "ticker" not in df.columns:
            return None
        log.info("Loaded material_8k_events: %d rows", len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("material_8k_events load fail: %s", exc)
        return None


def _load_statements() -> "pd.DataFrame | None":
    import pandas as pd
    p = _statements_path()
    if not p.exists():
        log.warning("statements not found: %s", p)
        return None
    try:
        df = pd.read_parquet(p)
        if "ticker" not in df.columns:
            return None
        log.info("Loaded statements: %d rows", len(df))
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("statements load fail: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Per-ticker source assembly
# ---------------------------------------------------------------------------

def _funnel_row_to_dict(row: "pd.Series") -> dict:
    """Convert a thesis_funnel_states row to the dict shape assemble_packet expects."""
    import json as _json
    d: dict[str, Any] = {}
    for col in row.index:
        v = row[col]
        # Deserialize JSON strings (e.g. s2_sensors_fired is a JSON list string)
        if isinstance(v, str) and v.startswith("["):
            try:
                v = _json.loads(v)
            except Exception:  # noqa: BLE001
                pass
        # Convert numpy booleans and scalar types
        try:
            import numpy as np
            if isinstance(v, (np.bool_,)):
                v = bool(v)
            elif isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = None if np.isnan(v) else float(v)
        except ImportError:
            pass
        d[col] = v
    return d


def _events_for_ticker(events_df: "pd.DataFrame | None", ticker: str) -> list[dict]:
    """Return material_8k_events rows for ticker as list of dicts."""
    if events_df is None:
        return []
    rows = events_df[events_df["ticker"] == ticker]
    if rows.empty:
        return []
    result = []
    for _, row in rows.iterrows():
        d: dict[str, Any] = {}
        for col in row.index:
            v = row[col]
            try:
                import numpy as np
                if isinstance(v, float) and np.isnan(v):
                    v = None
                elif isinstance(v, (np.bool_,)):
                    v = bool(v)
                elif isinstance(v, (np.integer,)):
                    v = int(v)
                elif isinstance(v, (np.floating,)):
                    v = None if np.isnan(v) else float(v)
            except ImportError:
                pass
            d[col] = v
        result.append(d)
    return result


def _waterfall_best_row(waterfall_df: "pd.DataFrame | None", ticker: str) -> dict | None:
    """Return the most recent non-refused delivery_waterfall row for ticker, or None."""
    if waterfall_df is None:
        return None
    rows = waterfall_df[
        (waterfall_df["ticker"] == ticker) & (waterfall_df["status"] == "ok")
    ]
    if rows.empty:
        return None
    # Sort by t0 descending — pick the most recent episode onset
    rows = rows.sort_values("t0", ascending=False)
    row = rows.iloc[0]
    d: dict[str, Any] = {}
    for col in row.index:
        v = row[col]
        try:
            import numpy as np
            if isinstance(v, float) and np.isnan(v):
                v = None
            elif isinstance(v, (np.bool_,)):
                v = bool(v)
            elif isinstance(v, (np.integer,)):
                v = int(v)
            elif isinstance(v, (np.floating,)):
                v = None if np.isnan(v) else float(v)
            elif isinstance(v, np.ndarray):
                v = v.tolist()
        except ImportError:
            pass
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        d[col] = v
    return d


def _statements_for_ticker(stmts_df: "pd.DataFrame | None", ticker: str) -> "pd.DataFrame | None":
    if stmts_df is None:
        return None
    grp = stmts_df[stmts_df["ticker"] == ticker]
    return grp if not grp.empty else None


# ---------------------------------------------------------------------------
# Packet serialisation helper
# ---------------------------------------------------------------------------

def _make_serialisable(obj: Any) -> Any:
    """Recursively make an object JSON-serialisable."""
    import math
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, str)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _make_serialisable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serialisable(v) for v in obj]
    # numpy types
    try:
        import numpy as np
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return [_make_serialisable(v) for v in obj.tolist()]
    except ImportError:
        pass
    # pandas Timestamp / datetime
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def _has_non_unverifiable(packet: dict) -> bool:
    """True if the packet has at least one sensor not in unverifiable status."""
    for sensor in packet.get("business_evidence_axis") or []:
        if sensor.get("status") != "unverifiable":
            return True
    for event in packet.get("a6_events") or []:
        if event.get("status") in ("challenged", "broken"):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Build A1 falsifier packets.")
    parser.add_argument("--smoke", action="store_true",
                        help="First 50 tickers only (fast smoke-test).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write output files.")
    args = parser.parse_args()

    t0_total = time.time()

    from engine.falsifier_packet import assemble_packet  # noqa: PLC0415

    # ------------------------------------------------------------------
    # 1. Load input artifacts
    # ------------------------------------------------------------------
    log.info("Loading input artifacts...")
    funnel_df = _load_funnel()
    waterfall_df = _load_waterfall()
    events_df = _load_events()
    stmts_df = _load_statements()

    # Determine universe: all tickers with any hold-side data
    tickers: set[str] = set()
    if funnel_df is not None:
        tickers |= set(funnel_df["ticker"].unique())
    if waterfall_df is not None:
        tickers |= set(waterfall_df["ticker"].unique())
    # events-only tickers are edge cases; include them
    if events_df is not None:
        tickers |= set(events_df["ticker"].unique())

    ticker_list = sorted(tickers)
    if args.smoke:
        ticker_list = ticker_list[:50]
        log.info("--smoke: using first %d tickers", len(ticker_list))
    else:
        log.info("Universe: %d tickers", len(ticker_list))

    # ------------------------------------------------------------------
    # 2. Group data by ticker for fast lookup
    # ------------------------------------------------------------------
    funnel_by_ticker: dict[str, dict] = {}
    if funnel_df is not None:
        for ticker, grp in funnel_df.groupby("ticker"):
            # Take most recent row (sort by as_of desc)
            grp = grp.sort_values("as_of", ascending=False)
            funnel_by_ticker[str(ticker)] = _funnel_row_to_dict(grp.iloc[0])

    # ------------------------------------------------------------------
    # 3. Build packets
    # ------------------------------------------------------------------
    all_packets: list[dict] = []
    status_counter: Counter = Counter()
    a6_item_counter: Counter = Counter()
    n_with_non_unverifiable = 0
    n_summary_only = 0

    for ticker in ticker_list:
        funnel_state = funnel_by_ticker.get(ticker)
        waterfall_row = _waterfall_best_row(waterfall_df, ticker)
        events_rows = _events_for_ticker(events_df, ticker)
        stmts_ticker = _statements_for_ticker(stmts_df, ticker)

        sources: dict[str, Any] = {
            "moat_falsifiers_result":   None,    # not available as standalone per-ticker dict here
            "long_hold_clocks_entry":   None,    # not available in batch (embedded in stock JSON)
            "thesis_funnel_state":      funnel_state,
            "capital_allocation_delta": None,    # embedded in stock JSON; not batched here
            "delivery_waterfall_row":   waterfall_row,
            "pricing_power_state":      None,    # embedded in stock JSON
            "material_8k_events_rows":  events_rows,
            "statements_df":            stmts_ticker,
            "price":                    None,    # not available in batch
            "shares":                   None,    # not available in batch
            "net_debt":                 None,    # not available in batch
        }

        packet = assemble_packet(ticker, sources)
        packet = _make_serialisable(packet)

        # Count statuses across all sensors
        for sensor in packet.get("business_evidence_axis") or []:
            s = sensor.get("status")
            if s:
                status_counter[s] += 1
        for event in packet.get("a6_events") or []:
            a6_item_counter[event.get("item_code", "unknown")] += 1

        has_signal = _has_non_unverifiable(packet)
        if has_signal:
            n_with_non_unverifiable += 1
            all_packets.append(packet)
        else:
            n_summary_only += 1
            # Summarized entry: header only, no sensor detail
            all_packets.append({
                "schema": packet["schema"],
                "ticker": ticker,
                "generated_at": packet["generated_at"],
                "_display_only": True,
                "_horizon_role": "hold_thesis",
                "_version": "v1",
                "summary_only": True,
                "note": "All sensors unverifiable — full packet omitted for size cap.",
            })

    # ------------------------------------------------------------------
    # 4. Build output structure
    # ------------------------------------------------------------------
    generated_at = datetime.now(timezone.utc).isoformat()

    packets_out: dict[str, Any] = {
        "schema": "falsifier_packets.v1",
        "generated_at": generated_at,
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
        "counts": {
            "n_tickers": len(ticker_list),
            "n_with_signal": n_with_non_unverifiable,
            "n_summary_only": n_summary_only,
            "sensor_status_counts": dict(status_counter),
            "a6_item_counts": dict(a6_item_counter),
        },
        "packets": all_packets,
        "ffb_r2_coverage_copy": (
            "Advance review in 7 of 12 studied true breaks; 5 of 12 were visible only "
            "coincident with the break. A6 is a hard-stop bus, not a lead generator."
        ),
        "notes": [
            "DISPLAY-ONLY. horizon_role=hold_thesis. MUST NOT feed board ordering, alert triage, "
            "top-setups gates, or push floor (LHB-R2 / LH-R1).",
            "Full packet shown for tickers with at least one non-unverifiable sensor; "
            "summary_only=True for all-unverifiable tickers (size cap).",
            "moat_falsifiers, long_hold_clocks, capital_allocation, price/shares/net_debt: "
            "not available in batch build (embedded in per-stock JSON); "
            "those sensors show unverifiable here — run per-ticker via assemble_packet() for full packet.",
            "EV/sales burden axis uses current-EV approximation (no historical prices in batch).",
        ],
    }

    manifest_out: dict[str, Any] = {
        "schema": "falsifier_packets_manifest.v1",
        "generated_at": generated_at,
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
        "n_tickers": len(ticker_list),
        "n_with_signal": n_with_non_unverifiable,
        "n_summary_only": n_summary_only,
        "sensor_status_counts": dict(status_counter),
        "a6_item_counts": dict(a6_item_counter),
        "input_paths": {
            "thesis_funnel_states": str(_funnel_path()),
            "delivery_waterfall": str(_waterfall_path()),
            "material_8k_events": str(_events_path()),
            "statements": str(_statements_path()),
        },
        "output_paths": {
            "falsifier_packets": str(_out_packets()),
            "falsifier_packets_manifest": str(_out_manifest()),
        },
        "elapsed_seconds": round(time.time() - t0_total, 1),
    }

    # ------------------------------------------------------------------
    # 5. Write outputs
    # ------------------------------------------------------------------
    if args.dry_run:
        log.info(
            "[dry-run] Would write %d packets (%d with signal, %d summary-only) "
            "to %s and manifest to %s",
            len(all_packets), n_with_non_unverifiable, n_summary_only,
            _out_packets(), _out_manifest(),
        )
        log.info(
            "[dry-run] Sensor status counts: %s",
            dict(sorted(status_counter.items())),
        )
        log.info(
            "[dry-run] A6 item counts: %s",
            dict(sorted(a6_item_counter.items())),
        )
        elapsed = round(time.time() - t0_total, 1)
        log.info("[dry-run] Total elapsed: %.1fs", elapsed)
        return 0

    # Write packets JSON
    out_p = _out_packets()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(packets_out, indent=2, ensure_ascii=False))
    log.info("Wrote %s (%.1f KB)", out_p, out_p.stat().st_size / 1024)

    # Write manifest
    out_m = _out_manifest()
    out_m.write_text(json.dumps(manifest_out, indent=2, ensure_ascii=False))
    log.info("Wrote %s", out_m)

    elapsed = round(time.time() - t0_total, 1)
    log.info(
        "Done: %d tickers, %d with signal, %d summary-only, elapsed %.1fs",
        len(ticker_list), n_with_non_unverifiable, n_summary_only, elapsed,
    )
    log.info("Sensor status counts: %s", dict(sorted(status_counter.items())))
    log.info("A6 item counts: %s", dict(sorted(a6_item_counter.items())))

    return 0


if __name__ == "__main__":
    rc = main()
    hard_exit(rc)
