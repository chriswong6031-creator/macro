#!/usr/bin/env python3
"""Stock Identity W2 — the pilot addendum (registration §6, operator ruling 3).

The 2026-08-14 operator return ruled on NYSE ``GOLD``'s instrument identity:

* ``GOLD`` is **Gold.com, Inc.** (fka A-Mark Precious Metals; ``AMRK`` -> ``GOLD``
  on 2025-12-02). The store tape begins 2014-03-17 — A-Mark's spinoff listing —
  and carries **zero Barrick rows** (#5613 forensics). Its W1 "miner neighborhood
  probe" role is void; it is preserved as a **reused-ticker hygiene case study
  (bullion dealer instrument)**.
* **Barrick Mining trades as NYSE ``B``** (``GOLD`` -> ``B`` on 2025-05-09). The
  lineage ``ABX`` -> ``GOLD`` -> ``B`` is ONE continuous NYSE listing through two
  renames, so ``B`` is the intended miner pilot and is added here.

What this writes (every path clearly named as an ADDENDUM; the W1 pilot stores for
the other 21 names are never rewritten)::

    data/stock_identity/ohlcv/B.parquet                     collected tape
    data/stock_identity/ohlcv/manifest.json                 EXTENDED (B entry + lineage)
    data/stock_identity/fingerprints/addendum_b_fingerprint.parquet
    data/stock_identity/state/addendum_b_state.parquet
    data/stock_identity/episodes/addendum_b_catalog.parquet
    data/stock_identity/addendum/pilot_addendum_v1.json     receipts
    research/stock_identity/dossiers/B.md + B.svg
    research/stock_identity/dossiers/GOLD.md + GOLD.svg     REGENERATED (true identity)

Frozen inputs, read-only: ``partition_manifest_v1.json`` (asof, spec hash, procedure
hash), ``si_constants_v1.json`` (episode + state constants), ``fingerprint_spec.json``.
Nothing here re-draws a partition, re-hashes a sealed object, or recalibrates a
constant. ``B`` never entered the W1 universe snapshot, so it is in neither the blind
arm nor SI-SEALED-CAL-P1 **by construction** — asserted by test, not by assumption.

Cross-sectional percentiles for ``B`` are read against the **frozen W1 asof
cross-section** (the 2,780-name raw feature matrix the W1 build produced under the
frozen spec). ``B`` is inserted into that cross-section for its own ranking only;
no other name's published percentile is recomputed and no W1 artifact is rewritten.
The universe raw matrix is a build checkpoint, so ``--stage fingerprint`` will
rebuild it read-only into scratch when it is absent.

Usage::

    python3 scripts/stock_identity_pilot_addendum.py --stage collect
    python3 scripts/stock_identity_pilot_addendum.py --stage atlas,artifacts
    python3 scripts/stock_identity_pilot_addendum.py --stage dossiers
    python3 scripts/stock_identity_pilot_addendum.py --stage all
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.stock_identity import dossier as dossier_mod  # noqa: E402
from engine.stock_identity import episodes as ep_mod  # noqa: E402
from engine.stock_identity import fingerprint as fp_mod  # noqa: E402
from engine.stock_identity import hygiene as hyg_mod  # noqa: E402
from engine.stock_identity import state as state_mod  # noqa: E402
from engine.stock_identity.authority import authority_block  # noqa: E402
from engine.stock_identity.plane import (  # noqa: E402
    PLANE_BASKETS,
    PLANE_PROGRAM,
    PLANE_STOCKS,
    load_symbol,
    plane_dir,
    primary_planes,
    symbols_on_plane,
)

log = logging.getLogger("stock_identity.addendum")

DATA = REPO_ROOT / "data" / "stock_identity"
RESEARCH = REPO_ROOT / "research" / "stock_identity"
DOSSIER_DIR = RESEARCH / "dossiers"
MANIFEST_PATH = DATA / "partition" / "partition_manifest_v1.json"
CONSTANTS_PATH = DATA / "constants" / "si_constants_v1.json"

SCRATCH = Path(
    os.environ.get(
        "STOCK_IDENTITY_REPLAY_SCRATCH",
        "/private/tmp/claude-501/-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-"
        "worktrees-vigorous-mirzakhani-3ae795/c32f41aa-0889-4850-9b1b-a7edd35407e9/scratchpad/"
        "replay_work",
    )
)
W1_CHECKPOINTS = SCRATCH / "w1_checkpoints"

ADDENDUM_SYMBOL = "B"

#: The ruling text, carried verbatim into every artifact this script writes.
RULING_DATE = "2026-08-14"
RULING_CITE = (
    "operator/CEO W1-return ruling 3, 2026-08-14 (#5613 ticker-identity forensics)"
)
B_LINEAGE_NOTE = (
    "ABX -> GOLD (2019-01-02 rename) -> B (2025-05-09 rename): ONE continuous NYSE "
    "listing for Barrick through two symbol changes, not a splice of three instruments. "
    "The tape collected here is that listing under its current symbol. Barrick's retired "
    "symbols are separately occupied today — data/baskets/ohlcv/ABX.parquet (2020-09 "
    "onward) and data/baskets/ohlcv/GOLD.parquet (2014-03-17 onward) are DIFFERENT "
    f"instruments on reused symbols. {RULING_CITE}."
)
B_ROLE = "miner neighborhood probe (Barrick Mining — the intended miner pilot)"
GOLD_ROLE = "reused-ticker hygiene case study (bullion dealer instrument)"
GOLD_CORRECTION = (
    f"**Dated correction ({RULING_DATE}).** This dossier's W1 edition read this tape as "
    "Barrick and assigned it the *miner neighborhood probe* role. That identity was wrong "
    "and is withdrawn. NYSE `GOLD` is **Gold.com, Inc.** (fka A-Mark Precious Metals; "
    "`AMRK` -> `GOLD` on 2025-12-02) — a precious-metals trading and bullion-dealing "
    "business, not a mining company. The tape's 2014-03-17 first print is **A-Mark's "
    "spinoff listing**, and the store carries zero Barrick rows. Barrick Mining trades as "
    "NYSE `B` and is covered by its own dossier in this addendum. Nothing on this page "
    "should be read as a miner's behavior. Authority: "
    f"{RULING_CITE}."
)
GOLD_HYGIENE = {
    "flags": ["reused_symbol_unacked", "instrument_identity_corrected"],
    "notes": {
        "reused_symbol_unacked": (
            "NYSE `GOLD` has carried two unrelated issuers. Barrick used it from the 2019 "
            "`ABX` rename until its own 2025-05-09 rename to `B`; A-Mark Precious Metals "
            "took the freed symbol on 2025-12-02 and now trades as Gold.com, Inc. This "
            "store's tape is the A-MARK instrument throughout (first print 2014-03-17 = "
            "A-Mark's spinoff listing), so the symbol is a reused ticker whose reuse is "
            "absent from config.yml quality.reused_ticker_acks / ticker_key_migrations / "
            "breadth.ticker_fixups. Roster/config repair belongs to the sibling lane "
            "(#5613 + the curated-basket act), not to this program."
        ),
        "instrument_identity_corrected": (
            f"{RULING_CITE}: the W1 dossier's 'continuous Barrick history' note was a "
            "misidentification and is withdrawn. The instrument is the bullion dealer; the "
            "miner is NYSE `B`."
        ),
    },
    "first_print_sanity": "INSTRUMENT_IDENTITY_CORRECTED",
    "first_print_note": (
        "first print 2014-03-17 is A-Mark Precious Metals' spinoff listing date — the "
        "correct first print for THIS instrument, and the receipt that the tape is not "
        "Barrick's (whose NYSE listing long predates it)"
    ),
    "compute_eligible": True,
    "blind_eligible": False,
}

FETCH_CFG: dict[str, float | int] = {
    "retries": 3,
    "backoff_base_s": 5.0,
    "batch_size": 1,
    "sleep_s": 2.0,
}


# ---------------------------------------------------------------------------
# frozen-input readers
# ---------------------------------------------------------------------------
def _manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"missing {MANIFEST_PATH} — W1 partition manifest is a frozen input")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _constants() -> tuple[ep_mod.EpisodeConstants, state_mod.StateConstants, dict[str, Any]]:
    if not CONSTANTS_PATH.exists():
        raise SystemExit(f"missing {CONSTANTS_PATH} — the frozen constants are a frozen input")
    payload = json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))
    v = payload["values"]
    ec = ep_mod.EpisodeConstants(
        X=float(v["X"]), Y=float(v["Y"]), N=int(v["N"]), k=float(v["k"]), z=float(v["z"]),
        M=int(v["M"]), m=int(v["m"]), D1=int(v["D1"]), D2=int(v["D2"]),
        S_reclaim=int(v["S_reclaim"]),
    )
    sc = state_mod.StateConstants(
        g=float(v["g"]), theta_dw=float(v["theta_dw"]), theta_bd=float(v["theta_bd"]),
        theta_pb=float(v["theta_pb"]), theta_up=float(v["theta_up"]), J=float(v["J"]),
        V=int(v["V"]), E=int(v["E"]), R=int(v["R"]),
    )
    return ec, sc, payload


def _scratch(name: str) -> Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return SCRATCH / name


# ---------------------------------------------------------------------------
# stage: collect
# ---------------------------------------------------------------------------
def stage_collect(*, dry_run: bool = False) -> dict[str, Any]:
    """Collect B into the program-owned plane and EXTEND the ohlcv manifest."""
    out_dir = plane_dir(PLANE_PROGRAM, REPO_ROOT)
    for plane_id in (PLANE_STOCKS, PLANE_BASKETS):
        if ADDENDUM_SYMBOL in symbols_on_plane(plane_id, REPO_ROOT):
            raise SystemExit(
                f"REFUSING to collect {ADDENDUM_SYMBOL}: present on curated plane "
                f"{plane_id}. Collecting a curated name would create a second, "
                "differently-adjusted history for one instrument."
            )
    print(f"[gate] {ADDENDUM_SYMBOL}: absent_from_both_curated_planes", flush=True)
    if dry_run:
        return {"dry_run": True}

    try:
        from collectors._stock_ohlc import fetch_ohlc
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"cannot import collectors._stock_ohlc.fetch_ohlc ({exc}). The addendum uses "
            "the house fetcher only — no substitute source (registration §6/§11)."
        ) from exc

    fetched_at = datetime.now(timezone.utc).isoformat()
    frames = fetch_ohlc(
        [ADDENDUM_SYMBOL], "stock_identity_w2", FETCH_CFG, full_history=True, auto_adjust=True
    )
    df = frames.get(ADDENDUM_SYMBOL)
    if df is None or df.empty:
        raise SystemExit(
            f"yfinance returned nothing for {ADDENDUM_SYMBOL}. STOPPING this item rather "
            "than substituting a source (registration §6/§11)."
        )
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.index.name = "Date"
    df.columns = pd.Index(list(df.columns))
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].astype("float64")
    if "open" not in df.columns:
        raise SystemExit(
            f"{ADDENDUM_SYMBOL}: response carried no `open` column — the program-owned "
            "store's whole point is a plane that has one. Not writing a degraded file."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ADDENDUM_SYMBOL}.parquet"
    df.to_parquet(path)

    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    symbols = dict(manifest.get("symbols") or {})
    symbols[ADDENDUM_SYMBOL] = {
        "rows": int(len(df)),
        "first_date": str(df.index[0].date()),
        "last_date": str(df.index[-1].date()),
        "columns": list(df.columns),
        "path": str(path.relative_to(REPO_ROOT)),
        "collected_by": "W2 pilot addendum (registration §6, ruling 3)",
        "fetched_at": fetched_at,
        "lineage_note": B_LINEAGE_NOTE,
    }
    manifest["symbols"] = symbols
    gate_check = dict(manifest.get("gate_check") or {})
    gate_check[ADDENDUM_SYMBOL] = "absent_from_both_curated_planes"
    manifest["gate_check"] = gate_check
    manifest.setdefault("schema", "stock_identity.ohlcv_manifest.v1")
    manifest.setdefault("price_plane_id", PLANE_PROGRAM)
    manifest.setdefault("source", "yfinance")
    manifest.setdefault("fetcher", "collectors._stock_ohlc.fetch_ohlc")
    manifest.setdefault(
        "adjustment_mode", "auto_adjust=True (dividend/split adjusted total-return)"
    )
    manifest.setdefault("fetch_period", "max")
    manifest["w2_addendum"] = {
        "ruling": RULING_CITE,
        "symbol": ADDENDUM_SYMBOL,
        "gate": (
            "registration §6 (ruling 3): Barrick Mining trades as NYSE B and is absent "
            "from both curated TR-adjusted planes; the collection clause fires for it."
        ),
        "lineage_note": B_LINEAGE_NOTE,
        "sealed_objects": (
            "B never entered the W1 universe snapshot, so it is in neither the blind arm "
            "nor SI-SEALED-CAL-P1 by construction; no sealed hash is touched."
        ),
    }
    manifest["authority"] = authority_block()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"[write] {ADDENDUM_SYMBOL}: {len(df)} rows {df.index[0].date()} -> "
        f"{df.index[-1].date()} cols={list(df.columns)} -> {path}",
        flush=True,
    )
    return {"rows": int(len(df)), "first": str(df.index[0].date()),
            "last": str(df.index[-1].date())}


# ---------------------------------------------------------------------------
# stage: atlas — B's W1-layer artifacts under the FROZEN constants
# ---------------------------------------------------------------------------
def _universe_raw() -> pd.DataFrame:
    """The frozen W1 asof raw feature cross-section (build checkpoint, read-only)."""
    p = W1_CHECKPOINTS / "raw_all.parquet"
    if not p.exists():
        raise SystemExit(
            f"missing {p}. The universe raw matrix is a W1 BUILD CHECKPOINT, not a "
            "committed artifact. Rebuild it read-only with\n"
            "  python3 scripts/stock_identity_build_atlas.py --stage atlas,artifacts\n"
            "against a scratch STOCK_IDENTITY_SCRATCH, then copy raw_all.parquet here. "
            "Do NOT let that run rewrite the committed W1 artifacts."
        )
    raw = pd.read_parquet(p)
    if "symbol" in raw.columns:
        raw = raw.set_index("symbol")
    return raw


def _factor_returns() -> pd.Series | None:
    p = W1_CHECKPOINTS / "univ_ew.parquet"
    if not p.exists():
        log.warning("UNIV_EW checkpoint absent — F9 beta/idio features will be null for B")
        return None
    return pd.read_parquet(p)["UNIV_EW"]


def stage_atlas() -> dict[str, Any]:
    """State series, episode catalog and raw fingerprint for B at the FROZEN asof."""
    manifest = _manifest()
    ec, sc, _ = _constants()
    asof = pd.Timestamp(manifest["asof"])

    df = load_symbol(ADDENDUM_SYMBOL, PLANE_PROGRAM, REPO_ROOT)
    df = df.loc[df.index <= asof]
    if df.empty:
        raise SystemExit(f"{ADDENDUM_SYMBOL}: no rows at or before the frozen asof {asof.date()}")

    states = state_mod.tag_states(df, PLANE_PROGRAM, sc)
    catalog = ep_mod.build_catalog(
        df, symbol=ADDENDUM_SYMBOL, plane_id=PLANE_PROGRAM, const=ec,
        states=states["state"],
        terminated_reason="right_censored_at_asof (tape active through asof)",
    )
    f3 = ep_mod.catalog_f3_stats(catalog)
    raw = fp_mod.compute_raw(
        df, plane_id=PLANE_PROGRAM, asof=asof,
        factor_returns=_factor_returns(), catalog_stats=f3,
    )
    raw["symbol"] = ADDENDUM_SYMBOL

    SCRATCH.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([raw]).to_parquet(_scratch("addendum_b_raw.parquet"))
    catalog.to_parquet(_scratch("addendum_b_catalog.parquet"))
    states.to_parquet(_scratch("addendum_b_states.parquet"))
    print(
        f"[atlas] {ADDENDUM_SYMBOL}: {len(df)} sessions <= {asof.date()} · "
        f"{len(catalog)} episodes · {len(states)} state rows",
        flush=True,
    )
    return {"n_sessions": int(len(df)), "n_episodes": int(len(catalog))}


def stage_artifacts() -> dict[str, Any]:
    """Write B's addendum stores (clearly-named ADDITIONS; W1 stores untouched)."""
    manifest = _manifest()
    _, _, constants = _constants()
    asof = manifest["asof"]

    raw_b = pd.read_parquet(_scratch("addendum_b_raw.parquet")).set_index("symbol")
    catalog = pd.read_parquet(_scratch("addendum_b_catalog.parquet"))
    states = pd.read_parquet(_scratch("addendum_b_states.parquet"))

    raw_all = _universe_raw()
    numeric = [
        c for c in raw_all.columns
        if c in set(fp_mod.METRIC_NAMES) | set(fp_mod.DIAGNOSTIC_NUMERIC)
    ]
    # B is inserted into the FROZEN cross-section for its own ranking only. No other
    # name's published percentile is recomputed and no W1 artifact is rewritten.
    joint = pd.concat([raw_all[numeric], raw_b.reindex(columns=numeric)], axis=0)
    pct = fp_mod.cross_sectional_percentiles(joint, numeric)
    unstable = fp_mod.unstable_flags(pct)

    row: dict[str, Any] = {
        "symbol": ADDENDUM_SYMBOL,
        "asof": asof,
        "epoch_key": "epoch_0",
        "epoch_detector": "none/provisional",
        "price_plane_id": raw_b.loc[ADDENDUM_SYMBOL].get("d_price_plane_id"),
        "n_sessions": int(raw_b.loc[ADDENDUM_SYMBOL].get("_n_sessions", 0)),
        "fingerprint_spec_hash": manifest["fingerprint_spec_hash"],
        "addendum_wave": "W2",
        "cross_section_basis": (
            f"frozen W1 asof cross-section ({len(raw_all)} names at {asof}); B inserted "
            "for its own ranking only — no W1 percentile is recomputed"
        ),
    }
    for f in fp_mod.METRIC_NAMES + fp_mod.DIAGNOSTIC_NAMES:
        row[f] = raw_b.loc[ADDENDUM_SYMBOL].get(f)
        if f in numeric:
            row[f"{f}__pct"] = (
                float(pct.loc[ADDENDUM_SYMBOL, f])
                if ADDENDUM_SYMBOL in pct.index and pd.notna(pct.loc[ADDENDUM_SYMBOL, f])
                else None
            )
            row[f"{f}__covered"] = bool(pd.notna(raw_b.loc[ADDENDUM_SYMBOL].get(f)))
            row[f"{f}__unstable"] = bool(unstable.loc[ADDENDUM_SYMBOL, f])
    for k, v in authority_block().items():
        row[f"authority_{k}"] = v

    (DATA / "fingerprints").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([row]).to_parquet(
        DATA / "fingerprints" / "addendum_b_fingerprint.parquet"
    )

    cat = catalog.copy()
    for k, v in authority_block().items():
        cat[f"authority_{k}"] = v
    (DATA / "episodes").mkdir(parents=True, exist_ok=True)
    cat.to_parquet(DATA / "episodes" / "addendum_b_catalog.parquet")

    st = states.reset_index().rename(columns={"Date": "date", "index": "date"})
    st.insert(0, "symbol", ADDENDUM_SYMBOL)
    st.insert(1, "price_plane_id", PLANE_PROGRAM)
    for k, v in authority_block().items():
        st[f"authority_{k}"] = v
    (DATA / "state").mkdir(parents=True, exist_ok=True)
    st.to_parquet(DATA / "state" / "addendum_b_state.parquet")

    receipts = {
        "schema": "stock_identity.pilot_addendum.v1",
        "wave": "W2",
        "asof": asof,
        "ruling": RULING_CITE,
        "authority": authority_block(),
        "symbol_added": {
            "symbol": ADDENDUM_SYMBOL,
            "name": "Barrick Mining Corporation",
            "role": B_ROLE,
            "price_plane_id": PLANE_PROGRAM,
            "lineage_note": B_LINEAGE_NOTE,
            "n_sessions": row["n_sessions"],
            "n_episodes": int(len(catalog)),
            "n_state_rows": int(len(st)),
            "sealed_membership": (
                "absent from the W1 universe snapshot; therefore in neither the blind arm "
                "nor SI-SEALED-CAL-P1 by construction"
            ),
        },
        "symbol_corrected": {
            "symbol": "GOLD",
            "name": "Gold.com, Inc. (fka A-Mark Precious Metals)",
            "role": GOLD_ROLE,
            "w1_role_withdrawn": "miner neighborhood probe",
            "correction": GOLD_CORRECTION,
            "tape_first_print": "2014-03-17 (A-Mark spinoff listing)",
            "artifacts_regenerated": ["research/stock_identity/dossiers/GOLD.md",
                                      "research/stock_identity/dossiers/GOLD.svg"],
            "artifacts_not_touched": (
                "the W1 partition manifest, constants, fingerprint/state/episode stores "
                "and the W1 registration text are hash-pinned frozen inputs; this addendum "
                "is the governing correction record instead"
            ),
        },
        "miner_probe_roster": ["NEM", "AEM", "PAAS", "WPM", "AG", ADDENDUM_SYMBOL],
        "frozen_inputs": {
            "fingerprint_spec_hash": manifest["fingerprint_spec_hash"],
            "partition_procedure_sha256": manifest["partition_procedure_sha256"],
            "calibration_sha256": constants.get("calibration_sha256"),
            "blind_sha256": manifest["blind_arm"]["blind_sha256"],
        },
        "cross_section_basis": row["cross_section_basis"],
    }
    (DATA / "addendum").mkdir(parents=True, exist_ok=True)
    (DATA / "addendum" / "pilot_addendum_v1.json").write_text(
        json.dumps(receipts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"[artifacts] addendum stores written · fingerprint/state/episodes + receipts",
        flush=True,
    )
    return receipts


# ---------------------------------------------------------------------------
# stage: dossiers — B (new) and GOLD (regenerated with the true identity)
# ---------------------------------------------------------------------------
def _snapshot_row(symbol: str, plane_id: str, df: pd.DataFrame) -> dict[str, Any]:
    """The snapshot fields the dossier header reads, computed like W1's stage_snapshot."""
    close = df["close"]
    adv = (
        float((close * df["volume"]).rolling(252, min_periods=200).median().iloc[-1])
        if "volume" in df.columns else float("nan")
    )
    lr = np.log(close / close.shift(1))
    rv = (
        float(lr.iloc[-252:].std(ddof=0) * np.sqrt(252) * 100.0)
        if len(close) >= 252 else float("nan")
    )
    return {
        "symbol": symbol,
        "price_plane_id": plane_id,
        "first_date": df.index[0],
        "last_date": df.index[-1],
        "n_rows": int(len(df)),
        "has_open": "open" in df.columns,
        "adv_252": adv,
        "realized_vol_252": rv,
        "tape_ended": False,
        "terminated_reason": "right_censored_at_asof (tape active through asof)",
    }


def _strata_row(symbol: str) -> dict[str, Any]:
    p = W1_CHECKPOINTS / "strata.parquet"
    if not p.exists():
        return {}
    s = pd.read_parquet(p).set_index("symbol")
    if symbol not in s.index:
        return {}
    return s.loc[symbol, ["sector", "cap_bucket", "vol_tercile"]].to_dict()


def _write_one_dossier(
    *, symbol: str, plane_id: str, pilot_role: str,
    hygiene: dict[str, Any], raw: pd.Series, pct: pd.Series, unstable: pd.Series,
    catalog: pd.DataFrame, prologue: str | None,
) -> None:
    manifest = _manifest()
    _, sc, constants = _constants()
    asof = pd.Timestamp(manifest["asof"])

    df = load_symbol(symbol, plane_id, REPO_ROOT)
    df = df.loc[df.index <= asof]
    st = state_mod.tag_states(df, plane_id, sc)
    shares = state_mod.state_share_by_year(st["state"])

    s = _snapshot_row(symbol, plane_id, df)
    s.update(_strata_row(symbol))

    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    chart = dossier_mod.render_chart(
        symbol=symbol, df=df, states=st["state"], catalog=catalog,
        out_path=DOSSIER_DIR / f"{symbol}.svg",
    )
    md = dossier_mod.render_markdown(
        symbol=symbol, plane_id=plane_id, snapshot_row=s, hygiene=hygiene,
        raw=raw.to_dict(), percentiles=pct.to_dict(),
        coverage={f: bool(pd.notna(raw.get(f))) for f in raw.index},
        unstable=unstable.to_dict(),
        catalog=catalog, state_shares=shares,
        constants_meta={
            "gap_basis": str(st["gap_basis"].iloc[0]) if len(st) else "n/a",
            "constants_sha256": constants.get("calibration_sha256", "n/a"),
            "fingerprint_spec_hash": manifest["fingerprint_spec_hash"],
            "partition_procedure_sha256": manifest["partition_procedure_sha256"],
            "asof": manifest["asof"],
        },
        chart_rel=chart.name,
        pilot_role=pilot_role,
    )
    if prologue:
        lines = md.split("\n")
        # Insert directly under the title + standing-authority paragraph so a reader
        # meets the correction before the identity table, never after it.
        cut = 1
        for i, line in enumerate(lines[1:], start=1):
            if line.startswith("## "):
                cut = i
                break
        md = "\n".join(lines[:cut] + [prologue, ""] + lines[cut:])
    dossier_mod.write_dossier(symbol=symbol, out_dir=DOSSIER_DIR, markdown=md)
    print(f"[dossier] {symbol} -> {DOSSIER_DIR / (symbol + '.md')}", flush=True)


def stage_dossiers() -> dict[str, Any]:
    manifest = _manifest()
    raw_all = _universe_raw()
    raw_b = pd.read_parquet(_scratch("addendum_b_raw.parquet")).set_index("symbol")
    numeric = [
        c for c in raw_all.columns
        if c in set(fp_mod.METRIC_NAMES) | set(fp_mod.DIAGNOSTIC_NUMERIC)
    ]
    joint = pd.concat([raw_all[numeric], raw_b.reindex(columns=numeric)], axis=0)
    pct = fp_mod.cross_sectional_percentiles(joint, numeric)
    unstable = fp_mod.unstable_flags(pct)

    # ---- B (new) ----
    cat_b = pd.read_parquet(_scratch("addendum_b_catalog.parquet"))
    b_hygiene = hyg_mod.check_symbol(
        ADDENDUM_SYMBOL, repo_root=REPO_ROOT,
        first_date=pd.Timestamp(
            load_symbol(ADDENDUM_SYMBOL, PLANE_PROGRAM, REPO_ROOT).index[0]
        ),
    )
    b_hygiene = dict(b_hygiene)
    flags = list(b_hygiene.get("flags") or [])
    notes = dict(b_hygiene.get("notes") or {})
    flags.append("symbol_lineage_note")
    notes["symbol_lineage_note"] = B_LINEAGE_NOTE
    b_hygiene["flags"] = flags
    b_hygiene["notes"] = notes
    _write_one_dossier(
        symbol=ADDENDUM_SYMBOL, plane_id=PLANE_PROGRAM, pilot_role=B_ROLE,
        hygiene=b_hygiene, raw=raw_b.loc[ADDENDUM_SYMBOL],
        pct=pct.loc[ADDENDUM_SYMBOL], unstable=unstable.loc[ADDENDUM_SYMBOL],
        catalog=cat_b,
        prologue=(
            "**Pilot addendum (W2).** Barrick Mining, NYSE `B` — added by the "
            f"{RULING_DATE} operator ruling as the intended miner pilot after NYSE `GOLD` "
            "was resolved to a different issuer. `B` never entered the W1 universe "
            "snapshot, so it is in neither the blind evaluation arm nor the sealed "
            "calibration partition, and no sealed object was touched to add it. Its "
            "percentiles rank against the FROZEN W1 asof cross-section."
        ),
    )

    # ---- GOLD (regenerated with the true identity) ----
    planes = manifest["universe"]["plane_by_symbol"]
    gold_plane = planes.get("GOLD", PLANE_BASKETS)
    ec, sc, _ = _constants()
    asof = pd.Timestamp(manifest["asof"])
    dfg = load_symbol("GOLD", gold_plane, REPO_ROOT)
    dfg = dfg.loc[dfg.index <= asof]
    stg = state_mod.tag_states(dfg, gold_plane, sc)
    cat_g = ep_mod.build_catalog(
        dfg, symbol="GOLD", plane_id=gold_plane, const=ec, states=stg["state"],
        terminated_reason="right_censored_at_asof (tape active through asof)",
    )
    if "GOLD" not in raw_all.index:
        raise SystemExit("GOLD absent from the frozen W1 cross-section checkpoint")
    pct_all_only = fp_mod.cross_sectional_percentiles(raw_all[numeric], numeric)
    unstable_only = fp_mod.unstable_flags(pct_all_only)
    _write_one_dossier(
        symbol="GOLD", plane_id=gold_plane, pilot_role=GOLD_ROLE,
        hygiene=GOLD_HYGIENE, raw=raw_all.loc["GOLD"],
        pct=pct_all_only.loc["GOLD"], unstable=unstable_only.loc["GOLD"],
        catalog=cat_g, prologue=GOLD_CORRECTION,
    )
    return {"written": [ADDENDUM_SYMBOL, "GOLD"]}


STAGES = ("collect", "atlas", "artifacts", "dossiers")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", default="all")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    stages = STAGES if args.stage == "all" else tuple(
        s.strip() for s in args.stage.split(",") if s.strip()
    )
    bad = [s for s in stages if s not in STAGES]
    if bad:
        raise SystemExit(f"unknown stage(s) {bad}; choose from {STAGES}")

    if "collect" in stages:
        stage_collect(dry_run=args.dry_run)
    if "atlas" in stages:
        stage_atlas()
    if "artifacts" in stages:
        stage_artifacts()
    if "dossiers" in stages:
        stage_dossiers()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
