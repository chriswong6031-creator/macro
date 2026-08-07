"""Build the dispersion regime artifact — data/dispersion/regime.json.

L3 chartered lobe (NW Rails program §5). Promotes the existing engine/dispersion.py
output to a registered nightly artifact + display chip. No new math — this builder
reconstructs the same ext-universe returns panel that build_stock_library.main() uses
(via the breadth close caches, same _TIERS order and dedup logic), calls the same
dispersion.assess() call, and emits a standalone JSON so downstream consumers can read
the regime without importing build_stock_library.

Run:  python -m scripts.build_dispersion_regime
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import dispersion  # noqa: E402
from lib import config  # noqa: E402
from lib.closes_panel import disclose_merge, merge_close_caches  # noqa: E402

log = logging.getLogger("build_dispersion_regime")

# tiers whose wide close caches together form the ext-universe (same order +
# dedup logic as build_stock_library.universe() / build_impulse._load_panel).
_TIERS = ("breadth", "midcap_breadth", "smallcap_breadth")

# Rolling history length stored in the JSON (regime states, one per trading day).
_HISTORY_LEN = 252

# Output path (canonical; also declared in synapse.yml).
_OUT_PATH_REL = "data/dispersion/regime.json"


# ---------------------------------------------------------------------------
#  Panel reconstruction — mirrors build_stock_library._ext_closes logic
# ---------------------------------------------------------------------------

def _load_closes() -> pd.DataFrame:
    """Merge the per-tier wide close caches into a single panel.

    Priority = tier order: breadth → midcap_breadth → smallcap_breadth.
    A ticker taken from an earlier tier is NOT re-added from a later one.
    Duplicate columns dropped; result sorted by date index.

    Returns an empty DataFrame when no cache exists (builder degrades gracefully).
    """
    for tier in _TIERS:
        p = config.data_dir() / tier / "_closes_cache.parquet"
        if not p.exists():
            # Bare print, never the logger — the prefixing log format makes GitHub
            # drop the annotation silently (tests/test_gh_annotation_line_start.py).
            print(f"::warning title=dispersion_regime::close cache missing for tier "
                  f"{tier} ({p}) — tier skipped; regime universe thinner than the "
                  "board's", flush=True)
            log.warning("close cache missing for tier %s — skipped", tier)
    # Freshest column per ticker (lib/closes_panel.py) — tier order alone hands an index
    # migrant the column from the tier it LEFT, which is NaN at the tip and so drops the
    # name out of the cross-section entirely. Unreadable tiers are skipped in there.
    panel, meta = merge_close_caches(_TIERS)
    disclose_merge(meta, "dispersion_regime")
    return panel


# ---------------------------------------------------------------------------
#  History maintenance — rolling 252-day state log in the JSON
# ---------------------------------------------------------------------------

def _load_history(out_path: Path) -> list[dict]:
    """Load the existing history list from the output JSON (if it exists)."""
    if not out_path.exists():
        return []
    try:
        existing = json.loads(out_path.read_text())
        return existing.get("history", [])
    except Exception:  # noqa: BLE001
        return []


def _update_history(history: list[dict], today_entry: dict) -> list[dict]:
    """Append today's state entry and keep the last _HISTORY_LEN days."""
    # Deduplicate by as_of (keep the latest record for any given date).
    as_of = today_entry.get("as_of")
    pruned = [h for h in history if h.get("as_of") != as_of]
    pruned.append(today_entry)
    return pruned[-_HISTORY_LEN:]


# ---------------------------------------------------------------------------
#  Main builder
# ---------------------------------------------------------------------------

def build() -> dict:
    """Run the dispersion assessment and write data/dispersion/regime.json.

    Returns the emitted dict (useful for testing).  Never raises — on any error
    a degraded JSON (state=null) is written and the function returns it.
    """
    t0 = time.perf_counter()
    out_path = config.data_dir() / "dispersion" / "regime.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    as_of = date.today().isoformat()
    history = _load_history(out_path)

    # ---------- load panel ------------------------------------------------
    closes = _load_closes()

    # ---------- assess ----------------------------------------------------
    result: dict | None = None
    if not closes.empty:
        try:
            returns = closes.pct_change(fill_method=None).tail(280)
            result = dispersion.assess(returns)
        except Exception as e:  # noqa: BLE001
            print(f"::warning title=dispersion_regime::dispersion.assess() crashed ({e}) "
                  "— emitting degraded regime.json (state=null)", flush=True)
            log.warning("dispersion.assess() failed (%s) — emitting degraded JSON", e,
                        exc_info=True)

    # ---------- build output ----------------------------------------------
    if result is None:
        # Degraded path: sparse universe or assess() failure. This overwrites the
        # committed regime.json with state=null — leader radar reads it same-night —
        # so the degrade must be loud (the silent form of this is how index_leadership
        # froze for 18 nightlies, PR #4363).
        print("::warning title=dispersion_regime::assess() produced no state (empty/"
              "sparse close-cache universe, or the crash above) — DEGRADED regime.json "
              "(state=null) written; leader radar + pick lab read a null regime until "
              "the next good run", flush=True)
        log.warning(
            "dispersion.assess() returned None (sparse universe or error) — "
            "emitting degraded regime JSON"
        )
        degraded: dict = {
            "as_of": as_of,
            "state": None,
            "dispersion_pctile": None,
            "avg_corr": None,
            "shadow_gross_mult": None,
            "gross_mult_live": 1.0,
            "passport": {
                "basis": "prior",
                "verdict": "display-only per US_BOARD_MEASUREMENT",
                "validation": {
                    "artifact": "research/US_BOARD_MEASUREMENT.md#study-3",
                    "n": None,
                    "survives": False,
                },
                "note": "degraded — universe too sparse for assess()",
            },
            "history": history,
        }
        out_path.write_text(json.dumps(degraded, indent=2, default=str))
        elapsed = time.perf_counter() - t0
        log.info("dispersion regime (DEGRADED) written to %s in %.2fs", out_path, elapsed)
        return degraded

    # Normal path — mirror assess() field names verbatim per spec §5.
    # History entries are kept slim: eigen block is intentionally excluded
    # (bulk SVD fields would bloat the 252-entry rolling history list).
    today_entry = {
        "as_of": as_of,
        "state": result["state"],
        "dispersion_pctile": result.get("dispersion_pctile"),
        "avg_corr": result.get("avg_corr"),
    }
    history = _update_history(history, today_entry)

    output: dict = {
        # ---- fields mirroring assess() output verbatim (§5) ----
        "as_of": as_of,
        "state": result["state"],
        "dispersion_pctile": result.get("dispersion_pctile"),
        "avg_corr": result.get("avg_corr"),
        "shadow_gross_mult": result["shadow_gross_mult"],
        # HARD CONSTRAINT §5 + §10: gross_mult stays clamped 1.0;
        # this PR changes display and measurement only.
        "gross_mult_live": 1.0,
        # passport carried through verbatim (basis/verdict/survives provenance
        # must travel with the artifact per spec §5)
        "passport": result["passport"],
        # rolling 252-day state history (maintained in-place each nightly run)
        # NOTE: eigen block is excluded from history rows (kept slim).
        "history": history,
        # convenience display labels (from dispersion._LABEL)
        "label": result.get("label"),
        "label_zh": result.get("label_zh"),
        # eigen-concentration block (display-only; DISP-EIGEN-1, activation DEFERRED)
        # emitted at top-level only — NOT in history rows (size discipline).
        "eigen": result.get("eigen"),
    }

    out_path.write_text(json.dumps(output, indent=2, default=str))
    elapsed = time.perf_counter() - t0
    eigen_summary = (
        f"eigen.dom_pc={output['eigen']['dominant_equity_pc_share']}"
        if output.get("eigen") else "eigen=None"
    )
    log.info(
        "dispersion regime: %s (pctile=%s, avg_corr=%s, %s) → gross_mult_live=1.0 "
        "written to %s in %.2fs",
        output["state"], output["dispersion_pctile"], output["avg_corr"],
        eigen_summary, out_path, elapsed,
    )
    return output


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

def main() -> dict:
    """Nightly entrypoint (daily.yml run_py). A degraded emit HERE is a real fault —
    the engine job restores the breadth close caches before this runs, and the
    degraded JSON overwrites the committed regime.json with state=null for every
    same-night consumer (leader radar, pick lab) — so it exits non-zero: run_py only
    alerts on rc != 0 (the step runs `set +e`, so the job never aborts). Tests and
    ad-hoc callers use build() directly, which keeps its never-raise contract."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    out = build()
    ok = out.get("state") is not None
    if not ok:
        print("::error title=dispersion_regime::nightly wrote a DEGRADED regime.json "
              "(state=null) — see the ::warning above for the missing input", flush=True)
    return {"ok": ok}


if __name__ == "__main__":
    raise SystemExit(0 if main()["ok"] else 1)
