"""Turning-point fragility meta-layer — "are the signals here coincident?"

The dashboard's regime/rotation/technical reads are COINCIDENT tape readers: they
say what is moving, never how PERSISTENT that move is. At a fast, one-factor
turning point (a single macro shock driving six markets as one bet, positioning
pinned) those reads look high-conviction and then snap back when the driver
resolves — the classic whipsaw (e.g. a geopolitical oil/real-rate/USD shock that
forces a defensive rotation, then reverses in days). This leaf does NOT predict
the turn; it reads ACROSS the existing leaves and, when the configuration is the
kind that whipsaws, raises a CAUTION that LOWERS stated conviction.

DESIGN — display-only, never scored, reads existing snapshots only.
  • A pure function of latest.json: it consumes cross_asset (one-factor-ness),
    market_drivers (which macro driver, how dominant), conditions (RORO/capitulation
    extremes), dislocation (the validated Fed-put test), fed_path (rate-path pinned)
    and the regime transition_state. It invents NO new math and NO new data.
  • The gate fires only on the CONJUNCTION: one-factor tape AND a dominant
    macro-shock driver AND positioning/sentiment stretched. Either leg alone is
    just a normal read.
  • THE SAFETY GUARD: the message never claims mean-reversion. With the Fed put
    PRESENT it says "persistence is unknowable, size smaller" (safe in any regime).
    With the put ABSENT (recession / inflation-locked — the 2008/2022 falling-knife
    regime) it UPGRADES to a risk-reduction message and defers to the Dislocation
    gate — never a fade. Missing Fed-put input degrades to the put-present (no
    structural claim) branch, which is the safe default because that branch makes
    no directional call at all.
  • Why this CANNOT be scored: the layer cannot distinguish "forced and reversible"
    from "early and real" (a genuine late-cycle defensive rotation, or a shock that
    persists) at the moment it must — so the only honest output is lower conviction,
    not a trade. Nothing in axes / regime / macro_risk reads it (invariant test).

ADDITIVE / leaf module: snapshot(latest, transition_state, prev_active) returns a
dict for latest.json["turning_point"], degrading to a normal (no-banner) state if
inputs are unavailable. append_log() / last_active() persist a one-day cooldown so
the caution doesn't flicker, mirroring engine/market_drivers.append_log.
"""
from __future__ import annotations

import pandas as pd

from lib import config


# --- the macro-shock cluster: the drivers whose co-firing IS the one-bet tape ---
MACRO_SHOCK_CLUSTER = ("oil_shock", "real_rate_shock", "usd_shock", "credit_stress")


def _cfg() -> dict:
    """Thresholds, with safe defaults so the leaf works even without a config block."""
    c = (config.load().get("engine", {}).get("turning_point") or {})
    return {
        "strength_primary": c.get("strength_primary", 2.0),   # σ on the dominant driver
        "strength_cluster": c.get("strength_cluster", 1.5),   # σ to count a cluster leg
        "cluster_min": c.get("cluster_min", 2),               # how many cluster legs co-fire
        "roro_tail": c.get("roro_tail", 1.0),                 # |RORO z| extreme
        "fed_pinned_bp": c.get("fed_pinned_bp", 13),          # |market−Fed| gap = pinned
    }


def _one_factor(ca: dict | None) -> tuple[bool, float | None]:
    """Is the cross-asset tape one-factor? Reuse cross_asset's calibrated verdict."""
    if not ca:
        return False, None
    pctile = ca.get("absorption_pctile_5y")
    return ca.get("verdict") == "concentrated", pctile


def _macro_shock(md: dict | None, cfg: dict) -> tuple[bool, list[str]]:
    """Is a macro-shock driver dominant (or several co-firing) — the one-bet driver?"""
    if not md:
        return False, []
    legs = [s.get("driver") for s in (md.get("scores") or [])
            if s.get("driver") in MACRO_SHOCK_CLUSTER
            and (s.get("strength") or 0) >= cfg["strength_cluster"]]
    primary_shock = (md.get("verdict") == "clear"
                     and md.get("primary") in MACRO_SHOCK_CLUSTER
                     and (md.get("strength") or 0) >= cfg["strength_primary"])
    return bool(primary_shock or len(legs) >= cfg["cluster_min"]), legs


def _stretched(latest: dict, transition_state, cfg: dict) -> list[str]:
    """Which positioning / sentiment extremes are firing — returns the EN tags."""
    tags: list[str] = []
    cond = (latest or {}).get("conditions") or {}
    risk = cond.get("risk_appetite") or {}
    roro = risk.get("roro")
    if roro is not None and abs(roro) >= cfg["roro_tail"]:
        tags.append("RORO extreme")
    cap = cond.get("capitulation") or {}
    if cap.get("strong"):
        tags.append("capitulation")
    if transition_state in ("TRANSITIONING", "NEW_REGIME"):
        tags.append("regime transitioning")
    gap = ((latest or {}).get("fed_path") or {}).get("gap") or {}
    gbp = gap.get("gap_bp")
    if gbp is not None and abs(gbp) < cfg["fed_pinned_bp"]:
        tags.append("rate path priced")
    return tags


def _gate(latest: dict, transition_state) -> dict:
    """Pure boolean gate + its evidence, from the latest snapshot dicts."""
    cfg = _cfg()
    one_factor, pctile = _one_factor((latest or {}).get("cross_asset"))
    macro_shock, cluster_legs = _macro_shock((latest or {}).get("market_drivers"), cfg)
    stretched = _stretched(latest, transition_state, cfg)
    raw_fire = bool(one_factor and macro_shock and len(stretched) >= 1)
    return {
        "raw_fire": raw_fire,
        "one_factor": one_factor,
        "absorption_pctile": pctile,
        "macro_shock": macro_shock,
        "cluster_legs": cluster_legs,
        "stretched": stretched,
    }


def _messages(state: str, primary_en: str | None, primary_zh: str | None) -> dict:
    """Bilingual headline / body / sizing note per state. The reversible body makes
    NO mean-reversion claim, so it is safe to show in any regime."""
    drv_en = primary_en or "a single macro driver"
    drv_zh = primary_zh or "单一宏观驱动"
    if state == "fragile-structural":
        return {
            "headline_en": "Fragile turning point — stress with the Fed put ABSENT",
            "headline_zh": "脆弱转折点 — 压力下美联储托底缺失",
            "message_en": (f"One-factor macro stress driven by {drv_en}, with the Fed put "
                           "absent (the 2000/2008/2022 regime). Do NOT treat this as a "
                           "buyable, mean-reverting dip — see the Dislocation gate. The "
                           "reads below are coincident, not predictive."),
            "message_zh": (f"由{drv_zh}驱动的单因子宏观压力，且美联储托底缺失"
                           "（2000／2008／2022 情形）。请勿当作可买入、会均值回归的回调"
                           "——参见错位一道闸。下方读数是巧合同步，并非预测。"),
            "size_note_en": ("Risk-reduction regime, not a fade. Defer to the Dislocation "
                             "gate's falling-knife read; reduce risk rather than chase."),
            "size_note_zh": ("这是降低风险的情形，而非做空机会。以错位闸的接飞刀读数为准；"
                             "降低风险，不要追逐。"),
        }
    if state == "cooling":
        return {
            "headline_en": "Turning-point extreme unwinding",
            "headline_zh": "转折点极值正在消退",
            "message_en": ("The one-factor extreme is unwinding. The new regime is "
                           "unconfirmed and yesterday's reads were coincident — a violent "
                           "snap-back is common here."),
            "message_zh": ("单因子极值正在消退。新周期尚未确认，昨日读数为巧合同步"
                           "——此处常见剧烈反向急拉。"),
            "size_note_en": ("Confirm the new regime before re-engaging at size; don't "
                             "chase the snap-back."),
            "size_note_zh": "在加仓前确认新周期；不要追逐反向急拉。",
        }
    # fragile-reversible
    return {
        "headline_en": "Fragile turning point — signals here are coincident",
        "headline_zh": "脆弱转折点 — 此处信号为巧合同步",
        "message_en": (f"The tape is one-factor (six markets on one macro bet) driven by "
                       f"{drv_en}. Trend and rotation reads here are coincident, not "
                       "predictive — their persistence depends on a driver whose path is "
                       "unknowable. This can reverse violently in either direction."),
        "message_zh": (f"行情呈单因子（六个市场押注同一宏观主题），由{drv_zh}驱动。"
                       "此处的趋势与轮动读数是巧合同步，并非预测——其持续性取决于一个"
                       "路径不可知的驱动。可能向任一方向剧烈反转。"),
        "size_note_en": ("Lower conviction, size smaller, wait for confirmation before "
                         "extrapolating the trend."),
        "size_note_zh": "降低确信度、缩小仓位，在外推趋势前等待确认。",
    }


def snapshot(latest: dict, transition_state=None, prev_active: bool = False) -> dict:
    """Display dict for latest.json['turning_point']. Pure function of `latest`
    (+ the regime transition_state and the prior build's active flag for the
    one-day cooldown). Never raises into the build."""
    try:
        g = _gate(latest or {}, transition_state)
    except Exception:  # pragma: no cover - defensive, mirrors other leaves
        g = {"raw_fire": False, "one_factor": False, "absorption_pctile": None,
             "macro_shock": False, "cluster_legs": [], "stretched": []}
    dl = (latest or {}).get("dislocation") or {}
    # default safe: missing/None Fed-put input => put-present (no structural claim)
    put_absent = dl.get("put_state") == "put-absent"
    raw_fire = g["raw_fire"]

    if raw_fire:
        state = "fragile-structural" if put_absent else "fragile-reversible"
    elif prev_active:
        state = "cooling"
    else:
        state = "normal"

    md = (latest or {}).get("market_drivers") or {}
    msgs = _messages(state, md.get("primary_label"), md.get("primary_label_zh"))
    asof = md.get("asof") or ((latest or {}).get("cross_asset") or {}).get("asof")

    return {
        "asof": asof,
        "present": state != "normal",
        "state": state,
        "raw_fire": raw_fire,
        "active": raw_fire,  # what the next build reads as prev_active
        "put_state": dl.get("put_state"),
        "defer_to": "dislocation" if state == "fragile-structural" else None,
        "drivers": {
            "one_factor": g["one_factor"],
            "absorption_pctile": g["absorption_pctile"],
            "macro_shock": g["macro_shock"],
            "primary": md.get("primary"),
            "primary_label": md.get("primary_label"),
            "primary_label_zh": md.get("primary_label_zh"),
            "cluster_legs": g["cluster_legs"],
            "stretched": g["stretched"],
        },
        **msgs,
        "note": ("Display-only meta-read across cross_asset / market_drivers / "
                 "conditions / dislocation. A conviction guardrail, never scored."),
    }


def _log_path():
    return config.data_dir() / "regime" / "turning_point_log.parquet"


def last_active(asof=None) -> bool:
    """The prior build's raw_fire (for the one-day cooldown). If `asof` is given,
    ignore any row already logged for that date so a same-day rebuild is stable."""
    try:
        p = _log_path()
        if not p.exists():
            return False
        old = pd.read_parquet(p)
        if old.empty or "raw_fire" not in old.columns:
            return False
        if asof is not None and "asof" in old.columns:
            old = old[old["asof"].astype(str) < str(asof)]
        if old.empty:
            return False
        return bool(old.iloc[-1]["raw_fire"])
    except Exception:
        return False


def append_log(snap: dict) -> None:
    """Append today's gate to an append-only log (keep-first per date) so the
    cautions can be GRADED later and so the cooldown has memory. Best-effort —
    never read into a score, never breaks the build."""
    try:
        if not snap or not snap.get("asof"):
            return
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        asof = str(snap["asof"])
        old = pd.read_parquet(p) if p.exists() else None
        if old is not None and "asof" in old.columns and asof in set(old["asof"].astype(str)):
            return  # keep-first: already logged today
        d = snap.get("drivers") or {}
        row = {
            "asof": asof, "state": snap.get("state"), "raw_fire": bool(snap.get("raw_fire")),
            "put_state": snap.get("put_state"), "one_factor": bool(d.get("one_factor")),
            "macro_shock": bool(d.get("macro_shock")), "n_stretch": len(d.get("stretched") or []),
            "primary": d.get("primary"),
        }
        new = pd.DataFrame([row])
        out = pd.concat([old, new], ignore_index=True) if old is not None else new
        out.to_parquet(p, index=False)
    except Exception:
        pass
