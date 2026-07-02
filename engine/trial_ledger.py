"""Trial Ledger — honest multiple-testing accounting for the Deflated Sharpe gate.

The Deflated Sharpe Ratio (engine.validation.deflated_sharpe) deflates a hand-picked
"best" Sharpe for the number of configs ``N`` that were tried. Today every caller
passes that ``N`` as a literal int — and a caller can LOWBALL it (report ``n_trials=4``
for a 40-config search), which silently makes the haircut too lenient. That is the
single biggest p-hacking surface in the calibration suite.

The Trial Ledger removes the caller's discretion: every config a search touches is
logged AT GENERATION (not at backtest) to an append-only JSONL, keyed by a ``family``
(the signal/strategy whose multiple-testing budget is being spent). ``deflated_sharpe``
then reads the family's honest distinct-config count from the ledger instead of
trusting a number the caller chose.

Counting at GENERATION is deliberate: multiple testing is incurred when you GENERATE
and evaluate a candidate, not only when one survives to a headline backtest. A breadth
fan-out that enumerates 200 transforms and reports the best spent 200 trials, not 1.

``effective_n()`` is conservative by construction: it counts every DISTINCT config in
the family (dedup by content hash so a re-run does not inflate ``N``). Correlation
credit — the claim that near-duplicate trials should count as fewer independent tests —
is the gaming direction, so it is OFF by default and, when explicitly enabled, is
hard-floored at ``ceil(sqrt(literal_N))`` and can never make the haircut more lenient
than that floor.

Design notes
------------
* Pure stdlib (hashlib/json/math/datetime/pathlib/threading) so the thin data-bot env
  stays thin, matching engine/validation.py's "no scipy/sklearn" rule.
* Append-only + dedup-by-(family, config-hash): re-running a calibrator is idempotent
  (N does not grow), but a genuinely new config does grow it.
* The on-disk file persists across nightly CI builds the same way
  ``data/ai_desk/theses.jsonl`` does — it IS the multiple-testing memory.
* ``deflated_sharpe`` duck-types the ledger (it only calls ``.effective_n(family)``),
  so engine/validation.py keeps zero import coupling to this module.
"""
from __future__ import annotations

import hashlib
import json
import math
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

# The canonical persistent ledger — committed + appended in CI, like theses.jsonl.
DEFAULT_PATH = Path("data") / "trial_ledger.jsonl"

_WRITE_LOCK = threading.Lock()


def _canon(config) -> str:
    """Stable, order-independent JSON encoding of a config for hashing.

    Accepts dicts / lists / tuples / scalars; ``default=str`` lets exotic values
    (numpy scalars, Paths) hash deterministically without importing numpy here."""
    return json.dumps(config, sort_keys=True, default=str, separators=(",", ":"))


def _hash(family: str, config) -> str:
    return hashlib.sha1(f"{family}\x00{_canon(config)}".encode("utf-8")).hexdigest()[:16]


class TrialLedger:
    """Append-only record of every config tried per signal family.

    Usage (in a calibrator, log the WHOLE grid at generation — before backtesting)::

        led = TrialLedger(family="commodity_tsmom")
        led.log_grid(GRID, info_cutoff="2026-06-20")        # count every config tried
        ...
        dsr = deflated_sharpe(sr, sk, ku, T, ledger=led, family="commodity_tsmom")

    The ``family`` namespaces a multiple-testing budget: all configs that compete to
    produce one headline result share a family, so the DSR deflates by the full count.
    """

    def __init__(self, path: str | Path | None = None, family: str | None = None) -> None:
        self.path = Path(path) if path is not None else DEFAULT_PATH
        self.default_family = family
        # family -> set(config_hash); rebuilt from disk so counts survive process restarts
        self._seen: dict[str, set[str]] = {}
        # family -> max declared research budget (a floor on effective_n; see log_declared_budget)
        self._declared: dict[str, int] = {}
        self._declared_seen: set[str] = set()
        self._load()

    # -- internals --------------------------------------------------------- #
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue  # tolerate a torn final line; never crash a calibrator
                    if row.get("kind") == "declared_budget":
                        fam, n = row.get("family"), row.get("n")
                        if fam and isinstance(n, int):
                            self._declared[fam] = max(self._declared.get(fam, 0), n)
                            h = row.get("config_hash")
                            if h:
                                self._declared_seen.add(h)
                        continue
                    fam, h = row.get("family"), row.get("config_hash")
                    if fam and h:
                        self._seen.setdefault(fam, set()).add(h)
        except OSError:
            return

    def _fam(self, family: str | None) -> str:
        fam = family or self.default_family
        if not fam:
            raise ValueError(
                "a trial 'family' is required — it names the signal whose "
                "multiple-testing budget this trial spends")
        return fam

    # -- writing ----------------------------------------------------------- #
    def log_trial(self, config, *, family: str | None = None, info_cutoff=None,
                  source: str = "grid", note: str | None = None) -> bool:
        """Record one config tried for ``family``. Append-only + deduplicated.

        Returns True if this (family, config) is newly distinct, False if it was
        already logged (a re-run). ``info_cutoff`` stamps the data-availability date
        so a later leakage audit can check the config could not have peeked ahead."""
        fam = self._fam(family)
        h = _hash(fam, config)
        seen = self._seen.setdefault(fam, set())
        if h in seen:
            return False
        seen.add(h)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "family": fam,
            "config_hash": h,
            "config": config,
            "source": source,
            "info_cutoff": info_cutoff,
            "note": note,
        }
        with _WRITE_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
        return True

    def log_grid(self, configs, *, family: str | None = None, **kw) -> int:
        """Bulk-log an iterable of configs (the whole search grid, at generation).
        Returns the count of NEWLY-distinct trials added this call."""
        return sum(int(self.log_trial(c, family=family, **kw)) for c in configs)

    def log_declared_budget(self, n: int, *, family: str | None = None,
                            reason: str | None = None) -> bool:
        """Record a DECLARED multiple-testing budget for ``family`` — a manual
        upper-bound on configs explored that are NOT all itemized in code (e.g. the
        signal/threshold/window variants tried during research). It acts as a FLOOR on
        ``effective_n``: it can only ever RAISE the haircut, never lower it (anti-gaming,
        and de Prado's "overestimating is the conservative direction"). Use it to migrate
        a calibrator that deflated by a hand-declared n_trials larger than its in-code
        grid — the conservative count is preserved, but now persisted + auditable instead
        of a bare literal. Returns True if newly recorded for this (family, n, reason)."""
        fam = self._fam(family)
        n = int(n)
        if n < 1:
            raise ValueError("declared budget must be >= 1")
        h = _hash(fam, {"__declared_budget__": n, "reason": reason})
        self._declared[fam] = max(self._declared.get(fam, 0), n)
        if h in self._declared_seen:
            return False
        self._declared_seen.add(h)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "family": fam,
            "kind": "declared_budget",
            "n": n,
            "reason": reason,
            "config_hash": h,
        }
        with _WRITE_LOCK:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, default=str) + "\n")
        return True

    @classmethod
    def with_declared_budget(cls, n: int, family: str | None = None) -> "TrialLedger":
        """Ephemeral ledger carrying just a DECLARED budget of ``n`` (so ``effective_n() ==
        n``), persisted to a deterministic throwaway temp file. The honest, audited,
        ratchet-clean stand-in for a bare ``deflated_sharpe(n_trials=n)`` where the count
        is COMPUTED (not a p-hacked lowball) and no caller ledger is threaded through:

            deflated_sharpe(..., ledger=TrialLedger.with_declared_budget(n, fam), family=fam)

        The temp path is keyed by (family, n) so repeated identical calls reuse one tiny
        file (``log_declared_budget`` is idempotent) — never the production ledger. The
        family must be non-empty (the ledger keys on it), so the caller passes a real one."""
        key = hashlib.sha1(f"{family}:{int(n)}".encode()).hexdigest()[:12]
        led = cls(path=Path(tempfile.gettempdir()) / f"_declbudget_{key}.jsonl", family=family)
        led.log_declared_budget(int(n), family=family)
        return led

    # -- reading ----------------------------------------------------------- #
    def literal_n(self, family: str | None = None) -> int:
        """Distinct configs logged for ``family`` — the honest multiple-testing N."""
        return len(self._seen.get(self._fam(family), ()))

    def effective_n(self, family: str | None = None, *,
                    correlation_credit: float | None = None) -> int:
        """Effective number of independent trials for the DSR haircut.

        Default (``correlation_credit=None``) = ``literal_n``: every distinct config
        counts as one independent test — the conservative, ungameable baseline.

        ``correlation_credit`` in (0, 1] is the OPT-IN gaming direction: it scales N
        down to reflect near-duplicate trials, but is hard-floored at
        ``ceil(sqrt(literal_n))`` so a 400-config search can never be laundered into
        "effectively 2". Counting at generation + this floor are what make the ledger
        a gate rather than a knob.

        A declared research budget (see ``log_declared_budget``) is applied last as a
        hard floor: ``effective_n`` is never below it. Returns at least 1."""
        fam = self._fam(family)
        declared = self._declared.get(fam, 0)
        lit = len(self._seen.get(fam, ()))
        if lit <= 1:
            base = max(lit, 1)
        elif correlation_credit is None:
            base = lit
        else:
            cc = float(correlation_credit)
            if not (0.0 < cc <= 1.0):
                raise ValueError("correlation_credit must be in (0, 1]")
            floor = math.ceil(math.sqrt(lit))
            base = max(floor, int(round(lit * cc)))
        return max(base, declared, 1)

    def declared_budget(self, family: str | None = None) -> int:
        """The declared research-budget floor for ``family`` (0 if none)."""
        return self._declared.get(self._fam(family), 0)

    def families(self) -> list[str]:
        """All families seen so far (itemized or declared), for audit/registry enumeration."""
        return sorted(set(self._seen) | set(self._declared))


class register_trials:
    """Declare a harness's multiple-testing BUDGET at the top of its run — W1d "trial
    budgets with teeth". Usable as a decorator OR a context manager; either way it writes
    a ``declared_budget`` row for ``family`` to the persistent ledger BEFORE the search
    runs, so a CI lint (scripts/check_trial_registration.py) can prove every
    ``validate_*``/``*_phase0`` harness registered, and ``walk_forward._mt_bump`` can source
    an honest ``n_trials`` from it.

    Decorator::

        @register_trials("commodity_tsmom", budget=48,
                         reason="8 windows x 3 lookbacks x 2 stops")
        def main():
            ...

    Context::

        with register_trials("commodity_tsmom", budget=48):
            best = sweep(GRID)

    ``budget`` is an HONEST UPPER BOUND on the configs the harness explores (itemized grid
    size + the variants tried during research). It is a FLOOR on ``effective_n`` — it can
    only raise the DSR haircut, never lower it (anti-gaming). ``basis`` stamps how the count
    was arrived at: ``'itemized'`` (exact grid), ``'estimated'`` (a documented upper-bound
    guess — better than the zero it replaces), or ``'frozen-quote'`` (a legacy hardcoded N
    being migrated). ``expiry`` optionally date-stamps a frozen-quote per the passport rule.
    Idempotent: re-running a harness does not inflate N (dedup on family+n+reason)."""

    def __init__(self, family: str, budget: int, *, reason: str | None = None,
                 basis: str = "itemized", expiry: str | None = None,
                 ledger: "TrialLedger | None" = None) -> None:
        if not family:
            raise ValueError("register_trials needs a non-empty family")
        self.family = family
        self.budget = int(budget)
        self.basis = basis
        note = reason or ""
        if basis and basis != "itemized":
            note = f"[{basis}] {note}".strip()
        if expiry:
            note = f"{note} (expiry {expiry})".strip()
        self.reason = note or None
        self.ledger = ledger

    def _write(self) -> None:
        led = self.ledger if self.ledger is not None else TrialLedger()
        led.log_declared_budget(self.budget, family=self.family, reason=self.reason)

    # -- context-manager form --
    def __enter__(self) -> "register_trials":
        self._write()
        return self

    def __exit__(self, *exc) -> bool:
        return False

    # -- decorator form --
    def __call__(self, fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            self._write()
            return fn(*a, **kw)
        # expose the declared budget for introspection/CI
        wrapper.__trial_family__ = self.family
        wrapper.__trial_budget__ = self.budget
        return wrapper


__all__ = ["TrialLedger", "DEFAULT_PATH", "register_trials"]
