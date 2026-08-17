#!/usr/bin/env python3
"""Mutation tests: the validator must reject corrupted evidence for the intended reason."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_dossier import validate_path  # noqa: E402

SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        path.write_text(json.dumps(obj, indent=2) + "\n")
    else:
        path.write_text(str(obj))


def valid_dossier(root: Path) -> Path:
    d = root / "pages" / "mini"
    shot = d / "screenshots" / "mini_default_1440x1000.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    rel = "pages/mini/screenshots/mini_default_1440x1000.png"
    # artifact path is repo-relative from a fake repo: we put ux-evidence-like root
    write(
        d / "00-meta.json",
        {"route": "https://example.test/mini", "schema_version": "1.0-candidate"},
    )
    write(
        d / "run-manifest.json",
        {
            "schema_version": "1.0-candidate",
            "collector_version": SHA,
            "run_id": "20260816T000000Z-aaaaaaaa",
            "run_started_at": "2026-08-16T00:00:00+00:00",
            "repository": "example/test",
            "repo_head_sha": SHA,
            "working_tree_dirty": False,
            "browser_name": "chrome",
            "browser_version": "1",
            "playwright_version": "1",
            "device_scale_factor": 1,
            "authenticated_session_used": False,
            "source_parity_method": "sha256",
            "operating_platform": "test",
        },
    )
    write(
        d / "element-manifest.json",
        {
            "elements_1440": [
                {
                    "stable_id": "E.mini.btn",
                    "id": "E.mini.btn",
                    "found": True,
                    "selector": "#btn",
                    "selector_used": "#btn",
                    "match_count": 1,
                    "expected_cardinality": 1,
                    "resolution_status": "RESOLVED",
                    "visible": True,
                }
            ]
        },
    )
    write(
        d / "interaction-manifest.json",
        [
            {
                "interaction_id": "I.mini.click",
                "element_stable_id": "E.mini.btn",
                "section_id": "S.mini",
                "baseline_state": "DEFAULT",
                "action": "click",
                "expected_postconditions": {"open": True},
                "observed_postconditions": {"open": True},
                "pass": True,
                "attempt_status": "passed",
                "resulting_state": "OPEN",
                "screenshot_refs": ["pages/mini/screenshots/mini_default_1440x1000.png"],
                "side_effect_class": "READ_ONLY",
            }
        ],
    )
    write(
        d / "state-manifest.json",
        {"observed_verified_states": ["OPEN"], "failed_attempts": [], "transitions": ["DEFAULT -> OPEN"]},
    )
    write(
        d / "page-sections.json",
        [
            {
                "section_id": "S.mini",
                "id": "S.mini",
                "label": "Mini",
                "order": 0,
                "found": True,
                "visible": True,
                "resolution_status": "RESOLVED",
                "match_count": 1,
                "expected_cardinality": 1,
                "selector_used": "#mini",
            }
        ],
    )
    write(
        d / "control-coverage.json",
        [{"id": "E.mini.btn", "status": "tested", "section": "S.mini"}],
    )
    write(
        d / "source-parity.json",
        {"items": [{"artifact": "mini.html", "status": "UNVERIFIED", "parity_reason": "fixture"}]},
    )
    write(
        d / "capture-fidelity.json",
        [
            {
                "repo_relative_path": rel,
                "capture_fidelity": {
                    "requested_width": 1440,
                    "requested_height": 1000,
                    "inner_width": 1440,
                    "inner_height": 1000,
                    "DPR": 1,
                    "PNG_width": 1440,
                    "PNG_height": 1000,
                    "png_dimensions_valid": True,
                    "full_page": False,
                },
                "requested": {"w": 1440, "h": 1000, "full": False},
                "inner": {"w": 1440, "h": 1000},
                "dpr": 1,
                "screenshot_px": {"w": 1440, "h": 1000},
            }
        ],
    )
    write(d / "accessibility-summary.json", {"landmarks": [], "headings": [], "anomalies": []})
    # artifact hash filled after we know bytes
    digest = __import__("hashlib").sha256(shot.read_bytes()).hexdigest()
    write(
        d / "artifact-manifest.json",
        {
            "artifacts": [
                {
                    "repo_relative_path": rel,
                    "artifact_type": "screenshot",
                    "sha256": digest,
                    "byte_size": shot.stat().st_size,
                    "generated_by": "test",
                    "associated_route": "/mini",
                    "associated_state": "DEFAULT",
                    "associated_viewport": "1440x1000",
                }
            ]
        },
    )
    write(d / "decision-data-map.json", {"fields": []})
    return d


class ValidatorMutations(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uxev-"))
        # Pretend this tmp is a repo so repo_root-relative artifact paths resolve.
        (self.tmp / ".git").mkdir()
        (self.tmp / "ux-evidence").mkdir()
        self.d = valid_dossier(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _validate_with_monkey(self):
        import validate_dossier as vd

        real = vd.repo_root

        def fake_root():
            return self.tmp

        vd.repo_root = fake_root
        try:
            return vd.validate_path(self.d)
        finally:
            vd.repo_root = real

    def assert_p0_contains(self, report, needle: str):
        blob = " | ".join(report.p0)
        self.assertTrue(report.p0, f"expected P0 failures, got PASS. needle={needle}")
        self.assertIn(needle.lower(), blob.lower(), f"missing {needle!r} in {blob}")

    def test_valid_passes(self):
        report = self._validate_with_monkey()
        self.assertTrue(report.ok, report.p0)

    def test_missing_screenshot(self):
        (self.d / "screenshots" / "mini_default_1440x1000.png").unlink()
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "artifact missing")

    def test_dangling_screenshot_reference(self):
        ix = json.loads((self.d / "interaction-manifest.json").read_text())
        ix[0]["screenshot_refs"] = ["pages/mini/screenshots/does-not-exist.png"]
        write(self.d / "interaction-manifest.json", ix)
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "dangling screenshot")

    def test_duplicate_stable_id(self):
        el = json.loads((self.d / "element-manifest.json").read_text())
        el["elements_1440"].append(dict(el["elements_1440"][0]))
        write(self.d / "element-manifest.json", el)
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "duplicate stable")

    def test_tested_control_unresolved(self):
        el = json.loads((self.d / "element-manifest.json").read_text())
        el["elements_1440"][0]["found"] = False
        el["elements_1440"][0]["selector"] = None
        el["elements_1440"][0]["selector_used"] = None
        el["elements_1440"][0]["resolution_status"] = "UNRESOLVED"
        write(self.d / "element-manifest.json", el)
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "unresolved")

    def test_pass_without_postcondition(self):
        ix = json.loads((self.d / "interaction-manifest.json").read_text())
        ix[0]["observed_postconditions"] = None
        write(self.d / "interaction-manifest.json", ix)
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "postcondition")

    def test_failed_named_as_success(self):
        ix = json.loads((self.d / "interaction-manifest.json").read_text())
        ix[0]["pass"] = False
        ix[0]["attempt_status"] = "failed"
        ix[0]["resulting_state"] = "CYCLE_EXPANDED"
        write(self.d / "interaction-manifest.json", ix)
        st = json.loads((self.d / "state-manifest.json").read_text())
        st["observed_verified_states"] = ["CYCLE_EXPANDED"]
        write(self.d / "state-manifest.json", st)
        report = self._validate_with_monkey()
        joined = " ".join(report.p0).lower()
        self.assertTrue("success" in joined or "verified" in joined, joined)

    def test_absolute_path(self):
        ix = json.loads((self.d / "interaction-manifest.json").read_text())
        ix[0]["screenshot_refs"] = ["/Users/chriswong/secret/shot.png"]
        write(self.d / "interaction-manifest.json", ix)
        report = self._validate_with_monkey()
        self.assertTrue(any("absolute" in m.lower() or "repo-relative" in m.lower() for m in report.p0), report.p0)

    def test_leaked_cookie(self):
        write(self.d / "leak.txt", "Set-Cookie: session=abc123supersecretvalue\n")
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "secret")

    def test_cardinality_not_unresolved(self):
        el = json.loads((self.d / "element-manifest.json").read_text())
        el["elements_1440"][0]["match_count"] = 4
        el["elements_1440"][0]["resolution_status"] = "RESOLVED"
        write(self.d / "element-manifest.json", el)
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "match_count")

    def test_missing_source_parity(self):
        (self.d / "source-parity.json").unlink()
        report = self._validate_with_monkey()
        self.assertTrue(any("source-parity" in m.lower() or "source-parity" in m for m in report.p0), report.p0)

    def test_incorrect_artifact_hash(self):
        art = json.loads((self.d / "artifact-manifest.json").read_text())
        art["artifacts"][0]["sha256"] = "0" * 64
        write(self.d / "artifact-manifest.json", art)
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "hash mismatch")

    def test_unsupported_schema(self):
        run = json.loads((self.d / "run-manifest.json").read_text())
        run["schema_version"] = "9.9"
        write(self.d / "run-manifest.json", run)
        report = self._validate_with_monkey()
        self.assert_p0_contains(report, "unsupported schema")


if __name__ == "__main__":
    unittest.main()
