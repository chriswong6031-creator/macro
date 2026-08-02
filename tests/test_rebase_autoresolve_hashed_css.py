"""scripts/rebase_autoresolve_hashed_css.sh — replay of the 2026-07-22 incident.

asia-close run 29904079071 committed the day's engine outputs, then every push
retry died on the same CONFLICT (rename/rename): two lanes had renamed the same
content-hashed stylesheet under site/assets/css/ to different hashes, `-X theirs`
cannot settle path-level conflicts, and after 5 identical failures the loop gave
up under a green run — dropping the day's data (hk_regime stuck at 07-21).

These tests build real git repos reproducing that exact stop and assert the
resolver finishes the rebase keeping BOTH sides' files byte-pure
(filename == sha256(content)[:8]), and refuses to touch anything else.

Since PR #4247 externalize_css.py mints a second content-hashed tree,
site/assets/js/<hash>.js (from <script data-externalize> blocks); the resolver
covers it with the same posture: hashed filenames only, never real content.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rebase_autoresolve_hashed_css.sh"

PULL = ["git", "pull", "--rebase", "--autostash", "-X", "theirs", "origin", "main"]


def _env(home: Path) -> dict:
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.com",
        GIT_TERMINAL_PROMPT="0",
    )
    return env


def run(args, cwd, env, check=True):
    r = subprocess.run(args, cwd=str(cwd), env=env, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(
            f"{args} rc={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
    return r


def resolver(cwd, env):
    return run(["bash", str(SCRIPT)], cwd, env, check=False)


def css_body(tag: str) -> str:
    # ~200 identical lines + one distinct tail line: similar enough across lanes
    # that git's rename detection pairs old->new, like real externalized css.
    return "body{margin:0}\n" + ".x{color:#111}\n" * 200 + tag + "\n"


def js_body(tag: str) -> str:
    # Same shape for the js tree; shares no lines with css_body, so rename
    # detection can never pair a stylesheet with a script across kinds.
    return "(function(){\n" + "  var n=0;n+=1;\n" * 200 + tag + "\n})();\n"


def _write_hashed(root: Path, kind: str, body: str) -> str:
    h = hashlib.sha256(body.encode()).hexdigest()[:8]
    p = root / "site" / "assets" / kind / f"{h}.{kind}"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return h


def write_hashed_css(root: Path, css: str) -> str:
    return _write_hashed(root, "css", css)


def write_hashed_js(root: Path, js: str) -> str:
    return _write_hashed(root, "js", js)


def in_rebase(root: Path) -> bool:
    return (root / ".git" / "rebase-merge").is_dir() or (root / ".git" / "rebase-apply").is_dir()


def assert_hash_pure(root: Path):
    for kind in ("css", "js"):
        tree = root / "site" / "assets" / kind
        if not tree.is_dir():
            continue
        for f in tree.glob(f"*.{kind}"):
            h = hashlib.sha256(f.read_bytes()).hexdigest()[:8]
            assert f.stem == h, f"{f.name} content hashes to {h} — filename==hash contract broken"


@pytest.fixture()
def lanes(tmp_path):
    """Bare origin + two clones sharing a base commit (hashed css + page + data)."""
    env = _env(tmp_path)
    origin = tmp_path / "origin.git"
    run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], tmp_path, env)
    lane1, lane2 = tmp_path / "lane1", tmp_path / "lane2"
    run(["git", "clone", "-q", str(origin), str(lane1)], tmp_path, env)
    base_css = css_body("/*base*/")
    base_hash = write_hashed_css(lane1, base_css)
    (lane1 / "site" / "page.html").write_text(f"<link href=assets/css/{base_hash}.css>\n")
    (lane1 / "data").mkdir()
    (lane1 / "data" / "x.json").write_text('{"day": 1}\n')
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "base"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)
    run(["git", "clone", "-qb", "main", str(origin), str(lane2)], tmp_path, env)
    return env, origin, lane1, lane2, base_hash, base_css


def rename_css(root: Path, base_hash: str, new_css: str, relink=True) -> str:
    (root / "site" / "assets" / "css" / f"{base_hash}.css").unlink()
    h = write_hashed_css(root, new_css)
    if relink:
        (root / "site" / "page.html").write_text(f"<link href=assets/css/{h}.css>\n")
    return h


def rename_js(root: Path, base_hash: str, new_js: str) -> str:
    (root / "site" / "assets" / "js" / f"{base_hash}.js").unlink()
    return write_hashed_js(root, new_js)


def test_rename_rename_keeps_both_sides_and_completes(lanes):
    env, origin, lane1, lane2, base_hash, base_css = lanes
    h1 = rename_css(lane1, base_hash, css_body(".lane1{top:0}"))
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "render: lane1"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)

    h2 = rename_css(lane2, base_hash, css_body(".lane2{left:0}"))
    (lane2 / "data" / "x.json").write_text('{"day": 2}\n')
    run(["git", "add", "-A"], lane2, env)
    run(["git", "commit", "-qm", "engine: lane2 outputs"], lane2, env)

    pull = run(PULL, lane2, env, check=False)
    assert pull.returncode != 0 and "rename/rename" in pull.stdout + pull.stderr
    assert in_rebase(lane2)

    r = resolver(lane2, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not in_rebase(lane2)

    css_dir = lane2 / "site" / "assets" / "css"
    assert sorted(p.name for p in css_dir.glob("*.css")) == sorted([f"{h1}.css", f"{h2}.css"])
    assert not (css_dir / f"{base_hash}.css").exists()
    assert_hash_pure(lane2)
    # -X theirs keeps the replayed (lane2) page, whose link must not dangle
    assert h2 in (lane2 / "site" / "page.html").read_text()
    assert (lane2 / "data" / "x.json").read_text() == '{"day": 2}\n'
    assert not run(["git", "ls-files", "-u"], lane2, env).stdout.strip()
    run(["git", "push", "-q", "origin", "main"], lane2, env)  # the day's outputs land


def test_rename_rename_hashed_js_resolves_alongside_css(lanes):
    """PR #4247's site/assets/js/<hash>.js tree auto-resolves like the css tree."""
    env, origin, lane1, lane2, base_hash, base_css = lanes
    # seed a hashed js asset present in both lanes
    base_js_hash = write_hashed_js(lane1, js_body("var base=0;"))
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "seed hashed js"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)
    run(["git", "pull", "-q", "--rebase", "origin", "main"], lane2, env)

    # each lane renames BOTH hashed assets in one commit
    h1c = rename_css(lane1, base_hash, css_body(".lane1{top:0}"))
    h1j = rename_js(lane1, base_js_hash, js_body("var lane1=1;"))
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "render: lane1 both trees"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)

    h2c = rename_css(lane2, base_hash, css_body(".lane2{left:0}"))
    h2j = rename_js(lane2, base_js_hash, js_body("var lane2=2;"))
    run(["git", "add", "-A"], lane2, env)
    run(["git", "commit", "-qm", "render: lane2 both trees"], lane2, env)

    pull = run(PULL, lane2, env, check=False)
    assert pull.returncode != 0 and "rename/rename" in pull.stdout + pull.stderr
    assert in_rebase(lane2)

    r = resolver(lane2, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not in_rebase(lane2)
    css_names = {p.name for p in (lane2 / "site" / "assets" / "css").glob("*.css")}
    js_names = {p.name for p in (lane2 / "site" / "assets" / "js").glob("*.js")}
    assert css_names == {f"{h1c}.css", f"{h2c}.css"}
    assert js_names == {f"{h1j}.js", f"{h2j}.js"}
    assert_hash_pure(lane2)
    assert not run(["git", "ls-files", "-u"], lane2, env).stdout.strip()
    run(["git", "push", "-q", "origin", "main"], lane2, env)


def test_refuses_conflicts_outside_hashed_css(lanes):
    env, origin, lane1, lane2, base_hash, base_css = lanes
    # same divergent css rename AND a non-derived rename/rename in data/
    seed = "line\n" * 200
    (lane1 / "data" / "base.txt").write_text(seed)
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "seed data file"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)
    run(["git", "pull", "-q", "--rebase", "origin", "main"], lane2, env)

    rename_css(lane1, base_hash, css_body(".lane1{top:0}"))
    (lane1 / "data" / "base.txt").rename(lane1 / "data" / "one.txt")
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "lane1"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)

    rename_css(lane2, base_hash, css_body(".lane2{left:0}"))
    (lane2 / "data" / "base.txt").rename(lane2 / "data" / "two.txt")
    run(["git", "add", "-A"], lane2, env)
    run(["git", "commit", "-qm", "lane2"], lane2, env)

    pull = run(PULL, lane2, env, check=False)
    assert pull.returncode != 0 and in_rebase(lane2)

    r = resolver(lane2, env)
    assert r.returncode != 0
    assert "refusing" in r.stdout + r.stderr
    # rebase left in place for the caller's abort+retry path
    assert in_rebase(lane2)
    run(["git", "rebase", "--abort"], lane2, env)


def test_refuses_non_hashed_js_inside_the_js_tree(lanes):
    """The js allowance is hash-shaped, not tree-wide: a real, hand-named script
    under site/assets/js/ must never be auto-resolved."""
    env, origin, lane1, lane2, base_hash, base_css = lanes
    seed = "console.log('seed');\n" * 200
    (lane1 / "site" / "assets" / "js").mkdir(parents=True)
    (lane1 / "site" / "assets" / "js" / "vendor.js").write_text(seed)
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "seed real js file"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)
    run(["git", "pull", "-q", "--rebase", "origin", "main"], lane2, env)

    (lane1 / "site" / "assets" / "js" / "vendor.js").rename(
        lane1 / "site" / "assets" / "js" / "vendor-one.js"
    )
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "lane1 renames vendor"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)

    (lane2 / "site" / "assets" / "js" / "vendor.js").rename(
        lane2 / "site" / "assets" / "js" / "vendor-two.js"
    )
    run(["git", "add", "-A"], lane2, env)
    run(["git", "commit", "-qm", "lane2 renames vendor"], lane2, env)

    pull = run(PULL, lane2, env, check=False)
    assert pull.returncode != 0 and in_rebase(lane2)

    r = resolver(lane2, env)
    assert r.returncode != 0
    assert "refusing" in r.stdout + r.stderr
    assert in_rebase(lane2)
    run(["git", "rebase", "--abort"], lane2, env)


def test_noop_without_rebase_in_progress(lanes):
    env, origin, lane1, lane2, base_hash, base_css = lanes
    r = resolver(lane2, env)
    assert r.returncode != 0
    assert "no rebase in progress" in r.stdout + r.stderr


def test_multi_commit_stack_resolves_each_stop(lanes):
    env, origin, lane1, lane2, base_hash, base_css = lanes
    # second base stylesheet, present in both lanes
    css_b = css_body("/*second*/")
    hash_b = write_hashed_css(lane1, css_b)
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "second stylesheet"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)
    run(["git", "pull", "-q", "--rebase", "origin", "main"], lane2, env)

    # lane1: one commit renaming BOTH stylesheets
    h1a = rename_css(lane1, base_hash, css_body(".lane1a{top:0}"))
    h1b = rename_css(lane1, hash_b, css_body(".lane1b{top:1}"), relink=False)
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "lane1 both"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)

    # lane2: TWO commits, each renaming one — the rebase stops twice
    h2a = rename_css(lane2, base_hash, css_body(".lane2a{left:0}"))
    run(["git", "add", "-A"], lane2, env)
    run(["git", "commit", "-qm", "lane2 first"], lane2, env)
    h2b = rename_css(lane2, hash_b, css_body(".lane2b{left:1}"), relink=False)
    run(["git", "add", "-A"], lane2, env)
    run(["git", "commit", "-qm", "lane2 second"], lane2, env)

    pull = run(PULL, lane2, env, check=False)
    assert pull.returncode != 0 and in_rebase(lane2)

    r = resolver(lane2, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not in_rebase(lane2)
    names = {p.name for p in (lane2 / "site" / "assets" / "css").glob("*.css")}
    assert names == {f"{h}.css" for h in (h1a, h1b, h2a, h2b)}
    assert_hash_pure(lane2)


def test_rename_delete_keeps_upstream_rename(lanes):
    env, origin, lane1, lane2, base_hash, base_css = lanes
    h1 = rename_css(lane1, base_hash, css_body(".lane1{top:0}"))
    run(["git", "add", "-A"], lane1, env)
    run(["git", "commit", "-qm", "lane1 rename"], lane1, env)
    run(["git", "push", "-q", "origin", "main"], lane1, env)

    # lane2 drops the stylesheet entirely (page lost its big inline block)
    (lane2 / "site" / "assets" / "css" / f"{base_hash}.css").unlink()
    (lane2 / "site" / "page.html").write_text("<p>no styles</p>\n")
    run(["git", "add", "-A"], lane2, env)
    run(["git", "commit", "-qm", "lane2 delete"], lane2, env)

    pull = run(PULL, lane2, env, check=False)
    if pull.returncode == 0:
        pytest.skip("git auto-resolved rename/delete on this version — nothing to do")
    assert in_rebase(lane2)

    r = resolver(lane2, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert not in_rebase(lane2)
    # upstream's renamed file survives; next externalize run prunes it if orphaned
    assert (lane2 / "site" / "assets" / "css" / f"{h1}.css").exists()
    assert_hash_pure(lane2)
