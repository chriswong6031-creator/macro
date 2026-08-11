"""Strict-JSON encoding helper for committed research artifacts.

THE DEFECT THIS CLOSES. `json.dumps(summary, indent=2, default=str)` looks like it
sanitizes, and does not: `default=` is only consulted for objects the encoder
CANNOT serialize. A float NaN is perfectly serializable — the encoder happily
writes the bare token `NaN` — so NaN sails straight through `default=str` into the
artifact. `NaN`, `Infinity` and `-Infinity` are Python/JavaScript-literal
extensions, not JSON (RFC 8259 has no non-finite number), so `jq`, browsers,
`JSON.parse`, and every strict parser reject the file outright. Three shipped
`data/research/top_anatomy_*_summary.json` artifacts carried six such fields each
under `ruler.*` (e.g. `fwd_63_excess` for a leg with no fires).

THE CONTRACT — read before using this.

* **JSON-WRITE TIME ONLY.** Call :func:`sanitize_non_finite` at the `json.dump`/
  `json.dumps` site, never inside an engine computation. NaN is the correct
  in-memory value for "not measurable here": it propagates through arithmetic,
  it is what pandas/numpy reductions over empty or all-null groups return, and
  downstream code legitimately tests it with `isnan`/`notna`. Sanitizing upstream
  of a computation would turn an honest unmeasurable into a `None` that raises,
  or worse into a number.
* **NEVER MUTATES ITS INPUT.** New dicts/lists are returned; the caller's object
  — very often an engine return value that another code path still reads, or the
  same `summary` dict a report writer formats after the JSON write — is left
  byte-identical. Do not "optimize" this into an in-place walk.
* **`None` is the honest encoding.** `null` is the one strict-JSON value that
  means "no value here". Substituting `0`, `0.0`, or `-1` would fabricate a
  measurement; dropping the key would make an absent leg indistinguishable from
  a leg that was never run.
* **PAIR IT WITH `allow_nan=False`.** The sanitizer is the fix; `allow_nan=False`
  is the enforcement that keeps the fix honest. Sanitize FIRST, then dump with
  `allow_nan=False`, so the flag can only ever fire on a value this walker was
  structurally unable to reach — a loud `ValueError` at write time instead of a
  silently invalid committed artifact. The canonical call:

      path.write_text(json.dumps(sanitize_non_finite(payload), indent=2,
                                 default=str, allow_nan=False))

SCOPE / KNOWN EDGE. Only dict *values* and sequence *items* are walked; dict KEYS
are passed through untouched so key identity is never silently rewritten. A
non-finite float used as a dict key therefore still reaches the encoder — where
`allow_nan=False` raises `ValueError` on it. That is deliberate: such a key is a
bug in the producer, and failing loudly beats renaming it.

Dependency-free on purpose (stdlib `math` only) so any writer — engine module,
`scripts/` harness, or collector — can import it without pulling pandas/numpy.
"""
from __future__ import annotations

import math
from typing import Any

__all__ = ["sanitize_non_finite"]


def sanitize_non_finite(obj: Any) -> Any:
    """Return a copy of ``obj`` with every non-finite float replaced by ``None``.

    NaN, ``+inf`` and ``-inf`` become ``None``. Dicts, lists and tuples are walked
    recursively and rebuilt (tuples come back as lists — that is what ``json``
    encodes them to anyway, so nothing is lost at the write site this feeds).
    Everything else — finite floats, ints, bools, strings, ``None``, and any
    object the encoder's ``default=`` will handle — is returned unchanged.

    ``isinstance(obj, float)`` is the right test rather than an exact type check:
    ``numpy.float64`` subclasses ``float``, so numpy's NaN (the usual source here,
    from a reduction over an empty group) is caught by the same branch. ``bool``
    is NOT a ``float`` subclass, so ``True``/``False`` pass through as bools.

    The input is never mutated — see the module docstring's contract.
    """
    if isinstance(obj, float):
        # Covers numpy.float64 via subclassing. Non-finite -> null; finite floats
        # are returned as-is (no rounding, no type coercion — encoding only).
        return None if not math.isfinite(obj) else obj
    if isinstance(obj, dict):
        # Keys pass through untouched; see the module docstring's SCOPE note.
        return {k: sanitize_non_finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_non_finite(v) for v in obj]
    return obj
