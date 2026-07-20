"""DISCOVERY / scan layer — admit pre-consensus names the five desks MISS.

The Intelligence Hub's universe is the set-union of names the feeders already
surfaced (engine/intelligence.py) — every feeder is a recognition gate, so a name
that nobody is writing about, that isn't on a buy-list, and whose tape hasn't
diverged is invisible by construction. This module scans LEADING sources directly
for OFF-DESK candidates and hands them to the hub so accumulation can surface
BEFORE a lagging desk flags it.

Two feeds (both already collected, neither consumed by the hub today):

  • RADAR QUIET-but-accumulating — the divergence radar computes a full signal
    (signal_score / channels / crowd / options / activity) for QUIET names too,
    then engine.intelligence DROPS them (`_radar_for` returns None on QUIET). A
    QUIET name with a real, multi-channel, uncrowded, not-extended signal is
    accumulation before a divergence forms — exactly the pre-consensus setup.

  • FEDERAL contract-award VELOCITY — data/usaspending/obligations.parquet is a
    dates × tickers matrix of obligated $ for ~41 federal-exposed names with the
    ticker crosswalk already resolved (curated, narrow by design). Accelerating
    obligated $ = funded backlog → revenue over 1-4q, before the tape prices it.

CONTEXT-ONLY · DEGRADE-NEVER-RAISE · PURE (load_* read artifacts). Nothing here
scores or sizes; it republishes leading signals the hub was throwing away.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "intel_discovery.v1"


def _f(x):
    if x is None or isinstance(x, (dict, list, bool)):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


# --------------------------------------------------------------------------- #
# Feed 1 — radar QUIET-but-accumulating
# --------------------------------------------------------------------------- #
# channels that are genuinely LEADING (smart-money / catalyst / activity), so two
# of them firing under a quiet tape is real corroboration, not noise.
_LEADING_CHANNELS = {
    "13f_add", "congress_buy", "insider_cluster", "insider_buy", "material_8k",
    "clinical_phase3_start", "fda_label_expansion", "fda_approval", "gov_grant",
    "gov_contract", "patent_cluster", "affiliation", "unusual_options",
    "analyst_upgrade_cluster", "earnings_beat", "github_momentum", "hf_model_momentum",
}


def scan_radar_quiet(radar_tickers: list | None, min_signal: float = 45.0,
                     min_channels: int = 2) -> list[dict]:
    """QUIET radar names with a real, multi-channel, uncrowded, not-extended signal —
    accumulation before a divergence forms. Returns scored candidates, strongest first."""
    out: list[dict] = []
    for r in (radar_tickers or []):
        if not isinstance(r, dict) or r.get("state") != "QUIET":
            continue
        sig = _f(r.get("signal_score"))
        if sig is None or sig < min_signal:
            continue
        channels = [c for c in (r.get("channels") or []) if isinstance(c, str)]
        leading = [c for c in channels if c in _LEADING_CHANNELS]
        if len(leading) < min_channels:                 # need ≥2 independent leading legs
            continue
        if r.get("extended") is True:                   # anti-chase
            continue
        # radar_plus._crowd_penalty emits a 0–15 scale (5·dark-pool-dist + 4·wsb); normalize to 0–1
        crowd_pen = (_f((r.get("crowd") or {}).get("penalty")) or 0.0) / 15.0
        if crowd_pen > 0.25:                            # already crowded → not stealth
            continue
        opt = (r.get("options") or {}).get("lean")
        opt_lean = opt if isinstance(opt, (int, float)) else 0
        activity = _f(r.get("activity")) or 0.0
        rs = _f(r.get("rs_vs_spy_60d"))

        # accumulation score 0-1: signal magnitude + leading-channel breadth + uncrowded
        # + options call-lean + some activity, with a haircut for a big prior run-up.
        breadth = _clamp01(len(leading) / 4.0)
        runup_haircut = 1.0 if (rs is None or rs <= 0) else _clamp01(1.0 - rs / 120.0)
        score = (0.42 * _clamp01((sig - 40.0) / 50.0)
                 + 0.26 * breadth
                 + 0.12 * _clamp01(1.0 - crowd_pen / 0.25)
                 + 0.10 * (0.5 + 0.5 * max(-1, min(1, opt_lean)))
                 + 0.10 * _clamp01(activity))
        score = round(_clamp01(score * (0.6 + 0.4 * runup_haircut)), 3)

        reasons = []
        if len(leading) >= 2:
            reasons.append(" + ".join(c.replace("_", " ") for c in leading[:3]))
        if opt_lean and opt_lean > 0:
            reasons.append("options call-leaning")
        if crowd_pen <= 0.05:
            reasons.append("uncrowded")
        out.append({
            "ticker": (r.get("ticker") or "").upper(), "source": "radar_quiet",
            "disc_score": score, "signal_score": sig, "edge_score": _f(r.get("edge_score")),
            "channels": leading[:5], "n_channels": len(leading),
            "rs_vs_spy_60d": rs, "options_lean": opt_lean, "activity": round(activity, 2),
            "reason": "; ".join(reasons) or "multi-channel signal under a quiet tape",
            "note": r.get("note"),
        })
    out.sort(key=lambda d: d["disc_score"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# Feed 2 — federal contract-award velocity (funded backlog)
# --------------------------------------------------------------------------- #
def scan_federal_velocity(obligations, recent: int = 3, base: int = 6,
                          min_recent_usd: float = 2.0e6, prior_floor: float = 2.5e5) -> list[dict]:
    """Per-ticker obligated-$ ACCELERATION: trailing-`recent`-period sum vs the prior
    `base`-period average. A FLOW (never forward-filled). obligations = a DataFrame
    indexed by date with one obligated-$ column per ticker.

    Federal CONTRACT awards are LUMPY — a single prime award lands entirely in one month
    and would otherwise read as a giant 'acceleration'. We therefore (a) detect single-month
    concentration (peak_share) and cap + flag it as a one-off award (not a sustained ramp),
    (b) require a real prior baseline before grading an acceleration, and (c) LOG-COMPRESS the
    acceleration so +150% and +3800% don't score identically. Degrades to [] without pandas/data."""
    import math
    out: list[dict] = []
    try:
        if obligations is None or getattr(obligations, "empty", True):
            return out
        df = obligations.sort_index()
        cols = list(df.columns)
    except Exception as e:  # noqa: BLE001
        log.debug("federal velocity: bad frame (%s)", e)
        return out
    if len(df) < recent + 2:
        return out
    for tk in cols:
        try:
            s = df[tk].fillna(0.0).astype(float)
        except Exception:  # noqa: BLE001
            continue
        rec = s.iloc[-recent:]
        recent_sum = float(rec.sum())
        if recent_sum < min_recent_usd:
            continue
        prior = s.iloc[-(recent + base):-recent]
        prior_avg = float(prior.mean()) if len(prior) else 0.0
        nonzero_prior = int((prior > 0).sum())
        recent_avg = recent_sum / float(recent)
        peak_share = (float(rec.max()) / recent_sum) if recent_sum > 0 else 1.0
        lumpy = peak_share > 0.8                            # one month dominates → a one-off award

        if prior_avg < prior_floor or nonzero_prior < 2:   # no usable baseline → can't grade a ramp
            accel = None
            score = 0.40                                    # provisional flow, not a graded acceleration
        else:
            accel = round((recent_avg - prior_avg) / prior_avg, 2)
            if accel <= 0:
                continue                                    # decelerating → not a discovery
            # log-compressed: knee ~+150%, saturates gently so a lumpy 3800% ≠ a real 150% ramp
            score = _clamp01(0.30 + 0.45 * _clamp01(math.log1p(accel) / math.log1p(2.5)))
        if lumpy:
            score = min(score, 0.50)                        # a single award can't be a top-tier discovery

        if accel is None:
            reason = "new / sparse federal obligated-$ flow"
        elif lumpy:
            reason = "one large federal award (lumpy — not a sustained ramp)"
        else:
            pct = min(int(accel * 100), 1000)               # never display absurd magnitudes
            reason = f"federal obligated $ accelerating {pct}%{'+' if accel > 10 else ''} vs prior run-rate"
        out.append({
            "ticker": (tk or "").upper(), "source": "federal_velocity",
            "disc_score": round(score, 3), "accel": accel, "lumpy": lumpy,
            "peak_share": round(peak_share, 2),
            "recent_usd": round(recent_sum, 0), "prior_avg_usd": round(prior_avg, 0),
            "reason": reason,
        })
    out.sort(key=lambda d: (d["disc_score"], d["recent_usd"]), reverse=True)
    return out


# --------------------------------------------------------------------------- #
# Feed 3 — insider opportunistic-cluster buying (a CONFIRMER, not an alpha)
# --------------------------------------------------------------------------- #
import re as _re

_TICKER_OK = _re.compile(r"^[A-Z]{1,5}$")
_JUNK_TICKERS = {"NONE", "NULL", "NA", "NAN", "TBD", "N"}     # SEC bulk-data sentinels, not tickers
_ROLE_OFFICER, _ROLE_DIRECTOR, _ROLE_TENPCT = 1.0, 0.6, 0.4
# insider clusters are a LAGGING confirmer (quarterly bulk panel) — capped well below the
# leading feeds (radar_quiet up to ~0.9) so they surface in Discovery but never out-rank a lead.
_INSIDER_CAP = 0.45


def scan_insider_clusters(panel, recent_days: int = 90, min_buyers: int = 3,
                          min_usd: float = 2.5e5) -> list[dict]:
    """Clusters of DISTINCT insiders making OPEN-MARKET purchases (Form-4 code 'P', the
    opportunistic/non-routine trade — grants and option-exercises are excluded), role-weighted.
    The decomposed cluster (NOT naive net-$, which is folklore). HONEST CAVEAT: the bulk SEC
    panel is quarterly and lags ~1 quarter, so this is a lagging CONFIRMER (capped score), never
    a lead. panel = a DataFrame with columns ticker/trans_date/code/rptownercik/usd/is_officer/
    is_director/is_tenpct. Degrades to [] without pandas/data."""
    out: list[dict] = []
    try:
        import pandas as pd
        if panel is None or getattr(panel, "empty", True):
            return out
        df = panel.copy()
        df["trans_date"] = pd.to_datetime(df["trans_date"], errors="coerce")
        mx = df["trans_date"].max()
        if pd.isna(mx):
            return out
        buys = df[(df["code"] == "P") & (df["usd"] > 0)
                  & (df["trans_date"] >= mx - pd.Timedelta(days=recent_days))]
        if buys.empty:
            return out
        lag_days = None
        try:
            lag_days = int((pd.Timestamp(date.today()) - mx).days)
        except Exception:  # noqa: BLE001
            lag_days = None
        for tk, g in buys.groupby("ticker"):
          try:                                            # one bad group must not abort the scan
            t = str(tk).upper().strip()
            if not _TICKER_OK.match(t) or t in _JUNK_TICKERS:   # drop NONE / blanks / numeric junk
                continue
            opp_buyers = int(g["rptownercik"].nunique())
            usd = float(g["usd"].sum())
            if opp_buyers < min_buyers or usd < min_usd:
                continue
            officer_led = bool(g.get("is_officer").any()) if "is_officer" in g else False
            breadth = _clamp01((opp_buyers - 2) / 6.0)
            usd_score = _clamp01(math.log1p(usd) / math.log1p(5.0e6))
            score = min(_INSIDER_CAP, 0.50 * breadth + 0.30 * (1.0 if officer_led else 0.6) + 0.20 * usd_score)
            out.append({
                "ticker": t, "source": "insider_cluster",
                "disc_score": round(score, 3), "opp_buyers": opp_buyers,
                "usd": round(usd, 0), "officer_led": officer_led, "lag_days": lag_days,
                "reason": (f"{opp_buyers} insiders bought open-market"
                           + (" (officer-led)" if officer_led else "")
                           + (f" · {lag_days}d-lagged filing" if lag_days else "")),
            })
          except Exception:  # noqa: BLE001 — skip a malformed group, keep the good ones
            continue
        out.sort(key=lambda d: (d["disc_score"], d["opp_buyers"]), reverse=True)
    except Exception as e:  # noqa: BLE001
        log.debug("insider cluster scan failed (%s)", e)
    return out


def _read_insider_panel():
    """Load the most-recent SEC insider panel quarters (the rich per-transaction Form-4 grid)."""
    try:
        import glob
        import pandas as pd
        files = sorted(glob.glob(str(config.ROOT / "data" / "sec_insider" / "panel" / "*.parquet")))
        if not files:
            return None
        return pd.concat([pd.read_parquet(f) for f in files[-2:]], ignore_index=True)
    except Exception as e:  # noqa: BLE001
        log.debug("insider panel read failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# Feed 4 — activist beneficial-ownership (Schedule 13D initiation / 13G→13D flip)
# --------------------------------------------------------------------------- #
# An activist 13D is a hard, dated smart-money event — the filer has crossed 5% with
# CONTROL intent (board seats / breakup / sale), which the literature (Brav-Jiang-
# Partnoy-Thomas 2008) shows underreacts initially. It IS leading (the stake is fresh),
# but slightly lagged by the ≤5-biz-day filing window, and event-sparse — so it's a
# CONFIRMER. The cap is raised to the LEADING tier only if the post-2024 event study
# (scripts/validate_activist_ownership.py) certified the drift; else it's a measuring
# confirmer capped like insiders. The custodian/index-aggregation guard already lives
# in engine.beneficial_ownership (only state ∈ {activist, flip} reach here).
_ACTIVIST_CAP_SCORED = 0.62      # validated leading event (still below radar_quiet ~0.9)
_ACTIVIST_CAP_MEASURING = 0.45   # not-yet-validated confirmer (insider tier)
_ACTIVIST_FRESH_DAYS = 63        # coherent with the ≤63d drift window — a stale 13D isn't a discovery


_ACTIVIST_MAX_EMIT = 20          # a curated discovery surface, not the full 13D firehose


def scan_activist_ownership(regime: dict | None, gate: dict | None = None,
                            today: date | None = None,
                            fresh_days: int = _ACTIVIST_FRESH_DAYS,
                            max_emit: int = _ACTIVIST_MAX_EMIT) -> list[dict]:
    """Per-ticker activist-ownership candidates from the beneficial-ownership regime map
    ({ticker: {state, signal, n_13d, is_flip, latest_date, latest_filer, ...}}). Only the
    HIGH-signal escalations — activist 13D and 13G→13D flips by a NON-custodian filer —
    surface (passive/custodial dropped upstream + here). `gate` is the event-study verdict
    (data/beneficial_ownership/validation_gate.json); a SCORED gate lifts the cap to the
    leading tier. US 13D base-rate is high, so only the freshest/strongest `max_emit` are
    emitted (the count available is logged, not silently hidden). PURE."""
    import pandas as pd
    out: list[dict] = []
    if not regime:
        return out
    today = today or date.today()
    scored = bool((gate or {}).get("scored"))
    lead_h = (gate or {}).get("lead_horizon")
    cap = _ACTIVIST_CAP_SCORED if scored else _ACTIVIST_CAP_MEASURING
    for tk, reg in regime.items():
        if not isinstance(reg, dict) or reg.get("signal") != "high":
            continue                                    # only activist / flip escalations
        if reg.get("latest_filer_type") == "passive_giant":
            continue                                    # custodian/index 13D = aggregation, not activism
        t = (tk or "").upper().strip()
        if not _TICKER_OK.match(t) or t in _JUNK_TICKERS:
            continue
        # recency — a fresh stake; drop stale filings (drift is captured in ≤63d)
        age_days = None
        try:
            ld = pd.to_datetime(reg.get("latest_date"), errors="coerce")
            if pd.notna(ld):
                age_days = int((pd.Timestamp(today) - ld).days)
        except Exception:  # noqa: BLE001
            age_days = None
        if age_days is not None and age_days > fresh_days:
            continue
        is_flip = bool(reg.get("is_flip"))
        n_13d = int(reg.get("n_13d") or 0)
        # within the cap: a 13G→13D flip (the highest-signal escalation, Brav-Jiang) earns
        # near the cap; a single plain activist 13D sits a tier below; fresher = stronger;
        # multiple 13D filers = a real campaign, not a single dabble.
        base = 1.0 if is_flip else 0.78
        recency = 1.0 if age_days is None else _clamp01(1.0 - age_days / float(max(fresh_days, 1)))
        campaign = _clamp01((n_13d - 1) / 3.0)
        score = round(cap * _clamp01(0.62 * base + 0.28 * recency + 0.10 * campaign), 3)

        filer = reg.get("latest_filer")
        filer_txt = f" ({filer})" if filer and str(filer).lower() != "none" else ""
        kind = "13G→13D flip — escalation to active" if is_flip else "activist 13D"
        age_txt = f" {age_days}d ago" if age_days is not None else ""
        tag = (f"validated leading event (peak {lead_h}d drift)" if scored
               else "measuring — not yet event-study-validated")
        out.append({
            "ticker": t, "source": "activist_ownership",
            "disc_score": score, "state": reg.get("state"), "is_flip": is_flip,
            "n_13d": n_13d, "age_days": age_days, "latest_filer": filer,
            "validated": scored, "lead_horizon": lead_h if scored else None,
            "reason": (f"{kind}{filer_txt} filed{age_txt} · {tag}"
                       " · ≤5-biz-day filing lag"),
        })
    out.sort(key=lambda d: (d["disc_score"], d.get("n_13d") or 0), reverse=True)
    if len(out) > max_emit:
        log.info("activist_ownership: %d fresh activist names, emitting top %d", len(out), max_emit)
        out = out[:max_emit]
    return out


def _load_activist_gate() -> dict | None:
    """The post-2024 13D event-study verdict (degrade to None → 'measuring')."""
    try:
        import json
        p = config.ROOT / "data" / "beneficial_ownership" / "validation_gate.json"
        return json.loads(p.read_text()) if p.exists() else None
    except Exception as e:  # noqa: BLE001
        log.debug("activist gate read failed (%s)", e)
        return None


def _read_ownership_regime() -> dict | None:
    try:
        from engine.beneficial_ownership import load_regime
        return load_regime() or None
    except Exception as e:  # noqa: BLE001
        log.debug("ownership regime read failed (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# Feed 5 — index-reconstitution forced flow (gate-controlled; dormant until validated)
# --------------------------------------------------------------------------- #
# A name ADDED to the S&P 500/400/600 is force-bought by index funds — a mechanical,
# leading flow. BUT the classic index effect (Shleifer 1986) is widely documented to
# have DECAYED post-2010 (crowded + patient execution), so this leg ships OFF and only
# activates if scripts/validate_index_reconstitution.py certifies a tradeable
# post-effective ADD drift on the modern regime. Deletes are forced SELLING (a name to
# avoid) — never surfaced as a long discovery.
_RECON_CAP = 0.55
_RECON_FRESH_DAYS = 15           # only names added within the last ~3 trading weeks
_INDEX_TIER = {"sp500": 1.0, "sp400": 0.72, "sp600": 0.55, "r2000": 0.45}


def scan_index_reconstitution(changes: list | None, gate: dict | None = None,
                              today: date | None = None,
                              fresh_days: int = _RECON_FRESH_DAYS) -> list[dict]:
    """Fresh S&P index ADDITIONS as forced-flow discovery candidates. GATE-CONTROLLED:
    returns [] (dormant) unless the event study certified a tradeable post-effective add
    drift (gate['add_scored']) — the honest default, since the effect has largely decayed.
    `changes` = [{ticker, d (effective ISO date), kind, index}]. PURE."""
    import pandas as pd
    out: list[dict] = []
    if not changes or not (gate or {}).get("add_scored"):
        return out                                  # decayed/unvalidated → no scoring injection
    today = today or date.today()
    for ch in changes:
        if not isinstance(ch, dict) or ch.get("kind") != "add":
            continue
        t = (ch.get("ticker") or "").upper().strip()
        if not _TICKER_OK.match(t) or t in _JUNK_TICKERS:
            continue
        age = None
        try:
            d = pd.to_datetime(ch.get("d"), errors="coerce")
            if pd.notna(d):
                age = int((pd.Timestamp(today) - d).days)
        except Exception:  # noqa: BLE001
            age = None
        if age is None or age < 0 or age > fresh_days:
            continue
        ix = ch.get("index")
        tier = _INDEX_TIER.get(ix, 0.5)
        recency = _clamp01(1.0 - age / float(max(fresh_days, 1)))
        score = round(_RECON_CAP * (0.6 * tier + 0.4 * recency), 3)
        out.append({
            "ticker": t, "source": "index_reconstitution",
            "disc_score": score, "index": ix, "age_days": age,
            "reason": (f"added to {str(ix).upper().replace('SP', 'S&P ')} {age}d ago"
                       " · forced index-fund buying (validated post-effective drift)"),
        })
    out.sort(key=lambda d: (d["disc_score"], -(d.get("age_days") or 0)), reverse=True)
    return out


def _read_recent_index_changes(today: date | None = None,
                               lookback_days: int = 21) -> list[dict]:
    """Recent S&P 500/400/600 add & delete events from the PIT membership history."""
    try:
        import pandas as pd
        p = config.ROOT / "data" / "breadth" / "sp1500_pit_membership.parquet"
        if not p.exists():
            return []
        pit = pd.read_parquet(p)
        today = today or date.today()
        cut = pd.Timestamp(today) - pd.Timedelta(days=lookback_days)
        out = []
        for col, kind in (("start_date", "add"), ("end_date", "delete")):
            sub = pit.dropna(subset=[col]).copy()
            sub["_d"] = pd.to_datetime(sub[col], errors="coerce")
            sub = sub[sub["_d"] >= cut]
            for r in sub.itertuples(index=False):
                out.append({"ticker": str(r.ticker).upper(), "d": str(r._d.date()),
                            "kind": kind, "index": str(r.src)})
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("index-change read failed (%s)", e)
        return []


def _load_recon_gate() -> dict | None:
    try:
        import json
        p = config.ROOT / "data" / "index_reconstitution" / "validation_gate.json"
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# build — merge feeds, mark which candidates are OFF-desk (not in the hub universe)
# --------------------------------------------------------------------------- #
def build(radar_tickers: list | None, obligations=None, insider=None,
          bundle_universe: set | None = None, today: date | None = None,
          ownership=None, ownership_gate=None,
          index_changes=None, recon_gate=None) -> dict:
    """Scan the leading feeds and return discovery candidates keyed by ticker, each tagged
    off_desk (not already in the hub's bundle universe) or on_desk (a corroborating boost).
    Never raises."""
    today = today or date.today()
    universe = {(t or "").upper() for t in (bundle_universe or set())}
    quiet = scan_radar_quiet(radar_tickers)
    fed = scan_federal_velocity(obligations)
    ins = scan_insider_clusters(insider)
    act = scan_activist_ownership(ownership, ownership_gate, today)
    recon = scan_index_reconstitution(index_changes, recon_gate, today)

    by_ticker: dict[str, dict] = {}
    for c in quiet + fed + ins + act + recon:
        t = c["ticker"]
        if not t:
            continue
        cur = by_ticker.get(t)
        if cur is None or c["disc_score"] > cur["disc_score"]:
            by_ticker[t] = {**c, "off_desk": t not in universe}
        else:                                            # keep the best, note the 2nd source
            cur.setdefault("also", []).append(c["source"])
    # secondary magnitude key so ties at a capped disc_score (esp. insider 0.45) keep the
    # STRONGEST by breadth/$/channels, not an arbitrary alphabetical subset at the cap boundary
    def _mag(d):
        return (d.get("opp_buyers") or d.get("recent_usd") or d.get("n_channels")
                or d.get("n_13d") or 0)
    cands = sorted(by_ticker.values(), key=lambda d: (d["disc_score"], _mag(d)), reverse=True)
    off_desk = [c for c in cands if c["off_desk"]]
    return {
        "schema": SCHEMA, "is_context_only": True, "as_of": today.isoformat(),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "by_ticker": by_ticker,
        "candidates": cands,
        "off_desk": off_desk,
        "n": len(cands), "n_off_desk": len(off_desk),
        "sources": {"radar_quiet": len(quiet), "federal_velocity": len(fed),
                    "insider_cluster": len(ins), "activist_ownership": len(act),
                    "index_reconstitution": len(recon)},
    }


def _read_obligations():
    try:
        import pandas as pd
        p = config.ROOT / "data" / "usaspending" / "obligations.parquet"
        return pd.read_parquet(p) if p.exists() else None
    except Exception as e:  # noqa: BLE001
        log.debug("intel_discovery: obligations read failed (%s)", e)
        return None


def load_and_build(bundle_universe: set | None = None, today: date | None = None) -> dict:
    """Read the radar + federal artifacts and build the discovery feed. Never raises."""
    import json
    radar = None
    try:
        p = config.ROOT / "site" / "basketdata" / "radar_ticker.json"
        if p.exists():
            radar = (json.loads(p.read_text()) or {}).get("tickers")
    except Exception as e:  # noqa: BLE001
        log.warning("intel_discovery: radar read failed (%s)", e)
    return build(radar, _read_obligations(), _read_insider_panel(), bundle_universe, today,
                 ownership=_read_ownership_regime(), ownership_gate=_load_activist_gate(),
                 index_changes=_read_recent_index_changes(today), recon_gate=_load_recon_gate())
