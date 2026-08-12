from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "browser" / "momoedge_capture"
NATIVE_MANIFEST = ROOT / "ops" / "native_messaging" / "com.mastermind.optionsnbbocohort.momoedge_observe.json"


def _extension_id(public_key: str) -> str:
    digest = hashlib.sha256(base64.b64decode(public_key)).digest()[:16].hex()
    return digest.translate(str.maketrans("0123456789abcdef", "abcdefghijklmnop"))


def test_manifest_is_origin_scoped_and_has_stable_public_key() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) == {"alarms", "nativeMessaging", "scripting"}
    assert manifest["host_permissions"] == ["https://momoedge.ai/*"]
    assert _extension_id(manifest["key"]) == "hgplipfmplcbbkjmhaijacaanmiljfdi"
    native = json.loads(NATIVE_MANIFEST.read_text())
    assert native["allowed_origins"] == [
        "chrome-extension://hgplipfmplcbbkjmhaijacaanmiljfdi/"
    ]


def test_extension_has_no_credential_or_broad_browser_api_access() -> None:
    source = "\n".join(path.read_text() for path in EXTENSION.glob("*.js"))
    forbidden = [
        "document.cookie",
        "chrome.cookies",
        "localStorage",
        "sessionStorage",
        "chrome.storage",
        "webRequest",
        "debugger",
        ".headers",
        "response.headers",
        "request.headers",
        "postMessage(",
    ]
    for marker in forbidden:
        assert marker not in source
    assert 'world: "MAIN"' in source
    assert "window.fetch = originalFetch" in source
    assert "response.clone()" in source
    assert "getReader()" in source
    assert "arrayBuffer()" not in source
    assert "coverage_eligible: false" in source


def test_service_worker_freezes_grid_lateness_and_restart_gap_behavior() -> None:
    source = (EXTENSION / "service_worker.js").read_text()
    projection = (EXTENSION / "projection.js").read_text()
    assert "cadenceMs: 300000" in projection
    assert "periodInMinutes: 5" in source
    assert "chrome.alarms.get(MOMOEDGE_OBSERVE.alarmName" in source
    assert "chrome.runtime.lastError || existing" in source
    assert "Date.now() - scheduledMs > 120000" in source
    assert 'unavailablePageCapture("alarm_late")' in source
    assert "chrome.runtime.onStartup.addListener(armMomoEdgeAlarm)" in source
    assert "!tab.discarded" in source


def test_source_cutoff_contract_is_explicit_and_never_claims_complete_ny_day() -> None:
    source = (EXTENSION / "page_capture.js").read_text()
    runbook = (ROOT / "docs" / "runbooks" / "MOMOEDGE_BROWSER_COMPANION.md").read_text()
    assert 'zonedParts(nowMs, "America/New_York")' in source
    assert 'current.month >= 3 && current.month <= 11 ? "-04:00" : "-05:00"' in source
    assert "signals_active_plus_source_today_closed_fresh_fetch/v1" in source
    assert "complete_new_york_day_proven: false" in source
    assert "8e50889204ca52795e4c9b7bfd51758f93c585427e103c6b3e65827c1812f553" in runbook


@pytest.mark.parametrize("filename", ["page_capture.js", "projection.js", "service_worker.js"])
def test_extension_javascript_parses(filename: str) -> None:
    subprocess.run(["node", "--check", str(EXTENSION / filename)], check=True)


def _run_page_capture(
    *,
    now_ms: int,
    cutoff: str,
    body: str,
    status: int = 200,
    fetch_count: int = 1,
    retain_cached: bool = False,
    origin: str = "https://pojiqfeemksvocnaellu.supabase.co",
    extra_query: str = "",
    throwing_headers_getter: bool = False,
    page_origin: str = "https://momoedge.ai",
    page_path: str = "/terminal.html",
) -> dict[str, object]:
    page_source = json.dumps((EXTENSION / "page_capture.js").read_text())
    script = f"""
const vm = require('vm');
const {{ performance }} = require('perf_hooks');
const {{ webcrypto }} = require('crypto');
global.performance = performance;
global.crypto = webcrypto;
global.btoa = (value) => Buffer.from(value, 'binary').toString('base64');
global.Date.now = () => {now_ms};
const body = require('fs').readFileSync(0, 'utf8');
let receivedCache = null;
const originalFetch = async (_input, requestInit) => {{
  receivedCache = requestInit && requestInit.cache;
  return new Response(body, {{ status: {status} }});
}};
const runtime = {{ SIGNALS: [{{id:'cached', _isFallback:false}}] }};
global.window = {{
  location: {{
    href: {json.dumps(page_origin + page_path)},
    origin: {json.dumps(page_origin)},
    pathname: {json.dumps(page_path)},
  }},
  fetch: originalFetch,
}};
runtime.loadSignals = async () => {{
  for (let i = 0; i < {fetch_count}; i += 1) {{
    const scope = '(is_active.eq.true,and(is_active.eq.false,closed_at.gte.{cutoff}))';
    const url = {json.dumps(origin)} + '/rest/v1/signals?or=' + encodeURIComponent(scope) + '&order=sort_order.asc' + {json.dumps(extra_query)};
    let requestInit;
    if ({str(throwing_headers_getter).lower()}) {{
      requestInit = {{}};
      Object.defineProperty(requestInit, 'headers', {{
        enumerable: true,
        get: () => {{ throw new Error('headers getter must remain opaque'); }},
      }});
    }}
    const response = await window.fetch(url, requestInit);
    if (response.ok && !{str(retain_cached).lower()}) {{
      runtime.SIGNALS = await response.json();
      window.SIGNALS = runtime.SIGNALS;
    }}
  }}
}};
window.MomoEdge = {{ signals: runtime }};
vm.runInThisContext({page_source});
captureFreshMomoEdgeSignals().then((result) => {{
  process.stdout.write(JSON.stringify({{ result, restored: window.fetch === originalFetch, receivedCache }}));
}}).catch(() => process.exit(2));
"""
    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        input=body,
        text=True,
        timeout=10,
        env={"PATH": os.environ["PATH"], "TZ": "America/Vancouver"},
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize(
    ("now_ms", "cutoff"),
    [
        (1784131200000, "2026-07-15T00:00:00-04:00"),
        (1768492800000, "2026-01-15T00:00:00-05:00"),
        (1772985600000, "2026-03-08T00:00:00-04:00"),
        (1793548800000, "2026-11-01T00:00:00-04:00"),
    ],
)
def test_vancouver_host_accepts_exact_source_cutoff_including_transition_counterexamples(
    now_ms: int, cutoff: str
) -> None:
    body = json.dumps(
        [
            {
                "id": "s1",
                "is_active": True,
                "created_at": "2026-01-01T15:00:00.000Z",
                "asset": "AAPL",
            }
        ],
        separators=(",", ":"),
    )
    observed = _run_page_capture(now_ms=now_ms, cutoff=cutoff, body=body)
    assert observed["restored"] is True
    assert observed["result"]["disposition"] == "fresh_response"
    assert base64.b64decode(observed["result"]["capture"]["response_body_base64"]) == body.encode()


def test_cached_runtime_without_matched_fetch_is_unavailable() -> None:
    observed = _run_page_capture(
        now_ms=1784131200000,
        cutoff="2026-07-15T00:00:00-04:00",
        body="[]",
        fetch_count=0,
        retain_cached=True,
    )
    assert observed["result"]["reason"] == "fresh_request_not_observed"
    assert observed["restored"] is True


def test_page_bridge_rejects_nonterminal_path_before_fetch() -> None:
    observed = _run_page_capture(
        now_ms=1784131200000,
        cutoff="2026-07-15T00:00:00-04:00",
        body="[]",
        page_path="/pricing",
    )
    assert observed["result"]["reason"] == "page_origin_path_mismatch"


def test_request_init_headers_remain_opaque_while_cache_policy_is_overridden() -> None:
    observed = _run_page_capture(
        now_ms=1784131200000,
        cutoff="2026-07-15T00:00:00-04:00",
        body='[{"id":"s1","is_active":true,"created_at":"2026-07-15T14:00:00Z"}]',
        throwing_headers_getter=True,
    )
    assert observed["result"]["disposition"] == "fresh_response"
    assert observed["receivedCache"] == "no-store"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"origin": "https://momoedge.ai"},
        {"extra_query": "&limit=100"},
        {"cutoff": "2026-07-15T04:00:00.000Z"},
    ],
)
def test_wrong_origin_query_or_cutoff_cannot_prove_fresh_response(kwargs: dict[str, str]) -> None:
    arguments = {
        "now_ms": 1784131200000,
        "cutoff": "2026-07-15T00:00:00-04:00",
        "body": '[{"id":"s1","is_active":true,"created_at":"2026-07-15T14:00:00Z"}]',
    }
    arguments.update(kwargs)
    observed = _run_page_capture(**arguments)
    assert observed["result"]["reason"] == "fresh_request_not_observed"


def test_http_error_multiple_fetch_sensitive_and_oversize_fail_closed() -> None:
    now_ms = 1784131200000
    cutoff = "2026-07-15T00:00:00-04:00"
    valid = '[{"id":"s1","is_active":true,"created_at":"2026-07-15T14:00:00Z"}]'
    http = _run_page_capture(now_ms=now_ms, cutoff=cutoff, body=valid, status=401, retain_cached=True)
    assert http["result"] == {
        "schema": "options.momoedge_browser_page_capture/v1",
        "disposition": "unavailable",
        "reason": "http_error",
        "capture": None,
    }
    multiple = _run_page_capture(now_ms=now_ms, cutoff=cutoff, body=valid, fetch_count=2)
    assert multiple["result"]["reason"] == "multiple_matching_responses"
    sensitive = '[{"id":"s1","is_active":true,"created_at":"2026-07-15T14:00:00Z","nested":{"session_id":"x"}}]'
    rejected = _run_page_capture(now_ms=now_ms, cutoff=cutoff, body=sensitive)
    assert rejected["result"]["reason"] == "sensitive_key_rejected"
    token_like = '[{"id":"s1","is_active":true,"created_at":"2026-07-15T14:00:00Z","nested":{"access_token_value":"x"}}]'
    rejected = _run_page_capture(now_ms=now_ms, cutoff=cutoff, body=token_like)
    assert rejected["result"]["reason"] == "sensitive_key_rejected"
    numeric_bomb = '[{"id":1e400,"is_active":true,"created_at":"2026-07-15T14:00:00Z"}]'
    rejected = _run_page_capture(now_ms=now_ms, cutoff=cutoff, body=numeric_bomb)
    assert rejected["result"]["reason"] == "invalid_response_shape"
    oversized = _run_page_capture(now_ms=now_ms, cutoff=cutoff, body='["' + ("x" * 600001) + '"]')
    assert oversized["result"]["reason"] == "response_too_large"


def test_service_worker_validates_exact_ack_retries_identical_envelope_and_filters_tabs() -> None:
    projection = json.dumps((EXTENSION / "projection.js").read_text())
    page = json.dumps((EXTENSION / "page_capture.js").read_text())
    worker = (EXTENSION / "service_worker.js").read_text().replace(
        'importScripts("projection.js", "page_capture.js");', ""
    )
    worker_source = json.dumps(worker)
    valid_ack = {
        "schema": "options.momoedge_browser_native_ack/v1",
        "accepted": True,
        "created": True,
        "disposition": "unavailable",
        "reason": "no_matching_tab",
        "journal_sha256": "a" * 64,
        "raw_sha256": None,
        "coverage_eligible": False,
    }
    script = f"""
const vm = require('vm');
let sends = [];
let callbacks = 0;
let alarmCreates = 0;
global.chrome = {{
  alarms: {{
    get: (_name, callback) => callback({{name:'already-armed'}}),
    create: () => {{ alarmCreates += 1; }},
    onAlarm: {{ addListener: () => {{}} }},
  }},
  runtime: {{
    lastError: null,
    onInstalled: {{ addListener: () => {{}} }},
    onStartup: {{ addListener: () => {{}} }},
    sendNativeMessage: (_host, observation, callback) => {{
      sends.push(JSON.stringify(observation));
      callbacks += 1;
      callback(callbacks === 1 ? {{accepted:true}} : {json.dumps(valid_ack)});
    }},
  }},
  tabs: {{ query: async () => [{{id:9,discarded:false}},{{id:3,discarded:true}},{{id:5,discarded:false}}] }},
  scripting: {{ executeScript: async () => [] }},
}};
vm.runInThisContext({projection});
vm.runInThisContext({page});
vm.runInThisContext({worker_source});
Promise.all([sendObservationToNativeHost({{slot:'same'}}), selectTerminalTab()]).then(([ack, tab]) => {{
  process.stdout.write(JSON.stringify({{
    ack,
    tabId:tab.id,
    sends,
    extraAccepted:isAcceptedMomoEdgeAck({{...ack, extra:true}}),
    nullJournalAccepted:isAcceptedMomoEdgeAck({{...ack, journal_sha256:null}}),
    contradictoryFreshAccepted:isAcceptedMomoEdgeAck({{...ack, disposition:'fresh_response', reason:null, raw_sha256:null}}),
    contradictoryUnavailableAccepted:isAcceptedMomoEdgeAck({{...ack, raw_sha256:'b'.repeat(64)}}),
    alarmCreates,
  }}));
}});
"""
    completed = subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True, timeout=10
    )
    result = json.loads(completed.stdout)
    assert result["ack"] == valid_ack
    assert result["sends"] == ['{"slot":"same"}', '{"slot":"same"}']
    assert result["tabId"] == 5
    assert result["extraAccepted"] is False
    assert result["nullJournalAccepted"] is False
    assert result["contradictoryFreshAccepted"] is False
    assert result["contradictoryUnavailableAccepted"] is False
    assert result["alarmCreates"] == 0
