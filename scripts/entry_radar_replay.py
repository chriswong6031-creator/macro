#!/usr/bin/env python3
"""scripts/entry_radar_replay.py — the W5 replay orchestrator SHELL.

WHAT THIS FILE IS, AND WHAT IT DELIBERATELY IS NOT
--------------------------------------------------
This is the runner the prereg §14 names: it executes the gates, spends the §13
looks, gathers episodes, attaches outcomes and matches controls — and then hands
the assembled inputs to ``engine.entry_radar.replay.confirmatory``, which owns
EVERY statistic.  Not one aggregation, bootstrap, p-value, CI or verdict is
computed here.  The split is not tidiness: a statistic computed in an
orchestration script is a statistic with no unit test and no frozen seed, and
§11 pins both.

WRITE DISCIPLINE.  This script writes ONLY under ``--out-dir`` (default
``research/live_entry_radar/w5_results``) and appends to the TrialLedger
(``data/trial_ledger.jsonl``, which IS the multiple-testing memory and is
append-only by construction).  It writes no other ``data/`` path — durable
evidence has exactly one writer, ``scripts/reconcile_entry_radar.py --nightly``
(prereg §8).

THE GATES RUN FIRST, ALWAYS
---------------------------
``run_gates()`` is called before any episode is derived, any outcome is read and
any look is logged, and a refusal is an exception that ends the process.  The
identity constants are STAMPED from the merged PR-5a commit
(416bb8cab3ae9239916aa3952f4541665917d5cc); a checkout that predates that merge
fails G-2 by construction — the prereg must be earlier merged history wherever
this runner executes.

ASSEMBLY (reconciled 2026-08-15)
--------------------------------
The original shell late-bound four sibling modules through ``_resolve`` because
they were authored in a parallel lane; the orchestrator has since reconciled the
seam: ``gather_episodes``/``build_match_context``/``_assemble_frame`` call the
REAL granular APIs directly (``panels.panel_a_names``/``panel_b_names``,
``feature_panel.build_feature_rows``/``cross_sectionalize``, the per-detector
``episodes.*`` builders and ``engine.entry_radar.replay.assembly``), and
``confirmatory`` now exposes the ``run_all``/``write_results`` pair this shell
drives (still resolved through ``_resolve``, which refuses loudly if either
disappears).

``scripts/entry_radar_vendor.py`` DOES exist and is wired against its real API
(``daily_ohlcv`` / ``quotes_at`` / ``half_spread_bps`` / ``read_manifest``).
``scripts/entry_radar_stage_terminal.py`` produces the G-5 report via
``--fidelity --json``; this runner reads that JSON from ``--staging-report``
rather than shelling out, so the staging run and the replay run stay separable.

USAGE
    python3 scripts/entry_radar_replay.py --declare-budget          # one-shot §13
    python3 scripts/entry_radar_replay.py --stage gates             # §14 only
    python3 scripts/entry_radar_replay.py --cache-dir <vendor> --panel both
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
# UNCONDITIONAL, position 0 — strong pin (tests/test_check_script_import_pinning.py).
sys.path.insert(0, str(ROOT))

from engine.entry_radar.replay import controls, gates, outcomes, prereg  # noqa: E402

log = logging.getLogger("entry_radar_replay")

DEFAULT_OUT_DIR = "research/live_entry_radar/w5_results"

#: Candidate symbol names per sibling module, in preference order.  See the
#: module docstring: a miss raises naming every candidate.
_SIBLING_CANDIDATES: dict[str, tuple[str, ...]] = {
    "engine.entry_radar.replay.panels": ("build_panel", "build", "panel_members"),
    "engine.entry_radar.replay.feature_panel": ("build_feature_panel", "build",
                                                "feature_rows"),
    "engine.entry_radar.replay.episodes": ("derive_episodes", "derive", "episodes_for"),
    "engine.entry_radar.replay.confirmatory": ("run_all",),
}

#: Second entry point for modules that also WRITE their own output.
_SIBLING_WRITERS: dict[str, tuple[str, ...]] = {
    "engine.entry_radar.replay.confirmatory": ("write_results",),
}

#: Detector id -> the short key the §13 ``LOOK_CELLS`` names use.  C4 is absent
#: on purpose: it is stratification-only and owns no primary table, only the
#: three ``c4_strata_rc*`` cells.
_DETECTOR_LOOK_KEY: dict[str, str] = {
    "G0_GREY_DOT@1": "G0",
    "C1_1D_LIVE_WASHOUT@1": "C1",
    "C2_1D_TURN@1": "C2A",
    "C3_1D_4H_RECOVERY@1": "C3",
    "C5_BOTTOM_WATCH@1": "C5",
}


class ReplayRefusal(RuntimeError):
    """The runner refuses to proceed.  The message always names the cause."""


# --------------------------------------------------------------------------- #
# assembled inputs handed to the statistics module
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ReplayInputs:
    """Everything ``confirmatory.run_all`` needs, and nothing it must re-derive.

    Deliberately minimal and TYPED: the boundary between "assembly" (here) and
    "inference" (there) is exactly this object, so a statistic that needs a field
    absent from this dataclass is a statistic reaching back into orchestration —
    which is the coupling this split exists to prevent.
    """

    gate_receipts: tuple[gates.GateReceipt, ...]
    episodes: tuple[outcomes.EpisodeRef, ...]
    outcome_rows: tuple[outcomes.OutcomeRow, ...]
    control_matches: tuple[controls.ControlMatch, ...]
    #: Per-episode refusals — G-6 holdout hits, missing planes, absent controls.
    #: A REFUSAL IS A ROW, never a silent drop (§13 row 14, the coverage census).
    refusals: tuple[dict[str, Any], ...]
    panel: str
    info_cutoff: str | None
    seeds: dict[str, int] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    #: The shell's own look-logger, bound to this run's ledger and info_cutoff.
    #: Handed ACROSS the boundary so ``confirmatory`` spends its §13 cells
    #: through the same ``check_look_cell``-enforced path the shell uses — a
    #: second logging path is a second place an undeclared look could slip in.
    log_look: Callable[[str, dict[str, Any]], bool] | None = None
    #: The assembled §7-contract episode frame (assembly.episode_row rows) —
    #: what confirmatory.run_all grades.  None => run_all reports no-frame.
    frame: Any = None
    #: Q5 matched-pair table (assembly.q5_pairs), Panel-B only.
    q5_pairs: Any = None
    #: §13 row-16 measured G0 date agreement (NaN when the check did not run).
    row16_agreement: float = float("nan")
    #: Pre-assembled §7 false-start sensitivity grid rows (cell/fav/adv/h/…).
    fs_grid: Any = None


# --------------------------------------------------------------------------- #
# progress heartbeat (STDERR ONLY)
# --------------------------------------------------------------------------- #
#: Wall-clock seconds between heartbeat lines, and the share of the item count
#: that also forces one.  Whichever falls due FIRST wins, so a fast loop over
#: many items still prints ~20 lines and a slow loop over few items still proves
#: it is alive every minute.
_HEARTBEAT_SECONDS = 60.0
_HEARTBEAT_FRACTION = 0.05


class _Heartbeat:
    """A ``[phase] k/N (elapsed Xs)`` liveness line, on STDERR and nowhere else.

    WHY STDERR.  This runner's stdout carries the gate receipts, the census
    lines and (downstream) the results contract that tests and operators parse;
    a progress line printed there would be a parse hazard for every consumer.
    stderr is the channel with no contract, which is exactly where liveness
    belongs.

    WHY IT EXISTS.  Measured 2026-08-15: a Panel-B run went ~2 wall-hours silent
    between the post-gather census line and the results write, and the only
    liveness evidence available to the operator was ``ps`` CPU-time forensics —
    made worse because the macOS spawn workers do not match a ``pgrep`` on this
    script's name.  A phase that cannot say "still working, k of N" is a phase
    that cannot be distinguished from a hang.

    The instrument must never be able to kill the work it watches: a write that
    raises (closed/broken stderr) disables further emission rather than
    propagating out of a loop that has been running for an hour.
    """

    def __init__(self, phase: str, total: int, *, stream: Any = None,
                 every_seconds: float = _HEARTBEAT_SECONDS,
                 every_fraction: float = _HEARTBEAT_FRACTION) -> None:
        self.phase = phase
        self.total = max(0, int(total))
        self._stream = stream if stream is not None else sys.stderr
        self._every_seconds = float(every_seconds)
        #: Emit at least every this many items; never 0 (a 0-item loop still
        #: prints its opening line, which is what proves the phase was entered).
        self._step = max(1, int(self.total * every_fraction))
        self._start = time.monotonic()
        self._last_emit = self._start
        self._k = 0
        self._emitted_k = 0
        self._live = True
        self._emit(0)

    def _emit(self, k: int) -> None:
        if not self._live:
            return
        elapsed = time.monotonic() - self._start
        try:
            print(f"[{self.phase}] {k}/{self.total} (elapsed {elapsed:.0f}s)",
                  file=self._stream, flush=True)
        except (OSError, ValueError):  # closed/broken stderr — go quiet, keep working
            self._live = False

    def tick(self, n: int = 1) -> None:
        """Count ``n`` more items REACHED; print iff a threshold is due.

        Every call site ticks at the top of its loop body, so ``k`` is the item
        currently being worked, not the last one finished — which is the reading
        an operator wants when the question is "what is it stuck on".
        """
        self._k += n
        now = time.monotonic()
        if (now - self._last_emit >= self._every_seconds
                or self._k - self._emitted_k >= self._step):
            self._last_emit = now
            self._emitted_k = self._k
            self._emit(self._k)

    def done(self) -> None:
        """Close the phase with a final count, unless the last tick already did."""
        if self._k != self._emitted_k:
            self._emitted_k = self._k
            self._emit(self._k)


# --------------------------------------------------------------------------- #
# (a) §14 gates
# --------------------------------------------------------------------------- #
def _is_ancestor_closure(root: Path) -> Callable[[str], bool]:
    """Closure over ``git merge-base --is-ancestor <sha> HEAD``.

    Injected rather than called inside ``gates`` so the gate module stays pure
    and battery C can prove the refusal with a fake closure.  A non-zero exit
    other than git's "not an ancestor" (1) RAISES, and ``check_merged_ancestry``
    turns a raise into a refusal — an unavailable git is not a pass.
    """
    def _probe(sha: str) -> bool:
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
            cwd=str(root), capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return True
        if proc.returncode == 1:
            return False
        raise ReplayRefusal(
            f"git merge-base --is-ancestor exited {proc.returncode}: "
            f"{(proc.stderr or '').strip()}")
    return _probe


def _f1_refuses_closure() -> Callable[[], bool]:
    """True iff ``get_spec('F1_FUSION')`` still raises ``NotYetSpecified``."""
    def _probe() -> bool:
        from engine.entry_radar import detectors  # noqa: PLC0415

        try:
            detectors.get_spec("F1_FUSION")
        except detectors.NotYetSpecified:
            return True
        return False
    return _probe


def _live_spec_hashes() -> dict[str, str]:
    """Recompute every registered detector's spec hash from the LIVE registry.

    Keyed over ``prereg.EXPECTED_SPEC_HASHES`` AND the live registry's own keys,
    so an UNREGISTERED detector appearing in ``DETECTORS`` reaches G-4 as an
    extra and refuses.  Iterating only the frozen dict would make the "extra
    detector" arm of G-4 structurally unreachable.
    """
    from engine.entry_radar import detectors  # noqa: PLC0415

    ids = set(prereg.EXPECTED_SPEC_HASHES) | set(detectors.DETECTORS)
    out: dict[str, str] = {}
    for did in sorted(ids):
        try:
            out[did] = detectors.get_spec(did).spec_hash
        except Exception:  # noqa: BLE001 — an unresolvable id is a MISS, not a pass
            continue
    return out


def load_staging_report(path: Path | None) -> dict[str, Any]:
    """The G-5 evidence produced by ``entry_radar_stage_terminal.py --fidelity``.

    An absent or unreadable report returns ``{}``, which G-5 refuses on the pin
    mismatch.  Fail-closed and named: "no staging evidence" must never read the
    same as "staging evidence that passed".
    """
    if path is None:
        print("::warning title=entry-radar-replay::no --staging-report given; G-5 will "
              "refuse (a missing fidelity report is not a passing one)", flush=True)
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"::warning title=entry-radar-replay::staging report {path} unreadable "
              f"({exc}) — G-5 will refuse", flush=True)
        return {}


def run_gates(root: Path, *, staging_report_path: Path | None,
              ledger_path: Path | None = None) -> list[gates.GateReceipt]:
    """Execute G-1..G-5.  Raises ``PreregGateRefusal`` on any failure."""
    doc = root / prereg.PREREG_DOC_PATH
    try:
        doc_bytes = doc.read_bytes()
    except OSError as exc:
        raise ReplayRefusal(f"prereg document {doc} unreadable ({exc}) — G-1 cannot "
                            "be evaluated, so nothing may run") from exc
    lpath = ledger_path or (root / "data" / "trial_ledger.jsonl")
    try:
        ledger_lines = lpath.read_text(encoding="utf-8").splitlines()
    except OSError:
        ledger_lines = []          # G-3 refuses on an empty ledger — correct
    receipts = gates.run_all(
        doc_bytes=doc_bytes,
        is_ancestor_of_head=_is_ancestor_closure(root),
        ledger_lines=ledger_lines,
        live_hashes=_live_spec_hashes(),
        f1_refuses=_f1_refuses_closure(),
        staging_report=load_staging_report(staging_report_path),
    )
    for r in receipts:
        print(f"entry-radar replay gate {r.gate}: {r.detail}", flush=True)
    return receipts


# --------------------------------------------------------------------------- #
# (b) §13 look ledger
# --------------------------------------------------------------------------- #
def log_look(cell_name: str, config: dict[str, Any], *,
             info_cutoff: str | None, ledger_path: Path | None = None) -> bool:
    """Spend ONE §13 look — called BEFORE the cell computes anything.

    Counting at GENERATION is the whole point (TrialLedger's own docstring): a
    cell logged after its result is a cell whose logging can be skipped when the
    result is boring.  ``info_cutoff`` is the vendor cache's data vintage, so a
    later leakage audit can check the cell could not have peeked past it.

    ``gates.check_look_cell`` runs FIRST and refuses any name outside the
    enumerated ``prereg.LOOK_CELLS``.  That ordering is the §15.C "undeclared
    look ⇒ caught" mechanism: an undeclared cell must be unable to reach the
    append-only ledger at all, because a spurious row there cannot be withdrawn.
    """
    from engine.trial_ledger import TrialLedger  # noqa: PLC0415

    gates.check_look_cell(cell_name)
    led = (TrialLedger(path=ledger_path, family=prereg.TRIAL_FAMILY)
           if ledger_path is not None else TrialLedger(family=prereg.TRIAL_FAMILY))
    payload = {"cell": cell_name, **config}
    return led.log_trial(payload, source="w5_replay", info_cutoff=info_cutoff)


def declare_budget(ledger_path: Path | None = None) -> int:
    """One-shot §13 budget declaration.  Refuses while either identity is UNSET.

    The reason string is not decoration — G-3 verifies it CONTAINS exactly the
    G-1/G-2 identifiers, so declaring the budget before the prereg is stamped
    would write a permanent, append-only row that the gate can never accept and
    that a later correct row does not erase.
    """
    from engine.trial_ledger import TrialLedger  # noqa: PLC0415

    if prereg.PREREG_COMMIT == "UNSET" or prereg.PREREG_DOC_SHA256 == "UNSET":
        raise ReplayRefusal(
            "refusing to declare the §13 budget: PREREG_COMMIT="
            f"{prereg.PREREG_COMMIT!r} PREREG_DOC_SHA256={prereg.PREREG_DOC_SHA256!r}. "
            "The declared_budget row is APPEND-ONLY and G-3 checks its reason string "
            "verbatim — a row written now could never be accepted and could never be "
            "withdrawn. Stamp the merged prereg (PR-5b) first.")
    reason = (f"w5_prereg={prereg.PREREG_COMMIT}; "
              f"doc_sha256={prereg.PREREG_DOC_SHA256}; itemized §13")
    led = (TrialLedger(path=ledger_path, family=prereg.TRIAL_FAMILY)
           if ledger_path is not None else TrialLedger(family=prereg.TRIAL_FAMILY))
    fresh = led.log_declared_budget(prereg.DECLARED_BUDGET,
                                    family=prereg.TRIAL_FAMILY, reason=reason)
    print(f"entry-radar replay: declared_budget n={prereg.DECLARED_BUDGET} "
          f"family={prereg.TRIAL_FAMILY} new={fresh}", flush=True)
    return 0


# --------------------------------------------------------------------------- #
# (d) episode gathering
# --------------------------------------------------------------------------- #
def _resolve(module_name: str, *, kind: str = "entry") -> Callable[..., Any]:
    """Import a sibling-owned module and bind its entry point BY NAME.

    Raises a refusal naming every candidate tried, so a rename in the sibling
    lane produces an actionable message instead of an AttributeError.
    """
    import importlib  # noqa: PLC0415

    candidates = (_SIBLING_CANDIDATES[module_name] if kind == "entry"
                  else _SIBLING_WRITERS[module_name])
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        raise ReplayRefusal(
            f"{module_name} is not importable ({exc}). It is authored in the parallel "
            f"W5 lane; this runner expects one of {list(candidates)} on it.") from exc
    for name in candidates:
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    raise ReplayRefusal(
        f"{module_name} exposes none of {list(candidates)} — the runner cannot guess "
        f"an entry point (available: {sorted(n for n in dir(mod) if not n.startswith('_'))})")


def _daily_cached(cache_dir: Path, ticker: str):
    """A name's cached vendor daily plane, or None (a miss is a refusal fact)."""
    import pandas as pd  # noqa: PLC0415

    path = cache_dir / "vendor_daily" / f"{ticker}.parquet"
    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path)
        return frame if len(frame) else None
    except Exception:  # noqa: BLE001 — a torn cache file is a miss
        return None


def _minute_reader_cache_only(cache_dir: Path):
    """Cache-only minute reader for the engine (no network inside episodes)."""
    from scripts import entry_radar_vendor as vendor  # noqa: PLC0415

    def _read(ticker: str, session: date):
        try:
            win = vendor.minute_window(ticker, session, session, cache_dir=cache_dir)
        except Exception:  # noqa: BLE001 — a fetch/cache fault is a refusal
            return None
        return None if win is None or len(win) == 0 else win
    return _read


def _finalize_candidates(cands: list[dict[str, Any]], *, panel: str,
                         cache_dir: Path, spy_close, sectors: dict[str, str],
                         refusals: list[dict[str, Any]],
                         p0_minute: str = "attempt") -> list[Any]:
    """§6 reference units + features -> frozen EpisodeRefs, refusal-recorded."""
    import pandas as pd  # noqa: PLC0415

    from engine.entry_radar.replay import (assembly, episodes as ep_mod,  # noqa: PLC0415
                                           features as feat)
    from scripts import entry_radar_vendor as vendor  # noqa: PLC0415

    def _minute_open(ticker: str, session: date) -> float | None:
        if p0_minute == "skip":
            return None  # frozen §6 fallback binds: next session close, uniform
        try:
            rows = vendor.minute_window(ticker, session, session, cache_dir=cache_dir)
        except Exception:  # noqa: BLE001
            return None
        if rows is None or len(rows) == 0:
            return None
        rth = rows  # tape_from_rows applies the RTH filter; here take first print >= 09:30 ET
        try:
            ts = pd.to_datetime(rth["t"])
            mask = (ts.dt.hour * 60 + ts.dt.minute) >= (9 * 60 + 30)
            first = rth[mask].iloc[0] if mask.any() else rth.iloc[0]
            return float(first["o"])
        except Exception:  # noqa: BLE001
            return None

    out: list[Any] = []
    beat = _Heartbeat(f"finalize:{panel}", len(cands))
    for cand in cands:
        beat.tick()
        ticker = str(cand["ticker"])
        daily = _daily_cached(cache_dir, ticker)
        if daily is None:
            refusals.append({"reason": "no_daily_plane", "panel": panel,
                             "ticker": ticker,
                             "detector_id": cand.get("detector_id")})
            continue
        try:
            gates.check_decision_in_era(
                cand["decision_session"] if isinstance(cand["decision_session"], date)
                else __import__("pandas").Timestamp(cand["decision_session"]).date())
        except gates.PreregGateRefusal as exc:
            refusals.append({"reason": "g6_out_of_era", "panel": panel,
                             "ticker": ticker,
                             "detector_id": cand.get("detector_id"),
                             "detail": str(exc)})
            continue
        units = assembly.resolve_reference_units(cand, daily, _minute_open)
        if units.refusal is not None or units.p0 is None:
            refusals.append({"reason": f"reference_units:{units.refusal}",
                             "panel": panel, "ticker": ticker,
                             "detector_id": cand.get("detector_id")})
            continue
        decision = (cand["decision_session"] if isinstance(cand["decision_session"], date)
                    else __import__("pandas").Timestamp(cand["decision_session"]).date())
        close = daily["c"]
        idx = daily.index
        dpos = int(idx.searchsorted(__import__("pandas").Timestamp(decision),
                                    side="left"))
        k_series = ep_mod.confirmed_k(daily)
        k_fwd = ep_mod.forward_confirmed_k(k_series, decision,
                                           horizon=prereg.HORIZON_PRIMARY)
        cohort = _cohort_of(cand, daily, dpos, panel=panel)
        regime = feat.regime_tag(spy_close, decision) if spy_close is not None else "unknown"
        c32 = feat.c32_flag(close, max(0, dpos - 1))
        extra = {"sector": sectors.get(ticker),
                 "p0_timestamp": cand.get("candidate_at"),
                 "variant": cand.get("variant"),
                 "c2a_fired_in_episode": cand.get("c2a_fired_in_episode"),
                 "common_eligible_c3_c2a": cand.get("common_eligible_c3_c2a"),
                 "day0_samples": cand.get("day0_samples")}
        try:
            ref = ep_mod.finalize_episode(
                cand, p0=units.p0, p0_basis=units.p0_basis, a0=units.a0,
                atr_basis=units.atr_basis,
                washout_low=ep_mod.washout_low(cand, daily),
                cohort=cohort, regime=regime, c32=c32,
                confirmed_k_fwd=k_fwd, extra=extra)
        except gates.PreregGateRefusal as exc:
            refusals.append({"reason": "g6_out_of_era", "panel": panel,
                             "ticker": ticker, "detail": str(exc)})
            continue
        out.append(ref)
    beat.done()
    return out


def _cohort_of(cand: dict[str, Any], daily, dpos: int, *, panel: str) -> str:
    """The frozen features.py first-match cohort law, computed at D."""
    import numpy as np  # noqa: PLC0415

    from engine.entry_radar.replay import features as feat  # noqa: PLC0415

    close = daily["c"]
    if dpos < 5:
        return "other"
    hist = close.iloc[: dpos + 1]
    n = len(hist)
    if n < feat.IPO_YOUNG_SESSIONS:
        return "ipo_young"
    opens = daily["o"].iloc[max(0, dpos - feat.GAP_LOOKBACK_SESSIONS): dpos + 1]
    prev_close = close.shift(1).iloc[max(0, dpos - feat.GAP_LOOKBACK_SESSIONS): dpos + 1]
    with np.errstate(all="ignore"):
        gaps = (opens / prev_close - 1.0).abs()
    if np.nanmax(gaps.to_numpy(dtype=float), initial=0.0) >= feat.GAP_ABS_PCT:
        return "gap_catalyst"
    win63 = hist.iloc[-feat.DEEP_DD_SESSIONS:]
    if len(win63) and float(hist.iloc[-1] / win63.max() - 1.0) <= feat.DEEP_DRAWDOWN:
        return "deep_mtf_washout"
    from engine.entry_radar.replay import episodes as ep_mod  # noqa: PLC0415
    k = ep_mod.confirmed_k(daily).iloc[: dpos + 1]
    k5 = k.iloc[-feat.FULL_WASHOUT_LOOKBACK:].dropna()
    if len(k5) and float(k5.min()) < feat.FULL_WASHOUT_K:
        return "full_daily_washout"
    k8 = k.iloc[-feat.PARTIAL_WASHOUT_LOOKBACK:].dropna()
    if len(k8) and feat.FULL_WASHOUT_K < float(k8.min()) <= 20.0:
        return "partial_shallow_washout"
    if n >= 200:
        ma200 = float(hist.iloc[-200:].mean())
        hi252 = float(hist.iloc[-252:].max()) if n >= 252 else float(hist.max())
        if float(hist.iloc[-1]) < ma200 and float(hist.iloc[-1] / hi252 - 1.0) <= feat.DAMAGED_DD_252:
            return "damaged_trend_rebound"
    if n >= 121 and float(hist.iloc[-1] / hist.iloc[-121] - 1.0) >= feat.LEADER_RET120:
        return "leader_reset"
    return "other"


def gather_episodes(*, cache_dir: Path, panel: str,
                    info_cutoff: str | None,
                    names: list[str] | None = None,
                    p0_minute: str = "attempt") -> tuple[list[Any], list[dict[str, Any]]]:
    """Derive one panel's episodes from the granular W5 APIs, G-6-fenced.

    Panel-B: staged-Terminal tables (G0 dots + C5 watches, emitted by
    ``entry_radar_stage_terminal.py --emit-tables``) + the incumbent gauge, all
    on cached vendor dailies.  Panel-A: C1/C2 (minute-reconstruction) + C3 (4H)
    via the cache-only reader — a missing window is a recorded refusal, never an
    EOD approximation (§5).  Every candidate passes §6 reference-unit
    resolution and the G-6 fence inside :func:`_finalize_candidates`.
    """
    import json as _json  # noqa: PLC0415

    from engine.entry_radar.replay import episodes as ep_mod, panels  # noqa: PLC0415

    refusals: list[dict[str, Any]] = []
    cands: list[dict[str, Any]] = []
    sectors = panels.sector_of(ROOT)
    spy = _daily_cached(cache_dir, "SPY")
    spy_close = spy["c"] if spy is not None else None

    if panel == "B":
        members = panels.panel_b_names(ROOT)
        if names:
            members = [t for t in members if t in set(names)]
        tables_dir = cache_dir / "staged_tables"
        beat = _Heartbeat(f"gather:{panel}", len(members))
        for t in members:
            beat.tick()
            path = tables_dir / f"{t}.json"
            if not path.exists():
                refusals.append({"reason": "no_staged_table", "panel": panel,
                                 "ticker": t})
                continue
            try:
                table = _json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                refusals.append({"reason": f"staged_table_unreadable:{exc!r}",
                                 "panel": panel, "ticker": t})
                continue
            daily = _daily_cached(cache_dir, t)
            if daily is None:
                refusals.append({"reason": "no_daily_plane", "panel": panel,
                                 "ticker": t})
                continue
            g0_c, g0_r = ep_mod.g0_candidates(t, table.get("dots") or [],
                                              daily, panel=panel)
            cands.extend(g0_c)
            refusals.extend({**r, "panel": panel, "ticker": t} for r in g0_r)
            c5_c, c5_r = ep_mod.c5_candidates_from_watches(
                t, table.get("watches") or [], daily, panel=panel)
            cands.extend(c5_c)
            refusals.extend({**r, "panel": panel, "ticker": t} for r in c5_r)
            cands.extend(ep_mod.incumbent_candidates(t, daily, panel=panel))
        beat.done()
    elif panel == "A":
        members = panels.panel_a_names(ROOT)
        if names:
            members = [t for t in members if t in set(names)]
        reader = _minute_reader_cache_only(cache_dir)
        beat = _Heartbeat(f"gather:{panel}", len(members))
        for t in members:
            beat.tick()
            daily = _daily_cached(cache_dir, t)
            if daily is None:
                refusals.append({"reason": "no_daily_plane", "panel": panel,
                                 "ticker": t})
                continue
            screen = [s for s in ep_mod.c1_screen_sessions(daily)
                      if prereg.REPLAY_ERA_START <= s <= prereg.HOLDOUT_BOUNDARY]
            if not screen:
                continue
            # Evaluate the screen PLUS each hit's 15-session tail: a C2 turn may
            # lawfully fire on a later session of the same nonterminal episode
            # whose own K never dipped below the screen (A5.3 — the turn needs
            # no current K<20).  Omitting tails would silently under-count C2.
            import pandas as _pd  # noqa: PLC0415
            sess_index = [ _pd.Timestamp(x).date() for x in daily.index ]
            pos_of = {s: i for i, s in enumerate(sess_index)}
            eval_set = set()
            for s in screen:
                i = pos_of.get(s)
                if i is None:
                    continue
                for j in range(i, min(i + 16, len(sess_index))):
                    d2 = sess_index[j]
                    if prereg.REPLAY_ERA_START <= d2 <= prereg.HOLDOUT_BOUNDARY:
                        eval_set.add(d2)
            sessions_to_eval = sorted(eval_set)
            out = ep_mod.c1_c2_episodes(t, daily, reader, sessions_to_eval,
                                        panel=panel)
            c1c2 = list(out.get("episodes") or [])
            fired_by_episode = {e.get("decision_session"): bool(e.get("c2_variants_fired"))
                                for e in c1c2 if e.get("detector_id", "").startswith("C1")}
            for e in c1c2:
                if e.get("detector_id", "").startswith("C1"):
                    e["c2a_fired_in_episode"] = any(
                        v.startswith("c2a") for v in (e.get("c2_variants_fired") or {}))
            cands.extend(c1c2)
            for r in out.get("refusals") or []:
                refusals.append({"reason": "minute_refusal", "panel": panel,
                                 "ticker": t, "detail": r})
            c3 = ep_mod.c3_episodes(t, daily, reader, sessions_to_eval, panel=panel)
            c3_eps = list(c3.get("episodes") or [])
            c3_sessions = {e.get("decision_session") for e in c3_eps}
            c2a_sessions = {e.get("decision_session") for e in c1c2
                            if str(e.get("variant") or "").startswith("c2a")}
            for e in c3_eps + [e for e in c1c2
                               if str(e.get("variant") or "").startswith("c2a")]:
                e["common_eligible_c3_c2a"] = bool(c3_sessions) and bool(c2a_sessions)
            cands.extend(c3_eps)
            for r in c3.get("refusals") or []:
                refusals.append({"reason": "c3_refusal", "panel": panel,
                                 "ticker": t, "detail": r})
            del fired_by_episode
        beat.done()
    else:  # pragma: no cover — argparse constrains
        raise ReplayRefusal(f"unknown panel {panel!r}")

    kept = _finalize_candidates(cands, panel=panel, cache_dir=cache_dir,
                                spy_close=spy_close, sectors=sectors,
                                refusals=refusals, p0_minute=p0_minute)
    if refusals:
        print(f"entry-radar replay: {len(refusals)} refusal(s) recorded on panel "
              f"{panel} (coverage census, never dropped)", flush=True)
    return kept, refusals


def cache_manifest_date(cache_dir: Path) -> str | None:
    """The vendor cache's data vintage — the ``info_cutoff`` every look carries.

    Two shapes are accepted, in order: an explicit ``manifest.json`` vintage
    stamp, then ``entry_radar_vendor.read_manifest``'s per-fetch receipt lines
    (the §5 fetch log), whose LATEST timestamp is the newest byte the cache can
    contain.  Taking the latest is the conservative direction — an info_cutoff
    earlier than the true vintage would understate what a cell could have seen.
    """
    for name in ("manifest.json", "cache_manifest.json"):
        path = cache_dir / name
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key in ("vintage", "asof", "cache_date", "as_of"):
            if payload.get(key):
                return str(payload[key])
    try:
        from scripts import entry_radar_vendor as vendor  # noqa: PLC0415

        stamps = [str(row[key]) for row in vendor.read_manifest(cache_dir)
                  for key in ("to", "end", "at") if row.get(key)]
        return max(stamps) if stamps else None
    except Exception:  # noqa: BLE001 — an unreadable manifest is an UNKNOWN vintage
        return None


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Live Entry Radar W5 replay runner.")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--cache-dir", default=None,
                    help="vendor cache directory (scripts/entry_radar_vendor.py)")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--panel", choices=("A", "B", "both"), default="both")
    ap.add_argument("--stage", choices=("gates", "episodes", "outcomes",
                                        "confirmatory", "all"), default="all")
    ap.add_argument("--staging-report", default=None,
                    help="G-5 fidelity JSON from entry_radar_stage_terminal.py")
    ap.add_argument("--trial-ledger", default=None,
                    help="TrialLedger path override (tests only; default data/)")
    ap.add_argument("--declare-budget", action="store_true",
                    help="declare the §13 budget once and exit")
    ap.add_argument("--p0-minute", choices=("attempt", "skip"), default="attempt",
                    help="confirmed-bar P0 minute reconstruction: 'skip' refuses "
                         "wholesale (P0 = next session close, the frozen §6 "
                         "fallback, uniform across the panel; recorded per episode)")
    ap.add_argument("--names", default=None,
                    help="comma-separated ticker subset (sharding / smoke runs); "
                         "the coverage census records the restriction")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    root = Path(args.root).resolve()
    ledger_path = Path(args.trial_ledger) if args.trial_ledger else None

    if args.declare_budget:
        return declare_budget(ledger_path)

    # ---- (a) gates, before ANYTHING else -------------------------------- #
    receipts = run_gates(root, staging_report_path=(
        Path(args.staging_report) if args.staging_report else None),
        ledger_path=ledger_path)
    if args.stage == "gates":
        return 0

    if not args.cache_dir:
        raise ReplayRefusal("--cache-dir is required past the gates stage: episodes are "
                            "derived from the vendor cache, never from live vendor calls")
    cache_dir = Path(args.cache_dir).resolve()
    info_cutoff = cache_manifest_date(cache_dir)
    if info_cutoff is None:
        raise ReplayRefusal(
            f"vendor cache {cache_dir} carries no manifest vintage — every §13 look must "
            "record an info_cutoff, and a look with an unknown data vintage cannot be "
            "leakage-audited later")

    panels = ("A", "B") if args.panel == "both" else (args.panel,)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    shard_names = ([t.strip() for t in args.names.split(",") if t.strip()]
                   if args.names else None)

    def _look(cell: str, config: dict[str, Any]) -> bool:
        # A shard-restricted run is a DIFFERENT look from the full-panel run:
        # the restriction rides the config so the ledger records both honestly
        # (dedup only collapses true re-runs of the same universe).
        cfg = dict(config)
        if shard_names:
            cfg["names_shard"] = shard_names
        return log_look(cell, cfg, info_cutoff=info_cutoff,
                        ledger_path=ledger_path)

    for panel in panels:
        # Episode DERIVATION spends no look: nothing is read as a result yet, and
        # the §13 budget itemizes result cells, not assembly steps.  The first
        # look is spent below, immediately before the outcome tables are built.
        shard = shard_names
        episodes, refusals = gather_episodes(cache_dir=cache_dir, panel=panel,
                                             info_cutoff=info_cutoff, names=shard,
                                             p0_minute=args.p0_minute)
        if shard:
            refusals.append({"reason": "names_shard_restriction", "panel": panel,
                             "names": shard})
        if args.stage == "episodes":
            print(f"entry-radar replay: panel {panel} -> {len(episodes)} episodes, "
                  f"{len(refusals)} refusals", flush=True)
            continue

        # (b) the look is SPENT BEFORE the cell runs — see log_look's docstring.
        # §13 row 6: one primary per-detector outcome table per detector present.
        for detector in sorted({getattr(e, "detector_id", "") for e in episodes}):
            key = _DETECTOR_LOOK_KEY.get(detector)
            if key is None:
                # C4 (stratification-only) and anything unregistered own no
                # primary table; a cell name invented for them would be refused
                # by check_look_cell anyway, which is the correct outcome.
                continue
            _look(f"primary_table_{key}",
                  {"panel": panel, "detector_id": detector,
                   "horizon": prereg.HORIZON_PRIMARY,
                   "target_atr": prereg.TARGET_ATR,
                   "invalidation_atr": prereg.INVALIDATION_ATR})
        ctx = build_match_context(episodes, cache_dir=cache_dir, panel=panel)
        rows, matches, more_refusals, kept_eps = _attach_and_match(
            episodes, cache_dir=cache_dir, panel=panel, ctx=ctx)
        refusals = list(refusals) + list(more_refusals)
        # §13 row 14 — the refusal/coverage census is itself a declared cell, so
        # the count of what W5 could NOT read is spent from the same budget as
        # what it could.
        _look("refusal_census", {"panel": panel, "n_refusals": len(refusals),
                                 "n_episodes": len(episodes)})
        if args.stage == "outcomes":
            print(f"entry-radar replay: panel {panel} -> {len(rows)} outcome rows, "
                  f"{len(matches)} control matches", flush=True)
            continue

        # ---- hand off to the statistics module ------------------------- #
        # EVERYTHING below this line is confirmatory.py's: aggregation,
        # bootstrap, BH, CIs, verdict language.  The shell only assembles.
        #
        # Both entry points are resolved BY NAME through the same late-binding
        # discipline as the other sibling modules, because confirmatory.py is
        # authored in the parallel lane and currently exposes per-question
        # functions (``q1_g0_vs_controls`` … ``q5_g0_vs_incumbent``, ``apply_bh``)
        # rather than the panel-level pair this shell drives.  A miss therefore
        # names what IS available instead of dying on an AttributeError.
        run_all = _resolve("engine.entry_radar.replay.confirmatory")
        write_results = _write_results  # shell-side writer: the ENGINE writes nothing

        frame, q5_pairs = _assemble_frame(kept_eps, rows, matches,
                                          cache_dir=cache_dir, panel=panel,
                                          ctx=ctx)
        fs_grid = _fs_grid(kept_eps, cache_dir=cache_dir, panel=panel)
        inputs = ReplayInputs(
            gate_receipts=tuple(receipts),
            episodes=tuple(kept_eps),
            outcome_rows=tuple(rows),
            control_matches=tuple(m[0] for m in matches if m is not None),
            refusals=tuple(refusals),
            panel=panel,
            info_cutoff=info_cutoff,
            seeds=dict(prereg.CONFIRMATORY_SEEDS),
            meta={"cache_dir": str(cache_dir), "root": str(root)},
            log_look=_look,
            frame=frame,
            q5_pairs=q5_pairs,
            row16_agreement=_row16_agreement(cache_dir),
            fs_grid=fs_grid,
        )
        results = run_all(inputs)
        write_results(results, out_dir)
        print(f"entry-radar replay: panel {panel} results written to {out_dir}",
              flush=True)
    return 0


#: Calendar-day padding around a decision session when pulling its daily plane.
#: BACK covers the D-1 bar every benchmark leg needs (`outcomes._leg_excess`
#: anchors at pos-1); FORWARD covers H=10 SESSIONS with room for holidays — a
#: window that merely counted 10 calendar days would censor every episode that
#: spans a long weekend and report `no_further_trades` for a tape that traded.
_PLANE_BACK_DAYS = 21
_PLANE_FORWARD_DAYS = 45


def _attach_and_match(episodes: Sequence[Any], *, cache_dir: Path,
                      panel: str, ctx: dict[str, Any]) -> tuple[
                          list[outcomes.OutcomeRow],
                          list[tuple[controls.ControlMatch,
                                     controls.ControlMatch] | None],
                          list[dict[str, Any]]]:
    """Attach §7 outcomes and select §7 matched controls, episode by episode.

    Kept as a named seam rather than inlined so the per-episode plane lookups
    have exactly one place to land.  Every failure is a REFUSAL ROW, never a
    dropped episode.

    The cost leg is the §11 law end to end: the vendor's NBBO half-spread at the
    decision timestamp when one is lawfully available, then
    ``costs.per_side_cost_bps`` applies ``max(measured, floor)``.  A missing or
    unentitled quote response returns None from ``half_spread_bps`` and the
    liquidity floor binds — never zero.
    """
    from datetime import timedelta  # noqa: PLC0415

    from engine.entry_radar.replay import costs  # noqa: PLC0415
    from scripts import entry_radar_vendor as vendor  # noqa: PLC0415

    rows: list[outcomes.OutcomeRow] = []
    matches: list[tuple[controls.ControlMatch, controls.ControlMatch] | None] = []
    kept_eps: list[Any] = []
    refusals: list[dict[str, Any]] = []
    beat = _Heartbeat(f"attach+match:{panel}", len(episodes))
    for ep in episodes:
        beat.tick()
        start = ep.decision_session - timedelta(days=_PLANE_BACK_DAYS)
        end = ep.decision_session + timedelta(days=_PLANE_FORWARD_DAYS)
        try:
            plane = vendor.daily_ohlcv(ep.ticker, start, end, cache_dir=cache_dir)
            bench = vendor.daily_ohlcv("SPY", start, end, cache_dir=cache_dir)["c"]
            sector_etf = _sector_etf(ep)
            sector = (vendor.daily_ohlcv(sector_etf, start, end,
                                         cache_dir=cache_dir)["c"]
                      if sector_etf else None)
            measured = vendor.half_spread_bps(
                vendor.quotes_at(ep.ticker, _cost_timestamp(ep), cache_dir=cache_dir))
            cost_bps, cost_basis = costs.per_side_cost_bps(
                measured, _adv_usd(ep, plane))
        except Exception as exc:  # noqa: BLE001
            refusals.append({"reason": "vendor_plane_unavailable",
                             "ticker": getattr(ep, "ticker", None),
                             "panel": panel, "detail": repr(exc)})
            continue
        rows.append(outcomes.attach(ep, daily=plane, bench_close=bench,
                                    sector_close=sector,
                                    cost_per_side_bps=cost_bps, cost_basis=cost_basis))
        kept_eps.append(ep)
        try:
            session_panel = _ctx_session_rows(ctx, ep.decision_session)
            pool = controls.eligible_pool(
                session_panel,
                detector_fire_sessions=ctx["fire_sessions"].get(ep.detector_id, {}),
                candidate_session=ep.decision_session,
                suppressed=ctx["suppressed"].get(
                    (ep.detector_id, ep.decision_session), frozenset()))
            cand_rows = session_panel[session_panel["ticker"] == ep.ticker]
            if cand_rows.empty:
                raise KeyError(f"no feature row for {ep.ticker} at "
                               f"{ep.decision_session} (sector/history refusal)")
            candidate_row = cand_rows.iloc[0]
            matches.append((controls.match(candidate_row, pool),
                            controls.match(candidate_row, pool,
                                           match_proximity=False)))
        except Exception as exc:  # noqa: BLE001
            refusals.append({"reason": "control_match_unavailable",
                             "ticker": getattr(ep, "ticker", None),
                             "panel": panel, "detail": repr(exc)})
            matches.append(None)
    beat.done()
    return rows, matches, refusals, kept_eps


def _session_key(value: Any) -> date:
    """The feature panel's canonical session spelling: a plain ``datetime.date``.

    ``pd.Timestamp`` subclasses ``datetime`` which subclasses ``date``, and
    ``date(2020, 2, 26) == pd.Timestamp("2020-02-26")`` is **False**.  A lookup that
    keys on the wrong one of the two therefore matches ZERO rows instead of raising,
    which is why the defect below survived: it looked like data, not like a bug.
    Every session that crosses the panel boundary goes through here.
    """
    import pandas as pd  # noqa: PLC0415

    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return pd.Timestamp(value).date()


def _ctx_session_rows(ctx: dict[str, Any], session: date):
    """One session's cross-sectionalized feature rows from the prebuilt panel.

    Indexed, not scanned.  The straightforward
    ``panel_frame[panel_frame["session"] == Timestamp(session)]`` compares EVERY
    row of the whole-era panel (millions) once per episode; ``groupby.indices``
    pays that scan once for the run and turns each lookup into a ``take`` of just
    that session's rows.  Identical output — group positions come out in
    ascending order of appearance, so row order, index labels, dtypes and the
    propagated ``attrs`` all match the mask exactly (pinned by
    ``tests/test_entry_radar_w5_perf.py``).

    Keyed on the panel's canonical ``datetime.date`` (see :func:`_session_key`).
    Both this index and the mask it replaced used to key on ``pd.Timestamp``,
    against the OBJECT column of ``date`` objects that ``feature_panel._as_dates``
    -> ``build_feature_rows`` -> ``cross_sectionalize`` actually produces — so both
    missed EVERY session and pushed EVERY episode into the
    ``control_match_unavailable`` refusal branch, a total §7 control blackout
    indistinguishable from ordinary sparse refusals in the census.  (That the two
    implementations missed identically is exactly why the perf refactor's
    byte-identity proof held.)  Both column spellings are looked up explicitly
    rather than assumed, because the failure mode of guessing wrong is silence.
    """
    import pandas as pd  # noqa: PLC0415

    panel_frame = ctx["features"]
    by_session = ctx.get("_rows_by_session")
    if by_session is None:
        by_session = panel_frame.groupby("session", sort=False).indices
        ctx["_rows_by_session"] = by_session
    key = _session_key(session)
    positions = by_session.get(key)
    if positions is None:
        # datetime64 panel (fixtures, or a future builder): groupby labels are
        # Timestamps there and dates here.  Ask for the other spelling rather
        # than assume one — a miss returns None, it does not raise.
        positions = by_session.get(pd.Timestamp(key))
    if positions is None or not len(positions):
        raise KeyError(f"no feature rows for session {session}")
    return panel_frame.take(positions)


def build_match_context(episodes_list: Sequence[Any], *, cache_dir: Path,
                        panel: str) -> dict[str, Any]:
    """The matching substrate: features for every decision session, fire maps,
    and §10 re-arm suppression sets.

    Features are built per NAME across the union of decision sessions (the
    vectorized shape ``feature_panel.build_feature_rows`` provides), then
    cross-sectionalized per session — deciles/quintiles are within
    (panel, session) as §7 freezes.
    """
    import pandas as pd  # noqa: PLC0415

    from engine.entry_radar.replay import feature_panel, panels  # noqa: PLC0415
    from scripts import entry_radar_vendor as vendor  # noqa: PLC0415

    sessions = sorted({ep.decision_session for ep in episodes_list})
    members = (panels.panel_a_names(ROOT) if panel == "A"
               else panels.panel_b_names(ROOT))
    sectors = panels.sector_of(ROOT)
    spy = _daily_cached(cache_dir, "SPY")
    spy_close = spy["c"] if spy is not None else pd.Series(dtype=float)

    def _shares(t: str) -> float | None:
        try:
            return vendor.shares_outstanding(t, cache_dir=cache_dir)
        except Exception:  # noqa: BLE001 — unknown shares => unknown bucket
            return None

    frames = []
    beat = _Heartbeat(f"featurize:{panel}", len(members))
    for t in members:
        beat.tick()
        daily = _daily_cached(cache_dir, t)
        if daily is None:
            continue
        try:
            rows = feature_panel.build_feature_rows(
                t, daily, spy_close, sectors.get(t), _shares, sessions,
                panel=panel)
        except Exception:  # noqa: BLE001 — a name that cannot feature is absent
            continue
        if len(rows):
            frames.append(rows)
    beat.done()
    if not frames:
        raise ReplayRefusal(f"panel {panel}: no feature rows could be built")
    features = feature_panel.cross_sectionalize(pd.concat(frames, ignore_index=True))
    # Pin the canonical ``datetime.date`` spelling ONCE, at the only seam where the
    # panel is born, so no downstream lookup has to guess the dtype (§7 reads it
    # through ``_ctx_session_rows``; ``controls.ControlMatch.session`` is a ``date``).
    features["session"] = [_session_key(s) for s in features["session"]]

    # §7 offsets are TRADING sessions ("did NOT fire within ±5 sessions of D";
    # "does NOT fire anywhere in (D, D+H]"), so positions must come from the BENCH
    # calendar.  Deriving them from the panel's own rows measures slots between
    # DECISION sessions — the panel only carries those — which is <= the true
    # trading-session distance, so both exclusions silently over-exclude and shrink
    # every control pool.  ``attach_session_positions`` takes the calendar for
    # exactly this reason ("a bench calendar must override the panel's own"); it was
    # simply never passed one here.
    #
    # Wrapped in SessionPositions, never a plain dict: this rides in ``attrs`` and
    # pandas DEEP-COPIES attrs on every metadata-propagating op (see
    # panels.SessionPositions).  The bench calendar makes the map BIGGER than the
    # panel-derived one it replaces, so sharing rather than copying matters more here,
    # not less.
    if spy is None:
        raise ReplayRefusal(
            f"panel {panel}: no cached SPY plane, so the §7 session calendar cannot "
            f"be built — offsets guessed from the panel's own decision sessions are "
            f"not trading-session offsets and would silently mis-scale the ±5 and "
            f"(D, D+H] control exclusions")
    pos = panels.SessionPositions(
        feature_panel.attach_session_positions(
            features, panels.session_calendar(spy)))
    features.attrs["session_pos_by_date"] = pos

    # A lookup that answers ZERO of the decision sessions is a broken panel, not a
    # sparse one, and must never be reported as a census of ordinary refusals.
    have = set(features["session"])
    resolvable = sum(1 for s in sessions if _session_key(s) in have)
    if not resolvable:
        raise ReplayRefusal(
            f"panel {panel}: the feature panel answers 0 of {len(sessions)} decision "
            f"sessions (session dtype {features['session'].dtype}) — the §7 control "
            f"lookup is structurally broken, not merely sparse. Refusing rather than "
            f"emitting a 100% control_match_unavailable census that reads like data.")
    if resolvable < len(sessions):
        print(f"::warning title=entry-radar-panel-coverage::panel {panel}: the feature "
              f"panel answers {resolvable}/{len(sessions)} decision sessions; the "
              f"remainder refuse control matching", flush=True)

    fire_sessions: dict[str, dict[str, list[date]]] = {}
    for ep in episodes_list:
        fire_sessions.setdefault(ep.detector_id, {}).setdefault(
            ep.ticker, []).append(ep.decision_session)
    for det in fire_sessions.values():
        for t in det:
            det[t] = sorted(det[t])

    suppressed: dict[tuple[str, date], frozenset[str]] = {}
    # §10 re-arm blackout approximation for CONTROL POOLS: a name is suppressed
    # at D for a detector iff one of its own episodes for that detector ended
    # within the prior 15 sessions.  Episode ends are approximated by
    # decision_session + H (CANDIDATE resolves at H) — conservative: it excludes
    # slightly more names from control pools than strictly required, never fewer.
    by_det_name: dict[str, dict[str, list[date]]] = fire_sessions
    for det_id, names in by_det_name.items():
        for s in {ep.decision_session for ep in episodes_list
                  if ep.detector_id == det_id}:
            blocked = set()
            for t, fires in names.items():
                for f in fires:
                    gap = (pd.Timestamp(s) - pd.Timestamp(f)).days
                    if 0 < gap <= 45:  # calendar over-approximation of H+15 sessions
                        blocked.add(t)
                        break
            if blocked:
                suppressed[(det_id, s)] = frozenset(blocked)
    return {"features": features, "fire_sessions": fire_sessions,
            "suppressed": suppressed, "session_pos": pos,
            "sessions_resolvable": resolvable, "sessions_total": len(sessions)}


def _sector_etf(episode: Any) -> str | None:
    """The sector-matched ETF for the episode's second excess leg, or None.

    Reuses ``qledger.control_for_sector`` — the estate's ONE GICS-name -> ETF
    map — rather than minting a second table.  A None is a valid recorded state
    (the sector leg simply stays null), exactly as it is for a qledger claim.
    """
    from engine.qledger import control_for_sector  # noqa: PLC0415

    sector = (episode.extra or {}).get("sector") if hasattr(episode, "extra") else None
    return control_for_sector(sector) if sector else None


def _cost_timestamp(episode: Any) -> Any:
    """§11 T: the P0 timestamp for confirmed-bar detectors, else the signal ts."""
    extra = getattr(episode, "extra", None) or {}
    return extra.get("p0_timestamp") or extra.get("signal_ts")


def _adv_usd(episode: Any, plane: Any) -> float | None:
    """Median trailing-60-session dollar volume at D (§11 ADV_WINDOW_SESSIONS).

    Computed from the episode's own vendor plane so the tier and the tape agree.
    Returns None when the plane is too short — and None binds the WIDEST floor in
    ``costs.tier_floor_bps``, never the cheapest.
    """
    import pandas as pd  # noqa: PLC0415

    try:
        window = plane.loc[: pd.Timestamp(episode.decision_session)].tail(
            prereg.ADV_WINDOW_SESSIONS)
        if window.empty:
            return None
        return float((window["c"] * window["v"]).median())
    except Exception:  # noqa: BLE001 — an unreadable plane is an UNKNOWN ADV
        return None




# --------------------------------------------------------------------------- #
# frame / Q5 / grid / row-16 assembly (the §7-contract inputs run_all grades)
# --------------------------------------------------------------------------- #
def _assemble_frame(kept_eps, rows, matches, *, cache_dir: Path, panel: str,
                    ctx: dict[str, Any]):
    """Aligned (episode, outcome, matched+unmatched) -> the §7 episode frame.

    Control forward returns come from each control name's cached daily plane
    (close-to-close from D, the §7 control-leg law); a control with no cached
    plane simply contributes nothing (its absence is visible in n_controls).
    """
    import pandas as pd  # noqa: PLC0415

    from engine.entry_radar.replay import assembly  # noqa: PLC0415

    plane_cache: dict[str, Any] = {}

    def _plane(t: str):
        if t not in plane_cache:
            plane_cache[t] = _daily_cached(cache_dir, t)
        return plane_cache[t]

    class _PlaneMap(dict):
        def get(self, key, default=None):  # noqa: A003 — dict-shaped lazy loader
            plane = _plane(str(key))
            return plane if plane is not None else default

    panel_daily = _PlaneMap()
    frame_rows = []
    for ref, row, pair in zip(kept_eps, rows, matches):
        if pair is None:
            matched = controls.ControlMatch(
                ticker=ref.ticker, session=ref.decision_session, controls=(),
                n_cell=0, uninformative_no_control=True, same_band_control=False)
            unmatched = matched
        else:
            matched, unmatched = pair
        frame_rows.append(assembly.episode_row(ref, row, matched, unmatched,
                                               panel_daily))
    frame = pd.DataFrame(frame_rows)

    q5_pairs = None
    if panel == "B" and len(frame):
        g0 = frame[frame["detector"] == "G0"]
        if len(g0):
            inc_by_name: dict[str, list[date]] = {}
            for ep in kept_eps:
                if ep.detector_id.startswith("INCUMBENT"):
                    inc_by_name.setdefault(ep.ticker, []).append(ep.decision_session)
            fs_by_key = {(r["name"], pd.Timestamp(r["session"]).date()): r["false_start"]
                         for r in frame_rows}
            inc_fs = {(ep.ticker, ep.decision_session): fs_by_key.get(
                (ep.ticker, ep.decision_session))
                for ep in kept_eps if ep.detector_id.startswith("INCUMBENT")}
            g0_fs = {(r["name"], pd.Timestamp(r["session"]).date()): r["false_start"]
                     for r in frame_rows}
            q5_pairs = assembly.q5_pairs(
                g0, {k: sorted(v) for k, v in inc_by_name.items()},
                ctx["session_pos"], g0_fs, inc_fs)
    return frame, q5_pairs


def _fs_grid(kept_eps, *, cache_dir: Path, panel: str | None = None):
    """§7's 27x5 diagnostic grid: false-start rate per (fav, adv, h, detector).

    Re-attaches outcomes per grid cell over cached planes — bounded, cache-only,
    and skipped (None) when no episodes exist.  ``panel`` labels the heartbeat
    only; the grid itself is panel-agnostic (it grades whatever it is handed).
    """
    import pandas as pd  # noqa: PLC0415

    if not kept_eps:
        return None
    from scripts import entry_radar_vendor as vendor  # noqa: PLC0415

    grid_rows = []
    by_ticker: dict[str, list[Any]] = {}
    for ref in kept_eps:
        by_ticker.setdefault(ref.ticker, []).append(ref)
    det_key = {"G0_GREY_DOT@1": "G0", "C1_1D_LIVE_WASHOUT@1": "C1",
               "C2_1D_TURN@1": "C2A", "C3_1D_4H_RECOVERY@1": "C3",
               "C5_BOTTOM_WATCH@1": "C5"}
    fs_by_cell: dict[tuple[float, float, int, str], list[bool]] = {}
    beat = _Heartbeat("fs_grid" if panel is None else f"fs_grid:{panel}",
                      len(by_ticker))
    for ticker, refs in by_ticker.items():
        beat.tick()
        plane = _daily_cached(cache_dir, ticker)
        if plane is None:
            continue
        spy = _daily_cached(cache_dir, "SPY")
        bench = spy["c"] if spy is not None else plane["c"]
        for ref in refs:
            key = det_key.get(ref.detector_id)
            if key is None:
                continue
            for fav in prereg.SENSITIVITY_FAVORABLE:
                for adv in prereg.SENSITIVITY_ADVERSE:
                    for h in prereg.SENSITIVITY_HORIZONS:
                        row = outcomes.attach(
                            ref, daily=plane, bench_close=bench,
                            sector_close=None, cost_per_side_bps=0.0,
                            cost_basis="floor", horizon=h,
                            adverse_atr=adv, favorable_atr=fav)
                        if row.false_start is not None:
                            fs_by_cell.setdefault((fav, adv, h, key),
                                                  []).append(row.false_start)
    beat.done()
    for (fav, adv, h, key), vals in sorted(fs_by_cell.items()):
        grid_rows.append({
            "cell": f"fs_grid_f{int(fav*100):03d}_a{int(adv*100):03d}_h{h}_{key}",
            "fav": fav, "adv": adv, "h": h, "detector": key,
            "false_start_rate": float(pd.Series(vals).mean()),
            "n": int(len(vals)),
        })
    return pd.DataFrame(grid_rows) if grid_rows else None


def _row16_agreement(cache_dir: Path) -> float:
    """§13 row-16 measured G0 date agreement, if the check's artifact exists.

    Produced by the basis-fidelity pass (curated-plane vs vendor-plane staged
    runs on Panel-A ∩ Panel-B); ABSENT => NaN => Q1/Q5 refuse fail-closed (§4).
    """
    import json as _json  # noqa: PLC0415

    path = cache_dir / "row16_agreement.json"
    if not path.exists():
        return float("nan")
    try:
        payload = _json.loads(path.read_text(encoding="utf-8"))
        return float(payload["date_agreement"])
    except Exception:  # noqa: BLE001 — unreadable evidence is no evidence
        return float("nan")



def _write_results(results, out_dir) -> None:
    """Write one panel's results (JSON + flat CSV).  SHELL-side on purpose —
    the engine package writes nothing (W1 guard law), and rewriting an existing
    panel file is refused by numbering (append-only results discipline)."""
    import pandas as pd  # noqa: PLC0415

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    panel = str(results.get("panel", "X"))
    path = out / f"w5_results_panel_{panel}.json"
    n = 1
    while path.exists():
        path = out / f"w5_results_panel_{panel}.{n}.json"
        n += 1
    path.write_text(json.dumps(results, indent=1, sort_keys=True, default=str),
                    encoding="utf-8")
    rows = [t for t in results.get("tables", {}).values()
            if isinstance(t, dict) and "n_episodes" in t]
    if rows:
        pd.DataFrame(rows).to_csv(path.with_suffix(".tables.csv"), index=False)


if __name__ == "__main__":
    raise SystemExit(main())
