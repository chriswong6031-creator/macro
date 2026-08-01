"""engine.marketing.indexnow — diff, ordering/cap, fail-soft, and annotation guards.

Hermetic: every test builds its own site/ + sitemap.xml under tmp_path and the ONE
network seam (``indexnow._urlopen``) is monkeypatched to explode unless a test
deliberately stubs it.  A test that reaches the real endpoint fails loudly rather
than quietly submitting our production URLs from CI.

Run: .venv/bin/python -m pytest tests/test_indexnow.py -q
"""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path

import pytest

from engine.marketing import indexnow

BASE = "https://www.mastermind-x.com"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _local_rel(path: str) -> str:
    rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return rel


def _write_page(root: Path, path: str, body: str) -> None:
    f = root / "site" / _local_rel(path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")


def _write_sitemap(root: Path, paths: list[str]) -> None:
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    urls = "".join(f"  <url><loc>{BASE}{p}</loc></url>\n" for p in paths)
    (site / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n",
        encoding="utf-8",
    )


def _write_key(root: Path, body: str | None = None) -> None:
    site = root / "site"
    site.mkdir(parents=True, exist_ok=True)
    (site / f"{indexnow.INDEXNOW_KEY}.txt").write_text(
        indexnow.INDEXNOW_KEY if body is None else body, encoding="utf-8"
    )


def _write_state(root: Path, submitted: dict[str, str]) -> Path:
    path = root / "data" / "marketing" / "seo" / "indexnow_state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"as_of": "2026-07-01T00:00:00+00:00", "submitted": submitted}),
        encoding="utf-8",
    )
    return path


def _state_path(root: Path) -> Path:
    return root / "data" / "marketing" / "seo" / "indexnow_state.json"


def _sha1_of(root: Path, path: str) -> str:
    digest = indexnow._sha1_file(root / "site" / _local_rel(path))
    assert digest is not None
    return digest


class _FakeResp:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Default seam: any un-stubbed submission is a test failure, not a live POST."""

    def _boom(req, timeout):  # noqa: ANN001
        raise AssertionError(
            f"indexnow attempted a real network call to {getattr(req, 'full_url', req)}"
        )

    monkeypatch.setattr(indexnow, "_urlopen", _boom)


@pytest.fixture()
def site(tmp_path: Path) -> Path:
    """A minimal three-page site with a valid key file and no prior state."""
    _write_key(tmp_path)
    _write_page(tmp_path, "/", "home v1")
    _write_page(tmp_path, "/plans.html", "plans v1")
    _write_page(tmp_path, "/stocks/aapl.html", "aapl v1")
    _write_sitemap(tmp_path, ["/", "/plans.html", "/stocks/aapl.html"])
    return tmp_path


# ---------------------------------------------------------------------------
# Diff logic — new / changed / deleted
# ---------------------------------------------------------------------------


def test_first_run_is_all_new(site: Path):
    plan = indexnow.build_plan(site)
    assert plan["new"] == [
        f"{BASE}/",
        f"{BASE}/plans.html",
        f"{BASE}/stocks/aapl.html",
    ]
    assert plan["changed"] == []
    assert plan["deleted"] == []
    assert len(plan["submit"]) == 3


def test_unchanged_inventory_is_not_resubmitted(site: Path):
    """The docket's hard acceptance: IndexNow cannot bulk-submit unchanged pages."""
    _write_state(site, {
        f"{BASE}/": _sha1_of(site, "/"),
        f"{BASE}/plans.html": _sha1_of(site, "/plans.html"),
        f"{BASE}/stocks/aapl.html": _sha1_of(site, "/stocks/aapl.html"),
    })
    plan = indexnow.build_plan(site)
    assert plan["new"] == []
    assert plan["changed"] == []
    assert plan["deleted"] == []
    assert plan["submit"] == []


def test_changed_body_is_detected_by_hash(site: Path):
    _write_state(site, {
        f"{BASE}/": _sha1_of(site, "/"),
        f"{BASE}/plans.html": "stale-hash-from-a-previous-body",
        f"{BASE}/stocks/aapl.html": _sha1_of(site, "/stocks/aapl.html"),
    })
    plan = indexnow.build_plan(site)
    assert plan["changed"] == [f"{BASE}/plans.html"]
    assert plan["new"] == []
    assert plan["submit"] == [f"{BASE}/plans.html"]


def test_url_dropped_from_sitemap_is_submitted_as_deleted(site: Path):
    gone = f"{BASE}/retired.html"
    _write_state(site, {
        f"{BASE}/": _sha1_of(site, "/"),
        f"{BASE}/plans.html": _sha1_of(site, "/plans.html"),
        f"{BASE}/stocks/aapl.html": _sha1_of(site, "/stocks/aapl.html"),
        gone: "whatever-it-used-to-be",
    })
    plan = indexnow.build_plan(site)
    assert plan["deleted"] == [gone]
    assert plan["submit"] == [gone]


def test_sitemap_url_whose_file_vanished_is_a_deletion(site: Path):
    """Still listed, but the builder no longer emits it — announce the removal."""
    _write_state(site, {f"{BASE}/plans.html": _sha1_of(site, "/plans.html")})
    (site / "site" / "plans.html").unlink()
    plan = indexnow.build_plan(site)
    assert plan["deleted"] == [f"{BASE}/plans.html"]
    assert f"{BASE}/plans.html" not in plan["hashes"]


def test_sitemap_url_with_no_file_and_no_history_is_not_submitted(site: Path):
    """Nothing honest to say about a URL that never had content — never guess."""
    _write_sitemap(site, ["/", "/plans.html", "/stocks/aapl.html", "/never_built.html"])
    plan = indexnow.build_plan(site)
    assert plan["unresolved"] == [f"{BASE}/never_built.html"]
    assert f"{BASE}/never_built.html" not in plan["submit"]


def test_full_ignores_state_and_submits_everything(site: Path):
    _write_state(site, {
        f"{BASE}/": _sha1_of(site, "/"),
        f"{BASE}/plans.html": _sha1_of(site, "/plans.html"),
        f"{BASE}/stocks/aapl.html": _sha1_of(site, "/stocks/aapl.html"),
    })
    assert indexnow.build_plan(site)["submit"] == []
    assert len(indexnow.build_plan(site, full=True)["submit"]) == 3


def test_foreign_host_in_sitemap_is_ignored(tmp_path: Path):
    _write_key(tmp_path)
    _write_page(tmp_path, "/", "home")
    _write_sitemap(tmp_path, ["/"])
    sm = tmp_path / "site" / "sitemap.xml"
    sm.write_text(
        sm.read_text(encoding="utf-8").replace(
            "</urlset>",
            "  <url><loc>https://evil.example.com/x.html</loc></url>\n</urlset>",
        ),
        encoding="utf-8",
    )
    urls = indexnow.read_sitemap_urls(sm)
    assert urls == [f"{BASE}/"]


# ---------------------------------------------------------------------------
# Ordering + cap
# ---------------------------------------------------------------------------


def _big_site(root: Path, *, cores: int, stocks: int, researches: int) -> Path:
    _write_key(root)
    paths = []
    for i in range(cores):
        p = f"/core{i}.html"
        _write_page(root, p, f"core {i}")
        paths.append(p)
    for i in range(stocks):
        p = f"/stocks/t{i}.html"
        _write_page(root, p, f"stock {i}")
        paths.append(p)
    for i in range(researches):
        p = f"/research/r{i}.html"
        _write_page(root, p, f"research {i}")
        paths.append(p)
    _write_sitemap(root, paths)
    return root


def test_core_pages_are_ordered_ahead_of_the_bulk_estates(tmp_path: Path):
    root = _big_site(tmp_path, cores=3, stocks=5, researches=4)
    submit = indexnow.build_plan(root)["submit"]
    ranks = [indexnow._rank(u) for u in submit]
    assert ranks == sorted(ranks), "submission order must be core-first, then tails"
    assert ranks[:3] == [0, 0, 0]
    assert set(ranks) == {0, 1, 2}


def test_cap_keeps_core_pages_and_defers_the_tail(tmp_path: Path):
    root = _big_site(tmp_path, cores=3, stocks=5, researches=4)
    plan = indexnow.build_plan(root, cap=4)
    assert len(plan["submit"]) == 4
    assert len(plan["dropped"]) == 8
    assert all("/core" in u for u in plan["submit"][:3])
    # No overlap, no loss: cap partitions the candidate set, it never truncates it.
    assert set(plan["submit"]) & set(plan["dropped"]) == set()
    assert len(set(plan["submit"]) | set(plan["dropped"])) == 12


def test_cap_emits_a_notice_naming_the_dropped_count(tmp_path: Path, capsys):
    root = _big_site(tmp_path, cores=3, stocks=5, researches=4)
    indexnow.run(root, dry_run=True, cap=4)
    out = capsys.readouterr().out
    notices = [l for l in out.splitlines() if l.startswith("::notice")]
    assert len(notices) == 1, out
    assert "indexnow" in notices[0]
    assert "8" in notices[0], f"dropped count not named: {notices[0]}"


def test_uncapped_run_emits_no_notice(tmp_path: Path, capsys):
    root = _big_site(tmp_path, cores=3, stocks=5, researches=4)
    indexnow.run(root, dry_run=True, cap=100)
    assert "::notice" not in capsys.readouterr().out


def test_capped_urls_are_requeued_not_lost(tmp_path: Path, monkeypatch):
    root = _big_site(tmp_path, cores=3, stocks=5, researches=4)
    monkeypatch.setattr(indexnow, "_urlopen", lambda req, timeout: _FakeResp(200))

    first = indexnow.run(root, cap=4)
    assert first["status"] == "ok" and first["submitted"] == 4

    second = indexnow.build_plan(root, cap=100)
    assert len(second["submit"]) == 8
    assert set(second["submit"]) == set(first["plan"]["dropped"])


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def test_dry_run_sends_nothing_and_writes_nothing(site: Path, capsys):
    # The autouse _no_network seam raises on any submission attempt.
    result = indexnow.run(site, dry_run=True)
    assert result["status"] == "dry_run"
    assert result["submitted"] == 0
    assert not _state_path(site).exists()
    out = capsys.readouterr().out
    assert "dry run" in out
    assert f"{BASE}/" in out


def test_dry_run_via_cli_leaves_state_untouched(site: Path):
    before = _write_state(site, {f"{BASE}/plans.html": "stale"}).read_bytes()
    indexnow.main(["--root", str(site), "--dry-run"])
    assert _state_path(site).read_bytes() == before


def test_dry_run_preview_is_bounded(tmp_path: Path, capsys):
    root = _big_site(tmp_path, cores=40, stocks=0, researches=0)
    indexnow.run(root, dry_run=True)
    out = capsys.readouterr().out
    listed = [l for l in out.splitlines() if l.startswith(f"  {BASE}/")]
    assert len(listed) == indexnow._PLAN_PREVIEW_N
    assert "20 more" in out


# ---------------------------------------------------------------------------
# Failure paths — state must never advance past an unaccepted batch
# ---------------------------------------------------------------------------


def _stale_state(root: Path) -> bytes:
    return _write_state(root, {f"{BASE}/plans.html": "stale-hash"}).read_bytes()


@pytest.mark.parametrize(
    "boom",
    [
        lambda req, timeout: (_ for _ in ()).throw(
            urllib.error.URLError("connection refused")
        ),
        lambda req, timeout: (_ for _ in ()).throw(
            urllib.error.HTTPError(indexnow.ENDPOINT, 403, "Forbidden", {}, None)
        ),
        lambda req, timeout: (_ for _ in ()).throw(TimeoutError("timed out")),
        lambda req, timeout: _FakeResp(500),
    ],
    ids=["urlerror", "http403", "timeout", "http500"],
)
def test_failed_submission_leaves_state_untouched(site: Path, monkeypatch, capsys, boom):
    before = _stale_state(site)
    monkeypatch.setattr(indexnow, "_urlopen", boom)

    result = indexnow.run(site)

    assert result["status"] == "failed"
    assert result["submitted"] == 0
    assert _state_path(site).read_bytes() == before, "state advanced past a failed batch"
    warnings = [l for l in capsys.readouterr().out.splitlines() if l.startswith("::warning")]
    assert len(warnings) == 1
    assert "retry" in warnings[0]


def test_retry_after_failure_resubmits_the_same_set(site: Path, monkeypatch):
    _stale_state(site)
    monkeypatch.setattr(
        indexnow,
        "_urlopen",
        lambda req, timeout: (_ for _ in ()).throw(urllib.error.URLError("down")),
    )
    failed = indexnow.run(site)["plan"]["submit"]

    monkeypatch.setattr(indexnow, "_urlopen", lambda req, timeout: _FakeResp(200))
    retried = indexnow.run(site)
    assert retried["status"] == "ok"
    assert retried["plan"]["submit"] == failed


def test_accepted_submission_advances_state(site: Path, monkeypatch):
    sent: list[dict] = []

    def _ok(req, timeout):
        sent.append(json.loads(req.data.decode("utf-8")))
        assert timeout == 30
        return _FakeResp(202)

    monkeypatch.setattr(indexnow, "_urlopen", _ok)
    result = indexnow.run(site)

    assert result["status"] == "ok"
    assert len(sent) == 1, "one batch, not one request per URL"
    body = sent[0]
    assert body["host"] == indexnow.HOST
    assert body["key"] == indexnow.INDEXNOW_KEY
    assert body["keyLocation"] == indexnow.KEY_LOCATION
    assert sorted(body["urlList"]) == sorted([
        f"{BASE}/", f"{BASE}/plans.html", f"{BASE}/stocks/aapl.html",
    ])

    state = json.loads(_state_path(site).read_text(encoding="utf-8"))
    assert state["submitted"][f"{BASE}/"] == _sha1_of(site, "/")
    assert state["as_of"]
    # Second run is a genuine no-op.
    assert indexnow.run(site)["status"] == "noop"


def test_deleted_url_is_removed_from_state_after_acceptance(site: Path, monkeypatch):
    gone = f"{BASE}/retired.html"
    _write_state(site, {
        f"{BASE}/": _sha1_of(site, "/"),
        f"{BASE}/plans.html": _sha1_of(site, "/plans.html"),
        f"{BASE}/stocks/aapl.html": _sha1_of(site, "/stocks/aapl.html"),
        gone: "old",
    })
    monkeypatch.setattr(indexnow, "_urlopen", lambda req, timeout: _FakeResp(200))
    indexnow.run(site)
    state = json.loads(_state_path(site).read_text(encoding="utf-8"))
    assert gone not in state["submitted"]


# ---------------------------------------------------------------------------
# Key file fail-soft
# ---------------------------------------------------------------------------


def test_missing_key_file_warns_and_skips(tmp_path: Path, capsys):
    _write_page(tmp_path, "/", "home")
    _write_sitemap(tmp_path, ["/"])
    result = indexnow.run(tmp_path)          # autouse seam would raise on a POST
    assert result["status"] == "skipped"
    warnings = [l for l in capsys.readouterr().out.splitlines() if l.startswith("::warning")]
    assert len(warnings) == 1
    assert "key file missing" in warnings[0]
    assert not _state_path(tmp_path).exists()


def test_wrong_key_file_contents_warns_and_skips(tmp_path: Path, capsys):
    _write_key(tmp_path, body="not-the-key")
    _write_page(tmp_path, "/", "home")
    _write_sitemap(tmp_path, ["/"])
    result = indexnow.run(tmp_path)
    assert result["status"] == "skipped"
    assert "do not match" in capsys.readouterr().out


def test_key_file_tolerates_a_trailing_newline(tmp_path: Path):
    _write_key(tmp_path, body=indexnow.INDEXNOW_KEY + "\n")
    ok, _ = indexnow.key_file_ok(tmp_path / "site")
    assert ok


def test_shipped_key_file_matches_the_constant():
    """The repo's served key file IS the ownership proof — a drift breaks every push."""
    repo = Path(__file__).resolve().parents[1]
    ok, detail = indexnow.key_file_ok(repo / "site")
    assert ok, detail
    assert indexnow.KEY_LOCATION.endswith(f"/{indexnow.INDEXNOW_KEY}.txt")


def test_key_file_is_public_at_the_edge():
    """A regwalled key file means every submission is rejected for unproven ownership."""
    repo = Path(__file__).resolve().parents[1]
    caddy = (repo / "app" / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    entry = f"/{indexnow.INDEXNOW_KEY}.txt"
    active = [
        l for l in caddy.splitlines()
        if "/robots.txt" in l and not l.lstrip().startswith("#")
    ]
    assert active, "no active Caddy allowlist line found"
    for line in active:
        assert entry in line, f"key file missing from an active allowlist: {line.strip()[:80]}"
    policy = (repo / "config" / "site_access.yml").read_text(encoding="utf-8")
    assert f"- {entry}" in policy


# ---------------------------------------------------------------------------
# Annotation compliance (house law — tests/test_gh_annotation_line_start.py)
# ---------------------------------------------------------------------------


def test_every_annotation_starts_its_line(tmp_path: Path, monkeypatch, capsys):
    """A logger-prefixed annotation is invisible to GitHub. Assert via capsys.

    caplog would pass on the broken form — it reads the record, not the stream —
    so the stream is what this checks, and it checks the COLUMN, not the wording.
    """
    # 1. key-file warning
    _write_page(tmp_path, "/", "home")
    _write_sitemap(tmp_path, ["/"])
    indexnow.run(tmp_path)
    # 2. cap notice
    root2 = _big_site(tmp_path / "b", cores=3, stocks=5, researches=4)
    indexnow.run(root2, dry_run=True, cap=2)
    # 3. submission-failure warning
    _write_key(tmp_path)
    monkeypatch.setattr(
        indexnow,
        "_urlopen",
        lambda req, timeout: (_ for _ in ()).throw(urllib.error.URLError("down")),
    )
    indexnow.run(tmp_path)

    lines = capsys.readouterr().out.splitlines()
    annotated = [l for l in lines if "::warning" in l or "::notice" in l or "::error" in l]
    assert len(annotated) >= 3, annotated
    for line in annotated:
        assert line.startswith("::"), (
            f"annotation does not start its line — GitHub will drop it: {line!r}"
        )
        assert line.startswith(("::warning title=indexnow::",
                               "::notice title=indexnow::",
                               "::error title=indexnow::")), line


def test_module_routes_no_annotation_through_a_logger():
    """Local mirror of the repo-wide guard, pinned to this module."""
    import ast

    src = Path(indexnow.__file__).read_text(encoding="utf-8")
    offenders = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in {"debug", "info", "warning", "error", "critical", "exception"}:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) \
                and first.value.startswith("::"):
            offenders.append(node.lineno)
    assert offenders == [], f"annotation routed through a logger at lines {offenders}"


# ---------------------------------------------------------------------------
# URL -> file mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"{BASE}/", "index.html"),
        (f"{BASE}/plans.html", "plans.html"),
        (f"{BASE}/blog/", "blog/index.html"),
        (f"{BASE}/stocks/aapl.html", "stocks/aapl.html"),
        ("https://mastermind-x.com/plans.html", "plans.html"),   # apex is still ours
    ],
)
def test_url_maps_to_the_built_file(tmp_path: Path, url: str, expected: str):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    got = indexnow.local_file(site_dir, url)
    assert got is not None
    assert got.relative_to(site_dir).as_posix() == expected


@pytest.mark.parametrize(
    "url",
    ["https://evil.example.com/x.html", "ftp://www.mastermind-x.com/x", "not a url"],
)
def test_foreign_or_malformed_urls_do_not_map(tmp_path: Path, url: str):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    assert indexnow.local_file(site_dir, url) is None


def test_traversal_out_of_site_is_refused(tmp_path: Path):
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    assert indexnow.local_file(site_dir, f"{BASE}/../../etc/passwd") is None
