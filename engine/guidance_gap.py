"""Guidance-gap tilt — T3 of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md + research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md).

THE IDEA. T3 sits between T2 (customer demand) and T4 (revision breadth): *has management
pre-signaled versus the bar the market set?* The clean numeric gap (guidance − whisper)
needs a paywalled expectation series, but the LANGUAGE side is free and genuinely LEADING:
when a company files an off-cycle 8-K that says "raising our guidance", that sentence hits
the wire BEFORE the consensus revision (T4) catches up. So a RAISE-tilted theme with FLAT
revision breadth is a pre-revision flag — the T3 read that should precede a BROADENING T4.

We roll collectors/edgar_guidance.py's directional 8-K hits (data/edgar/guidance_hits.parquet;
cols ticker, direction raise|cut, phrase, file_date) up to each curated theme in config
`themes:`. A theme needs >=MIN_FILERS distinct filers to leave NEUTRAL (no single-name
overfit). Bands: CUTTING / NEUTRAL / RAISING / BROAD-RAISE. DISPLAY-ONLY; the cascade reads
this as a leading CONFIRMER on the rationale + an acceleration input to the 0-100 score, it
is NOT a stage-changer (stage stays T1×T4×exit-risk). Returns None cleanly when the
collector hasn't run (then the cascade is unchanged).

HONEST LIMITS. Phrase matching has no sentence-level negation handling; this is a coarse
directional BAND, never a numeric beat/miss. The numeric gap and the off-cycle Item-2.02
refinement (front-running one's own print) are the paid / LLM-layer upgrades.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

RECENT_DAYS = 90           # window for the CURRENT tilt (parquet may accrue older rows)
MIN_FILERS = 2             # distinct filers required before a theme leaves NEUTRAL
BROAD_RAISERS = 3          # >= this many distinct raisers (and raise-led) = BROAD-RAISE

WEIGHTS = {"guidance_band": "raise/cut tilt of member 8-K guidance language (last 90d)",
           "net": "distinct raisers - distinct cutters",
           "n_raisers/n_cutters": "distinct member filers pre-signaling up / down"}


def _hits() -> pd.DataFrame | None:
    p = config.data_dir() / "edgar" / "guidance_hits.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("guidance_hits unreadable: %s", e)
        return None
    if (df is None or df.empty or "ticker" not in df.columns
            or "direction" not in df.columns or "file_date" not in df.columns):
        return None
    return df


def _band(n_raisers: int, n_cutters: int) -> str:
    """Directional tilt band. >=MIN_FILERS distinct filers required to leave NEUTRAL."""
    if n_raisers + n_cutters < MIN_FILERS:
        return "NEUTRAL"                                   # too thin to call a tilt
    if n_raisers >= MIN_FILERS and n_raisers > n_cutters:
        return "BROAD-RAISE" if n_raisers >= BROAD_RAISERS else "RAISING"
    if n_cutters >= MIN_FILERS and n_cutters > n_raisers:
        return "CUTTING"
    return "NEUTRAL"                                       # balanced / mixed


def _theme_guidance(name: str, member_hits: pd.DataFrame) -> dict | None:
    """Roll a member-filtered hit frame up to one theme dict. None if no hits.

    A ticker that appears more than once is resolved to its MOST RECENT direction, so a
    name that cut last quarter and raised this quarter counts once, as a raiser."""
    if member_hits is None or member_hits.empty:
        return None
    h = member_hits.copy()
    h["file_date"] = pd.to_datetime(h["file_date"], errors="coerce")
    h = h.dropna(subset=["file_date"])
    if h.empty:
        return None
    # latest direction per ticker
    latest = (h.sort_values("file_date").groupby("ticker").tail(1))
    raisers = sorted(latest.loc[latest["direction"] == "raise", "ticker"].astype(str).unique())
    cutters = sorted(latest.loc[latest["direction"] == "cut", "ticker"].astype(str).unique())
    n_r, n_c = len(raisers), len(cutters)
    band = _band(n_r, n_c)
    recent = []
    for _, r in h.sort_values("file_date", ascending=False).head(6).iterrows():
        recent.append({"ticker": str(r["ticker"]), "direction": str(r["direction"]),
                       "phrase": str(r.get("phrase", "")),
                       "file_date": r["file_date"].date().isoformat()})
    return {
        "name": name,
        "guidance_band": band,
        "n_raisers": n_r,
        "n_cutters": n_c,
        "net": n_r - n_c,
        "raisers": raisers[:8],
        "cutters": cutters[:8],
        "asof": h["file_date"].max().date().isoformat(),
        "recent": recent,
    }


def compute_guidance_gap(write_ledger: bool = True,
                         hits: pd.DataFrame | None = None) -> dict | None:
    """Per-theme guidance-language tilt over config `themes:`. DISPLAY-ONLY.

    Returns None when the guidance-hits cache is absent (collector hasn't run) — the
    cascade then runs unchanged on T1×T2×T4."""
    df = _hits() if hits is None else hits
    if (df is None or df.empty or "ticker" not in df.columns
            or "direction" not in df.columns or "file_date" not in df.columns):
        return None
    df = df.copy()
    df["file_date"] = pd.to_datetime(df["file_date"], errors="coerce")
    df = df.dropna(subset=["file_date"])
    cutoff = pd.Timestamp(date.today() - timedelta(days=RECENT_DAYS))
    df = df[df["file_date"] >= cutoff]
    if df.empty:
        return None

    themes = (config.load() or {}).get("themes") or {}
    if not themes:
        return None
    out: dict[str, dict] = {}
    for key, spec in themes.items():
        members = set(spec.get("tickers") or [])
        if not members:
            continue
        mh = df[df["ticker"].isin(members)]
        try:
            r = _theme_guidance(spec.get("name", key), mh)
        except Exception as e:  # noqa: BLE001 — one theme failing never blocks the rest
            log.warning("guidance_gap[%s] failed: %s", key, e)
            r = None
        if r is not None:
            out[key] = r
    if not out:
        return None

    payload = {
        "asof": str(df["file_date"].max().date()),
        "n_themes": len(out),
        "window_days": RECENT_DAYS,
        "themes": out,
        "weights": WEIGHTS,
        "note": ("display-only; T3 guidance-gap LANGUAGE leg — 8-K 'raising/lowering "
                 "guidance' language leads the consensus revision (T4) by days-to-weeks. "
                 "Coarse directional band, not a numeric beat/miss; >=2 filers to leave "
                 "NEUTRAL. The numeric gap (vs whisper) is the paid upgrade."),
    }
    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001 — logging is never fatal
            log.warning("guidance_gap ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict) -> None:
    """Append-only forward-grading ledger: one row per (theme, asof) for a non-NEUTRAL
    tilt — graded forward (did a RAISING/BROAD-RAISE tilt precede a rise in T4 revision
    breadth / basket outperformance? did CUTTING precede the opposite?). Deduped."""
    d = config.data_dir() / "guidance_gap"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("theme"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue
    ts = datetime.now(timezone.utc).isoformat()
    lines = []
    for key, t in payload["themes"].items():
        # key off the THEME's own latest filing date, so a tilt is re-logged only when that
        # theme itself gets a fresh filing (not when any unrelated theme advances the global asof)
        asof = t.get("asof") or payload.get("asof")
        if t["guidance_band"] == "NEUTRAL" or (key, asof) in seen:
            continue
        lines.append(json.dumps({
            "theme": key, "asof": asof, "ts": ts, "guidance_band": t["guidance_band"],
            "n_raisers": t["n_raisers"], "n_cutters": t["n_cutters"], "net": t["net"],
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
