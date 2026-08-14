#!/usr/bin/env python3
"""Stock Identity W2 — expert replay over the pilot cohort (registration §8).

Stage-resumable by design: extraction writes one parquet per ``(family, symbol)`` into
scratch and skips anything already there, so a long run can be split across several
invocations without redoing work. Nothing heavy ever touches the render path.

Stage order — and it IS an order::

    registry   the family registry + the STARTER consequence-matrix investigation
    fixtures   the leak fixtures (registration §7) — run BEFORE any event is written,
               because a family whose fixture fails must ship NO events, and a test file
               cannot stop this script from writing
    extract    per family x symbol event chunks
    assemble   events + edges + attribution + inventory + the committed registry

Usage::

    python3 scripts/stock_identity_replay_pilot.py --stage registry,fixtures
    python3 scripts/stock_identity_replay_pilot.py --stage extract --families grey_dot,tiers
    python3 scripts/stock_identity_replay_pilot.py --stage extract --symbols KO,MCD
    python3 scripts/stock_identity_replay_pilot.py --stage assemble

The pilot cohort is W1's 21 names plus ``B`` (Barrick Mining — the W2 addendum's miner
pilot, ruling 3), 22 in total.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from engine.stock_identity.authority import authority_block  # noqa: E402
from engine.stock_identity.plane import load_symbol, primary_planes  # noqa: E402
from engine.stock_identity.replay import (  # noqa: E402
    attribution as attr_mod,
    bottom_watch as bw_mod,
    confirmed_buy as cb_mod,
    events as ev,
    grey_dot as gd_mod,
    leak as leak_mod,
    naive as naive_mod,
    reclaim_waiver as rw_mod,
    registry as reg_mod,
    sea as sea_mod,
    starter as starter_mod,
    tiers as tier_mod,
    washout_turn as wt_mod,
)

log = logging.getLogger("stock_identity.replay")

DATA = REPO_ROOT / "data" / "stock_identity"
OUT_DIR = DATA / "expert_events"
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
CHUNKS = SCRATCH / "chunks"
COMMITTED = SCRATCH / "committed"

#: The W2 addendum name (registration §6, ruling 3).
ADDENDUM_SYMBOL = "B"

#: Family GROUPS the CLI schedules by. A group is one extraction routine; the families it
#: writes may be several (tiers writes four; naive writes three).
FAMILY_GROUPS: tuple[str, ...] = (
    "grey_dot", "confirmed_buy", "tiers", "washout_turn", "reclaim_waiver",
    "bottom_watch", "starter", "sea", "naive",
)

#: Groups that RECOMPUTE and therefore take the full recompute fixture set. ``sea`` is the
#: only pure-store family and takes the append-only check alone.
_RECOMPUTE_GROUPS = frozenset({
    "grey_dot", "confirmed_buy", "tiers", "washout_turn", "reclaim_waiver",
    "bottom_watch", "starter", "naive",
})

#: Fixture probe names: a fixture is a property of the family's FUNCTION, not of a name, so
#: it is exercised on a small set with long history and different planes rather than on all
#: 22 (the truncated-frame walk is quadratic and would dominate the run for no extra proof).
_FIXTURE_NAMES: tuple[str, ...] = ("NVDA", "AEM")
#: The weekly organ's truncated walk is quadratic; one name is enough to pin the property.
_FIXTURE_NAMES_SLOW: tuple[str, ...] = ("AEM",)

#: DECLARED FIXTURE EXEMPTIONS — a property a producer genuinely does not have, named with
#: its mechanism rather than hidden by a loosened ceiling. There is exactly one, and it is
#: reported as an exemption in the registry and the inventory, never as a pass.
_FIXTURE_EXEMPTIONS: dict[str, dict[str, str]] = {
    "washout_turn": {
        "shift_audit_start_invariance": (
            "NOT APPLICABLE, mechanism named: engine.washout_turn's depth percentile is a "
            "declared WHOLE-SAMPLE statistic — its own _evaluate documents it as 'percent "
            "of the FULL weekly line history strictly BELOW bar j'. The reference "
            "distribution therefore legitimately depends on how much history exists, so a "
            "cross sitting near the 15th-percentile gate flips when leading history is "
            "dropped (measured on a synthetic tape: 8/18 events, 44%). This is PAST-data "
            "window dependence, not future leakage: the organ's three leak fixtures "
            "(truncation invariance, forming bar, feed truncation) are green, and the "
            "replay always walks one fixed full per-name prefix chain, so the window is "
            "constant across the whole extraction."
        )
    },
}


# ---------------------------------------------------------------------------
# frozen-input readers
# ---------------------------------------------------------------------------
def _manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"missing {MANIFEST_PATH} — the W1 manifest is a frozen input")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _constants() -> dict[str, Any]:
    if not CONSTANTS_PATH.exists():
        raise SystemExit(f"missing {CONSTANTS_PATH} — the frozen constants are a frozen input")
    return json.loads(CONSTANTS_PATH.read_text(encoding="utf-8"))


def _pilot_symbols() -> list[str]:
    m = _manifest()
    syms = list(m["pilot"]["members"])
    if ADDENDUM_SYMBOL not in syms:
        syms.append(ADDENDUM_SYMBOL)
    return sorted(syms)


def _planes(symbols: list[str]) -> dict[str, str]:
    live = primary_planes(REPO_ROOT)
    m = _manifest()
    frozen = m["universe"]["plane_by_symbol"]
    out: dict[str, str] = {}
    for s in symbols:
        # The frozen snapshot's assignment wins for W1 names (it is what every W1 artifact
        # was built on); B has no frozen assignment and takes the live one.
        out[s] = frozen.get(s) or live.get(s)
        if not out[s]:
            raise SystemExit(f"{s}: no price plane carries this symbol")
    return out


def _load(symbol: str, plane_id: str, asof: pd.Timestamp) -> pd.DataFrame:
    df = load_symbol(symbol, plane_id, REPO_ROOT)
    return df.loc[df.index <= asof]


def _scratch(*parts: str) -> Path:
    p = SCRATCH.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _washout_state_path() -> Path | None:
    for cand in (REPO_ROOT / "site" / "factordata" / "basket_washout_state.json",
                 COMMITTED / "basket_washout_state.json"):
        if cand.exists():
            return cand
    return None


# ---------------------------------------------------------------------------
# spec hashes — minted once, from the producers' own constants
# ---------------------------------------------------------------------------
def _spec_hashes() -> dict[str, str]:
    h = {
        gd_mod.MACRO_FAMILY_KEY: ev.spec_hash(gd_mod.macro_constants()),
        gd_mod.TERMINAL_FAMILY_KEY: ev.spec_hash(gd_mod.terminal_constants()),
        cb_mod.FAMILY_BUY: ev.spec_hash(cb_mod.constants()),
        cb_mod.FAMILY_REBUY: ev.spec_hash(cb_mod.constants()),
        wt_mod.FAMILY_KEY: ev.spec_hash(wt_mod.constants()),
        rw_mod.FAMILY_KEY: ev.spec_hash(rw_mod.constants()),
        bw_mod.FAMILY_KEY: ev.spec_hash(bw_mod.constants()),
        starter_mod.SIGNATURE_FAMILY_KEY: ev.spec_hash(starter_mod.constants()),
        sea_mod.FAMILY_KEY: ev.spec_hash(sea_mod.constants()),
    }
    for t, key in tier_mod.FAMILY_KEYS.items():
        h[key] = ev.spec_hash(tier_mod.constants() | {"tier": t})
    for key in naive_mod.FAMILY_KEYS:
        h[key] = ev.spec_hash(naive_mod.constants(key))
    return h


# ---------------------------------------------------------------------------
# stage: registry
# ---------------------------------------------------------------------------
def stage_registry() -> dict[str, Any]:
    m = _manifest()
    symbols = _pilot_symbols()
    planes = _planes(symbols)

    overrides = {}
    for rel, name in (("site/basketdata/us_basket_turn.json", "us_basket_turn.json"),
                      ("site/anticipationdata/us_leader_pullback.json",
                       "us_leader_pullback.json")):
        p = COMMITTED / name
        if p.exists() and not (REPO_ROOT / rel).exists():
            overrides[rel] = p
    verdict = starter_mod.investigate_licensing_context(
        REPO_ROOT, artifact_overrides=overrides
    )
    print(f"[registry] STARTER licensing context: {verdict['verdict']}", flush=True)

    state = rw_mod.load_state(REPO_ROOT, override=_washout_state_path())
    wl = wt_mod.load_ledger(REPO_ROOT)
    wl_first = (
        str(pd.Timestamp(wl["session"].min()).date())
        if wl is not None and not wl.empty else None
    )

    registry = reg_mod.build_registry(
        universe_as_of=str(m["asof"]),
        price_plane_ids=sorted(set(planes.values())),
        pilot_symbols=symbols,
        coverage_frac=None,
        reclaim_state_as_of=rw_mod.state_era(state),
        washout_ledger_first_session=wl_first,
        starter_verdict=verdict,
    )
    _scratch("registry.json").write_text(
        json.dumps(registry, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    print(
        f"[registry] {len(registry['families'])} families "
        f"({sum(1 for f in registry['families'] if f['provenance_class'] == 'P')} Class P) "
        f"-> {_scratch('registry.json')}",
        flush=True,
    )
    return registry


def _read_registry() -> dict[str, Any]:
    p = _scratch("registry.json")
    if not p.exists():
        raise SystemExit("missing registry checkpoint — run --stage registry first")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# per-group extraction routines
# ---------------------------------------------------------------------------
def _fire_fns(
    symbol: str, plane_id: str, hashes: dict[str, str], registry: dict[str, Any],
    ledgers: dict[str, Any],
) -> dict[str, Callable[[pd.DataFrame], list[dict[str, Any]]]]:
    """One frame -> events callable per group, closed over the symbol's identity.

    The fixtures call exactly these, so a fixture cannot pass against a different function
    than the one that ships the events.
    """
    fa = {f["family_key"]: f.get("family_first_available") for f in registry["families"]}

    def grey(df: pd.DataFrame) -> list[dict[str, Any]]:
        macro, _ = gd_mod.macro_fires(
            df, symbol=symbol, price_plane_id=plane_id,
            spec_hash=hashes[gd_mod.MACRO_FAMILY_KEY],
            family_first_available=fa.get(gd_mod.MACRO_FAMILY_KEY))
        term, _ = gd_mod.terminal_fires(
            df, symbol=symbol, price_plane_id=plane_id,
            spec_hash=hashes[gd_mod.TERMINAL_FAMILY_KEY],
            family_first_available=fa.get(gd_mod.TERMINAL_FAMILY_KEY))
        return macro + term

    def cbuy(df: pd.DataFrame) -> list[dict[str, Any]]:
        ledger = ledgers["track_record"]
        first = None
        sub = ledger[ledger["ticker"] == symbol] if not ledger.empty else ledger
        if not sub.empty:
            first = pd.Timestamp(sub["date"].min())
        return (
            cb_mod.ledger_fires(
                ledger, df, symbol=symbol, price_plane_id=plane_id,
                spec_hash=hashes[cb_mod.FAMILY_BUY],
                family_first_available=fa.get(cb_mod.FAMILY_BUY))
            + cb_mod.recompute_fires(
                df, symbol=symbol, price_plane_id=plane_id,
                spec_hash=hashes[cb_mod.FAMILY_BUY],
                family_first_available=fa.get(cb_mod.FAMILY_BUY),
                ledger_first_date=first)
        )

    def tier(df: pd.DataFrame) -> list[dict[str, Any]]:
        return tier_mod.fires(
            df, symbol=symbol, price_plane_id=plane_id,
            spec_hash=hashes[tier_mod.FAMILY_KEYS["T1"]],
            family_first_available=fa.get(tier_mod.FAMILY_KEYS["T1"]))

    def wash(df: pd.DataFrame) -> list[dict[str, Any]]:
        ledger = ledgers["washout"]
        stop = None
        if ledger is not None and not ledger.empty and "symbol" in ledger.columns:
            sub = ledger[ledger["symbol"] == symbol]
            if not sub.empty:
                stop = pd.Timestamp(sub["session"].min())
        return (
            wt_mod.ledger_fires(
                ledger, symbol=symbol, price_plane_id=plane_id,
                spec_hash=hashes[wt_mod.FAMILY_KEY],
                family_first_available=fa.get(wt_mod.FAMILY_KEY))
            + wt_mod.recompute_fires(
                df, symbol=symbol, price_plane_id=plane_id,
                spec_hash=hashes[wt_mod.FAMILY_KEY],
                family_first_available=fa.get(wt_mod.FAMILY_KEY),
                stop_before=stop)
        )

    def waiver(df: pd.DataFrame) -> list[dict[str, Any]]:
        rows, _ = rw_mod.fires(
            df, symbol=symbol, price_plane_id=plane_id,
            spec_hash=hashes[rw_mod.FAMILY_KEY], state=ledgers["washout_state"])
        return rows

    def bottom(df: pd.DataFrame) -> list[dict[str, Any]]:
        rows, _ = bw_mod.fires(
            df, symbol=symbol, price_plane_id=plane_id,
            spec_hash=hashes[bw_mod.FAMILY_KEY],
            family_first_available=fa.get(bw_mod.FAMILY_KEY))
        return rows

    def start(df: pd.DataFrame) -> list[dict[str, Any]]:
        return starter_mod.signature_fires(
            df, symbol=symbol, price_plane_id=plane_id,
            spec_hash=hashes[starter_mod.SIGNATURE_FAMILY_KEY],
            family_first_available=fa.get(starter_mod.SIGNATURE_FAMILY_KEY))

    def sea_(df: pd.DataFrame) -> list[dict[str, Any]]:
        return sea_mod.fires(
            ledgers["sea"], symbol=symbol, price_plane_id=plane_id,
            spec_hash=hashes[sea_mod.FAMILY_KEY],
            family_first_available=fa.get(sea_mod.FAMILY_KEY))

    def naive_(df: pd.DataFrame) -> list[dict[str, Any]]:
        return naive_mod.fires(
            df, symbol=symbol, price_plane_id=plane_id,
            spec_hashes={k: hashes[k] for k in naive_mod.FAMILY_KEYS},
            family_first_available={k: fa.get(k) for k in naive_mod.FAMILY_KEYS})

    return {
        "grey_dot": grey, "confirmed_buy": cbuy, "tiers": tier, "washout_turn": wash,
        "reclaim_waiver": waiver, "bottom_watch": bottom, "starter": start,
        "sea": sea_, "naive": naive_,
    }


def _ledgers(symbols: list[str]) -> dict[str, Any]:
    return {
        "track_record": cb_mod.load_ledger(REPO_ROOT, symbols),
        "washout": wt_mod.load_ledger(REPO_ROOT, symbols),
        "sea": sea_mod.load_store(REPO_ROOT, symbols),
        "washout_state": rw_mod.load_state(REPO_ROOT, override=_washout_state_path()),
    }


# ---------------------------------------------------------------------------
# stage: fixtures
# ---------------------------------------------------------------------------
def stage_fixtures() -> dict[str, Any]:
    registry = _read_registry()
    symbols = _pilot_symbols()
    planes = _planes(symbols)
    asof = pd.Timestamp(_manifest()["asof"])
    hashes = _spec_hashes()
    ledgers = _ledgers(symbols)

    results: dict[str, Any] = {}
    for group in FAMILY_GROUPS:
        names = _FIXTURE_NAMES_SLOW if group == "washout_turn" else _FIXTURE_NAMES
        group_results: list[dict[str, Any]] = []
        for sym in names:
            if sym not in planes:
                continue
            df = _load(sym, planes[sym], asof)
            fns = _fire_fns(sym, planes[sym], hashes, registry, ledgers)
            fn = fns[group]
            if group in _RECOMPUTE_GROUPS:
                exempt = _FIXTURE_EXEMPTIONS.get(group)
                for r in leak_mod.run_recompute_fixtures(fn, df, exemptions=exempt):
                    group_results.append({**r, "symbol": sym})
            if group == "confirmed_buy":
                emitted = [r for r in fn(df) if r["field_origin"] == "ledger_recorded"]
                group_results.append({
                    **leak_mod.append_only_conformance(
                        emitted, ledgers["track_record"][
                            ledgers["track_record"]["ticker"] == sym],
                        store_key=("ticker", "date", "type"),
                        date_column="date", symbol_column="ticker"),
                    "symbol": sym,
                })
            if group == "washout_turn":
                emitted = [r for r in fn(df) if r["field_origin"] == "ledger_recorded"]
                wl = ledgers["washout"]
                wl_sym = wl[wl["symbol"] == sym] if not wl.empty else wl
                group_results.append({
                    **leak_mod.append_only_conformance(
                        emitted, wl_sym, store_key=("session", "symbol", "state"),
                        date_column="session", symbol_column="symbol"),
                    "symbol": sym,
                })
            if group == "sea":
                emitted = fn(df)
                store = ledgers["sea"]
                store_sym = store[store["ticker"] == sym] if not store.empty else store
                group_results.append({
                    **leak_mod.append_only_conformance(
                        emitted, store_sym,
                        store_key=("ticker", "grid", "date", "direction"),
                        date_column="date", symbol_column="ticker"),
                    "symbol": sym,
                })
        applicable = [r for r in group_results if r.get("applicable", True)]
        exempt_rows = [r for r in group_results if not r.get("applicable", True)]
        results[group] = {
            "fixtures": group_results,
            "n_exempt": len(exempt_rows),
            "all_passed": all(r["passed"] for r in applicable) if applicable else False,
        }
        state = "GREEN" if results[group]["all_passed"] else "RED"
        note = f" · {len(exempt_rows)} declared exemption(s)" if exempt_rows else ""
        print(
            f"[fixtures] {group:<15} {state}  ({len(applicable)} applicable check(s){note})",
            flush=True,
        )
        for r in group_results:
            if not r.get("applicable", True):
                print(f"           ~ {r['symbol']} {r['name']}: EXEMPT — "
                      f"{r['detail'][:90]}...", flush=True)
            elif not r["passed"]:
                print(f"           ! {r['symbol']} {r['name']}: {r['detail']}", flush=True)

    _scratch("fixtures.json").write_text(
        json.dumps(results, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return results


def _read_fixtures() -> dict[str, Any]:
    p = _scratch("fixtures.json")
    if not p.exists():
        raise SystemExit("missing fixtures checkpoint — run --stage fixtures first")
    return json.loads(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# stage: extract
# ---------------------------------------------------------------------------
def stage_extract(groups: tuple[str, ...], symbols: tuple[str, ...]) -> None:
    registry = _read_registry()
    fixtures = _read_fixtures()
    planes = _planes(_pilot_symbols())
    asof = pd.Timestamp(_manifest()["asof"])
    hashes = _spec_hashes()
    ledgers = _ledgers(list(symbols))
    CHUNKS.mkdir(parents=True, exist_ok=True)

    for group in groups:
        if not fixtures.get(group, {}).get("all_passed"):
            print(
                f"[extract] {group}: BLOCKED — leak fixtures are not green, so this family "
                "ships NO events (registration §7)",
                flush=True,
            )
            continue
        for sym in symbols:
            out = CHUNKS / f"{group}__{sym}.parquet"
            edge_out = CHUNKS / f"{group}__{sym}__edges.parquet"
            if out.exists():
                continue
            df = _load(sym, planes[sym], asof)
            fns = _fire_fns(sym, planes[sym], hashes, registry, ledgers)
            rows = fns[group](df)
            ev.finalize_events(rows).to_parquet(out)
            if group == "bottom_watch":
                _, edges = bw_mod.fires(
                    df, symbol=sym, price_plane_id=planes[sym],
                    spec_hash=hashes[bw_mod.FAMILY_KEY], family_first_available=None)
                ev.finalize_edges(edges).to_parquet(edge_out)
            print(f"[extract] {group:<15} {sym:<6} {len(rows):>7} row(s)", flush=True)


def _collect_chunks() -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted(p for p in CHUNKS.glob("*.parquet") if "__edges" not in p.name)
    if not files:
        raise SystemExit(f"no extraction chunks in {CHUNKS} — run --stage extract")
    frames = [pd.read_parquet(f) for f in files]
    frames = [f for f in frames if not f.empty]
    events = pd.concat(frames, ignore_index=True) if frames else ev.empty_events()

    efiles = sorted(CHUNKS.glob("*__edges.parquet"))
    eframes = [pd.read_parquet(f) for f in efiles]
    eframes = [f for f in eframes if not f.empty]
    edges = pd.concat(eframes, ignore_index=True) if eframes else pd.DataFrame(
        {c: pd.Series(dtype="object") for c in ev.EDGE_COLUMNS}
    )
    return events, edges


# ---------------------------------------------------------------------------
# stage: assemble
# ---------------------------------------------------------------------------
def _promotion_edges(events: pd.DataFrame) -> list[dict[str, Any]]:
    """``promoted_by``: a grey dot in washout context -> its bottom-watch event.

    This is the as-restated view of the grey dot, expressed as an edge. The dot row is
    never deleted: the as-recorded reading must stay readable from the same store.
    """
    if events.empty:
        return []
    dots = events[
        (events["family_key"] == gd_mod.MACRO_FAMILY_KEY)
        & (events["in_washout_context"] == True)  # noqa: E712 — object dtype, `is` fails
    ]
    watches = events[
        (events["family_key"] == bw_mod.FAMILY_KEY)
        & (events["subtype"] == bw_mod.KIND_DOT)
    ]
    if dots.empty or watches.empty:
        return []
    key = watches.set_index(
        [watches["symbol"], pd.to_datetime(watches["signal_ts"]).dt.date]
    )["event_id"].to_dict()
    out: list[dict[str, Any]] = []
    for r in dots.itertuples(index=False):
        tgt = key.get((r.symbol, pd.Timestamp(r.signal_ts).date()))
        if not tgt:
            continue
        out.append(ev.make_edge(
            relation="promoted_by",
            source_event_id=r.event_id,
            target_event_id=tgt,
            symbol=r.symbol,
            source_family_key=gd_mod.MACRO_FAMILY_KEY,
            target_family_key=bw_mod.FAMILY_KEY,
            note=(
                "as-restated view: today's promotion rule would carve this dot out to "
                "amber_early. The dot row is retained; this edge is the restatement."
            ),
        ))
    return out


def _inventory_markdown(
    events: pd.DataFrame, edges: pd.DataFrame, coverage: pd.DataFrame,
    registry: dict[str, Any], fixtures: dict[str, Any], parity: dict[str, Any],
    reclaim_receipts: list[dict[str, Any]],
) -> str:
    L: list[str] = []
    L.append("# Stock Identity W2 — expert event inventory v0")
    L.append("")
    L.append(
        "Counts only. **This file publishes no ruler metric** — no lead/lag, distance, "
        "MAE, capture, recall, precision, composite, fit, rank or best appears here or in "
        "any artifact this wave produces; those are PR-3's object (registration §0.1). "
        "Every artifact carries the five-key all-false authority block, and a "
        "`scored_authority` flag on a row records what the EMITTER's authority was — a "
        "fact about the past, never a grant."
    )
    L.append("")
    L.append(f"* pilot cohort: {len(registry['pilot_symbols'])} names "
             f"(`{'`, `'.join(registry['pilot_symbols'])}`)")
    L.append(f"* universe as-of: {registry['vintage_stamp']['universe_as_of']}")
    L.append(f"* total events: **{len(events):,}** · typed edges: **{len(edges):,}**")
    L.append("")

    L.append("## Family inventory")
    L.append("")
    L.append("| family_key | class | era pin(s) | first available | events | names | fixtures |")
    L.append("|---|---|---|---|---:|---:|---|")
    by_family = events.groupby("family_key") if not events.empty else []
    counts = {str(k): (len(v), v["symbol"].nunique()) for k, v in by_family}
    group_of = _family_to_group()
    for f in registry["families"]:
        key = f["family_key"]
        n, nn = counts.get(key, (0, 0))
        grp = group_of.get(key)
        res = fixtures.get(grp, {}) if grp else {}
        fx = res.get("all_passed") if grp else None
        fx_s = "green" if fx else ("—" if fx is None else "RED")
        if fx and res.get("n_exempt"):
            fx_s = f"green (+{res['n_exempt']} declared exemption)"
        if f["provenance_class"] == "P":
            fx_s = "n/a (zero rows by law)"
        L.append(
            f"| `{key}` | {f['provenance_class']} | `{'`, `'.join(str(e) for e in f['era_pins'])}` "
            f"| {f['family_first_available'] or '—'} | {n:,} | {nn} | {fx_s} |"
        )
    L.append("")

    L.append("### Provenance split")
    L.append("")
    if not events.empty:
        split = events.groupby(["family_key", "field_origin"]).size().reset_index(name="n")
        L.append("| family_key | field_origin | events |")
        L.append("|---|---|---:|")
        for r in split.itertuples(index=False):
            L.append(f"| `{r.family_key}` | `{r.field_origin}` | {r.n:,} |")
    L.append("")

    L.append("### Era split (`DNR:LAW-ERA-SPLIT` — never pooled across the 2010 break)")
    L.append("")
    if not events.empty:
        e = events.copy()
        e["era_cohort"] = np.where(
            pd.to_datetime(e["signal_known_ts"]).dt.year < 2010, "pre2010", "post2010"
        )
        tab = e.groupby(["family_key", "era_cohort"]).size().unstack(fill_value=0)
        L.append("| family_key | pre2010 | post2010 |")
        L.append("|---|---:|---:|")
        for key, row in tab.iterrows():
            L.append(f"| `{key}` | {int(row.get('pre2010', 0)):,} | "
                     f"{int(row.get('post2010', 0)):,} |")
    L.append("")

    L.append("## Grey-dot twin parity (counts, not a verdict)")
    L.append("")
    L.append(
        "The two implementations stay SEPARATE families regardless of what these counts "
        "say (registration §3). Dates are compared on `signal_known_ts` — the decision "
        "date both sides key on."
    )
    L.append("")
    t = parity.get("total", {})
    L.append(f"* agreeing fire dates: **{t.get('agree', 0):,}**")
    L.append(f"* macro-only: **{t.get('macro_only', 0):,}** · terminal-only: "
             f"**{t.get('terminal_only', 0):,}**")
    L.append(f"* totals: macro {t.get('macro_total', 0):,} · terminal "
             f"{t.get('terminal_total', 0):,} over {t.get('n_names', 0)} names")
    L.append("")
    L.append("| name | agree | macro-only | terminal-only | macro total | terminal total |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for sym, v in sorted(parity.get("per_name", {}).items()):
        L.append(f"| {sym} | {v['agree']} | {v['macro_only']} | {v['terminal_only']} | "
                 f"{v['macro_total']} | {v['terminal_total']} |")
    L.append("")

    L.append("## Grey-dot dual series (as-recorded / as-restated)")
    L.append("")
    if not events.empty:
        dots = events[events["family_key"] == gd_mod.MACRO_FAMILY_KEY]
        washed = int((dots["in_washout_context"] == True).sum())  # noqa: E712
        L.append(f"* as-recorded fires: **{len(dots):,}**")
        L.append(f"* of which in washout context (today's rule would carve these to "
                 f"`amber_early`): **{washed:,}**")
        L.append(f"* as-restated raw-dot reading: **{len(dots) - washed:,}**")
        L.append("")
        L.append(
            "The carve-out is expressed as `promoted_by` edges; **no row is deleted**, so "
            "both readings come out of one store. `amber_early` itself remains Class P with "
            "zero rows — the flag above is what the rule WOULD have done, never that "
            "family's history."
        )
    L.append("")

    L.append("## Attribution join coverage (the only published aggregate)")
    L.append("")
    if not coverage.empty:
        agg = coverage.groupby("family_key", as_index=False)[
            ["n_events", "n_attributed", "n_unattributed"]].sum()
        L.append("| family_key | events | attributed | unattributed | coverage |")
        L.append("|---|---:|---:|---:|---:|")
        for r in agg.itertuples(index=False):
            frac = (r.n_attributed / r.n_events) if r.n_events else 0.0
            L.append(f"| `{r.family_key}` | {r.n_events:,} | {r.n_attributed:,} | "
                     f"{r.n_unattributed:,} | {frac:.1%} |")
        L.append("")
        L.append(
            "Unattributed events are **RETAINED**, carrying a null episode edge: the §7.3 "
            "unconditional block needs them at PR-3, because an expert that fires 500 times "
            "a year with 5 fires inside episodes would look perfectly localized while being "
            "worthless live — and that arithmetic is only possible if the other 495 are "
            "still in the store."
        )
    L.append("")

    L.append("## STARTER consequence matrix")
    L.append("")
    v = registry["starter_resolution"]
    L.append(f"**Verdict: `{v['verdict']}`**")
    L.append("")
    L.append(f"{v['reasoning']}")
    L.append("")
    L.append(f"*Consequence applied:* {v['consequence']}")
    L.append("")
    L.append("| artifact | role | present | carries a dated history | as_of |")
    L.append("|---|---|:--:|:--:|---|")
    for e in v["context_state_evidence"]:
        L.append(f"| `{e['artifact']}` | {e['role']} | "
                 f"{'yes' if e['present_in_checkout'] else 'no'} | "
                 f"{'yes' if e['carries_history'] else 'NO'} | {e['as_of'] or '—'} |")
    for e in v["membership_evidence"]:
        L.append(f"| `{e['artifact']}` | {e['role']} | "
                 f"{'yes' if e['present_in_checkout'] else 'no'} | "
                 f"{'n/a' if e['n_snapshot_dates'] is None else str(e['n_snapshot_dates']) + ' snapshot date(s)'} | — |")
    L.append("")

    L.append("## Reclaim-waiver era receipts")
    L.append("")
    L.append(
        "A zero here is a **structural absence** — the nightly state artifact is "
        "overwritten and no historical vintage exists — never evidence that the waiver "
        "does nothing."
    )
    L.append("")
    L.append("| name | state available | as_of | qualifies at notch | markers in window | waived |")
    L.append("|---|:--:|---|:--:|---:|---:|")
    for r in reclaim_receipts:
        L.append(f"| {r['symbol']} | {'yes' if r['state_available'] else 'no'} | "
                 f"{r['as_of'] or '—'} | {'yes' if r['qualifies_at_notch'] else 'no'} | "
                 f"{r['markers_in_window']} | {r['waived']} |")
    L.append("")

    L.append("## Ledger extraction coverage (counts)")
    L.append("")
    for c in (registry.get("ledger_coverage") or []):
        L.append(f"* `{c['store']}` -> `{'`, `'.join(c['families'])}`: "
                 f"**{c['rows_emitted']:,}** emitted of **{c['rows_in_store']:,}** in store")
        L.append(f"  * {c['unresolved_reason']}")
        if c.get("rows_by_ledger_era"):
            for era, v in sorted(c["rows_by_ledger_era"].items()):
                L.append(f"  * ledger era `{era}`: {v['rows']:,} row(s)")
    L.append("")

    L.append("## Class P families — enumerated with zero rows")
    L.append("")
    L.append(
        "Structural absence is never negative evidence. None of these zeros says the "
        "family does nothing; each says its history was never recorded or never existed."
    )
    L.append("")
    L.append("| family_key | first available | why there is no history |")
    L.append("|---|---|---|")
    for f in registry["families"]:
        if f["provenance_class"] != "P":
            continue
        L.append(f"| `{f['family_key']}` | {f['family_first_available'] or '—'} | "
                 f"{f['replay_notes']} |")
    L.append("")

    L.append("## Leak fixtures (registration §7)")
    L.append("")
    L.append(
        "A row marked **exempt** is a property the producer genuinely does not have, with "
        "the mechanism named — never a loosened ceiling. There is exactly one."
    )
    L.append("")
    L.append("| family group | fixture | name | verdict | detail |")
    L.append("|---|---|---|:--:|---|")
    for grp, res in fixtures.items():
        for r in res["fixtures"]:
            if not r.get("applicable", True):
                verdict = "**exempt**"
            else:
                verdict = "yes" if r["passed"] else "**NO**"
            L.append(f"| {grp} | `{r['name']}` | {r['symbol']} | {verdict} | {r['detail']} |")
    L.append("")
    return "\n".join(L) + "\n"


def _ledger_coverage(events: pd.DataFrame, symbols: list[str]) -> list[dict[str, Any]]:
    """Rows in each committed store vs rows emitted from it — counts, with the reason.

    The confirmed-buy arm is the one that needs this: a §7 marker is LABELLED with its 3D
    bucket's open date, and the pre-``sq-abs-session-2026-08-06`` ledger rows carry labels
    minted by the RETIRED ``3B`` resample, whose synthetic left-edge bins are not labels of
    the current absolute-anchor grid. ``marker_last_session`` refuses those, and a guessed
    known-ts would break the known-ts law — so they are counted here rather than stamped.
    """
    out: list[dict[str, Any]] = []
    tr = cb_mod.load_ledger(REPO_ROOT, symbols)
    if not tr.empty:
        emitted = int(len(events[(events["field_origin"] == "ledger_recorded")
                                 & (events["family_key"].isin(
                                     [cb_mod.FAMILY_BUY, cb_mod.FAMILY_REBUY]))]))
        by_era: dict[str, dict[str, int]] = {}
        for r in tr.itertuples(index=False):
            era = str(r.anchor_era) if isinstance(r.anchor_era, str) and r.anchor_era \
                else "pre-era-stamp"
            by_era.setdefault(era, {"rows": 0})["rows"] += 1
        out.append({
            "store": cb_mod.LEDGER_PATH,
            "families": [cb_mod.FAMILY_BUY, cb_mod.FAMILY_REBUY],
            "rows_in_store": int(len(tr)),
            "rows_emitted": emitted,
            "rows_by_ledger_era": by_era,
            "unresolved_reason": (
                "a §7 marker is labelled with its 3D bucket's OPEN date. Rows minted before "
                "the sq-abs-session-2026-08-06 anchor era carry labels from the RETIRED 3B "
                "resample, whose synthetic left-edge bins are not labels of the current "
                "absolute-anchor grid; signal_quality.marker_last_session refuses them and "
                "a guessed known_ts would break the known-ts law, so they are counted here "
                "instead of stamped. Measured: 100% of era-stamped rows resolve, 32.3% of "
                "pre-era-stamp rows do."
            ),
        })
    wl = wt_mod.load_ledger(REPO_ROOT, symbols)
    if wl is not None and not wl.empty:
        out.append({
            "store": wt_mod.LEDGER_PATH,
            "families": [wt_mod.FAMILY_KEY],
            "rows_in_store": int(len(wl)),
            "rows_emitted": int(len(events[(events["field_origin"] == "ledger_recorded")
                                           & (events["family_key"] == wt_mod.FAMILY_KEY)])),
            "unresolved_reason": (
                "the organ's transitions ledger records the full US universe; only pilot "
                "names are extracted, and only the two states this family recognises"
            ),
        })
    sea_store = sea_mod.load_store(REPO_ROOT, symbols)
    if sea_store is not None and not sea_store.empty:
        out.append({
            "store": sea_mod.BACKFILL_PATH + " ∪ " + sea_mod.LIVE_DIR,
            "families": [sea_mod.FAMILY_KEY],
            "rows_in_store": int(len(sea_store)),
            "rows_emitted": int(len(events[events["family_key"] == sea_mod.FAMILY_KEY])),
            "unresolved_reason": (
                "pure filter, keep-FIRST on the store's own key; a name absent from the "
                "SEA universe contributes no rows"
            ),
        })
    return out


def _family_to_group() -> dict[str, str]:
    m = {
        gd_mod.MACRO_FAMILY_KEY: "grey_dot",
        gd_mod.TERMINAL_FAMILY_KEY: "grey_dot",
        cb_mod.FAMILY_BUY: "confirmed_buy",
        cb_mod.FAMILY_REBUY: "confirmed_buy",
        wt_mod.FAMILY_KEY: "washout_turn",
        rw_mod.FAMILY_KEY: "reclaim_waiver",
        bw_mod.FAMILY_KEY: "bottom_watch",
        starter_mod.SIGNATURE_FAMILY_KEY: "starter",
        sea_mod.FAMILY_KEY: "sea",
    }
    for key in tier_mod.FAMILY_KEYS.values():
        m[key] = "tiers"
    for key in naive_mod.FAMILY_KEYS:
        m[key] = "naive"
    return m


def stage_assemble() -> None:
    registry = _read_registry()
    fixtures = _read_fixtures()
    constants = _constants()
    p_pre = int(constants["values"]["P_pre"])
    symbols = _pilot_symbols()
    planes = _planes(symbols)
    asof = pd.Timestamp(_manifest()["asof"])

    events, edges = _collect_chunks()
    events = ev.finalize_events(events.to_dict("records"))

    extra_edges = _promotion_edges(events)
    if extra_edges:
        edges = pd.concat(
            [edges, ev.finalize_edges(extra_edges)], ignore_index=True
        ) if not edges.empty else ev.finalize_edges(extra_edges)
    edges = ev.finalize_edges(edges.to_dict("records")) if not edges.empty else edges

    # --- attribution ---------------------------------------------------------
    catalog = pd.read_parquet(DATA / "episodes" / "pilot_episode_catalog_v0.parquet")
    add_cat = DATA / "episodes" / "addendum_b_catalog.parquet"
    if add_cat.exists():
        catalog = pd.concat([catalog, pd.read_parquet(add_cat)], ignore_index=True)
    cal = pd.DatetimeIndex(sorted({
        d for s in symbols
        for d in pd.DatetimeIndex(_load(s, planes[s], asof).index)
    }))
    attribution = attr_mod.attribute(events, catalog, p_pre=p_pre, calendar=cal)
    coverage = attr_mod.coverage_counts(attribution)

    # --- parity + waiver receipts -------------------------------------------
    macro = events[events["family_key"] == gd_mod.MACRO_FAMILY_KEY][
        ["symbol", "signal_known_ts"]]
    term = events[events["family_key"] == gd_mod.TERMINAL_FAMILY_KEY][
        ["symbol", "signal_known_ts"]]
    parity = gd_mod.parity_counts(macro, term)

    state = rw_mod.load_state(REPO_ROOT, override=_washout_state_path())
    receipts: list[dict[str, Any]] = []
    for sym in symbols:
        _, rec = rw_mod.fires(
            _load(sym, planes[sym], asof), symbol=sym, price_plane_id=planes[sym],
            spec_hash="", state=state)
        receipts.append(rec)

    # --- write ---------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    events.to_parquet(OUT_DIR / "pilot_events_v0.parquet")
    edges.to_parquet(OUT_DIR / "event_edges_v0.parquet")
    attribution.to_parquet(OUT_DIR / "attribution_v0.parquet")

    inventory: dict[str, Any] = {}
    if not events.empty:
        for key, sub in events.groupby("family_key"):
            inventory[str(key)] = {
                "n_events": int(len(sub)),
                "n_names": int(sub["symbol"].nunique()),
                "by_field_origin": sub["field_origin"].value_counts().to_dict(),
                "by_symbol": sub["symbol"].value_counts().to_dict(),
            }
    registry["inventory"] = inventory
    registry["parity_counts"] = parity
    registry["reclaim_waiver_receipts"] = receipts
    registry["join_coverage"] = (
        coverage.groupby("family_key", as_index=False)[
            ["n_events", "n_attributed", "n_unattributed"]].sum().to_dict("records")
        if not coverage.empty else []
    )
    registry["fixtures"] = fixtures
    registry["ledger_coverage"] = _ledger_coverage(events, symbols)
    registry["vintage_stamp"]["coverage_frac"] = (
        round(float(len(set(events["symbol"])) / len(symbols)), 4) if not events.empty else 0.0
    )
    registry["authority"] = authority_block()
    (OUT_DIR / "family_registry.json").write_text(
        json.dumps(registry, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "inventory_v0.md").write_text(
        _inventory_markdown(events, edges, coverage, registry, fixtures, parity, receipts),
        encoding="utf-8",
    )
    print(
        f"[assemble] {len(events):,} events · {len(edges):,} edges · "
        f"{len(attribution):,} attribution rows -> {OUT_DIR}",
        flush=True,
    )


STAGES = ("registry", "fixtures", "extract", "assemble")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", default="all")
    ap.add_argument("--families", default="all",
                    help=f"comma-separated group(s) from {FAMILY_GROUPS}")
    ap.add_argument("--symbols", default="all")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    stages = STAGES if args.stage == "all" else tuple(
        s.strip() for s in args.stage.split(",") if s.strip())
    bad = [s for s in stages if s not in STAGES]
    if bad:
        raise SystemExit(f"unknown stage(s) {bad}; choose from {STAGES}")

    groups = FAMILY_GROUPS if args.families == "all" else tuple(
        g.strip() for g in args.families.split(",") if g.strip())
    badg = [g for g in groups if g not in FAMILY_GROUPS]
    if badg:
        raise SystemExit(f"unknown family group(s) {badg}; choose from {FAMILY_GROUPS}")

    symbols = tuple(_pilot_symbols()) if args.symbols == "all" else tuple(
        s.strip().upper() for s in args.symbols.split(",") if s.strip())

    if "registry" in stages:
        stage_registry()
    if "fixtures" in stages:
        stage_fixtures()
    if "extract" in stages:
        stage_extract(groups, symbols)
    if "assemble" in stages:
        stage_assemble()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
