"""Build the thematic-baskets page -> site/baskets.html (+ basketdata/baskets.json).

Standalone (clones build_discovery.py / build_seasonality.py): reads
data/baskets/membership.json + the price caches + SPY via engine.baskets.compute_baskets()
and renders the FactorWatch-style baskets view — a sortable performance table
(1d/5d/20d/60d/YTD, raw or relative-to-SPY), a cumulative spark per basket, a
per-basket members drill and a dated membership changelog. Additive — any failure
logs and returns 0 so it can never break the rest of the site.

Usage: python -m scripts.build_baskets
       python -m scripts.build_baskets --snapshot   (PIT membership side-car only)

--snapshot (GMI W1a): append a dated point-in-time snapshot of US basket membership to
data/baskets/snapshots/YYYY-MM-DD.json and stamp it into the append-only per-suite PIT
parquet data/baskets/membership_history.parquet (engine/basket_membership_pit.py), then
rewrite the cadence stamp. Skips the page render entirely. The exact mirror of
scripts/build_baskets_china_ths.py --snapshot, one suite over.

WHY THE US SUITE NEEDED THIS. data/baskets/membership.json is a single MUTABLE document:
49 baskets with per-member added/removed dates, edited in place. engine/basket_freeze.py
writes only membership HASHES (`<bid>__mhash`) into data/basket_levels/us.parquet — change
DETECTION, from which membership cannot be reconstructed. So before this flag there was no
way to answer "who was in this basket on that date" for the US suite at all: any study over
US baskets was measuring today's membership applied backward, which is exactly the
look-ahead basis the CN store was built to end. The first snapshot is a genuine observation
of current membership; no pre-W1a history is reconstructed (masterplan G0.2).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_baskets")


def _check_basket_store_staleness(data: dict) -> None:
    """Emit a GitHub Actions warning (and an ops alert if available) when the basket
    price store is older than the last completed NYSE session.

    This is a WARN-ONLY guard — it never raises, never returns a non-zero exit code,
    and never blocks the build.  Intent: when the upstream collect job dies silently
    (timeout-cancelled, conclusion=cancelled fires no built-in alert) the next engine
    run still publishes stale data.  This warning makes the staleness visible in the
    Actions log and, when alert_triage is reachable, in ops channels (M7C-R8).
    """
    try:
        from datetime import date as _date
        from lib.nyse_calendar import expected_last_session  # noqa: PLC0415

        as_of_str: str | None = data.get("as_of")
        if not as_of_str:
            return  # no date in payload — nothing to compare

        last_bar: _date = _date.fromisoformat(str(as_of_str))
        expected: _date = expected_last_session()

        if last_bar >= expected:
            return  # store is current

        msg = (
            f"basket store stale: last bar {last_bar}, expected {expected} "
            f"— collect job likely timed-out or was cancelled upstream (M7C-R8)"
        )
        # GitHub Actions annotation — visible in the step log
        print(f"::warning ::{msg}", flush=True)
        log.warning(msg)

        # Ops alert via the W6b spine (dispatch-always channel).  Fail-open: if
        # alert_triage is unreachable we still have the ::warning annotation above.
        try:
            from engine.alert_triage import push_ops_alert  # noqa: PLC0415
            push_ops_alert(
                source="build_baskets",
                type_="basket_store_stale",
                message=msg,
                severity="major",
                lane="collect",
                window_hours=20,  # suppress repeats within same nightly window
            )
        except Exception as _ae:  # noqa: BLE001
            log.debug("_check_basket_store_staleness: push_ops_alert unavailable (%s)", _ae)

    except Exception as _e:  # noqa: BLE001 — staleness check must never crash the build
        log.debug("_check_basket_store_staleness failed (%s)", _e)


def _membership_pit_lane() -> str | None:
    """The collection lane this process runs in, resolved FAIL-CLOSED from ``COLLECT_LANE``.

    The US mirror of ``scripts.build_baskets_china_ths._membership_pit_lane``, and
    defaultless for the same reason: the PIT store is append-only, keep-FIRST per
    ``(snapshot_date, basket_id, ticker)`` and content-deduped, so the FIRST lane to
    stamp a date owns that snapshot forever and a later lane's view of the same day is
    discarded in silence.  A permissive ``os.environ.get("COLLECT_LANE", "nightly")``
    would hand that ownership to whichever hand-run or render lane happened to go first
    — the exact defect that made the CN gate dead on arrival until 2026-08-09
    (see tests/test_cn_membership_pit_lane_gate.py for the postmortem).

    ``US_LANE`` is accepted as the legacy alias, matching ``engine.ledger_lane``.
    daily.yml's engine job sets ``COLLECT_LANE: nightly`` at job level; the render,
    closing-bell and earlyclose lanes leave it unset and so append nothing.
    """
    import os  # noqa: PLC0415 — local to the side-car path

    val = os.environ.get("COLLECT_LANE") or os.environ.get("US_LANE") or ""
    return val.strip().lower() or None


def _snapshot_membership_pit() -> int:
    """Stamp the US suite into its append-only PIT parquet. Never fatal. Returns rows added."""
    try:
        from engine import basket_membership_pit as _pit  # noqa: PLC0415

        res = _pit.append_all(lane=_membership_pit_lane(), suites=_pit.SUITES_US)
        rows = 0
        for suite, r in res.items():
            snap = r.get("snapshot") or {}
            rows += int(snap.get("rows_added") or 0)
            log.info("membership PIT [%s]: %s (+%d rows, backfill +%d)", suite,
                     snap.get("snapshot_date") if snap.get("written")
                     else f"skipped — {snap.get('reason')}",
                     int(snap.get("rows_added") or 0),
                     int((r.get("backfill") or {}).get("rows_added") or 0))
        return rows
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("membership PIT snapshot failed (%s)", e)
        return 0


def snapshot_membership() -> int:
    """Append a dated PIT snapshot of US basket membership (content-deduped, never fatal).

    Two stores plus one stamp, mirroring the CN side-car writer exactly:

      * the queryable per-suite parquet (lane-gated, keep-first per snapshot_date);
      * the dated JSON side-car, byte-deduped against the newest one already on disk —
        membership moves when a curator edits it, not on the trading calendar, so
        stamping one every night would add ~250 identical files a year that say nothing;
      * ``_cadence.json``, rewritten UNCONDITIONALLY — including on the dedup skip.

    That last one is the whole reason this function is not just the first two.  A
    content-deduped writer that has been unwired and a content-deduped writer whose
    input has not changed leave the identical trace on disk: nothing.  That is how the
    THS side-car store sat at two snapshots for six weeks while its nightly step ran
    green ~35 nights in a row.  The cadence stamp is the artifact that tells those two
    apart, and ``scripts/check_membership_snapshot_freshness.py`` is what reads it.
    """
    import hashlib

    from engine import basket_membership_pit as _pit  # noqa: PLC0415

    suite = _pit.SUITE_US
    _snapshot_membership_pit()
    sha = None
    try:
        src = _pit.membership_path(suite)
        # NO early return anywhere below: every path falls through to the stamp. A
        # writer that ran and found no membership.json must look different from a
        # writer nobody wired — otherwise the tripwire reads a real outage as
        # INDETERMINATE, the one verdict that never pages anyone.
        if not src.exists():
            log.warning("us basket snapshot: membership.json missing — nothing to stamp")
        else:
            raw = src.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            snap_dir = _pit.snapshot_dir(suite)
            snap_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            dest = snap_dir / f"{today}.json"
            prior = _pit.dated_snapshots(suite)
            if dest.exists():
                log.info("us basket snapshot: %s already stamped — skipping", today)
            elif prior and hashlib.sha256(prior[-1].read_bytes()).hexdigest() == sha:
                log.info("us basket snapshot: membership unchanged since %s — dedup skip",
                         prior[-1].stem)
            else:
                dest.write_bytes(raw)
                log.info("us basket snapshot: wrote %s (%d bytes)", dest.name, len(raw))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("us basket snapshot failed (%s)", e)
    # ALWAYS stamped — the dedup-skip path above is exactly the case it exists for.
    _pit.write_cadence_stamp(suite, writer="scripts.build_baskets", membership_sha=sha)
    return 0


def _write_score_snapshot(ti: dict) -> None:
    """Slim per-theme score snapshot -> data/baskets/latest.json (archived daily by
    scripts.archive_signals into the 'baskets' stream → detail-page score history)."""
    slim = {"as_of": ti.get("as_of"), "themes": []}
    for t in ti.get("themes", []):
        tx = t.get("textures") or {}
        slim["themes"].append({
            "id": t["id"], "name": t.get("name"), "score": t.get("score"),
            "label": t.get("label"), "reco": t.get("reco"), "rank": t.get("rank"),
            "net_ad": t.get("net_ad"), "components": t.get("components"),
            "bull_days": (tx.get("bull_age") or {}).get("days"),
            "overbought": (tx.get("overbought") or {}).get("value"),
            "clean_entry": (tx.get("clean_entry") or {}).get("flag"),
            "rollover": (tx.get("rollover_risk") or {}).get("risk"),
        })
    p = config.data_dir() / "baskets" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(slim, separators=(",", ":"), default=str))


def main() -> int:
    if "--snapshot" in sys.argv[1:]:
        return snapshot_membership()
    site = config.ROOT / "site"
    try:
        from engine.baskets import compute_baskets
        data = compute_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no baskets (need data/baskets/membership.json + price caches) — skipping")
        return 0

    # M7C-R8: basket-store staleness warning — fires when collect died upstream (e.g.
    # timeout-cancelled).  WARN ONLY; never fails the build (stale site > broken site).
    _check_basket_store_staleness(data)

    # THEME ROTATION DESK (engine.theme_scoring) — score / label / recommend every theme,
    # 5-day rotation, impulse + new-hi-lo scorecards. Rides inside baskets_json. Then
    # engine.theme_alerts diffs vs the prior snapshot and fires change events into
    # data/themes/alerts.jsonl (picked up by alert_triage -> alerts.html with zero new
    # plumbing). Additive — never fatal.
    try:
        from engine.theme_scoring import compute_theme_intel
        ti = compute_theme_intel()
        if ti:
            data["theme_intel"] = ti
            from engine import theme_alerts
            theme_alerts.rebuild(ti)
            _write_score_snapshot(ti)            # data/baskets/latest.json → score-history archive
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme rotation desk failed: %s", e)

    # 🔵 BOTTOMING WATCH (engine.us_act_now, W-A) — the US port of China's
    # bottoming lane + FT-R1 dual-read law. The nightly cycle engine already
    # writes data/sector_cycles/forward_log.parquet; before this, nothing carried
    # a Trough+rising row to a decision surface (gold_miners sat on reduce/avoid
    # while the log printed Trough pos=2.0 osc_slope=+1.3). Display tier, zero
    # scored authority. EXTENDS theme_intel.act_now with two new keys plus its
    # authority block; the buy / add_on_pullback / reduce lanes are read ONLY
    # (for the dual-read id set) and are never mutated — G0.3 keeps their
    # membership byte-identical. Additive, never fatal.
    try:
        _ti_ba = data.get("theme_intel")
        if _ti_ba and isinstance(_ti_ba.get("act_now"), dict):
            from engine.us_act_now import assemble_bottoming_watch, load_cycle_rows
            _an_ba = _ti_ba["act_now"]
            # Bilingual law (G0.5): the forward log is English-only. Basket zh names
            # come from the theme desk; sector-ETF zh names from the sector board.
            _zh_ba: dict = {}
            for _t_ba in (_ti_ba.get("themes") or []):
                if _t_ba.get("id") and _t_ba.get("name_zh"):
                    _zh_ba[_t_ba["id"]] = _t_ba["name_zh"]
            try:
                _sc_ba = site / "sectordata" / "sector_central.json"
                if _sc_ba.exists():
                    with open(_sc_ba, encoding="utf-8") as _f_ba:
                        for _s_ba in (json.load(_f_ba).get("sectors") or []):
                            if _s_ba.get("id") and _s_ba.get("name_zh"):
                                _zh_ba[_s_ba["id"]] = _s_ba["name_zh"]
            except Exception as _e_ba:  # noqa: BLE001 — names only, never fatal
                log.warning("bottoming watch: sector zh names unavailable: %s", _e_ba)
            _bw = assemble_bottoming_watch(
                load_cycle_rows(),
                reduce_ids=[x.get("id") for x in (_an_ba.get("reduce") or []) if x.get("id")],
                names_zh=_zh_ba,
            )
            _an_ba["bottoming_watch"] = _bw["bottoming_watch"]
            _an_ba["dual_read_ids"] = _bw["dual_read_ids"]
            # Graduation gap: reduce/avoid rows the cycle organ reads as
            # recovering off a low but which have left the bottoming lane.
            # Disjoint from dual_read_ids — a separate chip, separate sentence.
            _an_ba["recovering_ids"] = _bw["recovering_ids"]
            _an_ba["bottoming_authority"] = _bw["authority"]
            log.info(
                "bottoming watch: %d row(s), %d dual-read id(s), %d recovering id(s)%s",
                len(_bw["bottoming_watch"]), len(_bw["dual_read_ids"]),
                len(_bw["recovering_ids"]),
                (" — " + "; ".join(_bw["notes"])) if _bw["notes"] else "",
            )
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("bottoming watch lane failed: %s", e)

    # 🔥 FORMING NARRATIVES (engine.narrative_emergence) — fuse the theme-discovery radar
    # (coherent, TIGHTENING name-groups not yet in a basket) with the GDELT attention
    # backdrop + the AI desk's emerging_watch into a ranked, surfaced read with clean-entry
    # recommended tickers. engine.emergence_alerts diffs vs the prior snapshot and fires a
    # "narrative_forming" event (picked up by alert_triage). Display-only, additive, noisy —
    # a watchlist / avoid-the-peak lens, never a buy list. Never fatal.
    emergence = None
    try:
        from engine.narrative_emergence import compute_emergence
        emergence = compute_emergence("us")
        if emergence:
            from engine import emergence_alerts
            emergence_alerts.rebuild(emergence, "us")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("narrative emergence desk failed: %s", e)

    fdir = site / "basketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    # baskets.json is written AFTER the sector_pulse merge below — the page now FETCHES this
    # artifact instead of an inline embed, so it must carry the pulse keys (velocity/heat)
    # the rotation map and lanes read. Writing here would freeze a pre-merge snapshot.
    if emergence:
        (fdir / "narrative_emergence.json").write_text(
            json.dumps(emergence, separators=(",", ":"), default=str))

    # Engine-1 FLOW LENS (display-only characterization + the AI-handoff payload). It
    # ranks where cross-sectional flow is CONCENTRATING (PIT sectors + baskets), maps the
    # cross-group cluster, and carries the validated-honest verdict/caveats. flow.json is
    # the contract a downstream AI judge reads. Additive — never breaks the page.
    flow = None
    try:
        from engine.group_flow import compute_group_flows
        flow = compute_group_flows()
        if flow:
            (fdir / "flow.json").write_text(json.dumps(flow, separators=(",", ":"), default=str))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("group_flow lens failed: %s", e)

    # GR0 — GROUP PULSE (engine.group_pulse, group_pulse.v1). The basket-level
    # PARTICIPATION / DIRECTION / ARC read plane: how many members are actually
    # moving, whether they are moving the same way, and where the group sits in a
    # washout->advance arc. An ASSEMBLER over organs that already exist (group_flow's
    # cohesion + the sign-agreement leg added beside it, coiled's capitulation read,
    # weinstein_stage) — NOT a new scorer, and the artifact carries no fused
    # score/rank/heat number of any kind (tests/test_group_pulse_tripwire.py).
    #
    # Placed here, immediately after the flow lens, for the same reason flow sits
    # here: membership + the member tape are fresh at this point in the DAG band and
    # fdir already exists. site/basketdata/pulse.json is written in ANY lane (it is a
    # display snapshot); only the episode LEDGER append is nightly-gated, inside the
    # engine on engine.ledger_lane.nightly_advance_enabled() — house law, nightly is
    # the sole advancer of forward ledgers and an intraday lane computes and discards.
    #
    # DISPLAY TIER, ZERO AUTHORITY: no lane, rank, gate, or size reads it.
    # Own try/except — exit-0 always (additive, never fatal).
    try:
        from engine.group_pulse import run as _gp_run
        _gp_res = _gp_run()
        _gp_led = _gp_res.get("ledger") or {}
        log.info(
            "group_pulse: %d basket(s) as_of=%s in %.1fs -> %s; episode ledger %s"
            " (%s rows, %s closed); history -> %s (%s closed episode(s) published)",
            _gp_res.get("n_baskets", 0), _gp_res.get("as_of"),
            float(_gp_res.get("elapsed_s") or 0.0), _gp_res.get("artifact"),
            "advanced" if _gp_led.get("written") else
            f"skipped ({_gp_led.get('reason', 'unknown')})",
            _gp_led.get("rows", 0), _gp_led.get("closed", 0),
            _gp_res.get("episodes_artifact"), _gp_res.get("n_closed_episodes", 0),
        )
    except Exception as _gp_exc:  # noqa: BLE001 — additive, never fatal
        # Bare print at column 0, NOT a logger call: this package's logging format
        # prefixes every record, and GitHub only parses a "::" that STARTS the line.
        print(f"::warning title=group-pulse::group_pulse hook failed: {_gp_exc}",
              flush=True)

    # 📅 GROUP EARNINGS PULSE (Group Reads W-GR2, engine.group_earnings) — the earnings
    # LAYER of each basket read: season clock, beat/miss rollup, guidance band (the
    # guidance_gap classifier generalized to basket rosters), revision breadth, post-report
    # drift, and the earnings SYMPATHY ratio (do this group's members move together around
    # each other's prints). CONTEXT-ONLY: never ranked, sized, gated, or fused into a
    # score; every stat carries its n and every floor refusal prints a null.
    #
    # Reads committed artifacts only (no network at build time) and caches the member
    # return series ONCE for the whole 49-basket sweep — ~4s wall clock. The sympathy
    # ledger append inside is lane-gated by engine.ledger_lane (nightly is the sole
    # advancer), so the express/intraday lanes compute the JSON and discard the write.
    # Additive — never breaks the page.
    try:
        from engine.group_earnings import compute_group_earnings
        pulse = compute_group_earnings()
        if pulse:
            (fdir / "earnings_pulse.json").write_text(
                json.dumps(pulse, separators=(",", ":"), default=str))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("group earnings pulse failed: %s", e)

    # SECTOR PULSE — compact per-theme rotation data product for Mastermind bot / Terminal.
    # Reads theme_intel (already computed above) and writes basketdata/sector_pulse.json.
    # Also merges per-theme velocity/heat keys into theme_intel so the page JS can render
    # the rotation velocity scorecard enhancements (heat pill, 20d rank trajectory, act-now
    # pulse strip).  Additive — never breaks the build.
    try:
        if data.get("theme_intel"):
            from engine import sector_pulse as _sp
            _sp.write_pulse(data["theme_intel"], "us", fdir)
            _sp.merge_pulse_into_theme_intel(data["theme_intel"], "us")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_pulse hook failed: %s", e)

    # The Sector Intelligence page (sector_central.html) fetches this artifact client-side
    # (the old inline `var BASKETS = …` embed is gone) — written post-pulse-merge and
    # pre-chart-pop so it carries BOTH the velocity/heat keys and the chart matrix.
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))

    # THEME ROTATION DESK ADD-ONS (display-only context): ETF Pulse (style/risk/sector
    # rotation), vol-regime + CBOE put/call chip, and per-theme ATR extension. Each writes
    # its own basketdata/*.json, consumed client-side by site/theme_addons.js (the
    # _theme_addons.html.j2 panel). Additive — never breaks the page.
    try:
        from scripts.build_theme_addons import main as _build_theme_addons
        _build_theme_addons()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme add-ons failed: %s", e)

    # 🛰️ DIVERGENCE RADAR (display-only): federal contract spend (collectors.usaspending)
    # vs each theme's already-priced 60-day relative strength -> per-theme divergence
    # states + falsifiable watch-hypotheses (data/radar/theses.jsonl, graded later).
    # Read client-side via site/radar_panel.js (the _radar_panel.html.j2 panel).
    # Additive — never breaks the page.
    try:
        from engine.radar import append_ledger, compute_radar
        radar = compute_radar(data)
        if radar:
            (fdir / "radar.json").write_text(json.dumps(radar, separators=(",", ":"), default=str))
            append_ledger(radar)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("divergence radar failed: %s", e)
    # dedicated Divergence Radar page (site/radar.html) — pure render of the radar/brain JSON
    try:
        from scripts.build_radar_page import main as _build_radar_page
        _build_radar_page()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("radar page failed: %s", e)

    # split the dense CHART (level matrix, for the interactive chart + live σ/sort table)
    # from the BASKETS metadata (thesis/members/rationale/perf/changelog/reference).
    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # Risk strip (top of page): the headline mirrors the canonical Market Risk Radar
    # (engine/risk_radar.py → latest.json.risk_radar) shown identically on macro.html, so the
    # two pages always agree on the number. The risk_state engine (engine/risk_state.py) supplies
    # the de-gross SIZING guidance (gross factor / leadership cap) — the leadership-driven
    # baskets surface should DOWN-SIZE and favor good entries, not chase extended leaders.
    # Read-only from latest.json; never fatal. Both surfaced only at caution or worse.
    risk_state = None
    risk_radar = None
    try:
        _latest = json.loads((config.data_dir() / "regime" / "latest.json").read_text())
        rs = _latest.get("risk_state")
        if rs and rs.get("state") in ("caution", "elevated", "risk-off"):
            risk_state = rs
        rr = _latest.get("risk_radar")
        if rr and rr.get("state") in ("caution", "elevated", "risk-off"):
            risk_radar = rr
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("baskets risk-state read failed: %s", e)
    # B4: seasonal-climate chip (display-only page furniture; read committed artifact).
    factor_season = None
    try:
        _seas_path = site / "factordata" / "factor_seasonality.json"
        if _seas_path.exists():
            _seas_raw = json.loads(_seas_path.read_text(encoding="utf-8"))
            _seas_now = _seas_raw.get("now") if isinstance(_seas_raw, dict) else None
            if (
                isinstance(_seas_raw, dict)
                and _seas_raw.get("schema") == "factor_seasonality.v2"
                and isinstance(_seas_now, dict)
                and _seas_now.get("chip_en")
            ):
                _factor_list = _seas_now.get("factors") or []
                _mom = next((f for f in _factor_list if f.get("key") == "momentum"), None)
                _any_non_neutral = (
                    (_mom and _mom.get("verdict") != "neutral")
                    or any(f.get("verdict") != "neutral" for f in _factor_list if f.get("key") != "momentum")
                )
                if _any_non_neutral:
                    _mom_verdict = (_mom or {}).get("verdict", "neutral")
                    _tone = _mom_verdict if _mom_verdict != "neutral" else next(
                        (f.get("verdict") for f in _factor_list if f.get("verdict") != "neutral"),
                        "neutral",
                    )
                    factor_season = {
                        "chip_en": _seas_now.get("chip_en"),
                        "chip_zh": _seas_now.get("chip_zh"),
                        "tip_en": (
                            (_seas_now.get("headline_en") or "")
                            + (" " + _seas_now.get("stance_en") if _seas_now.get("stance_en") else "")
                        ).strip(),
                        "tip_zh": (
                            (_seas_now.get("headline_zh") or "")
                            + (" " + _seas_now.get("stance_zh") if _seas_now.get("stance_zh") else "")
                        ).strip(),
                        "tone": _tone,
                    }
    except Exception as _fse:  # noqa: BLE001 — additive display chip, never fatal
        log.warning("factor_season chip read failed: %s", _fse)
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    # Collect flat sorted unique member symbols for W2a hidden live-span scrape expansion.
    # The scraper (build_live_quotes.scrape_site_symbols) reads site/*.html for data-sym attrs;
    # basket member tickers are only in the BASKETS JSON blob otherwise, so they are invisible
    # to the scraper. Passing them to Jinja lets us emit aria-hidden spans in static HTML.
    _member_syms: list[str] = sorted({
        str(m.get("symbol", "")).strip().upper()
        for b in data.get("baskets", [])
        for m in (b.get("members") or [])
        if m.get("symbol")
    })

    # Thematic Narrative-Rotation pages (engine.narrative_rotation -> site/allocation*.html)
    # for ALL FOUR markets (US + China + HK + Canada). Built here off the same baskets
    # membership + price caches the collectors already refresh, so they ship on every CI run
    # without new daily.yml steps (the PAT lacks `workflow` scope, like build_canada /
    # build_baskets_china). First refresh the honest Phase-0 backtest artifacts the pages
    # cite (US 27y + Canada ~24y + China ~8y; HK is too thin → cites the US proxy) — committed
    # copies are the fallback if a refresh fails; an absent file just hides that panel. Both
    # additive — never fatal. TODO: promote to dedicated daily.yml steps once a workflow-scoped
    # token is available.
    try:
        from scripts.thematic_rotation_phase0 import run_all as _phase0_all
        _phase0_all()                                     # us, canada, china (HK skipped → US proxy)
    except Exception as e:  # noqa: BLE001 — additive; falls back to the committed artifacts
        log.error("thematic rotation Phase-0 refresh failed (using committed artifacts): %s", e)
    _alloc_stale = False
    try:
        from scripts.build_allocation import main as _build_allocation
        _alloc_stale = _build_allocation()                # builds all four allocation pages
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        _alloc_stale = True
        log.error("allocation pages (via build_baskets) failed: %s", e, exc_info=True)
        print("::warning::allocation sub-build (via build_baskets) raised an unhandled exception"
              " — data/allocation/latest_*.json will NOT be updated this run. "
              f"Root cause: {type(e).__name__}: {e}")
    # Always write freshness.json so the file reflects the CURRENT run, not the worst
    # run in history.  If we only write on failure the file persists stale=true in the
    # committed tree forever after the first bad nightly, permanently misleading W3.
    import json as _json
    from lib import config as _cfg
    _fdir = _cfg.ROOT / "site" / "allocationdata"
    _fdir.mkdir(parents=True, exist_ok=True)
    (_fdir / "freshness.json").write_text(
        _json.dumps({"stale": _alloc_stale,
                     "reason": ("allocation sub-build failed or returned stale"
                                if _alloc_stale else "ok"),
                     "stamped_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                    separators=(",", ":")))

    # THEME CONTEXT (theme_context.v1) — wired HERE so that allocation.json has already been
    # written by build_allocation() above (PIT correctness: theme_context.as_of, the
    # same-day idempotency check, and the context_history.jsonl ledger row all reflect the
    # CURRENT build's allocation data, not the prior build's file).  Additive — a context
    # failure never blocks the page build.  baskets.html is rendered below (after this block)
    # so the Jinja var carries the fresh context.
    _theme_context: dict | None = None
    try:
        from engine.theme_context import compute_theme_context, write_context as _write_ctx
        _alloc_json_path = config.ROOT / "site" / "allocationdata" / "allocation.json"
        if _alloc_json_path.exists() and data.get("theme_intel"):
            _alloc_payload = json.loads(_alloc_json_path.read_text())
            _theme_context = compute_theme_context(
                alloc=_alloc_payload,
                theme_intel=data["theme_intel"],
                region="us",
            )
            if _theme_context:
                _write_ctx(_theme_context)
                log.info(
                    "theme_context: state=%s leader=%s",
                    _theme_context.get("leadership", {}).get("state"),
                    (_theme_context.get("leadership", {}).get("trailing_leader") or {}).get("id"),
                )
    except Exception as _tc_exc:  # noqa: BLE001 — additive, never fatal
        log.warning("theme_context hook failed: %s", _tc_exc)

    # SECTOR INTELLIGENCE HANDOFF — the merged page (rendered by build_sector_central, which
    # runs after this in the DAG band) needs the server-side hero/lane context this builder
    # computes. Written as one small artifact (si_handoff.json — NOT theme_context.json,
    # which engine.theme_context owns and the Neural Web theme_rotation lobe reads);
    # build_sector_central reads it fail-soft.
    try:
        (fdir / "si_handoff.json").write_text(json.dumps({
            "theme_context": _theme_context,
            "factor_season": factor_season,
            "flow": ({"cluster": {"regime": ((flow or {}).get("cluster") or {}).get("regime")}}
                     if (flow or {}).get("cluster") else None),
            "basket_member_syms": _member_syms,
            "generated_utc": built,
        }, separators=(",", ":"), default=str))
    except Exception as _si_exc:  # noqa: BLE001 — additive, never fatal
        log.warning("sector-intelligence handoff write failed: %s", _si_exc)

    # Render baskets.html — now a redirect stub (Thematic Baskets merged into Sector
    # Intelligence at sector_central.html; operator consolidation 2026-08-01). The stub
    # takes ONE piece of context: theme_ids, the id list its #theme-<id> deep-link
    # resolver validates against before sending a visitor to basket/<id>.html. It is the
    # same list build_detail_pages() writes pages from below, so the resolver can never
    # aim at a page that was not built; detail pages still consume the full `data`.
    _theme_ids = [str(b["id"]) for b in data.get("baskets", []) if b.get("id")]
    html = env.get_template("baskets.html.j2").render(theme_ids=_theme_ids)
    write_page(site / "baskets.html", html)
    # PER-THEME DETAIL PAGES (one site/basket/<id>.html each) — needs `data` (with
    # theme_intel + members) and the env; chart already split off above. Additive.
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, "us", chart)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("theme detail pages failed: %s", e)
    # ship the TradingView Lightweight Charts runtime (Apache-2.0) used by the page
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    # ship the prevailing-narrative scorecard renderer (all baskets pages use it)
    sc = config.ROOT / "templates" / "allocation_scorecard.js"
    if sc.exists():
        (site / "allocation_scorecard.js").write_text(sc.read_text())
    # ship the Forming Narratives renderer (all baskets pages use it)
    ne = config.ROOT / "templates" / "forming_narratives.js"
    if ne.exists():
        (site / "forming_narratives.js").write_text(ne.read_text())
    log.info("wrote %s/baskets.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), len(html) // 1024)

    try:
        from scripts.build_anticipation import main as _build_anticipation
        _build_anticipation()                             # anticipation.html + per-ticker cones
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("anticipation page (via build_baskets) failed: %s", e)

    # W3.8 — FREEZE US basket levels + membership hashes (append-only, PIT).
    # Runs AFTER compute_baskets() and the chart pop, so both `data` (BASKETS metadata)
    # and `chart` (level matrix) are in scope.  Additive + never fatal: a freeze failure
    # skips today's snapshot without breaking the page.  The grader reports
    # "accruing from <date>" for any day the freeze was skipped.
    try:
        from engine.basket_freeze import freeze_domain, FreezeSkipped
        from engine.baskets import _membership as _us_mem
        from engine.equity_factors import _closes as _us_closes
        _us_mem_data = _us_mem()
        try:
            _us_cl = _us_closes()
        except Exception:  # noqa: BLE001
            _us_cl = None
        # chart was popped from data above and is still in scope
        _freeze_payload = {"chart": chart}
        _freeze_result = freeze_domain("us", _freeze_payload, _us_cl, _us_mem_data)
        log.info("basket_freeze[us]: %s", _freeze_result)
    except FreezeSkipped as e:
        log.error("basket_freeze[us]: SKIPPED (churn guard): %s", e)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("basket_freeze[us]: failed: %s", e)

    # FTR W4 — BASKET TURN-WATCH K-of-N confluence organ.
    # Placed before the freshness sentinel (W0) so the sentinel can audit the artifact.
    # Own try/except — exit-0 always (build_allocation hook pattern).
    try:
        from engine.basket_turn_watch import compute as _btw_compute, write_site_artifact as _btw_write
        _btw_result = _btw_compute()
        _btw_path = _btw_write(_btw_result)
        _btw_n_watch = sum(
            1 for b in _btw_result.get("baskets", [])
            if b.get("state") in ("WATCH", "IGNITION")
        )
        log.info("basket_turn_watch: wrote %s (%d WATCH/IGNITION baskets)", _btw_path, _btw_n_watch)
    except Exception as _btw_exc:  # noqa: BLE001 — additive, never fatal
        # Bare print, NOT a logger call: GitHub only parses a workflow command when
        # "::" STARTS the line, and this module's logging format prefixes every
        # record (e.g. "WARNING ::warning ..."), which silently drops the annotation.
        print(f"::warning::basket_turn_watch hook failed: {_btw_exc}", flush=True)

    # W1-D — US WASHOUT-LIFECYCLE organ (us_basket_turn.v1), the port of the CN
    # engine/china_basket_turn.py machine that was the only detector in the estate
    # to change state before the 2026-07 precious-metals low (masterplan G0.6,
    # research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md).
    # A SEPARATE organ from basket_turn_watch above — different construction
    # (washout lifecycle, no K-of-N legs) — placed immediately after it because
    # both read the same member tape and the freshness sentinel below audits both.
    # DISPLAY TIER, ZERO SCORED AUTHORITY: writes a state artifact + forward ledger
    # and nothing else; no lane, rank, or gate reads it.
    # Own try/except — exit-0 always (additive, never fatal).
    try:
        from engine.us_basket_turn import run as _ubt_run
        _ubt_result = _ubt_run()
        _ubt_states: dict[str, int] = {}
        for _ubt_row in _ubt_result.get("baskets", {}).values():
            _ubt_s = _ubt_row.get("state", "NONE")
            _ubt_states[_ubt_s] = _ubt_states.get(_ubt_s, 0) + 1
        _ubt_cov = _ubt_result.get("coverage", {})
        log.info(
            "us_basket_turn: %d baskets, session=%s, members %s/%s — dist: %s",
            len(_ubt_result.get("baskets", {})),
            _ubt_result.get("data_session"),
            _ubt_cov.get("members_read"), _ubt_cov.get("members_total"),
            _ubt_states,
        )
    except Exception as _ubt_exc:  # noqa: BLE001 — additive, never fatal
        # Bare print at line start, never a logger (see the note above).
        print(f"::warning::us_basket_turn hook failed: {_ubt_exc}", flush=True)

    # TS-U2 — MTF UPTURN per-stock K-of-N confluence organ (mtf_upturn.v1).
    # Placed immediately after basket_turn_watch (U2 is the per-stock twin of that organ).
    # Own try/except — exit-0 always (additive, display-tier).
    try:
        from engine.mtf_upturn import compute as _mtu_compute, write_site_artifact as _mtu_write
        _mtu_result = _mtu_compute()
        _mtu_path = _mtu_write(_mtu_result)
        _mtu_n_conf = len(_mtu_result.get("cohort", {}).get("confirmed", []))
        _mtu_n_watch = len(_mtu_result.get("cohort", {}).get("watch", []))
        log.info(
            "mtf_upturn: wrote %s (%d confirmed, %d watch, elapsed=%.1fs)",
            _mtu_path, _mtu_n_conf, _mtu_n_watch,
            _mtu_result.get("elapsed_s", 0),
        )
    except Exception as _mtu_exc:  # noqa: BLE001 — additive, never fatal
        print(f"::warning::mtf_upturn hook failed: {_mtu_exc}", flush=True)

    # WTN-W1 — per-name WEEKLY washout-turn watch organ (washout_turn.v1).
    # The MCD miss (research/washout_turn_name_lane/MCD_MISS_EVIDENCE_2026-08-05.md):
    # nothing consumed the house canon RSI-MACD at WEEKLY grain per name, so a
    # 6th-percentile-depth weekly cross reached no surface. Sits beside mtf_upturn
    # (that organ watches standard PRICE MACD-vs-zero — a different indicator family).
    # Display-tier, zero authority; own try/except — exit-0 always.
    try:
        from engine.washout_turn import compute as _wtn_compute, write_site_artifact as _wtn_write
        _wtn_result = _wtn_compute()
        _wtn_path = _wtn_write(_wtn_result)
        _wtn_n_turn = len(_wtn_result.get("cohort", {}).get("turn", []))
        _wtn_n_watch = len(_wtn_result.get("cohort", {}).get("watch", []))
        log.info(
            "washout_turn: wrote %s (%d washout-turn, %d turn-watch, elapsed=%.1fs)",
            _wtn_path, _wtn_n_turn, _wtn_n_watch,
            _wtn_result.get("elapsed_s", 0),
        )
    except Exception as _wtn_exc:  # noqa: BLE001 — additive, never fatal
        # Bare print, NOT a logger call — GitHub only parses "::" at LINE START.
        print(f"::warning::washout_turn hook failed: {_wtn_exc}", flush=True)

    # SEA-W1/W2 — Signal Episode Atlas: nightly event append + outcome maturation
    # + the cohort-grain atlas artifact (research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md).
    # Sits after washout_turn: that organ says a name IS in a washout turn, this
    # library says what the matching historical episodes of the same CLASS did.
    # The append and the maturation are both COLLECT_LANE-gated inside the engine
    # (an off-lane run computes and discards); only small monthly live parts are
    # ever rewritten (#4540). Measurement tier, zero authority; own try/except.
    try:
        from engine import event_atlas as _sea_atlas
        from engine import stock_events as _sea_events
        _sea_upd = _sea_events.nightly_update()
        _sea_payload = _sea_atlas.build_atlas(refresh_cache=True)
        _sea_path = _sea_atlas.write_site_artifact(_sea_payload)
        log.info(
            "stock_events: %d events extracted, %d appended, %d outcome cells matured "
            "(lane_write=%s); event_atlas: %d cells → %s (elapsed=%.1fs)",
            _sea_upd.get("extracted", 0), _sea_upd.get("appended", 0),
            _sea_upd.get("matured_filled", 0), _sea_upd.get("written"),
            _sea_payload.get("n_cells", 0), _sea_path,
            float(_sea_upd.get("elapsed_s", 0.0)) + float(_sea_payload.get("elapsed_s", 0.0)),
        )
    except Exception as _sea_exc:  # noqa: BLE001 — additive, never fatal
        # Bare print, NOT a logger call — GitHub only parses "::" at LINE START.
        print(f"::warning::stock_events hook failed: {_sea_exc}", flush=True)

    # NAR-W1 — Flare Persistence organ (flare_persistence.v1). Reads raw tape witnesses
    # (T1 altdata convergence, T2 call premium z, T3 GEX flip, T4 news bull ratio z).
    # Placed beside mtf_upturn (TS-U2 pattern). Display-tier; own try/except — never fatal.
    try:
        from engine.flare_persistence import (
            compute as _fpo_compute,
            write_site_artifact as _fpo_write,
        )
        _fpo_result = _fpo_compute()
        _fpo_path = _fpo_write(_fpo_result)
        _fpo_n_primed = sum(
            1 for r in _fpo_result.get("rows", []) if r.get("state") == "PRIMED"
        )
        log.info(
            "flare_persistence: wrote %s (%d rows, %d PRIMED, elapsed=%.1fs)",
            _fpo_path, len(_fpo_result.get("rows", [])), _fpo_n_primed,
            _fpo_result.get("elapsed_s", 0),
        )
    except Exception as _fpo_exc:  # noqa: BLE001 — additive, never fatal
        print(f"::warning::flare_persistence hook failed: {_fpo_exc}", flush=True)

    # NAR-W3 — Narrative Flare organ (narrative_flare.v1). Reads W2 collector stores
    # (substack_posts, hn_mentions, edgar_8k_counts) + Polygon news counts; computes
    # per-ticker narrative witnesses (news_count_z, similarity_gap, tfidf_novelty,
    # kleinberg_burst, first_coverage). Writes site/narrativedata/flares.json.
    # Placed beside flare_persistence (TS-U2 pattern). Display-tier; own try/except.
    try:
        from engine.narrative_flare import (
            compute as _nfo_compute,
            write_site_artifact as _nfo_write,
        )
        _nfo_result = _nfo_compute()
        _nfo_path = _nfo_write(_nfo_result)
        _nfo_n_present = sum(
            1 for r in _nfo_result.get("rows", []) if r.get("present")
        )
        log.info(
            "narrative_flare: wrote %s (%d rows, %d present, elapsed=%.1fs)",
            _nfo_path, len(_nfo_result.get("rows", [])), _nfo_n_present,
            _nfo_result.get("elapsed_s", 0),
        )
    except Exception as _nfo_exc:  # noqa: BLE001 — additive, never fatal
        print(f"::warning::narrative_flare hook failed: {_nfo_exc}", flush=True)

    # FTR W10 — Discord alerts for turn-watch IGNITION / shock activation / tape disagreement.
    # Placed after basket_turn_watch so turn_watch.json is fresh.
    # Own try/except — exit-0 always (FT-R13 / FT-R5 contract).
    try:
        from scripts.notify_turn_events import run as _notify_turn_events
        _notify_turn_events()
    except Exception as _nte_exc:  # noqa: BLE001 — additive, never fatal
        print(f"::warning::notify_turn_events hook failed: {_nte_exc}", flush=True)

    # GR3 — filing-linked outsiders per basket (outside confirmation).
    # Placed AFTER the group_pulse hook on purpose: it reads pulse.json from the
    # same run for each basket's direction sign.  A missing pulse.json degrades to
    # "unavailable" states with a coverage warning rather than failing.
    try:
        from engine.group_linked_outsiders import run as _glo_run
        _glo_summary = _glo_run()
        log.info(
            "group_linked_outsiders: wrote %s (%d baskets, %d with outsiders, %d ledger rows)",
            _glo_summary["path"], _glo_summary["baskets"],
            _glo_summary["baskets_with_outsiders"], _glo_summary["edges_appended"],
        )
    except Exception as _glo_exc:  # noqa: BLE001 — additive, never fatal
        # Bare print, NOT a logger call — GitHub only parses "::" at LINE START.
        print(f"::warning::group_linked_outsiders hook failed: {_glo_exc}", flush=True)

    # FT-R8 — surface-freshness sentinel: assert first-class artifacts carry today's
    # NYSE session.  Warn-only (exits 0 always); annotations appear in the job summary.
    try:
        from scripts.check_surface_freshness import run as _check_freshness
        _check_freshness()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("check_surface_freshness failed: %s", e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
