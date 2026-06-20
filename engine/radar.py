"""Divergence Radar — where free observables DISAGREE with price (the variant edge).

The kernel of the narrative radar. It lays ONE non-price observable — federal
contract obligations per ticker (collectors/usaspending.py) — against the theme's
already-priced CONSENSUS read (60-day relative strength, from the baskets payload),
and emits a state per covered theme:

    money up   + price flat/down  -> POSITIVE_DIVERGENCE   (spend ahead of the tape — watch)
    money down + price leading    -> NEGATIVE_DIVERGENCE   (narrative running on fumes)
    money & price same direction  -> CONFIRMED             (corroborated, already priced)
    neither moving                -> QUIET

DISCIPLINE: the radar is SILENT on the diagonal (when sources agree there is no edge —
it is in the tape) and only speaks off it. DISPLAY-ONLY / context, never a trade
trigger. HONEST + NARROW: covers only the federally-exposed members in
data/usaspending/recipient_aliases.json (defense / space / nuclear / uranium /
DoD critical-minerals / gov-software); awards are lagged (most-recent months dropped);
cross-section is small so cross-sectional z is rough (surfaced as a caveat). A
POSITIVE_DIVERGENCE seeds a FALSIFIABLE watch-hypothesis (graded later, Part B), so
the radar measures whether divergence predicts instead of assuming it.

Pure where it can be: compute_radar() takes the baskets payload and optionally an
injected obligations frame, so it is unit-testable without the live source.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

SCHEMA = "radar.v1"

# --- tunables (module-level so they are easy to calibrate) -------------------
LAG_MONTHS = 3            # most-recent award months are incomplete (primes book mods late) -> drop them
RECENT_MONTHS = 3        # "recent" spend window
YOY_LAG = 12             # compare recent window to the SAME months a year ago (kills federal seasonality)
MIN_COVERED = 2          # a theme needs >=2 federally-covered members to qualify
MIN_BASE_USD = 10e6      # ignore trivially small federal footprints (year-ago 3-month spend)
ACCEL_UP = 1.25          # recent3m / year-ago-3m >= this -> spend accelerating
ACCEL_DOWN = 0.80        # <= this -> spend cooling
CON_Z = 0.5              # |robust-z of 60d rel| >= this -> price clearly leading/lagging
Z_CLAMP = 3.5            # winsorise robust-z (small clustered cross-section -> tiny MAD -> blow-ups)
HORIZON_D = 63           # ~3 trading months for the falsifiable watch-hypothesis


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


def _robust_z(values: list[float]) -> list[float]:
    """Median/MAD z (robust to the small, lumpy cross-section). Falls back to std,
    then to zeros when there is no spread."""
    arr = np.asarray([v if v is not None and np.isfinite(v) else np.nan for v in values], float)
    good = arr[~np.isnan(arr)]
    if len(good) < 2:
        return [0.0] * len(values)
    med = float(np.median(good))
    mad = float(np.median(np.abs(good - med))) * 1.4826
    scale = mad if mad > 1e-9 else float(np.std(good))
    if not scale or scale < 1e-9:
        return [0.0] * len(values)
    return [0.0 if np.isnan(v) else float(np.clip((v - med) / scale, -Z_CLAMP, Z_CLAMP)) for v in arr]


def _basket_observable(obl: pd.DataFrame, covered: list[str]) -> dict | None:
    """Per-theme federal-spend acceleration: recent 3 months vs the SAME 3 months a
    year ago. The year-over-year frame removes federal-fiscal seasonality (the Sept
    year-end award spike) and the award-posting lag (year-ago months are fully settled)."""
    cols = [c for c in covered if c in obl.columns]
    if len(cols) < MIN_COVERED:
        return None
    monthly = obl[cols].sum(axis=1, min_count=1).dropna().sort_index()
    if LAG_MONTHS:
        monthly = monthly.iloc[:-LAG_MONTHS] if len(monthly) > LAG_MONTHS else monthly.iloc[:0]
    if len(monthly) < RECENT_MONTHS + YOY_LAG:
        return None
    recent = float(monthly.iloc[-RECENT_MONTHS:].sum())
    prior = float(monthly.iloc[-(RECENT_MONTHS + YOY_LAG):-YOY_LAG].sum())  # same 3 months, 1 year earlier
    if prior < MIN_BASE_USD or prior <= 0:
        return None
    accel = recent / prior
    return {
        "accel": round(accel, 3),
        "recent_3m_usd": round(recent, 0),
        "base_3m_usd": round(prior, 0),  # year-ago same-quarter spend
        "obs_metric": float(np.log(max(accel, 1e-6))),
        "n_covered": len(cols),
        "covered": cols,
    }


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


def _note(state: str, accel: float, rel: float, covered: list[str]) -> tuple[str, str]:
    names = ", ".join(covered[:4]) + ("…" if len(covered) > 4 else "")
    relp = f"{rel * 100:+.0f}%"
    ax = f"{accel:.1f}×"
    if state == "POSITIVE_DIVERGENCE":
        return (f"Federal contract $ to {names} is accelerating (~{ax} the year-ago quarter) "
                f"while the theme's 60-day relative strength sits at {relp}. Money ahead of price — watch.",
                f"流向 {names} 的联邦合同金额同比加速（约为去年同季的 {ax}），"
                f"而该主题 60 日相对强度为 {relp}。资金领先于价格 —— 观察。")
    if state == "NEGATIVE_DIVERGENCE":
        return (f"Federal contract $ to {names} is cooling (~{ax} the year-ago quarter) while price "
                f"still leads ({relp}). The narrative may be running ahead of the fundamentals.",
                f"流向 {names} 的联邦合同金额同比降温（约为去年同季的 {ax}），而价格仍在领先（{relp}）。"
                f"叙事可能已跑在基本面前面。")
    if state == "CONFIRMED_UP":
        return (f"Contract $ and price are both rising — the move is corroborated and largely priced.",
                f"合同金额与价格同步上升 —— 走势已被印证，且大体已反映在价格中。")
    if state == "CONFIRMED_DOWN":
        return (f"Contract $ and price are both falling — corroborated weakness.",
                f"合同金额与价格同步下降 —— 走弱已被印证。")
    return ("No meaningful divergence between federal spend and price.",
            "联邦支出与价格之间无明显背离。")


_RANK = {"POSITIVE_DIVERGENCE": 0, "NEGATIVE_DIVERGENCE": 1,
         "CONFIRMED_UP": 2, "CONFIRMED_DOWN": 2, "QUIET": 3}


def compute_radar(baskets_payload: dict, obligations: pd.DataFrame | None = None,
                  root=None, asof: str | None = None) -> dict | None:
    """Join the federal-spend observable onto the baskets' priced consensus and emit
    per-theme divergence states. Returns None when there is nothing to read."""
    if not baskets_payload or not baskets_payload.get("baskets"):
        return None
    obl = obligations if obligations is not None else store.read("usaspending", "obligations")
    if obl is None or obl.empty:
        log.info("radar: no usaspending obligations — skipping")
        return None

    mem = _membership(root)
    aliases = set(obl.columns)
    asof = asof or baskets_payload.get("as_of") or datetime.now(timezone.utc).date().isoformat()

    rows: list[dict] = []
    for b in baskets_payload["baskets"]:
        members = {m.get("symbol") for m in b.get("members", []) if m.get("symbol")}
        covered = sorted(members & aliases)
        if len(covered) < MIN_COVERED:
            continue
        obs = _basket_observable(obl, covered)
        rel = _consensus(b.get("perf") or {})
        if obs is None or rel is None:
            continue
        rows.append({"b": b, "obs": obs, "rel": rel})

    if not rows:
        log.info("radar: no theme cleared coverage/history floors")
        return None

    con_z = _robust_z([r["rel"] for r in rows])
    obs_z = _robust_z([r["obs"]["obs_metric"] for r in rows])

    flags: list[dict] = []
    n_members_cov = 0
    for r, cz, oz in zip(rows, con_z, obs_z):
        b, obs, rel = r["b"], r["obs"], r["rel"]
        n_members_cov += obs["n_covered"]
        accel = obs["accel"]
        obs_dir = 1 if accel >= ACCEL_UP else (-1 if accel <= ACCEL_DOWN else 0)
        con_dir = 1 if cz >= CON_Z else (-1 if cz <= -CON_Z else 0)
        state = _state(obs_dir, con_dir)
        note_en, note_zh = _note(state, accel, rel, obs["covered"])
        flags.append({
            "id": f"{asof}-{b['id']}",
            "basket": b["id"],
            "name": b.get("name"),
            "name_zh": b.get("name_zh"),
            "category": b.get("category"),
            "state": state,
            "divergence": round(oz - cz, 3),
            "salience": round(abs(oz - cz), 3),
            "observable": {
                "accel": accel, "dir": obs_dir,
                "recent_3m_usd": obs["recent_3m_usd"], "base_3m_usd": obs["base_3m_usd"],
                "z": round(oz, 3), "n_covered": obs["n_covered"], "covered": obs["covered"],
            },
            "consensus": {"rel_60d": round(rel, 4), "z": round(cz, 3), "dir": con_dir},
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
            "members_with_federal_data": n_members_cov,
            "recipients": len(aliases),
        },
        "flags": flags,
        "hypotheses": _hypotheses(flags, mem, asof),
        "caveats": [
            "Federal-contract proxy only — covers defense / space / nuclear / uranium / "
            "DoD critical-minerals / gov-software members, blind to themes with no federal channel.",
            "Award data is lagged; the most recent months are dropped. Cross-section is small, "
            "so the z-scores are rough. Display-only context — not a trade signal.",
        ],
        "caveats_zh": [
            "仅为联邦合同代理指标 —— 覆盖国防／航天／核电／铀燃料／国防部关键矿产／政府软件成员，"
            "对没有联邦渠道的主题无能为力。",
            "合同数据滞后，最近月份已剔除；横截面样本小，故 z 分数较粗。仅供参考 —— 非交易信号。",
        ],
    }


def _hypotheses(flags: list[dict], mem: dict, asof: str) -> list[dict]:
    """A POSITIVE_DIVERGENCE seeds a falsifiable, gradeable watch-hypothesis: the theme's
    ETF proxy should not UNDER-perform SPY by >5% over ~3 months. Graded later (Part B)."""
    try:
        check_by = (pd.Timestamp(asof) + pd.Timedelta(days=91)).date().isoformat()
    except Exception:  # noqa: BLE001
        check_by = None
    out = []
    for f in flags:
        if f["state"] != "POSITIVE_DIVERGENCE":
            continue
        proxy = _proxy_for(f["basket"], mem)
        check = ({"kind": "rel_return", "subject_ticker": proxy, "vs": "SPY",
                  "op": "<", "threshold": -0.05, "horizon_d": HORIZON_D}
                 if proxy else {"kind": "soft", "reason": "no ETF proxy to score"})
        out.append({
            "id": f"{asof}-radar-{f['basket']}",
            "subject": f["basket"], "subject_ticker": proxy,
            "lean": "positive_divergence", "horizon_d": HORIZON_D,
            "thesis": f["note"],
            "falsifier": {
                "text": (f"{proxy or f['basket']} under-performs SPY by more than 5% over ~3 months "
                         f"— federal spend did not lead price."),
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
                fh.write(json.dumps(h, separators=(",", ":")) + "\n")
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
            print(f"  {f['state']:20s} {f['basket']:18s} div={f['divergence']:+.2f} "
                  f"accel={f['observable']['accel']:.2f} rel60={f['consensus']['rel_60d']:+.3f} "
                  f"[{','.join(f['observable']['covered'])}]")
