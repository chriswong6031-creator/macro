"""China DISCOVERY / scan layer — off-desk LEADING accumulation (Stage 6a).

The China analogue of engine/intel_discovery.py. The radar fires on sector ETFs
and the alt-data desk ranks individual tickers, so the synthesis universe is the
set-union of names some surface already flagged — a name with quiet sector flow
and no convergence read is invisible by construction. This module scans the
per-name LEADING feeds DIRECTLY for accumulation that precedes a radar/price read:

  • institutional 龙虎榜 net-buying    (china_lhb: inst_net_buy>0 & ≥2 inst seats)
  • block-trade PREMIUM handoff       (china_block_trades: avg_premium_pct>0, material)
  • in-progress buyback               (china_buyback: 实施/完成)
  • rising attention rank             (china_comment: rank_delta>0)

A name showing ≥2 of these leading legs BEFORE the radar/price confirms is the
pre-consensus setup. Each candidate is tagged off_desk (no surface flagged it —
not in basket_spine members [curated ∪ THS concept boards] ∪ altdata convergence
keys) so the hub can inject the off-desk names as bounded discovery dossiers.

CONTEXT-ONLY · DEGRADE-NEVER-RAISE · LEAF · KEYLESS. Every public fn returns plain
data and never raises into a build. Nothing here scores or sizes an allocation; it
republishes leading per-name signals the synthesis would otherwise miss.
See /tmp/china_parity_spec.md Stage 6a.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from functools import lru_cache

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "china_discovery.v1"

# weights over the present LEADING legs (renormalized over whichever fire).
#
# SIGN-FLIP NOTE (research/CHINA_ENGINE_REASSESSMENT.md §W6-CN Fix 2):
#   block_premium was previously +0.24 (treated as accumulation).
#   Measured: block-trade PREMIUM on dip names = −0.60%/5d (t≈−2.8) — DRAINS alpha.
#   Premium = institutional unload disguised as a handoff, not conviction accumulation.
#   Removed from the positive scoring legs; now emitted as a DEMOTION chip on the
#   candidate row (block_premium_demotion=True). The MIN_LEGS count excludes it so
#   a name can only qualify via genuinely positive legs.
_LEG_WEIGHTS = {
    "inst_accum": 0.50,       # bumped: only validated positive leg in this module
    "buyback": 0.30,
    "attention_rising": 0.20,
}
_BUYBACK_CAP = 0.40       # buyback is a CONFIRMER, capped (spec Stage 1 / 6a)
_MIN_LEGS = 2             # mirror intel_discovery min_channels=2


def _f(x):
    if x is None or isinstance(x, (dict, list, bool)):
        return None
    try:
        v = float(x)
        return v if v == v else None      # drop NaN
    except (TypeError, ValueError):
        return None


def _clip01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


# --------------------------------------------------------------------------- #
# collector parquet readers — each degrades to {} (never raises)
# --------------------------------------------------------------------------- #
# append-only drip caches carry a PIT history now; slice to the latest single-day snapshot on read.
_DRIP_DATE_COL = {"china_zt_pool": "date", "china_margin_detail": "date", "china_lhb": "asof"}


def _read_parquet(group: str, file: str):
    """Read data/<group>/<file>.parquet → DataFrame, or None on any failure."""
    try:
        p = config.data_dir() / group / file
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if df is None or df.empty:
            return None
        dc = _DRIP_DATE_COL.get(group)
        if dc and dc in df.columns:
            from collectors._drip import latest_snapshot
            df = latest_snapshot(df, dc)                    # single-day snapshot from PIT history
        return df if df is not None and not df.empty else None
    except Exception as e:  # noqa: BLE001 — a missing/corrupt cache must never break a build
        log.debug("china_discovery: read %s/%s failed (%s)", group, file, e)
        return None


def _col(df, *needles):
    """First column whose name CONTAINS any needle (substring) — akshare columns drift.
    Falls back to an exact match. None if absent."""
    cols = [str(c) for c in df.columns]
    for n in needles:
        if n in cols:                       # exact first
            return n
    for c in cols:
        for n in needles:
            if n in c:                      # substring
                return c
    return None


def _index_by_ticker(df):
    """Map ticker -> last row (dedup, latest wins). Empty on no ticker column."""
    if df is None:
        return {}
    tcol = _col(df, "ticker")
    if tcol is None:
        return {}
    out: dict[str, pd.Series] = {}
    for _, r in df.iterrows():
        t = r.get(tcol)
        if t is None or (isinstance(t, float) and t != t):
            continue
        t = str(t).strip()
        if t:
            out[t] = r           # later rows overwrite -> latest snapshot wins
    return out


def lhb_inst() -> dict[str, dict]:
    """{ticker: {inst_net_buy_yi, n_inst_buy, inst_accum_score}} for INSTITUTIONAL-seat
    net buyers (机构吸筹: inst_net_buy>0 & n_inst_buy≥2). Reads china_lhb/detail.parquet."""
    df = _read_parquet("china_lhb", "detail.parquet")
    out: dict[str, dict] = {}
    if df is None:
        return out
    inb = _col(df, "inst_net_buy_yi", "inst_net_buy", "机构净买")
    nbuy = _col(df, "n_inst_buy", "机构买入")
    score = _col(df, "inst_accum_score")
    for t, r in _index_by_ticker(df).items():
        net = _f(r.get(inb)) if inb else None
        n = _f(r.get(nbuy)) if nbuy else None
        if net is None or n is None or net <= 0 or n < 2:   # LEADING gate
            continue
        sc = _f(r.get(score)) if score else None
        if sc is None:        # collector may not have baked the score → derive (spec formula)
            import math
            sc = 0.5 * _clip01((n - 0) / 4.0) + 0.5 * _clip01(
                math.log1p(max(net * 1e8, 0)) / math.log1p(3e8))
        out[t] = {"inst_net_buy_yi": round(net, 4), "n_inst_buy": int(n),
                  "inst_accum_score": round(_clip01(sc), 4)}
    return out


def block_premium() -> dict[str, dict]:
    """{ticker: {avg_premium_pct, block_amt_yi, block_score}} for MATERIAL premium block
    trades (avg_premium_pct>0 & material). Reads china_block_trades/detail.parquet."""
    df = _read_parquet("china_block_trades", "detail.parquet")
    out: dict[str, dict] = {}
    if df is None:
        return out
    prem = _col(df, "avg_premium_pct", "溢价")
    amt = _col(df, "block_amt_yi", "成交")
    score = _col(df, "block_score")
    # "material" = top tercile by block amount across the snapshot (spec: gated top-tercile)
    amts = []
    if amt:
        for _, r in df.iterrows():
            v = _f(r.get(amt))
            if v is not None:
                amts.append(v)
    thresh = None
    if amts:
        amts.sort()
        thresh = amts[max(0, int(len(amts) * 2 / 3) - 1)]
    for t, r in _index_by_ticker(df).items():
        p = _f(r.get(prem)) if prem else None
        if p is None or p <= 0:                              # premium-only = conviction handoff
            continue
        a = _f(r.get(amt)) if amt else None
        if thresh is not None and a is not None and a < thresh:  # not material → skip
            continue
        sc = _f(r.get(score)) if score else None
        if sc is None:
            sc = _clip01(p / 8.0)        # clip(avg_premium_pct/8) positive arm (spec)
        out[t] = {"avg_premium_pct": round(p, 3),
                  "block_amt_yi": round(a, 4) if a is not None else None,
                  "block_score": round(_clip01(sc), 4)}
    return out


def buyback() -> dict[str, dict]:
    """{ticker: {pct_shares, done_amt_yi, progress, buyback_score}} for IN-PROGRESS buybacks
    (progress contains 实施/完成). Reads china_buyback/buyback.parquet. Score capped 0.40."""
    df = _read_parquet("china_buyback", "buyback.parquet")
    out: dict[str, dict] = {}
    if df is None:
        return out
    pcol = _col(df, "progress", "进度", "状态")
    pct = _col(df, "pct_shares", "占总股本", "比例")
    done = _col(df, "done_amt_yi", "已回购", "实施金额")
    score = _col(df, "buyback_score")
    for t, r in _index_by_ticker(df).items():
        prog = r.get(pcol) if pcol else None
        prog_s = str(prog) if prog is not None else ""
        if not ("实施" in prog_s or "完成" in prog_s or "in" in prog_s.lower()):  # in-progress only
            continue
        sc = _f(r.get(score)) if score else None
        if sc is None:
            import math
            ps = _f(r.get(pct)) if pct else None
            da = _f(r.get(done)) if done else None
            sc = (0.6 * _clip01((ps or 0) / 3.0)
                  + 0.4 * _clip01(math.log1p(max((da or 0) * 1e8, 0)) / math.log1p(1e9)))
        sc = min(_BUYBACK_CAP, _clip01(sc))                 # CONFIRMER cap
        out[t] = {"pct_shares": _f(r.get(pct)) if pct else None,
                  "done_amt_yi": _f(r.get(done)) if done else None,
                  "progress": prog_s or None, "buyback_score": round(sc, 4)}
    return out


def attention_rising() -> dict[str, dict]:
    """{ticker: {rank_delta, attention_rising}} for names whose attention rank is RISING
    (rank_delta>0). Reads china_comment/detail.parquet. attention_rising ∈ {0,1} leg."""
    df = _read_parquet("china_comment", "detail.parquet")
    out: dict[str, dict] = {}
    if df is None:
        return out
    rd = _col(df, "rank_delta")
    for t, r in _index_by_ticker(df).items():
        d = _f(r.get(rd)) if rd else None
        if d is None or d <= 0:                              # only RISING attention is leading
            continue
        out[t] = {"rank_delta": d, "attention_rising": 1.0}
    return out


# --------------------------------------------------------------------------- #
# off-desk universe + runup haircut
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _basket_to_etf() -> dict[str, str]:
    """basket_id -> ETF proxy ticker (invert basket_spine.etf_to_basket). {} on failure."""
    try:
        from engine import china_basket_spine as spine
        out: dict[str, str] = {}
        for etf, bids in spine.etf_to_basket().items():
            for bid in bids:
                out.setdefault(bid, etf)
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("china_discovery: basket_to_etf failed (%s)", e)
        return {}


def _runup_haircut(ticker: str) -> float:
    """Anti-chase: 1.0 (no run-up) → lower as the name's basket ETF has already led.
    Uses china_radar._price_rs of the basket ETF (rolling 63d CSI300-relative return)."""
    try:
        from engine import china_basket_spine as spine
        bid = spine.ticker_to_basket().get(str(ticker))
        if not bid:
            return 1.0
        etf = _basket_to_etf().get(bid)
        if not etf:
            return 1.0
        from engine import china_radar
        rs_pct, _ = china_radar._price_rs(etf)
        if rs_pct is None or rs_pct <= 0:       # lagging/flat ETF → no run-up to haircut
            return 1.0
        return _clip01(1.0 - rs_pct / 15.0)     # +15% rel run-up → fully haircut
    except Exception as e:  # noqa: BLE001
        log.debug("china_discovery: runup_haircut %s failed (%s)", ticker, e)
        return 1.0


@lru_cache(maxsize=1)
def _bundle_universe() -> frozenset:
    """Names ALREADY on a desk = basket_spine members (curated ∪ THS concept boards)
    ∪ altdata convergence keys. A candidate not in here is OFF-DESK. frozenset() on
    failure (→ everything off-desk)."""
    uni: set[str] = set()
    try:
        from engine import china_basket_spine as spine
        uni |= {str(t) for t in spine.member_tickers_all()}
    except Exception as e:  # noqa: BLE001
        log.debug("china_discovery: spine universe failed (%s)", e)
    try:
        from engine import china_altdata
        uni |= {str(t) for t in (china_altdata.convergence_map() or {}).keys()}
    except Exception as e:  # noqa: BLE001
        log.debug("china_discovery: altdata universe failed (%s)", e)
    return frozenset(uni)


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _name_for(ticker: str) -> str | None:
    try:
        from engine import china_basket_spine as spine
        return spine.ticker_name(ticker)
    except Exception:  # noqa: BLE001
        return None


def build(today: date | None = None) -> dict:
    """Scan the four LEADING per-name feeds, surface names with ≥2 legs, score each, and
    tag off_desk (not in basket_spine members [curated ∪ THS] ∪ altdata convergence keys).
    Never raises.

    disc_score = weighted mean of the present leading legs × (0.6 + 0.4·runup_haircut),
    legs: 0.34·inst_accum + 0.24·block_premium + 0.22·buyback(cap .40) + 0.20·attention_rising.
    """
    today = today or date.today()
    try:
        inst = lhb_inst()
        block = block_premium()
        bb = buyback()
        att = attention_rising()
    except Exception as e:  # noqa: BLE001 — a feed read must never abort discovery
        log.warning("china_discovery: feed read failed (%s)", e)
        inst, block, bb, att = {}, {}, {}, {}

    universe = _bundle_universe()
    # Include block tickers so we can emit block_premium_demotion chips even on names
    # that don't qualify via positive legs (they won't make it past MIN_LEGS check).
    tickers = set(inst) | set(block) | set(bb) | set(att)
    by_ticker: dict[str, dict] = {}

    for t in tickers:
        # the present POSITIVE leading legs, each contributing a [0,1] value.
        # block_premium is NOT included here — it is a DEMOTION (measured −0.60%/5d,
        # t≈−2.8; see research/CHINA_ENGINE_REASSESSMENT.md §W6-CN Fix 2).
        legs: dict[str, float] = {}
        if t in inst:
            legs["inst_accum"] = _clip01(inst[t]["inst_accum_score"])
        if t in bb:
            legs["buyback"] = min(_BUYBACK_CAP, _clip01(bb[t]["buyback_score"]))
        if t in att:
            legs["attention_rising"] = _clip01(att[t]["attention_rising"])

        if len(legs) < _MIN_LEGS:                      # need ≥2 positive leading legs
            continue

        tw = sum(_LEG_WEIGHTS[k] for k in legs) or 1.0
        raw = sum(_LEG_WEIGHTS[k] * v for k, v in legs.items()) / tw
        haircut = _runup_haircut(t)
        score = round(_clip01(raw * (0.6 + 0.4 * haircut)), 3)

        # block_premium = DEMOTION chip (do NOT count in legs or score; display only).
        # A premium block trade on a reversal-candidate name signals institutional UNLOADING,
        # not accumulation. Wired as a warning chip, never a positive leg.
        block_prem_demotion = None
        if t in block and block[t].get("block_score", 0.0) > 0:
            block_prem_demotion = {
                "avg_premium_pct": block[t].get("avg_premium_pct"),
                "block_amt_yi": block[t].get("block_amt_yi"),
                "note": ("DEMOTION: premium block trade measured −0.60%/5d on dip names "
                         "(t≈−2.8). Signals institutional unload, not accumulation. "
                         "research/CHINA_ENGINE_REASSESSMENT.md §W6-CN Fix 2."),
            }

        reasons = []
        if "inst_accum" in legs:
            reasons.append(f"机构吸筹 (LHB inst net-buy, {inst[t]['n_inst_buy']} seats)")
        if "buyback" in legs:
            reasons.append("buyback in progress")
        if "attention_rising" in legs:
            reasons.append("attention rank rising")
        if block_prem_demotion:
            reasons.append(f"⚠ block premium +{block[t].get('avg_premium_pct', 0):.1f}% (demotion flag)")

        by_ticker[t] = {
            "ticker": t, "name": _name_for(t),
            "disc_score": score, "n_legs": len(legs),
            "legs": sorted(legs.keys()),
            "runup_haircut": round(haircut, 3),
            "off_desk": t not in universe,
            "reason": "; ".join(reasons),
            "inst_accum_score": legs.get("inst_accum"),
            "block_score": None,         # legacy field nulled — block_premium is no longer scored
            "block_premium_demotion": block_prem_demotion,   # DEMOTION chip (display only)
            "buyback_score": legs.get("buyback"),
            "attention_rising": legs.get("attention_rising"),
        }

    cands = sorted(by_ticker.values(),
                   key=lambda d: (d["disc_score"], d["n_legs"]), reverse=True)
    off_desk = [c for c in cands if c["off_desk"]]
    return {
        "schema": SCHEMA, "is_context_only": True, "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "by_ticker": by_ticker,
        "candidates": cands,
        "off_desk": off_desk,
        "n": len(cands), "n_off_desk": len(off_desk),
        "sources": {"inst_accum": len(inst), "block_premium_demotion": len(block),
                    "buyback": len(bb), "attention": len(att)},
        # Sign-flip note: block_premium was previously a +0.24 positive leg.
        # Measured −0.60%/5d (t≈−2.8) → DEMOTION chip only. See §W6-CN Fix 2.
        "sign_flip_note": ("block_premium removed from positive legs; emitted as demotion chip. "
                           "LHB hotmoney_score weight flipped to −0.10 in china_altdata. "
                           "Source: research/CHINA_ENGINE_REASSESSMENT.md §W6-CN Fix 2."),
    }


def load_and_build(today: date | None = None) -> dict:
    """Convenience entry — build() reads the collector parquets directly. Never raises."""
    return build(today)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    b = build()
    print(json.dumps({k: b[k] for k in ("schema", "n", "n_off_desk", "sources")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
