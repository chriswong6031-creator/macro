"""engine.price_pressure.backfill — the one-shot historical seed (masterplan §6).

Run MANUALLY, locally, off the render path and off CI.  It seeds the ledger with
``era="backfill"`` rows over the whole panel span and freezes the base-rate
tables the display quotes.  The nightly never runs this and never re-freezes the
tables.

It also measures the two motivating exemplars under the SHIPPED construction
rather than describing them (operator's adjudication coverage gate, 2026-08-10):

* **MU, April 2025** — expected NOT to fire the idiosyncratic fence, and that is
  correct behavior: on the tariff-shock days the whole semi complex fell
  together, so MU's sector-ex-self residual stayed modest.  The study prints the
  measured worst residual z and the fire count instead of asserting either.
* **CDE, 2026-08** — postdates this store snapshot, so it arrives on the first
  nightly with ``era="gap"``, and it carries two honesty traps the design
  answers: it is not EDGAR-covered (chip must read "filings not tracked for this
  name"), and its GICS peer set is the whole Materials sector, so the thematic
  basket residual is what makes the comparison economically honest.
"""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from engine.price_pressure import base_rates as _br
from engine.price_pressure import detect as _detect
from engine.price_pressure import pipeline as _pipeline
from engine.price_pressure.context import FAMILY_LABELS, family_of
from engine.price_pressure.panel import VOL_TRIGGER, Z_TRIGGER

log = logging.getLogger("price_pressure.backfill")

MU_WINDOW = ("2025-04-01", "2025-04-30")
CDE_TICKER = "CDE"


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=f".tmp_{path.name}_", suffix=".json",
                                     delete=False) as tf:
        tf.write(text + "\n")
        tmp = Path(tf.name)
    tmp.replace(path)
    return path


def day_facts(prep: dict) -> dict:
    """Frozen distribution of the numeric day facts — the broad-selloff marker.

    A NUMBER with a plain-word label, not a day taxonomy: the artifact calls a
    session broad when its ``panel_shock_count`` sits at or above this frozen
    P90.  The base-rate TABLES carry no day split at all (masterplan §12,
    review finding 9): no historical day taxonomy exists to cut them by.
    """
    b = prep["breadth"]
    c = pd.to_numeric(b["panel_shock_count"], errors="coerce").dropna()
    s = pd.to_numeric(b["panel_share_z2"], errors="coerce").dropna()
    return {
        "panel_shock_count_p50": float(np.percentile(c, 50)) if len(c) else None,
        "panel_shock_count_p90": float(np.percentile(c, 90)) if len(c) else None,
        "panel_shock_count_p99": float(np.percentile(c, 99)) if len(c) else None,
        "panel_share_z2_p90": float(np.percentile(s, 90)) if len(s) else None,
        "sessions": int(len(c)),
        "label": ("A session at or above the P90 shock count is described as "
                  "market-wide pressure rather than single-name pressure. This is "
                  "a count threshold, not a classification of the day."),
    }


def exemplar_mu(prep: dict, window: tuple[str, str] = MU_WINDOW) -> dict:
    """MU's measured April-2025 residual path — a non-fire, printed as evidence."""
    d = prep["d"]
    out: dict = {"ticker": "MU", "window": list(window),
                 "expectation": ("expected NOT to fire the single-name fence: on the "
                                 "tariff-shock days the whole semi complex fell "
                                 "together, so the sector-ex-self residual stays modest"),
                 "in_panel": False}
    z = d["f"]["resid_z"]
    if "MU" not in z.columns:
        out["note"] = "MU not in the liquidity-filtered panel"
        return out
    out["in_panel"] = True
    lo, hi = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    idx = (z.index >= lo) & (z.index <= hi)
    zw = z.loc[idx, "MU"]
    av = d["f"]["abn_volume"].loc[idx, "MU"]
    el = d["eligible"].loc[idx, "MU"]
    ret = d["f"]["ret"].loc[idx, "MU"]
    resid = d["resid"].loc[idx, "MU"]
    fires = int(((zw.abs() >= Z_TRIGGER) & (av >= VOL_TRIGGER) & el).sum())
    worst = zw.idxmin() if zw.notna().any() else None
    out.update({
        "fence_fires": fires,
        "z_trigger": float(Z_TRIGGER),
        "worst_resid_z": float(zw.min()) if zw.notna().any() else None,
        "worst_resid_z_date": str(pd.Timestamp(worst).date()) if worst is not None else None,
        "path": [
            {"date": str(pd.Timestamp(dt).date()),
             "ret": None if pd.isna(r) else round(float(r), 4),
             "resid": None if pd.isna(rs) else round(float(rs), 4),
             "resid_z": None if pd.isna(zz) else round(float(zz), 2)}
            for dt, r, rs, zz in zip(zw.index, ret, resid, zw)
            if pd.notna(zz) and abs(float(zz)) >= 1.0
        ],
        "reading": ("The fence separates single-name pressure from a market-wide "
                    "washout. A MU-type secular washout is a different family and "
                    "belongs to the winners-program linkage, not to this fence."),
    })
    return out


def exemplar_cde(prep: dict, ledger: pd.DataFrame) -> dict:
    """CDE's honesty traps, measured against the shipped stores."""
    data_dir = prep["data_dir"]
    covered = False
    try:
        e8k = pd.read_parquet(data_dir / "edgar" / "earnings_8k_dates.parquet",
                              columns=["ticker"])
        covered = CDE_TICKER in set(e8k["ticker"].astype(str).unique())
    except Exception as exc:  # noqa: BLE001
        log.debug("price_pressure: CDE coverage probe failed (%s)", exc)
    fam = family_of(False, False, covered)
    sector = None
    if len(prep["sectors"]) and CDE_TICKER in prep["sectors"].index:
        sector = str(prep["sectors"].loc[CDE_TICKER])
    basket = None
    frames, sizes = prep["baskets"]
    cands = sorted((b for b in frames if CDE_TICKER in frames[b].columns),
                   key=lambda b: (int(sizes[b]), b))
    if cands:
        basket = cands[0]
    in_panel = CDE_TICKER in prep["d"]["f"]["resid_z"].columns
    rows = ledger[ledger["ticker"] == CDE_TICKER] if len(ledger) else ledger
    return {
        "ticker": CDE_TICKER,
        "in_panel": bool(in_panel),
        "edgar_covered": bool(covered),
        "family_if_no_filing_found": fam,
        "family_label": FAMILY_LABELS.get(fam, fam),
        "gics_sector": sector,
        "thematic_basket": basket,
        "events_in_this_seed": int(len(rows)),
        "note": (
            "The 2026-08 episode postdates this store snapshot, so it arrives on "
            "the first nightly with era=\"gap\" via the self-healing catch-up. Two "
            "traps the design answers: EDGAR does not track this ticker, so its "
            "chip reads \"filings not tracked for this name\" and never \"no "
            "filing\"; and its GICS peer set is the whole Materials sector "
            "(chemicals and steel), so a \"peers implied\" line would be "
            "economically false — the thematic basket residual carries the honest "
            "comparison."
        ),
    }


def run(*, store: Path, cache: Path, data_root: Path, data_dir: Path | None = None,
        write_ledger: bool = True) -> dict:
    """Seed the ledger and freeze the base rates.  Returns a stats bag."""
    data_dir = Path(data_dir) if data_dir is not None else Path(data_root)
    prep = _pipeline.prepare(Path(store), Path(cache), data_dir)
    res = _pipeline.advance(prep, Path(data_root), mode="backfill",
                            write=write_ledger, require_nightly_lane=False)
    ledger = res["ledger"]

    payload = _br.build(
        ledger,
        panel_names=prep["panel_names"],
        span=prep["panel_span"],
        design=_detect.constants(),
        day_facts=day_facts(prep),
        exemplars={"MU_2025_04": exemplar_mu(prep),
                   "CDE_2026_08": exemplar_cde(prep, ledger)},
    )
    payload["coverage"]["sector_covered_share"] = (
        round(float(prep["sector_covered_share"]), 4)
        if prep["sector_covered_share"] is not None else None
    )
    p = _br.artifact_path(Path(data_root))
    _write_json(p, payload)

    # Emit the display snapshot too, so the committed set is coherent from the
    # first commit: a base_rates.json with no latest.json next to it would leave
    # every reader (site band, brain packet) with nothing to read until the first
    # nightly. The seed artifact is stamped at the panel's own newest session and
    # carries no day-character banner — it is not describing today.
    from engine.price_pressure import artifact as _artifact

    display = _artifact.build(
        ledger, root=Path(data_root).parent, panel_names=prep["panel_names"],
        panel_span=prep["panel_span"], design=_detect.constants(),
        base_rates=payload, sector_covered_share=prep["sector_covered_share"],
        basket_labels=prep.get("basket_labels"),
        extra_gaps=["seed: rows are era=backfill; forward-era accrual starts at "
                    "the first nightly"],
    )
    display_path = _artifact.write(display, Path(data_root))
    return {"stats": res["stats"], "base_rates_path": str(p),
            "artifact_path": str(display_path), "prep": prep,
            "ledger": ledger, "payload": payload, "display": display}
