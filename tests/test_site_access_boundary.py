"""Static serving-boundary drift and client-artifact leak tripwires."""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())
CADDY = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
SITE = ROOT / "site"

# Caddy exclusions that have no home in config/site_access.yml. The policy
# schema classifies static FILE paths under site/; these are reverse-proxied
# ROUTES to macro-api (app/main.py), which enforces its own auth. Excluding them
# from the static matchers is what stops a ws upgrade / API call from being
# swallowed by the file gate — it is not a public-content decision.
NON_POLICY_ROUTES = {"/api/*", "/ws/tape"}

# Public policy entries whose target is a RUNTIME artifact, not a committed
# file. site/live/ is gitignored: the systemd lanes publish by atomic rename
# into /var/lib/macro-live/public and scripts/live_breadth_poller.py force-adds
# a snapshot, so a fresh checkout may hold none of them. The policy line is
# still the boundary of record — only the on-disk existence check is exempt.
#
# The qualifying property is the DELIVERY path, NOT "is the content generated".
# site/live/ reaches the edge out of band, so a fresh checkout legitimately lacks
# it. A tree that reaches the edge only by being COMMITTED — "the VPS serves
# committed main; there is no Pages-artifact fallback" (render.yml) — is committed
# content no matter which builder emits it, and belongs in the existence check.
#
# /research/ was added here by #3507 to clear the #3488 red and is REMOVED again:
# it is render-lane output delivered by `git add site/`, and the exemption required
# gitignoring site/research/ to satisfy the honesty guard below. A gitignored
# subtree makes `git add site/` silently skip every NEW file — edits to the pages
# already tracked keep staging, new ones never do — so the estate would have frozen
# at the 86 pages #3501 landed while the research-ingest lane kept growing
# catalog.json: the exact "shipped dark" failure #3487 had just fixed. The tree is
# committed, so the assertion below now passes on its own merits.
RUNTIME_ARTIFACT_PREFIXES = ("/live/",)

# Shown on every missing-target failure. A public entry that points at nothing is a
# REAL defect (the edge advertises a path that 404s), so this stays a hard failure --
# but the cheap exit is the wrong one and #3507 proves the bait works: when a policy
# entry lands before its content, the red reads "missing public prefix" and the
# nearest fix is RUNTIME_ARTIFACT_PREFIXES. Name the two real remedies instead.
_MISSING_TARGET_HINT = (
    "config/site_access.yml declares it public but that path does not exist under "
    "site/. Either land the content first (a CI-generated tree needs its builder's "
    "first output committed BEFORE the policy entry -- see #3487/#3488/#3501), or "
    "drop the policy entry until it does. Do NOT add it to RUNTIME_ARTIFACT_PREFIXES "
    "unless the content reaches the edge WITHOUT being committed: that exemption "
    "requires gitignoring the tree, which silently stops the render lane's "
    "`git add site/` from ever shipping a new file under it."
)


def _caddy_public_exclusions() -> set[str]:
    match = re.search(
        r"# PUBLIC-BOUNDARY-START.*?@reg_asset\s*\{\s*not path ([^\n]+)",
        CADDY,
        flags=re.S,
    )
    assert match, "Caddy public-boundary marker/matcher missing"
    return set(shlex.split(match.group(1)))


def test_caddy_public_boundary_matches_policy_exactly():
    expected = set(NON_POLICY_ROUTES) | {"*.html"}
    expected.update(POLICY["public"]["exact"])
    expected.update(prefix.rstrip("/") + "/*" for prefix in POLICY["public"]["prefixes"])
    assert _caddy_public_exclusions() == expected


def test_product_family_is_public_in_every_caddy_html_path():
    """Success and fail-open/error matchers must agree on the public product tree."""
    for matcher in (
        "reg_html",
        "reg_asset",
        "gate_html",
        "reg_html_err",
        "reg_asset_err",
        "gate_html_err",
    ):
        match = re.search(rf"@{matcher}\s*\{{(.*?)^\s*\}}", CADDY, flags=re.S | re.M)
        assert match, f"Caddy matcher @{matcher} missing"
        path_lines = re.findall(r"^\s*(?:not\s+)?path\s+([^\n]+)", match.group(1), flags=re.M)
        matcher_paths = {
            token
            for path_line in path_lines
            for token in shlex.split(path_line)
        }
        assert "/products/*" in matcher_paths, (
            f"@{matcher} does not expose /products/*; anonymous product pages "
            "would change behavior between normal and error paths"
        )


def test_confluence_lead_magnet_is_public_in_every_caddy_html_path():
    """The free screener must never regress behind the account wall.

    Its paid ticker rows are omitted server-side by the builder; the static page
    is the intentionally public acquisition shell.
    """
    page = "/confluence_screener.html"
    assert page in POLICY["public"]["exact"]
    for matcher in (
        "reg_html",
        "reg_asset",
        "gate_html",
        "reg_html_err",
        "reg_asset_err",
        "gate_html_err",
    ):
        match = re.search(rf"@{matcher}\s*\{{(.*?)^\s*\}}", CADDY, flags=re.S | re.M)
        assert match, f"Caddy matcher @{matcher} missing"
        matcher_paths = {
            token
            for path_line in re.findall(
                r"^\s*(?:not\s+)?path\s+([^\n]+)",
                match.group(1),
                flags=re.M,
            )
            for token in shlex.split(path_line)
        }
        assert page in matcher_paths, (
            f"@{matcher} does not expose {page}; the free screener would be "
            "registration-gated on this serving path"
        )


def test_public_policy_targets_exist():
    for path in POLICY["public"]["exact"]:
        if path == "/" or path.startswith(RUNTIME_ARTIFACT_PREFIXES):
            continue
        assert (SITE / path.lstrip("/")).is_file(), (
            f"missing public exact path: {path} -- {_MISSING_TARGET_HINT}"
        )
    for prefix in POLICY["public"]["prefixes"]:
        if prefix.startswith(RUNTIME_ARTIFACT_PREFIXES):
            continue
        assert (SITE / prefix.strip("/")).is_dir(), (
            f"missing public prefix: {prefix} -- {_MISSING_TARGET_HINT}"
        )


def test_public_theme_imports_are_declared_public():
    """A public stylesheet must not import an asset hidden behind the regwall."""
    public_exact = set(POLICY["public"]["exact"])
    theme = (SITE / "theme.css").read_text()
    imports = re.findall(r'@import\s+url\(["\']?([^"\')?]+)', theme)
    assert imports, "site/theme.css should expose its external dependencies"
    for imported in imports:
        public_path = "/" + imported.split("?", 1)[0].lstrip("/")
        assert public_path in public_exact, (
            f"public theme.css imports gated asset {public_path}; "
            "declare the UI dependency in config/site_access.yml"
        )


def test_runtime_artifact_exemption_stays_honest():
    """The existence exemption is only legitimate for genuinely gitignored
    planes. If site/live/ ever became a committed tree, the exemption would
    start hiding typo'd/dead public policy entries instead of runtime churn."""
    ignored = {line.strip() for line in (ROOT / ".gitignore").read_text().splitlines()}
    for prefix in RUNTIME_ARTIFACT_PREFIXES:
        assert f"site{prefix}" in ignored, f"exempt prefix is not gitignored: site{prefix}"


def test_exempt_prefixes_publish_out_of_band():
    """Closes the hole BOTH existing guards leave open: the exemption and the
    .gitignore added TOGETHER.

    test_runtime_artifact_exemption_stays_honest asks "is it gitignored" -- which
    an author silencing a red can simply make true. test_public_estates_stay_committable
    skips exempt prefixes by construction. So the exact #3507 change (add /research/
    to RUNTIME_ARTIFACT_PREFIXES *and* site/research/ to .gitignore) passes both:
    verified by replaying it against the post-#3504/#3522 suite -- 8 passed. Only the
    gitignore half done ALONE was ever caught.

    The property that actually separates the two planes is DELIVERY, and it leaves a
    mechanical trace. A gitignored tree is invisible to the render lane's plain
    `git add site/`, so anything legitimately shipped from one must be named by an
    explicit `git add -f`:

        site/live/     14 tracked files, every one force-added by name across
                       intraday-fastpath / earlyclose / closing-bell / btc-live /
                       daily -- a genuine out-of-band plane with committed fallbacks.
        site/research/ 87 tracked files under #3507, ZERO force-adds anywhere. They
                       could only have arrived via plain `git add site/`, which is
                       proof the prefix is commit-delivered and the exemption false.

    So: if the repo TRACKS files under an exempt prefix and nothing force-adds there,
    the exemption contradicts how the content actually reaches the edge.
    """
    workflows = ROOT / ".github" / "workflows"
    wf_text = "\n".join(
        p.read_text() for p in sorted(workflows.glob("*.yml")) if p.is_file()
    )
    for prefix in RUNTIME_ARTIFACT_PREFIXES:
        tree = f"site{prefix}"                      # e.g. "site/live/"
        proc = subprocess.run(
            ["git", "ls-files", "--", tree],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        # Never read a broken git as "nothing tracked" -- that is the vacuous-green
        # failure this whole module keeps re-learning.
        assert proc.returncode == 0, (
            f"git ls-files unusable (rc={proc.returncode}), so this guard cannot "
            f"vouch for {tree}: {proc.stderr.strip()}"
        )
        tracked = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if not tracked:
            continue                                 # purely runtime -- nothing to explain
        assert re.search(rf"add\s+(?:-f|--force)\s+[^\n]*{re.escape(tree)}", wf_text), (
            f"{tree} is exempt as a runtime artifact and gitignored, yet the repo "
            f"tracks {len(tracked)} file(s) under it and NO workflow force-adds there "
            f"(`git add -f {tree}...`). Plain `git add site/` cannot stage an ignored "
            f"path, so those files prove the prefix is delivered by being COMMITTED -- "
            f"it is not a runtime plane. Either drop it from RUNTIME_ARTIFACT_PREFIXES "
            f"and un-ignore it (what #3522 did for /research/), or, if it really does "
            f"publish out of band, force-add its committed fallbacks by name the way "
            f"site/live/ does. See #3501/#3507/#3522."
        )


def test_public_estates_stay_committable():
    """The inverse guard: a NON-exempt public path must not be gitignored.

    Everything above is about the exemption being honest. This is about the 87%
    of the boundary that takes no exemption: those paths reach the edge only by
    being committed ("the VPS serves committed main; there is no Pages-artifact
    fallback" -- render.yml), and the render lane ships them with `git add site/`,
    which SKIPS ignored new files. So ignoring a served estate does not fail --
    it freezes. Edits to already-tracked pages keep staging, so the nightly diff
    still looks alive, while every new page silently never lands and the tracked
    index keeps linking to them.

    That is not hypothetical: #3507 ignored site/research/ hours after #3501
    committed 86 pages there, and the pair merged 32s apart. #3522 reverted it;
    this is the tripwire neither had. The existence check alone cannot catch it
    (the directory is present -- it is the NEXT file that vanishes), which is why
    it needs its own probe.
    """
    probes: dict[str, str] = {}
    for path in POLICY["public"]["exact"]:
        if path == "/" or path.startswith(RUNTIME_ARTIFACT_PREFIXES):
            continue
        probes[f"site{path}"] = path
    for prefix in POLICY["public"]["prefixes"]:
        if prefix.startswith(RUNTIME_ARTIFACT_PREFIXES):
            continue
        # A path that cannot exist, so this asks the ignore RULES rather than
        # the index -- exactly the question `git add site/` asks of a new page.
        probes[f"site{prefix}_ignore_probe.html"] = prefix

    proc = subprocess.run(
        ["git", "check-ignore", "--stdin"],
        cwd=ROOT,
        input="\n".join(probes) + "\n",
        capture_output=True,
        text=True,
    )
    # 0 = at least one path matched an ignore rule, 1 = none did. Anything else
    # (128 = not a git repo / git missing) must NOT be read as "nothing is
    # ignored" -- that is precisely how this guard would go vacuously green off
    # a checkout, reporting safety it never checked.
    assert proc.returncode in (0, 1), (
        f"git check-ignore unusable (rc={proc.returncode}), so this guard cannot "
        f"vouch for anything: {proc.stderr.strip()}"
    )
    offenders = sorted({probes[ln] for ln in proc.stdout.splitlines() if ln in probes})
    assert not offenders, (
        f"public path(s) {offenders} are gitignored. They are served from the "
        "committed tree, so the render lane's `git add site/` will silently skip "
        "every NEW file under them -- the estate freezes at whatever is tracked "
        "today while the builder keeps emitting pages that never ship. Either "
        "un-ignore them, or force-add them in render.yml the way site/stockbrief "
        "is. See #3501/#3507/#3522."
    )


def _gh_path_filter_to_re(pattern: str) -> re.Pattern:
    """GitHub filter-pattern globbing: `*` stays inside a segment, `**` crosses `/`.

    Deliberately not fnmatch, whose `*` crosses `/` — that is looser than GitHub
    and would report a path as covered when a PR touching it would trigger nothing.
    """
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern[i] == "*":
            if pattern[i + 1:i + 2] == "*":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def test_tier_gate_is_reachable_from_its_own_inputs():
    """A guard the guarded change cannot trigger is not a guard.

    ci.yml is `on: pull_request` with a ~530-entry `paths:` filter, so a job whose
    inputs are unlisted still exists but fires only as a bystander — on unrelated
    PRs that happen to touch a listed path. Until 2026-07-25 that was true of ALL
    eleven of tier-gate's inputs. #3488 changed exactly config/site_access.yml +
    Caddyfile + regwall.py, triggered no workflow at all, and merged with this
    suite never executed; `missing public prefix: /research/` then sat red on main
    and surfaced on everyone else's PR. #3474 gave the test a workflow that NAMES
    it; nothing gave it a trigger that REACHES it — two separate halves.

    They are all listed today. This keeps them listed, and is derived rather than
    hand-copied: it reads the tier-gate job's own `run:` steps, so a test file
    added to the job later is required in the filter automatically.
    """
    ci = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    manifest = yaml.safe_load(
        (ROOT / ".github" / "ci" / "legacy-jobs.yml").read_text()
    )
    # PyYAML resolves the bare key `on` to True (YAML 1.1 booleans).
    triggers = ci.get("on") or ci.get(True)
    matchers = [_gh_path_filter_to_re(p) for p in triggers["pull_request"]["paths"]]

    steps = manifest["jobs"]["tier-gate"]["steps"]
    required = set(re.findall(
        r"tests/test_[A-Za-z0-9_]+\.py",
        "\n".join(s["run"] for s in steps if "run" in s),
    ))
    assert required, "tier-gate runs no pytest targets — did the job change shape?"
    # Subjects under test that no `run:` line names: the two halves of the boundary
    # this module diffs, plus the routers the regwall/paywall suites exercise.
    required |= {"config/site_access.yml", "app/deploy/Caddyfile",
                 "app/regwall.py", "app/paywall.py"}

    unreachable = sorted(t for t in required if not any(m.match(t) for m in matchers))
    assert unreachable == [], (
        f"tier-gate inputs missing from ci.yml's pull_request paths: {unreachable}. "
        "A PR touching only these would run no serving-boundary guard at all — the "
        "#3488 failure mode. Add each to the paths list."
    )


def test_generated_data_is_not_accidentally_public():
    public = _caddy_public_exclusions()
    intentional = {
        # Reviewed machine-readable marketing metadata; contains no signal rows.
        "/brand-facts.json",
        "/live/quotes.json",
        "/live/breadth.json",
        # Official agency publication lifecycle and verified factual outcomes.
        "/live/release_publications.json",
        "/prophet/showcase.json",
        "/factordata/tech_lab.json",
        # Static Natural Earth geometry required by the public start-page globe.
        "/world-110m.json",
    }
    exposed_json = {p for p in public if p.endswith(".json")}
    assert exposed_json == intentional
    assert "/factordata/tech_events/*" in public
    assert "/factordata/*" not in public
    assert "/labdata/*" not in public
    assert "/neuralwebdata/*" not in public
    assert "/oracledata/*" not in public
    assert "/signals/*" not in public


def test_no_source_maps_secrets_or_server_source_in_site_tree():
    forbidden_suffixes = {".map", ".py", ".pyc", ".pem", ".key", ".env", ".sql"}
    bad = [
        p.relative_to(SITE).as_posix()
        for p in SITE.rglob("*")
        if p.is_file() and (p.suffix.lower() in forbidden_suffixes or p.name.startswith(".env"))
    ]
    assert bad == []


def test_fail_closed_and_browser_hardening_are_present():
    assert 'rewrite /api/regwall/check' in CADDY
    assert 'rewrite /api/paywall/check' in CADDY
    assert '{"error":"site_access_temporarily_unavailable"}' in CADDY
    assert "Content-Security-Policy \"base-uri 'self'; object-src 'none'; frame-ancestors 'none'\"" in CADDY
    assert 'X-Frame-Options "DENY"' in CADDY
    assert 'Permissions-Policy "camera=(), microphone=(), geolocation=(), usb=()"' in CADDY
