"""Build the Capital-Flow Velocity desk -> site/flow_velocity.html (+ flowdata/desk.json).

"How fast is big money flowing into China / HK names and sectors" — the velocity &
acceleration of the net-flow series the build already collects (Stock-Connect channels,
the Tushare 主力 weekly grid, the Dragon-Tiger institutional seats, southbound holdings).
engine.flow_velocity is the brain; this script is the thin render tier.

Additive — any failure logs and returns 0 so it never breaks the rest of the build.
Run: python -m scripts.build_flow_velocity
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402
from engine.flow_observatory import changes as fo_changes  # noqa: E402
from engine.flow_observatory import contract as fo_contract  # noqa: E402
from engine.flow_observatory import groups as fo_groups  # noqa: E402
from engine.flow_observatory import history as fo_history  # noqa: E402
from engine.flow_observatory import quality as fo_quality  # noqa: E402
from engine.flow_observatory import workflow as fo_workflow  # noqa: E402
from engine.flow_observatory.contract import ContractError, build_v2, validate  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_flow_velocity")


# ── W4: official (Shenwan L1) sector lens — wired here, not engine.flow_velocity.py
# (OWNED-FILES scope: flow_velocity.py exposes reusable rollup HELPERS only; the lens
# itself, and its enrich_group/assign_ranks pass, are "lens wiring" and live here). ──
def _l1_names() -> dict[str, tuple[str, str]]:
    """The official-sector lens' code -> ``(name_en, name_zh)`` map, built from
    ``collectors.china_sectors.SW_L1`` (``code: (cn, en)``).

    SF/W4 repair: this used to be inlined as a one-line dict comprehension inside
    ``_official_sectors_panel`` — the ZH-name regression test could only exercise
    ``engine.flow_observatory.groups.aggregate_lens`` with a HAND-WRITTEN
    ``l1_names`` fixture, which pins ``aggregate_lens``' own plumbing but not the
    real CALLER that builds this dict in production; an EN-only revert here
    (``{code: (en, en)}``) would have shipped without failing anything. Extracted so
    a test can import and assert on THIS function directly."""
    from collectors.china_sectors import SW_L1
    return {code: (en, cn) for code, (cn, en) in SW_L1.items()}


def _official_sectors_panel() -> dict | None:
    """Build the official-sector lens payload, or ``None`` when there is nothing to
    show (2B spike-failure shape — this build's spike SUCCEEDED, §1, so ``None`` here
    only means the membership store has not collected yet, e.g. a fresh checkout
    before the china_sectors collector's first run). Recomputes ``wide``/``kmap`` —
    the same shared kinetics primitives ``engine.flow_velocity.snapshot()`` already
    built for the theme lens — because OWNED-FILES scope keeps this assembly OUT of
    flow_velocity.py itself; the recompute's wall-time cost is measured in the PR
    body's performance note (spec §7)."""
    import pandas as pd

    from engine.flow_velocity import _flow_panel, _name_kinetics_map, _name_map

    p = config.data_dir() / "china_sectors" / "membership.parquet"
    if not p.exists():
        return None
    try:
        membership_df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("official-sector membership store unreadable (%s)", e)
        return None
    wide = _flow_panel()
    if wide is None:
        return None
    kmap = _name_kinetics_map(wide)
    l1_names = _l1_names()
    # M3/W4 repair: thread the SAME ticker->display-name map the curated lens already
    # uses so an official-sector excluded/missing entry shows a real name (the ticker
    # slug rides along in the entry's own LENS tip only) rather than a bare ticker.
    result = fo_groups.aggregate_lens(wide, kmap, membership_df, l1_names=l1_names,
                                      name_map=_name_map())
    if not result.get("available"):
        return result
    # same abs/rel/quadrant/rank contract the theme lens gets from contract.build_v2
    # (spec §2A "emitting the same per-row contract as themes") — reused here via
    # contract.py's PUBLIC functions, never a re-implementation.
    rows = result["rows"]
    for row in rows:
        row.update(fo_contract.enrich_group(row.get("rate_4wk"), row.get("vel"),
                                            abs_unit="pct_rate", abs_period="20d",
                                            reference_window=126))
    fo_contract.assign_ranks(rows)
    return result


def _apply_official_rank_change(rows: list[dict], ledger_rows: list[dict] | None,
                                market_session: str | None, cn_status: str | None) -> None:
    """M1/W4 repair: official_sectors rows never got ``rank_change``/``state_*`` —
    those fields are assigned to theme rows INSIDE ``contract.build_v2``'s own
    per-row loop, but ``official_sectors`` isn't part of that loop (it lives
    entirely in THIS builder, per OWNED-FILES scope: contract.py owns only the
    ``validate()`` extension this wave, never ``build_v2`` itself). Mutates ``rows``
    in place with the SAME ledger-derived shape themes get
    (``engine.flow_observatory.history.state_for_session``, entity_kind ``"sector"``,
    entity_id = the SW L1 code) once the ledger holds >=2 distinct sector sessions;
    until then every row gets ``rank_change=None`` + ``state_note="first tracked
    session"`` — a real value that stays honest as history accrues, NEVER a
    permanent dash by construction (there is no legacy sector state_log to fall back
    to, unlike themes, so there is only the one branch)."""
    from engine.flow_observatory import history as fo_history

    ledger_rows = ledger_rows or []
    ledger_ready = bool(ledger_rows) and fo_history.ledger_session_count(ledger_rows, "sector") >= 2
    for row in rows:
        rid = row.get("id")
        if ledger_ready and market_session and rid:
            hist = fo_history.state_for_session(
                ledger_rows, "sector", rid, market_session, row.get("quadrant"),
                current_rank=row.get("rank"), current_status=cn_status)
        else:
            hist = {"state_started": None, "state_age_sessions": None, "prior_state": None,
                   "rank_change": None, "note": "first tracked session"}
        row["rank_change"] = hist["rank_change"]
        row["state_started"] = hist["state_started"]
        row["state_age_sessions"] = hist["state_age_sessions"]
        row["prior_state"] = hist["prior_state"]
        row["state_note"] = hist["note"]


def _official_sector_ledger_entities(rows: list[dict] | None, cn_status: str | None) -> dict:
    """M1/W4 repair: official-sector observations for the append-only ledger —
    entity_kind ``"sector"``, entity_id = the SW L1 code — same
    ``{(entity_kind, entity_id): {<subset of FIELDS>}}`` shape ``theme_entities``
    already builds below, so both flow through the SAME guarded
    ``fo_history.append_observations`` call in ``main()`` (spec M1 "in the
    builder's guarded append", never a second append path)."""
    return {
        ("sector", r["id"]): {"vel": r.get("vel"), "abs_value": (r.get("abs") or {}).get("value"),
                              "quadrant": r.get("quadrant"), "state": r.get("state"),
                              "rank": r.get("rank"), "status": cn_status}
        for r in (rows or []) if r.get("id")
    }


def _attach_group_histories(candidate: dict, ledger_rows: list[dict] | None) -> None:
    """W6 (``research/flow_observatory/W6_SPEC.md`` §1/§3): attach a per-group
    ``row["history"]``/``row["episodes"]`` payload to every curated-theme row and, gated
    on the official lens' own accrual readiness, every official-sector row —
    ``engine.flow_observatory.workflow``'s pure functions do the actual computation;
    this is wiring only.

    OWNED-FILES scope keeps this assembly OUT of engine/flow_velocity.py and
    engine/flow_observatory/groups.py (same boundary ``_official_sectors_panel``
    already documents), so ``wide``/``kmap``/membership are recomputed a THIRD time in
    this build (once inside ``flow_velocity.snapshot()``, once inside
    ``_official_sectors_panel``, once here) — the added wall-clock cost is measured and
    reported in the PR body's performance note, matching the precedent
    ``_official_sectors_panel``'s own docstring already accepts for the same reason.

    Official-sector gate: a sector's row only gets a history/episodes panel when its
    OWN ``spark_accrual.ready`` is true (or it already carries a ``spark``) — the W4
    official lens applies TODAY's membership retroactively across the whole flow panel,
    so a REPLAY drawn from that backfill before real accrual covers the window would
    imply a composition depth the membership store has never actually held (the exact
    thing ``engine.flow_observatory.groups.aggregate_lens`` already refuses for the
    single-point spark — replay history for W6 refuses it identically, never a second,
    laxer rule for the SAME data).
    """
    try:
        import pandas as pd

        from engine.baskets_china import _membership as _curated_membership
        from engine.flow_velocity import WK, _flow_panel, _name_kinetics_map
        from engine.flow_velocity import _THEMES_VIN, _THEMES_VOUT
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("flow_observatory workflow: import failed (non-fatal): %s", e)
        return

    wide = _flow_panel()
    if wide is None:
        return
    kmap = _name_kinetics_map(wide)
    wide_cols = set(wide.columns)
    ledger_rows = ledger_rows or []

    # ── curated themes (spec §1: every group gets a history panel) ──────────────────
    theme_rows = (candidate.get("ashare_sectors") or {}).get("rows") or []
    if theme_rows:
        try:
            mem = _curated_membership() or {}
        except Exception as e:  # noqa: BLE001
            log.debug("flow_observatory workflow: curated membership unavailable (%s)", e)
            mem = {}
        baskets = mem.get("baskets") or {}
        for r in theme_rows:
            bid = r.get("id")
            b = baskets.get(bid)
            if not b:
                continue
            members = [m["ticker"] for m in b.get("members", [])
                      if isinstance(m, dict) and m.get("ticker") and not m.get("removed")]
            covered = [t for t in members if t in wide_cols and t in kmap]
            if len(covered) < fo_groups.MIN_COLS_FOR_KINETICS:
                continue
            sect_flow = wide[covered].mean(axis=1)
            full = fo_workflow.compute_full_series(sect_flow, WK, _THEMES_VIN, _THEMES_VOUT)
            hist = fo_workflow.history_panel(full, ledger_rows, "theme", bid)
            r["history"] = hist
            r["episodes"] = fo_workflow.select_episodes(full) if hist else []

    # ── official (Shenwan L1) sectors — accrual-gated (see docstring) ───────────────
    official_rows = (candidate.get("official_sectors") or {}).get("rows") or []
    if official_rows:
        p = config.data_dir() / "china_sectors" / "membership.parquet"
        membership_df = None
        if p.exists():
            try:
                membership_df = pd.read_parquet(p)
            except Exception as e:  # noqa: BLE001
                log.debug("flow_observatory workflow: sector membership unreadable (%s)", e)
        if membership_df is not None and not membership_df.empty:
            by_code, _ = fo_groups.resolve_active_membership(membership_df, as_of=None)
            for r in official_rows:
                accrual = r.get("spark_accrual") or {}
                if not (r.get("spark") or accrual.get("ready")):
                    continue  # not yet accrued — no replay before real history exists (spec §2A)
                code = r.get("id")
                members = by_code.get(code, [])
                covered = [t for t in members if t in wide_cols and t in kmap]
                if len(covered) < fo_groups.MIN_COLS_FOR_KINETICS:
                    continue
                sect_flow = wide[covered].mean(axis=1)
                full = fo_workflow.compute_full_series(sect_flow, WK, 0.5, -0.5)
                hist = fo_workflow.history_panel(full, ledger_rows, "sector", code)
                r["history"] = hist
                r["episodes"] = fo_workflow.select_episodes(full) if hist else []


def _strip_unpersisted_revisions(v2_snap: dict) -> bool:
    """M11: never publish ``change_summary.source_revisions[]`` receipts the ledger does not
    actually hold. ``preview_revisions`` runs BEFORE ``validate()`` (spec §2 ordering) so a
    valid payload's ``change_summary`` can already name this build's corrections — but the
    REAL, disk-writing append happens later, after validate() passes, and can itself fail
    (disk full, a monotonicity refusal, an I/O error) after some, none, or an unknown subset
    of its per-session calls already landed. Call this from that append's own except block:
    it zeroes the previewed receipts rather than guess which (if any) survived, so desk.json
    never claims a correction the ledger cannot back up. Returns True iff there was anything
    to strip (so the caller knows whether to also emit its own annotation).
    """
    cs = v2_snap.get("change_summary")
    if isinstance(cs, dict) and cs.get("source_revisions"):
        cs["source_revisions"] = []
        return True
    return False


def _leg_map(snap: dict) -> dict:
    """Flatten the desk payload into {display name: leg} for the staleness check.

    The payload is not uniform — ``aggregate`` is a list of channel dicts while
    the rest are single dicts — so the shape knowledge lives here and
    lib.desk_guard stays a pure date comparison it can share with other desks.
    """
    legs: dict[str, dict] = {}
    for chan in (snap.get("aggregate") or []):
        if isinstance(chan, dict) and chan.get("key"):
            legs[f"aggregate:{chan['key']}"] = chan
    for key in ("ashare_names", "ashare_sectors", "hk_names"):
        leg = snap.get(key)
        if isinstance(leg, dict):
            legs[key] = leg
    return legs


def _warn_if_stale(snap: dict) -> list[dict]:
    """Emit a GitHub annotation for any desk leg that stopped advancing.

    The alarm this desk did not have. ``site/flowdata/desk.json`` sat 12 days
    stale (A-share legs pinned at 2026-07-24 by a dark upstream Tushare plane)
    while declaring a DAILY cadence, and nothing anywhere went red: the artifact
    was rewritten nightly, so every mtime- and existence-based check read healthy.

    Annotations are bare ``print`` at column 0 with ``flush=True`` per repo law —
    this module runs inside an Actions step (asia-close), so it is not in the
    FastAPI exemption list in tests/test_gh_annotation_line_start.py, and a
    logger call here would be silently swallowed by the level prefix.
    """
    from datetime import date

    from lib.desk_guard import stale_legs

    findings = stale_legs(_leg_map(snap), today=date.today())
    for f in findings:
        if f["reason"] == "unreadable":
            print(f"::warning title=flow-velocity-stale::flow desk leg {f['leg']} has an "
                  f"unreadable as_of ({f['as_of']!r}) — the staleness guard cannot read it, "
                  f"so this leg is now unguarded. Fix the stamp or the guard in "
                  f"lib/desk_guard.stale_legs.", flush=True)
        elif f["reason"] == "desk_frozen":
            print(f"::warning title=flow-velocity-stale::flow desk is FROZEN — its freshest "
                  f"live leg ({f['leg']}) is {f['age_days']}d old (as_of {f['as_of']}). Every "
                  f"leg stopped advancing, so site/flowdata/desk.json is serving a stale "
                  f"vintage. Check the China/HK collectors in the asia lane.", flush=True)
        else:
            print(f"::warning title=flow-velocity-stale::flow desk leg {f['leg']} is "
                  f"{f['lag_days']}d behind the desk's freshest leg (as_of {f['as_of']}, "
                  f"{f['age_days']}d old) while declaring cadence "
                  f"{(_leg_map(snap).get(f['leg']) or {}).get('cadence') or 'daily'}. Its "
                  f"upstream store has stopped advancing — consumers that gate on freshness "
                  f"(engine/cn_theme_tape, 7d) will drop this leg's chips.", flush=True)
    if findings:
        log.warning("flow desk staleness: %d leg(s) flagged — %s",
                    len(findings), ", ".join(f"{f['leg']}:{f['reason']}" for f in findings))
    return findings


def _escalate_if_degraded(v2_snap: dict, log_rows: list | None = None,
                          run_date: str | None = None) -> None:
    """>=2-consecutive-RUN degradation escalates to ::error + a job-summary line in the
    asia-close lane (W2_SPEC.md §2) — never fails the job (additive lane law); the
    annotation IS the escalation surface. Bare column-zero print+flush, house annotation
    law (this module runs inside an Actions step, same as ``_warn_if_stale`` above).

    B2/SF-8 repair: the desk-wide gate (``should_escalate``, >=2 consecutive BUILD RUNS —
    see ``quality.consecutive_degraded_sessions``) is unchanged, but each bad leg's OWN
    printed count now comes from ``quality.leg_consecutive_bad_runs`` — a leg's own streak
    can differ from the desk's worst-of rollup (one leg may have been STALE for nine runs
    while another only just went DEGRADED today), so borrowing the desk-wide ``n`` for every
    leg was itself a false claim. The wording also changes from the false "for N sessions"
    (SF-8 — the counter was never sessions, and even the corrected session-based read would
    have been wrong) to "×N runs".
    """
    health = v2_snap.get("health") or {}
    if not fo_quality.should_escalate(health):
        return
    log_rows = log_rows or []
    bad_legs = [s for s in (v2_snap.get("sources") or [])
               if s.get("status") not in (None, fo_quality.HEALTHY, fo_quality.HISTORICAL_ONLY)]
    lines = []
    for leg in bad_legs:
        n = fo_quality.leg_consecutive_bad_runs(log_rows, leg.get("source_id"), run_date,
                                                leg.get("status"))
        line = (f"::error title=flow-observatory-degraded::{leg['source_id']} "
               f"{leg.get('status')} ×{n} runs")
        print(line, flush=True)
        lines.append(line)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path and lines:
        try:
            with open(summary_path, "a", encoding="utf-8") as fh:
                leg_names = ", ".join(b["source_id"] for b in bad_legs)
                fh.write(f"- flow-observatory degraded: {leg_names} — see annotations for "
                        f"each leg's own run streak\n")
        except OSError as e:  # noqa: BLE001 — the annotation above already fired
            log.warning("flow_observatory: could not append GITHUB_STEP_SUMMARY (%s)", e)


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    try:
        from engine.flow_velocity import snapshot
        snap = snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("flow_velocity engine failed: %s", e)
        return 0
    if not snap:
        log.warning("no flow-velocity data (run the China/Tushare collectors first) — skipping")
        return 0

    # W4: official (Shenwan L1) sector lens — additive, never fatal; a build with no
    # membership store yet (fresh checkout) still ships the curated-theme lens alone.
    try:
        t0 = datetime.now(timezone.utc)
        official = _official_sectors_panel()
        if official is not None:
            snap["official_sectors"] = official
        log.info("official-sector lens: %s (%.2fs)", "built" if official else "unavailable",
                 (datetime.now(timezone.utc) - t0).total_seconds())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("official-sector lens failed (non-fatal): %s", e)

    # Before the render: a template error returns 0 early (below), and the
    # staleness of the DATA is worth saying even on a night the page fails to
    # draw. Never fatal — an alarm that can sink the build is an alarm someone
    # eventually deletes.
    try:
        _warn_if_stale(snap)
    except Exception as e:  # noqa: BLE001
        log.warning("flow desk staleness check failed (non-fatal): %s", e)

    # flow_observatory.v2 — additive, never fatal (masterplan §3 builder contract): a
    # state_log/contract failure logs + SKIPS the v2 extensions rather than killing the
    # page build, but a payload that fails validate() never gets published — publishing a
    # contract-violating payload (a quadrant disagreeing with its own abs/rel directions,
    # a market_read with no denominator) is exactly the defect class this program exists
    # to kill, so on that one failure mode the plain (pre-v2) `snap` ships instead.
    data_root = config.data_dir()
    v2_snap = None
    run_date = None
    log_rows: list = []
    ledger_rows: list = []
    ledger_path = fo_history.observations_path(data_root)
    theme_entities: dict = {}
    # B1: a ledger that EXISTS but fails to parse must never be treated as an empty
    # bootstrap ledger — that reading is exactly what lets the ordinary append below
    # overwrite (destroy) a torn file's still-valid closed rows. Caught here, at the read
    # boundary, so both the revisions PREVIEW (further below) and the real append (much
    # further below, after validate()) skip together — never one without the other.
    ledger_unavailable = False
    try:
        log_rows = fo_changes.read_state_log(data_root)
        try:
            ledger_rows = fo_history.read_ledger(ledger_path)
        except fo_history.LedgerCorrupt as e:
            ledger_unavailable = True
            ledger_rows = []
            log.error("flow_observatory: observations ledger unreadable — refusing to "
                     "append; publishing without ledger features: %s", e)
            print("::warning title=flow-observatory-ledger::unreadable ledger — refusing "
                 "to append; publishing without ledger features", flush=True)
        generated_at_dt = datetime.now(timezone.utc)
        generated_at = generated_at_dt.isoformat(timespec="seconds")
        run_date = generated_at[:10]
        # B1: `now=generated_at_dt` — a real tz-aware UTC datetime, routed through the
        # calendars' own settle-buffer-aware expected_last_session (never a bare
        # `.date()` fed straight to an Asia calendar — the exact forbidden shape B1 closes).
        candidate = build_v2(snap, log_rows=log_rows, ledger_rows=ledger_rows,
                             market_session=snap.get("as_of"),
                             generated_at=generated_at, seats_as_of=snap.get("seats_as_of"),
                             now=generated_at_dt)
        current_themes = {
            r["id"]: {"quadrant": r.get("quadrant"), "state": r.get("state"),
                      "vel": r.get("vel"), "rank": r.get("rank"),
                      "abs": (r.get("abs") or {}).get("value")}
            for r in (candidate.get("ashare_sectors") or {}).get("rows") or []
            if r.get("id")
        }
        current_legs = {s["source_id"]: s.get("status") for s in (candidate.get("sources") or [])}
        # M1/W4 repair: official_sectors rows never flow through build_v2's own
        # per-row loop (that assembly lives entirely in THIS builder, see
        # _official_sectors_panel — contract.py's build_v2 is out of OWNED-FILES
        # scope this wave) — apply the SAME ledger-derived rank_change/state_*
        # fields here, in place, before validate() sees the final payload.
        official_rows = (candidate.get("official_sectors") or {}).get("rows") or []
        _apply_official_rank_change(official_rows, ledger_rows, candidate.get("market_session"),
                                    current_legs.get("cn_large_order_proxy"))
        # W6: per-group 60-session history/episodes drawer (spec §1/§3) — additive,
        # never fatal; a failure here must not sink a build that already produced a
        # valid v1/v2 payload.
        try:
            t_hist0 = datetime.now(timezone.utc)
            _attach_group_histories(candidate, ledger_rows)
            log.info("flow_observatory workflow (history/episodes): attached in %.2fs",
                     (datetime.now(timezone.utc) - t_hist0).total_seconds())
        except Exception as e:  # noqa: BLE001
            log.warning("flow_observatory workflow (history/episodes) failed (non-fatal): %s", e)
        # W3: theme observations this build would append to the ledger (the SAME shape
        # `_escalate_if_degraded`/state_log already read off `candidate` — status carries
        # cn_large_order_proxy's OWN current-session read, the input the ledger's
        # stale-freeze rule needs, spec §3 test 6). Built here (before validate()) so a
        # PREVIEW of any resulting revision can feed change_summary.source_revisions
        # without writing anything yet (spec §2 ordering — the real append happens only
        # after validate() passes, further below).
        theme_entities = {
            ("theme", tid): {"vel": rec.get("vel"), "abs_value": rec.get("abs"),
                             "quadrant": rec.get("quadrant"), "state": rec.get("state"),
                             "rank": rec.get("rank"), "status": current_legs.get("cn_large_order_proxy")}
            for tid, rec in current_themes.items()
        }
        # B1: a corrupt ledger skips BOTH the preview and the real append (below) — never
        # preview a "revision" against a ledger we have already refused to trust.
        revisions_preview = [] if ledger_unavailable else fo_history.preview_revisions(
            ledger_rows, candidate.get("market_session"), theme_entities, generated_at_dt)
        candidate["change_summary"] = fo_changes.compute_changes(
            {"session": candidate.get("market_session"), "themes": current_themes,
             "legs": current_legs}, log_rows, ledger_rows=ledger_rows, revisions=revisions_preview)
        validate(candidate)
        v2_snap = candidate
    except ContractError as e:
        log.error("flow_observatory.v2 contract validation failed — publishing WITHOUT the "
                  "v2 extensions this build: %s", e)
        print(f"::error title=flow-observatory-contract::flow_observatory.v2 payload failed "
              f"validation ({e}) — desk.json published without the v2 extensions this build.",
              flush=True)
    except Exception as e:  # noqa: BLE001 — additive: assembly failure must not sink the page
        log.warning("flow_observatory.v2 assembly failed (non-fatal, skipping v2 extensions): %s", e)
    if v2_snap is not None:
        snap = v2_snap
        # B2: log_rows here are the PRIOR runs (read before this run's candidate was built,
        # so they never include the current run) + run_date names the CURRENT run explicitly.
        _escalate_if_degraded(v2_snap, log_rows=log_rows, run_date=run_date)

    # W3: observations ledger append — AFTER validate() passes, BEFORE desk.json write
    # (spec §2 ordering); same lane gate as state_log (asia-close/US-nightly only,
    # append_observations is a no-op elsewhere); best-effort, never fatal — a ledger write
    # failure logs + annotates but must not sink a build that already produced a valid
    # payload. Appends every entity this build observed: the 22 themes (market_session),
    # the southbound aggregate (market_session), and each of the 5 source legs at ITS OWN
    # effective_date (never market_session — a leg's own date is what sources[].
    # first_known_at keys on, spec §1/§2).
    # B1: never attempt an append against a ledger already known to be unreadable this
    # build — `append_observations` would just re-raise LedgerCorrupt from its own
    # `read_ledger` call, and the point is to refuse cleanly, not to retry into the same
    # exception a second time.
    if v2_snap is not None and v2_snap.get("market_session") and theme_entities and not ledger_unavailable:
        try:
            agg_entities: dict = {}
            for chan in v2_snap.get("aggregate") or []:
                if chan.get("key") == "southbound" and chan.get("live"):
                    agg_entities[("aggregate", "southbound")] = {
                        "vel": chan.get("vel_primary"),
                        "abs_value": (chan.get("abs") or {}).get("value"),
                        "quadrant": chan.get("quadrant"), "state": chan.get("state"),
                        "status": current_legs.get("sb_aggregate")}
            # M1/W4 repair: official-sector observations ride the SAME guarded append
            # as themes — entity_kind "sector", entity_id = the SW L1 code, keyed on
            # market_session (the sector rollup is computed off the same daily flow
            # panel as the theme rollup, same effective session).
            sector_entities = _official_sector_ledger_entities(
                (v2_snap.get("official_sectors") or {}).get("rows"),
                current_legs.get("cn_large_order_proxy"))
            by_session: dict[str, dict] = {}
            by_session.setdefault(v2_snap["market_session"], {}).update(theme_entities)
            by_session.setdefault(v2_snap["market_session"], {}).update(sector_entities)
            by_session.setdefault(v2_snap["market_session"], {}).update(agg_entities)
            for s in v2_snap.get("sources") or []:
                sid, ed = s.get("source_id"), s.get("effective_date")
                if sid and ed:
                    by_session.setdefault(ed, {})[("market", sid)] = {
                        "status": s.get("status"),
                        "coverage_n": (s.get("coverage") or {}).get("n_observed")}
            total_added = 0
            for sess, ents in by_session.items():
                if not sess or not ents:
                    continue
                res = fo_history.append_observations(ledger_path, sess, ents, generated_at_dt)
                if res.get("written"):
                    total_added += res.get("rows_added", 0)
            if total_added:
                log.info("flow_observatory: observations ledger advanced (+%d rows)", total_added)
        except Exception as e:  # noqa: BLE001 — additive lane law, same as state_log below
            log.warning("flow_observatory observations ledger append failed (non-fatal): %s", e)
            print("::warning title=flow-observatory-ledger::observations ledger append "
                 f"failed ({e}) — desk.json publishes normally this build; state age/"
                 "replay history may lag one build.", flush=True)
            # M11: `revisions_preview` (computed BEFORE validate(), spec §2 ordering) already
            # sits inside v2_snap["change_summary"]["source_revisions"] — but the append that
            # was SUPPOSED to actually persist those corrections just failed above (possibly
            # partway through the per-session loop, so some, none, or all of them may have
            # landed). Publishing the previewed receipts anyway would claim the ledger holds
            # a correction it may not — strip them rather than guess which (if any) survived.
            if _strip_unpersisted_revisions(v2_snap):
                print("::warning title=flow-observatory-ledger::append failure — "
                     "source_revisions[] stripped from this build's change_summary (the "
                     "ledger does not hold what was previewed)", flush=True)

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr)
    except Exception:  # noqa: BLE001
        env.globals.update(td=lambda en: en, tr=lambda en: en)
    from engine.flow_observatory.contract import QUADRANT_LABELS, STATUS_WORD
    env.globals.update(quadrant_labels=QUADRANT_LABELS, status_word=STATUS_WORD)

    try:
        from scripts.build_vector import C  # shared palette
    except Exception:  # noqa: BLE001
        C = {}

    try:
        html = env.get_template("flow_velocity.html.j2").render(C=C, snap=snap, built=built)
    except Exception as e:  # noqa: BLE001 — a template error must not sink the China build
        log.error("flow_velocity render failed: %s", e)
        return 0
    write_page(site / "flow_velocity.html", html)

    # small JSON payload (parity with the other desks; handy for a future hub card)
    try:
        fdir = site / "flowdata"
        fdir.mkdir(parents=True, exist_ok=True)
        (fdir / "desk.json").write_text(
            json.dumps(snap, separators=(",", ":"), ensure_ascii=False, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("flow_velocity json payload failed: %s", e)

    # state_log.jsonl advance — lane-gated (asia-close/US-nightly only; append_state_log
    # is a no-op elsewhere), idempotent per session, best-effort. Reflects what actually
    # got PUBLISHED above, never a payload that failed validate().
    if v2_snap is not None and v2_snap.get("market_session"):
        try:
            themes_entry = {
                r["id"]: {"quadrant": r.get("quadrant"), "state": r.get("state"),
                          "vel": r.get("vel"), "rank": r.get("rank"),
                          "abs": (r.get("abs") or {}).get("value")}
                for r in (v2_snap.get("ashare_sectors") or {}).get("rows") or []
                if r.get("id")
            }
            health_entry = {"publication_state": v2_snap.get("publication_state"),
                            "legs": fo_contract.state_log_legs_snapshot(v2_snap.get("sources") or [])}
            entry = {"themes": themes_entry, "aggregate": {},
                    "market_read": v2_snap.get("market_read") or {}, "health": health_entry}
            res = fo_changes.append_state_log(v2_snap["market_session"], entry, data_root)
            if res.get("written"):
                log.info("flow_observatory: state_log advanced (%d rows)", res.get("rows", 0))
        except Exception as e:  # noqa: BLE001
            log.warning("flow_observatory state_log append failed (non-fatal): %s", e)

    n_sec = len((snap.get("ashare_sectors") or {}).get("rows", []))
    n_names = (snap.get("ashare_names") or {}).get("n", 0)
    log.info("wrote %s/flow_velocity.html (%d sectors, %d names, %d KB)",
             site, n_sec, n_names, len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
