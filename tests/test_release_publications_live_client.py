"""Contracts for the official-event progressive-enhancement client."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "release_publications_live.js"
SITE = ROOT / "site" / "release_publications_live.js"


def test_release_publication_client_copies_are_identical():
    assert TEMPLATE.read_bytes() == SITE.read_bytes(), (
        "templates/release_publications_live.js and site/release_publications_live.js "
        "must be byte-identical"
    )


def test_release_publication_client_uses_et_lifecycle_and_safe_sources():
    driver = f"""
const fs = require("fs");
const vm = require("vm");
global.window = {{ location: {{ href: "https://www.mastermind-x.com/macro.html" }} }};
global.document = {{
  readyState: "loading",
  addEventListener: function () {{}}
}};
vm.runInThisContext(fs.readFileSync({json.dumps(str(TEMPLATE))}, "utf8"));
const api = window.__mmReleasePublicationTest;
if (!api) throw new Error("test API missing");
if (api.easternDateKey(new Date("2026-07-30T00:00:01Z")) !== "2026-07-29") {{
  throw new Error("UTC evening boundary did not remain on the ET event date");
}}
const event = {{ date: "2026-07-29", time_et: "14:00" }};
if (api.eventHasPassed(event, new Date("2026-07-29T17:59:00Z"))) {{
  throw new Error("event advanced before scheduled ET time");
}}
if (!api.eventHasPassed(event, new Date("2026-07-29T18:00:00Z"))) {{
  throw new Error("event did not advance at scheduled ET time");
}}
if (!api.safeOfficialUrl("https://www.federalreserve.gov/example")) {{
  throw new Error("official Fed URL rejected");
}}
if (api.safeOfficialUrl("https://federalreserve.gov.evil.example/payload")) {{
  throw new Error("lookalike source URL accepted");
}}
const coldStartRow = {{
  source_released_at: "2026-07-29T18:00:15Z",
  detected_at: "2026-07-30T01:00:00Z"
}};
if (api.officialReleaseTime(coldStartRow) !== "14:00 ET") {{
  throw new Error("official release time was replaced by cold-start detection time");
}}
const freshNow = new Date("2026-07-29T18:03:00Z");
if (!api.payloadIsFresh({{ built: "2026-07-29T18:01:00Z" }}, freshNow)) {{
  throw new Error("fresh sidecar was rejected");
}}
if (api.payloadIsFresh({{ built: "2026-07-29T17:59:00Z" }}, freshNow)) {{
  throw new Error("stale sidecar retained live status");
}}
const radar = api.radarState(
  [{{ type: "FOMC", actual: {{ headline_en: "Old result" }} }}],
  [{{ type: "GDP" }}]
);
if (radar.kind !== "awaiting" || radar.en.indexOf("GDP") < 0) {{
  throw new Error("active verification did not outrank an older publication");
}}
const sameDayPublications = [
  {{
    event_id: "GDP:2026-07-30:08:30",
    type: "GDP",
    date: "2026-07-30",
    data_ready: true,
    actual: {{ headline_en: "GDP rose 2.1%" }}
  }},
  {{
    event_id: "PCE:2026-07-30:08:30",
    type: "PCE",
    date: "2026-07-30",
    data_ready: true,
    actual: {{ headline_en: "Core PCE rose 0.2%" }}
  }}
];
const sameDayAwaiting = [{{
  event_id: "CLAIMS:2026-07-30:08:30",
  type: "CLAIMS",
  date: "2026-07-30"
}}];
const sameDayGroup = api.activeReleaseGroup(sameDayPublications, sameDayAwaiting);
if (!sameDayGroup || sameDayGroup.total !== 3 ||
    sameDayGroup.verified.length !== 2 || sameDayGroup.awaiting.length !== 1) {{
  throw new Error("same-day release lifecycle was not grouped");
}}
const sameDaySummary = api.releaseGroupSummary(sameDayGroup);
["GDP", "PCE", "CLAIMS", "2 verified results", "1 awaiting official source"].forEach(
  function (part) {{
    if (sameDaySummary.en.indexOf(part) < 0) {{
      throw new Error("same-day summary omitted " + part);
    }}
  }}
);
if (sameDaySummary.zh.indexOf("2 个结果已核验") < 0 ||
    sameDaySummary.zh.indexOf("1 个正在等待官方来源") < 0) {{
  throw new Error("same-day summary is not bilingual");
}}
const groupedRadar = api.radarState(sameDayPublications, sameDayAwaiting);
if (groupedRadar.kind !== "awaiting" || groupedRadar.count !== 3 ||
    groupedRadar.en.indexOf("GDP") < 0 ||
    groupedRadar.en.indexOf("PCE") < 0 ||
    groupedRadar.en.indexOf("CLAIMS") < 0) {{
  throw new Error("radar banner collapsed a same-day group to one release");
}}
const priorDayPlusGroup = api.activeReleaseGroup(
  [{{
    event_id: "FOMC:2026-07-29:14:00",
    type: "FOMC",
    date: "2026-07-29",
    data_ready: true
  }}].concat(sameDayPublications),
  sameDayAwaiting
);
if (priorDayPlusGroup.total !== 3 || priorDayPlusGroup.names.indexOf("FOMC") >= 0) {{
  throw new Error("same-day summary included an older retained release");
}}
const singleRadar = api.radarState(
  [{{ type: "GDP", date: "2026-07-30",
      actual: {{ headline_en: "GDP rose 2.1%" }} }}],
  []
);
if (singleRadar.en !== "GDP rose 2.1%" || singleRadar.count) {{
  throw new Error("single-release banner output changed");
}}
const latestSingleRadar = api.radarState(
  [{{ type: "GDP", date: "2026-07-30",
      actual: {{ headline_en: "GDP rose 2.1%" }} }}],
  [{{ type: "FOMC", date: "2026-07-29" }}]
);
if (latestSingleRadar.kind !== "published" ||
    latestSingleRadar.en !== "GDP rose 2.1%") {{
  throw new Error("older retained verification displaced the latest release date");
}}
const duplicateTypeRows = api.awaitingEvents({{
  events: [
    {{
      event_id: "CLAIMS:2026-07-30:08:30:A",
      type: "CLAIMS",
      date: "2026-07-30",
      time_et: "08:30",
      status: "awaiting_publication"
    }},
    {{
      event_id: "CLAIMS:2026-07-30:08:30:B",
      type: "CLAIMS",
      date: "2026-07-30",
      time_et: "08:30",
      status: "awaiting_publication"
    }}
  ]
}}, new Date("2026-07-30T13:00:00Z"), {{
  "event:CLAIMS:2026-07-30:08:30:A": true,
  "CLAIMS:2026-07-30": true
}});
if (duplicateTypeRows.length !== 1 ||
    duplicateTypeRows[0].event_id !== "CLAIMS:2026-07-30:08:30:B") {{
  throw new Error("event identity collapsed distinct same-type releases");
}}
const overnight = api.awaitingEvents({{
  events: [{{
    type: "FOMC",
    date: "2026-07-29",
    time_et: "14:00",
    status: "published_unparsed"
  }}]
}}, new Date("2026-07-30T05:00:00Z"), {{}});
if (overnight.length !== 1) {{
  throw new Error("prior-day FOMC verification disappeared after ET midnight");
}}
const unparsedPayload = {{
  publications: [{{
    type: "FOMC",
    date: "2026-07-29",
    status: "published_unparsed",
    data_ready: false,
    detected_at: "2026-07-30T00:50:00Z"
  }}],
  events: [{{
    type: "FOMC",
    date: "2026-07-29",
    time_et: "14:00",
    status: "published_unparsed",
    data_ready: false
  }}]
}};
const detectedRows = api.recentPublications(
  unparsedPayload, new Date("2026-07-30T01:00:00Z"));
if (detectedRows.length !== 1 || detectedRows[0].status !== "published_unparsed") {{
  throw new Error("published-but-unparsed event was not routed as detected");
}}
if (api.awaitingEvents(
    unparsedPayload,
    new Date("2026-07-30T01:00:00Z"),
    {{ "FOMC:2026-07-29": true }}
  ).length !== 0) {{
  throw new Error("detected publication was mislabeled as awaiting release");
}}
if (api.radarState(detectedRows, []).kind !== "published") {{
  throw new Error("detected publication did not reach publication UI state");
}}
const detectedAfter25h = api.recentPublications(
  unparsedPayload, new Date("2026-07-31T02:00:00Z"));
if (detectedAfter25h.length !== 1) {{
  throw new Error("unparsed publication disappeared after the 24h result window");
}}
if (api.awaitingEvents(
    unparsedPayload,
    new Date("2026-07-31T02:00:00Z"),
    {{ "FOMC:2026-07-29": true }}
  ).length !== 0) {{
  throw new Error("T+25h detected publication regressed to awaiting release");
}}
const expiringPayload = {{
  publications: [{{
    type: "FOMC",
    date: "2026-07-29",
    status: "published",
    detected_at: "2026-07-29T06:00:00Z"
  }}]
}};
if (api.recentPublications(
    expiringPayload, new Date("2026-07-30T05:00:00Z")).length !== 1) {{
  throw new Error("T+23h verified result expired too early");
}}
if (api.recentPublications(
    expiringPayload, new Date("2026-07-30T07:00:00Z")).length !== 0) {{
  throw new Error("T+25h verified result remained active");
}}
if (api.trackPrimaryState(true) || !api.trackPrimaryState(false)) {{
  throw new Error("active-to-expired primary transition was not detected");
}}
if (api.rowMatchesText({{ type: "FOMC", label: "FOMC rate decision" }},
    "GDP and PCE release today")) {{
  throw new Error("retained FOMC result matched a different current event");
}}
if (!api.rowMatchesText({{ type: "FOMC", label: "FOMC rate decision" }},
    "FOMC rate decision today")) {{
  throw new Error("matching FOMC surface was not recognized");
}}
api.notePollFailure(freshNow);
if (api.freshness() !== "stale") {{
  throw new Error("poll failure did not downgrade an uninitialized live feed");
}}
"""
    result = subprocess.run(
        ["node", "-e", driver],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_release_publication_client_patches_all_event_surfaces():
    source = TEMPLATE.read_text()
    for contract in (
        "America/New_York",
        "mx-live-event-outcomes",
        ".mx5-dlg-cal-card",
        ".mx5-tl-item",
        ".mx5-events-sub",
        '.wnx-card[href="#dlg-events"]',
        "awaiting official source",
        "Official result · live",
        '.ms-sig[data-ms-dlg="dlg-events"]',
        ".mx5-action-label",
        ".aib2-watch-row",
        ".aib2-cat-read",
        "Update delayed",
        "published_unparsed",
        "Official publication detected — result verification underway",
        "publication detected — verified facts are being extracted",
        'data-live-event-id',
        "FOMC (?:decision|statement)",
        "activeReleaseGroup",
        "patchEventsFaceGroup",
        "patchWhereNextGroup",
        "Same-day releases",
        "official results · live",
    ):
        assert contract in source
    assert "toISOString().slice(0, 10)" not in source


def test_release_publication_client_covers_actual_stale_macro_surfaces():
    """Pin selectors against a stable fixture from the rendered incident page."""
    page = (ROOT / "tests" / "fixtures" / "macro_fomc_stale_surfaces.html").read_text()
    source = TEMPLATE.read_text()
    stale_fixture_markers = {
        'data-ms-dlg="dlg-events"': '.ms-sig[data-ms-dlg="dlg-events"]',
        "FOMC rate decision: expect noise": ".mx5-action-label",
        "FOMC (Jul 29)": ".aib2-watch-row",
        "The immediate hurdle is the FOMC decision": ".aib2-cat-read",
        "Major event on deck": ".mx5-alert-item.warn",
        "FOMC rate decision 07-29": ".v2chip",
    }
    for stale_text, runtime_selector in stale_fixture_markers.items():
        assert stale_text in page, f"expected fixture marker missing: {stale_text}"
        assert runtime_selector in source, (
            f"live client does not supersede {stale_text!r}"
        )
    current_page = (ROOT / "site" / "macro.html").read_text()
    assert 'id="sx-events-v2"' in current_page
    assert 'id="dlg-events"' in current_page
    assert "release_publications_live.js" in current_page


def test_new_live_labels_have_bilingual_pairs():
    source = TEMPLATE.read_text()
    for english, chinese in (
        ("Official source ↗", "官方来源 ↗"),
        ("Official statement ↗", "官方声明 ↗"),
        ("Detected ", "检测于 "),
        ("Last checked ", "上次检查 "),
        ("Awaiting official release", "等待官方发布"),
        ("Update delayed", "更新延迟"),
        ("Last verified result", "上次核验结果"),
        ("No active live result", "当前无实时结果"),
        ("Scheduled time passed · verifying official source", "预定时间已过 · 正在核验官方来源"),
    ):
        assert english in source
        assert chinese in source


def test_release_publication_client_uses_current_immutable_asset_hash():
    expected = hashlib.sha256(SITE.read_bytes()).hexdigest()[:8]
    for page_name in ("macro.html", "us_stocks.html"):
        page = (ROOT / "site" / page_name).read_text()
        match = re.search(r"release_publications_live\.js\?v=([0-9a-f]{8})", page)
        assert match, f"{page_name} does not version the live event client"
        assert match.group(1) == expected, (
            f"{page_name} points at a stale immutable client hash"
        )

    caddy = (ROOT / "app" / "deploy" / "Caddyfile").read_text()
    versioned = caddy[caddy.index("@public_versioned {") :]
    versioned = versioned[: versioned.index("}")]
    assert "/release_publications_live.js" in versioned
