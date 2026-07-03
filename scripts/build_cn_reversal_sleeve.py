"""CN Reversal Sleeve — SHADOW build (site/factordata/cn_reversal_sleeve.json + preview page).

§W6-CN, CN-5. Ships the validated within-sector 3M reversal edge at ITS OWN product unit — a
monthly-rebalanced, no-gate, equal-weight, small-per-name BASKET (a portfolio, NOT stock tips)
— instead of buried as a tiebreaker in a daily act-now board it overlaps 1/110.

A NON-LIVE shadow artifact: it never touches any live board / linked page. It runs AFTER the
china builds in the asia lane, wrapped so a failure can NEVER break the render. Reuses the
committed china_search plane + risk_radar_intl chip + CN-3 member-context chips (no recompute
of prices → well under a minute).

WHAT IT DOES
------------
  1. Load the committed china_search closes + members plane (the same the reversal watch reads).
  2. Compute the CURRENT deepest-quintile within-sector reversal membership (EW, NO gate) with
     universe hygiene (ST fail-closed, sentinel-aware mktcap floor, ADV floor).
  3. Size the SLEEVE (never per-name) by risk_radar_intl CN gross_factor (today ×0.90 caution),
     surfacing radar state + can_force provenance.
  4. Attach CN-3 member-context chips (demotion flags: raw-LHB / premium-block; probationary
     confirmers: deep-discount block / inst-seat LHB) — DISPLAY ONLY, zero effect on membership.
  5. Register the rebalance to the forward ledger (own parquet, CN-1-compatible conventions) so
     the sleeve accrues its own graded track record from day 1; render the accruing state.
  6. Backcast the trailing ~24 monthly rebalances on the current (upper-bound) plane → a NAV-vs
     -CSI300 line, honestly labeled "reconstruction, upper bound".
  7. Emit sleeve.json + an unlinked, noindex preview page.

Honest presentation: sleeve-level stats only, historical stats labeled UPPER BOUND, per-name
−37.6% maxDD disclosure, ~56% expected monthly hit, the ~10σ "one bet on a bounce regime" note,
small-per-name sizing guidance, T+1/fill-timing note. Passports on every number.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from engine import cn_reversal_sleeve as sleeve
from engine import cn_reversal_sleeve_ledger as ledger
from lib import config
from lib.pages import write_page

log = logging.getLogger("build_cn_reversal_sleeve")

_OUT = "cn_reversal_sleeve.json"
_PAGE = "cn_reversal_sleeve.html"
# Path to the committed W5-A re-derive stats JSON (emitted by
# scripts/china_reversal_rederive_phase0.py after a completed run).  Loaded
# defensively — a missing / corrupt file means the rederive block is omitted
# from the page without crashing the build.
_REDERIVE_STATS = config.ROOT / "research" / "china_alpha" / "w5" / "w5a_rederive_stats.json"
_JUNK_SECTOR = "—"
_ADV_FLOOR_YI = 0.5                 # matches engine.china_liquidity.ADV_FLOOR_YI (post-#791)


# --------------------------------------------------------------------------- #
#  plane loading (reuse the committed china_search panel — no recompute)       #
# --------------------------------------------------------------------------- #
def _load_plane():
    """Return (closes, tkr_sector, tkr_name, tkr_name_zh, tkr_mktcap) from the committed
    china_search panel — the SAME plane engine.china_reversal reads. None on missing/corrupt."""
    dd = config.data_dir()
    cp = dd / "china_search" / "closes.parquet"
    mp = dd / "china_search" / "members.parquet"
    if not (cp.exists() and mp.exists()):
        log.warning("cn reversal sleeve: search panel missing — skipped")
        return None
    try:
        closes = pd.read_parquet(cp).sort_index()
        closes = closes.loc[:, ~closes.columns.duplicated()]
        members = pd.read_parquet(mp)
    except Exception as e:  # noqa: BLE001
        log.warning("cn reversal sleeve: panel unreadable (%s) — skipped", e)
        return None
    tkr_sector = {t: (s if s != _JUNK_SECTOR else "—") for t, s in members["sector"].items()}
    tkr_name = {t: str(n) for t, n in members["name"].items()}
    tkr_name_zh = ({t: str(z) for t, z in members["name_zh"].items()}
                   if "name_zh" in members.columns else {})
    tkr_mktcap = ({t: float(v) for t, v in members["mktcap_yi"].items()}
                  if "mktcap_yi" in members.columns else {})
    return closes, tkr_sector, tkr_name, tkr_name_zh, tkr_mktcap


def _adv_map(tickers):
    """ADV floor input from the deep OHLCV store (measured close×volume). Best-effort — an
    unavailable map simply means the ADV screen passes everything (logged)."""
    try:
        from engine import china_liquidity
        return china_liquidity.adv_map(list(tickers))
    except Exception as e:  # noqa: BLE001
        log.warning("cn reversal sleeve: ADV map unavailable (%s)", e)
        return {}


def _bench_series():
    try:
        from lib import store
        df = store.read("china", sleeve.BENCH_TICKER)
        if df is not None and "close" in df:
            return pd.to_numeric(df["close"], errors="coerce").dropna()
    except Exception as e:  # noqa: BLE001
        log.debug("cn reversal sleeve: bench series unavailable (%s)", e)
    return None


# --------------------------------------------------------------------------- #
#  sleeve sizing chip (risk_radar_intl — SLEEVE-level, never per-name)         #
# --------------------------------------------------------------------------- #
def _sizing():
    """risk_radar_intl CN gross_factor as the SLEEVE-level size multiplier + provenance."""
    try:
        from engine.risk_radar_intl import cn_sleeve_chip
        return cn_sleeve_chip()
    except Exception as e:  # noqa: BLE001
        log.warning("cn reversal sleeve: sizing chip unavailable (%s)", e)
        return {"sleeve_factor": 1.0, "radar_state": None, "can_force": False,
                "label_en": "Sleeve ×1.00 — CN drawdown radar: unavailable",
                "label_zh": "仓位 ×1.00 — CN回撤雷达：不可用",
                "passport": {"basis": "measured", "display_only": True, "degraded": True}}


# --------------------------------------------------------------------------- #
#  member-context chips (CN-3 — DISPLAY ONLY, zero membership effect)          #
# --------------------------------------------------------------------------- #
def _member_context():
    """{ticker: {demotions:[...], probationary:{...}}} from CN-3 altdata. DISPLAY ONLY — these
    NEVER affect membership or weights (asserted in tests). Best-effort: {} on any failure."""
    ctx: dict[str, dict] = {}
    try:
        from engine import china_altdata
        prob = china_altdata._probationary_chips()      # deep-discount block, inst-seat LHB
        for t, chips in prob.items():
            ctx.setdefault(t, {}).setdefault("probationary", {}).update(chips)
    except Exception as e:  # noqa: BLE001
        log.debug("cn reversal sleeve: probationary chips unavailable (%s)", e)
    try:
        from engine import china_extras as ce
        # DEMOTION flags (measured wrong-sign as raw signals; §W6-CN Fix 2). Display as cautions.
        lhb = ce.lhb() or {}
        for t, lv in lhb.items():
            # raw hot-money LHB flag (游资) — −1.43%/21d fill-realistic on dip names; NOT inst-seat.
            if not lv.get("leading") and (lv.get("hotmoney_score") or 0) > 0:
                ctx.setdefault(t, {}).setdefault("demotions", []).append({
                    "kind": "raw_lhb", "tone": "warn",
                    "label_en": "Raw hot-money LHB (drag)", "label_zh": "游资龙虎榜（拖累）",
                    "measured": "−1.43%/21d fill-realistic on dip names (cluster-t≈−2.2)",
                    "passport": {"basis": "measured", "weight": 0.0, "display_only": True},
                })
        block = ce.block_trades() or {}
        for t, bv in block.items():
            prem = bv.get("avg_premium_pct") or 0.0
            if prem > 0 and (bv.get("block_amt_yi") or 0) > 0:      # premium block (not discount)
                ctx.setdefault(t, {}).setdefault("demotions", []).append({
                    "kind": "premium_block", "tone": "warn",
                    "label_en": "Premium block-trade (drag)", "label_zh": "溢价大宗（拖累）",
                    "measured": "−0.60%/5d premium-block drag (t≈−2.8)",
                    "passport": {"basis": "measured", "weight": 0.0, "display_only": True},
                })
    except Exception as e:  # noqa: BLE001
        log.debug("cn reversal sleeve: demotion chips unavailable (%s)", e)
    return ctx


def _attach_context(members: list[dict], ctx: dict) -> None:
    """Annotate members with their display-only context chips. Mutates in place; membership
    and weights are UNTOUCHED (the whole point — chips are cosmetic)."""
    for m in members:
        c = ctx.get(m.get("ticker"))
        if c:
            m["context_chips"] = c


# --------------------------------------------------------------------------- #
#  W5-B: load the survivorship-honest re-derivation stats (display only)      #
# --------------------------------------------------------------------------- #
def _load_rederive_stats() -> dict | None:
    """Load the W5-A re-derive stats JSON emitted by china_reversal_rederive_phase0.py.

    Returns None when the file is absent or corrupt — the page omits the block
    rather than crashing.  This is display-only metadata: it does NOT affect
    membership, weights, sizing, or the ledger."""
    if not _REDERIVE_STATS.exists():
        log.debug("cn reversal sleeve: rederive stats absent (%s) — block omitted", _REDERIVE_STATS)
        return None
    try:
        import json as _json
        data = _json.loads(_REDERIVE_STATS.read_text())
        # basic sanity: must have a verdict key
        if "verdict" not in data:
            log.warning("cn reversal sleeve: rederive stats missing 'verdict' key — block omitted")
            return None
        return data
    except Exception as e:  # noqa: BLE001
        log.warning("cn reversal sleeve: rederive stats unreadable (%s) — block omitted", e)
        return None


# --------------------------------------------------------------------------- #
#  compute                                                                     #
# --------------------------------------------------------------------------- #
def compute() -> dict:
    plane = _load_plane()
    now = datetime.now(timezone.utc)
    base = {
        "status": "ok", "shadow": True,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "product": "cn_reversal_sleeve",
        "note": ("SHADOW product — the validated A-share within-sector 3M reversal edge shipped "
                 "at its own unit: a monthly-rebalanced, no-gate, equal-weight, small-per-name "
                 "BASKET. This is a PORTFOLIO, not stock tips. Not live; the forward ledger is "
                 "the real record."),
        "reference": sleeve.REFERENCE,
    }
    # load the W5-B re-derive stats early so early-return paths also carry the key
    rederive_stats = _load_rederive_stats()
    if plane is None:
        return {**base, "status": "no_data", "note": "china_search plane missing",
                "rederive_stats": rederive_stats}
    closes, tkr_sector, tkr_name, tkr_name_zh, tkr_mktcap = plane
    adv_by = _adv_map(closes.columns)
    bench = _bench_series()

    membership = sleeve.current_membership(
        closes, tkr_sector, tkr_name, tkr_name_zh=tkr_name_zh, tkr_mktcap=tkr_mktcap,
        adv_by=adv_by, adv_floor_yi=_ADV_FLOOR_YI)
    if membership is None:
        return {**base, "status": "no_data", "note": "reversal membership unavailable",
                "rederive_stats": rederive_stats}

    # sleeve sizing (SLEEVE-level, never per-name) + member-context chips (display only)
    sizing = _sizing()
    ctx = _member_context()
    _attach_context(membership["members"], ctx)
    n_with_ctx = sum(1 for m in membership["members"] if m.get("context_chips"))

    # data_through: the freshest CN session the membership was computed against (distinct
    # from as_of, per the §W6-CN cross-repo staleness contract).
    data_through = str(closes.index.max().date())

    # forward ledger — register THIS rebalance (own parquet, CN-1 conventions). Only the asia
    # lane persists (lane gate); the nightly render lane discards data/ writes anyway.
    ledger_rows = 0
    try:
        lane = "asia" if _is_asia_lane() else None
        ledger_rows = ledger.append_rebalance(membership, data_through=data_through, lane=lane)
    except Exception as e:  # noqa: BLE001
        log.warning("cn reversal sleeve: ledger append skipped (%s)", e)
    try:
        graded = ledger.grade()
    except Exception as e:  # noqa: BLE001
        graded = {"available": False, "note": f"grade failed: {e}"}

    # backcast (reconstruction on the current upper-bound plane)
    try:
        bc = sleeve.backcast(closes, tkr_sector, tkr_name_zh=tkr_name_zh,
                             tkr_mktcap=tkr_mktcap, adv_by=adv_by, adv_floor_yi=_ADV_FLOOR_YI,
                             months=24, bench=bench)
    except Exception as e:  # noqa: BLE001
        log.warning("cn reversal sleeve: backcast skipped (%s)", e)
        bc = None

    return {
        **base,
        "as_of": membership["as_of"],
        "data_through": data_through,
        "n_universe": membership["n_universe"],
        "n_members": membership["n_members"],
        "equal_weight": membership["equal_weight"],
        "construction": membership["construction"],
        "screened": membership["screened"],
        "sectors": membership["sectors"],
        "members": membership["members"],
        "n_members_with_context": n_with_ctx,
        "sizing": sizing,
        "rederive_stats": rederive_stats,
        "backcast": bc,
        "ledger": {
            "rows": ledger_rows,
            "artifact": "data/cn_reversal_sleeve_track/sleeve.parquet",
            "conventions": "CSI300-relative · T+1 fill · locked-limit excluded · data_through",
            "graded": graded,
        },
        "presentation": _presentation_passports(bc),
    }


def _is_asia_lane() -> bool:
    """The asia collection lane sets CI env or is invoked from asia-close.yml. Heuristic: the
    env flag the workflow can set. Defaults to True when run standalone from the asia build (the
    only lane that commits data/). The ledger gate is belt-and-braces regardless."""
    import os
    v = os.environ.get("CN_SLEEVE_LANE", "").strip().lower()
    return v == "asia" or v == "" or os.environ.get("ASIA_LANE", "") == "1"


def _presentation_passports(bc) -> dict:
    """Honest-presentation metadata (per §W6-CN): the disclosures the page must show."""
    ref = sleeve.REFERENCE
    return {
        "is_portfolio_not_tips": True,
        "upper_bound": True,
        "maxdd_disclosure_pct": ref["maxdd_pct"],
        "expected_monthly_hit_pct": ref["hit_pct"],
        "one_bet_note": ("~10σ pairwise-correlation elevation vs random baskets — this is ONE bet "
                         "on a bounce regime, not N independent picks. Size the SLEEVE small."),
        "sizing_guidance": ("Equal-weight, small per name; the sleeve gross is scaled by the CN "
                            "drawdown radar (never per-name vetoes)."),
        "fill_note": ("Entries spread over the rebalance day (T+1 fill). Measured fill haircut "
                      "~1pp/entry, ~2-3pp hit vs close-to-close — survivable, not a product-killer."),
        "backcast_caveat": (bc or {}).get("caveat") if bc else None,
        "passport": {"basis": "measured (upper-bound plane)", "frame": "monthly rebalance",
                     "freshness": "current plane", "n": ref["n_rebalances"],
                     "source": ref["source"]},
    }


# --------------------------------------------------------------------------- #
#  render (unlinked, noindex preview page)                                     #
# --------------------------------------------------------------------------- #
def render(payload: dict, site=None) -> None:
    site = site or (config.ROOT / "site")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = env.get_template("cn_reversal_sleeve.html.j2").render(d=payload, built=built)
    write_page(site / _PAGE, html)
    log.info("wrote %s (%.0f KB)", site / _PAGE, (site / _PAGE).stat().st_size / 1024)


def build(write: bool = True, site=None) -> dict:
    site = site or (config.ROOT / "site")
    payload = compute()
    if write:
        (site / "factordata").mkdir(parents=True, exist_ok=True)
        (site / "factordata" / _OUT).write_text(
            json.dumps(payload, separators=(",", ":"), allow_nan=False, ensure_ascii=False))
        log.info("wrote %s (members=%s, sleeve×%s, ledger rows=%s)", _OUT,
                 payload.get("n_members"), (payload.get("sizing") or {}).get("sleeve_factor"),
                 (payload.get("ledger") or {}).get("rows"))
        try:
            render(payload, site)
        except Exception as e:  # noqa: BLE001 — a render hiccup must not fail the shadow
            log.warning("cn reversal sleeve preview render skipped (%s)", e)
    return payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s :: %(message)s")
    # SHADOW: swallow ALL failures. This runs after the china builds; nothing it does may
    # break the render. Always return 0.
    try:
        build()
    except Exception as e:  # noqa: BLE001
        log.warning("cn reversal sleeve shadow build skipped (%s)", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
