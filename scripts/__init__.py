"""Make ``scripts`` a REGULAR package so the repo-root sys.path pin actually wins.

This file is intentionally EMPTY of executable statements — it is a marker, not a
module. Deleting it, or adding imports/side effects to it, breaks the guarantee
below. ``tests/test_check_script_import_pinning.py`` enforces both properties.

WHY IT EXISTS
-------------
Entry scripts are invoked two ways: as a module (``python -m scripts.check_x``,
which puts the repo root on ``sys.path[0]``) and by file path
(``python3 scripts/check_x.py``, which puts ``<repo>/scripts`` on ``sys.path[0]``
and the repo root NOWHERE). In the second shape every top-level repo import
(``scripts.*``, ``engine.*``, ``lib.*``, ``collectors.*``) resolves from whatever
AMBIENT ``sys.path`` entries the host happens to carry — a ``.pth`` file from a
sibling repo's editable install, a ``PYTHONPATH`` set by a caller, a stray
site-packages directory. Observed on a dev host: a sibling repo's editable
install served a foreign ``scripts`` package, so a CI guard here imported —
and executed — another repository's code.

The repair is a PAIR, and BOTH halves are required:

  1. Each entry script pins its own repo root at the front of ``sys.path``::

         _ROOT = Path(__file__).resolve().parent.parent
         sys.path.insert(0, str(_ROOT))

  2. This file.

Half 1 alone is NOT enough. Without ``__init__.py`` our ``scripts/`` directory is
a PEP 420 NAMESPACE package, and namespace packages LOSE to regular packages
regardless of ``sys.path`` order: the import machinery walks the whole path,
remembers namespace portions, and keeps going — the first REGULAR package
(a directory with ``__init__.py``) it finds anywhere on the path wins, even from
a later position. So a foreign regular ``scripts`` package beats a namespace
``scripts`` that was pinned at position 0. Making this package regular removes
that asymmetry: the pinned entry at position 0 is a regular package and matches
first, deterministically.

Keep this file free of imports and executable code — it is imported implicitly by
every ``scripts.*`` import in the repo, including inside CI guards that must not
acquire new import-time dependencies or side effects.
"""
