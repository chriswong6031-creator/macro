"""engine.price_pressure.pipeline — the ONE harvest → merge → grade path.

The historical backfill and the nightly increment are the same pipeline over
different windows.  They live in one function on purpose: two code paths would
be two constructions, the backfill's frozen base rates would drift from the
rows the nightly appends, and every published table would quietly stop
describing the ledger it sits next to.  ``mode`` changes only the WINDOW and the
ERA rule (masterplan §5) — never the math.

Nothing here writes unless ``write=True`` and the ledger lane allows it: any
lane may compute a display, only the nightly may advance the ledger.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from engine.price_pressure import completion as _completion
from engine.price_pressure import context as _ctx
from engine.price_pressure import detect as _detect
from engine.price_pressure import ledger as _ledger
from engine.price_pressure import panel as _panel

log = logging.getLogger("price_pressure.pipeline")


def load_sectors(data_dir: Path) -> pd.Series:
    """The GICS map ``derive`` itself residualizes against (same file, same shape)."""
    p = Path(data_dir) / "breadth" / "ticker_sectors.parquet"
    if not p.exists():
        return pd.Series(dtype="object")
    return pd.read_parquet(p).set_index("ticker")["sector"]


def prepare(store: Path, cache: Path, data_dir: Path) -> dict:
    """Build the panel and every frame the identity block needs.  ~45-60s.

    Returned dict is a plain bag so the caller can inspect timings and coverage
    without this module owning a class nobody else wants.
    """
    t0 = time.time()
    pan = _panel.load_panel(Path(cache), Path(store))
    t_panel = time.time() - t0

    t1 = time.time()
    d = _detect.derive_frames(pan, Path(data_dir))
    sectors = load_sectors(Path(data_dir))
    sessions = d["sessions"]
    membership = _ctx.load_basket_membership(Path(data_dir))
    baskets = _ctx.basket_residual_frames(d["f"]["ret"], membership)
    out = {
        "panel": pan,
        "d": d,
        "sessions": sessions,
        "sectors": sectors,
        "breadth": _detect.breadth_by_date(d),
        "peer_shocks": _detect.peer_shock_by_date(d, sectors),
        "peer_basis": _detect.peer_basis_mask(d, sectors),
        "spy_z": _ctx.spy_return_z(Path(data_dir), sessions),
        "vix_pct": _ctx.vix_percentile(Path(data_dir), sessions),
        "pos_frames": _ctx.position_frames(pan),
        "revisions_covered": _ctx.revisions_covered_set(Path(data_dir)),
        "membership": membership,
        "baskets": baskets,
        "basket_labels": _ctx.basket_labels(Path(data_dir)),
        "data_dir": Path(data_dir),
        "timing_s": {"panel": round(t_panel, 1), "derive": round(time.time() - t1, 1)},
    }
    names = pan["close"].shape[1]
    labelled = int(sectors.reindex(pan["close"].columns).notna().sum()) if len(sectors) else 0
    out["panel_names"] = int(names)
    out["sector_covered_share"] = (labelled / names) if names else None
    out["panel_span"] = (str(sessions[0].date()), str(sessions[-1].date())) if len(sessions) else ("", "")
    return out


def harvest_rows(prep: dict, window: pd.DatetimeIndex, *, era: str,
                 harvested_asof: str) -> pd.DataFrame:
    """Identity rows for every shock inside ``window`` — the frozen PIT block."""
    ev = _detect.harvest(prep["d"], window=window)
    if ev.empty:
        return _ledger.empty_ledger()
    ev = _ctx.attach_filings(ev, prep["data_dir"])
    ev = _ctx.attach_families(ev)
    ev = _ctx.attach_basket_context(ev, prep["d"]["f"]["ret"], prep["membership"],
                                    precomputed=prep["baskets"])
    return _ledger.identity_rows(
        ev, era=era, harvested_asof=harvested_asof,
        sectors=prep["sectors"], peer_basis=prep["peer_basis"],
        breadth=prep["breadth"], peer_shocks=prep["peer_shocks"],
        spy_z=prep["spy_z"], vix_pct=prep["vix_pct"],
        pos_frames=prep["pos_frames"], revisions_covered=prep["revisions_covered"],
    )


def advance(prep: dict, data_root: Path, *, mode: str = "nightly",
            write: bool = True, require_nightly_lane: bool = True,
            min_sessions: int = 15, cap: int = 90,
            lookback: int = 5) -> dict:
    """Harvest the window, merge idempotently, re-grade every open row.

    ``mode="nightly"``  — self-healing catch-up window (§4.0/§6): from the
    ledger's own max date minus ``lookback`` sessions to the store's newest
    session, floored at ``min_sessions`` and capped at ``cap``.  Rows landing on
    the newest session are era ``forward``; anything the catch-up picked up late
    is era ``gap``.

    ``mode="backfill"`` — the whole panel span, era ``backfill``, refusing to
    touch any row already forward or gap.

    The nightly additionally runs the §10.1 VIXCLS stamp-completion pass after
    the advance (``completion.py``): the FRED store trails the tape at harvest,
    so a row's own ``vix_pctile`` often arrives a night late, and completing it
    inside the row's maturity window is what keeps the R4 evidence arms from
    starving to zero.  The backfill does not run it — the prereg names the
    nightly producer, and a historical seed's rows are stamped from a store that
    already carries their dates.
    """
    t0 = time.time()
    sessions = prep["sessions"]
    stored = _ledger.read_ledger(data_root)
    ledger_max = pd.Timestamp(stored["date"].max()) if len(stored) else None
    asof_session = pd.Timestamp(sessions[-1]) if len(sessions) else None

    if mode == "backfill":
        window = sessions
        era = "backfill"
    elif mode == "nightly":
        window = _ledger.catchup_window(sessions, ledger_max, lookback=lookback,
                                        min_sessions=min_sessions, cap=cap)
        era = "gap"   # merge() re-stamps the newest session's rows as forward
    else:
        raise ValueError(f"unknown mode {mode!r}")

    harvested_asof = asof_session.strftime("%Y-%m-%d") if asof_session is not None else ""
    fresh = harvest_rows(prep, window, era=era, harvested_asof=harvested_asof)
    merged, mstats = _ledger.merge(stored, fresh, mode=mode, asof_session=asof_session)
    merged = _ledger.assign_episodes(merged, sessions)
    graded, gstats = _ledger.grade(merged, prep["d"]["cum"], sessions)

    # §10.1 stamp completion — AFTER the advance, and only on the nightly, which
    # is the producer the prereg names.  It runs against the VIXCLS store as of
    # this run: the FRED collector refreshes and commits that store in the
    # earlier `collect` job, so a t0 close that FRED published late simply lands
    # on the next night, inside the row's own window.  Receipts are held back
    # until the ledger write is known to have landed (completion module
    # docstring) — a receipt filed against a skipped write would fence the row
    # out of its own window forever.
    cstats: dict = {}
    creceipts: list[dict] = []
    if mode == "nightly":
        comp = _completion.run(graded, data_root, data_dir=prep["data_dir"],
                               sessions=sessions, asof=asof_session)
        graded, creceipts, cstats = comp["ledger"], comp["receipts"], comp["stats"]

    wstats = {"written": False, "reason": "write=False", "rows": int(len(graded))}
    if write:
        wstats = _ledger.write_ledger(graded, data_root,
                                      require_nightly_lane=require_nightly_lane)

    if cstats:
        appended = (_completion.append_receipts(data_root, creceipts)
                    if (creceipts and wstats.get("written")) else 0)
        cstats["receipts"] = appended
        if cstats.get("candidates"):
            print(_completion.log_line(cstats), flush=True)

    stats = {
        "mode": mode,
        "window": [str(pd.Timestamp(window[0]).date()), str(pd.Timestamp(window[-1]).date())]
        if len(window) else None,
        "window_sessions": int(len(window)),
        "asof_session": harvested_asof or None,
        "ledger_max_before": str(ledger_max.date()) if ledger_max is not None and pd.notna(ledger_max) else None,
        "merge": mstats,
        "grade": gstats,
        "completion": cstats,
        "write": wstats,
        "elapsed_s": round(time.time() - t0, 1),
    }
    log.info("price_pressure: %s window=%s rows=%d appended=%d advanced=%d closed=%d",
             mode, stats["window"], len(graded), mstats.get("appended", 0),
             gstats.get("advanced", 0), gstats.get("closed", 0))
    return {"ledger": graded, "stats": stats}
