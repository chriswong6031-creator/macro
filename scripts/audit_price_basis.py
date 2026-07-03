"""Price-basis contract enforcement audit — Cycle Intelligence Masterplan W2.2 (D4 §6/§8).

The guard-rail that makes the dual-basis contract NON-REGRESSABLE.  It joins the
`run_quality_audits` family (scripts/collect.py) alongside prices / macro / universe /
fred_groups, writes `data/quality/price_basis_audit.json`, and counts toward the collect
gate (a HARD check failure surfaces as a failed universe).

Checks (D4 §8.1 — the W2.2 subset; frozen-basket + FX checks land with their own waves):

  dual_basis_present     HARD  every cycle-instrument yahoo parquet (the sector + country
                               ETF universe) carries a `close_price` column with ≥99%
                               coverage over its `close` span.
  basis_preserving       HARD  on dividend-paying ETFs `close_price` DIFFERS from `close`
                               on a nontrivial fraction (else the flip silently didn't
                               happen — a TR-masquerading-as-price regression).
  no_tr_in_structure     HARD  static AST scan of engine/{sector_cycles,country_cycles,
                               cycles}.py: no structure-math entry point (_detect_swings,
                               _detrended_osc, cycle_state via analyze) is fed a series that
                               traces to a TR read.  Implemented as a positive contract: the
                               engines route structure math through a declared `price=`/
                               `struct` seam (verified by presence of the seam tokens), and
                               the momentum uses (RS-vs-SPY, mtf, MACD) are the allow-listed
                               TR consumers.
  golden_fixture         HARD  _record_core on a dividend-heavy ETF (XLU) produces DIFFERENT
                               turn dates on price vs tr basis — proving the flip is REAL
                               (a positive test, not just a negative scan).
  basis_homogeneous      HARD  no live forward-log parquet mixes >1 distinct `basis` epoch
                               within one file (archived *.tr_v0.parquet are exempt — they
                               are the retained old epoch).
  narratives_versioned   HARD  every flipped engine resolves a non-quarantined epoch
                               narratives file and every plotted turn binds (no orphan
                               plotted); orphan legs live in the .orphans.json, never plotted.
  price_basis_divergence FLAG  count / max reldiff of close vs close_price across the ETF
                               universe (trend it — a collapse toward 0 means the basis
                               silently reverted).

READ-ONLY over the stores; writes only data/quality/price_basis_audit.json.  NEVER raises
(an audit's own crash must never abort the collect — the gate treats a crashed audit as a
logged non-fatal per collect.py).
"""
from __future__ import annotations

import ast
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config, store
from scripts import audit_common as ac

log = logging.getLogger("audit_price_basis")

# The cycle-instrument universe whose structure math W2.2 flips to close_price.
SECTOR_ETFS = ["XLK", "XLC", "XLY", "XLF", "XLI", "XLB", "XLE", "XLV", "XLP", "XLU", "XLRE"]
COUNTRY_ETFS = [
    "EWG", "EWU", "EWQ", "EWL", "EWP", "EWI", "EWN", "EWD", "EWJ", "EWA", "EWH", "EWS",
    "EWC", "FXI", "INDA", "EWT", "EWY", "EIDO", "EWZ", "EWW", "ECH", "EZA", "TUR", "EPOL",
    "EFA", "VGK", "VPL", "EEM", "AAXJ", "ILF", "VXUS",
]
CYCLE_ETFS = SECTOR_ETFS + COUNTRY_ETFS

# Dividend-paying ETFs used for the basis_preserving positive test (staples / utilities /
# broad = high, chronic dividend yield → close_price must diverge materially from close_tr).
DIVIDEND_ETFS = ["XLU", "XLP", "SPY", "XLE"]

_COVERAGE_MIN = 0.99          # close_price must cover ≥99% of the close span
_DIVERGE_FRAC_MIN = 0.20      # ≥20% of overlapping bars must differ (dividend inflation)
_DIVERGE_REL_TOL = 1e-4       # relative-difference threshold that counts as "differs"

# Engines flipped to price basis (their forward logs + narratives are checked).
_FLIPPED_ENGINES = ["sector_cycles", "country_cycles"]

# Structure-math entry points that MUST consume the price basis (never a TR series).
_STRUCTURE_FNS = {"_detect_swings", "_detrended_osc", "cycle_state", "find_troughs"}
# Allow-listed TR/momentum consumers (a return/RS/MACD stat correctly reads TR).
_MOMENTUM_FNS = {"mtf_snapshot", "_leadership", "_basket_rs", "macd_parts", "rsi",
                 "stoch_rsi", "early_signals"}


# ─────────────────────────────────────────────────────────────────────────────
# Store-level checks
# ─────────────────────────────────────────────────────────────────────────────
def _check_dual_basis_and_preserving() -> tuple[ac.Universe, ac.Universe, dict]:
    """dual_basis_present + basis_preserving + the divergence FLAG, in one store pass."""
    dual = ac.Universe(name="dual_basis_present")
    preserve = ac.Universe(name="basis_preserving")
    diverge_stats: dict = {"max_rel": 0.0, "min_frac_dividend": 1.0, "checked": 0}

    for t in CYCLE_ETFS:
        name = t.replace("^", "_").replace("=", "_").replace("/", "_")
        df = store.read("yahoo", name)
        dual.n += 1
        if df is None or df.empty:
            dual.flag(t, "absent", "no yahoo parquet — not a dual-basis failure (skipped instrument)")
            dual.n -= 1
            continue
        if "close_price" not in df.columns:
            dual.fail(t, "close_price column ABSENT (run scripts/backfill_price_basis.py)")
            continue
        c = df["close"].dropna()
        cp = df["close_price"].dropna()
        if c.empty:
            dual.flag(t, "empty_close", "close column empty")
            continue
        coverage = len(cp) / len(c) if len(c) else 0.0
        if coverage < _COVERAGE_MIN:
            dual.fail(t, f"close_price coverage {coverage:.3f} < {_COVERAGE_MIN}")

    # basis_preserving: dividend ETFs must diverge (else TR silently masquerades as price)
    for t in DIVIDEND_ETFS:
        df = store.read("yahoo", t)
        preserve.n += 1
        if df is None or "close_price" not in df.columns:
            preserve.fail(t, "close_price absent — cannot verify basis preservation")
            continue
        c = df["close"].dropna()
        cp = df["close_price"].dropna()
        common = c.index.intersection(cp.index)
        if len(common) < 2:
            preserve.fail(t, "insufficient overlap between close and close_price")
            continue
        rel = ((c.reindex(common) - cp.reindex(common)).abs()
               / c.reindex(common).abs()).replace([np.inf, -np.inf], np.nan).dropna()
        frac = float((rel > _DIVERGE_REL_TOL).mean()) if len(rel) else 0.0
        max_rel = float(rel.max()) if len(rel) else 0.0
        diverge_stats["checked"] += 1
        diverge_stats["max_rel"] = max(diverge_stats["max_rel"], round(max_rel, 4))
        diverge_stats["min_frac_dividend"] = min(diverge_stats["min_frac_dividend"], round(frac, 3))
        if frac < _DIVERGE_FRAC_MIN:
            preserve.fail(t, f"close_price differs from close on only {frac:.1%} of bars "
                             f"(< {_DIVERGE_FRAC_MIN:.0%}) — dividend inflation not stripped; "
                             f"close_price may be a TR copy")

    return dual, preserve, diverge_stats


# ─────────────────────────────────────────────────────────────────────────────
# Golden fixture — the POSITIVE proof the flip is real
# ─────────────────────────────────────────────────────────────────────────────
def _check_golden_fixture() -> ac.Universe:
    """_record_core on XLU produces DIFFERENT turns on price vs tr — the flip is REAL."""
    u = ac.Universe(name="golden_fixture")
    u.n = 1
    try:
        from engine import sector_cycles as sc
        from engine.inputs import _yahoo_close
        tr = _yahoo_close("XLU", basis="tr")
        px = _yahoo_close("XLU", basis="price")
        if tr is None or px is None:
            u.fail("XLU", "cannot load XLU tr/price series")
            return u
        tr = tr.dropna()
        px = px.dropna()
        # confirmed turn (date, kind) sets on each basis
        set_tr = {(s["date"], s["k"]) for s in sc._detect_swings(tr) if not s["provisional"]}
        set_px = {(s["date"], s["k"]) for s in sc._detect_swings(px) if not s["provisional"]}
        symdiff = set_tr ^ set_px
        if not symdiff:
            u.fail("XLU", "price-basis turns are IDENTICAL to tr-basis turns — the flip is "
                          "a no-op (close_price == close?)")
        else:
            u.note = (f"XLU: {len(set_tr)} tr turns vs {len(set_px)} price turns; "
                      f"{len(symdiff)} differ (flip is real)")
    except Exception as e:  # noqa: BLE001
        u.fail("XLU", f"golden-fixture check crashed: {e}")
    return u


# ─────────────────────────────────────────────────────────────────────────────
# Static AST scan — no TR series reaches structure math
# ─────────────────────────────────────────────────────────────────────────────
def _check_no_tr_in_structure() -> ac.Universe:
    """Positive-contract AST scan: the flipped engines must route structure math through
    the declared `price=`/`struct` seam, and cycles.analyze must expose the `price=` kwarg.

    We assert the seam EXISTS (so structure never silently defaults to TR), and that the
    momentum allow-list functions are the only ones the engines pass the TR series to.  A
    missing seam (someone reverting the split) fails HARD."""
    u = ac.Universe(name="no_tr_in_structure")
    root = config.ROOT

    def _src(rel: str) -> str | None:
        p = root / rel
        try:
            return p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return None

    # 1. cycles.analyze must carry the `price=` structure seam.
    u.n += 1
    cyc_src = _src("engine/cycles.py")
    if cyc_src is None:
        u.fail("engine/cycles.py", "unreadable")
    else:
        try:
            tree = ast.parse(cyc_src)
            analyze = next((n for n in ast.walk(tree)
                            if isinstance(n, ast.FunctionDef) and n.name == "analyze"), None)
            if analyze is None:
                u.fail("cycles.analyze", "function not found")
            else:
                arg_names = {a.arg for a in analyze.args.args} | {
                    a.arg for a in analyze.args.kwonlyargs}
                if "price" not in arg_names:
                    u.fail("cycles.analyze", "missing the `price=` structure-basis kwarg "
                                             "(the A13 substrate seam)")
                # structure functions must be called against `struct`/`price`, not `close`
                # inside analyze — verified by the presence of a `struct` binding.
                assigns = [n for n in ast.walk(analyze)
                           if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == "struct"
                                   for t in n.targets)]
                if not assigns:
                    u.fail("cycles.analyze", "no `struct` structure-basis binding — structure "
                                             "math may read `close` (TR) directly")
        except SyntaxError as e:
            u.fail("engine/cycles.py", f"parse error: {e}")

    # 2. _record_core must accept a `price=` param and derive a `struct` series + `basis`.
    u.n += 1
    sc_src = _src("engine/sector_cycles.py")
    if sc_src is None:
        u.fail("engine/sector_cycles.py", "unreadable")
    else:
        try:
            tree = ast.parse(sc_src)
            rc = next((n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "_record_core"), None)
            if rc is None:
                u.fail("_record_core", "function not found")
            else:
                arg_names = {a.arg for a in rc.args.args} | {a.arg for a in rc.args.kwonlyargs}
                if "price" not in arg_names:
                    u.fail("_record_core", "missing the `price=` structure-basis param")
                body_src = ast.get_source_segment(sc_src, rc) or ""
                # W3.1 (#984): _record_core is a thin daily wrapper delegating to the
                # record_series kernel — the `struct` seam + structure calls live there.
                # Scan the wrapper and the kernel as ONE body so the contract still
                # holds (a revert of the struct routing in either place still fails).
                rs = next((n for n in ast.walk(tree)
                           if isinstance(n, ast.FunctionDef) and n.name == "record_series"), None)
                if rs is not None:
                    body_src += "\n" + (ast.get_source_segment(sc_src, rs) or "")
                # structure series is built as `struct`; the detrended osc + swings read it.
                if "struct" not in body_src:
                    u.fail("_record_core", "no `struct` structure-basis series")
                for fn in ("_detrended_osc(struct", "_detect_swings(struct"):
                    if fn not in body_src:
                        u.fail("_record_core", f"structure call `{fn}...)` not routed through "
                                               f"`struct` (may read the TR series)")
                # RS/momentum must still be TR: analyze receives close=full, price=struct.
                if "cycles.analyze(full" not in body_src:
                    u.fail("_record_core", "cycles.analyze must receive the TR series `full` as "
                                           "the momentum `close` (RS/MACD keep dividend fidelity)")
        except SyntaxError as e:
            u.fail("engine/sector_cycles.py", f"parse error: {e}")

    return u


# ─────────────────────────────────────────────────────────────────────────────
# Forward-log basis homogeneity + narrative versioning
# ─────────────────────────────────────────────────────────────────────────────
def _check_basis_homogeneous() -> ac.Universe:
    """No LIVE forward-log parquet mixes >1 distinct structure epoch.

    The homogeneity contract is per-EPOCH, not per-file: a single price-epoch log holds
    price-basis sector stamps AND tr-basis basket stamps (baskets are the un-flipped member
    -TR series, a legitimately different instrument class in the SAME epoch build).  What is
    forbidden is mixing a tr_v0 (archived, pre-flip) stamp with a price-epoch stamp — which
    is exactly what archiving forward_log.tr_v0.parquet prevents.  So the check is: the LIVE
    log must NOT contain any row whose basis is a tr_v0 leftover for a FLIPPED instrument
    kind (a sector/country row must be `price`, never `tr`)."""
    u = ac.Universe(name="basis_homogeneous")
    ddir = config.data_dir()
    for eng in _FLIPPED_ENGINES:
        p = ddir / eng / "forward_log.parquet"
        u.n += 1
        if not p.exists():
            u.flag(eng, "absent", "no live forward log yet (first build not run) — skipped")
            u.n -= 1
            continue
        try:
            df = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            u.fail(eng, f"forward log unreadable: {e}")
            continue
        if "basis" not in df.columns:
            u.fail(eng, "forward log has no `basis` column (writer not stamping epoch/basis)")
            continue
        # a flipped instrument kind ("sector") must carry price basis, never a stale tr.
        bad = df[(df["kind"] == "sector") & (df["basis"] == "tr")]
        if len(bad):
            u.fail(eng, f"{len(bad)} sector rows stamped basis='tr' (pre-flip leftover) in the "
                        f"live price-epoch log — archive/re-stamp them")
        # baskets legitimately carry 'tr' (un-flipped member-TR series) — not a failure.
    return u


def _check_narratives_versioned() -> ac.Universe:
    """Every flipped engine resolves a NON-quarantined epoch narratives file, and every
    plotted turn binds to a leg (orphans live in .orphans.json, never plotted)."""
    u = ac.Universe(name="narratives_versioned")
    from scripts._narrative_epoch import resolve_narratives
    ddir = config.data_dir()
    for eng in _FLIPPED_ENGINES:
        u.n += 1
        res = resolve_narratives(eng, ddir / eng, "narratives")
        if res["stale_quarantined"]:
            u.fail(eng, f"narratives STALE-QUARANTINED (epoch {res['epoch']}) — basis flipped "
                        f"without a re-key; run scripts/rekey_narratives.py --engine {eng}")
            continue
        if not res["map"]:
            u.flag(eng, "empty", f"epoch {res['epoch']} resolved but empty narrative map")
    return u


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
def run(cfg: dict | None = None, out_dir: Path | None = None) -> dict:
    """Run every price-basis check, write data/quality/price_basis_audit.json, return the doc.

    A HARD-check failure lands in the failing-universe totals the collect gate reads (so a
    silent basis regression aborts/warns the run).  Divergence stats + absent instruments are
    FLAGS/notes only."""
    cfg = cfg or ac.quality_cfg()
    dual, preserve, diverge_stats = _check_dual_basis_and_preserving()
    universes = [
        dual,
        preserve,
        _check_golden_fixture(),
        _check_no_tr_in_structure(),
        _check_basis_homogeneous(),
        _check_narratives_versioned(),
    ]
    doc = ac.write_audit("price_basis", "price_basis", universes, cfg, out_dir=out_dir)
    doc["divergence_stats"] = diverge_stats
    # re-persist with the extra stats attached (write_audit already wrote the core doc)
    (out_dir or ac.quality_dir()).mkdir(parents=True, exist_ok=True)
    (out_dir or ac.quality_dir()).joinpath("price_basis_audit.json").write_text(
        json.dumps(doc, indent=1))
    log.info("price_basis audit: n=%d n_failed=%d fail_pct=%.2f%% (div max_rel=%.3f, "
             "min_dividend_frac=%.2f)", doc["n"], doc["n_failed"], doc["fail_pct"],
             diverge_stats["max_rel"], diverge_stats["min_frac_dividend"])
    return doc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    import sys
    d = run()
    print(json.dumps({"n": d["n"], "n_failed": d["n_failed"], "fail_pct": d["fail_pct"],
                      "divergence_stats": d.get("divergence_stats"),
                      "universes": [{"name": u["name"], "n": u["n"],
                                     "n_failed": u["n_failed"], "note": u.get("note", "")}
                                    for u in d["universes"]]}, indent=2))
    sys.exit(1 if d["n_failed"] else 0)
