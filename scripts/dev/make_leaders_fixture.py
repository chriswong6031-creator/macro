#!/usr/bin/env python3
"""Generate tests/fixtures/leaders_v2_realdata_fixture.json — the leaders lane's REAL-DATA pin.

RUN-ONCE GENERATOR. The committed artifact is the FIXTURE, not this script: the test suite
reads `tests/fixtures/leaders_v2_realdata_fixture.json` and never runs this file. This script
exists so the fixture's provenance is auditable and reproducible — every number in it can be
re-derived from committed caches by re-running the generator. Re-run it only to re-pin the
fixture on a NEW as-of date (and then say so in the PR: the fixture's whole value is that it
holds a specific measured day still).

WHY IT EXISTS (masterplan §0 G0.3 — `research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md`):
the program's central claim is that the leaders lane v2 surfaces the software/AI cohort rather
than residual-alpha noise. Until this fixture, that claim was only exercised on synthetic rows
in `tests/test_us_leaders_lane.py` — hand-built numbers chosen to make the rule work, which can
only prove the rule is self-consistent. A synthetic fixture cannot fail the way production fails.
This one is real: it is the actual 2026-07-31 board reading for ~45 real names.

DETERMINISM / NO NETWORK
  Every input is a committed file (see SOURCES below). Nothing is fetched, nothing reads the
  wall clock, nothing samples. Two runs produce byte-identical JSON. The cross-sectional map
  handed to `total_return_z` is sorted by ticker before the call so the float summation order
  inside it cannot depend on how the universe happened to be assembled.

WHAT IS CAPTURED, AND FROM WHERE (the production call, not a re-implementation)
  total_return_z  engine.us_board_rank.total_return_z(<universe closes>, sessions=63)
                  — the cross-section is the FULL committed universe, not the ~45 fixture
                    names, so each name's z is its real standing on the board.
  above200        engine.signal_gate.gate(ticker, close)["above200"]
  weekly_bull     engine.signal_gate.gate(ticker, close)["weekly_bull"]
                  — the same one-arg call the builder makes (build_stock_library.py L2322).
  off_high        engine.technicals.snapshot(close)["off_52w_high_pct"]
                  — what the builder puts on disp_map["off_high"] (L2698-2699 via rec["tech"]).
  dir             engine.cycles.analyze(close, high)["ladder"]["dir"]
                  — what engine.setups.setup_score copies onto the board row (setups.py L104).
                    `dir` is read straight off the cycle STATE table (cycles.py STATE_DISP), so
                    the nightly's liquidity / macro_drag / vix_ctx overlays — which move the
                    conviction score, not the state — cannot change it.
  alpha           site/factordata/alpha.json per_ticker[t]["alpha"] — the residual alpha the
                  board row carries (build_stock_library.py L2354-2355 -> setups.py L102).
  theme           engine.us_board_rank.load_theme_context()["by_ticker"][t]

SOURCES (all committed, all as-of 2026-07-31)
  data/stocks/*.parquet                       deep-history holdings closes (+ high)
  data/{breadth,smallcap_breadth,midcap_breadth}/_closes_cache.parquet + constituents.parquet
  data/baskets/extras.parquet                 curated searchable extras (SNOW lives here)
  data/sector_holdings/*.parquet              company name + sector for the deep-history names
  site/factordata/alpha.json                  residual alpha per ticker
  data/baskets/{latest,membership}.json       in-favour theme map

FIXTURE NAME SET (mechanical, stated, not cherry-picked)
  The TOP_N names by total-return z across the whole committed universe, plus the CHARTER
  names the claim is about (the ai_software cohort + the three residual-alpha-only names the
  v1 rule used to select). Nothing is hand-added or hand-removed.

  Because the fixture holds the top TOP_N by z, and the leaders rank key is
  `z + LEADERS_THEME_BOOST`, no omitted name can score above `z[TOP_N+1] + boost`. The
  generator ASSERTS that the LEADERS_CAP-th admitted fixture name already beats that bound —
  i.e. running `_select_leaders` over the fixture yields the SAME top-`cap` as running it over
  the full universe. Without that assertion the fixture could quietly become a flattering
  subset instead of a faithful one.

  Usage:  python3 scripts/dev/make_leaders_fixture.py [--out PATH] [--check]
          --check re-derives and compares against the committed fixture WITHOUT writing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine import cycles, signal_gate, technicals, us_board_rank  # noqa: E402
from engine.playbook import SECTOR_NAMES  # noqa: E402
from scripts.build_stock_library import (  # noqa: E402
    LEADERS_CAP,
    LEADERS_OFF_HIGH_FLOOR,
    LEADERS_THEME_BOOST,
    _SPDR_TO_GICS,
)

# ---------------------------------------------------------------------------
# Pins
# ---------------------------------------------------------------------------
AS_OF = "2026-07-31"          # the measured day the whole program's §1 evidence cites
TOP_N = 40                    # fixture = top-N by total-return z, + CHARTER below
MIN_HISTORY_DAYS = 300        # build_stock_library._one min_days: below this there is no board row

# The cohort the central claim is about (ai_software / non_ai_software), and the three
# residual-alpha-only small caps the v1 rule selected instead (masterplan §1.3).
COHORT = ("SNOW", "PANW", "CRWD", "MSFT", "PLTR")
RESIDUAL_ONLY = ("CALY", "TMP", "NHC")
CHARTER = COHORT + RESIDUAL_ONLY

DEFAULT_OUT = _REPO / "tests" / "fixtures" / "leaders_v2_realdata_fixture.json"

BREADTH_GROUPS = ("breadth", "smallcap_breadth", "midcap_breadth")


# ---------------------------------------------------------------------------
# Universe assembly — mirrors scripts.build_stock_library.universe() priority
# ---------------------------------------------------------------------------

def _holdings_names(data: Path) -> dict[str, tuple[str, str]]:
    """ticker -> (company name, GICS sector) from the sector-holdings parquets.

    Same filter the builder applies: only stems that are real SPDR sector funds, so the
    cross-fund log files (history.parquet, holdings_runs.parquet) cannot leak in as fake
    sector labels.
    """
    out: dict[str, tuple[str, str]] = {}
    hd = data / "sector_holdings"
    if not hd.exists():
        return out
    for p in sorted(hd.glob("*.parquet")):
        if p.stem not in SECTOR_NAMES:
            continue
        sec = _SPDR_TO_GICS.get(SECTOR_NAMES[p.stem], SECTOR_NAMES[p.stem])
        df = pd.read_parquet(p)
        if "ticker" not in df.columns:
            continue
        for _, r in df.iterrows():
            out[str(r["ticker"]).replace(".", "-")] = (str(r.get("name", "")).title(), sec)
    return out


def _truncate(s: pd.Series, asof: pd.Timestamp) -> pd.Series:
    s = s.dropna()
    return s[s.index <= asof]


def build_universe(data: Path, asof: pd.Timestamp) -> dict[str, dict[str, Any]]:
    """{ticker: {close, high, name, sector, source}} from committed caches only.

    Priority order is the builder's: deep-history holdings win, then the breadth caches in
    S&P 500 / 600 / 400 order, then the curated searchable extras. `high` is carried only
    where the builder carries one (the deep-history path) — the breadth caches feed
    universe() with high=None, and the fixture must not be luckier than production.
    """
    uni: dict[str, dict[str, Any]] = {}
    names = _holdings_names(data)
    tail = us_board_rank.LEADERS_MOMENTUM_SESSIONS + 1

    def add(ticker: str, close: pd.Series, high: pd.Series | None,
            name: str | None, sector: str | None, source: str) -> None:
        if ticker in uni:
            return
        close = _truncate(close, asof)
        if len(close) < tail:          # too little history to carry a momentum reading
            return
        if high is not None:
            high = _truncate(high, asof)
        uni[ticker] = {"close": close, "high": high, "name": name,
                       "sector": sector, "source": source}

    for p in sorted((data / "stocks").glob("*.parquet")):
        df = pd.read_parquet(p)
        nm, sec = names.get(p.stem, (None, None))
        add(p.stem, df["close"], df.get("high"), nm, sec, "data/stocks")

    for grp in BREADTH_GROUPS:
        cache, cons = data / grp / "_closes_cache.parquet", data / grp / "constituents.parquet"
        if not (cache.exists() and cons.exists()):
            print(f"  ! {grp}: cache or constituents missing — group skipped")
            continue
        closes, meta = pd.read_parquet(cache), pd.read_parquet(cons)
        for t in closes.columns:
            if t in meta.index:
                add(t, closes[t], None, str(meta.loc[t, "name"]),
                    str(meta.loc[t, "sector"]), f"data/{grp}")

    scfg = yaml.safe_load((_REPO / "config.yml").read_text()).get("stock_search") or {}
    labels = scfg.get("extra_names") or {}
    extras_path = data / "baskets" / "extras.parquet"
    extras = pd.read_parquet(extras_path) if extras_path.exists() else None
    for t in scfg.get("extra_tickers") or []:
        if extras is not None and t in extras.columns:
            lbl = labels.get(t) or {}
            add(t, extras[t], None, lbl.get("name"), lbl.get("sector"),
                "data/baskets/extras")

    return uni


# ---------------------------------------------------------------------------
# Per-name capture
# ---------------------------------------------------------------------------

def capture(ticker: str, entry: dict[str, Any], *, z: float | None,
            z_rank: int | None, alpha_pt: dict, theme_by: dict) -> dict[str, Any]:
    close, high = entry["close"], entry["high"]
    v = signal_gate.gate(ticker, close)
    snap = technicals.snapshot(close)
    ladder = (cycles.analyze(close, high) or {}).get("ladder") or {}
    theme = theme_by.get(ticker)
    return {
        "ticker": ticker,
        "name": entry["name"],
        "sector": entry["sector"],
        "closes_source": entry["source"],
        "history_days": int(len(close)),
        "total_return_z": z,
        "z_rank": z_rank,
        "above200": v.get("above200"),
        "weekly_bull": v.get("weekly_bull"),
        "dir": ladder.get("dir"),
        "cycle_state": ladder.get("state"),
        "off_high": snap.get("off_52w_high_pct"),
        "alpha": (alpha_pt.get(ticker) or {}).get("alpha"),
        # A name with no residual alpha never becomes a board row at all
        # (build_stock_library.py L2354 `if alpha_pt.get(ticker):` gates setup_score), and
        # `scored` is itself filtered to `t in row_by_t` (L3274). So a null here means the
        # name is invisible to _select_leaders in production, and the fixture says so
        # rather than handing the test a row production would never have built.
        "has_board_row": (alpha_pt.get(ticker) or {}).get("alpha") is not None,
        "theme": None if not theme else {
            "id": theme.get("id"), "rank": theme.get("rank"),
            "name": theme.get("name"), "reco": theme.get("reco")},
    }


def _admits(row: dict) -> bool:
    """The `_select_leaders` admission predicate, applied here ONLY to prove the fixture
    is faithful (below). The TEST never re-implements it — it calls the real selector."""
    if not row["has_board_row"]:            # row_by_t.get(t) is None -> skipped
        return False
    if not (row["above200"] is True and row["weekly_bull"] is True):
        return False
    if row["dir"] == "down" or row["total_return_z"] is None or row["off_high"] is None:
        return False
    return row["off_high"] >= LEADERS_OFF_HIGH_FLOOR


def _rank_key(row: dict) -> float:
    return row["total_return_z"] + (LEADERS_THEME_BOOST if row["theme"] else 0.0)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(data: Path, site: Path) -> dict[str, Any]:
    asof = pd.Timestamp(AS_OF)
    print(f"as-of {AS_OF} · assembling the committed universe…")
    uni = build_universe(data, asof)
    print(f"  universe: {len(uni)} names with >= "
          f"{us_board_rank.LEADERS_MOMENTUM_SESSIONS + 1} sessions")

    # Sorted by ticker so the float summation inside total_return_z is assembly-independent.
    tail = us_board_rank.LEADERS_MOMENTUM_SESSIONS + 1
    z = us_board_rank.total_return_z(
        {t: uni[t]["close"].tail(tail).tolist() for t in sorted(uni)},
        sessions=us_board_rank.LEADERS_MOMENTUM_SESSIONS)
    ranked = sorted(z.items(), key=lambda kv: (-kv[1], kv[0]))
    z_rank = {t: i + 1 for i, (t, _) in enumerate(ranked)}
    print(f"  total-return z: {len(z)} names")

    selected = sorted(set([t for t, _ in ranked[:TOP_N]]) | set(CHARTER))
    missing = [t for t in selected if t not in uni]
    if missing:
        raise SystemExit(
            "no committed closes for: " + ", ".join(missing) +
            " — the fixture must not invent a series for a name the caches do not carry")

    alpha_doc = json.loads((site / "factordata" / "alpha.json").read_text())
    alpha_pt = alpha_doc.get("per_ticker") or {}
    theme_ctx = us_board_rank.load_theme_context(data)
    theme_by = theme_ctx.get("by_ticker") or {}

    print(f"  capturing {len(selected)} names (top-{TOP_N} by z + {len(CHARTER)} charter)…")
    rows = [capture(t, uni[t], z=z.get(t), z_rank=z_rank.get(t),
                    alpha_pt=alpha_pt, theme_by=theme_by)
            for t in selected]

    thin = [r["ticker"] for r in rows if r["history_days"] < MIN_HISTORY_DAYS]
    if thin:
        print(f"  ! below the builder's {MIN_HISTORY_DAYS}-session floor (no board row in "
              f"production): {', '.join(thin)}")
    no_alpha = [r["ticker"] for r in rows if r["alpha"] is None]
    if no_alpha:
        print(f"  ! no residual alpha in alpha.json -> no board row in production, "
              f"invisible to _select_leaders: {', '.join(no_alpha)}")

    # ---- faithfulness: the fixture's top-cap IS the full universe's top-cap ----
    admitted = sorted((r for r in rows if _admits(r)), key=lambda r: -_rank_key(r))
    if len(admitted) < LEADERS_CAP:
        raise SystemExit(
            f"only {len(admitted)} admitted names in the fixture — fewer than the "
            f"{LEADERS_CAP} cap, so names outside it could enter the strip; raise TOP_N")
    cap_key = _rank_key(admitted[LEADERS_CAP - 1])
    omitted_ceiling = ranked[TOP_N][1] + LEADERS_THEME_BOOST
    if not cap_key > omitted_ceiling:
        raise SystemExit(
            f"fixture is NOT a faithful subset: the #{LEADERS_CAP} admitted name scores "
            f"{cap_key:.4f}, but an omitted universe name could reach {omitted_ceiling:.4f} "
            f"(z[{TOP_N + 1}] + theme boost). Raise TOP_N until the margin is positive.")
    print(f"  faithful: #{LEADERS_CAP} admitted key {cap_key:.4f} > omitted ceiling "
          f"{omitted_ceiling:.4f} (margin {cap_key - omitted_ceiling:.4f})")

    return {
        "schema": "leaders_v2_realdata_fixture/1",
        "as_of": AS_OF,
        "generated_by": "scripts/dev/make_leaders_fixture.py",
        "purpose": (
            "Real-data pin for masterplan G0.3: the leaders lane v2 surfaces the "
            "software/AI cohort, not residual-alpha noise. Every field is the production "
            "call on committed caches — nothing here is hand-authored."),
        "name_set_rule": (
            f"the top {TOP_N} names by total-return z across the whole committed universe, "
            f"plus the charter names {', '.join(CHARTER)}"),
        "universe": {
            "size": len(uni),
            "z_names": len(z),
            "z_sessions": us_board_rank.LEADERS_MOMENTUM_SESSIONS,
            "z_fn": "engine.us_board_rank.total_return_z",
            "z_rank_floor": ranked[TOP_N - 1][1],
            "first_omitted_z": ranked[TOP_N][1],
            "note": ("the committed-cache subset of the nightly universe: ETFs, crypto and "
                     "the ADR extras with no committed close series are absent"),
        },
        "leaders_params": {
            "cap": LEADERS_CAP,
            "off_high_floor": LEADERS_OFF_HIGH_FLOOR,
            "theme_boost": LEADERS_THEME_BOOST,
        },
        "faithfulness": {
            "admitted_in_fixture": len(admitted),
            "cap_rank_key": round(cap_key, 4),
            "omitted_ceiling": round(omitted_ceiling, 4),
            "claim": ("no universe name outside this fixture can reach the top "
                      f"{LEADERS_CAP}, so _select_leaders over the fixture returns the "
                      "same strip it would return over the full universe"),
        },
        "cohort": list(COHORT),
        "residual_alpha_only": list(RESIDUAL_ONLY),
        "theme_as_of": theme_ctx.get("as_of"),
        "alpha_as_of": alpha_doc.get("as_of"),
        "names": rows,
    }


def _serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--data", type=Path, default=_REPO / "data")
    ap.add_argument("--site", type=Path, default=_REPO / "site")
    ap.add_argument("--check", action="store_true",
                    help="re-derive and diff against the committed fixture; write nothing")
    args = ap.parse_args()

    payload = _serialize(build(args.data, args.site))
    if args.check:
        current = args.out.read_text() if args.out.exists() else ""
        if current == payload:
            print(f"OK — {args.out} matches a fresh derivation")
            return 0
        print(f"DRIFT — {args.out} does not match a fresh derivation")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(payload)
    print(f"wrote {args.out} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
