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
  3. Column ARITY — a row with more cells than its header is silently truncated by
     ``_parse_markdown_table``'s ``zip(headers, cells)``, which shifts every column
     one place left and drops the last one entirely. That is invisible to (1): the
     shifted Key still matches the key regex and the section prefix, so a malformed
     row reads as a well-formed one. #4625 shipped exactly this — the key was pasted
     twice, so the compiled registry carried ``topic: 'KILL-LIQUIDITY-SHOCK-REVERSAL-
     CLASSIFIER'`` (a key as a topic), the topic as the verdict, the verdict as the
     source, and the real source nowhere at all.
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
_SECTION_RE = re.compile(r"^##\s+(\d+)\.")
_SEPARATOR_RE = re.compile(r"^[-:]+$")


_CELL_BOUNDARY_RE = re.compile(r"(?<!\\)\|")


def _cells(line: str) -> list[str]:
    """Split a GFM pipe row on UNESCAPED boundaries.

    Written out here rather than imported from the compiler on purpose: this is the
    reference the arity test measures the file against, and importing the splitter
    under test would make the guard agree with whatever the compiler currently does.
    """
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|") and not inner.endswith("\\|"):
        inner = inner[:-1]
    return [c.strip().replace("\\|", "|") for c in _CELL_BOUNDARY_RE.split(inner)]


def _real_table_rows():
    """Yield ``(section, header_cells, line_number, row_cells)`` for sections 1-4.

    Deliberately re-derived here rather than reused from the compiler: the compiler
    is what loses the overflow cell, so a guard that asks the compiler how many cells
    a row had can only ever get the truncated answer back.
    """
    md = (_repo_root() / "research" / "DO_NOT_REBUILD.md").read_text(encoding="utf-8")
    section, header = None, None
    for lineno, line in enumerate(md.splitlines(), 1):
        m = _SECTION_RE.match(line)
        if m:
            section, header = int(m.group(1)), None
            continue
        if section not in _SECTION_PREFIX:
            continue
        if not line.strip().startswith("|"):
            continue
        cells = _cells(line)
        if header is None:
            header = cells
            continue
        if all(_SEPARATOR_RE.match(c.replace(" ", "")) for c in cells if c):
            continue
        yield section, header, lineno, cells


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

    def test_every_row_has_exactly_its_header_arity(self):
        """The defect the three tests above cannot see.

        ``_parse_markdown_table`` pads a SHORT row but truncates a LONG one through
        ``zip(headers, cells)``. A row with one extra cell therefore parses cleanly
        with every column shifted one place — key-shaped Key, topic-shaped Verdict —
        and the final column silently dropped. Arity is the only place that shows.
        """
        bad = []
        for section, header, row, cells in _real_table_rows():
            if len(cells) != len(header):
                bad.append(
                    f"§{section} row {row}: {len(cells)} cells vs {len(header)}-column "
                    f"header — starts {cells[0][:48]!r}"
                )
        assert not bad, (
            "DO_NOT_REBUILD.md rows whose cell count does not match their header. "
            "zip() truncates the overflow and shifts every column left, so this ships "
            f"as a well-formed-looking entry: {bad}"
        )


class TestRegistryRowShape:
    """Cell-count integrity — the failure mode the Key tests cannot see.

    `dict(zip(headers, cells))` truncates from the right, so a row with one cell
    too many shifts every column left and DROPS `Ruling / source` on the floor,
    silently. Three rows shipped that way while this suite was unwired:
    KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER carried a duplicated key cell (its
    compiled `topic` was the literal string "KILL-LIQUIDITY-SHOCK-REVERSAL-
    CLASSIFIER"), and two rulings quoting a pipe over-split — PM4-OVERHEAD-SUPPLY
    compiled to verdict "\\" with no source at all. Both survive the key regex,
    because the surviving first cell still looks like a well-formed key.

    This parses the raw markdown independently of `compile_loop_blocklists` on
    purpose: a guard that reuses the splitter it is guarding cannot fail when
    that splitter is what regressed.
    """

    _SECTION_RE = re.compile(r"^##\s+(\d+)\.")
    _UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
    _SEPARATOR_RE = re.compile(r"^[-:]+$")

    def _rows(self):
        """Yield (line_no, section, cells) for every data row in sections 1-4."""
        md = (_repo_root() / "research" / "DO_NOT_REBUILD.md").read_text(encoding="utf-8")
        section = None
        header_len = None
        for line_no, raw in enumerate(md.splitlines(), 1):
            line = raw.strip()
            m = self._SECTION_RE.match(line)
            if m:
                section, header_len = int(m.group(1)), None
                continue
            if section not in _SECTION_PREFIX or not line.startswith("|"):
                continue
            body = line[1:]
            if body.endswith("|") and not body.endswith("\\|"):
                body = body[:-1]
            cells = [c.strip() for c in self._UNESCAPED_PIPE.split(body)]
            if header_len is None:
                header_len = len(cells)
                continue
            if all(self._SEPARATOR_RE.match(c.replace(" ", "")) for c in cells if c):
                continue
            yield line_no, section, cells, header_len

    def test_every_row_has_one_cell_per_header(self):
        bad = [
            f"line {ln} (§{sec}): {len(cells)} cells vs {want} headers -> {cells[0][:40]!r}"
            for ln, sec, cells, want in self._rows()
            if len(cells) != want
        ]
        assert not bad, (
            "registry rows whose cell count does not match their header (columns "
            f"shift left and `Ruling / source` is dropped): {bad}"
        )

    def test_topic_column_is_not_a_registry_key(self):
        """A key-shaped Topic is the fingerprint of a left-shifted row."""
        bad = [
            f"line {ln} (§{sec}): topic {cells[1][:50]!r}"
            for ln, sec, cells, _ in self._rows()
            if len(cells) > 1 and _KEY_RE.match(cells[1])
        ]
        assert not bad, f"Topic column holds a registry key (row is column-shifted): {bad}"


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

    def test_escaped_pipe_stays_inside_its_cell(self, tmp_path: Path):
        """`\\|` is GFM for a literal pipe — splitting on it eats the source column.

        Before the fix, this row compiled to verdict "REDUNDANT — \\" with the
        `Ruling / source` column dropped entirely (the real KILL-PM4-OVERHEAD-SUPPLY
        row, live on main under a dark guard).
        """
        compiler = _load_compiler()
        md = textwrap.dedent("""\
            # DO NOT REBUILD

            ## 2. Killed / refuted signal families and theses

            | Key | Topic | Verdict | Ruling / source |
            |---|---|---|---|
            | KILL-RHO | Rho topic | REDUNDANT — \\|ρ\\| 0.95 vs ext_atr | EI-PM0 run |
        """)
        assert compiler.compile_blocklists(_setup(tmp_path, md)) == 0
        entries = compiler.parse_do_not_rebuild(md)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["key"] == "KILL-RHO"
        assert entry["topic"] == "Rho topic"
        assert entry["verdict"] == "REDUNDANT — |ρ| 0.95 vs ext_atr"
        assert entry["source"] == "EI-PM0 run"

    def test_an_escaped_pipe_is_a_literal_bar_not_a_cell_boundary(self, tmp_path: Path):
        """Pins the COMPILER's splitter, which the arity test above cannot reach.

        The arity test re-derives its own escape-aware split on purpose, so it stays
        green no matter what the compiler does — reverting `_split_row` to a plain
        `.split("|")` does not fail it. This is the assertion that fails instead.

        Two rows shipped mis-split by exactly that: `\\|ρ\\|` in KILL-PM4-OVERHEAD-SUPPLY
        compiled to verdict `'REDUNDANT — \\'` / source `'ρ\\'`, and the conditional-
        expectation bar in KILL-PER-SIGNAL-FAMILY-RELIABILITY pushed its ruling out of
        the row entirely. Both are cells that legitimately contain a bar.
        """
        compiler = _load_compiler()
        md = _KEYED_MD.replace(
            "| KILL-ALPHA | Alpha topic | FORBIDDEN | R-1 |",
            r"| KILL-ALPHA | Alpha topic | REDUNDANT — \|ρ\| 0.95 vs ext_atr | R-1 |",
        )
        entries = compiler.parse_do_not_rebuild(md)
        alpha = next(e for e in entries if e.get("key") == "KILL-ALPHA")
        assert alpha["topic"] == "Alpha topic"
        assert alpha["verdict"] == "REDUNDANT — |ρ| 0.95 vs ext_atr"   # unescaped
        assert alpha["source"] == "R-1"                                # not shifted away

    def test_an_extra_cell_shifts_every_column_and_drops_the_last(self, tmp_path: Path):
        """Pins the MECHANISM behind #4625, not just the row it produced.

        A doubled Key gives the row five cells against a four-column header. The
        parser's ``zip()`` keeps the first four, so `topic` becomes the real key,
        `verdict` becomes the topic, and the source vanishes — with no error. The
        arity test above is the only thing that can see it, so this proves the
        arity test is guarding a real failure and not a hypothetical one.
        """
        compiler = _load_compiler()
        doubled = _KEYED_MD.replace(
            "| KILL-ALPHA | Alpha topic | FORBIDDEN | R-1 |",
            "| KILL-ALPHA | KILL-REAL-KEY | Alpha topic | FORBIDDEN | R-1 |",
        )
        entries = compiler.parse_do_not_rebuild(doubled)
        shifted = next(e for e in entries if e.get("key") == "KILL-ALPHA")
        assert shifted["topic"] == "KILL-REAL-KEY"   # a key parsed as a topic
        assert shifted["verdict"] == "Alpha topic"   # the topic parsed as a verdict
        assert shifted["source"] == "FORBIDDEN"      # the verdict parsed as a source
        assert "R-1" not in str(shifted)             # the real source: gone

        # ... and the arity check is what turns that silence into a failure.
        header = ["Key", "Topic", "Verdict", "Ruling / source"]
        assert len(_cells("| KILL-ALPHA | KILL-REAL-KEY | Alpha topic | FORBIDDEN | R-1 |")) != len(header)

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
