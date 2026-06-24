"""Vol-Shock Risk Predictor — a forward 0-100 caution gauge that FUSES the
fast / LEADING precursors that tend to flash before an equity volatility shock,
with a transparent per-factor contribution breakdown (the "why").

WHY this exists: the repo's two existing 0-100 scores are deliberately SLOW —
engine.equity_alloc.risk_score (the S&P-Vector de-risk model) and the MRS
(engine.conditions.macro_risk_score) are both built from recession / NFCI /
liquidity / HY-OAS macro legs and LAG a days-ahead vol shock. The leading
precursors (cross-asset concentration, dealer short-gamma, a VIX term inversion,
a compressed variance-risk-premium, complacent positioning, an active
turning-point caution) are all ALREADY computed elsewhere but scattered and never
co-fused. This module is that fusion — and ONLY that fusion: a pure re-reading of
already-published dicts, never a new data fetch.

DISCIPLINE — honest by construction (mirrors engine/sector_bottom.py,
engine/turning_point.py, engine/event_risk.py):
  • DISPLAY-ONLY / VALIDATION-ACCRUING. It is a forward RISK / caution gauge, NOT
    an alpha signal. Nothing scored reads it; it feeds no allocation.
  • Renormalized weighted mean over AVAILABLE factors only (a missing factor drops
    out of BOTH numerator and denominator — engine.conditions._combine_legs /
    engine.equity_alloc.risk_legs precedent), with per-factor `points` that SUM to
    the headline so a stacked bar reconstructs the score (no black box).
  • Thin / young inputs are visibly flagged and down-weighted (put/call n<60).
  • turning_point is a CAPPED conditioning flag — it honors its own never-scored
    doctrine and can never dominate the gauge.
  • A FORWARD OUTCOME LOG (append/resolve/track_record, copied from
    engine.event_risk) accrues each firing against a PRE-REGISTERED outcome
    (realized SPY drawdown over N days OR a VIX intraday-high jump) so the gauge
    can be GRADED on forward data before it is ever allowed to govern anything.
    The band edges + the outcome label are pre-registered HERE, not tuned post-hoc.

Pure function of the stored dicts — no recompute, deterministic, unit-testable,
and wrapped so it NEVER raises into the build (degrade-never-raise house rule).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Config — in-code defaults, overridable via config.yml engine.vol_shock
# (cross_asset._cfg / dislocation.DEFAULTS precedent). All weights/thresholds and
# the PRE-REGISTERED band edges + forward-outcome label live here.
# --------------------------------------------------------------------------- #
DEFAULTS = {
    # Per-factor weights (leading precursors weighted heavier than the slow legs).
    "weights": {
        "concentration": 1.0,   # cross-asset absorption — documented drawdown leader
        "dealer_gamma": 1.0,    # dealer short-gamma amplifies moves
        "vix_term": 0.8,        # front-month vol bid vs 3m (inversion = stress)
        "vrp_skew": 0.7,        # compressed variance premium + fat tail demand
        "put_call": 0.5,        # complacent call-buying (young series, down-weighted)
        "complacency": 0.8,     # hidden-fragility state + breadth divergence
        "drawdown": 0.6,        # slower, VALIDATED macro-stress gauge
        "turning_point": 0.5,   # CAPPED conditioning flag (never-scored doctrine)
        "event_window": 0.4,    # additive positioning-fragility / event proximity
    },
    # PRE-REGISTERED band edges (do NOT tune post-hoc — the forward log grades these).
    "bands": {"elevated": 40, "high": 60, "extreme": 75},
    # put/call series is young early on — n_obs below this => down-weighted.
    "putcall_young_n": 60,
    "putcall_young_factor": 0.35,
    # turning_point sub-score is capped here so the never-scored layer can't dominate.
    "turning_point_cap": 60,
    # VIX term-structure ratio (VIX/VIX3M): deep contango lo => 0 risk, inverted hi => max.
    "vix_term_lo": 0.85,
    "vix_term_hi": 1.05,
    # near-flip proximity window (|spot_vs_flip_pct|) for the dealer-gamma factor.
    "gamma_prox_pct": 3.0,
    # PRE-REGISTERED forward-outcome label (the log grades each firing on this):
    #   HIT if, over (t+1 .. t+N], realized SPY drawdown <= -outcome_spy_move_pct
    #   OR the VIX intraday high >= VIX_t * outcome_vix_jump_mult.
    "outcome_horizon_d": 10,
    "outcome_spy_move_pct": 5.0,
    "outcome_vix_jump_mult": 1.4,
}


def _cfg() -> dict:
    try:
        from lib import config
        over = (config.load().get("engine", {}) or {}).get("vol_shock", {}) or {}
    except Exception:  # noqa: BLE001 — config must never break the snapshot
        over = {}
    cfg = {**DEFAULTS, **over}
    cfg["weights"] = {**DEFAULTS["weights"], **(over.get("weights") or {})}
    cfg["bands"] = {**DEFAULTS["bands"], **(over.get("bands") or {})}
    return cfg


# --------------------------------------------------------------------------- #
# Small defensive helpers
# --------------------------------------------------------------------------- #
def _num(v):
    try:
        f = float(v)
        return f if f == f else None  # drop NaN
    except (TypeError, ValueError):
        return None


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _site_dir() -> Path | None:
    try:
        from lib import config
        return config.ROOT / "site"
    except Exception:  # noqa: BLE001
        return None


def _read_json(path: Path):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        pass
    return None


# --------------------------------------------------------------------------- #
# Input resolution — injected kwargs first, then leak-free fallbacks. Never I/O
# that can block the build (every read is guarded; a miss just drops the factor).
# --------------------------------------------------------------------------- #
def _resolve_vol_sentiment(vs: dict | None) -> dict:
    if isinstance(vs, dict) and vs:
        return vs
    sd = _site_dir()
    if sd is not None:
        d = _read_json(sd / "basketdata" / "vol_sentiment.json")
        if isinstance(d, dict):
            return d
    return {}


def _resolve_gex(latest: dict, gex: dict | None) -> dict:
    """Normalize the dealer-gamma read to {regime, gamma_flip, net_gex_bn,
    spot_vs_flip_pct}. Priority: injected gex -> latest['market_gamma'] (sibling
    S2's first-class field) -> site/gex/SPX.json summary (one build stale, OK for a
    display gauge — staleness shows in asof)."""
    def _norm(src: dict) -> dict:
        if not isinstance(src, dict):
            return {}
        return {
            "regime": src.get("regime") or src.get("gamma_regime"),
            "gamma_flip": _num(src.get("gamma_flip")),
            "net_gex_bn": _num(src.get("net_gex_bn")),
            "spot_vs_flip_pct": _num(src.get("spot_vs_flip_pct")
                                     if src.get("spot_vs_flip_pct") is not None
                                     else src.get("dist_to_flip_pct")),
        }
    if isinstance(gex, dict) and gex:
        n = _norm(gex)
        if n.get("regime") is not None:
            return n
    mg = (latest or {}).get("market_gamma")
    if isinstance(mg, dict) and mg.get("regime") is not None:
        return _norm(mg)
    sd = _site_dir()
    if sd is not None:
        spx = _read_json(sd / "gex" / "SPX.json")
        if isinstance(spx, dict):
            return _norm(spx.get("summary") or spx)
    return {}


# --------------------------------------------------------------------------- #
# Per-factor sub-scores — each returns (sub_0_100 | None, value, note_en) where
# sub is the factor's own 0-100 shock-risk reading (higher = more risk) and None
# means the factor is unavailable (drops out of the renormalization).
# --------------------------------------------------------------------------- #
def _f_concentration(latest: dict):
    ca = (latest or {}).get("cross_asset") or {}
    p = _num(ca.get("absorption_pctile_5y"))
    if p is None:
        return None, None, ""
    sub = _clip(p * 100.0)
    note = "cross-asset moves compound (top-of-range absorption)" if p >= 0.85 \
        else "cross-asset correlation mid-range"
    return sub, round(p, 3), note


def _f_dealer_gamma(latest: dict, gex: dict, cfg: dict):
    regime = gex.get("regime")
    dist = gex.get("spot_vs_flip_pct")
    if regime is None and dist is None:
        return None, None, ""
    prox = 0.0
    if dist is not None:
        prox = _clip(1.0 - abs(dist) / max(cfg["gamma_prox_pct"], 0.1), 0.0, 1.0)
    if regime == "short":
        sub = _clip(75.0 + 25.0 * prox)
        note = "dealers short gamma — they amplify moves"
    elif regime == "long":
        sub = _clip(20.0 + 35.0 * prox)
        note = ("long-gamma cushion but spot near the flip" if prox > 0.5
                else "dealers long gamma — moves dampened")
    else:
        sub = 50.0
        note = "gamma regime indeterminate"
    val = (f"{regime}" + (f" · {dist:+.2f}% to flip" if dist is not None else ""))
    return sub, val, note


def _f_vix_term(latest: dict, vs: dict, cfg: dict):
    vr = vs.get("vol_regime") or {}
    ratio = _num(vr.get("term_ratio"))
    if ratio is None:
        ratio = _num((((latest or {}).get("dislocation") or {}).get("inputs") or {})
                     .get("vix_term"))
    if ratio is None:
        ratio = _num((((latest or {}).get("conditions") or {}).get("risk_appetite") or {})
                     .get("vix_term"))
    if ratio is None:
        return None, None, ""
    lo, hi = cfg["vix_term_lo"], cfg["vix_term_hi"]
    sub = _clip((ratio - lo) / max(hi - lo, 1e-6) * 100.0)
    note = ("term structure inverted — front-month fear bid" if ratio >= 1.0
            else "contango — calm term structure")
    return sub, round(ratio, 3), note


def _f_vrp_skew(latest: dict):
    ra = ((latest or {}).get("conditions") or {}).get("risk_appetite") or {}
    vrp_p = _num(ra.get("vrp_pctile"))
    skew_p = _num(ra.get("skew_pctile"))
    if vrp_p is None and skew_p is None:
        st = ra.get("vrp_state")
        if not st:
            return None, None, ""
        sub = {"compressed": 70.0, "low": 65.0, "normal": 40.0,
               "elevated": 20.0, "rich": 18.0}.get(st, 40.0)
        return sub, st, f"variance-risk premium {st}"
    parts, w = 0.0, 0.0
    if vrp_p is not None:          # LOW vrp percentile = compressed = complacency
        parts += (1.0 - vrp_p); w += 1.0
    if skew_p is not None:        # HIGH skew percentile = tail-hedge demand
        parts += skew_p; w += 1.0
    sub = _clip(parts / w * 100.0)
    note = "compressed variance premium" if (vrp_p is not None and vrp_p < 0.3) \
        else "variance premium mid-range"
    val = ra.get("vrp_state") or (round(vrp_p, 2) if vrp_p is not None else None)
    return sub, val, note


def _f_put_call(vs: dict, cfg: dict):
    """Complacency tail of equity put/call: a LOW put/call percentile (call-buying
    froth) precedes vol spikes, so risk = (1 - percentile). Young (n_obs < N) =>
    down-weighted (returned via the weight, not the sub-score) and flagged.
    Directional polarity documented; this is the weakest leg by design."""
    pc = vs.get("put_call") or {}
    pct = _num(pc.get("equity_pct_in_hist"))
    if pct is None:
        return None, None, "", False
    sub = _clip((1.0 - pct) * 100.0)
    n_obs = pc.get("n_obs")
    young = bool(pc.get("young")) or (isinstance(n_obs, (int, float))
                                      and n_obs < cfg["putcall_young_n"])
    note = ("complacent call-buying (low put/call)" if pct < 0.3
            else "protective put-buying (fearful)" if pct > 0.7
            else "balanced put/call")
    if young:
        note += f" · young series (n={n_obs}), down-weighted"
    return sub, round(pct, 2), note, young


def _f_complacency(latest: dict):
    c = ((latest or {}).get("conditions") or {}).get("complacency") or {}
    state = c.get("state")
    if state is None and not c:
        return None, None, ""
    base = {"hidden_fragility": 85.0, "fragile": 85.0, "watch": 55.0,
            "warning": 55.0, "calm": 20.0}.get(state)
    if base is None:
        base = 55.0 if (c.get("warning") or c.get("strong")) else 30.0
    bonus = 15.0 if c.get("breadth_div") else 0.0
    sub = _clip(base + bonus)
    note = (f"{state or 'mixed'}"
            + (" · breadth diverging from price" if c.get("breadth_div") else ""))
    return sub, state or ("watch" if c.get("warning") else "calm"), note


def _f_drawdown(latest: dict):
    dr = ((latest or {}).get("conditions") or {}).get("drawdown_risk") or {}
    s = _num(dr.get("score"))
    if s is None:
        return None, None, ""
    sub = _clip(s)
    note = f"validated macro-stress drawdown gauge ({dr.get('band', '—')})"
    return sub, round(s, 1), note


def _f_turning_point(latest: dict, cfg: dict):
    tp = (latest or {}).get("turning_point") or {}
    if not tp:
        return None, None, ""
    cap = cfg["turning_point_cap"]
    if tp.get("present") or tp.get("active"):
        sub = float(cap)
        note = "turning-point caution ACTIVE (capped — never-scored layer)"
    elif (tp.get("drivers") or {}).get("one_factor") or tp.get("raw_fire"):
        sub = min(30.0, cap)
        note = "one-factor tape (capped conditioning flag)"
    else:
        sub = 10.0
        note = "no turning-point caution"
    return _clip(sub, 0, cap), tp.get("state") or "normal", note


def _f_event_window(latest: dict, event_risk: dict | None, cfg: dict):
    """Positioning fragility (event-aware): engine.event_risk.fragility() leg-count
    + proximity to the nearest scheduled high-impact catalyst when the already-built
    event_risk snapshot is injected. Additive context (small weight)."""
    try:
        from engine.event_risk import fragility as _frag
        frag = _frag(latest)
    except Exception:  # noqa: BLE001
        frag = None
    if not frag:
        return None, None, ""
    score = int(frag.get("score") or 0)
    base = min(score, 3) / 3.0 * 70.0
    prox = 0.0
    ev_label = None
    if isinstance(event_risk, dict) and event_risk.get("show"):
        dt = event_risk.get("days_to")
        h = cfg["outcome_horizon_d"]
        if isinstance(dt, (int, float)) and dt <= h:
            prox = (1.0 - dt / max(h, 1)) * 30.0
            ev_label = event_risk.get("label")
    # purely-context leg: only contributes when something is actually fragile or an
    # event is near — a zero reading drops out (it must not keep the card alive on
    # its own, nor pad the denominator with a no-information leg).
    if score == 0 and prox == 0.0:
        return None, None, ""
    sub = _clip(base + prox)
    note = f"{score} fragility leg(s)" + (f" · {ev_label} near" if ev_label else "")
    return sub, score, note


# Display metadata per factor (bilingual labels).
_LABELS = {
    "concentration": ("Cross-asset concentration", "跨资产集中度"),
    "dealer_gamma": ("Dealer gamma (short-gamma fragility)", "做市商 Gamma（空头脆弱）"),
    "vix_term": ("VIX term structure (inversion)", "VIX 期限结构（倒挂）"),
    "vrp_skew": ("VRP compression / skew tail", "波动溢价压缩 / 偏度尾部"),
    "put_call": ("Put/call positioning", "看跌/看涨持仓"),
    "complacency": ("Complacency / hidden fragility", "自满 / 隐性脆弱"),
    "drawdown": ("Macro-stress drawdown gauge", "宏观压力回撤计"),
    "turning_point": ("Turning-point fragility (capped)", "转折点脆弱（封顶）"),
    "event_window": ("Positioning fragility (event-aware)", "仓位脆弱（含事件邻近）"),
}
_NOTE_ZH = {
    "cross-asset moves compound (top-of-range absorption)": "跨资产下挫相互叠加（吸收比率处于高位）",
    "cross-asset correlation mid-range": "跨资产相关性处于中位",
    "dealers short gamma — they amplify moves": "做市商持空头 Gamma——会放大波动",
    "dealers long gamma — moves dampened": "做市商持多头 Gamma——波动被抑制",
    "long-gamma cushion but spot near the flip": "多头 Gamma 有缓冲，但价格接近翻转点",
    "gamma regime indeterminate": "Gamma 状态不明",
    "term structure inverted — front-month fear bid": "期限结构倒挂——近月恐慌买盘",
    "contango — calm term structure": "Contango——期限结构平静",
    "compressed variance premium": "波动风险溢价被压缩",
    "variance premium mid-range": "波动风险溢价处于中位",
}


def _color(sub: float) -> str:
    """Stacked-bar / dot colour by how hard the factor is flashing."""
    if sub >= 70:
        return "#d04545"
    if sub >= 45:
        return "#e0a030"
    return "#5a9bd4"


def _band(score: float | None, cfg: dict) -> tuple[str | None, str | None]:
    if score is None:
        return None, None
    b = cfg["bands"]
    if score >= b["extreme"]:
        return "extreme", "极端"
    if score >= b["high"]:
        return "high", "偏高"
    if score >= b["elevated"]:
        return "elevated", "升高"
    return "low", "偏低"


# --------------------------------------------------------------------------- #
# THE snapshot — pure fusion of the already-published dicts.
# --------------------------------------------------------------------------- #
def snapshot(latest: dict | None, vol_sentiment: dict | None = None,
             etf_pulse: dict | None = None, gex: dict | None = None,
             event_risk: dict | None = None) -> dict | None:
    """Forward vol-shock risk gauge fused from the leading precursors on `latest`.

    Returns ``{score, band, band_zh, asof, factors:[...], why, why_zh,
    disclaimer, ...}`` — or ``None`` only when `latest` is empty. ``score=None``
    (the card hides) iff zero factors are available. Each factor row is
    ``{key, label, label_zh, value, points, weight, available, sub, color, note,
    note_zh}`` and active-factor `points` SUM to `score`.

    `vol_sentiment` / `etf_pulse` / `gex` / `event_risk` come from separate
    builders — injected when available, else read leak-free from their side-cars.
    NEVER raises (degrade-never-raise)."""
    if not isinstance(latest, dict) or not latest:
        return None
    cfg = _cfg()
    w = cfg["weights"]
    vs = _resolve_vol_sentiment(vol_sentiment)
    gx = _resolve_gex(latest, gex)
    # etf_pulse is accepted for forward-compat / caller symmetry; no factor reads it yet.
    _ = etf_pulse

    # (sub, value, note, base_weight, weight_factor) per factor — each guarded.
    specs: list[tuple] = []

    def _add(key, fn):
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001 — one bad sub-tree can't kill the card
            log.debug("vol_shock factor %s failed: %s", key, e)
            r = (None, None, "")
        specs.append((key, r))

    _add("concentration", lambda: _f_concentration(latest))
    _add("dealer_gamma", lambda: _f_dealer_gamma(latest, gx, cfg))
    _add("vix_term", lambda: _f_vix_term(latest, vs, cfg))
    _add("vrp_skew", lambda: _f_vrp_skew(latest))
    _add("put_call", lambda: _f_put_call(vs, cfg))
    _add("complacency", lambda: _f_complacency(latest))
    _add("drawdown", lambda: _f_drawdown(latest))
    _add("turning_point", lambda: _f_turning_point(latest, cfg))
    _add("event_window", lambda: _f_event_window(latest, event_risk, cfg))

    # Assemble per-factor entries with EFFECTIVE weights (young put/call down-weighted).
    entries: list[dict] = []
    den = 0.0
    num = 0.0
    for key, r in specs:
        young = False
        if key == "put_call" and isinstance(r, tuple) and len(r) == 4:
            sub, value, note, young = r
        else:
            sub, value, note = (r + (None, None, ""))[:3] if not isinstance(r, tuple) \
                else (r[0], r[1] if len(r) > 1 else None, r[2] if len(r) > 2 else "")
        base_w = float(w.get(key, 0.0))
        eff_w = base_w * (cfg["putcall_young_factor"] if young else 1.0)
        available = sub is not None and eff_w > 0
        label_en, label_zh = _LABELS.get(key, (key, key))
        entry = {
            "key": key, "label": label_en, "label_zh": label_zh,
            "value": value, "weight": round(eff_w, 3), "available": bool(available),
            "sub": round(float(sub), 1) if sub is not None else None,
            "note": note, "note_zh": _NOTE_ZH.get(note, note),
            "color": _color(float(sub)) if sub is not None else "#888",
            "points": None,
        }
        if available:
            den += eff_w
            num += eff_w * float(sub)
        entries.append(entry)

    n_available = sum(1 for e in entries if e["available"])
    if n_available == 0 or den <= 0:
        # No leading factor present — hide the card, but still return a shell so the
        # contract key exists (run.py sets latest['vol_shock']).
        asof = _asof(latest)
        return {"score": None, "band": None, "band_zh": None, "asof": asof,
                "factors": entries, "why": None, "why_zh": None,
                "n_available": 0, "disclaimer": _DISCLAIMER_EN,
                "disclaimer_zh": _DISCLAIMER_ZH}

    score = num / den
    for e in entries:
        if e["available"]:
            e["points"] = round(e["weight"] * float(e["sub"]) / den, 1)

    band, band_zh = _band(score, cfg)
    asof = _asof(latest)

    # "why" — the top 2 contributing factors (by points).
    active = sorted([e for e in entries if e["available"]],
                    key=lambda e: e["points"] or 0, reverse=True)
    top = active[:2]
    why = "; ".join(f"{e['label']} ({e['note']})" for e in top) if top else None
    why_zh = "；".join(f"{e['label_zh']}（{e['note_zh']}）" for e in top) if top else None

    return {
        "score": round(float(score), 1),
        "score_int": int(round(score)),
        "band": band, "band_zh": band_zh,
        "asof": asof,
        "n_available": n_available,
        "factors": entries,
        "why": why, "why_zh": why_zh,
        "horizon_d": cfg["outcome_horizon_d"],
        "outcome_label_en": (f"realized SPY drawdown ≤ −{cfg['outcome_spy_move_pct']:.0f}% "
                             f"OR VIX intraday-high ≥ {cfg['outcome_vix_jump_mult']:.2g}× "
                             f"within {cfg['outcome_horizon_d']}d"),
        "outcome_label_zh": (f"{cfg['outcome_horizon_d']} 日内标普回撤 ≤ −"
                             f"{cfg['outcome_spy_move_pct']:.0f}% 或 VIX 日内高点 ≥ "
                             f"{cfg['outcome_vix_jump_mult']:.2g} 倍"),
        "disclaimer": _DISCLAIMER_EN,
        "disclaimer_zh": _DISCLAIMER_ZH,
    }


_DISCLAIMER_EN = ("Display-only / validation-accruing — a FORWARD vol-shock RISK gauge "
                  "fused from leading precursors, NOT an alpha signal. It feeds no score "
                  "and no allocation; each firing is logged and graded on forward data.")
_DISCLAIMER_ZH = ("仅供展示／正在积累验证——由领先前兆融合而成的「前瞻性波动冲击风险」计，"
                  "并非选股信号。不计入任何评分或仓位；每次触发均会记录并以未来数据评分。")


def _asof(latest: dict) -> str | None:
    a = (latest or {}).get("date")
    if a:
        return str(a)
    for k in ("cross_asset", "dislocation", "turning_point"):
        v = (latest or {}).get(k) or {}
        if v.get("asof"):
            return str(v["asof"])
    return None


# --------------------------------------------------------------------------- #
# Forward-accruing outcome log — copied from engine.event_risk (append / resolve /
# track_record). Each firing is logged with its score + an anchor (the as-of VIX
# level), then resolved against forward SPY drawdown + VIX intraday highs once N
# trading days have elapsed. This is the honesty layer: the gauge cannot govern
# anything until its forward hit-rate is measured.
# --------------------------------------------------------------------------- #
def _log_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    from lib import config
    return config.data_dir() / "vol_shock" / "log.jsonl"


def _read_log(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def _write_log(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")


def append_log(snap: dict | None, latest: dict | None = None,
               path: str | Path | None = None) -> bool:
    """Append today's firing (realized fields filled later by resolve()). Idempotent
    per date. Stores the as-of VIX level as the anchor for the VIX-jump outcome.
    Returns True if a row was added. Never raises."""
    try:
        if not snap or snap.get("score") is None or not snap.get("asof"):
            return False
        p = _log_path(path)
        rows = _read_log(p)
        d = snap.get("asof")
        if any(r.get("date") == d for r in rows):
            return False
        vix_ref = _num(((((latest or {}).get("dislocation") or {}).get("inputs") or {})
                        .get("vix")))
        if vix_ref is None:
            vix_ref = _num((((latest or {}).get("conditions") or {})
                            .get("risk_appetite") or {}).get("vix"))
        rows.append({
            "date": d, "score": snap.get("score"), "band": snap.get("band"),
            "vix_ref": vix_ref, "n_factors": snap.get("n_available"),
            "horizon_d": snap.get("horizon_d"),
            "spy_mae_pct": None, "vix_jump_mult": None, "hit": None,
        })
        _write_log(p, rows)
        return True
    except Exception as e:  # noqa: BLE001 — accrual is additive, never fatal
        log.warning("vol_shock log append failed (%s)", e)
        return False


def resolve(spy_closes: dict, vix_highs: dict | None = None,
            path: str | Path | None = None, cfg: dict | None = None) -> int:
    """Fill the realized forward outcome for matured rows. `spy_closes` /
    `vix_highs` are {iso_date: value} maps that MUST include the firing date (the
    anchor) and ≥ horizon forward trading days. HIT per the pre-registered label:
    SPY drawdown ≤ −outcome_spy_move_pct OR VIX intraday-high ≥ vix_ref×mult over
    (t+1..t+N]. Returns # newly resolved. Never raises."""
    try:
        cfg = cfg or _cfg()
        horizon = int(cfg["outcome_horizon_d"])
        move_thr = float(cfg["outcome_spy_move_pct"])
        vix_mult = float(cfg["outcome_vix_jump_mult"])
        p = _log_path(path)
        rows = _read_log(p)
        if not rows or not spy_closes:
            return 0
        dates = sorted(spy_closes)
        vix_highs = vix_highs or {}
        n = 0
        for r in rows:
            if r.get("hit") is not None or r.get("date") not in spy_closes:
                continue
            i = dates.index(r["date"])
            if i + horizon >= len(dates):
                continue  # not matured yet
            ref = _num(spy_closes[r["date"]])
            if not ref:
                continue
            fwd = [_num(spy_closes[dates[j]]) for j in range(i + 1, i + horizon + 1)]
            fwd = [x for x in fwd if x is not None]
            if not fwd:
                continue
            mae = (min(fwd) / ref - 1.0) * 100.0
            r["spy_mae_pct"] = round(mae, 2)
            vref = _num(r.get("vix_ref"))
            jump = None
            if vref:
                fwd_vh = [_num(vix_highs.get(dates[j]))
                          for j in range(i + 1, i + horizon + 1)]
                fwd_vh = [x for x in fwd_vh if x is not None]
                if fwd_vh:
                    jump = max(fwd_vh) / vref
                    r["vix_jump_mult"] = round(jump, 2)
            r["hit"] = bool(mae <= -move_thr or (jump is not None and jump >= vix_mult))
            n += 1
        if n:
            _write_log(p, rows)
        return n
    except Exception as e:  # noqa: BLE001
        log.warning("vol_shock log resolve failed (%s)", e)
        return 0


def resolve_from_store(path: str | Path | None = None) -> int:
    """Convenience: load SPY closes + VIX intraday highs from the parquet store and
    resolve any matured firings. Lets run.py accrue the forward log in one call.
    Never raises."""
    try:
        from lib import store
        spy = store.read("yahoo", "SPY")
        vix = store.read("yahoo", "^VIX")
        if spy is None or spy.empty:
            return 0
        spy_closes = {d.strftime("%Y-%m-%d"): float(c)
                      for d, c in spy["close"].dropna().items()}
        vix_highs = {}
        if vix is not None and not vix.empty and "high" in vix.columns:
            vix_highs = {d.strftime("%Y-%m-%d"): float(h)
                         for d, h in vix["high"].dropna().items()}
        return resolve(spy_closes, vix_highs, path=path)
    except Exception as e:  # noqa: BLE001
        log.warning("vol_shock resolve_from_store failed (%s)", e)
        return 0


def track_record(path: str | Path | None = None) -> dict:
    """Summarize resolved firings: n, hit-rate, avg score, and hit-rate by band.
    The forward-validation surface (display the same way sector_bottom prints its
    measured stats). Never raises."""
    try:
        rows = [r for r in _read_log(_log_path(path)) if r.get("hit") is not None]
        if not rows:
            return {"n": 0}
        n = len(rows)
        hits = sum(1 for r in rows if r.get("hit"))
        by_band: dict[str, dict] = {}
        for r in rows:
            b = r.get("band") or "—"
            d = by_band.setdefault(b, {"n": 0, "hits": 0})
            d["n"] += 1
            d["hits"] += 1 if r.get("hit") else 0
        for b, d in by_band.items():
            d["hit_rate"] = round(d["hits"] / d["n"], 2) if d["n"] else None
        return {
            "n": n,
            "hit_rate": round(hits / n, 2),
            "avg_score": round(sum(r.get("score") or 0 for r in rows) / n, 1),
            "by_band": by_band,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("vol_shock track_record failed (%s)", e)
        return {"n": 0}
