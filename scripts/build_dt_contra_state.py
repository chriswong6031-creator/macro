"""Build the DT-NW-1 artifact — data/neuralweb/dt_contra_state.json.

DT-NW-1 (adjudication §4.2): promotion, not invention (RUL-P5 pattern).
Aggregates the already-computed per-ticker ``dt_contra`` field from the
stockdata JSONs written by ``scripts/build_stock_library.py`` into a small
committed JSON that the Neural Web cortex can cite as a governed display artifact.

DISPLAY-ONLY — authority ceiling: the cortex may reference this artifact to
de-escalate a calibrated key; it may never originate, score, or escalate.
Momentum-dilution law (DT-R11b): this artifact lives on the caution/extension
side only and must never be blended into any momentum ranker.

Run:  python -m scripts.build_dt_contra_state [--stockdata-dir PATH]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import caveat string from the chip module — single source of truth (DT-R11a).
from engine.dannytrades_chip import _CAVEAT as _CHIP_CAVEAT  # noqa: WPS450

log = logging.getLogger("build_dt_contra_state")

# Valid states per chip spec (engine/dannytrades_chip.py assess() output).
_VALID_STATES = frozenset({"fade", "bounce", "neutral"})

# Output path relative to repo root (canonical; also declared in synapse.yml).
_OUT_PATH_REL = "data/neuralweb/dt_contra_state.json"

# Default stockdata directory relative to repo root.
_DEFAULT_STOCKDATA_REL = "site/stockdata"

# Repo root inferred from this file's location.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def build(stockdata_dir: Path | None = None) -> dict:
    """Aggregate per-ticker dt_contra state and write data/neuralweb/dt_contra_state.json.

    Parameters
    ----------
    stockdata_dir:
        Directory containing per-ticker stockdata JSON files (e.g. ``AAPL.json``).
        Defaults to ``<repo_root>/site/stockdata``.

    Returns
    -------
    dict
        The emitted artifact dict (useful for testing). Never raises — degrades
        gracefully when the stockdata directory is absent (CI runners).
    """
    t0 = time.perf_counter()
    out_path = _REPO_ROOT / _OUT_PATH_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    asof = date.today().isoformat()

    if stockdata_dir is None:
        stockdata_dir = _REPO_ROOT / _DEFAULT_STOCKDATA_REL

    # ---------- graceful degradation: absent dir --------------------------------
    if not stockdata_dir.exists():
        log.warning(
            "stockdata dir not found (%s) — emitting degraded dt_contra_state JSON",
            stockdata_dir,
        )
        degraded: dict = {
            "asof": asof,
            "universe_n": 0,
            "n_with_chip": 0,
            "counts_by_state": {},
            "counts_by_band": {},
            "states": [],
            "caveat": _CHIP_CAVEAT,
            "note": f"degraded — stockdata dir absent ({stockdata_dir})",
        }
        out_path.write_text(json.dumps(degraded, indent=2, default=str))
        log.info(
            "dt_contra_state (DEGRADED — dir absent) written to %s in %.2fs",
            out_path,
            time.perf_counter() - t0,
        )
        return degraded

    # ---------- scan per-ticker JSON files -------------------------------------
    json_files = sorted(stockdata_dir.glob("*.json"))
    universe_n = len(json_files)

    states_list: list[dict] = []
    state_counter: Counter = Counter()
    band_counter: Counter = Counter()
    n_parse_errors = 0

    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — additive, never fatal
            log.debug("failed to parse %s (%s) — skipped", jf.name, exc)
            n_parse_errors += 1
            continue

        if not isinstance(data, dict):
            # index.json, fund_flows.json etc. are list-rooted — skip silently.
            log.debug("skipping non-dict JSON root in %s", jf.name)
            continue

        chip = data.get("dt_contra")
        if not chip:
            continue

        state = chip.get("state")
        band = chip.get("band")
        score_pct = chip.get("score_pct")
        whale = chip.get("whale")
        whale_chg = chip.get("whale_chg")

        # Guard against unexpected state values from a future chip change.
        if state not in _VALID_STATES:
            log.debug(
                "ticker %s: unexpected dt_contra state %r — skipped from counts",
                jf.stem, state,
            )

        ticker = jf.stem  # filename without .json = ticker symbol
        states_list.append({
            "ticker": ticker,
            "state": state,
            "band": band,
            "score_pct": score_pct,
            "whale": whale,
            "whale_chg": whale_chg,
        })
        if state is not None:
            state_counter[state] += 1
        if band is not None:
            band_counter[band] += 1

    # Deterministic ordering: sort by ticker symbol so diffs are stable.
    states_list.sort(key=lambda r: r["ticker"])

    if n_parse_errors:
        log.warning("%d stockdata JSON parse errors (skipped)", n_parse_errors)

    output: dict = {
        "asof": asof,
        "universe_n": universe_n,
        "n_with_chip": len(states_list),
        "counts_by_state": dict(sorted(state_counter.items())),
        "counts_by_band": dict(sorted(band_counter.items())),
        "states": states_list,
        "caveat": _CHIP_CAVEAT,
    }

    out_path.write_text(json.dumps(output, indent=2, default=str))
    elapsed = time.perf_counter() - t0
    log.info(
        "dt_contra_state: universe=%d with_chip=%d by_state=%s → %s in %.2fs",
        universe_n,
        len(states_list),
        dict(state_counter),
        out_path,
        elapsed,
    )
    return output


# ---------------------------------------------------------------------------
#  Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="Aggregate per-ticker dt_contra state into data/neuralweb/dt_contra_state.json"
    )
    parser.add_argument(
        "--stockdata-dir",
        type=Path,
        default=None,
        help=(
            f"Directory containing per-ticker stockdata JSON files "
            f"(default: <repo_root>/{_DEFAULT_STOCKDATA_REL})"
        ),
    )
    args = parser.parse_args()
    build(stockdata_dir=args.stockdata_dir)


if __name__ == "__main__":
    main()
