"""PRICE-BASIS GUARD — a production grader may not difference an UNADJUSTED name leg
against an ADJUSTED benchmark leg.

THE DEFECT THIS PINS
====================
`data/{breadth,midcap_breadth,smallcap_breadth,russell_breadth}/_closes_cache.parquet`
are RAW closes: accrued forward and re-based only at an infrequent full rebuild. Every
benchmark the house grades against (SPY, the GICS sector ETFs) exists ONLY back-adjusted.
`excess = name_ret - bench_ret` across that pair books a name's own dividend as a loss.

It shipped three times before anyone named it, and the third time it was ALREADY KNOWN:
`engine/desk_grader.py` was hardened against this exact cache on 2026-07-04 and says so
in its notes. The knowledge did not propagate, because nothing made it propagate. That is
what this file is for — not to re-state the fact in a comment, but to fail a build.

WHY IT IS STRUCTURAL, NOT A STRING MATCH
=========================================
A grep for "breadth" would pass the moment someone renamed a constant. These tests parse
the modules with `ast` and ask what they actually reach, and they hold a frozen REGISTRY
of every production module that currently pairs the two families. A new pairing fails
(the census grew); repairing one also fails until the registry is updated (the census
shrank). Fail-closed in both directions is the point: a guard that only notices additions
lets a fix quietly un-record itself, and then the next author re-adds the pairing to a
module the registry no longer claims.

MUTATION-CHECKED. Re-point `scripts/grade_us_board.py` at a cache-first ladder (drop the
`rebase_to_adjusted` call from `main`, or the `engine.price_ladder` import) and
`test_owned_graders_resolve_through_the_shared_ladder` fails. Add an adjusted benchmark
read to a cache-only module and `test_no_new_module_pairs_the_two_bases` fails.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# --------------------------------------------------------------------------- #
# what "reaches a raw cache" and "reaches an adjusted store" mean, structurally
# --------------------------------------------------------------------------- #
CACHE_GROUP_NAMES = {"breadth", "midcap_breadth", "smallcap_breadth", "russell_breadth"}

#: any of these string fragments in a literal means the module names a raw close cache
_CACHE_MARKERS = ("_closes_cache",)

#: reaching the caches THROUGH a shared helper instead of by name.
#:
#: `merge_close_caches` is here because leaving it out made this guard HALF-BLIND, and the
#: blindness read as a repair. #4711 moved the tier-merging cache accessor out of
#: `engine.equity_factors._closes` into `lib/closes_panel.py`; every caller that migrated
#: kept reading the same raw `_closes_cache.parquet` files but stopped naming them, so the
#: AST saw no cache leg. `engine/manager_trades.py` silently left the census that way and
#: `test_the_registry_does_not_rot` then demanded its registry line be deleted — i.e. the
#: guard was asking to record a fix nobody made. A detector that only knows the accessor's
#: OLD name decays every time the accessor is refactored; both names are matched now.
_CACHE_FUNCS = {"_closes", "merge_close_caches"}
_CACHE_MODULES = {
    "engine.equity_factors", "equity_factors",   # _closes()
    "lib.closes_panel", "closes_panel",          # merge_close_caches() — #4711 onward
}

#: literals that name a back-adjusted per-name store
_ADJUSTED_MARKERS = ("data/yahoo", "baskets/ohlcv", "baskets/extras", "data/stocks")

#: `store.read("yahoo", ...)` / `store.read("stocks", ...)` are the same thing by API
_ADJUSTED_STORE_GROUPS = {"yahoo", "stocks"}

#: The shared, audited ladder. A module that resolves through this is COMPLIANT by
#: construction — it is the one place the adjusted-first order is expressed.
SHARED_LADDER = "engine.price_ladder"

#: The two production graders this PR owns. They MUST resolve through the shared ladder.
OWNED_GRADERS = (
    "scripts/grade_us_board.py",
    "scripts/prophet_postmortem.py",
)

#: INFRASTRUCTURE — these DEFINE the two families rather than consuming them, so naming
#: both is their job, not a defect.
_INFRASTRUCTURE = {
    "engine/price_ladder.py",        # the shared ladder itself
    "engine/equity_factors.py",      # _closes(): the cache accessor every consumer calls
}

#: FROZEN CENSUS — production modules that REACH both a raw breadth cache and an adjusted
#: store without going through the shared ladder.
#:
#: READ THE CLAIM PRECISELY. Membership proves reachability, which is what an AST can see;
#: it does NOT prove a live mismatch. Some entries are benign (the benchmark leg is the
#: same raw panel, or the cache is used for a membership SET rather than for prices).
#: Triage state is recorded per line, and where this PR did not verify the combining
#: expression by hand it says so instead of inventing a verdict. Repairing any of these is
#: out of this PR's scope — its fence is the two named graders, the shared helper and
#: these tests — and the list is the handoff.
#:
#: To ADD a module you must state why it is not being fixed now.
#: To REMOVE one, migrate it to `engine.price_ladder` and delete the line.
KNOWN_UNMIGRATED = {
    # ---- verified: a real diff/ratio of a raw name leg against an adjusted benchmark --
    "scripts/build_stock_library.py":         "VERIFIED: feeds ticker_alerts/velocity RS vs adjusted SPY",
    "scripts/build_factor_panel.py":          "VERIFIED: residual return vs adjusted factor streams",
    "scripts/backtest_special_situations.py": "VERIFIED: x{h} = fwd - spy_fwd, SPY read from data/yahoo",
    "scripts/backtest_event_priors.py":       "VERIFIED: CAR excess vs adjusted SPY",
    "engine/crowding.py":                     "VERIFIED: relative strength vs adjusted bench",
    "engine/group_flow.py":                   "VERIFIED: US branch rs = lvl / adjusted SPY",
    "engine/us_sector_rotation.py":           "VERIFIED: fast-RS = raw member closes / adjusted ETF closes",
    "engine/narrative_rotation.py":           "VERIFIED: market residuals vs adjusted SPY",
    "engine/baskets.py":                      "VERIFIED: vs-SPY relative return per horizon",
    "engine/manager_trades.py": (
        "VERIFIED: ClosePanel.get() serves data/yahoo first and falls back to the raw "
        "merged breadth panel, while the benchmark leg (self.spy) always resolves from "
        "adjusted yahoo — so excess() = stock - bench mixes bases for any name the "
        "breadth caches carry and yahoo does not. RESTORED 2026-08-07: this exact row "
        "was deleted by #4863 because #4711's accessor rename had made the DETECTOR "
        "blind (the module stopped naming _closes_cache when it moved to "
        "merge_close_caches), not because the module was repaired. #4874 restored the "
        "detector but not the row. Do not delete it again without reading excess()."),
    # ---- reads both stores, but performs NO name-vs-benchmark arithmetic ------------
    "engine/prophet_bridge.py": (
        "NO PAIRING: _load_price_history (#4684 P3) is a hand-rolled ADJUSTED-FIRST "
        "ladder — data/baskets/ohlcv -> data/stocks -> the four breadth close panels. "
        "Exactly ONE rung ever serves a ticker (the per-ticker parquets return before "
        "_panel_close_history is reached), and the module computes no benchmark-relative "
        "return anywhere: excess/vs_spy are absent, and its only 'spy' is risk_radar's "
        "spy_below_200dma BOOLEAN context gate, not a price leg. RESIDUAL, named rather "
        "than hidden: a rung-3-only name (the 19 of 23 previously unpriced plans this "
        "rung exists to price) has its swing-level geometry measured on UNADJUSTED "
        "history. NOT migrated to the shared ladder because that returns closes, not the "
        "OHLCV the geometry reads, and its rung set and cache-group ORDER both differ "
        "(midcap/smallcap are swapped) — migrating blind would silently move which "
        "source prices a live plan."),
    "engine/prophet_doors.py":                "BENIGN: disjoint uses — cache gives the universe/flags, ohlcv gives self-contained W8 coil features joined on the flag DATE (exact bar, never imputed); no expression differences the two",
    "engine/factor_exposure.py":              "VERIFIED: regresses raw stock closes on adjusted ETFs",
    "engine/residual_momentum.py":            "VERIFIED: orthogonalises raw closes against adjusted SPY",
    "engine/residual_alpha.py":               "VERIFIED: orthogonalises raw closes against adjusted SPY",
    "engine/factor_series.py":                "VERIFIED: long/short spreads referencing adjusted SPY",
    "engine/volume_signature.py":             "VERIFIED: joins the adjusted extras frame onto the raw panel",
    # ---- benign on inspection: same-basis benchmark, or the cache is not a price leg ---
    "engine/desk_grader.py":                  "BENIGN: yahoo-only by design; cache only in notes/warnings",
    "engine/trajectory.py":                   "BENIGN: explicitly refuses the cache fallback",
    "engine/quant_lab/specs.py":              "BENIGN: metadata dict of store paths; never reads a parquet",
    "engine/prophet_miss_audit.py":           "INHERITS: reads excess_spy from a ledger, does not compute it",
    "scripts/prophet_pit_replay.py": (
        "BENIGN: the PIT replay harness names BOTH families on purpose — they are its "
        "per-market overlay/fence SURFACE (truncate, append-only overlay, no-bar-after "
        "fence, byte assertions), never price legs in arithmetic. No expression "
        "differences the two; all board/grading math runs inside the vintage tree's own "
        "builders, which carry their own registry rows"
    ),
    "scripts/fetch_basket_extras.py":         "BENIGN: writes the adjusted store; reads caches to pick symbols",
    # NB: `engine/prophet_doors.py` used to appear HERE as well as above. A dict literal
    # keeps the LAST duplicate, so #4863's longer "NO PAIRING" triage was silently dead
    # from the moment #4874 added this one — two commits triaged the same module without
    # either noticing the other. The surviving text is unchanged; only the dead twin went.
    "scripts/measure_cycles_anchor_blast_radius.py": "BENIGN: the instrument that MEASURES cross-basis divergence — it holds the three loaders apart on as-of-aligned reads by design",
    "scripts/measure_coiled_mtf_anchor_blast_radius.py": "BENIGN: same instrument class as measure_cycles_anchor_blast_radius.py above — it reads deep stocks/, 2014-start baskets/ohlcv and the breadth caches at their NATIVE depth as SEPARATE, as-of-aligned universes and REPORTS the per-loader disagreement as its output. Holding the bases apart is the measurement, not a defect",
    "scripts/backfill_prophet_outage_20260811.py": (
        "NO PAIRING: force-majeure reconstruction harness. It truncates BOTH "
        "families (adjusted ticker stores + unadjusted breadth panels) to the "
        "same as-of so the 2026-08-11 board can be rebuilt from a vintage that "
        "never collected that session. It does not compute a name-vs-benchmark "
        "return, residual, or excess. The two bases are listed together because "
        "truncation must cover the whole price surface, not because a raw name "
        "leg is differenced against an adjusted bench."
    ),
    # ---- reaches both families; combining expression NOT hand-verified by this PR ------
    "engine/altdata_picks.py":                "not triaged",
    "engine/foresight_earliness.py":          "not triaged",
    "engine/foresight_enb.py":                "not triaged",
    "engine/foresight_leadlag.py":            "not triaged",
    "engine/hk_inputs.py":                    "not triaged (HK caches; RAW-ness unconfirmed)",
    "engine/ignition_radar.py":               "not triaged",
    "engine/momentum_display.py":             "not triaged",
    "engine/personality_gate_shadow.py":      "not triaged",
    "engine/qledger_falsifier.py":            "not triaged",
    "engine/risk_radar_market_catalysts.py":  "not triaged",
    "engine/stock_desk.py":                   "not triaged (single-stock from cache, SPY from yahoo)",
    "scripts/_cycle_fix_probe.py":            "not triaged (probe script)",
    "scripts/backtest_strategies.py":         "not triaged",
    "scripts/build_canada.py":                "not triaged (regional caches; RAW-ness unconfirmed)",
    "scripts/build_chart_data.py":            "not triaged",
    "scripts/build_china_library.py":         "not triaged (regional caches; RAW-ness unconfirmed)",
    "scripts/build_hk_library.py":            "not triaged (regional caches; RAW-ness unconfirmed)",
    "scripts/calibrate_bottom_radar.py":      "not triaged (#4698 named it P2)",
    "scripts/fund_crowding_phase0.py":        "not triaged (phase0 study)",
    "scripts/mature_bottom_sensors_shadow.py": "not triaged",
    "scripts/mature_shadow_book.py":          ("triaged 2026-08-26 (#6499): cache-only "
                                               "cross-section, no adjusted benchmark leg "
                                               "differenced; adjusted store.read union is "
                                               "dormant (0 columns added). Grades PRICE-only "
                                               "returns — artifact stamps price_basis"),
    "scripts/residual_alpha_phase0.py":       "not triaged (phase0 study)",
    "scripts/residual_momentum_phase0.py":    "not triaged (phase0 study)",
    "scripts/theme_discovery_phase0.py":      "not triaged (phase0 study)",
    "scripts/validate_composite.py":          "not triaged",
}


def _iter_production_modules():
    for base in ("scripts", "engine"):
        for p in sorted((ROOT / base).rglob("*.py")):
            rel = p.relative_to(ROOT).as_posix()
            # `/dev/` = local fixtures, `scripts/research/` = research tier (#4698's fence)
            if "/dev/" in rel or rel.startswith("scripts/research/"):
                continue
            if rel.endswith("__init__.py") or rel in _INFRASTRUCTURE:
                continue
            yield rel, p


class _Reach(ast.NodeVisitor):
    """What families of price store does this module actually reach?"""

    def __init__(self) -> None:
        self.cache = False
        self.adjusted = False
        self.uses_shared_ladder = False
        self.imported_cache_fn = False

    # -- imports -----------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            if a.name == SHARED_LADDER or a.name.startswith(SHARED_LADDER + "."):
                self.uses_shared_ladder = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        if mod == SHARED_LADDER or mod.startswith(SHARED_LADDER + "."):
            self.uses_shared_ladder = True
        if mod in _CACHE_MODULES:
            for a in node.names:
                if a.name in _CACHE_FUNCS:
                    self.imported_cache_fn = True
                    self.cache = True
        self.generic_visit(node)

    # -- literals ----------------------------------------------------------
    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            v = node.value
            if any(m in v for m in _CACHE_MARKERS):
                self.cache = True
            if any(m in v for m in _ADJUSTED_MARKERS):
                self.adjusted = True
        self.generic_visit(node)

    # -- calls -------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        f = node.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        # store.read("yahoo", T) / store.read("stocks", T)
        if name == "read" and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and a0.value in _ADJUSTED_STORE_GROUPS:
                self.adjusted = True
        # equity_factors._closes("broad")
        if name in _CACHE_FUNCS:
            self.cache = True
        self.generic_visit(node)


def _reach(path: Path) -> _Reach:
    r = _Reach()
    try:
        r.visit(ast.parse(path.read_text(encoding="utf-8", errors="replace")))
    except SyntaxError:                                    # not our problem here
        pass
    return r


# --------------------------------------------------------------------------- #
# 1. the graders this PR owns must go through the shared ladder
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("rel", OWNED_GRADERS)
def test_owned_graders_resolve_through_the_shared_ladder(rel):
    """MUTATION: delete the `engine.price_ladder` import (or the rebase call) and this
    fails. This is the test that makes the knowledge propagate instead of being re-learnt
    by the next author from a postmortem."""
    p = ROOT / rel
    assert p.exists(), rel
    r = _reach(p)
    assert r.uses_shared_ladder, (
        f"{rel} prices names but does not import {SHARED_LADDER}. Every production "
        f"grader resolves prices adjusted-first through the shared ladder — a "
        f"hand-rolled cache-first ladder is the defect this guard exists to stop."
    )


def test_grade_us_board_actually_calls_the_rebase_in_main():
    """Importing the ladder is not using it. The 2026-08-06 census read this module
    mid-edit and reported the fix as dead code because `main()` did not yet call it —
    an importable-but-unwired fix is exactly as broken as no fix, and stamps every row
    `price_basis: null` while claiming to be adjusted."""
    tree = ast.parse((ROOT / "scripts/grade_us_board.py").read_text())
    mains = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "main"]
    assert mains, "grade_us_board has no main()"
    called = {n.func.id for n in ast.walk(mains[0])
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "rebase_to_adjusted" in called, (
        "main() never calls rebase_to_adjusted — the panel reaches grade_boards on the "
        "RAW cache basis and every excess_spy mixes bases again."
    )


def test_prophet_postmortem_resolver_is_adjusted_first(tmp_path):
    """The cache must be the LAST rung — asserted BEHAVIOURALLY, on a synthetic store.

    An earlier draft compared source-order positions inside the function text, which is
    both a string match and brittle: it broke the moment the body was refactored to
    delegate, while the actual contract was intact. Planting a name in BOTH families and
    checking which one comes back cannot rot that way, and it fails for the right reason
    if anyone reorders the ladder — the exact regression #4698 measured, and the one the
    module's own note said would require an era stamp.
    """
    import pandas as pd
    from scripts import prophet_postmortem as ppm
    from engine import price_ladder as pl

    assert ppm.SOURCE_CACHE in pl.UNADJUSTED_SOURCES, (
        "prophet_postmortem's cache tag must be the ladder's UNADJUSTED tag so the "
        "coverage receipt names its own basis")

    idx = pd.bdate_range("2026-06-01", periods=20)
    cache = pd.DataFrame({"BOTH": [100.0] * 20, "CACHEONLY": [50.0] * 20}, index=idx)
    d = tmp_path / "data" / "baskets" / "ohlcv"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"close": [999.0] * 20}, index=idx).to_parquet(d / "BOTH.parquet")

    resolve = ppm.close_resolver(tmp_path, cache)
    series, source = resolve("BOTH")
    assert source == ppm.SOURCE_BASKET_OHLCV, (
        "a name carried by BOTH families resolved to the RAW cache — cache-first is back")
    assert float(series.iloc[-1]) == 999.0

    # ...and coverage is still not traded away: a cache-only name resolves, stamped.
    series, source = resolve("CACHEONLY")
    assert source == ppm.SOURCE_CACHE and pl.is_adjusted(source) is False


# --------------------------------------------------------------------------- #
# 2. the census cannot grow — or shrink — in silence
# --------------------------------------------------------------------------- #
_PAIRING_CACHE: dict | None = None


def _pairing_modules() -> dict:
    """Memoized: the scan parses ~2,300 modules, and three tests ask the same question."""
    global _PAIRING_CACHE
    if _PAIRING_CACHE is None:
        out = {}
        for rel, p in _iter_production_modules():
            if rel in OWNED_GRADERS:
                continue
            r = _reach(p)
            if r.cache and r.adjusted and not r.uses_shared_ladder:
                out[rel] = r
        _PAIRING_CACHE = out
    return _PAIRING_CACHE


def test_no_new_module_pairs_the_two_bases():
    """A module that reaches BOTH a raw cache and an adjusted store, without going
    through the shared ladder, is a candidate price-basis mismatch. New ones must be
    fixed or explicitly registered — never added silently."""
    found = set(_pairing_modules())
    new = sorted(found - set(KNOWN_UNMIGRATED))
    assert not new, (
        "NEW module(s) pair an unadjusted breadth cache with an adjusted store:\n  "
        + "\n  ".join(new)
        + f"\n\nResolve prices through {SHARED_LADDER} (adjusted-first, stamped), or add "
          "the module to KNOWN_UNMIGRATED with the reason it is not being fixed."
    )


def test_the_registry_does_not_rot():
    """Fail-closed the other way: a registered module that no longer pairs the two bases
    has been fixed (or deleted) and must leave the registry, or the registry becomes a
    list of things that are no longer true — and the next author trusts it."""
    found = set(_pairing_modules())
    stale = sorted(set(KNOWN_UNMIGRATED) - found)
    assert not stale, (
        "KNOWN_UNMIGRATED lists module(s) that no longer pair the two bases:\n  "
        + "\n  ".join(stale)
        + "\n\nIf they were migrated or deleted, remove them from the registry."
    )


def test_the_registry_is_not_vacuous():
    """A detector that finds nothing would make both tests above pass forever. The
    2026-08-06 census found ~30 unmigrated production modules; if this collapses toward
    zero the AST matchers have stopped matching, not the repo become clean."""
    found = _pairing_modules()
    assert len(found) >= 30, (
        f"only {len(found)} pairing modules detected (46 on 2026-08-06; 47 on 2026-08-07 "
        "once the merge_close_caches accessor was matched) — the AST "
        "matchers have probably stopped recognising a store path or the _closes helper, "
        "which would make the whole guard vacuous"
    )


def test_the_detector_sees_a_planted_pairing(tmp_path):
    """Mutation check on the detector itself: it must FAIL a module that pairs the two
    bases, or every assertion above is decoration."""
    m = tmp_path / "planted.py"
    m.write_text(
        "import pandas as pd\n"
        "from lib import store\n"
        "def go(t):\n"
        "    px = pd.read_parquet('data/breadth/_closes_cache.parquet')[t]\n"
        "    spy = store.read('yahoo', 'SPY')['close']\n"
        "    return px.pct_change() - spy.pct_change()\n"
    )
    r = _reach(m)
    assert r.cache and r.adjusted and not r.uses_shared_ladder

    clean = tmp_path / "clean.py"
    clean.write_text(
        "from engine.price_ladder import resolve_close\n"
        "def go(t):\n"
        "    return resolve_close(t).series\n"
    )
    assert _reach(clean).uses_shared_ladder


def test_the_detector_sees_the_cache_through_the_shared_accessor(tmp_path):
    """The SAME pairing, reached through `lib.closes_panel.merge_close_caches` instead of by
    filename — the shape that made this guard half-blind between #4711 and now.

    Without this, the only thing pinning the accessor marker is the incidental fact that some
    module in the tree happens to use it, and the next accessor rename re-opens the hole
    silently. Drop `merge_close_caches` from `_CACHE_FUNCS` and this fails; the census tests
    would merely go quiet.
    """
    m = tmp_path / "via_accessor.py"
    m.write_text(
        "from lib.closes_panel import merge_close_caches\n"
        "from lib import store\n"
        "def go(t):\n"
        "    panel, _ = merge_close_caches(('breadth', 'midcap_breadth'))\n"
        "    spy = store.read('yahoo', 'SPY')['close']\n"
        "    return panel[t].pct_change() - spy.pct_change()\n"
    )
    r = _reach(m)
    assert r.cache, (
        "a module reaching the raw breadth caches through merge_close_caches reads as "
        "cache-free — the accessor moved and the detector did not follow it")
    assert r.adjusted and not r.uses_shared_ladder
