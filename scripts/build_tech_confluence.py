"""scripts/build_tech_confluence.py — Off-render artifact writer for the tech-confluence combo miner.

Computes multi-signal combination descriptive stats over the US stocks universe and
writes site/factordata/tech_confluence.json (or --output PATH).

HONESTY CONTRACT
----------------
- Display-only / research artifact. SURVIVORSHIP-BIASED mega-cap universe.
- Combos are found by SEARCH over many candidates; the artifact records how many
  were evaluated so the UI can disclose "found by searching N combos — leads,
  not proof".
- All edge claims use MONTH-COLLAPSED win rates (each calendar month contributes
  one observation) and a train/test split at cfg.split_date. Ranking uses the
  Wilson lower bound on the TEST half only.
- No 'validated' claims in any user-facing string (CI-guarded).
- Nulls (insufficient history / 0 combos with small samples) are reported, not hidden.
- Signals come only from engine.tech_catalog.compute (TLT-R3); this module
  never reimplements an indicator.
- Forward horizons restricted to descriptive ladder {10, 21, 42, 63} (TLT-R6).

USAGE
-----
    python scripts/build_tech_confluence.py [--sample N] [--output PATH]
                                             [--max-k K] [--long-top N] [--short-top N]

    --sample N      run on first N tickers only (smoke-test / CI mode)
    --output PATH   write output here (default: site/factordata/tech_confluence.json)
    --max-k K       max legs per combo (default: 4)
    --long-top N    top N long combos in the artifact (default: 150)
    --short-top N   top N short combos in the artifact (default: 75)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Path bootstrap — allow running from any cwd
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
os.chdir(_REPO_ROOT)  # engine modules that do relative data/ reads need this

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_tech_confluence")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_OUTPUT = _REPO_ROOT / "site" / "factordata" / "tech_confluence.json"
_HORIZONS = [10, 21, 42, 63]


# ---------------------------------------------------------------------------
# Lazy imports
# ---------------------------------------------------------------------------

def _import_engine():
    from engine import tech_catalog as tc        # noqa: PLC0415
    from engine import tech_confluence as tcf    # noqa: PLC0415
    from engine import lab                       # noqa: PLC0415
    return tc, tcf, lab


# ---------------------------------------------------------------------------
# Plain-word role mapping (requirement #8)
# ---------------------------------------------------------------------------

def _leg_role(leg: dict[str, Any], direction: int) -> tuple[str, str]:
    """Return (role_en, role_zh) for a leg given the combo direction.

    tf=W prefixes 'weekly ' / '周线' to the role phrase.
    """
    sid = leg["signal_id"]
    kind = leg.get("kind", "event")
    family = leg.get("family", "")
    tf = leg.get("tf", "D")

    if direction > 0:
        # Long / bullish roles
        if kind == "state" and family in {
            "trend", "trend_ribbon", "ma_price", "ichimoku",
            "ma_crosses", "tech_stars",
        }:
            role_en, role_zh = "uptrend backdrop", "上升趋势背景"
        elif kind == "state" and family in {"rsi_bands", "rsi_stack"}:
            role_en, role_zh = "washed-out dip", "超卖回调"
        elif kind == "event" and any(
            kw in sid for kw in ("oversold", "bottom", "reclaim", "double_bottom")
        ):
            role_en, role_zh = "dip signal", "回调信号"
        elif kind == "event" and family == "performance":
            role_en, role_zh = "momentum burst", "动量爆发"
        else:
            role_en, role_zh = "turn-up trigger", "转强触发"
    else:
        # Short / bearish roles
        if kind == "state" and family in {
            "trend", "trend_ribbon", "ma_price", "ichimoku",
            "ma_crosses", "tech_stars",
        }:
            role_en, role_zh = "downtrend backdrop", "下降趋势背景"
        elif kind == "state" and family in {"rsi_bands", "rsi_stack"}:
            role_en, role_zh = "overheated rally", "超买反弹"
        elif kind == "event" and any(
            kw in sid for kw in ("oversold", "bottom", "reclaim", "double_bottom")
        ):
            role_en, role_zh = "top signal", "见顶信号"
        elif kind == "event" and family == "performance":
            role_en, role_zh = "momentum break", "动量破位"
        else:
            role_en, role_zh = "turn-down trigger", "转弱触发"

    # tf=W prefix
    if tf == "W":
        role_en = "weekly " + role_en
        role_zh = "周线" + role_zh

    return role_en, role_zh


# Signal-specific plain short labels for combo names. Role phrases alone made
# every name read "turn-up trigger + double turn-up trigger" — accurate but
# information-free. Standard trader vocabulary (golden cross, RSI, cloud) is
# fine on this Tier-3 study page; the stance line above the board carries the
# plain-word framing.
_SHORT_LABELS: dict[str, tuple[str, str]] = {
    "bb_band_walk_up": ("riding the upper band", "沿上轨强势运行"),
    "bb_band_walk_down": ("pinned to the lower band", "沿下轨弱势运行"),
    "bb_lower_reclaim": ("lower-band reclaim", "收复布林下轨"),
    "bb_upper_rejection": ("upper-band rejection", "布林上轨受阻"),
    "bollinger_breakout_up": ("band breakout up", "布林带向上突破"),
    "bollinger_breakout_down": ("band breakdown", "布林带向下突破"),
    "death_cross_7_35": ("7/35 death cross", "7/35死叉"),
    "death_cross_21_100": ("21/100 death cross", "21/100死叉"),
    "death_cross_50_200": ("50/200 death cross", "50/200死叉"),
    "golden_cross_7_35": ("7/35 golden cross", "7/35金叉"),
    "golden_cross_21_100": ("21/100 golden cross", "21/100金叉"),
    "golden_cross_50_200": ("50/200 golden cross", "50/200金叉"),
    "golden_star_st_7_35": ("Golden Star 7/35", "黄金之星7/35"),
    "golden_star_st_21_100": ("Golden Star 21/100", "黄金之星21/100"),
    "golden_star_lt_50_200": ("Golden Star 50/200", "黄金之星50/200"),
    "death_star_st_7_35": ("Death Star 7/35", "死亡之星7/35"),
    "death_star_st_21_100": ("Death Star 21/100", "死亡之星21/100"),
    "death_star_lt_50_200": ("Death Star 50/200", "死亡之星50/200"),
    "double_bottom_short": ("double bottom (fast)", "短线双底"),
    "double_bottom_long": ("double bottom (slow)", "长线双底"),
    "double_top_short": ("double top (fast)", "短线双顶"),
    "double_top_long": ("double top (slow)", "长线双顶"),
    "ichimoku_above_cloud": ("above the cloud", "云层之上"),
    "ichimoku_below_cloud": ("below the cloud", "云层之下"),
    "ichimoku_tk_cross_up": ("Ichimoku bull cross", "一目均衡表金叉"),
    "ichimoku_tk_cross_down": ("Ichimoku bear cross", "一目均衡表死叉"),
    "ichimoku_cloud_breakout_up": ("cloud breakout", "向上突破云层"),
    "ichimoku_cloud_breakdown": ("cloud breakdown", "向下跌破云层"),
    "ma_buy_7": ("reclaims 7-day line", "站上7日线"),
    "ma_buy_21": ("reclaims 21-day line", "站上21日线"),
    "ma_buy_35": ("reclaims 35-day line", "站上35日线"),
    "ma_buy_100": ("reclaims 100-day line", "站上100日线"),
    "ma_sell_7": ("loses 7-day line", "跌破7日线"),
    "ma_sell_21": ("loses 21-day line", "跌破21日线"),
    "ma_sell_35": ("loses 35-day line", "跌破35日线"),
    "ma_sell_100": ("loses 100-day line", "跌破100日线"),
    "pivot_bottom": ("pivot low forms", "枢轴底形成"),
    "pivot_top": ("pivot high forms", "枢轴顶形成"),
    "possible_runners": ("momentum burst", "动量爆发"),
    "is_strong_move": ("strong move", "强势波动"),
    "ribbon_up": ("ribbon uptrend", "均线带多头排列"),
    "ribbon_down": ("ribbon downtrend", "均线带空头排列"),
    "ribbon_flip_up": ("ribbon flips up", "均线带翻多"),
    "ribbon_flip_down": ("ribbon flips down", "均线带翻空"),
    "rsi_stack_curl_up": ("RSI stack curls up", "RSI组齐转上"),
    "rsi_stack_curl_down": ("RSI stack curls down", "RSI组齐转下"),
    "rsi_stack_oversold": ("RSI stack washed out", "RSI组超卖"),
    "rsi_stack_overbought": ("RSI stack overheated", "RSI组超买"),
    "rsi14_oversold": ("RSI-14 washed out", "RSI-14超卖"),
    "rsi21_oversold": ("RSI-21 washed out", "RSI-21超卖"),
    "rsi14_overbought": ("RSI-14 overheated", "RSI-14超买"),
    "rsi21_overbought": ("RSI-21 overheated", "RSI-21超买"),
    "trend_rising_short": ("short-term uptrend", "短期上升趋势"),
    "trend_rising_long": ("long-term uptrend", "长期上升趋势"),
    "trend_falling_short": ("short-term downtrend", "短期下降趋势"),
    "trend_falling_long": ("long-term downtrend", "长期下降趋势"),
}


def _leg_short_label(leg: dict[str, Any]) -> tuple[str, str]:
    """(short_en, short_zh) for one leg, 'weekly '/'周线' prefixed for W legs."""
    sid = leg["signal_id"]
    en, zh = _SHORT_LABELS.get(
        sid, ((leg.get("display_en") or sid).split(" — ")[0].split(" (")[0], "")
    )
    if not zh:
        zh = (leg.get("display_zh") or en).split(" — ")[0].split("（")[0]
    if leg.get("tf", "D") == "W":
        en = "weekly " + en
        zh = "周线" + zh
    return en, zh


def _combo_name(
    leg_indices: list[int],
    legs: list[dict[str, Any]],
    direction: int,
) -> tuple[str, str]:
    """Combo name from signal-specific short labels.

    Ordering: W legs first, then D-state (the backdrop), then D-event (the
    trigger) — reads as 'context + setup + trigger'.
    """
    def sort_key(idx: int) -> tuple[int, int]:
        l = legs[idx]
        tf_rank = 0 if l.get("tf", "D") == "W" else 1
        kind_rank = 0 if l.get("kind", "event") == "state" else 1
        return (tf_rank, kind_rank)

    ordered = sorted(leg_indices, key=sort_key)
    parts_en = []
    parts_zh = []
    for idx in ordered:
        en, zh = _leg_short_label(legs[idx])
        parts_en.append(en)
        parts_zh.append(zh)
    name_en = " + ".join(parts_en)
    name_zh = " + ".join(parts_zh)
    name_en = name_en[:1].upper() + name_en[1:] if name_en else name_en
    return name_en, name_zh


# ---------------------------------------------------------------------------
# Artifact assembly helpers
# ---------------------------------------------------------------------------

def _build_leg_index(
    legs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Serialize the ordered leg list for the 'legs' key (no role fields — added per combo)."""
    return [
        {
            "leg_id": l["leg_id"],
            "signal_id": l["signal_id"],
            "tf": l["tf"],
            "kind": l["kind"],
            "family": l["family"],
            "direction": l["direction"],
            "display_en": l["display_en"],
            "display_zh": l["display_zh"],
        }
        for l in legs
    ]


def _leg_id_to_index(legs: list[dict[str, Any]]) -> dict[str, int]:
    return {l["leg_id"]: i for i, l in enumerate(legs)}


def _build_combo_entry(
    stats: dict[str, Any],
    combo_id: str,
    legs: list[dict[str, Any]],
    lid_to_idx: dict[str, int],
    panel: Any,
    tcf: Any,
) -> dict[str, Any]:
    """Build one combo artifact entry from mine() stats output."""
    direction = stats["dir"]
    leg_ids: list[str] = stats["legs"]
    leg_indices = [lid_to_idx[lid] for lid in leg_ids if lid in lid_to_idx]

    name_en, name_zh = _combo_name(leg_indices, legs, direction)

    # Determine per-leg role fields for this combo
    # (role depends on direction which is combo-level, so can't be pre-computed in leg index)

    entry: dict[str, Any] = {
        "id": combo_id,
        "legs": leg_indices,
        "k": stats["k"],
        "dir": direction,
        "name_en": name_en,
        "name_zh": name_zh,
    }

    # Per-horizon stat dicts
    for h in _HORIZONS:
        entry[f"h{h}"] = stats.get(f"h{h}")

    # Edge / rank fields
    entry["edge_wr_test"] = stats.get("edge_wr_test")
    entry["edge_wr_train"] = stats.get("edge_wr_train")
    entry["edges_by_h"] = stats.get("edges_by_h")
    entry["consistent"] = stats.get("consistent")
    entry["rank_score"] = stats.get("rank_score")
    entry["mfe_mae_med"] = stats.get("mfe_mae_med")
    entry["n_fires"] = stats.get("n_fires")
    entry["n_tickers"] = stats.get("n_tickers")
    entry["fires_per_year"] = stats.get("fires_per_year")
    entry["fires_last3y"] = stats.get("fires_last3y")
    entry["first_fire"] = stats.get("first_fire")
    entry["last_fire"] = stats.get("last_fire")

    # Current-state helpers
    entry["active_now"] = tcf.active_now(panel, leg_ids)
    entry["recent_fires"] = tcf.recent_fire_events(panel, leg_ids, years=3, cap=40)

    return entry


def _build_pairs_rows(
    mine_result: dict[str, Any],
    legs: list[dict[str, Any]],
    lid_to_idx: dict[str, int],
    panel: Any,
    tcf: Any,
    direction: int,
) -> list[list[Any]]:
    """Compact pair rows: [i, j, n21, wr_mc_test, edge_test, months_test, consistent01, n_active_now]."""
    rows: list[list[Any]] = []
    for stats in mine_result["combos"]:
        if stats["k"] != 2:
            continue
        leg_ids: list[str] = stats["legs"]
        leg_indices = [lid_to_idx[lid] for lid in leg_ids if lid in lid_to_idx]
        if len(leg_indices) != 2:
            continue
        i, j = leg_indices[0], leg_indices[1]
        h21 = stats.get("h21", {}) or {}
        n21 = h21.get("n")
        wr_mc_test = h21.get("wr_mc_test")
        months_test = h21.get("months_test")
        edge_test = stats.get("edge_wr_test")
        consistent01 = 1 if stats.get("consistent") else 0
        active = tcf.active_now(panel, leg_ids)
        n_active_now = len(active)
        rows.append([i, j, n21, wr_mc_test, edge_test, months_test, consistent01, n_active_now])
    return rows


def _n_evaluated_total(n_eval: dict) -> int:
    return sum(n_eval.values())


def _diversify_top(combos: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    """Greedy top-N by rank_score that skips single-leg swaps of picked combos.

    The raw leaderboard floods with variants that differ from a higher-ranked
    combo by one leg (same trade, one interchangeable condition). A candidate
    is skipped when some already-picked combo shares >= k-1 of its legs. The
    all-pairs matrix keeps full breadth; this only shapes the browsing surface
    (disclosed in artifact meta as 'top_selection').
    """
    picked: list[dict[str, Any]] = []
    picked_sets: list[set[str]] = []
    for stats in combos:
        legs = set(stats["legs"])
        if any(len(legs & p) >= len(legs) - 1 for p in picked_sets):
            continue
        picked.append(stats)
        picked_sets.append(legs)
        if len(picked) >= top_n:
            break
    return picked


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Build tech_confluence.json — multi-signal combo miner artifact."
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Run on first N tickers only (smoke-test mode)",
    )
    parser.add_argument(
        "--output", type=Path, default=_DEFAULT_OUTPUT,
        help="Output path (default: site/factordata/tech_confluence.json)",
    )
    parser.add_argument(
        "--max-k", type=int, default=4,
        help="Max legs per combo (default: 4)",
    )
    parser.add_argument(
        "--long-top", type=int, default=150,
        help="Top N long combos in artifact (default: 150)",
    )
    parser.add_argument(
        "--short-top", type=int, default=75,
        help="Top N short combos in artifact (default: 75)",
    )
    args = parser.parse_args(argv)

    output_path: Path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    log.info("=== build_tech_confluence starting ===")

    # Import engine modules
    tc, tcf, lab = _import_engine()

    # Build MinerConfig with CLI overrides
    cfg = tcf.MinerConfig(max_k=args.max_k)

    # Build leg defs
    legs = tcf.build_leg_defs(tc)
    log.info("Leg defs: %d legs enumerated", len(legs))

    # Load universe
    log.info("Loading universe …")
    t_phase = time.monotonic()
    universe: dict = lab.load("ALL", group="stocks")
    if args.sample:
        tickers = sorted(universe.keys())[: args.sample]
        universe = {t: universe[t] for t in tickers}
        log.info("Sample mode: %d tickers", len(universe))

    universe_n = len(universe)
    log.info("Universe: %d tickers", universe_n)

    # --- Build panel ---
    log.info("Building panel …")
    panel = tcf.build_panel(universe, tc, cfg, legs)
    elapsed_panel = time.monotonic() - t_phase
    log.info("[timing] panel: %.1fs", elapsed_panel)

    # --- Mine long ---
    log.info("Mining long combos (dir=+1) …")
    t_phase = time.monotonic()
    mine_long = tcf.mine(panel, direction=+1)
    elapsed_long = time.monotonic() - t_phase
    log.info("[timing] mine_long: %.1fs", elapsed_long)

    # --- Mine short ---
    log.info("Mining short combos (dir=-1) …")
    t_phase = time.monotonic()
    mine_short = tcf.mine(panel, direction=-1)
    elapsed_short = time.monotonic() - t_phase
    log.info("[timing] mine_short: %.1fs", elapsed_short)

    # --- Assemble artifact ---
    log.info("Assembling artifact …")
    t_phase = time.monotonic()

    lid_to_idx = _leg_id_to_index(legs)

    # Leg index for artifact
    leg_index = _build_leg_index(legs)

    # Add per-leg role fields using direction from each leg's own direction attribute
    for entry in leg_index:
        leg = legs[lid_to_idx[entry["leg_id"]]]
        re, rz = _leg_role(leg, leg["direction"])
        entry["role_en"] = re
        entry["role_zh"] = rz

    # 'now': active legs on each ticker's latest bar
    now_map: dict[str, list[int]] = {}
    for tk, pos in panel.last_pos.items():
        active_leg_indices = [
            i for i in range(len(legs))
            if bool(panel.act[i, pos])
        ]
        if active_leg_indices:
            now_map[tk] = active_leg_indices

    # Combos: greedy diversified top-N by rank_score (mine() pre-sorts)
    long_combos_raw = _diversify_top(mine_long["combos"], args.long_top)
    short_combos_raw = _diversify_top(mine_short["combos"], args.short_top)

    long_combos = [
        _build_combo_entry(
            stats=s,
            combo_id=f"L{(i + 1):04d}",
            legs=legs,
            lid_to_idx=lid_to_idx,
            panel=panel,
            tcf=tcf,
        )
        for i, s in enumerate(long_combos_raw)
    ]

    short_combos = [
        _build_combo_entry(
            stats=s,
            combo_id=f"S{(i + 1):04d}",
            legs=legs,
            lid_to_idx=lid_to_idx,
            panel=panel,
            tcf=tcf,
        )
        for i, s in enumerate(short_combos_raw)
    ]

    # Pairs: ALL k==2 combos passing report gate (already in mine results)
    pairs_long = _build_pairs_rows(mine_long, legs, lid_to_idx, panel, tcf, direction=+1)
    pairs_short = _build_pairs_rows(mine_short, legs, lid_to_idx, panel, tcf, direction=-1)

    # n_reported counts
    n_reported_long = len(mine_long["combos"])
    n_reported_short = len(mine_short["combos"])

    # Total candidates searched (for disclosure)
    n_eval_long = mine_long["n_evaluated"]
    n_eval_short = mine_short["n_evaluated"]
    total_candidates = _n_evaluated_total(n_eval_long) + _n_evaluated_total(n_eval_short)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    artifact: dict[str, Any] = {
        "generated_utc": now_utc,
        "universe_n": universe_n,
        "config": cfg.as_meta(),
        "horizons": _HORIZONS,
        "split_date": cfg.split_date,
        "n_evaluated": {
            "long": n_eval_long,
            "short": n_eval_short,
        },
        "n_reported": {
            "long": n_reported_long,
            "short": n_reported_short,
        },
        "n_dup_dropped": {
            "long": mine_long.get("n_dup_dropped", 0),
            "short": mine_short.get("n_dup_dropped", 0),
        },
        "top_selection": (
            "greedy by rank_score; candidates sharing all-but-one leg with a "
            "higher-ranked pick are omitted from the top list (full pair "
            "breadth retained in 'pairs')"
        ),
        "base": {
            "long": mine_long["base"],
            "short": mine_short["base"],
        },
        "universe_caveat": "survivor mega-caps; descriptive not a verdict",
        "search_caveat": (
            f"combos found by searching {total_candidates} candidates; "
            "month-collapsed win rates; treat as leads, not proof"
        ),
        "legs": leg_index,
        "now": now_map,
        "combos": {
            "long": long_combos,
            "short": short_combos,
        },
        "pairs": {
            "long": pairs_long,
            "short": pairs_short,
        },
    }

    elapsed_artifact = time.monotonic() - t_phase
    log.info("[timing] artifact: %.1fs", elapsed_artifact)

    # Write
    with open(output_path, "w") as fh:
        json.dump(artifact, fh, separators=(",", ":"))

    file_kb = output_path.stat().st_size / 1024
    elapsed_total = time.monotonic() - t0
    log.info("Wrote %s (%.1f KB)", output_path, file_kb)
    log.info("=== DONE in %.1fs ===", elapsed_total)

    print(
        f"\n[build_tech_confluence] universe={universe_n} tickers | "
        f"legs={len(legs)} | "
        f"long_reported={n_reported_long} (top {min(args.long_top, n_reported_long)} in artifact) | "
        f"short_reported={n_reported_short} (top {min(args.short_top, n_reported_short)} in artifact) | "
        f"{elapsed_total:.1f}s"
    )
    print(f"  Output: {output_path}")

    from lib.procutil import hard_exit  # noqa: PLC0415
    hard_exit(0)


if __name__ == "__main__":
    main()
