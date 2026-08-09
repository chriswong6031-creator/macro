"""Clock-shift pytest plugin — walk the wall clock forward to find fixture time bombs.

WHY THIS EXISTS
---------------
A test fixture that hardcodes a date and feeds it to a producer which reads the
REAL wall clock is a scheduled CI red: it passes today, and fails on every run
after the clock walks past the producer's freshness window.  It cannot be caught
by running the suite — only by running the suite *in the future*.  This plugin is
that future.  Set ``CLOCK_SHIFT_DAYS=N`` and every ``datetime.now`` /
``date.today`` / ``pd.Timestamp.now`` read inside REPO code answers N days ahead;
a test that flips pass -> fail is carrying a bomb with a fire date between the
last green shift and the first red one.

USAGE
-----
    TZ=UTC CLOCK_SHIFT_DAYS=90 PYTHONPATH=tests/tools \\
        python3 -m pytest -p clock_shift tests/test_foo.py -q

    # bisect the fire date once a flip is found
    for N in 30 60 45 52; do
        TZ=UTC CLOCK_SHIFT_DAYS=$N PYTHONPATH=tests/tools \\
            python3 -m pytest -p clock_shift tests/test_foo.py -q
    done

``TZ=UTC`` is not optional: CI runs UTC, so a local-evening run is already
"tomorrow" over there and a same-day boundary reads differently.
``CLOCK_SHIFT_DAYS=0`` still installs the instrumentation, which is the correct
baseline to diff against — an unshifted plain-pytest run is NOT the same lens.
Batch driver: ``tests/tools/clock_shift_sweep.py``.

This module is deliberately NOT named ``test_*`` so pytest never collects it,
and it is NOT wired into CI (see PROVENANCE).

HOW IT SHIFTS
-------------
* ``pandas.Timestamp``: ``now``/``today``/``utcnow`` are patched IN PLACE on the
  real class.  Class identity is preserved, so the shift is visible to engine
  code that re-imports pandas mid-call.
* ``datetime.datetime`` / ``datetime.date``: C types that reject in-place
  patching, so a shifted SUBCLASS is name-swapped into module namespaces —
  but ONLY into modules whose ``__file__`` lives under the repo root.
* Modules using the ``import datetime`` idiom get a forwarding proxy module
  whose ``.datetime`` / ``.date`` are the shifted classes.
* A ``builtins.__import__`` hook serves the proxy to REPO-FILE importers only
  (it reads the importer's ``globals()["__file__"]``) — that is what reaches
  sys.modules-invisible path-loaded modules the sweep cannot see, while third
  parties always import the real module.  Two properties keep the shifted
  classes inert where they do travel: a mirror metaclass makes isinstance
  answer as the real class, and a factory ``__new__`` means only REAL
  instances ever exist.

The repo-scoping is load-bearing.  A previous version swapped the names in EVERY
module in ``sys.modules`` and poisoned third-party internals: dateutil's
``relativedelta.__radd__`` isinstance-checks its operand against the ``datetime``
name in dateutil's OWN namespace, which the swap had replaced, so REAL datetime
instances (handed over by pandas) failed the check and raised TypeError.  That
produced ~176 artifact reds that looked exactly like real findings.

BOUNDARIES (a non-flip here is not proof of safety)
---------------------------------------------------
Not shifted — a test that reads the clock through one of these sees the REAL
time even at a large shift, so the flip a bomb would produce never appears:
  * ``time.time()`` and everything built on it (including file mtimes, and any
    fixture that backdates a file with ``os.utime(time.time() - X)``).
  * ``numpy.datetime64("now")`` / ``np.datetime64(datetime.now())`` inside numpy.
  * Subprocesses — a shifted parent spawns an unshifted child.
  * ``type(x) is datetime.datetime`` EXACT-type comparisons against a swapped
    name (isinstance is safe — the mirror metaclass answers as the real class
    — but ``type() is`` is not).  Tiny surface; classify a suspicious flip
    before believing it.
A fixture whose freshness gate is mtime-based ("MTIME_ARTIFACT") therefore reads
as a flip caused by the SHIFT rather than by a fixture literal — the tell is that
the fixture carries no date literal at all.

PROVENANCE
----------
Built for the fixture clock-bomb sweep that followed #5065 (a hermetic-in-DATA
fixture that was not hermetic in TIME).  The house fix pattern is
``tests/test_earnings_seasons.py`` ``_days_ago`` / ``_prior_quarter``: derive the
fixture date from the same clock the producer reads, and carry a comment naming
the producer gate and its window.

Deliberately not wired into CI, and deliberately not reduced to a
``scripts/check_*.py`` static guard: the proven detector is executable.  A
static "date literal near a freshness word" grep was measured useless here —
694 of 700 files match it.
"""

import datetime as _dtmod
import os
import sys
import types

SHIFT_DAYS = int(os.environ.get("CLOCK_SHIFT_DAYS", "0") or "0")
REPO_ROOT = os.environ.get("CLOCK_SHIFT_REPO_ROOT") or os.getcwd()

# The __import__ hook below scopes on REPO_ROOT; launched from anywhere but
# the repo root (without CLOCK_SHIFT_REPO_ROOT set) it would silently serve
# real clocks to every repo module — the exact artifact class the hook
# exists to close. Fail loudly instead of sweeping blind.
if not os.path.isfile(os.path.join(REPO_ROOT, "tests", "tools", "clock_shift.py")):
    raise RuntimeError(
        "clock_shift: REPO_ROOT does not look like the repo root "
        f"({REPO_ROOT!r}) — run pytest from the repo root or set "
        "CLOCK_SHIFT_REPO_ROOT explicitly."
    )


def _is_repo_file(f) -> bool:
    # Defined before the __import__ hook below installs — the hook calls this
    # on every import from the moment it is assigned.
    if not f:
        return False
    try:
        return os.path.realpath(f).startswith(os.path.realpath(REPO_ROOT) + os.sep)
    except Exception:
        return False

_REAL_DATETIME = _dtmod.datetime
_REAL_DATE = _dtmod.date
_DELTA = _dtmod.timedelta(days=SHIFT_DAYS)


class _MirrorMeta(type):
    """isinstance/issubclass against a shifted class answers exactly as the
    REAL class would.

    Load-bearing for the stdlib attr patch below: third-party code that does
    ``import datetime`` and then, AT CALL TIME, ``isinstance(x, datetime.date)``
    (dateutil.relativedelta does exactly this) resolves the module attribute to
    the shifted class — and must keep accepting the real instances everything
    actually constructs, or arithmetic dispatch collapses into TypeError.
    """

    def __instancecheck__(cls, instance):
        return isinstance(instance, cls.__mirror__)

    def __subclasscheck__(cls, subclass):
        return issubclass(subclass, cls.__mirror__)


class _ShiftedDateTime(_REAL_DATETIME, metaclass=_MirrorMeta):
    __mirror__ = _REAL_DATETIME

    def __new__(cls, *args, **kwargs):
        # Pure factory: constructing through the shifted name yields a REAL
        # instance, so no shifted-class instance ever reaches pandas/C
        # exact-type fast paths.
        return _REAL_DATETIME(*args, **kwargs)

    @classmethod
    def now(cls, tz=None):
        return _REAL_DATETIME.now(tz) + _DELTA

    @classmethod
    def utcnow(cls):
        return _REAL_DATETIME.utcnow() + _DELTA

    @classmethod
    def today(cls):
        return _REAL_DATETIME.today() + _DELTA


class _ShiftedDate(_REAL_DATE, metaclass=_MirrorMeta):
    __mirror__ = _REAL_DATE

    def __new__(cls, *args, **kwargs):
        return _REAL_DATE(*args, **kwargs)

    @classmethod
    def today(cls):
        return _REAL_DATE.today() + _DELTA


class _DatetimeModuleProxy(types.ModuleType):
    """Forwards to the real datetime module, serving shifted classes."""

    def __getattr__(self, name):
        if name == "datetime":
            return _ShiftedDateTime
        if name == "date":
            return _ShiftedDate
        return getattr(_dtmod, name)


_DT_PROXY = _DatetimeModuleProxy("datetime")

try:
    import pandas as _pd
except ImportError:  # pragma: no cover
    _pd = None

if _pd is not None:
    _REAL_TS = _pd.Timestamp
    _PD_DELTA = _pd.Timedelta(days=SHIFT_DAYS)
    _real_ts_now = _REAL_TS.now

    # today()/utcnow() are implemented ON TOP of the saved real now() — NEVER
    # wrap the originals: pandas implements both by delegating to
    # ``Timestamp.now``, which is already patched, so wrapping them adds the
    # delta twice (measured: +3 shift → +6 on ``pd.Timestamp.today()``), and
    # every fire date bracketed through such a path reads HALF its true
    # distance.
    def _ts_now(tz=None):
        return _real_ts_now(tz) + _PD_DELTA

    def _ts_today(tz=None):
        return _real_ts_now(tz) + _PD_DELTA

    def _ts_utcnow():
        return _real_ts_now("UTC") + _PD_DELTA

    try:
        _REAL_TS.now = staticmethod(_ts_now)
        _REAL_TS.today = staticmethod(_ts_today)
        _REAL_TS.utcnow = staticmethod(_ts_utcnow)
    except (TypeError, AttributeError):  # pragma: no cover
        pass

# Serve the shifted classes ONLY to repo-file importers, via an __import__
# hook that inspects the importer's ``globals()["__file__"]``.  This is what
# reaches sys.modules-INVISIBLE path-loaded modules (the
# ``importlib.util.spec_from_file_location`` idiom used to import
# ``scripts/*.py`` inside tests, e.g. ``_import_build()`` in
# tests/test_metabolism_reflex.py): their body executes with their repo
# ``__file__`` in globals, so their ``from datetime import ...`` routes
# through the hook even though the namespace sweep below can never see them.
# Without this, a mid-test path-loaded producer reads the REAL clock while the
# test writes SHIFTED fixtures — fabricating flips that look exactly like
# bombs.
#
# Why a hook and not patching the stdlib module's own attributes: a global
# ``datetime.date = _ShiftedDate`` poisons third parties two ways — call-time
# module-attr isinstance checks (dateutil.relativedelta) unless the classes
# carry the mirror metaclass, and then the metaclass itself breaks any late
# third-party SUBCLASSER that brings its own metaclass
# (pydantic.v1 ``ConstrainedDate(date, metaclass=ConstrainedNumberMeta)`` —
# metaclass-compatibility TypeError at import).  The hook sidesteps both:
# third parties always import the real module.
import builtins as _builtins

_REAL_IMPORT = _builtins.__import__


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    mod = _REAL_IMPORT(name, globals, locals, fromlist, level)
    if (
        name == "datetime"
        and level == 0
        and globals is not None
        and _is_repo_file(globals.get("__file__"))
    ):
        return _DT_PROXY
    return mod


_builtins.__import__ = _import_hook


def _is_repo_module(mod) -> bool:
    return _is_repo_file(getattr(mod, "__file__", None))


def _sweep_modules():
    """Rebind datetime/date names (and the datetime module ref) in REPO modules only.

    Runs at shift 0 too, so the baseline carries the same instrumentation as the
    shifted runs and a diff between them isolates the CLOCK, not the plugin.
    """
    for name, mod in list(sys.modules.items()):
        if mod is None or name == __name__:
            continue
        if not _is_repo_module(mod):
            continue
        d = getattr(mod, "__dict__", None)
        if not isinstance(d, dict):
            continue
        for attr, val in list(d.items()):
            try:
                if val is _REAL_DATETIME:
                    setattr(mod, attr, _ShiftedDateTime)
                elif val is _REAL_DATE:
                    setattr(mod, attr, _ShiftedDate)
                elif val is _dtmod:
                    setattr(mod, attr, _DT_PROXY)
            except Exception:
                pass


# Re-swept at three points because repo modules are imported lazily: at
# collection (conftest/test import), inside fixtures, and inside the tests
# themselves.  A module imported after the last sweep would keep the real names.
def pytest_sessionstart(session):
    _sweep_modules()


def pytest_collection_finish(session):
    _sweep_modules()


def pytest_runtest_setup(item):
    _sweep_modules()
