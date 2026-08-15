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
     + key renamed, one member swapped -> refusal + key_rename probation proposal,
                                         and no flag overrides it
  G  mis-nesting (~7x explosion)      -> GROWTH refusal, bytes unchanged. The direction
                                         that matters most in an append-only store: a
                                         false edge is permanent, because nothing later
                                         closes what the source never had. Every SHRINK
                                         wall is silent on this fixture — the test
                                         asserts that, so it cannot pass by accident.
  T  departed x arrived ticker pairs  -> a same-signature pair refuses as a symbol
                                         change; SNDK/PSTG (the receipted 08-14 pair)
                                         must NOT flag.

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
        tmp_path.mkdir(parents=True, exist_ok=True)
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


def copy(tree: list[dict]) -> list[dict]:
    return json.loads(json.dumps(tree))


def grid(n_subs: int = 100, n_members: int = 100, per_ticker: int = 1) -> list[dict]:
    """One theme, ``n_subs`` subthemes — a flat grid for boundary arithmetic.

    ``per_ticker`` places each ticker in that many consecutive subthemes, which
    is what lets the unique-ticker wall be isolated from the membership wall
    (with per_ticker=1 the two counts move together and no fixture can separate
    them).
    """
    pool = [f"G{i:05d}" for i in range((n_subs * n_members) // per_ticker)]
    subs = []
    for si in range(n_subs):
        members = [pool[((si * n_members) // per_ticker + mi) % len(pool)]
                   for mi in range(n_members)]
        subs.append({"key": f"g{si:03d}", "name": f"G{si}", "description": "d",
                     "members": sorted(set(members))})
    return [{"theme": "G", "key": "G", "subsectors": subs}]


def remove_exact(tree: list[dict], total: int, n_subs: int) -> list[dict]:
    """Remove exactly ``total`` memberships spread over ``n_subs`` subthemes."""
    out = copy(tree)
    subs = [s for t in out for s in t["subsectors"]][:n_subs]
    per, rem = divmod(total, n_subs)
    for i, s in enumerate(subs):
        s["members"] = s["members"][per + (1 if i < rem else 0):]
    return out


def add_exact(tree: list[dict], total: int, n_subs: int, *, novel: bool) -> list[dict]:
    """Add exactly ``total`` memberships over ``n_subs`` subthemes.

    ``novel=False`` reuses tickers that already exist elsewhere in the tree, so
    the unique-ticker count does not move and the total-membership wall is under
    test alone.
    """
    out = copy(tree)
    all_subs = [s for t in out for s in t["subsectors"]]
    pool = sorted({m for s in all_subs for m in s["members"]})
    per, rem = divmod(total, n_subs)
    for i, s in enumerate(all_subs[:n_subs]):
        k = per + (1 if i < rem else 0)
        if novel:
            s["members"] = s["members"] + [f"NEW{i:04d}X{j:05d}" for j in range(k)]
        else:
            here = set(s["members"])
            s["members"] = s["members"] + [m for m in pool if m not in here][:k]
    return out


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

    # --- deletion walls: zero tolerance, keyed on DELETION not on net count --- #

    @pytest.mark.parametrize("kept, refuses", [(40, False), (39, True)])
    def test_any_theme_deletion_refuses(self, kept, refuses):
        d = ftr.diff_trees(make_tree(40, 2, 2), make_tree(kept, 2, 2))
        got = [r for r in ftr.evaluate_interlocks(d) if r.startswith("theme_deletion")]
        assert bool(got) is refuses

    def test_a_deletion_plus_an_addition_still_refuses(self):
        """The wall is keyed on DELETION, not on the net count — a delete paired
        with an unrelated add nets to zero and walks through a count-based rule."""
        prev = make_tree(4, 2, 3)
        new = copy(prev)
        new[0]["theme"] = new[0]["key"] = "Something Else"
        for i, s in enumerate(new[0]["subsectors"]):
            s["key"] = f"brandnew{i}"
            s["members"] = [f"UNRELATED{i}{j}" for j in range(3)]
        d = ftr.diff_trees(prev, new)
        assert d["themes"]["prev"] == d["themes"]["new"] == 4  # net zero
        got = ftr.evaluate_interlocks(d)
        assert any(r.startswith("theme_deletion") for r in got)
        assert any(r.startswith("subtheme_deletion") for r in got)

    @pytest.mark.parametrize("kept, refuses", [(100, False), (99, True)])
    def test_any_subtheme_deletion_refuses(self, kept, refuses):
        prev = grid(n_subs=100, n_members=4)
        new = copy(prev)
        new[0]["subsectors"] = new[0]["subsectors"][:kept]
        got = [r for r in ftr.evaluate_interlocks(ftr.diff_trees(prev, new))
               if r.startswith("subtheme_deletion")]
        assert bool(got) is refuses

    # --- membership removal wall: boundary at the wall, both sides ----------- #

    @pytest.mark.parametrize("removed, frac, refuses", [
        (990, "9.9%", False),   # just under
        (1000, "10.0%", False),  # exactly AT the wall — the rule is `>10%`
        (1010, "10.1%", True),  # just over
    ])
    def test_membership_removal_wall_boundary(self, removed, frac, refuses):
        prev = grid(n_subs=100, n_members=100)          # 10,000 memberships
        new = remove_exact(prev, removed, n_subs=30)    # 30% of subthemes touched
        d = ftr.diff_trees(prev, new)
        got = [r for r in ftr.evaluate_interlocks(d) if r.startswith("membership_shrink")]
        assert bool(got) is refuses, f"{frac} removal"
        # nothing else may fire — this fixture isolates ONE wall
        assert [r.split(":")[0] for r in ftr.evaluate_interlocks(d)] in ([], ["membership_shrink"])

    def test_last_member_of_every_subtheme_truncation_is_caught(self):
        """The failure the 10% wall was re-derived to catch: a read that loses
        exactly one ticker per row. 268 of 2,339 = 11.5% — under the old 25%
        wall it promoted silently, and every row still looked plausible."""
        prev = make_tree(n_themes=40, n_subs=7, n_members=9)   # 2,520 memberships
        new = copy(prev)
        for t in new:
            for s in t["subsectors"]:
                s["members"] = s["members"][:-1]              # 280 removed = 11.1%
        d = ftr.diff_trees(prev, new)
        st = ftr.shrink_stats(d)
        assert st["membership_removal_frac"] > ftr.MAX_MEMBERSHIP_REMOVAL_FRAC
        assert any(r.startswith("membership_shrink") for r in ftr.evaluate_interlocks(d))

    # --- concentrated + distributed loss walls ------------------------------ #

    @pytest.mark.parametrize("kept, refuses", [(50, False), (49, True)])
    def test_single_subtheme_collapse_wall(self, kept, refuses):
        """A total-membership wall is blind to a concentrated failure: one
        subtheme of 268 emptied is 0.4% of the tree."""
        prev = grid(n_subs=100, n_members=100)
        new = copy(prev)
        new[0]["subsectors"][0]["members"] = new[0]["subsectors"][0]["members"][:kept]
        got = [r for r in ftr.evaluate_interlocks(ftr.diff_trees(prev, new))
               if r.startswith("subtheme_member_collapse")]
        assert bool(got) is refuses

    @pytest.mark.parametrize("touched, refuses", [(30, False), (31, True)])
    def test_distributed_loss_wall_boundary(self, touched, refuses):
        """The distributed-truncation fingerprint: small everywhere, so it hides
        from both the total wall and the per-subtheme wall. Genuine 2026-08-14
        churn touched 12% of subthemes; the wall sits at 30%."""
        prev = grid(n_subs=100, n_members=100)
        new = remove_exact(prev, total=touched, n_subs=touched)  # 1 member each
        d = ftr.diff_trees(prev, new)
        got = [r for r in ftr.evaluate_interlocks(d) if r.startswith("distributed_membership_loss")]
        assert bool(got) is refuses
        assert ftr.shrink_stats(d)["membership_removal_frac"] < 0.01, \
            "the totals must stay tiny — that is what makes this the hiding failure"

    # --- growth walls (§9.1): the catastrophic direction -------------------- #

    @pytest.mark.parametrize("added, refuses", [(990, False), (1000, False), (1010, True)])
    def test_membership_growth_wall_boundary(self, added, refuses):
        prev = grid(n_subs=100, n_members=100)
        new = add_exact(prev, added, n_subs=30, novel=False)  # reuse existing tickers
        d = ftr.diff_trees(prev, new)
        assert d["tickers"]["added"] == 0, "fixture must isolate the membership wall"
        got = [r for r in ftr.evaluate_interlocks(d) if r.startswith("membership_growth")]
        assert bool(got) is refuses

    @pytest.mark.parametrize("added, refuses", [(100, False), (120, True)])
    def test_unique_ticker_growth_wall(self, added, refuses):
        """Isolated from the membership wall by a fixture where each ticker sits
        in two subthemes, so 1,000 tickers carry 2,000 memberships."""
        prev = grid(n_subs=20, n_members=100, per_ticker=2)
        new = add_exact(prev, added, n_subs=20, novel=True)
        d = ftr.diff_trees(prev, new)
        assert d["tickers"]["prev"] < d["memberships"]["prev"]
        assert ftr.growth_stats(d)["membership_growth_frac"] <= ftr.MAX_MEMBERSHIP_GROWTH_FRAC
        got = [r for r in ftr.evaluate_interlocks(d) if r.startswith("ticker_growth")]
        assert bool(got) is refuses

    @pytest.mark.parametrize("prior, new_count, refuses", [
        (100, 200, False),   # exactly 2x — at the wall, `>` lets it pass
        (100, 201, True),    # over 2x
        (3, 18, False),      # small row: cap is prior+15 = 18, not 2x = 6
        (3, 19, True),
    ])
    def test_per_subtheme_growth_cap(self, prior, new_count, refuses):
        assert ftr._growth_cap(prior) == max(2 * prior, prior + 15)
        prev = grid(n_subs=100, n_members=prior)
        new = copy(prev)
        s = new[0]["subsectors"][0]
        s["members"] = s["members"] + [f"EXTRA{i:05d}" for i in range(new_count - prior)]
        got = [r for r in ftr.evaluate_interlocks(ftr.diff_trees(prev, new))
               if r.startswith("subtheme_growth_cap")]
        assert bool(got) is refuses

    # --- flag semantics ----------------------------------------------------- #

    def test_allow_shrink_clears_shrink_walls_only(self):
        d = ftr.diff_trees(make_tree(40, 7, 20), make_tree(10, 7, 20))
        assert len(ftr.evaluate_interlocks(d)) >= 2
        assert ftr.evaluate_interlocks(d, allow_shrink=True) == []

    def test_allow_shrink_does_not_clear_a_growth_wall(self):
        """One flag clearing both families would let the acknowledged half carry
        the unacknowledged half through."""
        prev = grid(n_subs=100, n_members=100)
        new = add_exact(remove_exact(prev, 20, 5), 3000, n_subs=30, novel=False)
        d = ftr.diff_trees(prev, new)
        assert any(r.startswith("membership_growth") for r in ftr.evaluate_interlocks(d))
        assert ftr.evaluate_interlocks(d, allow_shrink=True) != []
        assert ftr.evaluate_interlocks(d, allow_growth=True, allow_shrink=True) == []

    def test_bootstrap_against_no_prior_tree_refuses_nothing(self):
        d = ftr.diff_trees([], make_tree(3, 2, 2))
        assert ftr.evaluate_interlocks(d) == []

    def test_stats_carry_their_thresholds(self):
        """A measurement without the wall it was judged against cannot be
        re-adjudicated later if the wall moves."""
        d = ftr.diff_trees(make_tree(40, 7, 20), make_tree(40, 7, 20))
        st, gr = ftr.shrink_stats(d), ftr.growth_stats(d)
        assert st["max_membership_removal_frac"] == ftr.MAX_MEMBERSHIP_REMOVAL_FRAC == 0.10
        assert st["max_theme_deletions"] == ftr.MAX_THEME_DELETIONS == 0
        assert st["max_subtheme_deletions"] == ftr.MAX_SUBTHEME_DELETIONS == 0
        assert st["max_subtheme_member_loss_frac"] == ftr.MAX_SUBTHEME_MEMBER_LOSS_FRAC == 0.50
        assert st["max_subthemes_losing_members_frac"] == \
            ftr.MAX_SUBTHEMES_LOSING_MEMBERS_FRAC == 0.30
        assert gr["max_membership_growth_frac"] == ftr.MAX_MEMBERSHIP_GROWTH_FRAC == 0.10
        assert gr["max_ticker_growth_frac"] == ftr.MAX_TICKER_GROWTH_FRAC == 0.10
        assert gr["subtheme_growth_multiplier"] == ftr.SUBTHEME_GROWTH_MULTIPLIER == 2.0
        assert gr["subtheme_growth_absolute"] == ftr.SUBTHEME_GROWTH_ABSOLUTE == 15


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
        assert any(r.startswith("theme_deletion") for r in rec["refusal_reasons"])
        assert any(r.startswith("subtheme_deletion") for r in rec["refusal_reasons"])
        assert any(r.startswith("membership_shrink") for r in rec["refusal_reasons"])
        assert rec["counts"]["themes"] == 20
        assert rec["shrink"]["themes_deleted"] == 20
        assert rec["shrink"]["subthemes_deleted"] == 140
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
    """Remove 112 of 5,600 memberships = exactly 2.0%, shaped like real churn.

    Two members from each of 56 subthemes: 20% of subthemes touched, against the
    2026-08-14 vintage's 12%. Spreading the same 112 removals one-per-subtheme
    would touch 40% and trip the distributed-loss wall — which is the wall doing
    its job, not a fixture bug, so the fixture models the real shape instead.
    """
    out = copy(tree)
    subs = [s for t in out for s in t["subsectors"]]
    for s in subs[:56]:
        s["members"] = s["members"][:-2]
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
        sh = rec["shrink"]
        assert sh["prior_memberships"] == 5600
        assert sh["membership_removals"] == 2520
        assert sh["membership_removal_frac"] == pytest.approx(0.45)
        assert sh["max_membership_removal_frac"] == 0.10
        # structure intact — this is a MEMBERSHIP catastrophe only, and the receipt
        # must say so rather than blaming the structure walls.
        assert sh["themes_deleted"] == 0 and sh["subthemes_deleted"] == 0
        # Two walls see it, and both are the right ones: the total, and the
        # co-occurrence fingerprint (every subtheme lost members at once).
        assert sorted(r.split(":")[0] for r in rec["refusal_reasons"]) == [
            "distributed_membership_loss", "membership_shrink"]
        assert sh["subthemes_losing_members"] == 280
        assert sh["subthemes_losing_members_frac"] == pytest.approx(1.0)

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


def _rename_key_one_swap(tree: list[dict]) -> list[dict]:
    """Old key out, new key in, ONE member swapped — the review's negative control.

    This is the case J>=0.80 could not see: at n members a rename plus one swap
    scores Jaccard (n-1)/(n+1), i.e. 0.90 at n=20 but under 0.80 for every n<=8 —
    and n<=8 is 51.5% of the live tree. Containment of the smaller set reads
    (n-1)/n = 0.95 here and 0.857 at n=7, so the wall sees it at every size.
    """
    out = copy(tree)
    s = out[0]["subsectors"][0]
    s["key"] = "t00s0v2"
    s["members"] = s["members"][:-1] + ["SWAPPED1"]
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
        renamed = _rename_key_one_swap(BASE)

        rc = run(store, FakeFinviz(renamed))

        assert rc == ftr.EXIT_REFUSED
        store.assert_tree_unchanged()
        store.assert_no_history()

        rec = store.only_receipt()
        assert rec["promoted"] is False
        assert any(r.startswith("suspected_key_rename") for r in rec["refusal_reasons"])
        ident = rec["identity_report"]
        assert ident["rename_containment_min"] == ftr.RENAME_CONTAINMENT_MIN == 0.60
        assert len(ident["renames"]) == 1
        r = ident["renames"][0]
        assert (r["old_key"], r["new_key"]) == ("t00s0", "t00s0v2")
        assert r["containment"] == pytest.approx(19 / 20)
        assert (r["old_member_count"], r["new_member_count"], r["shared_member_count"]) == (20, 20, 19)

        rows = store.proposals()
        assert len(rows) == 1
        p = rows[0]
        assert p["kind"] == "key_rename"
        assert p["proposed_by"] == "refresh_identity"
        assert p["status"] == "proposed" and p["ratified_by"] is None
        assert p["created"] == "2026-08-14T23:30:00Z"
        assert p["proposal_id"] in ident["proposal_ids"]
        assert p["subject"] == {"source_family": "finviz_themes",
                                "old_key": "t00s0", "new_key": "t00s0v2"}
        assert p["evidence"]["containment"] == pytest.approx(19 / 20)
        assert p["evidence"]["prev_tree_sha256"] == ftr._tree_hash(BASE)
        assert p["evidence_refs"] and p["evidence_refs"][0].endswith(".json")

    @pytest.mark.parametrize("n", [2, 3, 5, 7, 8, 12, 20])
    def test_rename_plus_one_swap_flags_at_every_live_size(self, n):
        """The review's negative control. At n=7 this scores Jaccard 0.75 — the
        old J>=0.80 wall missed it, and n<=8 is 51.5% of the live tree."""
        prev = [{"theme": "T", "key": "T", "subsectors": [
            {"key": "old", "name": "N", "description": "d",
             "members": [f"M{i:02d}" for i in range(n)]}]}]
        new = copy(prev)
        new[0]["subsectors"][0]["key"] = "new"
        new[0]["subsectors"][0]["members"] = [f"M{i:02d}" for i in range(n - 1)] + ["SWAP"]
        got = ftr.detect_key_renames(prev, new)
        assert len(got) == 1, f"a rename+1-swap at n={n} must flag"
        if n >= 4:  # J = (n-1)/(n+1)
            assert got[0]["jaccard"] < 0.80 or n >= 9, \
                "n<=8 is exactly the band the old Jaccard wall could not see"

    def test_no_flag_overrides_a_key_rename(self, tmp_path):
        """No override BY DESIGN: auto-promoting fakes an identity break,
        auto-merging rewrites identity. Both must stay impossible.

        Under §9.2 a key rename is ALSO a subtheme deletion, so --allow-shrink
        clears that wall — and the identity refusal must be what survives alone.
        """
        store = Store(tmp_path, BASE)
        rc = run(store, FakeFinviz(_rename_key_one_swap(BASE)),
                 allow_shrink=True, allow_growth=True)
        assert rc == ftr.EXIT_REFUSED
        store.assert_tree_unchanged()
        assert [r.split(":")[0] for r in store.only_receipt()["refusal_reasons"]] == \
            ["suspected_key_rename"]

    def test_rerun_does_not_duplicate_the_proposal(self, tmp_path):
        """An operator investigating a refusal runs it more than once; a queue
        that grows a row per attempt is unreadable."""
        store = Store(tmp_path, BASE)
        renamed = _rename_key_one_swap(BASE)
        run(store, FakeFinviz(renamed))
        run(store, FakeFinviz(renamed), now=NOW + timedelta(minutes=7))
        assert len(store.proposals()) == 1
        assert len(store.receipts()) == 2

    def test_below_threshold_overlap_is_not_a_rename(self):
        """A genuinely new subtheme sharing half its members must NOT be
        laundered into a rename — containment 0.5 is under the 0.6 wall, and at
        n=10 the small-n slack does not apply."""
        prev = make_tree(n_themes=1, n_subs=2, n_members=10)
        new = copy(prev)
        new[0]["subsectors"][0]["key"] = "brandnew"
        new[0]["subsectors"][0]["members"] = (
            prev[0]["subsectors"][0]["members"][:5] + [f"NEW{i}" for i in range(5)])
        assert ftr.detect_key_renames(prev, new) == []

    def test_disjoint_rows_are_never_a_rename(self):
        prev = make_tree(n_themes=1, n_subs=2, n_members=10)
        new = copy(prev)
        new[0]["subsectors"][0]["key"] = "brandnew"
        new[0]["subsectors"][0]["members"] = [f"NEW{i}" for i in range(10)]
        assert ftr.detect_key_renames(prev, new) == []

    def test_rename_detection_is_pure_and_deterministic(self):
        renames = ftr.detect_key_renames(BASE, _rename_key_one_swap(BASE))
        assert [(r["old_key"], r["new_key"]) for r in renames] == [("t00s0", "t00s0v2")]
        assert ftr.detect_key_renames(BASE, BASE) == []


# ------------------------------------------------------------------ #
# ticker continuity (§9.7) — a symbol change is not a departure + arrival
# ------------------------------------------------------------------ #

def _sndk_pstg_tree(*, arrival: bool) -> list[dict]:
    """The receipted 2026-08-14 shape: PSTG in 2 subthemes, SNDK in 9.

    Before: PSTG holds 2 rows. After: PSTG is gone and SNDK holds 9 — the 2 PSTG
    had, plus 7 more. PSTG's set is entirely INSIDE SNDK's, so containment reads
    1.0; symmetric difference reads 7. They are different issuers and must not be
    flagged, which is exactly why the rule is symmetric difference.
    """
    subs = []
    for i in range(9):
        members = [f"FILLER{i}{j}" for j in range(5)]
        if arrival:
            members.append("SNDK")
        elif i < 2:
            members.append("PSTG")
        subs.append({"key": f"s{i}", "name": f"S{i}", "description": "d", "members": members})
    return [{"theme": "Storage", "key": "Storage", "subsectors": subs}]


class TestTickerContinuity:
    def test_sndk_pstg_slot_substitution_is_not_flagged(self):
        """The pinned NEGATIVE fixture, straight from the 2026-08-14 reconciliation."""
        prev, new = _sndk_pstg_tree(arrival=False), _sndk_pstg_tree(arrival=True)
        got = ftr.detect_ticker_continuity(prev, new)
        assert got == [], "PSTG⊂SNDK is a slot substitution of two different issuers"
        # ...and the reason it is not flagged is the metric, not luck:
        p_sets = ftr._ticker_subtheme_sets(prev)
        n_sets = ftr._ticker_subtheme_sets(new)
        assert len(p_sets["PSTG"] ^ n_sets["SNDK"]) == 7
        assert len(p_sets["PSTG"] & n_sets["SNDK"]) / len(p_sets["PSTG"]) == 1.0, \
            "containment says 1.0 — which is precisely why containment is the wrong rule here"

    def test_same_signature_pair_is_flagged(self):
        """The POSITIVE fixture: one symbol replaced by another in the same rows."""
        prev = make_tree(n_themes=2, n_subs=3, n_members=5)
        new = copy(prev)
        old_sym = prev[0]["subsectors"][0]["members"][0]
        for t in new:
            for s in t["subsectors"]:
                s["members"] = ["NEWSYM" if m == old_sym else m for m in s["members"]]
        got = ftr.detect_ticker_continuity(prev, new)
        assert len(got) == 1
        assert (got[0]["departed_ticker"], got[0]["arrived_ticker"]) == (old_sym, "NEWSYM")
        assert got[0]["symmetric_difference"] == 0

    def test_one_key_of_slack_is_allowed(self):
        """A real symbol change can coincide with ordinary churn in one row."""
        prev = make_tree(n_themes=1, n_subs=4, n_members=5)
        new = copy(prev)
        old = prev[0]["subsectors"][0]["members"][0]
        for s in new[0]["subsectors"][:3]:
            s["members"] = ["NEWSYM" if m == old else m for m in s["members"]]
        # the 4th row gains it too — signature differs by exactly one key
        new[0]["subsectors"][3]["members"] = new[0]["subsectors"][3]["members"] + ["NEWSYM"]
        got = ftr.detect_ticker_continuity(prev, new)
        assert len(got) == 1 and got[0]["symmetric_difference"] == 1

    def test_two_keys_of_difference_is_not_flagged(self):
        prev = make_tree(n_themes=1, n_subs=5, n_members=5)
        new = copy(prev)
        old = prev[0]["subsectors"][0]["members"][0]
        for s in new[0]["subsectors"][:1]:
            s["members"] = ["NEWSYM" if m == old else m for m in s["members"]]
        for s in new[0]["subsectors"][1:3]:
            s["members"] = s["members"] + ["NEWSYM"]
        assert ftr.detect_ticker_continuity(prev, new) == []

    def test_refuses_and_files_an_identity_continuity_proposal(self, tmp_path):
        prev = make_tree(n_themes=6, n_subs=4, n_members=8)
        store = Store(tmp_path, prev)
        new = copy(prev)
        old = prev[0]["subsectors"][0]["members"][0]
        for t in new:
            for s in t["subsectors"]:
                s["members"] = ["NEWSYM" if m == old else m for m in s["members"]]

        rc = run(store, FakeFinviz(new))

        assert rc == ftr.EXIT_REFUSED
        store.assert_tree_unchanged()
        store.assert_no_history()

        rec = store.only_receipt()
        assert [r.split(":")[0] for r in rec["refusal_reasons"]] == ["suspected_ticker_rename"]
        assert rec["identity_report"]["ticker_continuity_max_symdiff"] == 1
        assert len(rec["identity_report"]["ticker_continuity"]) == 1

        rows = store.proposals()
        assert len(rows) == 1 and rows[0]["kind"] == "identity_continuity"
        assert rows[0]["proposed_by"] == "refresh_identity" and rows[0]["status"] == "proposed"
        assert rows[0]["subject"] == {"source_family": "finviz_themes",
                                      "departed_ticker": old, "arrived_ticker": "NEWSYM"}
        assert rows[0]["evidence"]["symmetric_difference"] == 0


# ------------------------------------------------------------------ #
# cross-builder contract: the probation rows this collector writes are
# read by the theme-graph layer, which owns their schema
# ------------------------------------------------------------------ #

PROPOSAL_SCHEMA = ftr.ROOT / "contracts" / "theme_graph" / "probation_proposal.v1.schema.json"


def _emitted_proposals(tmp_path: Path) -> list[dict]:
    """Both proposal kinds this module can write, produced by real refusals."""
    rows: list[dict] = []
    s1 = Store(tmp_path / "a", BASE)
    run(s1, FakeFinviz(_rename_key_one_swap(BASE)))
    rows += s1.proposals()

    prev = make_tree(n_themes=6, n_subs=4, n_members=8)
    s2 = Store(tmp_path / "b", prev)
    new = copy(prev)
    old = prev[0]["subsectors"][0]["members"][0]
    for t in new:
        for s in t["subsectors"]:
            s["members"] = ["NEWSYM" if m == old else m for m in s["members"]]
    run(s2, FakeFinviz(new))
    rows += s2.proposals()
    return rows


class TestProbationRowContract:
    """These rows cross a builder boundary. This collector writes them inline (it
    must stay runnable with the graph layer absent or mid-build) and the graph
    layer reads them — so the SCHEMA is the contract, and a drift on either side
    has to fail a test here rather than a nightly."""

    def test_both_kinds_validate_against_the_committed_schema(self, tmp_path):
        jsonschema = pytest.importorskip("jsonschema")
        if not PROPOSAL_SCHEMA.is_file():
            pytest.skip("probation_proposal.v1 schema not present in this tree")
        schema = json.loads(PROPOSAL_SCHEMA.read_text())
        rows = _emitted_proposals(tmp_path)
        assert {r["kind"] for r in rows} == {"key_rename", "identity_continuity"}
        for row in rows:
            jsonschema.validate(row, schema)   # raises on any violation

    def test_proposal_id_matches_the_graph_layers_implementation(self, tmp_path):
        """Two implementations of one hash is the price of the decoupling; this
        is what stops them drifting silently."""
        probation = pytest.importorskip("engine.theme_graph.probation")
        for row in _emitted_proposals(tmp_path):
            assert row["proposal_id"] == probation.proposal_id(row["kind"], row["subject"]), \
                "the inline id and the graph layer's id must agree exactly"

    def test_rows_pass_the_graph_layers_own_validator(self, tmp_path):
        probation = pytest.importorskip("engine.theme_graph.probation")
        for row in _emitted_proposals(tmp_path):
            assert probation.validate(row) == []

    def test_id_is_stable_across_candidate_trees(self, tmp_path):
        """Deterministic on the SUBJECT, never on the candidate tree's hash: an
        operator re-running a refusal after the vendor moved again is looking at
        the same finding, and must not grow the queue a second row."""
        a = ftr._proposal_id("key_rename", {"old_key": "x", "new_key": "y"})
        b = ftr._proposal_id("key_rename", {"new_key": "y", "old_key": "x"})
        assert a == b and re.fullmatch(r"prop:[0-9a-f]{16}", a)
        assert a != ftr._proposal_id("identity_continuity", {"old_key": "x", "new_key": "y"})

    def test_a_proposer_can_never_mint_a_ratified_row(self):
        row = ftr._proposal_row(kind="key_rename", subject={"old_key": "a", "new_key": "b"},
                                evidence={}, evidence_refs=[], created="2026-08-14T00:00:00Z")
        assert row["status"] == "proposed" and row["ratified_by"] is None

    def test_no_flag_overrides_ticker_continuity(self, tmp_path):
        prev = make_tree(n_themes=6, n_subs=4, n_members=8)
        store = Store(tmp_path, prev)
        new = copy(prev)
        old = prev[0]["subsectors"][0]["members"][0]
        for t in new:
            for s in t["subsectors"]:
                s["members"] = ["NEWSYM" if m == old else m for m in s["members"]]
        rc = run(store, FakeFinviz(new), allow_shrink=True, allow_growth=True)
        assert rc == ftr.EXIT_REFUSED
        store.assert_tree_unchanged()

    def test_ordinary_churn_does_not_trip_continuity(self):
        """The 2026-08-14 vintage's real shape: departures and arrivals that are
        unrelated must promote, or the wall makes every refresh manual."""
        assert ftr.detect_ticker_continuity(BASE, _churn_2pct(BASE)) == []


# ------------------------------------------------------------------ #
# G — growth: the catastrophic direction in an append-only store
# ------------------------------------------------------------------ #

def _misnest(tree: list[dict]) -> list[dict]:
    """Smear each theme's full member union onto every one of its subthemes.

    The realistic mis-nesting bug: one level too shallow in the walk. Theme and
    subtheme COUNTS are untouched, NOTHING is removed, no key changes — it passes
    every shrink and structure wall by construction, and multiplies memberships
    ~7x. In an append-only store those false edges are permanent.
    """
    out = copy(tree)
    for t in out:
        union = sorted({m for s in t["subsectors"] for m in s["members"]})
        for s in t["subsectors"]:
            s["members"] = list(union)
    return out


class TestGGrowthExplosion:
    def test_misnesting_refuses_with_bytes_unchanged(self, tmp_path):
        store = Store(tmp_path, BASE)
        smeared = _misnest(BASE)

        rc = run(store, FakeFinviz(smeared))

        assert rc == ftr.EXIT_REFUSED
        store.assert_tree_unchanged()
        store.assert_no_history()

        rec = store.only_receipt()
        assert rec["promoted"] is False
        # counts and structure are IDENTICAL — the fixture's whole point
        assert rec["counts"]["themes"] == 40 and rec["counts"]["subthemes"] == 280
        assert rec["counts"]["unique_tickers"] == 5600
        assert rec["shrink"]["membership_removals"] == 0
        assert rec["counts"]["memberships"] == 39200          # 7x
        assert sorted(r.split(":")[0] for r in rec["refusal_reasons"]) == [
            "membership_growth", "subtheme_growth_cap"]

    def test_every_shrink_wall_is_silent_on_the_misnesting_fixture(self):
        """Without this assertion the test above could pass for the wrong reason.
        The growth family is the ONLY thing standing between a mis-nested read
        and 33,600 permanent false edges."""
        d = ftr.diff_trees(BASE, _misnest(BASE))
        assert ftr._shrink_refusals(d) == []
        assert ftr.evaluate_interlocks(d, allow_growth=True) == []
        assert ftr._growth_refusals(d) != []

    def test_allow_growth_promotes_the_same_explosion(self, tmp_path):
        """The wall is an interlock, not a prohibition."""
        store = Store(tmp_path, BASE)
        smeared = _misnest(BASE)
        rc = run(store, FakeFinviz(smeared), allow_growth=True)
        assert rc == ftr.EXIT_PROMOTED
        assert json.loads(store.paths.tree.read_text()) == smeared
        assert store.only_receipt()["allow_growth"] is True

    def test_growth_receipt_names_the_worst_offender(self, tmp_path):
        store = Store(tmp_path, BASE)
        run(store, FakeFinviz(_misnest(BASE)))
        gr = store.only_receipt()["growth"]
        assert len(gr["subthemes_over_growth_cap"]) == 280
        worst = gr["subthemes_over_growth_cap"][0]
        assert (worst["prev"], worst["new"], worst["cap"]) == (20, 140, 40)
        assert gr["membership_growth"] == 33600
        assert gr["ticker_growth"] == 0


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
        rc = run(store, FakeFinviz(_rename_key_one_swap(BASE)), dry_run=True)
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
# vintage stamping (§9.5) — a structure observation is dated by the
# instant it was READ, never by an NYSE session
# ------------------------------------------------------------------ #

class TestVintageStamp:
    @pytest.mark.parametrize("now, want, why", [
        (datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc), "2026-08-15",
         "Saturday: _asof_stamp would say Friday 08-14, which is a date the "
         "source was never read on"),
        (datetime(2026, 8, 16, 3, 30, tzinfo=timezone.utc), "2026-08-16",
         "Sunday, and early UTC — still the day of the read"),
        (datetime(2026, 9, 7, 22, 30, tzinfo=timezone.utc), "2026-09-07",
         "Labor Day: _asof_stamp falls back to 09-04; a structure read does not"),
    ])
    def test_stamps_the_utc_extraction_date(self, tmp_path, now, want, why):
        store = Store(tmp_path, BASE)
        rc = ftr.refresh_tree(paths=store.paths, fetch=FakeFinviz(_churn_2pct(BASE)).fetch,
                              now_utc=now)
        assert rc == ftr.EXIT_PROMOTED
        assert store.history_lines()[0]["asof"] == want, why
        assert store.only_receipt()["asof"] == want

    def test_diverges_from_the_perf_boards_session_stamp(self):
        """Pins the distinction rather than just the value: the perf lane's stamp
        is deliberately different, and must stay available for that lane."""
        sat = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
        assert ftr._asof_stamp(sat) == "2026-08-14"       # Friday's board
        assert sat.strftime("%Y-%m-%d") == "2026-08-15"   # Saturday's read

    def test_explicit_asof_override_still_wins(self, tmp_path):
        store = Store(tmp_path, BASE)
        run(store, FakeFinviz(_churn_2pct(BASE)))
        assert store.history_lines()[0]["asof"] == "2026-08-14"


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
        monkeypatch.setattr(ftr, "fetch_member_perf",
                            lambda members: {m: {"1D": 0.1} for m in members})
        monkeypatch.setattr(sys, "argv", ["fetch_finviz_themes.py"])

        ftr.main()

        out = capsys.readouterr().out
        ann = [ln for ln in out.splitlines() if ln.startswith("::warning")]
        assert len(ann) == 1
        assert ann[0].startswith("::warning title=finviz-tree-drift::")
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
        monkeypatch.setattr(ftr, "fetch_member_perf",
                            lambda members: {m: {"1D": 0.1} for m in members})
        monkeypatch.setattr(sys, "argv", ["fetch_finviz_themes.py"])
        ftr.main()
        assert "::warning" not in capsys.readouterr().out


# ------------------------------------------------------------------ #
# the nightly member-coverage tripwire (§9.6)
# ------------------------------------------------------------------ #

class TestMemberCoverageTripwire:
    def test_full_coverage_is_silent(self, capsys):
        members = [f"T{i}" for i in range(1000)]
        assert ftr.member_coverage_gap(members, members) is None
        assert ftr.emit_member_coverage_warning(None) is False
        assert capsys.readouterr().out == ""

    @pytest.mark.parametrize("total, missing, warns, why", [
        (1000, 4, False, "4 of 1,000 = 0.4% — under both floors"),
        (1000, 5, True, "the absolute floor is 5, and it binds at live scale"),
        (100, 1, True, "1 of 100 = 1.0% — the fractional floor binds on a small tree"),
        (100, 0, False, "nothing missing"),
        (941, 18, True, "the receipted 2026-08-13 board: 923 priced of 941"),
    ])
    def test_floors(self, total, missing, warns, why):
        members = [f"T{i:04d}" for i in range(total)]
        gap = ftr.member_coverage_gap(members, members[missing:])
        assert (gap is not None) is warns, why
        if gap:
            assert gap["missing_count"] == missing
            assert gap["covered_count"] == total - missing

    def test_annotation_starts_the_line_and_names_the_symbols(self, capsys):
        members = [f"T{i:04d}" for i in range(941)]
        emitted = ftr.emit_member_coverage_warning(
            ftr.member_coverage_gap(members, members[18:]))
        line = capsys.readouterr().out.strip()
        assert emitted is True
        assert len(line.splitlines()) == 1
        assert line.startswith("::warning title=finviz-member-coverage::")
        assert "923/941" in line and "T0000" in line and "(+13 more)" in line

    def test_emitter_uses_a_bare_flushed_print(self):
        body = inspect.getsource(ftr.emit_member_coverage_warning).split('"""')[-1]
        assert re.search(r"^\s*print\(", body, re.M)
        assert "flush=True" in body
        assert not re.search(r"\b(log|logger|logging)\.\w+\(", body)

    def test_perf_path_emits_it_end_to_end(self, tmp_path, monkeypatch, capsys):
        """The 923/941 pattern, driven through the nightly path."""
        tree = make_tree(n_themes=4, n_subs=5, n_members=10)   # 200 members
        monkeypatch.setattr(ftr, "TREE_PATH", tmp_path / "themes_tree.json")
        monkeypatch.setattr(ftr, "PERF_PATH", tmp_path / "perf_snapshot.json")
        monkeypatch.setattr(ftr, "SUBSECTOR_PERF_HISTORY_PATH", tmp_path / "sub.jsonl")
        monkeypatch.setattr(ftr, "TREE_HISTORY_PATH", tmp_path / "tree.jsonl")
        ftr.TREE_PATH.write_bytes(ftr._tree_json_bytes(tree))
        keys = [s["key"] for t in tree for s in t["subsectors"]]
        monkeypatch.setattr(ftr, "fetch_subsector_perf", lambda: {k: {"1D": 0.0} for k in keys})
        # the vendor stops pricing 6 symbols — a delisting cohort
        monkeypatch.setattr(ftr, "fetch_member_perf",
                            lambda members: {m: {"1D": 0.1} for m in sorted(members)[6:]})
        monkeypatch.setattr(sys, "argv", ["fetch_finviz_themes.py"])

        ftr.main()

        ann = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::warning")]
        assert len(ann) == 1, "the key sets agree, so ONLY the coverage wire should fire"
        assert ann[0].startswith("::warning title=finviz-member-coverage::")
        assert "194/200" in ann[0]
        # the board is written regardless — the tripwire is advisory
        assert json.loads(ftr.PERF_PATH.read_text())["source"] == "finviz-themes"


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
        assert seen == [{"allow_shrink": False, "allow_growth": False, "dry_run": False}]

    def test_flags_are_forwarded(self, monkeypatch):
        seen: list[dict] = []
        monkeypatch.setattr(ftr, "refresh_tree", lambda **kw: (seen.append(kw), 3)[1])
        monkeypatch.setattr(sys, "argv",
                            ["fetch_finviz_themes.py", "--refresh-tree", "--allow-shrink",
                             "--allow-growth", "--dry-run"])
        with pytest.raises(SystemExit) as e:
            ftr.main()
        assert e.value.code == 3
        assert seen == [{"allow_shrink": True, "allow_growth": True, "dry_run": True}]

    @pytest.mark.parametrize("flag", ["--dry-run", "--allow-shrink", "--allow-growth"])
    def test_refresh_flags_without_refresh_tree_are_refused_not_ignored(self, monkeypatch, flag):
        """Silently accepting these on the perf path would be a false promise:
        the perf path writes perf_snapshot.json unconditionally."""
        monkeypatch.setattr(sys, "argv", ["fetch_finviz_themes.py", flag])
        with pytest.raises(SystemExit) as e:
            ftr.main()
        assert isinstance(e.value.code, str) and "--refresh-tree" in e.value.code
