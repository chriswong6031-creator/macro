"""Cross-Asset Confirmation — Phase-0 validation.

The macro page now shows a DISPLAY-ONLY "cross-asset confirmation" read: do the
leading-family markets (BONDS + FX) confirm or diverge from the equity regime?
Before ANY of it is allowed to touch a SCORE, this harness answers the only
question that justifies scoring it:

    Does the cross-asset DIVERGENCE add INCREMENTAL forward-drawdown information
    beyond the equity-side drawdown_risk gauge we already compute?

If yes (robust, both halves, lift after controlling for drawdown_risk) → a leg is
worth wiring as a validated gate. If no (the expected outcome — the literature says
most of these reads are COINCIDENT, and the bonds calibration already found the bond
composite ≈ the drawdown_risk leg alone) → it stays DISPLAY-ONLY and the page says so.

What it measures, causally (no look-ahead — signals are the causal engine.bonds /
engine.conditions frames; targets are strictly forward S&P over [t+1..t+63]):

  • lead_caution (0..3) — count of BOND leading-caution flags firing each day:
      credit widening / elevated, MOVE elevated-or-leads-VIX, curve un-inverting.
      (FX is excluded from the empirical test — the literature grades the dollar /
      EM-FX risk-off read as COINCIDENT, endogenous co-movement, not leading, so it
      is display-only by construction. Stated, not silently dropped.)
  • divergence (binary) — equity drawdown_risk LOW *and* lead_caution ≥ 2 (the
      "leading markets cautious while equities calm" config the panel highlights).
  • cycle_divergence (binary) — bond cycle-clock phase later than the equity cycle tag.

Tests: split-half (config split, ~2013) + a forward-window embargo, CONFIRMED needs
both halves meaningful (the bonds-calibration bar); the KEY test is the partial
Spearman of lead_caution vs forward drawdown AFTER controlling for drawdown_risk, and
the conditional drawdown lift WITHIN low-drawdown_risk days.

Writes data/regime/cross_asset_confirm_phase0.json + reports/cross-asset-confirm-phase0.md.
Run: python -m scripts.cross_asset_confirm_phase0
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")

from lib import config  # noqa: E402
from engine import inputs, bonds, conditions  # noqa: E402
from scripts.calibrate_bonds import (build_targets, _spear, _verdict, _conditional,  # noqa: E402
                                     DD_WINDOW, MIN_OBS, SPLIT_DEFAULT)

CREDIT_DIR_WINDOW = 21   # ~1 month HY-OAS change for the widening/tightening read
MOVE_LEAD_MARGIN = 0.5   # MOVE z must exceed VIX z by this to "lead" (matches engine.bonds)
Z_WINDOW = 252           # rolling z window for the MOVE-vs-VIX read


def _z(s: pd.Series, w: int = Z_WINDOW) -> pd.Series:
    m = s.rolling(w, min_periods=w // 4).mean()
    sd = s.rolling(w, min_periods=w // 4).std()
    return (s - m) / sd.replace(0, np.nan)


def _partial_spear(a: pd.Series, b: pd.Series, ctrl: pd.Series) -> tuple[float, int]:
    """Partial Spearman corr(a, b | ctrl): rank everything, linearly residualize a and
    b on ctrl, correlate the residuals. The 'does it add anything beyond drawdown_risk'
    test. Returns (corr, n)."""
    j = pd.concat([a.rename("a"), b.rename("b"), ctrl.rename("c")], axis=1).dropna()
    if len(j) < MIN_OBS:
        return float("nan"), len(j)
    ra, rb, rc = j["a"].rank(), j["b"].rank(), j["c"].rank()

    def resid(y, x):
        x1 = np.c_[np.ones(len(x)), x.to_numpy()]
        beta, *_ = np.linalg.lstsq(x1, y.to_numpy(), rcond=None)
        return y.to_numpy() - x1 @ beta

    rra, rrb = resid(ra, rc), resid(rb, rc)
    if np.std(rra) < 1e-9 or np.std(rrb) < 1e-9:
        return float("nan"), len(j)
    return float(np.corrcoef(rra, rrb)[0, 1]), len(j)


def _reconstruct(fr: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
    """Reconstruct the BOND leading-caution flags + the divergence configs causally
    over history from the engine frames. Mirrors engine.cross_asset_confirm's flag
    logic but on the historical series (bonds_frame is causal)."""
    bcfg = config.load()["bonds"]
    out = pd.DataFrame(index=fr.index)

    # equity-side incumbent gauge (the control) + its low-band mask
    dcfg = config.load()["engine"]["conditions"]["drawdown_risk"]
    dd_risk = fr["drawdown_risk"] if "drawdown_risk" in fr else pd.Series(np.nan, index=fr.index)
    out["dd_risk"] = dd_risk
    out["dd_low"] = (dd_risk < dcfg["elevated"]).astype(float)   # equity gauge "calm"

    # --- credit caution: widening OR elevated+ distress band ---
    cred = pd.Series(0.0, index=fr.index)
    if "hy_oas" in fr:
        hy = fr["hy_oas"]
        widening = hy.diff(CREDIT_DIR_WINDOW) > 0
        band = hy.map(lambda v: bonds._hy_band(v, bcfg["credit"]) if pd.notna(v) else None)
        elevated = band.isin(["elevated", "distress", "crisis"])
        cred = (widening | elevated).astype(float)
    out["f_credit"] = cred

    # --- rates-vol caution: MOVE elevated/crisis OR MOVE leads VIX ---
    vol = pd.Series(0.0, index=fr.index)
    if "move" in fr:
        mv = fr["move"]
        mband = mv.map(lambda v: bonds._move_band(v, bcfg["rates_vol"]) if pd.notna(v) else None)
        elevated = mband.isin(["elevated", "crisis"])
        leads = pd.Series(False, index=fr.index)
        if "vix" in f:
            mz, vz = _z(mv), _z(f["vix"].reindex(fr.index))
            leads = (mz > vz + MOVE_LEAD_MARGIN)
        vol = (elevated | leads).astype(float)
    out["f_rates_vol"] = vol

    # --- curve un-inversion alarm (already a causal flag in bonds_frame) ---
    out["f_uninv"] = (fr["uninversion"].astype(float) if "uninversion" in fr else 0.0)

    out["lead_caution"] = out[["f_credit", "f_rates_vol", "f_uninv"]].sum(axis=1)

    # --- divergence config: equities calm AND ≥2 leading-caution flags ---
    out["divergence"] = ((out["dd_low"] == 1) & (out["lead_caution"] >= 2)).astype(float)

    # --- cycle divergence: bond clock later than the equity cycle tag ---
    ORD = {"recession": 0, "early": 1, "mid": 2, "late": 3}
    eq_cycle = _equity_cycle(fr.index)
    if "spread_10y3m" in fr and "hy_pctile" in fr:
        hy_dir = np.where(fr["hy_oas"].diff(CREDIT_DIR_WINDOW) > 0, "widening", "tightening") \
            if "hy_oas" in fr else None
        phases = []
        for i, (cv, hp) in enumerate(zip(fr["spread_10y3m"], fr["hy_pctile"])):
            d = hy_dir[i] if hy_dir is not None else None
            phases.append(bonds._cycle_phase(cv if pd.notna(cv) else None,
                                              hp if pd.notna(hp) else None, d, bcfg["cycle"]))
        bphase = pd.Series(phases, index=fr.index)
        bo = bphase.map(ORD)
        eo = eq_cycle.map(ORD)
        out["cycle_divergence"] = ((bo - eo) > 0).astype(float).where(bo.notna() & eo.notna())
    return out


def _equity_cycle(idx: pd.DatetimeIndex) -> pd.Series:
    """The equity cycle_tag history from the persisted regime frame (causal)."""
    try:
        rh = pd.read_parquet(config.data_dir() / "regime" / "regime_history.parquet")
        rh.index = pd.to_datetime(rh.index)
        if "cycle" in rh.columns:
            return rh["cycle"].reindex(idx).ffill()
    except Exception:  # noqa: BLE001
        pass
    return pd.Series(index=idx, dtype=object)


def _binary_lift(flag: pd.Series, tgt: pd.DataFrame, base_mask: pd.Series | None = None) -> dict:
    """P(dd10 | flag) vs the base rate (optionally within a base_mask subset), with a
    block-bootstrap CI on the flagged dd10 rate."""
    j = pd.concat([flag.rename("flag"), tgt[["dd10", "dd_depth"]]], axis=1).dropna()
    if base_mask is not None:
        j = j[base_mask.reindex(j.index).fillna(False).astype(bool)]
    if len(j) < 120 or j["flag"].sum() < 30:
        return {"n": int(len(j)), "n_flagged": int(j["flag"].sum()) if len(j) else 0,
                "note": "too few observations / firings to measure"}
    on = j[j["flag"] == 1]
    base = float(j["dd10"].mean())
    p_on = float(on["dd10"].mean())
    boot = on["dd10"].to_numpy(float)
    rng = np.random.default_rng(11)
    nb = int(np.ceil(len(boot) / DD_WINDOW))
    means = []
    for _ in range(2000):
        starts = rng.integers(0, len(boot), nb)
        ix = (starts[:, None] + np.arange(DD_WINDOW)[None, :]).ravel()[:len(boot)] % len(boot)
        means.append(boot[ix].mean())
    ci = [round(float(np.percentile(means, p)), 3) for p in (2.5, 50, 97.5)]
    return {"n": int(len(j)), "n_flagged": int(on.shape[0]),
            "base_p_dd10": round(base, 3), "flagged_p_dd10": round(p_on, 3),
            "lift_pp": round((p_on - base) * 100, 1),
            "flagged_mean_dd_depth_pct": round(float(on["dd_depth"].mean()) * 100, 1),
            "base_mean_dd_depth_pct": round(float(j["dd_depth"].mean()) * 100, 1),
            "flagged_p_dd10_ci": ci,
            # honest read: a lift whose CI lower bound is still above base is the only
            # thing that would justify scoring it.
            "ci_excludes_base": bool(ci[0] > base)}


def main() -> int:
    split = pd.Timestamp((config.load()["bonds"].get("calibration") or {}).get("split_date", SPLIT_DEFAULT))
    f = inputs.build_features()
    fr = bonds.bonds_frame(f)
    sig = _reconstruct(fr, f)
    tgt = build_targets(fr.index)

    # Restrict to the window where the LEADING flags actually have DATA. The credit
    # (hy_oas) and rates-vol (move) inputs don't exist before the late-1990s/early-2000s;
    # over the full 1971+ bonds_frame span the pre-half would be padded with all-zero
    # flags, contaminating the split-half comparison. Rolling z-scores inside _reconstruct
    # already used the full history, so trimming the OUTPUT introduces no warm-up artifact.
    have = pd.Series(True, index=fr.index)
    for col in ("hy_oas", "move"):
        if col in fr:
            have &= fr[col].notna()
    start = have[have].index.min() if bool(have.any()) else fr.index.min()
    sig, tgt = sig.loc[start:], tgt.loc[start:]

    report = {"meta": {
        "split": str(split.date()), "dd_window_d": DD_WINDOW,
        "analysis_start": str(pd.Timestamp(start).date()),
        "question": "Does the cross-asset DIVERGENCE add INCREMENTAL forward-drawdown info "
                    "beyond the equity-side drawdown_risk gauge?",
        "note": "No look-ahead: signals = causal engine.bonds/conditions frames; target = "
                "strictly-forward 63d S&P drawdown. Analysis is restricted to the window where the "
                "credit (HY-OAS) and rates-vol (MOVE) inputs exist (else the pre-half is all-zero "
                "flags). The validated `lead_caution` construct = credit + rates-vol + un-inversion "
                "(a BOND-leading proxy); it is intentionally NOT byte-identical to the engine's "
                "risk-leg votes, and FX is excluded (literature: dollar/EM-FX risk-off is COINCIDENT, "
                "not leading — display-only by construction). The block-bootstrap CI resamples the "
                "flagged-only series, so it is an approximate (not calendar-contiguous) interval. "
                "Several `ci_excludes_base` tests are run, so treat a single marginal pass as weak "
                "(no formal FDR applied). CONFIRMED-to-score needs incremental edge after controlling "
                "for drawdown_risk AND a both-halves-meaningful split."}}

    # 1) lead_caution as a standalone stress signal vs forward drawdown (split-half)
    s = sig["lead_caution"]
    span = pd.concat([s, tgt["dd_depth"]], axis=1).dropna().index
    pre = span[span < split]
    pre = pre[:-DD_WINDOW] if len(pre) > DD_WINDOW else pre
    post = span[span >= split]
    ic_full = _spear(s.reindex(span), tgt["dd_depth"].reindex(span))
    ic_pre = _spear(s.reindex(pre), tgt["dd_depth"].reindex(pre))
    ic_post = _spear(s.reindex(post), tgt["dd_depth"].reindex(post))
    report["lead_caution"] = {
        "n": int(len(span)), "span": f"{span.min().date()}..{span.max().date()}" if len(span) else None,
        "ic_dd_full": round(ic_full, 3), "ic_dd_pre": round(ic_pre, 3), "ic_dd_post": round(ic_post, 3),
        "verdict_standalone": _verdict(ic_full, ic_pre, ic_post, None),
        "conditional": _conditional(s, tgt),
    }

    # 2) THE KEY TEST — partial Spearman of lead_caution vs forward dd, controlling for drawdown_risk
    pic_full, n_full = _partial_spear(s.reindex(span), tgt["dd_depth"].reindex(span), sig["dd_risk"].reindex(span))
    pic_pre, _ = _partial_spear(s.reindex(pre), tgt["dd_depth"].reindex(pre), sig["dd_risk"].reindex(pre))
    pic_post, _ = _partial_spear(s.reindex(post), tgt["dd_depth"].reindex(post), sig["dd_risk"].reindex(post))
    report["incremental_partial_ic"] = {
        "partial_ic_full": None if np.isnan(pic_full) else round(pic_full, 3),
        "partial_ic_pre": None if np.isnan(pic_pre) else round(pic_pre, 3),
        "partial_ic_post": None if np.isnan(pic_post) else round(pic_post, 3),
        "n": n_full,
        "interpretation": "partial Spearman(lead_caution, forward-dd | drawdown_risk). ~0 ⇒ "
                          "redundant with the gauge we already have (DISPLAY-ONLY confirmed).",
    }

    # 3) the divergence config: forward-dd lift WITHIN low-drawdown_risk days (the panel's headline
    # case). The `divergence` flag fires ONLY on calm-equity days, so the correct comparison base is
    # the calm-day base rate — hence base_mask=low_mask (an all-days base would be an apples-to-oranges
    # comparison and is deliberately not reported).
    low_mask = sig["dd_low"] == 1
    report["divergence_lift_within_calm"] = _binary_lift(sig["lead_caution"].ge(2).astype(float),
                                                         tgt, base_mask=low_mask)

    # 4) cycle divergence (bond clock later than equities) — forward-dd lift
    if "cycle_divergence" in sig:
        report["cycle_divergence_lift"] = _binary_lift(sig["cycle_divergence"], tgt)

    # 5) component flags standalone (which flag, if any, carries the signal)
    report["component_flags"] = {}
    for k in ("f_credit", "f_rates_vol", "f_uninv"):
        report["component_flags"][k] = _binary_lift(sig[k], tgt)

    # --- decision ---
    pic = report["incremental_partial_ic"]["partial_ic_full"]
    pic_pre_v = report["incremental_partial_ic"]["partial_ic_pre"]
    pic_post_v = report["incremental_partial_ic"]["partial_ic_post"]
    div = report["divergence_lift_within_calm"]
    incremental = (pic is not None and pic >= 0.05
                   and pic_pre_v is not None and pic_post_v is not None
                   and pic_pre_v >= 0.02 and pic_post_v >= 0.02)
    div_real = bool(div.get("ci_excludes_base")) and (div.get("lift_pp") or 0) > 0
    if incremental and div_real:
        decision = ("SCORE-CANDIDATE — the cross-asset caution count adds forward-drawdown "
                    "information beyond drawdown_risk in BOTH halves, and the divergence config "
                    "lifts the drawdown rate within calm-equity days (CI excludes base). Promote "
                    "ONE validated leg (e.g. MOVE into the RORO composite, or a divergence gate "
                    "into drawdown_risk) — and re-confirm on the next data refresh before adopting.")
    elif incremental or div_real:
        decision = ("MARGINAL — one of the two incremental tests passes but not both. Keep "
                    "DISPLAY-ONLY; revisit if it strengthens on more data. Do not score yet.")
    else:
        decision = ("DISPLAY-ONLY (confirmed) — the cross-asset caution count adds ~no forward-"
                    "drawdown information beyond the drawdown_risk gauge, and the divergence config "
                    "does not robustly lift the drawdown rate. This matches the literature (these "
                    "reads are largely COINCIDENT) and the bonds calibration (composite ≈ the "
                    "drawdown_risk leg alone). The confirmation panel stays a context/early-attention "
                    "read and is NEVER scored.")
    report["decision"] = decision

    outdir = config.data_dir() / "regime"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "cross_asset_confirm_phase0.json").write_text(
        json.dumps(report, indent=2, default=str, ensure_ascii=False))
    _write_md(report)
    print(_summary(report))
    return 0


def _summary(r: dict) -> str:
    L = ["\n=== Cross-Asset Confirmation — Phase-0 ===",
         f"split {r['meta']['split']} · target = forward {DD_WINDOW}d S&P drawdown"]
    lc = r["lead_caution"]
    L.append(f"\nlead_caution standalone: IC dd full/pre/post = "
             f"{lc['ic_dd_full']}/{lc['ic_dd_pre']}/{lc['ic_dd_post']}  ({lc['verdict_standalone']})")
    pic = r["incremental_partial_ic"]
    L.append(f"INCREMENTAL partial IC | drawdown_risk: full/pre/post = "
             f"{pic['partial_ic_full']}/{pic['partial_ic_pre']}/{pic['partial_ic_post']}  (n={pic['n']})")
    d = r["divergence_lift_within_calm"]
    if "flagged_p_dd10" in d:
        L.append(f"divergence within calm-equity days: P(dd10) {d['flagged_p_dd10']} vs base "
                 f"{d['base_p_dd10']} ({d['lift_pp']:+}pp) CI {d.get('flagged_p_dd10_ci')} "
                 f"excludes base={d.get('ci_excludes_base')}")
    else:
        L.append(f"divergence within calm-equity days: {d.get('note','—')}")
    cd = r.get("cycle_divergence_lift", {})
    if "flagged_p_dd10" in cd:
        L.append(f"cycle divergence (bonds later): P(dd10) {cd['flagged_p_dd10']} vs base "
                 f"{cd['base_p_dd10']} ({cd['lift_pp']:+}pp)")
    L.append("\nDECISION: " + r["decision"])
    return "\n".join(L)


def _write_md(r: dict) -> None:
    m = r["meta"]
    lc = r["lead_caution"]
    pic = r["incremental_partial_ic"]
    L = ["# Cross-Asset Confirmation — Phase-0 validation", "",
         f"Split-half **{m['split']}** · target: forward **{DD_WINDOW}-day** S&P max drawdown "
         "(and P(≥10% drawdown)).", "", f"**Question.** {m['question']}", "", m["note"], "",
         "## 1 · `lead_caution` (0–3 bond leading flags) vs forward drawdown", "",
         f"- IC(stress, forward dd-depth) full / pre / post = **{lc['ic_dd_full']} / "
         f"{lc['ic_dd_pre']} / {lc['ic_dd_post']}** → standalone **{lc['verdict_standalone']}**.",
         f"- span {lc.get('span')}, n {lc['n']}.", "",
         "## 2 · The decisive test — incremental partial IC (controlling for `drawdown_risk`)", "",
         f"Partial Spearman(`lead_caution`, forward-dd | `drawdown_risk`): full **{pic['partial_ic_full']}**, "
         f"pre **{pic['partial_ic_pre']}**, post **{pic['partial_ic_post']}** (n {pic['n']}).", "",
         f"_{pic['interpretation']}_", "",
         "## 3 · The divergence config (panel headline: leading caution while equities calm)", ""]
    d = r["divergence_lift_within_calm"]
    if "flagged_p_dd10" in d:
        L.append(f"Within **low-drawdown_risk** days, `lead_caution ≥ 2` → P(dd10) **{d['flagged_p_dd10']}** "
                 f"vs base **{d['base_p_dd10']}** ({d['lift_pp']:+}pp); bootstrap CI {d['flagged_p_dd10_ci']} "
                 f"— excludes base: **{d['ci_excludes_base']}** (n {d['n']}, firings {d['n_flagged']}).")
    else:
        L.append(f"_{d.get('note','—')}_")
    cd = r.get("cycle_divergence_lift", {})
    if "flagged_p_dd10" in cd:
        L += ["", "## 4 · Cycle divergence (bond clock later than equities)", "",
              f"`cycle_divergence` → P(dd10) **{cd['flagged_p_dd10']}** vs base **{cd['base_p_dd10']}** "
              f"({cd['lift_pp']:+}pp), n {cd['n']}, firings {cd['n_flagged']}."]
    L += ["", "## 5 · Component flags (standalone forward-dd lift)", "",
          "| flag | n | firings | P(dd10) flagged | base | lift (pp) | CI excludes base |",
          "|---|--:|--:|--:|--:|--:|---|"]
    for k, c in r.get("component_flags", {}).items():
        if "flagged_p_dd10" in c:
            L.append(f"| {k} | {c['n']} | {c['n_flagged']} | {c['flagged_p_dd10']} | {c['base_p_dd10']} | "
                     f"{c['lift_pp']:+} | {c.get('ci_excludes_base')} |")
        else:
            L.append(f"| {k} | — | — | — | — | — | {c.get('note','too few')} |")
    L += ["", "## Decision", "", f"**{r['decision']}**", "",
          "_Honesty bar: this is the gate that decides whether the cross-asset confirmation read "
          "is allowed to feed a score. Display-only unless the incremental edge is real and holds "
          "on both halves — and even then, only after a re-confirm on the next data refresh._"]
    Path(config.load()["storage"]["reports_dir"], "cross-asset-confirm-phase0.md").write_text("\n".join(L))


if __name__ == "__main__":
    sys.exit(main())
