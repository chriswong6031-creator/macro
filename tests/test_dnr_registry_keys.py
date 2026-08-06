"""tests/test_dnr_registry_keys.py — stable Key column of the kill registry.

research/DO_NOT_REBUILD.md rows are cited across the repo as `DNR:<KEY>`
(append convention in the registry preamble). Row/line numbers shift on every
append and mis-resolved in the wild (a "DNR row 49" citation stopped pointing
at the graded-population fence, 2026-08-05), so the Key column is the citation
anchor. These tests keep that contract enforceable:

  1. REAL registry — every row in sections 1-4 carries a Key with the correct
     section prefix (KILL- §1-2, LAW- §3, HOLD- §4), unique file-wide. This is
     the gate that stops a future append from shipping keyless.
  2. Compiler — a Key column round-trips into config/compiled_kill_registry.yml,
     duplicate keys hard-fail, and keyless tables (fixtures, older forks) still
     compile.
"""
from __future__ import annotations

import importlib.util
import re
import textwrap
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_compiler():
    path = _repo_root() / "scripts" / "compile_loop_blocklists.py"
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_SECTION_PREFIX = {1: "KILL-", 2: "KILL-", 3: "LAW-", 4: "HOLD-"}
_KEY_RE = re.compile(r"^(KILL|LAW|HOLD)-[A-Z0-9][A-Z0-9-]+$")


# ---------------------------------------------------------------------------
# 1. Real registry — the enforcement gate for future appends
# ---------------------------------------------------------------------------

class TestRealRegistryKeys:
    def _entries(self):
        compiler = _load_compiler()
        md = (_repo_root() / "research" / "DO_NOT_REBUILD.md").read_text(encoding="utf-8")
        entries = compiler.parse_do_not_rebuild(md)
        assert entries, "no entries parsed from the real registry"
        return entries

    def test_every_row_has_a_key(self):
        missing = [e["topic"][:70] for e in self._entries() if not e.get("key")]
        assert not missing, (
            "DO_NOT_REBUILD.md rows without a Key (append convention: every row "
            f"mints one; cite as DNR:<KEY>): {missing}"
        )

    def test_keys_are_wellformed_and_section_prefixed(self):
        bad = []
        for e in self._entries():
            key = e.get("key", "")
            want = _SECTION_PREFIX[e["section"]]
            if not _KEY_RE.match(key) or not key.startswith(want):
                bad.append(f"§{e['section']} {key!r} ({e['topic'][:50]})")
        assert not bad, f"malformed or wrong-prefix registry keys: {bad}"

    def test_keys_are_unique_filewide(self):
        keys = [e["key"] for e in self._entries()]
        dupes = sorted({k for k in keys if keys.count(k) > 1})
        assert not dupes, f"duplicate registry keys (citations would be ambiguous): {dupes}"


# ---------------------------------------------------------------------------
# 2. Compiler behavior (hermetic fixtures)
# ---------------------------------------------------------------------------

_KEYED_MD = textwrap.dedent("""\
    # DO NOT REBUILD

    ## 1. Forbidden by ruling (design-level)

    | Key | Topic | Verdict | Ruling / source |
    |---|---|---|---|
    | KILL-ALPHA | Alpha topic | FORBIDDEN | R-1 |
    | KILL-BETA | Beta topic | FORBIDDEN | R-2 |

    ## 4. Held / suspended — do not revive without explicit ruling

    | Key | Topic | State | Ruling / source |
    |---|---|---|---|
    | HOLD-GAMMA | Gamma topic | HOLD | R-3 |
""")


def _setup(tmp_path: Path, md: str) -> Path:
    (tmp_path / "research").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / "research" / "DO_NOT_REBUILD.md").write_text(md, encoding="utf-8")
    return tmp_path


class TestCompilerKeyHandling:
    def test_key_column_reaches_compiled_registry(self, tmp_path: Path):
        compiler = _load_compiler()
        assert compiler.compile_blocklists(_setup(tmp_path, _KEYED_MD)) == 0
        reg = (tmp_path / "config" / "compiled_kill_registry.yml").read_text(encoding="utf-8")
        assert "key: KILL-ALPHA" in reg
        assert "key: HOLD-GAMMA" in reg

    def test_duplicate_keys_hard_fail(self, tmp_path: Path):
        compiler = _load_compiler()
        dup = _KEYED_MD.replace("KILL-BETA", "KILL-ALPHA")
        assert compiler.compile_blocklists(_setup(tmp_path, dup)) == 1

    def test_keyless_tables_still_compile(self, tmp_path: Path):
        """Backward compat: 3-column fixtures (and any older fork) stay green."""
        compiler = _load_compiler()
        keyless = textwrap.dedent("""\
            # DO NOT REBUILD

            ## 2. Killed / refuted signal families and theses

            | Topic | Verdict | Ruling / source |
            |---|---|---|
            | Old topic | KILLED | R-9 |
        """)
        assert compiler.compile_blocklists(_setup(tmp_path, keyless)) == 0
        reg = (tmp_path / "config" / "compiled_kill_registry.yml").read_text(encoding="utf-8")
        assert "Old topic" in reg
        assert "key:" not in reg
