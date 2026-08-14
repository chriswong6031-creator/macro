#!/usr/bin/env python3
"""Build the Identity Atlas v0 (W1 / PR-1) — staged, idempotent, resumable.

The stage order IS the registration's draw order, and the script enforces it:

    snapshot   universe enumeration + hygiene + shape facts   -> universe_snapshot_v1.parquet
    pilot      pilot cohort fixed by rule (incl. IPO /         -> scratch receipts
               secular-decliner / dead-name picks)
    partition  blind arm drawn, THEN calibration partition,    -> partition_manifest_v1.json
               THEN hashes written
    --- scripts/stock_identity_calibrate.py runs here; it refuses without the manifest ---
    atlas      per-name states + episode catalog + fingerprint -> scratch chunks
    artifacts  pilot parquets + cross-sectional percentiles    -> data/stock_identity/**
    census     coverage census over universe minus blind       -> census parquet + md
    dossiers   per-name markdown + chart for the pilot         -> research/stock_identity/dossiers

``atlas`` refuses to start before the constants file exists, because states and
episodes are *defined by* the frozen constants — running them first would mean the
catalog helped choose the numbers that define it.

Heavy compute is chunked with a checkpoint per chunk under the scratch directory
and never lands universe-scale intermediates in ``data/``. Nothing here touches
``site/`` or any render path (registration §11).

Usage::

    python3 scripts/stock_identity_build_atlas.py --stage snapshot,pilot,partition
    python3 scripts/stock_identity_calibrate.py
    python3 scripts/stock_identity_build_atlas.py --stage atlas --workers 8
    python3 scripts/stock_identity_build_atlas.py --stage artifacts,census,dossiers
"""
from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.stock_identity import census as census_mod  # noqa: E402
from engine.stock_identity import dossier as dossier_mod  # noqa: E402
from engine.stock_identity import episodes as ep_mod  # noqa: E402
from engine.stock_identity import fingerprint as fp_mod  # noqa: E402
from engine.stock_identity import hygiene as hyg_mod  # noqa: E402
from engine.stock_identity import partition as part_mod  # noqa: E402
from engine.stock_identity import state as state_mod  # noqa: E402
from engine.stock_identity.authority import authority_block  # noqa: E402
from engine.stock_identity.plane import (  # noqa: E402
    PLANE_BASKETS,
    load_symbol,
    primary_planes,
)

log = logging.getLogger("stock_identity.atlas")

DATA = REPO_ROOT / "data" / "stock_identity"
RESEARCH = REPO_ROOT / "research" / "stock_identity"
REGISTRATION = RESEARCH / "W1_IDENTITY_ATLAS_V0_REGISTRATION.md"
MANIFEST_PATH = DATA / "partition" / "partition_manifest_v1.json"
CONSTANTS_PATH = DATA / "constants" / "si_constants_v1.json"

SCRATCH = Path(
    os.environ.get(
        "STOCK_IDENTITY_SCRATCH",
        "/private/tmp/claude-501/-Users-chriswong-Documents-Cluade-Macro-Dashboard--claude-"
        "worktrees-vigorous-mirzakhani-3ae795/c32f41aa-0889-4850-9b1b-a7edd35407e9/scratchpad/"
        "atlas_work",
    )
)

CALIBRATION_LOOKBACK_SESSIONS = 126

# --- pilot cohort, registration §2 -------------------------------------------
OPERATOR_CORE = ("KRUS", "MCK", "NVDA", "REGN", "YELP", "KO", "WMT", "MCD", "BABA")
MINER_PROBE = ("NEM", "GOLD", "AEM", "PAAS", "WPM", "AG")
DISAGREEMENT = ("UEC", "HL")
STRESSORS = ("MSFT", "META")
PILOT_ROLES: dict[str, str] = {
    **{s: "operator core" for s in OPERATOR_CORE},
    **{s: "miner neighborhood probe" for s in MINER_PROBE},
    **{s: "disagreement set" for s in DISAGREEMENT},
    "MSFT": "stressor — steady-trender control",
    "META": "stressor — known epoch-changer",
}
PILOT_ROLES["NEM"] = "miner neighborhood probe + disagreement set"

DEAD_MIN_SESSIONS = 756
DEAD_TAPE_END_SESSIONS = 126
DEAD_NEED = 5
IPO_MIN_SESSIONS = 60
IPO_MAX_SESSIONS = 252
DECLINER_MIN_SESSIONS = 1000
DECLINER_WINDOW = 1260


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _scratch(name: str) -> Path:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    return SCRATCH / name


def _load_constants() -> tuple[ep_mod.EpisodeConstants, state_mod.StateConstants, dict[str, Any]]:
    if not CONSTANTS_PATH.exists():
        raise SystemExit(
            f"REFUSING: no constants at {CONSTANTS_PATH}. States and episodes are DEFINED "
            "by the frozen constants, so building them first would let the catalog help "
            "choose the numbers that define it. Run scripts/stock_identity_calibrate.py."
        )
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


# ---------------------------------------------------------------------------
# stage: snapshot
# ---------------------------------------------------------------------------
def _snapshot_one(args: tuple[str, str]) -> dict[str, Any] | None:
    symbol, plane_id = args
    try:
        df = load_symbol(symbol, plane_id, REPO_ROOT)
    except Exception as exc:  # noqa: BLE001
        log.warning("%s: unreadable on %s (%s)", symbol, plane_id, exc)
        return None
    if df.empty:
        return None
    close = df["close"]
    adv = float((close * df["volume"]).rolling(252, min_periods=200).median().iloc[-1]) \
        if "volume" in df.columns else float("nan")
    lr = np.log(close / close.shift(1))
    rv = float(lr.iloc[-252:].std(ddof=0) * np.sqrt(252) * 100.0) if len(close) >= 252 else float("nan")
    return {
        "symbol": symbol,
        "price_plane_id": plane_id,
        "first_date": df.index[0],
        "last_date": df.index[-1],
        "n_rows": int(len(df)),
        "has_open": "open" in df.columns,
        "adv_252": adv,
        "realized_vol_252": rv,
        "dates": df.index.values.astype("datetime64[ns]").astype("int64"),
    }


def stage_snapshot(workers: int) -> pd.DataFrame:
    planes = primary_planes(REPO_ROOT)
    tasks = sorted(planes.items())
    print(f"[snapshot] enumerating {len(tasks)} symbols across the allowed planes", flush=True)
    with mp.Pool(processes=max(1, workers)) as pool:
        rows = [r for r in pool.imap_unordered(_snapshot_one, tasks, chunksize=16) if r]

    all_dates = np.unique(np.concatenate([r.pop("dates") for r in rows]))
    calendar = pd.DatetimeIndex(all_dates.astype("datetime64[ns]"))
    np.save(_scratch("session_calendar.npy"), all_dates)

    snap = pd.DataFrame(rows).sort_values("symbol").reset_index(drop=True)

    # asof = the last trading date common to both curated planes at build time
    last_by_plane = snap.groupby("price_plane_id")["last_date"].max()
    asof = pd.Timestamp(min(last_by_plane.to_list()))
    print(f"[snapshot] last_date by plane: {dict(last_by_plane)} -> asof={asof.date()}", flush=True)

    hyg_rows = []
    asof_pos = int(calendar.searchsorted(pd.Timestamp(asof)))
    for r in snap.itertuples(index=False):
        h = hyg_mod.check_symbol(r.symbol, repo_root=REPO_ROOT, first_date=r.first_date)
        lag = asof_pos - int(calendar.searchsorted(pd.Timestamp(r.last_date)))
        tape_ended = bool(lag >= DEAD_TAPE_END_SESSIONS)
        # The truncation reason is stated at the confidence the evidence supports. A tape
        # that runs to asof is right-censored by the build date and nothing more; a tape
        # that stops a few weeks short is stale-vs-ceased UNRESOLVED, and calling that a
        # death would be the "delisted is not stale" error the ledger exists to prevent.
        if tape_ended:
            reason = hyg_mod.dead_name_reason(r.symbol, REPO_ROOT)
        elif lag > 0:
            reason = (
                f"store tape ends {lag} session(s) before asof; stale-vs-ceased unresolved"
            )
        else:
            reason = "right_censored_at_asof (tape active through asof)"
        hyg_rows.append(
            {
                "symbol": r.symbol,
                "hygiene_flags": ",".join(h["flags"]),
                "first_print_sanity": h["first_print_sanity"],
                "first_print_note": h["first_print_note"],
                "compute_eligible": h["compute_eligible"],
                "blind_eligible": h["blind_eligible"],
                "tape_end_lag_sessions": lag,
                "tape_ended": tape_ended,
                "terminated_reason": reason,
            }
        )
    snap = snap.merge(pd.DataFrame(hyg_rows), on="symbol", how="left")
    snap["asof"] = asof
    snap["authority_can_rank"] = False
    snap["authority_can_size"] = False
    snap["authority_can_gate"] = False
    snap["authority_can_originate_signal"] = False
    snap["authority_can_escalate"] = False

    out = DATA / "partition" / "universe_snapshot_v1.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    snap.to_parquet(out)
    print(
        f"[snapshot] {len(snap)} names -> {out} · tape_ended={int(snap['tape_ended'].sum())} · "
        f"compute-ineligible={int((~snap['compute_eligible']).sum())}",
        flush=True,
    )
    return snap


def _read_snapshot() -> pd.DataFrame:
    p = DATA / "partition" / "universe_snapshot_v1.parquet"
    if not p.exists():
        raise SystemExit(f"missing {p} — run --stage snapshot first")
    return pd.read_parquet(p)


def _read_calendar() -> pd.DatetimeIndex:
    p = _scratch("session_calendar.npy")
    if not p.exists():
        raise SystemExit("missing session calendar checkpoint — re-run --stage snapshot")
    return pd.DatetimeIndex(np.load(p).astype("datetime64[ns]"))


# ---------------------------------------------------------------------------
# stage: pilot
# ---------------------------------------------------------------------------
def _max_drawdown_final_window(symbol: str, plane_id: str, window: int) -> float:
    df = load_symbol(symbol, plane_id, REPO_ROOT)
    close = df["close"].astype(float).iloc[-window:]
    if len(close) < 2:
        return float("nan")
    run_max = close.cummax()
    return float((close / run_max - 1.0).min())


def stage_pilot(snap: pd.DataFrame) -> dict[str, Any]:
    receipts: dict[str, Any] = {}
    present = set(snap["symbol"])

    fixed = [s for s in (OPERATOR_CORE + MINER_PROBE + DISAGREEMENT + STRESSORS)]
    missing = [s for s in fixed if s not in present]
    receipts["fixed_membership"] = {
        "members": fixed,
        "absent_from_universe": missing,
        "note": "registration §13 fixed membership plus the two PR-1 rule-chosen picks",
    }

    # --- recent IPO: baskets plane, most recent first_date, 60 <= n < 252, no flags
    ipo_pool = snap[
        (snap["price_plane_id"] == PLANE_BASKETS)
        & (snap["n_rows"] >= IPO_MIN_SESSIONS)
        & (snap["n_rows"] < IPO_MAX_SESSIONS)
        & (snap["hygiene_flags"].fillna("") == "")
    ].sort_values("first_date", ascending=False)
    if ipo_pool.empty:
        raise SystemExit("no name satisfies the recent-IPO rule — reporting rather than relaxing it")
    ipo = str(ipo_pool.iloc[0]["symbol"])
    receipts["recent_ipo"] = {
        "pick": ipo,
        "rule": (
            "the baskets-plane name with the most recent first_date having >=60 and <252 "
            "sessions and no hygiene flags"
        ),
        "pool_size": int(len(ipo_pool)),
        "first_date": str(pd.Timestamp(ipo_pool.iloc[0]["first_date"]).date()),
        "n_rows": int(ipo_pool.iloc[0]["n_rows"]),
        "runners_up": [
            {"symbol": str(r.symbol), "first_date": str(pd.Timestamp(r.first_date).date()),
             "n_rows": int(r.n_rows)}
            for r in ipo_pool.iloc[1:4].itertuples(index=False)
        ],
    }

    # --- dead pool: ceased tape, >= 756 sessions, on an allowed plane -------
    dead_pool_df = snap[
        (snap["tape_ended"]) & (snap["n_rows"] >= DEAD_MIN_SESSIONS) & (snap["compute_eligible"])
    ]
    dead_pool = sorted(dead_pool_df["symbol"].tolist())

    ledger_syms = sorted(hyg_mod._load_delisted(str(REPO_ROOT)).keys())
    ledger_on_plane = [s for s in ledger_syms if s in present]
    max_lag = int(snap["tape_end_lag_sessions"].max())
    lag_top = (
        snap.nlargest(8, "tape_end_lag_sessions")[["symbol", "last_date", "tape_end_lag_sessions"]]
        .assign(last_date=lambda d: d["last_date"].astype(str).str[:10])
        .to_dict("records")
    )

    # --- secular decliner ---------------------------------------------------
    # Masterplan §13 sources this pick from the "delisted/**damaged** cohort ... subject
    # to data". The delisted half is empty here (see dead_names below), so the damaged
    # half supplies it, by the same deterministic depth rule, and the substitution is
    # logged. Membership choice is design-touched and is never evidence.
    decliner_pool = snap[
        (snap["n_rows"] >= DECLINER_MIN_SESSIONS)
        & (snap["compute_eligible"])
        & (~snap["symbol"].isin(set(fixed)))
    ]
    used_ceased_pool = bool(dead_pool)
    if used_ceased_pool:
        decliner_pool = decliner_pool[decliner_pool["symbol"].isin(dead_pool)]
    dd_rows = []
    for r in decliner_pool.itertuples(index=False):
        try:
            dd_rows.append((r.symbol, _max_drawdown_final_window(
                r.symbol, r.price_plane_id, DECLINER_WINDOW)))
        except Exception as exc:  # noqa: BLE001
            log.warning("decliner scan: %s unreadable (%s)", r.symbol, exc)
    dd_rows = [(s, d) for s, d in dd_rows if np.isfinite(d)]
    dd_rows.sort(key=lambda t: t[1])
    if not dd_rows:
        raise SystemExit("no name qualifies for the secular-decliner rule")
    decliner = dd_rows[0][0]
    receipts["secular_decliner"] = {
        "pick": decliner,
        "rule": (
            "deepest close-to-close max drawdown over the final 1,260 sessions among "
            "names with >=1,000 sessions (damaged-cohort rule)"
        ),
        "cohort_used": "ceased-tape (delisted)" if used_ceased_pool else "damaged (live tape)",
        "logged_substitution": None if used_ceased_pool else (
            "registration §2 narrows this pick to the ceased-tape pool, which is EMPTY on "
            "the allowed planes (see dead_names). Masterplan §13's own wording sources the "
            "pick from the 'delisted/damaged cohort ... subject to data', so the damaged "
            "half supplies it under the identical depth rule. Substitution logged; nothing "
            "about the pick is evidence."
        ),
        "max_drawdown_final_1260": float(dd_rows[0][1]),
        "pool_size": len(dd_rows),
        "runners_up": [{"symbol": s, "max_drawdown": float(d)} for s, d in dd_rows[1:4]],
    }

    # --- dead names ---------------------------------------------------------
    if dead_pool:
        draw = part_mod.draw_dead_names(
            [s for s in dead_pool if s != decliner], need=DEAD_NEED,
            ledger_first=ledger_on_plane,
        )
        dead_members = draw["members"]
        dead_receipt: dict[str, Any] = {
            "status": "SATISFIED",
            "members": dead_members,
            "pool_size": draw["pool_size"],
            "seed_string": draw["seed_string"],
            "seed": draw["seed"],
            "draw_order_head": draw["draw_order"][:20],
            "terminated_reasons": {
                s: hyg_mod.dead_name_reason(s, REPO_ROOT) for s in dead_members
            },
        }
    else:
        dead_members = []
        dead_receipt = {
            "status": "BLOCKED — no dead name is obtainable from any allowed source",
            "members": [],
            "requirement": (
                "masterplan §13 / review finding 18: >=5 names that ceased trading, with "
                "terminated_reason recorded, so cohort-level statements can name who is missing"
            ),
            "sources_checked": {
                "config/delisted_symbols.yml": (
                    f"holds exactly {len(ledger_syms)} row(s) {ledger_syms}; "
                    f"present on an allowed plane: {ledger_on_plane or 'NONE'}"
                ),
                "allowed-plane tape-end proxy (>=126 sessions before asof, >=756 rows)": (
                    f"ZERO candidates. The largest tape-end lag anywhere in the "
                    f"{len(snap)}-name universe is {max_lag} session(s), and the names at "
                    f"that lag are plainly still trading — stale feeds or index-membership "
                    f"drops, not deaths. Treating them as dead names would be exactly the "
                    f"'delisted is not stale' error the exit ledger exists to prevent, and "
                    f"index-exit is not death (masterplan §9.5)."
                ),
                "data/edgar/dead_name_prices.parquet": (
                    "close-only third plane — PROHIBITED for fingerprints and catalogs by "
                    "the price-plane law (masterplan §9.7); not read"
                ),
            },
            "largest_tape_end_lags": lag_top,
            "consequence": (
                "W1 ships with NO dead names in the pilot. Every cohort-level statement in "
                "this wave is therefore survivor-only and must say so; the survivorship "
                "stratification substrate (sp1500 PIT membership) is unaffected. Supplying "
                "dead names needs an operator decision on a source: extending "
                "config/delisted_symbols.yml, or admitting a close-only plane for catalog "
                "work under a fresh registration. Neither is a builder's call."
            ),
            "not_done": (
                "no substitute was invented. A live name relabeled 'dead' would corrupt "
                "every survivorship read this cohort exists to enable."
            ),
        }
    receipts["dead_names"] = dead_receipt

    members = sorted(set(fixed) | {ipo, decliner} | set(dead_members))
    members = [m for m in members if m in present]
    receipts["final"] = {"n_members": len(members), "members": members}

    roles = dict(PILOT_ROLES)
    roles[ipo] = "stressor — recent IPO (rule-chosen at PR-1)"
    roles[decliner] = (
        "stressor — secular decliner (rule-chosen at PR-1, damaged cohort)"
        if not used_ceased_pool
        else "stressor — secular decliner (rule-chosen at PR-1); ceased tape"
    )
    for s in dead_members:
        roles[s] = roles.get(s, "") + ("; " if roles.get(s) else "") + "dead name (ceased tape)"

    payload = {"members": members, "roles": roles, "receipts": receipts}
    _scratch("pilot.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"[pilot] {len(members)} names: {members}", flush=True)
    print(f"[pilot] IPO={ipo} decliner={decliner} dead={dead_members or 'BLOCKED (none obtainable)'}",
          flush=True)
    if not dead_members:
        print(
            "::warning title=stock-identity-dead-names::W1 pilot ships with ZERO dead names — "
            f"the delisted ledger's {len(ledger_syms)} row(s) are absent from both allowed "
            f"planes and the largest tape-end lag in the universe is {max_lag} sessions "
            "(stale feeds, not deaths). Cohort statements in W1 are survivor-only.",
            flush=True,
        )
    return payload


def _read_pilot() -> dict[str, Any]:
    p = _scratch("pilot.json")
    if not p.exists():
        raise SystemExit("missing pilot checkpoint — run --stage pilot")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# stage: partition
# ---------------------------------------------------------------------------
def stage_partition(snap: pd.DataFrame, pilot: dict[str, Any]) -> dict[str, Any]:
    calendar = _read_calendar()
    asof = pd.Timestamp(snap["asof"].iloc[0])

    sector_map = part_mod.load_sector_map(REPO_ROOT)
    adv = pd.Series(snap["adv_252"].to_numpy(), index=snap["symbol"])
    vol = pd.Series(snap["realized_vol_252"].to_numpy(), index=snap["symbol"])
    strata = part_mod.build_strata(
        snap, adv_252=adv, realized_vol_252=vol, sector_map=sector_map
    )

    blind = part_mod.draw_blind_arm(strata, pilot=pilot["members"])
    calibration = part_mod.draw_calibration_partition(
        strata, pilot=pilot["members"], blind=blind["members"]
    )
    part_mod.check_disjoint(pilot["members"], blind["members"], calibration["members"])

    proc_hash, _ = part_mod.partition_procedure_sha256(REGISTRATION)
    pos = int(calendar.searchsorted(asof))
    cutoff = calendar[max(0, pos - CALIBRATION_LOOKBACK_SESSIONS)]

    strata_summary = {
        "definition": "cap_bucket x sector x vol_tercile",
        "cap_bucket_source": (
            "trailing-252d dollar-ADV tercile — a PROXY; no per-name market-cap store is "
            "tracked, and the partial screener cap figures would stratify by index "
            "membership, which is the survivorship contamination the arm exists to avoid"
        ),
        "sector_source": "data/breadth/ticker_sectors.parquet (gics_sp500/sp400/sp600 + sic_mapped)",
        "vol_source": "trailing-252d realized vol at asof, on-plane",
        "n_strata_total": int(strata["stratum"].nunique()),
        "n_unknown_sector": int((strata["sector"] == part_mod.UNKNOWN).sum()),
        "counts_by_stratum": {
            str(k): int(v) for k, v in strata["stratum"].value_counts().items()
        },
    }

    manifest = part_mod.build_manifest(
        asof=asof, snapshot=snap, pilot=pilot["members"],
        pilot_receipts=pilot["receipts"], blind=blind, calibration=calibration,
        procedure_hash=proc_hash, fingerprint_spec_hash=fp_mod.spec_hash(),
        strata_summary=strata_summary,
    )
    manifest["calibration_partition"]["calibration_history_cutoff"] = str(cutoff.date())
    manifest["universe"]["plane_by_symbol"] = dict(
        zip(snap["symbol"], snap["price_plane_id"])
    )
    manifest["hygiene_excluded_from_compute"] = {
        s: r for s, r in hyg_mod.COMPUTE_BLOCKLIST.items() if s in set(snap["symbol"])
    }

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    strata[["symbol", "price_plane_id", "sector", "cap_bucket", "vol_tercile", "stratum"]].to_parquet(
        _scratch("strata.parquet")
    )
    print(
        f"[partition] blind={len(blind['members'])} across {blind['n_strata_non_empty']} strata · "
        f"calibration={calibration['n_drawn']} of pool {calibration['pool_size']} · "
        f"cutoff={cutoff.date()}",
        flush=True,
    )
    print(
        f"[partition] universe_sha256={manifest['universe']['universe_sha256']}\n"
        f"[partition] blind_sha256={blind['blind_sha256']}\n"
        f"[partition] calibration_sha256={calibration['calibration_sha256']}\n"
        f"[partition] partition_procedure_sha256={proc_hash}\n"
        f"[partition] fingerprint_spec_hash={manifest['fingerprint_spec_hash']}",
        flush=True,
    )
    return manifest


def _read_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"missing {MANIFEST_PATH} — run --stage partition")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# stage: atlas (heavy)
# ---------------------------------------------------------------------------
_W: dict[str, Any] = {}


def _atlas_init(ec_d: dict, sc_d: dict, asof_s: str, factor_path: str) -> None:
    _W["ec"] = ep_mod.EpisodeConstants(**ec_d)
    _W["sc"] = state_mod.StateConstants(**sc_d)
    _W["asof"] = pd.Timestamp(asof_s)
    _W["factor"] = pd.read_parquet(factor_path)["UNIV_EW"] if factor_path else None


def _atlas_one(args: tuple[str, str, str | None]) -> dict[str, Any] | None:
    symbol, plane_id, terminated_reason = args
    try:
        df = load_symbol(symbol, plane_id, REPO_ROOT)
    except Exception as exc:  # noqa: BLE001
        log.warning("%s: unreadable (%s)", symbol, exc)
        return None
    df = df.loc[df.index <= _W["asof"]]
    if df.empty:
        return None

    states = state_mod.tag_states(df, plane_id, _W["sc"])
    catalog = ep_mod.build_catalog(
        df, symbol=symbol, plane_id=plane_id, const=_W["ec"], states=states["state"],
        terminated_reason=terminated_reason,
    )
    f3 = ep_mod.catalog_f3_stats(catalog)
    raw = fp_mod.compute_raw(
        df, plane_id=plane_id, asof=_W["asof"], factor_returns=_W["factor"], catalog_stats=f3,
    )
    raw["symbol"] = symbol
    return {
        "symbol": symbol,
        "raw": raw,
        "catalog": catalog,
        "state_counts": states["state"].value_counts().to_dict(),
        "gap_basis": str(states["gap_basis"].iloc[0]) if len(states) else "n/a",
    }


def stage_factor(snap: pd.DataFrame, workers: int) -> Path:
    """UNIV_EW — computed once over the evaluated universe, cached to scratch."""
    out = _scratch("univ_ew.parquet")
    if out.exists():
        print(f"[factor] reusing {out}", flush=True)
        return out
    rets: dict[str, pd.Series] = {}
    for r in snap.itertuples(index=False):
        if not r.compute_eligible:
            continue
        try:
            df = load_symbol(r.symbol, r.price_plane_id, REPO_ROOT)
        except Exception:  # noqa: BLE001
            continue
        c = df["close"].astype(float)
        rets[r.symbol] = np.log(c / c.shift(1))
    fac = fp_mod.universe_equal_weight_factor(rets)
    fac.to_frame().to_parquet(out)
    print(f"[factor] UNIV_EW over {len(rets)} names, {len(fac)} sessions -> {out}", flush=True)
    return out


def stage_atlas(snap: pd.DataFrame, workers: int, chunk: int) -> None:
    ec, sc, _ = _load_constants()
    manifest = _read_manifest()
    asof = pd.Timestamp(manifest["asof"])
    factor_path = str(stage_factor(snap, workers))

    todo = snap[snap["compute_eligible"]].copy()
    tasks = [
        (r.symbol, r.price_plane_id, r.terminated_reason if r.tape_ended else None)
        for r in todo.itertuples(index=False)
    ]
    chunks = [tasks[i : i + chunk] for i in range(0, len(tasks), chunk)]
    print(f"[atlas] {len(tasks)} names in {len(chunks)} chunk(s) of {chunk}", flush=True)

    for ci, ch in enumerate(chunks):
        fp_out = _scratch(f"fp_chunk_{ci:04d}.parquet")
        cat_out = _scratch(f"cat_chunk_{ci:04d}.parquet")
        meta_out = _scratch(f"meta_chunk_{ci:04d}.json")
        if fp_out.exists() and cat_out.exists() and meta_out.exists():
            continue
        with mp.Pool(
            processes=max(1, workers), initializer=_atlas_init,
            initargs=(ec.as_dict(), sc.as_dict(), str(asof), factor_path),
        ) as pool:
            got = [r for r in pool.imap_unordered(_atlas_one, ch, chunksize=4) if r]
        pd.DataFrame([g["raw"] for g in got]).to_parquet(fp_out)
        cats = [g["catalog"] for g in got if g["catalog"] is not None and not g["catalog"].empty]
        (pd.concat(cats, ignore_index=True) if cats else pd.DataFrame()).to_parquet(cat_out)
        meta_out.write_text(
            json.dumps(
                {g["symbol"]: {"state_counts": g["state_counts"], "gap_basis": g["gap_basis"]}
                 for g in got}, default=str
            ),
            encoding="utf-8",
        )
        print(f"[atlas] chunk {ci + 1}/{len(chunks)} · {len(got)} names", flush=True)
    print("[atlas] complete", flush=True)


def _collect_chunks(prefix: str) -> pd.DataFrame:
    files = sorted(SCRATCH.glob(f"{prefix}_chunk_*.parquet"))
    if not files:
        raise SystemExit(f"no {prefix} chunks in {SCRATCH} — run --stage atlas")
    frames = [pd.read_parquet(f) for f in files]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# stage: artifacts
# ---------------------------------------------------------------------------
def stage_artifacts(snap: pd.DataFrame) -> None:
    manifest = _read_manifest()
    _, _, constants = _load_constants()
    pilot = list(manifest["pilot"]["members"])
    blind = set(manifest["blind_arm"]["members"])

    raw_all = _collect_chunks("fp").set_index("symbol")
    numeric = [c for c in raw_all.columns if c in set(fp_mod.METRIC_NAMES) | set(fp_mod.DIAGNOSTIC_NUMERIC)]
    pct_all = fp_mod.cross_sectional_percentiles(raw_all[numeric], numeric)
    unstable_all = fp_mod.unstable_flags(pct_all)
    print(
        f"[artifacts] cross-section over {len(raw_all)} names "
        f"(blind included ANONYMOUSLY in denominators only: {len(blind & set(raw_all.index))})",
        flush=True,
    )

    # ---- pilot fingerprints ------------------------------------------------
    rows: list[dict[str, Any]] = []
    for sym in pilot:
        if sym not in raw_all.index:
            continue
        r = raw_all.loc[sym]
        row: dict[str, Any] = {
            "symbol": sym,
            "asof": manifest["asof"],
            "epoch_key": "epoch_0",
            "epoch_detector": "none/provisional",
            "price_plane_id": r.get("d_price_plane_id"),
            "n_sessions": int(r.get("_n_sessions", 0)),
            "fingerprint_spec_hash": manifest["fingerprint_spec_hash"],
        }
        for f in fp_mod.METRIC_NAMES + fp_mod.DIAGNOSTIC_NAMES:
            row[f] = r.get(f)
            if f in numeric:
                row[f"{f}__pct"] = float(pct_all.loc[sym, f]) if sym in pct_all.index else None
                row[f"{f}__covered"] = bool(pd.notna(r.get(f)))
                row[f"{f}__unstable"] = bool(unstable_all.loc[sym, f]) if sym in unstable_all.index else False
        for k, v in authority_block().items():
            row[f"authority_{k}"] = v
        rows.append(row)
    fp_dir = DATA / "fingerprints"
    fp_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(fp_dir / "pilot_fingerprint_v0.parquet")

    spec_obj = fp_mod.spec()
    spec_obj["fingerprint_spec_hash"] = fp_mod.spec_hash(spec_obj)
    spec_obj["authority"] = authority_block()
    (fp_dir / "fingerprint_spec.json").write_text(
        json.dumps(spec_obj, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[artifacts] pilot fingerprints -> {fp_dir}", flush=True)

    # ---- pilot episodes ----------------------------------------------------
    cat_all = _collect_chunks("cat")
    ep_dir = DATA / "episodes"
    (ep_dir / "pilot").mkdir(parents=True, exist_ok=True)
    pilot_cat = cat_all[cat_all["symbol"].isin(pilot)].copy()
    for k, v in authority_block().items():
        pilot_cat[f"authority_{k}"] = v
    pilot_cat.to_parquet(ep_dir / "pilot_episode_catalog_v0.parquet")
    for sym in pilot:
        sub = pilot_cat[pilot_cat["symbol"] == sym]
        payload = {
            "schema": "stock_identity.episode_catalog.v0",
            "symbol": sym,
            "asof": manifest["asof"],
            "constants_values": constants["values"],
            "atr_basis": ep_mod.ATR_BASIS,
            "labeling_note": (
                "episode resolution labels use future data by design — a research-time "
                "labeling instrument, never a live signal"
            ),
            "episodes": json.loads(sub.to_json(orient="records", date_format="iso")),
            "authority": authority_block(),
        }
        (ep_dir / "pilot" / f"{sym}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"[artifacts] pilot episodes ({len(pilot_cat)} rows) -> {ep_dir}", flush=True)

    # ---- pilot daily states -------------------------------------------------
    _, sc, _ = _load_constants()
    st_rows = []
    planes = manifest["universe"]["plane_by_symbol"]
    asof = pd.Timestamp(manifest["asof"])
    for sym in pilot:
        df = load_symbol(sym, planes[sym], REPO_ROOT)
        df = df.loc[df.index <= asof]
        st = state_mod.tag_states(df, planes[sym], sc)
        st = st.reset_index().rename(columns={"Date": "date"})
        st.insert(0, "symbol", sym)
        st.insert(1, "price_plane_id", planes[sym])
        st_rows.append(st)
    states = pd.concat(st_rows, ignore_index=True)
    for k, v in authority_block().items():
        states[f"authority_{k}"] = v
    st_dir = DATA / "state"
    st_dir.mkdir(parents=True, exist_ok=True)
    states.to_parquet(st_dir / "pilot_state_daily.parquet")
    print(f"[artifacts] pilot states ({len(states)} rows) -> {st_dir}", flush=True)

    # cache for dossiers
    raw_all.to_parquet(_scratch("raw_all.parquet"))
    pct_all.to_parquet(_scratch("pct_all.parquet"))
    unstable_all.to_parquet(_scratch("unstable_all.parquet"))


# ---------------------------------------------------------------------------
# stage: census
# ---------------------------------------------------------------------------
def stage_census(snap: pd.DataFrame) -> None:
    manifest = _read_manifest()
    _, _, constants = _load_constants()
    blind = set(manifest["blind_arm"]["members"])
    calendar = _read_calendar()

    cat_all = _collect_chunks("cat")
    cat = cat_all[~cat_all["symbol"].isin(blind)].copy()
    census, clusters, _ = census_mod.build_census(cat, calendar=calendar)

    raw_all = pd.read_parquet(_scratch("raw_all.parquet"))
    if "symbol" in raw_all.columns:
        raw_all = raw_all.set_index("symbol")
    raw_vis = raw_all[~raw_all.index.isin(blind)]
    coverage = pd.DataFrame(
        {f: raw_vis[f].notna() for f in fp_mod.METRIC_NAMES + fp_mod.DIAGNOSTIC_NUMERIC
         if f in raw_vis.columns},
        index=raw_vis.index,
    )
    availability = census_mod.feature_availability_by_plane(
        coverage, raw_vis["d_price_plane_id"],
        [f for f in fp_mod.METRIC_NAMES + fp_mod.DIAGNOSTIC_NUMERIC if f in coverage.columns],
    )

    for k, v in authority_block().items():
        census[f"authority_{k}"] = v
    out_dir = DATA / "census"
    out_dir.mkdir(parents=True, exist_ok=True)
    census.to_parquet(out_dir / "coverage_census_v0.parquet")

    n_ep = int(census["n_episodes"].sum()) if not census.empty else 0
    n_cens = int(census["n_censored"].sum()) if not census.empty else 0
    hygiene_excluded = sorted(manifest.get("hygiene_excluded_from_compute", {}).keys())
    header = {
        "asof": manifest["asof"],
        "universe_n": manifest["universe"]["n_names"],
        "blind_excluded_n": len(blind),
        "hygiene_excluded_n": len(hygiene_excluded),
        "hygiene_excluded_list": ", ".join(hygiene_excluded) or "none",
        "census_n": int(cat["symbol"].nunique()),
        "n_episodes": n_ep,
        "censored_share": f"{(n_cens / n_ep):.3f}" if n_ep else "n/a",
        "constants_hash": constants.get("partition_procedure_sha256", "n/a"),
        "fingerprint_spec_hash": manifest["fingerprint_spec_hash"],
    }
    md = census_mod.render_markdown(census, clusters, availability, header=header)
    (out_dir / "coverage_census_v0.md").write_text(md, encoding="utf-8")
    print(
        f"[census] {len(census)} cells · {n_ep} episodes · {len(clusters)} calendar clusters "
        f"· blind excluded={len(blind)} -> {out_dir}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# stage: dossiers
# ---------------------------------------------------------------------------
def stage_dossiers(snap: pd.DataFrame) -> None:
    manifest = _read_manifest()
    _, sc, constants = _load_constants()
    pilot_meta = _read_pilot()
    pilot = list(manifest["pilot"]["members"])
    planes = manifest["universe"]["plane_by_symbol"]
    asof = pd.Timestamp(manifest["asof"])

    raw_all = pd.read_parquet(_scratch("raw_all.parquet"))
    if "symbol" in raw_all.columns:
        raw_all = raw_all.set_index("symbol")
    pct_all = pd.read_parquet(_scratch("pct_all.parquet"))
    unstable_all = pd.read_parquet(_scratch("unstable_all.parquet"))
    strata = pd.read_parquet(_scratch("strata.parquet")).set_index("symbol")
    cat_all = _collect_chunks("cat")

    out_dir = RESEARCH / "dossiers"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for sym in pilot:
        srow = snap[snap["symbol"] == sym]
        if srow.empty:
            log.warning("%s absent from the snapshot — skipping dossier", sym)
            continue
        s = srow.iloc[0].to_dict()
        if sym in strata.index:
            s.update(strata.loc[sym, ["sector", "cap_bucket", "vol_tercile"]].to_dict())
        hy = hyg_mod.check_symbol(sym, repo_root=REPO_ROOT, first_date=s.get("first_date"))

        df = load_symbol(sym, planes[sym], REPO_ROOT)
        df = df.loc[df.index <= asof]
        st = state_mod.tag_states(df, planes[sym], sc)
        cat = cat_all[cat_all["symbol"] == sym].copy()
        shares = state_mod.state_share_by_year(st["state"])

        chart = dossier_mod.render_chart(
            symbol=sym, df=df, states=st["state"], catalog=cat, out_path=out_dir / f"{sym}.svg"
        )
        md = dossier_mod.render_markdown(
            symbol=sym, plane_id=planes[sym], snapshot_row=s, hygiene=hy,
            raw=raw_all.loc[sym].to_dict() if sym in raw_all.index else {},
            percentiles=pct_all.loc[sym].to_dict() if sym in pct_all.index else {},
            coverage={f: pd.notna(raw_all.loc[sym, f]) for f in raw_all.columns}
            if sym in raw_all.index else {},
            unstable=unstable_all.loc[sym].to_dict() if sym in unstable_all.index else {},
            catalog=cat, state_shares=shares,
            constants_meta={
                "gap_basis": str(st["gap_basis"].iloc[0]) if len(st) else "n/a",
                "constants_sha256": constants.get("calibration_sha256", "n/a"),
                "fingerprint_spec_hash": manifest["fingerprint_spec_hash"],
                "partition_procedure_sha256": manifest["partition_procedure_sha256"],
                "asof": manifest["asof"],
            },
            chart_rel=chart.name,
            pilot_role=pilot_meta["roles"].get(sym, ""),
        )
        dossier_mod.write_dossier(symbol=sym, out_dir=out_dir, markdown=md)
        written.append(sym)
    print(f"[dossiers] {len(written)} written -> {out_dir}", flush=True)


# ---------------------------------------------------------------------------
STAGES = ("snapshot", "pilot", "partition", "atlas", "artifacts", "census", "dossiers")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", default="all")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk", type=int, default=400)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    stages = STAGES if args.stage == "all" else tuple(
        s.strip() for s in args.stage.split(",") if s.strip()
    )
    bad = [s for s in stages if s not in STAGES]
    if bad:
        raise SystemExit(f"unknown stage(s) {bad}; choose from {STAGES}")

    snap: pd.DataFrame | None = None
    for st in stages:
        if st == "snapshot":
            snap = stage_snapshot(args.workers)
            continue
        if snap is None:
            snap = _read_snapshot()
        if st == "pilot":
            stage_pilot(snap)
        elif st == "partition":
            stage_partition(snap, _read_pilot())
        elif st == "atlas":
            stage_atlas(snap, args.workers, args.chunk)
        elif st == "artifacts":
            stage_artifacts(snap)
        elif st == "census":
            stage_census(snap)
        elif st == "dossiers":
            stage_dossiers(snap)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
