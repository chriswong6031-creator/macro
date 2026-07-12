"""Calibration Hub — the unified observability surface for the self-improving AI suite (P2).

The suite produces a lot of self-improvement telemetry but never surfaced it together. This
consolidates it into ONE read:

  * every Phase-C desk's track record (hit-rate, by_regime, by_conviction) — are the
    falsifiable-thesis loops live, and are they right?
  * the Trial Ledger (engine.trial_ledger) — how many trials each calibrator HONESTLY
    counted, and the declared multiple-testing budgets (the P3 keystone made visible).
  * a per-desk CALIBRATION / health read: is conviction monotone (do 'high' calls hit more
    than 'low'?), and is the desk cold (tiny sample), weak (<50%), or inverted?

Display-only: reads the scorers' outputs, never a score / size / allocation. Writes
data/calibration/summary.json (+ a self-contained site/calibration.html). Degrade-never-raise.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from lib import config
from lib.pages import write_page
from engine.trial_ledger import TrialLedger

log = logging.getLogger(__name__)

SCHEMA = "calibration_hub.v1"
_MIN_SAMPLE = 10                 # below this a desk is "cold" — track record not yet meaningful

# The Phase-C falsifiable-thesis desks (label, track_record.json path).
_DESKS = (
    ("AI Desk", "ai_desk"),
    ("Policy Intent", "policy_intent"),
    ("Alt-Data Brain", "altdata"),
    ("Divergence Radar", "radar"),
    ("Stock Desk", "stock_desk"),
    ("Demand Chain", "demand_chain"),
)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001
        return None


def _conviction_monotone(by_conv: dict) -> bool | None:
    """True if hit-rate is monotone non-increasing high → medium → low (conviction means
    something). None when too few buckets have a sample to judge."""
    rates = [(by_conv.get(c) or {}).get("hit_rate") for c in ("high", "medium", "low")]
    present = [r for r in rates if r is not None]
    if len(present) < 2:
        return None
    return all(a >= b for a, b in zip(present, present[1:]))


def _desk_health(track: dict) -> tuple[str, str]:
    """Classify a desk from its track record → (health, note). The whole point of the
    suite is to make these states VISIBLE rather than letting a desk silently drift."""
    overall = track.get("overall") or {}
    n = overall.get("n") or 0
    hr = overall.get("hit_rate")
    by_conv = track.get("by_conviction") or {}
    if n < _MIN_SAMPLE:
        return "cold", f"only {n} scored — check-by windows still maturing; treat as provisional"
    if _conviction_monotone(by_conv) is False:
        return "inverted", "conviction inverted — high-conviction calls hit no more than low"
    if hr is not None and hr < 0.5:
        return "weak", f"hit-rate {hr} below coin-flip — leans not yet a validated edge"
    return "calibrated", f"hit-rate {hr} over {n} scored; conviction ordering holds"


def _desk_row(label: str, slug: str, root: Path) -> dict:
    track = _read_json(root / "data" / slug / "track_record.json") or {}
    overall = track.get("overall") or {}
    health, note = _desk_health(track) if overall else ("cold", "no track record yet")
    return {
        "name": label, "slug": slug,
        "scored": track.get("scored_total") or 0,
        "open": track.get("open") or 0,
        "hit_rate": overall.get("hit_rate"),
        "dir_accuracy": overall.get("dir_accuracy"),
        "conviction_monotone": _conviction_monotone(track.get("by_conviction") or {}),
        "regimes": sorted((track.get("by_regime") or {}).keys()),
        "health": health, "health_note": note,
    }


def _trial_ledger_summary(root: Path) -> dict:
    """How honestly the calibrators counted their multiple testing — the P3 keystone made
    visible: per signal family, the itemized trials + the declared upper-bound floor."""
    led = TrialLedger(Path(root).joinpath("data", "trial_ledger.jsonl"))
    fams = []
    for fam in led.families():
        fams.append({"family": fam, "itemized": led.literal_n(fam),
                     "declared": led.declared_budget(fam), "effective_n": led.effective_n(fam)})
    fams.sort(key=lambda f: f["effective_n"], reverse=True)
    return {"families": fams, "total_families": len(fams),
            "total_effective_n": sum(f["effective_n"] for f in fams)}


def build(root=None) -> dict:
    root = Path(root) if root else config.ROOT
    desks = [_desk_row(label, slug, root) for label, slug in _DESKS]
    live = sum(1 for d in desks if d["health"] != "cold")
    cold = len(desks) - live
    note = (f"{live}/{len(desks)} desk loops live; {cold} still cold (windows maturing). "
            "Display-only — track records calibrate conviction, never size a position.")
    return {
        "schema": SCHEMA,
        "as_of": date.today().isoformat(),
        "desks": desks,
        "loops": {"total": len(desks), "live": live, "cold": cold},
        "trial_ledger": _trial_ledger_summary(root),
        "summary_note": note,
    }


# --------------------------------------------------------------------------- #
# self-contained HTML (no theme/nav coupling) — one scannable observability page
# --------------------------------------------------------------------------- #
_HEALTH_COLOR = {"calibrated": "#1FA971", "weak": "#D98C00",
                 "inverted": "#E5484D", "cold": "#8B8D98"}


def _pct(x) -> str:
    return "—" if x is None else f"{round(x * 100):d}%"


def render_html(s: dict) -> str:
    rows = []
    for d in s["desks"]:
        c = _HEALTH_COLOR.get(d["health"], "#8B8D98")
        regimes = ", ".join(d["regimes"]) if d["regimes"] else "—"
        rows.append(
            f"<tr><td>{d['name']}</td><td style='text-align:right'>{d['scored']}</td>"
            f"<td style='text-align:right'>{d['open']}</td>"
            f"<td style='text-align:right'>{_pct(d['hit_rate'])}</td>"
            f"<td style='text-align:right'>{_pct(d['dir_accuracy'])}</td>"
            f"<td>{regimes}</td>"
            f"<td><span style='color:{c};font-weight:500'>{d['health']}</span><br>"
            f"<span style='color:#8B8D98;font-size:12px'>{d['health_note']}</span></td></tr>")
    led_rows = "".join(
        f"<tr><td>{f['family']}</td><td style='text-align:right'>{f['itemized']}</td>"
        f"<td style='text-align:right'>{f['declared'] or '—'}</td>"
        f"<td style='text-align:right'>{f['effective_n']}</td></tr>"
        for f in s["trial_ledger"]["families"]) or \
        "<tr><td colspan=4 style='color:#8B8D98'>no trials counted yet</td></tr>"
    lp = s["loops"]
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Calibration Hub</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:920px;margin:2rem auto;
padding:0 1rem;color:#1a1a1a;background:#fff}}
h1{{font-size:22px;font-weight:500}}h2{{font-size:16px;font-weight:500;margin-top:2rem}}
.sub{{color:#8B8D98;font-size:14px}}table{{width:100%;border-collapse:collapse;font-size:14px;margin-top:.5rem}}
th,td{{padding:8px 10px;border-bottom:1px solid #ececec;text-align:left;vertical-align:top}}
th{{color:#8B8D98;font-weight:500;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}
.chips{{display:flex;gap:1.5rem;margin:1rem 0}}.chip b{{font-size:24px;font-weight:500}}
/* our own scrollbars */
*{{scrollbar-width:thin;scrollbar-color:color-mix(in srgb,#8B8D98 50%,transparent) transparent}}
*::-webkit-scrollbar{{width:11px;height:11px}}
*::-webkit-scrollbar-track{{background:transparent}}
*::-webkit-scrollbar-thumb{{background:color-mix(in srgb,#8B8D98 50%,transparent);border-radius:999px;border:3px solid transparent;background-clip:padding-box}}
*::-webkit-scrollbar-thumb:hover{{background:color-mix(in srgb,#8B8D98 78%,transparent)}}
*::-webkit-scrollbar-corner{{background:transparent}}
@media(prefers-color-scheme:dark){{body{{background:#16171a;color:#e8e8e8}}th,td{{border-color:#2a2b2f}}*{{scrollbar-color:color-mix(in srgb,#c8ccd6 30%,transparent) transparent}}*::-webkit-scrollbar-thumb{{background:color-mix(in srgb,#c8ccd6 30%,transparent)}}}}
/* phone: the multi-column tables are wider than the screen — let each scroll
   horizontally within the page instead of pushing the whole page sideways. */
@media(max-width:700px){{table{{display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}}.chips{{flex-wrap:wrap;gap:1rem}}}}
</style></head><body>
<h1>Calibration Hub</h1>
<div class="sub">The self-improving AI suite, made visible · as of {s['as_of']} · display-only</div>
<div class="chips">
<div class="chip"><b>{lp['live']}</b><div class="sub">live loops</div></div>
<div class="chip"><b>{lp['cold']}</b><div class="sub">cold (maturing)</div></div>
<div class="chip"><b>{s['trial_ledger']['total_families']}</b><div class="sub">trial families</div></div>
</div>
<h2>Phase-C desks — are the falsifiable-thesis loops right?</h2>
<table><tr><th>Desk</th><th>Scored</th><th>Open</th><th>Hit-rate</th><th>Dir.</th>
<th>Regimes</th><th>Health</th></tr>{''.join(rows)}</table>
<h2>Trial Ledger — honest multiple-testing counts (P3 keystone)</h2>
<table><tr><th>Signal family</th><th>Itemized</th><th>Declared floor</th><th>Effective N</th></tr>{led_rows}</table>
<p class="sub">{s['summary_note']}</p>
</body></html>"""


def render_markdown(s: dict) -> str:
    L = [f"# Calibration Hub — {s['as_of']}", "", s["summary_note"], "",
         "## Phase-C desks", "", "| Desk | Scored | Hit-rate | Health |", "|---|---|---|---|"]
    for d in s["desks"]:
        L.append(f"| {d['name']} | {d['scored']} | {_pct(d['hit_rate'])} | {d['health']} — {d['health_note']} |")
    L += ["", "## Trial Ledger", "", "| Family | Itemized | Declared | Effective N |", "|---|---|---|---|"]
    for f in s["trial_ledger"]["families"]:
        L.append(f"| {f['family']} | {f['itemized']} | {f['declared'] or '—'} | {f['effective_n']} |")
    return "\n".join(L)


def run(root=None, persist: bool = True) -> dict:
    """Build the consolidated summary; write data/calibration/summary.json + site/calibration.html."""
    root = Path(root) if root else config.ROOT
    s = build(root)
    if persist:
        try:
            out = Path(root) / "data" / "calibration"
            out.mkdir(parents=True, exist_ok=True)
            (out / "summary.json").write_text(json.dumps(s, indent=2, default=str))
            site = Path(root) / config.load()["storage"]["site_dir"]
            site.mkdir(parents=True, exist_ok=True)
            write_page(site / "calibration.html", render_html(s))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("calibration_hub: persist failed: %s", e)
    return s


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    s = run(persist=True)
    print(render_markdown(s))
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    raise SystemExit(main())
