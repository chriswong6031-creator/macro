"""Hostile tests for the Finviz STRUCTURE refresh contract (`--refresh-tree`).

The contract is preregistered in research/theme_graph/W3A_LOCAL_THEME_PLANE_PLAN.md
§3 and these are its §5 acceptance tests A-C, plus the nightly key-drift tripwire.

What the refresh actually risks, and therefore what is tested here: the source is
an UNDOCUMENTED, hash-rotated webpack chunk. The realistic failure is not "the
vendor rewrote the taxonomy" — the structure has not moved since June — it is
"our parser read half of it and we promoted the half". A partial tree that lands
in `themes_tree.json` is silent and permanent: the graph closes thousands of
memberships as if the source had dropped them, the PIT tape records the
truncation as a real vintage, and nothing downstream can tell the difference. So
every test below asserts the SAME invariant from a different angle — a refusal
leaves `themes_tree.json` BYTE-IDENTICAL, appends nothing to the PIT tape, and
leaves a receipt saying why.

  A  half-tree (20 of 40 themes)      -> interlock refusal, bytes unchanged, no append
  B  45% of memberships removed       -> interlock refusal, receipt records the shrink
     + a 2% churn at real scale       -> PROMOTES atomically, appends history exactly once
  C  displayName changed, key stable  -> promotes (a label move is not identity churn)
     + key renamed, members 90% same  -> refusal + key_rename probation proposal,
                                         and --allow-shrink does NOT override it

Zero network: a fake Finviz serves synthetic map/runtime/chunk payloads built by
rendering a normalized tree BACK into the vendor's minified-JS shape, so the
trace, the strict literal parser and the normaliser all execute for real. Every
path is a tmp path — nothing in data/ is read or written by this suite.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts import fetch_finviz_themes as ftr


# ------------------------------------------------------------------ #
# fixture source: render a normalized tree back into Finviz's shape
# ------------------------------------------------------------------ #

MAP_HASH = "a1b2c3d4"
RUNTIME_HASH = "e5f6a7b8"
CHUNK_ID = "6574"
MODULE_ID = "13014"
CHUNK_HASH = "c9d0e1f2"

MAP_PAGE_URL = "https://finviz.com/map?t=themes"
MAP_JS_URL = f"https://finviz.com/assets/dist/map.v1.{MAP_HASH}.js"
RUNTIME_JS_URL = f"https://finviz.com/assets/dist/runtime.v1.{RUNTIME_HASH}.js"
CHUNK_URL = f"https://finviz.com/assets/dist/{CHUNK_ID}.v1.{CHUNK_HASH}.js"

NOW = datetime(2026, 8, 14, 23, 30, 0, tzinfo=timezone.utc)


def make_tree(n_themes: int = 40, n_subs: int = 7, n_members: int = 20) -> list[dict]:
    """A deterministic tree in the committed schema (40x7x20 = 5,600 memberships).

    Sized at the live scale on purpose: the interlocks are FRACTIONS, and a
    three-row toy fixture cannot tell a 2% churn from a 45% one.
    """
    return [
        {
            "theme": f"Theme {ti:02d}",
            "key": f"Theme {ti:02d}",
            "subsectors": [
                {
                    "key": f"t{ti:02d}s{si}",
                    "name": f"Sub {ti:02d}-{si}",
                    "description": f"Description for {ti:02d}-{si}",
                    "members": [f"T{ti:02d}{si}{mi:02d}" for mi in range(n_members)],
                }
                for si in range(n_subs)
            ],
        }
        for ti in range(n_themes)
    ]


def js_literal(tree: list[dict], groups: list[list[str]] | None = None) -> str:
    """Render a normalized tree into the vendor's MINIFIED object literal.

    Bare identifier keys and a supergroup layer, exactly as the live chunk carries
    them — so the fixture exercises the reader that cannot use ``json.loads``.
    """
    if groups is None:
        groups = [[t["theme"] for t in tree]]
    by_name = {t["theme"]: t for t in tree}

    def sub(s: dict) -> str:
        return ("{name:%s,displayName:%s,description:%s,extra:%s,value:%d}" % (
            json.dumps(s["key"]), json.dumps(s["name"]), json.dumps(s["description"]),
            json.dumps(",".join(s["members"])), len(s["members"])))

    def theme(t: dict) -> str:
        return "{name:%s,children:[%s]}" % (
            json.dumps(t["theme"]), ",".join(sub(s) for s in t["subsectors"]))

    def group(i: int, names: list[str]) -> str:
        return "{name:%s,children:[%s]}" % (
            json.dumps(str(i + 1)), ",".join(theme(by_name[n]) for n in names))

    return '{name:"Root",children:[%s]}' % ",".join(
        group(i, g) for i, g in enumerate(groups))


class FakeFinviz:
    """Serves the four trace hops from memory; records what was asked for."""

    def __init__(self, tree: list[dict] | None = None, *,
                 groups: list[list[str]] | None = None,
                 chunk_body: str | None = None,
                 fail_url: str | None = None,
                 map_page: str | None = None):
        body = chunk_body if chunk_body is not None else js_literal(tree or [], groups)
        self.fail_url = fail_url
        self.asked: list[str] = []
        self.payloads = {
            MAP_PAGE_URL: (map_page if map_page is not None else (
                "<!doctype html><html><head>"
                f'<script src="/assets/dist/map.v1.{MAP_HASH}.js"></script>'
                f'<script src="/assets/dist/runtime.v1.{RUNTIME_HASH}.js"></script>'
                "</head><body>themes map</body></html>")).encode(),
            MAP_JS_URL: (
                "!function(){switch(n){"
                "case a.IZ.Sector:return s(r.e(1111).then(r.t.bind(r,2222,23)));"
                f"case a.IZ.Themes:return s(r.e({CHUNK_ID}).then(r.t.bind(r,{MODULE_ID},23)))"
                "}}();").encode(),
            RUNTIME_JS_URL: (
                '(()=>{var e={1111:"0000aaaa",%s:"%s",9999:"ffff0000"};})();'
                % (CHUNK_ID, CHUNK_HASH)).encode(),
            CHUNK_URL: (
                "(self.wp=self.wp||[]).push([[%s],{9999:e=>{e.exports=1},%s(e){e.exports=%s}}]);"
                % (CHUNK_ID, MODULE_ID, body)).encode(),
        }

    def fetch(self, url: str, *, referer: str | None = None,
              rows: list[dict] | None = None) -> bytes:
        self.asked.append(url)
        retrieved = "2026-08-14T23:30:00+00:00"
        if url == self.fail_url or url not in self.payloads:
            if rows is not None:
                rows.append({"url": url, "retrieved_at_utc": retrieved,
                             "http_status": 403, "byte_size": 0, "sha256": None, "ok": False})
            raise RuntimeError(f"GET failed: {url} (HTTP 403, 0B body)")
        body = self.payloads[url]
        if rows is not None:
            rows.append({"url": url, "retrieved_at_utc": retrieved, "http_status": 200,
                         "byte_size": len(body),
                         "sha256": hashlib.sha256(body).hexdigest(), "ok": True})
        return body


class Store:
    """A tmp themes_heatmap store seeded with ``tree``, plus its starting bytes."""

    def __init__(self, tmp_path: Path, tree: list[dict] | None):
        self.paths = ftr._RefreshPaths(
            tree=tmp_path / "themes_tree.json",
            tree_history=tmp_path / "tree_history.jsonl",
            receipts_dir=tmp_path / "tree_refresh_receipts",
            proposals=tmp_path / "probation" / "proposals.jsonl",
        )
        self.seeded = tree is not None
        if tree is not None:
            # Seed through the module's own serialiser so a no-change promotion is
            # provably byte-identical rather than merely equal-after-parsing.
            self.paths.tree.write_bytes(ftr._tree_json_bytes(tree))
            self.before = self.paths.tree.read_bytes()
        else:
            self.before = None

    # --- assertions the whole suite leans on --- #
    def assert_tree_unchanged(self) -> None:
        assert self.paths.tree.read_bytes() == self.before, \
            "a refused refresh must leave themes_tree.json BYTE-IDENTICAL"

    def assert_no_history(self) -> None:
        assert not self.paths.tree_history.exists() or \
            self.paths.tree_history.read_text().strip() == "", \
            "a refused refresh must append nothing to the PIT tape"

    def history_lines(self) -> list[dict]:
        if not self.paths.tree_history.exists():
            return []
        return [json.loads(x) for x in self.paths.tree_history.read_text().splitlines() if x.strip()]

    def receipts(self) -> list[dict]:
        if not self.paths.receipts_dir.exists():
            return []
        return [json.loads(p.read_text()) for p in sorted(self.paths.receipts_dir.glob("*.json"))]

    def only_receipt(self) -> dict:
        got = self.receipts()
        assert len(got) == 1, f"expected exactly one receipt, got {len(got)}"
        return got[0]

    def proposals(self) -> list[dict]:
        if not self.paths.proposals.exists():
            return []
        return [json.loads(x) for x in self.paths.proposals.read_text().splitlines() if x.strip()]


def run(store: Store, source: FakeFinviz, *, now: datetime = NOW, **kw) -> int:
    return ftr.refresh_tree(paths=store.paths, fetch=source.fetch,
                            asof="2026-08-14", now_utc=now, **kw)


BASE = make_tree()


# ------------------------------------------------------------------ #
# the promoted file's FORMAT — pinned independently of the writer
# ------------------------------------------------------------------ #

def _committed_tree_bytes() -> bytes | None:
    """The committed themes_tree.json, from the worktree or from git HEAD.

    `data/` is one of the directories a session worktree omits by default
    (config/sparse_worktree.json), so a working-tree read alone would make this
    pin silently vanish exactly where sessions run. git still holds the bytes.
    """
    p = ftr.TREE_PATH
    try:
        if p.is_file() and p.stat().st_size:
            return p.read_bytes()
    except OSError:  # pragma: no cover - unreadable worktree file
        pass
    try:
        out = subprocess.run(
            ["git", "show", "HEAD:data/themes_heatmap/themes_tree.json"],
            cwd=str(ftr.ROOT), capture_output=True, timeout=60)
        if out.returncode == 0 and out.stdout:
            return out.stdout
    except Exception:  # noqa: BLE001 - no git, shallow tree, etc.
        pass
    return None


class TestPromotedFormatMatchesTheCommittedFile:
    """A promotion must write the format the committed file is STORED in.

    Otherwise every refresh — including one that changed nothing — lands as a
    whole-file diff and a reviewer can no longer see the delta a promotion
    carries. Pinned two ways deliberately: the literal-shape assertion is
    INDEPENDENT of ``_tree_json_bytes`` (a writer asserted against itself cannot
    fail, and the rest of this suite seeds its fixtures through that writer),
    while the byte-equality against the real committed tree is the contract.
    """

    def test_shape_is_two_space_indent_with_no_trailing_newline(self):
        got = ftr._tree_json_bytes([{
            "theme": "T", "key": "T",
            "subsectors": [{"key": "k", "name": "N", "description": "D",
                            "members": ["AAA", "BBB"]}],
        }]).decode()
        assert got.startswith('[\n  {\n    "theme": "T",\n    "key": "T",\n'
                              '    "subsectors": [\n      {\n        "key": "k",')
        assert '\n        "members": [\n          "AAA",\n          "BBB"\n        ]' in got
        assert got.endswith("]") and not got.endswith("\n"), \
            "the committed file carries NO trailing newline"

    def test_round_trips_the_committed_tree_byte_for_byte(self):
        committed = _committed_tree_bytes()
        if committed is None:  # pragma: no cover - no worktree copy and no git
            pytest.skip("themes_tree.json unreadable from the worktree and from git HEAD")
        assert ftr._tree_json_bytes(json.loads(committed)) == committed


# ------------------------------------------------------------------ #
# the strict literal reader (no eval, loud on anything unexpected)
# ------------------------------------------------------------------ #

class TestStrictParser:
    def test_bare_identifier_keys_and_minified_booleans(self):
        src = '{name:"x",ok:!0,off:!1,n:12,f:-1.5e3,z:null}'
        val, end = ftr.parse_js_object(src)
        assert val == {"name": "x", "ok": True, "off": False, "n": 12, "f": -1500.0, "z": None}
        assert end == len(src), "the reader must consume the whole literal"

    def test_single_quotes_escapes_and_trailing_comma(self):
        val, _ = ftr.parse_js_object("{a:'it\\'s',b:\"\\u00e9\\n\",c:[1,2,],}")
        assert val == {"a": "it's", "b": "\u00e9\n", "c": [1, 2]}

    def test_function_expression_raises(self):
        """A vendor refactor that inlines a function must NOT parse as data."""
        with pytest.raises(ftr.JsParseError):
            ftr.parse_js_object('{name:"Root",children:[function(){return 1}]}')

    def test_unterminated_string_raises(self):
        with pytest.raises(ftr.JsParseError):
            ftr.parse_js_object('{name:"Roo')

    def test_duplicate_key_raises(self):
        with pytest.raises(ftr.JsParseError):
            ftr.parse_js_object('{a:1,a:2}')

    def test_slice_balanced_ignores_braces_inside_strings(self):
        src = 'x={desc:"a { brace } inside",n:1};tail'
        got = ftr._slice_balanced(src, src.index("{"))
        assert got == '{desc:"a { brace } inside",n:1}'

    def test_slice_balanced_unbalanced_raises(self):
        with pytest.raises(ftr.JsParseError):
            ftr._slice_balanced('{a:{b:1}', 0)


# ------------------------------------------------------------------ #
# normalisation + completeness (complete-or-fail)
# ------------------------------------------------------------------ #

class TestNormalisationAndCompleteness:
    def test_supergroups_flatten_in_group_order(self):
        tree = make_tree(n_themes=6, n_subs=2, n_members=3)
        names = [t["theme"] for t in tree]
        groups = [names[:4], names[4:]]
        root, _ = ftr.parse_js_object(js_literal(tree, groups))
        out, notes, got_groups = ftr._normalise_tree(root)
        assert [t["theme"] for t in out] == names, "flattening must preserve source order"
        assert [g["group"] for g in got_groups] == ["1", "2"]
        assert got_groups[0]["themes"] == names[:4]
        assert any("supergroup layer" in n for n in notes)

    def test_unknown_subsector_field_raises(self):
        """A NEW vendor field might carry membership data; dropping it silently is
        exactly the invisible loss complete-or-fail exists to stop."""
        root, _ = ftr.parse_js_object(
            '{name:"Root",children:[{name:"1",children:[{name:"T",children:['
            '{name:"k",displayName:"K",description:"d",extra:"AAA",value:1,newField:"?"}]}]}]}')
        with pytest.raises(ftr.TreeIntegrityError, match="newField"):
            ftr._normalise_tree(root)

    def test_missing_extra_csv_raises(self):
        root, _ = ftr.parse_js_object(
            '{name:"Root",children:[{name:"1",children:[{name:"T",children:['
            '{name:"k",displayName:"K",description:"d",value:1}]}]}]}')
        with pytest.raises(ftr.TreeIntegrityError, match="extra"):
            ftr._normalise_tree(root)

    def test_non_root_raises(self):
        root, _ = ftr.parse_js_object('{name:"Nope",children:[]}')
        with pytest.raises(ftr.TreeIntegrityError):
            ftr._normalise_tree(root)

    def test_theme_with_zero_subthemes_refuses(self):
        tree = make_tree(n_themes=3, n_subs=2, n_members=2)
        tree[1]["subsectors"] = []
        with pytest.raises(ftr.TreeIntegrityError, match="ZERO subthemes"):
            ftr.assert_complete_tree(tree)

    def test_empty_member_csv_refuses(self):
        tree = make_tree(n_themes=3, n_subs=2, n_members=2)
        tree[2]["subsectors"][0]["members"] = []
        with pytest.raises(ftr.TreeIntegrityError, match="EMPTY member CSV"):
            ftr.assert_complete_tree(tree)

    def test_duplicate_subtheme_key_refuses(self):
        """Graph node identity is `ltheme:finviz:<subtheme_key>` — a duplicate key
        would collapse two concepts into one node."""
        tree = make_tree(n_themes=2, n_subs=2, n_members=2)
        tree[1]["subsectors"][0]["key"] = tree[0]["subsectors"][0]["key"]
        with pytest.raises(ftr.TreeIntegrityError, match="globally unique"):
            ftr.assert_complete_tree(tree)

    def test_empty_tree_refuses(self):
        with pytest.raises(ftr.TreeIntegrityError):
            ftr.assert_complete_tree([])


# ------------------------------------------------------------------ #
# pure diff + interlock arithmetic (no I/O)
# ------------------------------------------------------------------ #

class TestPureDiffAndInterlocks:
    def test_membership_diff_counts_pairs_not_tickers(self):
        """A ticker that MOVES between subthemes is one removal and one addition —
        a ticker-set diff would have scored it as no change at all."""
        prev = make_tree(n_themes=1, n_subs=2, n_members=2)
        new = json.loads(json.dumps(prev))
        moved = new[0]["subsectors"][0]["members"].pop()
        new[0]["subsectors"][1]["members"].append(moved)
        d = ftr.diff_trees(prev, new)
        assert (d["memberships"]["removed"], d["memberships"]["added"]) == (1, 1)
        assert (d["tickers"]["removed"], d["tickers"]["added"]) == (0, 0)

    def test_lost_subtheme_removes_all_its_pairs(self):
        prev = make_tree(n_themes=1, n_subs=2, n_members=5)
        new = json.loads(json.dumps(prev))
        new[0]["subsectors"].pop()
        d = ftr.diff_trees(prev, new)
        assert d["memberships"]["removed"] == 5
        assert d["subthemes"]["removed"] == ["t00s1"]

    @pytest.mark.parametrize("n_new, refuses", [(40, False), (39, True), (41, False)])
    def test_any_theme_decrease_refuses(self, n_new, refuses):
        d = ftr.diff_trees(make_tree(40, 2, 2), make_tree(n_new, 2, 2))
        got = [r for r in ftr.evaluate_interlocks(d) if r.startswith("theme_count_decrease")]
        assert bool(got) is refuses

    @pytest.mark.parametrize("kept, refuses", [
        (100, False),  # -0%    — no shrink at all
        (96, False),   # -4%
        (95, False),   # -5.0% of 100 — exactly AT the wall; the rule is `>5%`, so it passes
        (94, True),    # -6.0%  — over the wall
    ])
    def test_subtheme_shrink_wall_is_strictly_greater(self, kept, refuses):
        prev = make_tree(n_themes=100, n_subs=1, n_members=2)
        new = prev[:kept]
        d = ftr.diff_trees(prev, new)
        # Neutralise the theme wall: only the SUBTHEME fraction is under test here
        # (the fixture happens to carry one subtheme per theme).
        d["themes"] = {"prev": 1, "new": 1, "added": [], "removed": []}
        got = [r for r in ftr.evaluate_interlocks(d) if r.startswith("subtheme_shrink")]
        assert bool(got) is refuses

    @pytest.mark.parametrize("removed, refuses", [(250, False), (251, True)])
    def test_membership_shrink_wall_is_strictly_greater(self, removed, refuses):
        prev = make_tree(n_themes=1, n_subs=1, n_members=1000)
        new = json.loads(json.dumps(prev))
        new[0]["subsectors"][0]["members"] = prev[0]["subsectors"][0]["members"][removed:]
        d = ftr.diff_trees(prev, new)
        got = [r for r in ftr.evaluate_interlocks(d) if r.startswith("membership_shrink")]
        assert bool(got) is refuses

    def test_allow_shrink_clears_the_three_shrink_walls(self):
        d = ftr.diff_trees(make_tree(40, 7, 20), make_tree(10, 7, 20))
        assert len(ftr.evaluate_interlocks(d)) >= 2
        assert ftr.evaluate_interlocks(d, allow_shrink=True) == []

    def test_bootstrap_against_no_prior_tree_refuses_nothing(self):
        d = ftr.diff_trees([], make_tree(3, 2, 2))
        assert ftr.evaluate_interlocks(d) == []

    def test_shrink_stats_carry_their_thresholds(self):
        """A measurement without the wall it was judged against cannot be
        re-adjudicated later if the wall moves."""
        st = ftr.shrink_stats(ftr.diff_trees(make_tree(40, 7, 20), make_tree(40, 7, 20)))
        assert st["max_membership_removal_frac"] == ftr.MAX_MEMBERSHIP_REMOVAL_FRAC == 0.25
        assert st["max_subtheme_shrink_frac"] == ftr.MAX_SUBTHEME_SHRINK_FRAC == 0.05
        assert st["max_theme_shrink"] == ftr.MAX_THEME_SHRINK == 0


# ------------------------------------------------------------------ #
# A — half tree
# ------------------------------------------------------------------ #

class TestAHalfTree:
    """The realistic catastrophe: the chunk walk stopped halfway and the parse
    still looked structurally valid."""

    def test_half_tree_refuses_and_changes_nothing(self, tmp_path):
        store = Store(tmp_path, BASE)
        rc = run(store, FakeFinviz(BASE[:20]))

        assert rc == ftr.EXIT_REFUSED == 3
        store.assert_tree_unchanged()
        store.assert_no_history()

        rec = store.only_receipt()
        assert rec["promoted"] is False
        assert rec["reason"] == "refused_by_interlock"
        assert any(r.startswith("theme_count_decrease") for r in rec["refusal_reasons"])
        assert rec["counts"]["themes"] == 20
        assert rec["shrink"]["theme_delta"] == -20
        assert rec["prev_tree_sha256"] == ftr._tree_hash(BASE)

    def test_half_tree_receipt_names_the_source_it_read(self, tmp_path):
        """The refusal receipt IS the audit trail — it must be replayable."""
        store = Store(tmp_path, BASE)
        run(store, FakeFinviz(BASE[:20]))
        rec = store.only_receipt()
        assert rec["trace"]["chunk_url"] == CHUNK_URL
        assert rec["trace"]["module_id"] == MODULE_ID
        assert {f["url"] for f in rec["fetches"]} == {
            MAP_PAGE_URL, MAP_JS_URL, RUNTIME_JS_URL, CHUNK_URL}
        assert all(f["ok"] and f["sha256"] for f in rec["fetches"])
        assert rec["parser_version"] == ftr.PARSER_VERSION == "finviz_tree_refresh.v1"


# ------------------------------------------------------------------ #
# B — shrink interlock, and the passing scale that must still promote
# ------------------------------------------------------------------ #

def _drop_members(tree: list[dict], per_sub: int) -> list[dict]:
    out = json.loads(json.dumps(tree))
    for t in out:
        for s in t["subsectors"]:
            s["members"] = s["members"][per_sub:]
    return out


def _churn_2pct(tree: list[dict]) -> list[dict]:
    """Remove 112 of 5,600 memberships = exactly 2.0% (one member from 112 subs)."""
    out = json.loads(json.dumps(tree))
    subs = [s for t in out for s in t["subsectors"]]
    for s in subs[:112]:
        s["members"] = s["members"][:-1]
    return out


class TestBMembershipShrink:
    def test_45_percent_removal_refuses_and_records_the_shrink(self, tmp_path):
        store = Store(tmp_path, BASE)
        shrunk = _drop_members(BASE, 9)  # 9 of 20 per subtheme = 45%

        rc = run(store, FakeFinviz(shrunk))

        assert rc == ftr.EXIT_REFUSED
        store.assert_tree_unchanged()
        store.assert_no_history()

        rec = store.only_receipt()
        assert rec["promoted"] is False
        assert any(r.startswith("membership_shrink") for r in rec["refusal_reasons"])
        sh = rec["shrink"]
        assert sh["prior_memberships"] == 5600
        assert sh["membership_removals"] == 2520
        assert sh["membership_removal_frac"] == pytest.approx(0.45)
        assert sh["max_membership_removal_frac"] == 0.25
        # structure intact — this is a MEMBERSHIP catastrophe only, and the receipt
        # must say so rather than blaming the structure walls.
        assert sh["theme_delta"] == 0 and sh["subtheme_delta"] == 0
        assert len(rec["refusal_reasons"]) == 1

    def test_allow_shrink_promotes_the_same_45_percent(self, tmp_path):
        """The wall is an interlock, not a prohibition: an operator who has
        established the contraction is real can sign for it."""
        store = Store(tmp_path, BASE)
        shrunk = _drop_members(BASE, 9)
        rc = run(store, FakeFinviz(shrunk), allow_shrink=True)
        assert rc == ftr.EXIT_PROMOTED
        assert json.loads(store.paths.tree.read_text()) == shrunk
        assert store.only_receipt()["allow_shrink"] is True

    def test_two_percent_churn_promotes_atomically_and_appends_once(self, tmp_path):
        store = Store(tmp_path, BASE)
        churned = _churn_2pct(BASE)

        rc = run(store, FakeFinviz(churned))

        assert rc == ftr.EXIT_PROMOTED == 0
        assert store.paths.tree.read_bytes() == ftr._tree_json_bytes(churned)
        assert json.loads(store.paths.tree.read_text()) == churned
        assert not (store.paths.tree.parent / (store.paths.tree.name + ".tmp")).exists(), \
            "the atomic tmp file must not survive the rename"

        hist = store.history_lines()
        assert len(hist) == 1
        assert hist[0]["asof"] == "2026-08-14"
        assert hist[0]["sha256"] == ftr._tree_hash(churned)

        rec = store.only_receipt()
        assert rec["promoted"] is True and rec["reason"] == "promoted"
        assert rec["refusal_reasons"] == []
        assert rec["shrink"]["membership_removal_frac"] == pytest.approx(0.02)
        assert rec["history_appended"] is True
        assert rec["new_tree_sha256"] == ftr._tree_hash(churned)

    def test_rerunning_the_same_promotion_does_not_double_append(self, tmp_path):
        """`exactly once` has to survive the operator running it twice."""
        store = Store(tmp_path, BASE)
        churned = _churn_2pct(BASE)
        assert run(store, FakeFinviz(churned)) == ftr.EXIT_PROMOTED
        assert run(store, FakeFinviz(churned), now=NOW + timedelta(minutes=5)) == ftr.EXIT_PROMOTED
        assert len(store.history_lines()) == 1, "unchanged tree must not re-append the tape"
        assert len(store.receipts()) == 2, "but every RUN is receipted"
        assert store.receipts()[1]["tree_changed"] is False


# ------------------------------------------------------------------ #
# C — identity: a label move is not a key move
# ------------------------------------------------------------------ #

def _rename_display_name(tree: list[dict]) -> list[dict]:
    out = json.loads(json.dumps(tree))
    out[0]["subsectors"][0]["name"] = "Renamed Label"
    return out


def _rename_key_j90(tree: list[dict]) -> list[dict]:
    """Old key out, new key in, 18 of the old 20 members carried over.

    Jaccard = |A n B| / |A u B| = 18 / 20 = 0.90 — above the 0.80 wall.
    """
    out = json.loads(json.dumps(tree))
    s = out[0]["subsectors"][0]
    s["key"] = "t00s0v2"
    s["members"] = s["members"][:18]
    return out


class TestCIdentity:
    def test_display_name_change_promotes_without_interlock(self, tmp_path):
        """A name change is not identity churn at TREE level — the graph layer
        owns labels, and refusing here would block every cosmetic vendor edit."""
        store = Store(tmp_path, BASE)
        renamed = _rename_display_name(BASE)

        rc = run(store, FakeFinviz(renamed))

        assert rc == ftr.EXIT_PROMOTED
        assert json.loads(store.paths.tree.read_text())[0]["subsectors"][0]["name"] == "Renamed Label"
        rec = store.only_receipt()
        assert rec["refusal_reasons"] == []
        assert rec["identity_report"]["renames"] == []
        assert rec["diff"]["subthemes"]["name_changes"] == [
            {"key": "t00s0", "prev": "Sub 00-0", "new": "Renamed Label"}]
        assert rec["diff"]["subthemes"]["added"] == [] and rec["diff"]["subthemes"]["removed"] == []
        assert (rec["diff"]["memberships"]["added"], rec["diff"]["memberships"]["removed"]) == (0, 0)
        assert store.proposals() == []

    def test_key_rename_refuses_and_files_a_probation_proposal(self, tmp_path):
        store = Store(tmp_path, BASE)
        renamed = _rename_key_j90(BASE)

        rc = run(store, FakeFinviz(renamed))

        assert rc == ftr.EXIT_REFUSED
        store.assert_tree_unchanged()
        store.assert_no_history()

        rec = store.only_receipt()
        assert rec["promoted"] is False
        # The shrink walls are UNTOUCHED here (20 of 5,600 pairs move): the refusal
        # is identity, and only identity.
        assert len(rec["refusal_reasons"]) == 1
        assert rec["refusal_reasons"][0].startswith("suspected_key_rename")
        ident = rec["identity_report"]
        assert ident["threshold_jaccard"] == ftr.RENAME_JACCARD_MIN == 0.80
        assert len(ident["renames"]) == 1
        r = ident["renames"][0]
        assert (r["old_key"], r["new_key"]) == ("t00s0", "t00s0v2")
        assert r["jaccard"] == pytest.approx(0.9)
        assert (r["old_member_count"], r["new_member_count"], r["shared_member_count"]) == (20, 18, 18)

        rows = store.proposals()
        assert len(rows) == 1
        p = rows[0]
        assert p["kind"] == "key_rename"
        assert p["proposed_by"] == "refresh_identity"
        assert p["status"] == "proposed" and p["ratified_by"] is None
        assert p["created"] == NOW.isoformat(timespec="seconds")
        assert p["proposal_id"] in ident["proposal_ids"]
        assert p["evidence"]["old_key"] == "t00s0" and p["evidence"]["new_key"] == "t00s0v2"
        assert p["evidence"]["jaccard"] == pytest.approx(0.9)
        assert p["evidence"]["prev_tree_sha256"] == ftr._tree_hash(BASE)
        assert p["evidence_refs"] and p["evidence_refs"][0].endswith(".json")

    def test_allow_shrink_does_not_override_a_key_rename(self, tmp_path):
        """No flag override BY DESIGN: auto-promoting fakes an identity break,
        auto-merging rewrites identity. Both must stay impossible."""
        store = Store(tmp_path, BASE)
        rc = run(store, FakeFinviz(_rename_key_j90(BASE)), allow_shrink=True)
        assert rc == ftr.EXIT_REFUSED
        store.assert_tree_unchanged()
        assert store.only_receipt()["refusal_reasons"][0].startswith("suspected_key_rename")

    def test_rerun_does_not_duplicate_the_proposal(self, tmp_path):
        """An operator investigating a refusal runs it more than once; a queue
        that grows a row per attempt is unreadable."""
        store = Store(tmp_path, BASE)
        renamed = _rename_key_j90(BASE)
        run(store, FakeFinviz(renamed))
        run(store, FakeFinviz(renamed), now=NOW + timedelta(minutes=7))
        assert len(store.proposals()) == 1
        assert len(store.receipts()) == 2

    def test_below_threshold_overlap_is_not_a_rename(self, tmp_path):
        """A genuinely new subtheme that happens to share some members must NOT
        be laundered into a rename — Jaccard 0.5 is well under the 0.8 wall."""
        prev = make_tree(n_themes=1, n_subs=2, n_members=10)
        new = json.loads(json.dumps(prev))
        new[0]["subsectors"][0]["key"] = "brandnew"
        new[0]["subsectors"][0]["members"] = (
            prev[0]["subsectors"][0]["members"][:5] + [f"NEW{i}" for i in range(5)])
        assert ftr.detect_key_renames(prev, new) == []

    def test_rename_detection_is_pure_and_deterministic(self):
        renames = ftr.detect_key_renames(BASE, _rename_key_j90(BASE))
        assert [(r["old_key"], r["new_key"]) for r in renames] == [("t00s0", "t00s0v2")]
        assert ftr.detect_key_renames(BASE, BASE) == []


# ------------------------------------------------------------------ #
# fetch / parse failure — the receipt is still the audit trail
# ------------------------------------------------------------------ #

class TestFetchAndParseFailures:
    @pytest.mark.parametrize("fail_url", [MAP_PAGE_URL, MAP_JS_URL, RUNTIME_JS_URL, CHUNK_URL])
    def test_any_hop_failing_refuses_with_a_receipt_naming_the_url(self, tmp_path, fail_url):
        store = Store(tmp_path, BASE)
        rc = run(store, FakeFinviz(BASE, fail_url=fail_url))

        assert rc == ftr.EXIT_FETCH_PARSE == 4
        store.assert_tree_unchanged()
        store.assert_no_history()

        rec = store.only_receipt()
        assert rec["promoted"] is False
        assert rec["reason"] == "fetch_or_parse_failure"
        assert "403" in rec["error"]
        failed = [f for f in rec["fetches"] if not f["ok"]]
        assert [f["url"] for f in failed] == [fail_url]
        assert rec["prev_tree_sha256"] == ftr._tree_hash(BASE)

    def test_unparseable_chunk_refuses(self, tmp_path):
        store = Store(tmp_path, BASE)
        rc = run(store, FakeFinviz(chunk_body='{name:"Root",children:[function(){}]}'))
        assert rc == ftr.EXIT_FETCH_PARSE
        store.assert_tree_unchanged()
        assert store.only_receipt()["reason"] == "fetch_or_parse_failure"

    def test_ambiguous_map_page_refuses(self, tmp_path):
        """Two candidate map.v1 scripts means the page shape changed — guessing
        which one is current is exactly how a stale asset becomes 'the source'."""
        store = Store(tmp_path, BASE)
        page = ('<script src="/assets/dist/map.v1.aaaaaaaa.js"></script>'
                '<script src="/assets/dist/map.v1.bbbbbbbb.js"></script>'
                f'<script src="/assets/dist/runtime.v1.{RUNTIME_HASH}.js"></script>')
        rc = run(store, FakeFinviz(BASE, map_page=page))
        assert rc == ftr.EXIT_FETCH_PARSE
        assert "ambiguous" in store.only_receipt()["error"]
        store.assert_tree_unchanged()

    def test_zero_subtheme_theme_refuses_before_promotion(self, tmp_path):
        store = Store(tmp_path, BASE)
        broken = json.loads(json.dumps(BASE))
        broken[3]["subsectors"] = []
        rc = run(store, FakeFinviz(broken))
        assert rc == ftr.EXIT_FETCH_PARSE
        assert "ZERO subthemes" in store.only_receipt()["error"]
        store.assert_tree_unchanged()

    def test_empty_member_csv_refuses_before_promotion(self, tmp_path):
        store = Store(tmp_path, BASE)
        broken = json.loads(json.dumps(BASE))
        broken[2]["subsectors"][1]["members"] = []
        rc = run(store, FakeFinviz(broken))
        assert rc == ftr.EXIT_FETCH_PARSE
        assert "EMPTY member CSV" in store.only_receipt()["error"]
        store.assert_tree_unchanged()

    def test_history_append_failure_rolls_the_tree_back(self, tmp_path, monkeypatch):
        """Byte-identity must survive a failure at ANY step, not just an early one."""
        store = Store(tmp_path, BASE)
        monkeypatch.setattr(ftr, "append_tree_history",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        rc = run(store, FakeFinviz(_churn_2pct(BASE)))
        assert rc == ftr.EXIT_FETCH_PARSE
        store.assert_tree_unchanged()
        rec = store.only_receipt()
        assert rec["promoted"] is False and rec["reason"] == "promotion_failed"


# ------------------------------------------------------------------ #
# dry run + bootstrap
# ------------------------------------------------------------------ #

class TestDryRun:
    def test_clean_dry_run_reports_without_mutating(self, tmp_path):
        store = Store(tmp_path, BASE)
        rc = run(store, FakeFinviz(_churn_2pct(BASE)), dry_run=True)
        assert rc == ftr.EXIT_PROMOTED
        store.assert_tree_unchanged()
        store.assert_no_history()
        rec = store.only_receipt()
        assert rec["promoted"] is False
        assert rec["reason"] == "dry_run" and rec["mode"] == "dry_run"
        assert rec["refusal_reasons"] == []
        assert rec["counts"]["themes"] == 40

    def test_dry_run_that_would_refuse_exits_refused(self, tmp_path):
        store = Store(tmp_path, BASE)
        rc = run(store, FakeFinviz(BASE[:20]), dry_run=True)
        assert rc == ftr.EXIT_REFUSED
        assert store.only_receipt()["reason"] == "dry_run"
        assert store.only_receipt()["refusal_reasons"]

    def test_dry_run_files_no_probation_proposal(self, tmp_path):
        """`never mutates` includes the probation queue."""
        store = Store(tmp_path, BASE)
        rc = run(store, FakeFinviz(_rename_key_j90(BASE)), dry_run=True)
        assert rc == ftr.EXIT_REFUSED
        assert store.proposals() == []
        assert store.only_receipt()["identity_report"]["renames"]


class TestBootstrap:
    def test_first_materialisation_with_no_prior_tree_promotes(self, tmp_path):
        store = Store(tmp_path, None)
        rc = run(store, FakeFinviz(BASE))
        assert rc == ftr.EXIT_PROMOTED
        assert json.loads(store.paths.tree.read_text()) == BASE
        assert len(store.history_lines()) == 1
        assert store.only_receipt()["prev_tree_sha256"] is None


# ------------------------------------------------------------------ #
# the nightly key-drift tripwire
# ------------------------------------------------------------------ #

class TestKeyDriftTripwire:
    def test_matching_key_sets_are_silent(self, capsys):
        assert ftr.key_drift(["a", "b"], ["b", "a"]) is None
        assert ftr.emit_key_drift_warning(None) is False
        assert capsys.readouterr().out == ""

    def test_symmetric_difference_is_reported_both_ways(self):
        d = ftr.key_drift(["a", "b", "c"], ["b", "c", "x", "y"])
        assert d["tree_only"] == ["a"] and d["perf_only"] == ["x", "y"]
        assert d["tree_key_count"] == 3 and d["perf_key_count"] == 4

    def test_annotation_starts_the_line(self, capsys):
        """GitHub only parses a workflow command when `::` OPENS the line — an
        annotation routed through a prefixing logger is silently dropped."""
        emitted = ftr.emit_key_drift_warning(ftr.key_drift(["a", "b"], ["b", "z"]))
        out = capsys.readouterr().out
        assert emitted is True
        lines = out.splitlines()
        assert len(lines) == 1, "an annotation must be ONE line"
        assert lines[0].startswith("::warning title=finviz-tree-drift::")
        assert "tree-only: a" in lines[0] and "perf-only: z" in lines[0]

    def test_long_key_lists_are_truncated_to_five_per_side(self, capsys):
        tree_keys = [f"t{i}" for i in range(9)]
        ftr.emit_key_drift_warning(ftr.key_drift(tree_keys, ["p1", "p2"]))
        line = capsys.readouterr().out.strip()
        assert "t0, t1, t2, t3, t4 (+4 more)" in line
        assert "t5" not in line

    def test_emitter_uses_a_bare_flushed_print(self):
        """Pins the two properties the annotation dies without: a bare print (not
        a logger) and flush=True (stdout is block-buffered when piped in CI)."""
        src = inspect.getsource(ftr.emit_key_drift_warning)
        # Strip the docstring first — it QUOTES the broken `log.warning("::…")`
        # form to explain why it is banned, and a naive scan would match that.
        body = src.split('"""')[-1]
        assert re.search(r"^\s*print\(", body, re.M)
        assert "flush=True" in body
        assert not re.search(r"\b(log|logger|logging)\.\w+\(", body)

    def test_perf_path_emits_the_warning_end_to_end(self, tmp_path, monkeypatch, capsys):
        """The tripwire must fire from the NIGHTLY path, not just in isolation."""
        tree = make_tree(n_themes=2, n_subs=2, n_members=2)
        monkeypatch.setattr(ftr, "TREE_PATH", tmp_path / "themes_tree.json")
        monkeypatch.setattr(ftr, "PERF_PATH", tmp_path / "perf_snapshot.json")
        monkeypatch.setattr(ftr, "SUBSECTOR_PERF_HISTORY_PATH", tmp_path / "sub.jsonl")
        monkeypatch.setattr(ftr, "TREE_HISTORY_PATH", tmp_path / "tree.jsonl")
        ftr.TREE_PATH.write_bytes(ftr._tree_json_bytes(tree))

        # map_perf answers with ONE stale key and ONE key the tree does not carry.
        monkeypatch.setattr(ftr, "fetch_subsector_perf",
                            lambda: {"t00s0": {"1D": 1.0}, "t00s1": {"1D": 0.5},
                                     "t01s0": {"1D": -1.0}, "brandnew": {"1D": 2.0}})
        monkeypatch.setattr(ftr, "fetch_member_perf", lambda members: {})
        monkeypatch.setattr(sys, "argv", ["fetch_finviz_themes.py"])

        ftr.main()

        out = capsys.readouterr().out
        ann = [ln for ln in out.splitlines() if ln.startswith("::warning")]
        assert len(ann) == 1
        assert "tree-only: t01s1" in ann[0] and "perf-only: brandnew" in ann[0]
        # ...and the perf contract is otherwise untouched.
        snap = json.loads(ftr.PERF_PATH.read_text())
        assert snap["source"] == "finviz-themes" and snap["subsector_perf"]["brandnew"] == {"1D": 2.0}
        assert len(ftr.SUBSECTOR_PERF_HISTORY_PATH.read_text().strip().splitlines()) == 1

    def test_perf_path_is_silent_when_keys_agree(self, tmp_path, monkeypatch, capsys):
        tree = make_tree(n_themes=1, n_subs=2, n_members=2)
        monkeypatch.setattr(ftr, "TREE_PATH", tmp_path / "themes_tree.json")
        monkeypatch.setattr(ftr, "PERF_PATH", tmp_path / "perf_snapshot.json")
        monkeypatch.setattr(ftr, "SUBSECTOR_PERF_HISTORY_PATH", tmp_path / "sub.jsonl")
        monkeypatch.setattr(ftr, "TREE_HISTORY_PATH", tmp_path / "tree.jsonl")
        ftr.TREE_PATH.write_bytes(ftr._tree_json_bytes(tree))
        monkeypatch.setattr(ftr, "fetch_subsector_perf",
                            lambda: {"t00s0": {"1D": 1.0}, "t00s1": {"1D": 0.5}})
        monkeypatch.setattr(ftr, "fetch_member_perf", lambda members: {})
        monkeypatch.setattr(sys, "argv", ["fetch_finviz_themes.py"])
        ftr.main()
        assert "::warning" not in capsys.readouterr().out


# ------------------------------------------------------------------ #
# CLI wiring — --refresh-tree is STRUCTURE ONLY
# ------------------------------------------------------------------ #

class TestCliWiring:
    def test_refresh_tree_never_runs_the_perf_fetch(self, monkeypatch):
        """The nightly never passes the flag, and an operator's structural
        investigation must never silently rewrite tonight's board."""
        seen: list[dict] = []
        monkeypatch.setattr(ftr, "refresh_tree", lambda **kw: (seen.append(kw), 0)[1])

        def boom(*a, **k):
            raise AssertionError("the perf path must not run under --refresh-tree")

        monkeypatch.setattr(ftr, "fetch_subsector_perf", boom)
        monkeypatch.setattr(ftr, "fetch_member_perf", boom)
        monkeypatch.setattr(sys, "argv", ["fetch_finviz_themes.py", "--refresh-tree"])

        with pytest.raises(SystemExit) as e:
            ftr.main()
        assert e.value.code == 0
        assert seen == [{"allow_shrink": False, "dry_run": False}]

    def test_flags_are_forwarded(self, monkeypatch):
        seen: list[dict] = []
        monkeypatch.setattr(ftr, "refresh_tree", lambda **kw: (seen.append(kw), 3)[1])
        monkeypatch.setattr(sys, "argv",
                            ["fetch_finviz_themes.py", "--refresh-tree", "--allow-shrink", "--dry-run"])
        with pytest.raises(SystemExit) as e:
            ftr.main()
        assert e.value.code == 3
        assert seen == [{"allow_shrink": True, "dry_run": True}]

    def test_dry_run_without_refresh_tree_is_refused_not_ignored(self, monkeypatch):
        """Silently accepting --dry-run on the perf path would be a false promise:
        the perf path writes perf_snapshot.json unconditionally."""
        monkeypatch.setattr(sys, "argv", ["fetch_finviz_themes.py", "--dry-run"])
        with pytest.raises(SystemExit) as e:
            ftr.main()
        assert isinstance(e.value.code, str) and "--refresh-tree" in e.value.code
