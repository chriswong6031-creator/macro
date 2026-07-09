"""Divergence Radar (v2) — where free observables DISAGREE with price (the variant edge).

The kernel of the narrative radar. It lays a MULTI-SOURCE real-activity observable
(engine/real_activity.py — federal contracts + Quiver gov-contracts/congress/lobbying +
modeled news velocity) against each theme's already-priced CONSENSUS read (60-day
relative strength), and emits a state per covered theme:

    activity up   + price flat/down  -> POSITIVE_DIVERGENCE   (real activity ahead of the tape — watch)
    activity down + price leading     -> NEGATIVE_DIVERGENCE   (narrative running on fumes)
    activity & price same direction   -> CONFIRMED             (corroborated, already priced)
    neither moving                    -> QUIET

DISCIPLINE: the radar is SILENT on the diagonal (when sources agree there is no edge —
it is in the tape) and only speaks off it. DISPLAY-ONLY / context, never a trade trigger.
Each flag carries a LIFECYCLE stage (emerging→confirming→mature→fading) and the per-source
fusion breakdown, so the read is legible. A POSITIVE_DIVERGENCE seeds a FALSIFIABLE
watch-hypothesis (graded later), so the radar MEASURES whether divergence predicts.

Pure where it can be: compute_radar() takes the baskets payload and optional injected
source frames, so it is unit-testable without live data. Injecting sources auto-disables
the live news leg (hermetic). Sources absent (no key, no parquet) are down-weighted away,
so the radar degrades gracefully and sharpens as data sources are added.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from engine import theme_activity
from engine.theme_activity import (  # re-exported primitives (shared with the fuser)
    ACCEL_DOWN, ACCEL_UP, LAG_MONTHS, MIN_BASE_USD, MIN_COVERED, RECENT_MONTHS,
    YOY_LAG, Z_CLAMP, robust_z,
)
from engine import theme_warn as _theme_warn
from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "radar.v2"

CON_Z = 0.5              # |robust-z of 60d rel| >= this -> price clearly leading/lagging

# Radar clock constants — keep these in sync with radar_ic._HORIZON_D (the grader).
# SEED_HORIZON_D: the forward window we promise when seeding a watch-hypothesis (~3 trading
#   months = 63 business days).  radar_ic grades at this same horizon to close the loop.
# CHECK_BY_PAD_D: calendar days to deadline stamped on each hypothesis.  91 ≈ SEED_HORIZON_D
#   + ~28d slippage for weekends, holidays, and price-data latency.
SEED_HORIZON_D = 63      # ~3 trading months — the seeded falsifiable horizon
CHECK_BY_PAD_D = 91      # calendar-day pad to check_by (seed horizon + slippage)

# Back-compat alias so callers that imported HORIZON_D continue to work.
HORIZON_D = SEED_HORIZON_D

_robust_z = robust_z     # back-compat alias (tests + older callers)


def _membership(root=None) -> dict:
    base = (root / "data") if root is not None else config.data_dir()
    try:
        return json.loads((base / "baskets" / "membership.json").read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}


def _proxy_for(basket_id: str, mem: dict) -> str | None:
    b = mem.get(basket_id) or {}
    px = b.get("etf_proxy")
    if isinstance(px, list):
        px = px[0] if px else None
    if isinstance(px, str) and px.strip():
        return px.strip().split()[0]
    return None


def _consensus(perf: dict) -> float | None:
    """The already-priced read: 60-day relative strength vs SPY (fallbacks if absent)."""
    for h in ("60d", "20d", "ytd"):
        leg = (perf or {}).get(h) or {}
        if leg.get("rel") is not None:
            try:
                return float(leg["rel"])
            except (TypeError, ValueError):
                pass
    return None


def _state(obs_dir: int, con_dir: int) -> str:
    if obs_dir > 0 and con_dir <= 0:
        return "POSITIVE_DIVERGENCE"
    if obs_dir < 0 and con_dir > 0:
        return "NEGATIVE_DIVERGENCE"
    if obs_dir != 0 and con_dir != 0 and (obs_dir > 0) == (con_dir > 0):
        return "CONFIRMED_UP" if obs_dir > 0 else "CONFIRMED_DOWN"
    return "QUIET"


def _lifecycle(state: str, rad: dict, con_z: float) -> str:
    """Narrative lifecycle stage from the state + news velocity + how far price has run."""
    news = rad.get("news") or {}
    news_up = (news.get("acceleration") or 0) > 0
    if state == "POSITIVE_DIVERGENCE":
        return "emerging" if news_up else "forming"
    if state == "CONFIRMED_UP":
        return "mature" if con_z >= 1.0 else "confirming"
    if state in ("NEGATIVE_DIVERGENCE", "CONFIRMED_DOWN"):
        return "fading"
    return "quiet"


def _source_phrase(sources: list[dict]) -> tuple[str, str]:
    names_en = [s.get("label_en") for s in sources if s.get("label_en")][:3]
    names_zh = [s.get("label_zh") for s in sources if s.get("label_zh")][:3]
    return ("real activity (" + ", ".join(names_en) + ")" if names_en else "real activity",
            "真实活动（" + "、".join(names_zh) + "）" if names_zh else "真实活动")


def _note(state: str, accel, rel: float, covered: list[str], sources: list[dict]) -> tuple[str, str]:
    names = ", ".join(covered[:4]) + ("…" if len(covered) > 4 else "")
    relp = f"{rel * 100:+.0f}%"
    ax = f"~{accel:.1f}× YoY" if accel else "rising" if state.endswith("UP") or "POSITIVE" in state else "cooling"
    src_en, src_zh = _source_phrase(sources)
    if state == "POSITIVE_DIVERGENCE":
        return (f"{src_en.capitalize()} on {names} is accelerating ({ax}) while the theme's 60-day "
                f"relative strength sits at {relp}. Activity ahead of price — watch.",
                f"{src_zh}（{names}）正在加速（{ax}），而该主题 60 日相对强度为 {relp}。资金/活动领先于价格 —— 观察。")
    if state == "NEGATIVE_DIVERGENCE":
        return (f"{src_en.capitalize()} on {names} is cooling ({ax}) while price still leads ({relp}). "
                f"The narrative may be running ahead of the fundamentals.",
                f"{src_zh}（{names}）正在降温（{ax}），而价格仍在领先（{relp}）。叙事可能已跑在基本面前面。")
    if state == "CONFIRMED_UP":
        return ("Real activity and price are both rising — the move is corroborated and largely priced.",
                "真实活动与价格同步上升 —— 走势已被印证，且大体已反映在价格中。")
    if state == "CONFIRMED_DOWN":
        return ("Real activity and price are both falling — corroborated weakness.",
                "真实活动与价格同步下降 —— 走弱已被印证。")
    return ("No meaningful divergence between real activity and price.",
            "真实活动与价格之间无明显背离。")


_RANK = {"POSITIVE_DIVERGENCE": 0, "NEGATIVE_DIVERGENCE": 1,
         "CONFIRMED_UP": 2, "CONFIRMED_DOWN": 2, "QUIET": 3}


def compute_radar(baskets_payload: dict, obligations: pd.DataFrame | None = None,
                  sources_data: dict | None = None, news: bool | None = None,
                  root=None, asof: str | None = None) -> dict | None:
    """Join the fused multi-source real-activity observable onto the baskets' priced
    consensus and emit per-theme divergence states. Returns None when nothing to read.

    Back-compat: pass `obligations=` (a usaspending frame) and it is routed as the
    usaspending source; injecting any source auto-disables the live news leg (hermetic)
    unless `news=True` is passed explicitly."""
    if not baskets_payload or not baskets_payload.get("baskets"):
        return None
    if sources_data is None and obligations is not None:
        sources_data = {"usaspending": obligations}
    if news is None:
        news = sources_data is None  # live mode pulls news; injected mode stays hermetic

    ra = theme_activity.compute_real_activity(baskets_payload, sources_data=sources_data,
                                              root=root, news=news)
    if not ra:
        log.info("radar: no theme cleared real-activity coverage floors")
        return None

    # WARN velocity parallel leg (display/confluence only; NEVER enters fused_obs_z).
    # Tolerant — absent store / map -> all null; never blocks the radar.
    try:
        warn_leg = _theme_warn.compute_warn_activity(baskets_payload, root=root)
    except Exception as _warn_exc:  # noqa: BLE001
        log.debug("theme_warn: skipped (%s)", _warn_exc)
        warn_leg = {}

    mem = _membership(root)
    asof = asof or baskets_payload.get("as_of") or datetime.now(timezone.utc).date().isoformat()

    rows = []
    for b in baskets_payload["baskets"]:
        rad = ra.get(b.get("id"))
        rel = _consensus(b.get("perf") or {})
        if rad is None or rel is None:
            continue
        rows.append({"b": b, "rad": rad, "rel": rel})
    if not rows:
        log.info("radar: no theme had both real-activity and a price read")
        return None

    con_z = robust_z([r["rel"] for r in rows])

    flags: list[dict] = []
    n_members_cov = 0
    n_sources_total = 0
    for r, cz in zip(rows, con_z):
        b, rad, rel = r["b"], r["rad"], r["rel"]
        primary = rad.get("primary") or {}
        n_members_cov += primary.get("n_covered", 0)
        n_sources_total = max(n_sources_total, rad.get("n_sources", 0))
        obs_dir = rad["obs_dir"]
        fused_obs_z = rad["fused_obs_z"]
        con_dir = 1 if cz >= CON_Z else (-1 if cz <= -CON_Z else 0)
        state = _state(obs_dir, con_dir)
        accel = rad.get("fused_accel")
        note_en, note_zh = _note(state, accel, rel, primary.get("covered") or [], rad.get("sources") or [])
        # WARN parallel leg — display/confluence context; NEVER modifies fused_obs_z
        warn_basket = warn_leg.get(b["id"]) or {}
        flags.append({
            "id": f"{asof}-{b['id']}",
            "basket": b["id"], "name": b.get("name"), "name_zh": b.get("name_zh"),
            "category": b.get("category"),
            "state": state, "lifecycle": _lifecycle(state, rad, cz),
            "divergence": round(fused_obs_z - cz, 3),
            "salience": round(abs(fused_obs_z - cz), 3),
            "observable": {
                "accel": accel, "dir": obs_dir, "z": fused_obs_z,
                "recent_3m_usd": primary.get("recent_3m_usd"), "base_3m_usd": primary.get("base_3m_usd"),
                "n_covered": primary.get("n_covered"), "covered": primary.get("covered"),
                "n_sources": rad.get("n_sources"), "sources": rad.get("sources"),
            },
            "consensus": {"rel_60d": round(rel, 4), "z": round(cz, 3), "dir": con_dir},
            "news": rad.get("news"),
            # warn: SEPARATE loser-cohort/disruption leg (AVOID-shaped evidence only;
            # display + confluence context; never folded into fused_obs_z)
            "warn": {
                "warn_z": warn_basket.get("warn_z"),
                "warn_workers_90d": warn_basket.get("warn_workers_90d"),
                "warn_count_90d": warn_basket.get("warn_count_90d"),
                "warn_yoy_ratio": warn_basket.get("warn_yoy_ratio"),
                "matched_tickers": warn_basket.get("matched_tickers", []),
                "n_matched": warn_basket.get("n_matched", 0),
                "coverage_note": warn_basket.get("coverage_note"),
                "coverage_note_zh": warn_basket.get("coverage_note_zh"),
                "is_context_only": True,
                "may_rank": False,
                "may_gate": False,
            } if warn_basket else None,
            "note": note_en, "note_zh": note_zh,
        })

    flags.sort(key=lambda f: (_RANK[f["state"]], -f["salience"]))
    n_off = sum(1 for f in flags if f["state"].endswith("DIVERGENCE"))

    return {
        "schema": SCHEMA,
        "is_context_only": True,
        "as_of": asof,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lag_months": LAG_MONTHS,
        "coverage": {
            "themes_covered": len(flags),
            "divergences": n_off,
            "members_with_data": n_members_cov,
            "max_sources": n_sources_total,
        },
        "flags": flags,
        "hypotheses": _hypotheses(flags, mem, asof),
        "caveats": [
            "Multi-source real-activity proxy (federal + Quiver gov-contracts/congress/lobbying + "
            "modeled news velocity). Coverage varies by theme; absent sources are down-weighted, not faked.",
            "Activity data is lagged and the cross-section is small, so the z-scores are rough. "
            "Display-only context — not a trade signal.",
        ],
        "caveats_zh": [
            "多源真实活动代理（联邦合同＋Quiver 政府合同／国会／游说＋建模新闻流）。各主题覆盖不同，"
            "缺失来源按权重下调，绝不杜撰。",
            "活动数据滞后、横截面样本小，故 z 分数较粗。仅供参考 —— 非交易信号。",
        ],
    }


def _hypotheses(flags: list[dict], mem: dict, asof: str) -> list[dict]:
    """A POSITIVE_DIVERGENCE seeds a falsifiable, gradeable watch-hypothesis: the theme's
    ETF proxy should not UNDER-perform SPY by >5% over ~3 months.

    Each hypothesis carries `horizon_d` (= SEED_HORIZON_D) so radar_ic can grade it at
    the correct horizon.  `check_by` is asof + CHECK_BY_PAD_D calendar days (adds slippage
    buffer on top of the trading-day horizon).
    """
    try:
        check_by = (pd.Timestamp(asof) + pd.Timedelta(days=CHECK_BY_PAD_D)).date().isoformat()
    except Exception:  # noqa: BLE001
        check_by = None
    out = []
    for f in flags:
        if f["state"] != "POSITIVE_DIVERGENCE":
            continue
        proxy = _proxy_for(f["basket"], mem)
        check = ({"kind": "rel_return", "subject_ticker": proxy, "vs": "SPY",
                  "op": "<", "threshold": -0.05, "horizon_d": SEED_HORIZON_D}
                 if proxy else {"kind": "soft", "reason": "no ETF proxy to score"})
        out.append({
            "id": f"{asof}-radar-{f['basket']}",
            "subject": f["basket"], "subject_ticker": proxy,
            "lean": "positive_divergence",
            "horizon_d": SEED_HORIZON_D,   # stamped at seed time for grader
            "thesis": f["note"],
            "falsifier": {
                "text": (f"{proxy or f['basket']} under-performs SPY by more than 5% over ~3 months "
                         f"— real activity did not lead price."),
                "check": check,
            },
            "check_by": check_by, "logged_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def append_ledger(result: dict, root=None) -> int:
    """Append new watch-hypotheses to data/radar/theses.jsonl, idempotent by id.
    Append-only + guarded — the accountability seed, never breaks the build."""
    if not result or not result.get("hypotheses"):
        return 0
    try:
        base = config.data_dir() if root is None else (root / "data")
        p = base / "radar" / "theses.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        from engine.regime_label import quad_label      # regime stamp → by_regime track record
        regime = quad_label(config.ROOT if root is None else root)
        seen = set()
        if p.exists():
            for line in p.read_text().splitlines():
                try:
                    seen.add(json.loads(line).get("id"))
                except Exception:  # noqa: BLE001
                    continue
        n = 0
        with p.open("a") as fh:
            for h in result["hypotheses"]:
                if h.get("id") in seen:
                    continue
                fh.write(json.dumps({**h, "regime": regime}, separators=(",", ":")) + "\n")
                n += 1
        if n:
            log.info("radar: appended %d watch-hypotheses to %s", n, p)
        return n
    except Exception as e:  # noqa: BLE001 — accountability seed is best-effort
        log.warning("radar ledger append failed: %s", e)
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    bj = config.ROOT / "site" / "basketdata" / "baskets.json"
    payload = json.loads(bj.read_text()) if bj.exists() else None
    res = compute_radar(payload)
    if not res:
        print("radar: no output (need baskets.json + data/usaspending/obligations.parquet)")
    else:
        print(json.dumps(res["coverage"], indent=2))
        for f in res["flags"]:
            o = f["observable"]
            accel = o.get("accel")
            srcs = ",".join(s["name"] for s in (o.get("sources") or []))
            print(f"  {f['state']:20s} {f['lifecycle']:11s} {f['basket']:18s} "
                  f"div={f['divergence']:+.2f} accel={'—' if accel is None else f'{accel:.2f}'} "
                  f"rel60={f['consensus']['rel_60d']:+.3f} [{srcs}]")
