"""scripts/grade_qledger.py — nightly qledger grading job (§2.2 W1-B1).

Desk-independent: loads every open claim from data/qledger/claims.jsonl, grades
each at every in-scope horizon (5/21/63d capped by claim horizon_d) once enough
trading days have elapsed and price coverage exists, then writes the result to
data/qledger/grades.jsonl and updates site/qledger/track_record.json.

IDEMPOTENT: a (claim_id, horizon_d) pair that already has a grade row is never
double-graded. Re-running the job on the same day is safe.

HEALTH: always emits a one-line summary to stdout and writes
data/qledger/run_status.json — broken != quiet.

POST-STEP — W6 PROMOTION-READINESS MONITOR:
    After emit_ladder_states(), compute_promotion_readiness() runs for every
    claim family listed in config/qual_ladder.yml. It writes:
      • site/qledger/track_record.json["promotion_readiness"] — per family×horizon
        {n_dates, needed:25, wilson_ci_low, hit_rate, excess_mean, ready, approaching,
         projected_ready_date}.
      • data/qledger/run_status.json["w6_readiness"] — summary (n_families_ready,
        n_families_approaching, families_ready[]).
    On first-cross ready=True for any family, a Telegram/Discord alert fires once
    (fired state persisted in data/qledger/readiness_alerts_fired.json so it does
    not re-fire nightly); when a family×horizon later reads ready=False its key
    is released, so a genuine re-cross alerts again — an entry from a
    since-withdrawn gate must not suppress the honest cross forever.
    A grader-quiet alert fires if n_graded_today==0 for two
    consecutive days when open claims exist (checked in the summary as
    grader_quiet_days).

WIRING (end-of-collect hook):
    The job is registered as an end-of-collect step in scripts/collect.py, so it
    runs nightly as part of the collection pipeline without a separate scheduler.
    It is also runnable standalone:

        python scripts/grade_qledger.py            # use repo root
        python scripts/grade_qledger.py --root /other/root
        python scripts/grade_qledger.py --dry-run  # compute only, no writes

PRICE FALLBACK ORDER (reusing engine.ai_desk._close_series):
  1. data/yahoo/<ticker>.parquet  — ~153 major names, SPY/XL* etc.
  2. S&P-1500 breadth-cache       — wider coverage for entity claims
  3. data/baskets/ohlcv/<ticker>.parquet — per-member basket OHLCV
  4. 510300.SS parquet            — CN macro bench (via breadth cache or yahoo)

If subject OR bench price is unavailable the horizon is counted in
n_blocked_by_coverage (not silently dropped) and the run_status records it.
Ungradeable claims (EVENT_DATE/SNAPSHOT_DATE timestamp_quality) are counted in
n_ungradeable.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Allow running as a top-level script (`python scripts/grade_qledger.py`).
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import qledger as q
# lib/config is DEFERRED to call time on purpose: this module is a seed of the
# admin panel's load-time closure (the Intelligence OS evidence view calls
# compute_promotion_readiness per request), and lib/config is a declared
# non-admin lane — see ADMIN_MUST_NOT_RESTART in
# tests/test_deploy_update_self_heal.py. A module-level import here would
# restart the admin panel on every API/site-build config change.

log = logging.getLogger("grade_qledger")

_STATUS_FILE = ("data", "qledger", "run_status.json")
_READINESS_FIRED_FILE = ("data", "qledger", "readiness_alerts_fired.json")
_QUIET_LOG_FILE = ("data", "qledger", "grader_quiet_log.json")

# ──────────────────────────────────────────────────────────────────────────────
# W6 READINESS HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _load_qual_ladder_families(root: Path) -> list[str]:
    """Parse config/qual_ladder.yml to extract the authoritative set of
    claim_family values. Returns them sorted and deduplicated.
    Falls back to an empty list if the file is absent or unparseable (non-fatal).
    """
    yml_path = root / "config" / "qual_ladder.yml"
    if not yml_path.exists():
        return []
    families: set[str] = set()
    try:
        text = yml_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("claim_family:"):
                val = line.split(":", 1)[1].strip()
                if val and not val.startswith("#"):
                    families.add(val)
    except Exception as e:  # noqa: BLE001
        log.warning("_load_qual_ladder_families: failed to parse qual_ladder.yml: %s", e)
    return sorted(families)


def _accrual_rate_per_day(grades: list[dict], claims: list[dict],
                          family: str, horizon: int,
                          trailing_days: int = 14,
                          clock_basis: str | None = None) -> float | None:
    """Estimate the rate of NEW independent date clusters accruing per calendar day
    over the trailing `trailing_days` window. Returns None when insufficient data.
    Used for projected_ready_date linear extrapolation.

    P0a: pass `clock_basis` to count only rows on the basis the gate evaluates.
    Counting both bases would project a family onto a 25-date bar it is not
    accruing toward — during the migration the legacy rows still land nightly
    (unitless claims already registered keep maturing) while only the explicit
    ones count, so a pooled rate reads roughly double and the projected ready
    date lands early. None (the default) counts every row, unchanged.
    """
    cid_meta = {
        c["claim_id"]: c for c in claims
        if c.get("claim_id") and (c.get("claim_family") or c.get("desk")) == family
        and not c.get("is_placebo")
    }
    if not cid_meta:
        return None

    today_dt = date.today()
    cutoff = datetime(today_dt.year, today_dt.month, today_dt.day,
                      tzinfo=timezone.utc) - __import__("datetime").timedelta(days=trailing_days)

    recent_dates: set[str] = set()
    for g in grades:
        if int(g.get("horizon_d", -1)) != horizon:
            continue
        if clock_basis is not None and q.grade_clock_basis(g) != clock_basis:
            continue
        c = cid_meta.get(g.get("claim_id"))
        if c is None:
            continue
        graded_at = g.get("graded_at", "")
        try:
            gts = datetime.fromisoformat(graded_at)
            if gts >= cutoff:
                recent_dates.add(q._date_cluster(c.get("asof", "")))
        except Exception:  # noqa: BLE001
            continue

    if not recent_dates:
        return None
    rate = len(recent_dates) / trailing_days   # dates / calendar-day
    return rate if rate > 0 else None


def _projected_ready_date(n_dates: int, rate_per_day: float | None) -> str | None:
    """Linear projection: days_needed / rate → ISO date. Returns None when rate ~0."""
    needed = q.PROMOTION_MIN_DATES - n_dates
    if needed <= 0 or rate_per_day is None or rate_per_day < 1e-6:
        return None
    days = math.ceil(needed / rate_per_day)
    from datetime import timedelta
    proj = date.today() + timedelta(days=days)
    return proj.isoformat()


def compute_promotion_readiness(root: Path, families: list[str] | None = None,
                                today: date | str | None = None) -> dict:
    """Compute W6 promotion-readiness metrics for each claim family × grade horizon.

    For each (family, horizon):
      - n_dates:              independent date clusters graded so far
      - needed:               25 (PROMOTION_MIN_DATES constant)
      - wilson_ci_low:        Wilson CI lower bound (None if no directional grades)
      - hit_rate:             directional hit-rate (None if salience-only)
      - excess_mean:          mean excess return (None if no grades)
      - ready:                n_dates>=25 AND wilson_ci_low>0.5 (§3 gate — the bound is a
                              hit-rate PROPORTION, so 0.5 is the coin-flip null; the former
                              `>0` was cleared by any nonzero hit count)
      - approaching:          n_dates>=20 AND not ready (5-date warning window)
      - projected_ready_date: linear estimate from trailing-14d accrual rate (or None)

    Placebo tape duel summary per horizon (duel_context):
      champion vs challenger vs placebo |excess| at 5d — the key decision evidence
      for the human reviewer in the admin Experiments tab.

    `today` — the run's point-in-time reference (F5). `--today` already reached
    `grade_claim`; it did not reach the matched-control gate, so a replay graded
    against date T while cohort maturity was judged against `date.today()` —
    two dates inside one run, in the very classification (C4.4's
    `cohort_rowless`) whose job is to say WHY a row is missing. Defaults to
    `date.today()`, so an ordinary nightly is byte-identical.

    Returns a dict: {family: {horizon_str: {…}, …}, "_duel_context": {…}}
    """
    root = Path(root)
    claims = q.load_claims(root)
    grades = q.load_grades(root)

    if families is None:
        families = _load_qual_ladder_families(root)

    # P0d C5.4/C9 — a `matched_control_required` family is ALWAYS enumerated,
    # whether or not `config/qual_ladder.yml` lists it yet. The two required
    # families are prospective-only and carry zero rows today, so without this
    # union their coverage (and the honest "evidence has not begun accruing"
    # state) would be invisible in the nightly readiness payload until some
    # unrelated ladder edit happened to add them. The union is applied to a
    # CALLER-SUPPLIED list too: `run_readiness_post_step` passes the ladder
    # families explicitly, so unioning only in the `None` branch would leave the
    # production path — the one that writes track_record.json — blind.
    families = sorted(set(families) | {
        f for f, p in q.FAMILY_CONTROL_POLICY.items()
        if p == q.CONTROL_POLICY_REQUIRED})

    def _readiness_row(pr, fam: str, h: int) -> dict:
        """One readiness row for a single PromotionResult. Factored out (round
        5 / MAJOR 2) so a per-market sub-result gets IDENTICAL treatment to the
        pooled-default one — same accrual-rate/projection/track-record read,
        never a shortcut for the market that is not the headline."""
        rate = _accrual_rate_per_day(grades, claims, fam, h,
                                     clock_basis=pr.clock_basis)
        proj = _projected_ready_date(pr.n_dates, rate)
        basis = getattr(pr, "evidence_basis", None)
        # P0d C5.3 (review round 1, note 14): a `not_applicable` family is
        # STRUCTURALLY unpromotable — there is no directional proposition to
        # promote — so it can never be "approaching" a gate it will never take.
        # A salience family sitting at n_dates=24 read as five dates from a
        # promotion that cannot exist, in the same payload the operator alert
        # reads.
        approaching = (pr.n_dates >= 20 and not pr.eligible
                       and basis != q.EVIDENCE_BASIS_NOT_APPLICABLE)

        # hit_rate and excess_mean from track record aggregation.
        # P0a: `_aggregate` is FAIL-CLOSED on a mixed grading-clock basis —
        # calling it without a basis raises HorizonClockMismatch the first
        # night any ladder family holds both the legacy and the explicit
        # clock, which is this nightly step's normal state during the
        # migration. The basis is therefore always named, and it is the SAME
        # basis promotion_check just gated on (pr.clock_basis), so n_dates /
        # wilson_ci_low / hit_rate / excess_mean in one row all describe one
        # clock. None means there was nothing coherent to evaluate (no rows,
        # or a family mixing two explicit clocks) — report the null, never a
        # pooled number.
        fam_stats: dict = {}
        if pr.clock_basis is not None:
            stats = q._aggregate(claims, grades, "family", h,
                                 clock_basis=pr.clock_basis)
            fam_stats = stats.get(fam, {})

        # P0d C6.1/C5.1 (review round 1, finding 3) — TWO BASES MAY NEVER SHARE
        # ONE UNLABELLED SENTENCE. `_aggregate` measures the WHOLE family
        # BENCH-relative on this clock basis: every pre-clock row, every
        # uncontrolled row, every row outside the matched cohort. On a
        # matched-control verdict those numbers sat in `hit_rate` / `excess_mean`
        # right beside `n_dates`, `wilson_ci_low` and `control_coverage` computed
        # over the CONTROLLED COHORT ONLY — one row, two populations, no label.
        # The reviewer's repro published `evidence_basis=matched_control`,
        # `wilson_ci_low=0.886` (cohort, 30/30) and `hit_rate=0.4286` (whole
        # family, 30 of 70) in the same record, and a reader has no way to know
        # they describe different things. The bench numbers are still published —
        # C5.1 requires the labelled baseline — but under `benchmark_baseline_*`
        # names, which is what makes keeping the pre-clock rows in them honest
        # (C3.3: history is disclosed, never combined with cohort evidence).
        matched = (basis == q.EVIDENCE_BASIS_MATCHED_CONTROL)
        _base_keys = ("hit_rate", "excess_mean", "mean_abs_excess",
                      "excess_basis", "excess_mean_by_direction")
        headline = {k: (None if matched else fam_stats.get(k)) for k in _base_keys}
        baseline = {f"benchmark_baseline_{k}": (fam_stats.get(k) if matched else None)
                    for k in _base_keys}

        return {
            "n_dates": pr.n_dates,
            "needed": q.PROMOTION_MIN_DATES,
            "wilson_ci_low": pr.wilson_ci_low,
            # V1: _aggregate owns the legality gate, so excess_mean is already
            # None for a mixed-direction family; the basis + magnitude +
            # per-direction split travel with it so the admin surface can say
            # WHY rather than dash.
            **headline,
            # C5.1's "benchmark_baseline", realized. Populated only on a
            # matched-control verdict, where it is the labelled baseline beside
            # the authority basis; None elsewhere, where the unprefixed keys
            # already ARE the benchmark reading.
            **baseline,
            "ready": pr.eligible,
            "approaching": approaching,
            "projected_ready_date": proj,
            "reason": pr.reason,
            # The clock these four numbers were measured on. Same n_dates on
            # a different clock is a different claim about the world.
            "clock_basis": pr.clock_basis,
            # P0a MIGRATION LEGIBILITY. A family whose first explicit-clock
            # grade lands drops from (say) GRADED/n_dates=40 to
            # ACCRUING/n_dates=1 in one night, because authority resets at a
            # basis change rather than pooling across it (the CEO's ruling,
            # unchanged). Without these three fields the readiness row, the
            # alert and the admin tab all read that as evidence collapsing.
            # The counts are NEVER combined — `clock_prior_n_dates` is the
            # excluded basis's own number, published beside the live one.
            "clock_migration": pr.clock_migration,
            "clock_prior_n_dates": pr.clock_prior_n_dates,
            "migration_note": pr.migration_note,
            # P0d C5.4 — THE EVIDENCE BASIS TRAVELS WITH THE NUMBERS. Without
            # these, a readiness row stating n_dates and a hit rate says nothing
            # about WHICH baseline produced them, and "benchmark-relative" and
            # "matched-control" read as the same sentence (C6.1). For a
            # matched-control verdict the coverage pair is part of the evidence,
            # not a diagnostic: n_dates here IS n_controlled_dates, and the
            # cohort counts disclose what it is a fraction of.
            "evidence_basis": getattr(pr, "evidence_basis", None),
            "control_coverage": getattr(pr, "control_coverage", None),
            "n_cohort_dates": getattr(pr, "n_cohort_dates", None),
            "n_controlled_dates": getattr(pr, "n_controlled_dates", None),
            "n_cohort_rows": getattr(pr, "n_cohort_rows", None),
            "n_controlled_rows": getattr(pr, "n_controlled_rows", None),
            # P0d review finding 4 — a cohort claim whose DECLARED control could
            # not be priced over the shared window has NO grade row at all, so it
            # used to vanish from the coverage denominator: declaring an
            # unpriceable control read BETTER than declaring none. These three
            # publish the repair — the refused set is counted INTO
            # `n_cohort_rows`/`n_cohort_dates` above, and `cohort_rowless` is the
            # full reason census for every rowless cohort claim so a young cohort
            # is legible as young rather than as broken (or vice versa).
            "n_control_refused_rows": getattr(pr, "n_control_refused_rows", None),
            "n_control_refused_dates": getattr(pr, "n_control_refused_dates", None),
            "cohort_rowless": getattr(pr, "cohort_rowless", None),
            "control_clock_start": getattr(pr, "control_clock_start", None),
            "unclassified": getattr(pr, "unclassified", False),
        }

    result: dict[str, dict] = {}
    for fam in families:
        policy, classified = q.family_control_policy(fam)
        fam_res: dict[str, dict] = {}
        for h in q.GRADE_HORIZONS:
            # P0d C5.4: dispatch by the family's governed control policy. The
            # blanket `control_only=True` call — which evaluated every family
            # "vs matched control" against a store holding zero control legs —
            # is gone from production.
            pr = q.promotion_check_dispatch(fam, h, root=root, today=today)
            entry = _readiness_row(pr, fam, h)
            # P0a MAJOR 2 (round 5): `promotion_check`'s pooled default refuses
            # a bi-market family as STATE_MIXED_CLOCK, correctly — but this is
            # a production call path that feeds the admin Experiments tab, so
            # a family stuck here read as permanently un-promotable on EITHER
            # market even though `clock_basis=...` reaches each one. Nothing
            # is pooled: `by_clock_basis` adds each market's OWN readiness row
            # beside the refused pooled one.
            #
            # P0d: each family re-enters on its OWN evidence basis. A
            # benchmark/not_applicable family goes back through
            # `promotion_check_by_market` (`control_only=False`) with the same
            # policy label applied to each sub-result — a per-market cell must
            # not be the one place an unlabelled (or, for a `not_applicable`
            # family, an eligible) verdict escapes. A REQUIRED family goes back
            # through `matched_control_check(clock_basis=...)`, so its per-basis
            # cells stay matched-control and can never fall onto a bench basis by
            # taking the per-market route.
            #
            # (review round 1, finding 7) THIS PAYLOAD AND `ladder_states` MUST
            # AGREE. `emit_ladder_states` already minted per-basis matched
            # verdicts for a bi-market required family while this path emitted
            # only the refused pooled one — so the admin Experiments tab and the
            # readiness alerting, which read THIS payload, would have reported a
            # required family as permanently un-promotable on both markets while
            # track_record.json said otherwise. Same enumeration, same rule,
            # never CLOCK_LEGACY (P0c-2: legacy cannot originate authority).
            per_basis: dict = {}
            if policy == q.CONTROL_POLICY_REQUIRED:
                if pr.current_state == q.STATE_MIXED_CLOCK:
                    per_basis = {
                        b: q.matched_control_check(fam, h, root=root, clock_basis=b,
                                                   today=today)
                        for b in sorted(pr.clock_prior_n_dates or {})
                        if b != q.CLOCK_LEGACY
                    }
            else:
                per_basis = {
                    b: q._apply_policy_label(mpr, policy, classified)
                    for b, mpr in q.promotion_check_by_market(
                        fam, h, pr, root=root, control_only=False).items()
                }
            if per_basis:
                entry["by_clock_basis"] = {
                    b: _readiness_row(mpr, fam, h)
                    for b, mpr in per_basis.items()
                }
            fam_res[str(h)] = entry
        result[fam] = fam_res

    # Duel context: champion vs placebo |excess| at 5d from the track record
    # This is the key decision evidence visible in the admin Experiments tab.
    duel_context: dict[str, dict] = {}
    tr_path = root.joinpath(*q._TRACK_FILE)
    try:
        tr = json.loads(tr_path.read_text(encoding="utf-8")) if tr_path.exists() else {}
        placebo = (tr.get("placebo_magnitude") or {}).get("5", {})
        placebo_covered = (placebo.get("covered_ticker") or {}).get("mean_abs_excess")
        # P0a — THE DUEL'S TWO SIDES ARE SELECTED INDEPENDENTLY, so they can
        # land on DIFFERENT clock bases. `challenger_excess_mean_5d` comes from
        # a `_select_single_clock_block` cell and `placebo_covered_abs_excess_5d`
        # from `_placebo_magnitude`'s own separately-selected cell; each picks
        # the basis with the most observations, and during a migration those are
        # not the same basis at the same moment. Comparing a challenger measured
        # on 5 exchange sessions against a placebo measured on 5 CALENDAR days
        # is the pooling this contract forbids, wearing a comparison's clothes —
        # and this pair is the D3 counterfactual, rendered verbatim into the
        # admin Experiments tab. Neither basis used to be recorded at all, so
        # the mismatch was not merely unguarded, it was invisible.
        placebo_basis = placebo.get("clock_basis")
        by_family = tr.get("by_family") or {}
        for fam in families:
            h5 = (by_family.get(fam) or {}).get("5") or {}
            challenger_basis = h5.get("clock_basis")
            # Comparable only when BOTH sides name a basis and the bases match.
            # Unknown-vs-anything is not comparable either: an unstamped side is
            # a side whose clock we cannot name, and "unknown" matches nothing.
            comparable = (challenger_basis is not None
                          and placebo_basis is not None
                          and challenger_basis == placebo_basis)
            duel_context[fam] = {
                "challenger_excess_mean_5d": h5.get("excess_mean"),
                # The placebo side of this duel has ALWAYS been a |excess|, so for a
                # mixed-direction family — where the signed mean is now withheld —
                # the magnitude leg is both the legal reading and the like-for-like
                # one. `challenger_excess_basis_5d` tells the renderer which side of
                # the duel it is allowed to print.
                "challenger_abs_excess_5d": h5.get("mean_abs_excess"),
                "challenger_excess_basis_5d": h5.get("excess_basis"),
                "placebo_covered_abs_excess_5d": placebo_covered,
                "n_dates_5d": h5.get("n_dates", 0),
                "wilson_ci_low_5d": h5.get("wilson_ci_low"),
                "challenger_clock_basis": challenger_basis,
                "placebo_clock_basis": placebo_basis,
                "duel_comparable": comparable,
            }
            if not comparable:
                # Say WHY, in the record, rather than leaving a reader to infer
                # it from two basis strings. The numbers stay — they are each
                # honest on their own basis — but the COMPARISON is withdrawn.
                duel_context[fam]["duel_not_comparable_reason"] = (
                    f"challenger measured on {challenger_basis or 'an unstamped clock'}, "
                    f"placebo on {placebo_basis or 'an unstamped clock'}; a duel "
                    f"across two grading clocks is not a comparison")
    except Exception as e:  # noqa: BLE001
        log.debug("compute_promotion_readiness: duel_context build failed: %s", e)

    result["_duel_context"] = duel_context
    return result


def _summarise_readiness(readiness: dict) -> tuple[list[str], list[str]]:
    """(families_ready, families_approaching) for `run_status.json` and the
    first-cross operator alert.

    EXTRACTED FROM `main()` DELIBERATELY. This was eight inline lines inside a
    500-line entry point, which is why the defect below shipped: nothing could
    reach it to test it, so "the per-market promotion fix works" was only ever
    checked at the layer that produces the data, never at the layer that reads it.

    P0a — READ THE PER-MARKET ROWS. `promotion_check_by_market` exists because
    the pooled default refuses a bi-market family as STATE_MIXED_CLOCK, so
    `rec["ready"]` is False for it even when BOTH markets have independently
    cleared the 25-date bar. That fix wrote `by_clock_basis` into
    track_record.json and stopped — this summary and the first-cross alert read
    only the top-level `ready`, so a family promotable on two markets reported
    nothing and no operator was ever told. Fixing it one layer up and leaving it
    broken one layer down is not fixing it.

    NOTHING IS POOLED OR SUMMED. Each basis contributes its OWN row under its
    own key (`fam@21d[explicit_unit_v1:trading_days:CN]`), so the alert names
    the market it crossed on, and the pooled key stays absent because the pooled
    verdict is still a refusal. The key space is new, so a first cross alerts
    once, exactly like any other new family×horizon.

    THE LEGACY BASIS IS SKIPPED HERE TOO. `promotion_check_by_market` already
    excludes it; this excludes it again rather than trusting an upstream filter
    it does not own — a summary that would happily print a legacy `GRADED` cell
    if the producer ever regressed is not a guard.
    """
    families_ready: list[str] = []
    families_approaching: list[str] = []
    for fam, horizons in readiness.items():
        if fam.startswith("_"):
            continue
        for h_str, rec in (horizons or {}).items():
            if rec.get("ready"):
                families_ready.append(f"{fam}@{h_str}d")
            elif rec.get("approaching"):
                families_approaching.append(f"{fam}@{h_str}d")
            for basis, brec in (rec.get("by_clock_basis") or {}).items():
                if basis == q.CLOCK_LEGACY:
                    continue      # authority is never granted on the legacy clock
                key = f"{fam}@{h_str}d[{basis}]"
                if brec.get("ready"):
                    families_ready.append(key)
                elif brec.get("approaching"):
                    families_approaching.append(key)
    return families_ready, families_approaching


def _load_fired(root: Path) -> dict:
    p = root.joinpath(*_READINESS_FIRED_FILE)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_fired(root: Path, fired: dict) -> None:
    p = root.joinpath(*_READINESS_FIRED_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fired, ensure_ascii=False, indent=2), encoding="utf-8")


def _fire_readiness_alert(family: str, horizon: int, rec: dict) -> None:
    """Send Telegram+Discord alert for a first-cross ready=True. Non-fatal."""
    msg = (
        f"🔔 <b>W6 gate OPEN: {family} @ {horizon}d</b>\n"
        f"n_dates={rec['n_dates']}, CI-low={rec['wilson_ci_low']}\n"
        f"§3 promotion experiment runnable — see "
        f"QUALITATIVE_INTELLIGENCE_UPGRADE_BY_FABLE.md §4 W6\n"
        f"→ admin Experiments tab: https://admin.mastermind-x.com"
    )
    try:
        from scripts import notify
        notify.send_telegram(msg)
        notify.send_discord(msg)
        log.info("readiness alert fired: family=%s horizon=%d", family, horizon)
    except Exception as e:  # noqa: BLE001
        log.warning("readiness alert send failed: %s", e)


def _fire_grader_quiet_alert(n_open: int, quiet_days: int) -> None:
    """Send a warn-level alert when the grader has been quiet for quiet_days
    while open claims exist. Non-fatal."""
    msg = (
        f"⚠️ <b>qledger grader quiet {quiet_days}d</b>\n"
        f"n_graded_today=0 for {quiet_days} consecutive days with {n_open} open claims.\n"
        f"Broken ≠ quiet — check scripts/grade_qledger.py and data/qledger/run_status.json."
    )
    try:
        from scripts import notify
        notify.send_telegram(msg)
        notify.send_discord(msg)
        log.warning("grader-quiet alert fired: quiet_days=%d n_open=%d", quiet_days, n_open)
    except Exception as e:  # noqa: BLE001
        log.warning("grader-quiet alert send failed: %s", e)


def _update_grader_quiet_log(root: Path, n_graded_today: int, n_open: int) -> int:
    """Track consecutive days of n_graded_today==0 with open claims.
    Returns the current consecutive_quiet_days count. Updates the log file."""
    p = root.joinpath(*_QUIET_LOG_FILE)
    today = date.today().isoformat()
    try:
        state = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:  # noqa: BLE001
        state = {}

    if n_graded_today == 0 and n_open > 0:
        # Accumulate quiet days; avoid double-counting same calendar day
        last_quiet_date = state.get("last_quiet_date")
        if last_quiet_date == today:
            # Already counted today — no change
            return state.get("consecutive_quiet_days", 1)
        state["consecutive_quiet_days"] = state.get("consecutive_quiet_days", 0) + 1
        state["last_quiet_date"] = today
    else:
        state["consecutive_quiet_days"] = 0
        state["last_quiet_date"] = today

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.debug("_update_grader_quiet_log write failed: %s", e)
    return state.get("consecutive_quiet_days", 0)


def run_readiness_post_step(root: Path, n_graded_today: int, n_open: int,
                             dry_run: bool = False,
                             today: date | str | None = None) -> dict:
    """W6 promotion-readiness post-step. Called after emit_ladder_states().

    1. Computes per-family×horizon readiness metrics.
    2. Merges them into site/qledger/track_record.json["promotion_readiness"].
    3. Returns a summary dict for inclusion in run_status.json["w6_readiness"].
    4. Fires first-cross Telegram/Discord alerts (deduped via readiness_alerts_fired.json).
    5. Checks grader-quiet condition (n_graded_today==0 for >=2 days with open claims).

    Non-fatal — any crash returns an error summary without affecting grades.
    """
    try:
        families = _load_qual_ladder_families(root)
        readiness = compute_promotion_readiness(root, families, today=today)

        # Merge into track_record.json
        if not dry_run:
            tr_path = root.joinpath(*q._TRACK_FILE)
            try:
                payload: dict = json.loads(tr_path.read_text(encoding="utf-8")) \
                    if tr_path.exists() else {}
            except Exception:  # noqa: BLE001
                payload = {}
            payload["promotion_readiness"] = readiness
            payload["promotion_readiness_at"] = datetime.now(timezone.utc).isoformat()
            tr_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                               encoding="utf-8")

        # Summary for run_status.json
        families_ready, families_approaching = _summarise_readiness(readiness)

        # First-cross alert (two-sided dedup: a family×horizon that drops back
        # to ready=False releases its key, so a later genuine re-cross alerts
        # again — otherwise an entry fired under a since-withdrawn gate would
        # suppress the honest cross forever)
        if not dry_run:
            fired = _load_fired(root)
            fired_dirty = False
            for fam, horizons in readiness.items():
                if fam.startswith("_"):
                    continue
                for h_str, rec in horizons.items():
                    key = f"{fam}@{h_str}d"
                    if rec.get("ready") and not fired.get(key):
                        _fire_readiness_alert(fam, int(h_str), rec)
                        fired[key] = {
                            "fired_at": datetime.now(timezone.utc).isoformat(),
                            "n_dates": rec["n_dates"],
                            "wilson_ci_low": rec["wilson_ci_low"],
                        }
                        fired_dirty = True
                    elif not rec.get("ready") and key in fired:
                        log.info("readiness dedup released: %s ready=False "
                                 "(ci_low=%s) — will alert on next cross",
                                 key, rec.get("wilson_ci_low"))
                        del fired[key]
                        fired_dirty = True
            if fired_dirty:
                _save_fired(root, fired)

        # Grader-quiet check
        quiet_days = 0
        if not dry_run:
            quiet_days = _update_grader_quiet_log(root, n_graded_today, n_open)
            if quiet_days >= 2:
                # Only alert once per quiet episode (use fired map as dedup)
                fired = _load_fired(root)
                alert_key = f"__grader_quiet_{date.today().isoformat()}"
                if not fired.get(alert_key):
                    _fire_grader_quiet_alert(n_open, quiet_days)
                    fired[alert_key] = {"fired_at": datetime.now(timezone.utc).isoformat(),
                                        "quiet_days": quiet_days}
                    _save_fired(root, fired)

        return {
            "n_families_ready": len(families_ready),
            "n_families_approaching": len(families_approaching),
            "families_ready": families_ready,
            "families_approaching": families_approaching,
            "grader_quiet_days": quiet_days,
        }

    except Exception as e:  # noqa: BLE001
        log.warning("run_readiness_post_step failed (non-fatal): %s", e)
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# idempotency helper
# --------------------------------------------------------------------------- #
def _existing_grade_keys(root: Path) -> set[tuple]:
    """Set of (claim_id, horizon_d) pairs already written to grades.jsonl."""
    return {
        (g.get("claim_id"), int(g.get("horizon_d", -1)))
        for g in q.load_grades(root)
        if g.get("claim_id") is not None
    }


# --------------------------------------------------------------------------- #
# main grader
# --------------------------------------------------------------------------- #
def run(root: Path | str | None = None, today: date | None = None,
        dry_run: bool = False) -> dict:
    """Grade all open claims, write grades + track_record, return a summary dict.

    Parameters
    ----------
    root    : repo root (defaults to lib.config.ROOT).
    today   : reference date for maturity check (defaults to date.today()).
    dry_run : compute grades but do NOT write any files.

    Returns
    -------
    dict with keys: n_open, n_graded_today, n_blocked_by_coverage,
                    n_ungradeable, n_already_graded, generated_at.
    """
    if not root:
        from lib import config  # noqa: PLC0415 — see module header
        root = config.ROOT          # unwrapped, exactly as before
    else:
        root = Path(root)
    today_dt = today or date.today()

    # W0 Stage B-e (§3.4): backfill missing regime stamps from the persisted
    # daily vector (PIT; fill-null-only) BEFORE loading claims, and surface the
    # residual unstamped count — required visible by the stamping rules.
    regime_backfill = {"n_claims": 0, "n_backfilled": 0, "n_unstamped": 0}
    if not dry_run:
        try:
            regime_backfill = q.backfill_regime_stamps(root)
        except Exception as exc:  # noqa: BLE001 — never sink the grader
            log.warning("regime stamp backfill failed: %s", exc)

    claims = q.load_claims(root)
    open_claims = [c for c in claims if c.get("status") == q.STATUS_OPEN]
    existing_keys = _existing_grade_keys(root)

    grades_p = root.joinpath(*q._GRADES_FILE)
    if not dry_run:
        grades_p.parent.mkdir(parents=True, exist_ok=True)

    n_open = len(open_claims)
    n_graded_today = 0
    n_blocked_by_coverage = 0
    n_ungradeable = 0
    n_already_graded = 0

    # Collect new grade rows; we'll write them in a single pass.
    new_rows: list[dict] = []

    for claim in open_claims:
        cid = claim.get("claim_id")

        # Check gradeable at all (timestamp_quality gate).
        gradeable, _ = q._embargo_ok(claim)
        if not gradeable:
            n_ungradeable += 1
            continue

        scope = claim.get("scope") or {}
        subject = scope.get("key")
        bench = claim.get("bench") or q._DEFAULT_BENCH
        control = claim.get("control")
        start = q._entry_date(claim)

        try:
            horizon_d = int(claim.get("horizon_d"))
        except Exception:  # noqa: BLE001
            n_ungradeable += 1
            continue

        for h in q.in_scope_horizons(horizon_d):
            key = (cid, h)
            if key in existing_keys:
                n_already_graded += 1
                continue

            legs = [subject, bench] + ([control] if control else [])
            # P0a — THE PRE-GATE MUST USE THE CLAIM'S OWN CLOCK. This cheap
            # "is it time yet" check exists so the loop skips immature claims
            # without paying for grade_claim's price reads. It used to run the
            # LEGACY calendar maturity function for EVERY claim, explicit-clock
            # ones included, with no unit dispatch — so a `trading_days` h=21
            # claim opened on roughly the calendar clock: it could be admitted
            # up to ~9 days early (grade_claim then refused it and it counted as
            # blocked), or, under `calendar_days`, held past its real exit.
            # Dispatched here through the SAME `claim_window` grade_claim uses,
            # so the pre-gate and the grader can never disagree about which
            # window is being asked about. A declared-unit claim whose window
            # cannot resolve is blocked, not silently skipped.
            window = q.claim_window(claim, h, entry_anchor=start)
            if q.claim_horizon_unit(claim) is None:
                matured = q._matured(root, start, h, today_dt, legs)
            else:
                matured = (window is not None
                           and q._matured_window(root, window, today_dt, legs))
            if not matured:
                # Not yet elapsed or price not yet available — count as blocked.
                n_blocked_by_coverage += 1
                continue

            # grade_claim handles all the price maths; we filter to this horizon.
            rows = q.grade_claim(claim, root=root, today=today_dt)
            matched = [r for r in rows if int(r.get("horizon_d", -1)) == h]

            if matched:
                new_rows.extend(matched)
                n_graded_today += len(matched)
            else:
                # Matured but prices unavailable → coverage miss.
                n_blocked_by_coverage += 1

    # Write grades (append-only).
    if new_rows and not dry_run:
        with grades_p.open("a", encoding="utf-8") as fh:
            for row in new_rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Recompute and emit track_record.json, then overlay the §3 promotion-ladder
    # verdicts (per claim_family × horizon) so the ladder state is always current
    # alongside the grade stats. emit_ladder_states merges into the file written by
    # emit_track_record. Non-fatal: a ladder-emit crash must not lose the grades.
    if not dry_run:
        q.emit_track_record(root)
        try:
            q.emit_ladder_states(root, today=today_dt)
        except Exception as e:  # noqa: BLE001
            log.warning("emit_ladder_states failed (non-fatal): %s", e)

    # W6 post-step: promotion-readiness monitor (alerts + registry sync).
    # Non-fatal: a crash here must not affect run_status output.
    w6_readiness: dict = {}
    if not dry_run:
        try:
            w6_readiness = run_readiness_post_step(
                root, n_graded_today=n_graded_today, n_open=n_open,
                dry_run=dry_run, today=today_dt
            )
        except Exception as e:  # noqa: BLE001
            log.warning("run_readiness_post_step failed (non-fatal): %s", e)
            w6_readiness = {"error": str(e)}

    # P0a — the refused-clock population, counted rather than invisible. A claim
    # whose declared clock cannot resolve (unknown/mixed/uncalendared market, or
    # an anchor outside the calendar's modelled span) is REJECTED at registration
    # instead of registering open-forever with check_by=None. Publishing the count
    # here is what makes "fail closed" auditable: a lane that starts refusing
    # everything shows up as a number on the nightly instead of as claims that
    # quietly never grade.
    clock_refused = q.count_unresolvable_clock_claims(claims=claims)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": today_dt.isoformat(),
        "n_open": n_open,
        "n_graded_today": n_graded_today,
        "n_blocked_by_coverage": n_blocked_by_coverage,
        "n_ungradeable": n_ungradeable,
        "n_already_graded": n_already_graded,
        "clock_unresolvable_claims": clock_refused,
        "dry_run": dry_run,
        "w6_readiness": w6_readiness,
        "regime_stamp_backfill": regime_backfill,
    }

    # Write run_status.json — broken != quiet.
    if not dry_run:
        status_p = root.joinpath(*_STATUS_FILE)
        status_p.parent.mkdir(parents=True, exist_ok=True)
        status_p.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                            encoding="utf-8")

    msg = (
        f"[grade_qledger] open={n_open} graded_today={n_graded_today} "
        f"blocked={n_blocked_by_coverage} ungradeable={n_ungradeable} "
        f"already_graded={n_already_graded} "
        f"clock_unresolvable={clock_refused.get('n', 0)} "
        f"regime_backfilled={regime_backfill.get('n_backfilled', 0)} "
        f"regime_unstamped={regime_backfill.get('n_unstamped', 0)}"
        + (" [DRY RUN]" if dry_run else "")
    )
    log.info(msg)
    print(msg, flush=True)

    return summary


# --------------------------------------------------------------------------- #
# collect.py end-of-collect hook
# --------------------------------------------------------------------------- #
def run_as_collect_step(root: Path | str | None = None) -> None:
    """Called from scripts/collect.py as an end-of-collect step. Non-fatal:
    a grader crash must not abort the nightly collection run."""
    try:
        run(root=root)
    except Exception as exc:  # noqa: BLE001
        log.error("[grade_qledger] grader crashed (non-fatal): %s", exc)


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Nightly qledger claim grader — grades open claims and "
                    "emits site/qledger/track_record.json.")
    p.add_argument("--root", default=None,
                   help="Repo root (default: lib.config.ROOT).")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute grades but do not write any files.")
    p.add_argument("--today", default=None,
                   help="Override today's date (YYYY-MM-DD) for back-testing.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    today_dt = date.fromisoformat(args.today) if args.today else None
    run(root=args.root, today=today_dt, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
