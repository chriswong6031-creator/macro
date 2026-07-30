/* Live official-event lifecycle for the hybrid dashboard.
 *
 * The nightly HTML remains the resilient shell. This module hydrates only the
 * time-sensitive event islands from the VPS-owned official-source sidecar.
 * Verified facts are display-only here; canonical vintages and model scoring
 * remain nightly writers.
 */
(function () {
  "use strict";
  if (window.__mmReleasePublicationLive) return;
  window.__mmReleasePublicationLive = true;

  var ENDPOINT = "live/release_publications.json";
  var POLL_MS = 60000;
  var STALE_AFTER_MS = 3 * 60 * 1000;
  var OFFICIAL_HOSTS = [
    "federalreserve.gov",
    "bls.gov",
    "bea.gov",
    "dol.gov",
    "census.gov",
    "treasury.gov"
  ];
  var timer = null;
  var lastSuccessfulPollAt = 0;
  var missedPolls = 0;
  var feedFreshness = "unknown";
  var hadLivePrimary = false;

  function list(nodes) {
    return Array.prototype.slice.call(nodes || []);
  }

  function easternParts(value) {
    var formatter = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23"
    });
    var parts = {};
    formatter.formatToParts(value || new Date()).forEach(function (part) {
      if (part.type !== "literal") parts[part.type] = part.value;
    });
    return parts;
  }

  function easternDateKey(value) {
    var parts = easternParts(value);
    return parts.year + "-" + parts.month + "-" + parts.day;
  }

  function easternTime(value) {
    if (!value) return "";
    var parsed = new Date(value);
    if (isNaN(parsed.getTime())) return "";
    var parts = easternParts(parsed);
    return parts.hour + ":" + parts.minute + " ET";
  }

  function officialReleaseTime(row) {
    return easternTime(row && row.source_released_at);
  }

  function safeOfficialUrl(value) {
    if (!value) return "";
    try {
      var parsed = new URL(value, window.location.href);
      var host = parsed.hostname.toLowerCase();
      var allowed = OFFICIAL_HOSTS.some(function (suffix) {
        return host === suffix || host.slice(-(suffix.length + 1)) === "." + suffix;
      });
      return parsed.protocol === "https:" && allowed ? parsed.href : "";
    } catch (error) {
      return "";
    }
  }

  function languagePair(className, en, zh) {
    var wrap = document.createElement("div");
    if (className) wrap.className = className;
    var english = document.createElement("span");
    english.className = "l-en";
    english.textContent = en || "";
    var chinese = document.createElement("span");
    chinese.className = "l-zh";
    chinese.textContent = zh || en || "";
    wrap.appendChild(english);
    wrap.appendChild(chinese);
    return wrap;
  }

  function setPair(container, en, zh) {
    if (!container) return;
    var english = container.querySelector(".l-en");
    var chinese = container.querySelector(".l-zh");
    if (!english && !chinese) {
      container.textContent = "";
      english = document.createElement("span");
      english.className = "l-en";
      chinese = document.createElement("span");
      chinese.className = "l-zh";
      container.appendChild(english);
      container.appendChild(chinese);
    }
    if (english) english.textContent = en || "";
    if (chinese) chinese.textContent = zh || en || "";
  }

  function ensureStyles() {
    if (document.getElementById("mx-live-events-css")) return;
    var style = document.createElement("style");
    style.id = "mx-live-events-css";
    style.textContent =
      ":root{--mx-live-ok:#28c98b}" +
      "[data-theme=\"light\"]{--mx-live-ok:#087b4c}" +
      "#mx-live-event-outcomes{display:flex;flex-direction:column;gap:10px;margin:0 0 16px}" +
      ".mx-live-event-card{padding:13px 14px;border:1px solid color-mix(in srgb,#16a36a 38%,var(--line));" +
      "border-radius:12px;background:color-mix(in srgb,#16a36a 7%,var(--panel2));box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}" +
      ".mx-live-event-card.awaiting{border-color:color-mix(in srgb,#d99016 45%,var(--line));" +
      "background:color-mix(in srgb,#d99016 7%,var(--panel2))}" +
      ".mx-live-event-top{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:7px}" +
      ".mx-live-event-pill{font-size:10px;font-weight:750;letter-spacing:.055em;text-transform:uppercase;" +
      "color:var(--mx-live-ok);background:color-mix(in srgb,#16a36a 13%,transparent);border:1px solid color-mix(in srgb,#16a36a 32%,transparent);" +
      "border-radius:999px;padding:3px 7px}" +
      ".awaiting .mx-live-event-pill{color:#a76400;background:color-mix(in srgb,#d99016 12%,transparent);" +
      "border-color:color-mix(in srgb,#d99016 30%,transparent)}" +
      ".mx-live-event-asof{font-size:10px;color:var(--ink-3,var(--muted))}" +
      ".mx-live-event-headline{font-size:15px;font-weight:750;color:var(--ink-1,var(--text));line-height:1.3;margin-bottom:4px}" +
      ".mx-live-event-summary{font-size:11.5px;color:var(--ink-2,var(--muted));line-height:1.5}" +
      ".mx-live-event-source{display:inline-flex;margin-top:8px;font-size:10.5px;font-weight:650;color:var(--link,#2563eb);text-decoration:none}" +
      ".mx-live-event-source:hover{text-decoration:underline}" +
      ".mx5-dlg-cal-card.is-published{border-color:color-mix(in srgb,#16a36a 55%,var(--line))!important;" +
      "background:color-mix(in srgb,#16a36a 7%,var(--panel2))!important}" +
      ".mx5-dlg-cal-card.is-awaiting{border-color:color-mix(in srgb,#d99016 50%,var(--line))!important}" +
      ".mx5-dlg-cal-badge.live-out{color:var(--mx-live-ok)!important;background:color-mix(in srgb,#16a36a 13%,transparent)!important;" +
      "border-color:color-mix(in srgb,#16a36a 32%,transparent)!important}" +
      ".mx5-dlg-cal-badge.live-wait{color:#a76400!important;background:color-mix(in srgb,#d99016 12%,transparent)!important;" +
      "border-color:color-mix(in srgb,#d99016 30%,transparent)!important}" +
      ".mx5-tl-badge.live-out{color:var(--mx-live-ok)!important;background:color-mix(in srgb,#16a36a 13%,transparent)!important;" +
      "border-color:color-mix(in srgb,#16a36a 32%,transparent)!important}" +
      ".mx5-tl-badge.live-wait{color:#a76400!important;background:color-mix(in srgb,#d99016 12%,transparent)!important;" +
      "border-color:color-mix(in srgb,#d99016 30%,transparent)!important}" +
      ".mx5-tl-dot.live-out-dot{background:#16a36a!important;box-shadow:0 0 0 3px color-mix(in srgb,#16a36a 18%,transparent)!important}" +
      ".mx-live-cal-outcome{font-size:11px;font-weight:700;line-height:1.4;color:var(--mx-live-ok);margin-top:7px}" +
      ".mx-live-cal-outcome.awaiting{color:#a76400}" +
      ".mx-live-cal-source{display:inline-block;margin-top:5px;font-size:10px;color:var(--link,#2563eb);text-decoration:none}" +
      ".mx-live-fed-result{margin:7px 0 8px;padding:8px 9px;border-radius:8px;border:1px solid color-mix(in srgb,#16a36a 32%,var(--line));" +
      "background:color-mix(in srgb,#16a36a 7%,transparent);font-size:11px;font-weight:700;line-height:1.4;color:var(--mx-live-ok)}" +
      ".mx-live-fed-result.awaiting{color:#a76400;border-color:color-mix(in srgb,#d99016 30%,var(--line));" +
      "background:color-mix(in srgb,#d99016 7%,transparent)}" +
      ".mx-live-fed-result.stale{color:var(--ink-3,var(--muted));border-style:dashed}" +
      "[data-release-live-freshness=\"stale\"] .mx-live-event-pill{color:var(--ink-3,var(--muted));" +
      "border-color:var(--line);background:var(--panel2)}" +
      ".mx-live-event-face .mx5-events-sub{color:var(--mx-live-ok)!important;font-weight:700}" +
      ".mx-live-resolved{opacity:.9}" +
      "@media(max-width:640px){.mx-live-event-top{align-items:flex-start;flex-direction:column;gap:4px}}";
    (document.head || document.documentElement).appendChild(style);
  }

  function ensureOutcomePanel() {
    var body = document.querySelector("#dlg-events .mx5-dlg-body");
    if (!body) return null;
    var panel = document.getElementById("mx-live-event-outcomes");
    if (panel) return panel;
    panel = document.createElement("div");
    panel.id = "mx-live-event-outcomes";
    panel.setAttribute("aria-live", "polite");
    body.insertBefore(panel, body.firstChild);
    return panel;
  }

  function appendSource(card, row) {
    var href = safeOfficialUrl(row.source_url || (row.actual || {}).source_url);
    if (!href) return;
    var source = document.createElement("a");
    source.className = "mx-live-event-source";
    source.href = href;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    setPair(source, "Official source ↗", "官方来源 ↗");
    source.setAttribute("aria-label", "Open official source");
    card.appendChild(source);
  }

  function renderPublicationCard(row) {
    var actual = row.actual || {};
    var verified = row.data_ready === true;
    var card = document.createElement("section");
    card.className = "mx-live-event-card published " +
      (verified ? "verified" : "unparsed");
    card.setAttribute("data-live-event-id", row.event_id || "");
    card.setAttribute("data-live-verified", verified ? "true" : "false");
    var top = document.createElement("div");
    top.className = "mx-live-event-top";
    top.appendChild(languagePair(
      "mx-live-event-pill",
      verified ? "Official result · live" : "Official publication · extracting",
      verified ? "官方结果 · 实时" : "官方发布 · 正在提取"
    ));
    var asof = document.createElement("span");
    asof.className = "mx-live-event-asof";
    setPair(
      asof,
      "Detected " + (easternTime(row.detected_at) || "live"),
      "检测于 " + (easternTime(row.detected_at) || "实时")
    );
    top.appendChild(asof);
    card.appendChild(top);
    card.appendChild(languagePair(
      "mx-live-event-headline",
      actual.headline_en || ((row.label || row.type) + " publication detected"),
      actual.headline_zh || ((row.label_zh || row.label || row.type) + "官方发布已检测")
    ));
    card.appendChild(languagePair(
      "mx-live-event-summary",
      actual.summary_en || "Official publication detected. Verified values are being extracted.",
      actual.summary_zh || "已检测到官方发布，正在提取并核验数据。"
    ));
    appendSource(card, row);
    return card;
  }

  function renderAwaitingCard(row, payload) {
    var card = document.createElement("section");
    card.className = "mx-live-event-card awaiting";
    card.setAttribute("data-live-event-id", row.event_id || "");
    var top = document.createElement("div");
    top.className = "mx-live-event-top";
    top.appendChild(languagePair(
      "mx-live-event-pill",
      "Verifying official source",
      "正在核验官方来源"
    ));
    var asof = document.createElement("span");
    asof.className = "mx-live-event-asof";
    setPair(
      asof,
      "Last checked " + (easternTime(payload.built) || "now"),
      "上次检查 " + (easternTime(payload.built) || "刚刚")
    );
    top.appendChild(asof);
    card.appendChild(top);
    card.appendChild(languagePair(
      "mx-live-event-headline",
      (row.label || row.type) + " · scheduled time passed",
      (row.label_zh || row.label || row.type) + " · 预定发布时间已过"
    ));
    card.appendChild(languagePair(
      "mx-live-event-summary",
      "Awaiting the official release. This event is no longer shown as upcoming.",
      "正在等待官方发布；该事件不再显示为“即将发布”。"
    ));
    return card;
  }

  function cardsFor(row) {
    return list(document.querySelectorAll("#dlg-events .mx5-dlg-cal-card")).filter(
      function (card) {
        return card.getAttribute("data-cal-date") === row.date &&
          (card.getAttribute("data-cal-type") || "").toUpperCase() ===
            String(row.type || "").toUpperCase();
      }
    );
  }

  function patchCalendar(row, published) {
    var verified = published && row.data_ready === true;
    cardsFor(row).forEach(function (card) {
      card.classList.remove("is-published", "is-awaiting");
      card.classList.add(verified ? "is-published" : "is-awaiting");
      var time = card.querySelector(".mx5-dlg-cal-time");
      if (time) {
        var released = officialReleaseTime(row);
        setPair(
          time,
          published ?
            (released ? "Released " + released : "Official publication detected") :
            "Awaiting official release",
          published ?
            (released ? "发布于 " + released : "已检测到官方发布") :
            "等待官方发布"
        );
      }
      var badge = card.querySelector(".mx5-dlg-cal-badge");
      if (badge) {
        badge.classList.remove("high", "med", "low", "live-out", "live-wait");
        badge.classList.add(verified ? "live-out" : "live-wait");
        setPair(
          badge,
          verified ? "OUT" : "VERIFYING",
          verified ? "已发布" : "核验中"
        );
      }
      var outcome = card.querySelector(".mx-live-cal-outcome");
      if (!outcome) {
        outcome = languagePair("mx-live-cal-outcome", "", "");
        card.appendChild(outcome);
      }
      outcome.classList.toggle("awaiting", !verified);
      var actual = row.actual || {};
      setPair(
        outcome,
        published ?
          (actual.headline_en || "Official publication detected · extracting verified facts") :
          "Scheduled time passed · awaiting official source",
        published ?
          (actual.headline_zh || "已检测到官方发布 · 正在提取核验信息") :
          "预定时间已过 · 正在等待官方来源"
      );
      var oldSource = card.querySelector(".mx-live-cal-source");
      if (oldSource) oldSource.parentNode.removeChild(oldSource);
      var href = published && safeOfficialUrl(row.source_url || actual.source_url);
      if (href) {
        var source = document.createElement("a");
        source.className = "mx-live-cal-source";
        source.href = href;
        source.target = "_blank";
        source.rel = "noopener noreferrer";
        setPair(source, "Official statement ↗", "官方声明 ↗");
        source.addEventListener("click", function (event) {
          event.stopPropagation();
        });
        card.appendChild(source);
      }
    });
  }

  function matchingCalendarIndex(row) {
    var cards = list(document.querySelectorAll("#dlg-events .mx5-dlg-cal-card"));
    for (var index = 0; index < cards.length; index += 1) {
      if (cards[index].getAttribute("data-cal-date") === row.date &&
          (cards[index].getAttribute("data-cal-type") || "").toUpperCase() ===
            String(row.type || "").toUpperCase()) return index;
    }
    return -1;
  }

  function patchTimeline(row, published) {
    var verified = published && row.data_ready === true;
    var index = matchingCalendarIndex(row);
    var timeline = list(document.querySelectorAll("#sx-events-v2 .mx5-tl-item"));
    if (index < 0 || index >= timeline.length) return;
    var item = timeline[index];
    item.classList.add("mx-live-resolved");
    var badge = item.querySelector(".mx5-tl-badge");
    if (badge) {
      badge.classList.remove("high", "med", "low", "live-out", "live-wait");
      badge.classList.add(verified ? "live-out" : "live-wait");
      setPair(badge, verified ? "OUT" : "VERIFY", verified ? "已发布" : "核验");
    }
    var dot = item.querySelector(".mx5-tl-dot");
    if (dot) dot.classList.toggle("live-out-dot", verified);
    if (verified && row.actual) {
      var name = item.querySelector(".mx5-tl-name");
      setPair(
        name,
        row.actual.action === "hold" ? "Fed held" : (row.actual.headline_en || row.type),
        row.actual.action === "hold" ? "美联储维持" : (row.actual.headline_zh || row.label_zh)
      );
    }
  }

  function patchEventsFace(row, published) {
    var face = document.querySelector("#sx-events-v2 .mx5-card-face");
    if (!face) return;
    face.classList.add("mx-live-event-face");
    face.setAttribute("data-live-state", published ?
      (row.data_ready === true ? "verified" : "detected") : "awaiting");
    var title = face.querySelector(".mx5-card-title");
    var subline = face.querySelector(".mx5-events-sub");
    var badge = face.querySelector(".mx5-card-badge");
    var actual = row.actual || {};
    if (published) {
      var verified = row.data_ready === true;
      setPair(
        title,
        verified ? "Latest official result" : "Official publication detected",
        verified ? "最新官方结果" : "已检测到官方发布"
      );
      setPair(
        subline,
        actual.headline_en || ((row.label || row.type) + " · extracting verified values"),
        actual.headline_zh || ((row.label_zh || row.label || row.type) + " · 正在提取核验值")
      );
      setPair(badge, verified ? "Live" : "Parsing", verified ? "实时" : "提取中");
    } else {
      setPair(title, "Live event status", "实时事件状态");
      setPair(subline, (row.label || row.type) + " · verifying official source",
        (row.label_zh || row.label || row.type) + " · 正在核验官方来源");
      setPair(badge, "Checking", "核验中");
    }
  }

  function patchWhereNext(row, published) {
    var card = document.querySelector('.wnx-card[href="#dlg-events"]');
    if (!card) return;
    var actual = row.actual || {};
    var verified = row.data_ready === true;
    setPair(
      card.querySelector(".wnx-kicker"),
      published ?
        (verified ? "Latest official result" : "Official publication detected") :
        "Live event status",
      published ? (verified ? "最新官方结果" : "已检测到官方发布") : "实时事件状态"
    );
    setPair(
      card.querySelector(".wnx-state"),
      published ? (actual.headline_en || ((row.label || row.type) + " released")) :
        ((row.label || row.type) + " · verifying"),
      published ? (actual.headline_zh || ((row.label_zh || row.label || row.type) + "已发布")) :
        ((row.label_zh || row.label || row.type) + " · 核验中")
    );
    setPair(
      card.querySelector(".wnx-line"),
      published ? (actual.summary_en || "Official source detected.") :
        "Scheduled time passed · awaiting official source",
      published ? (actual.summary_zh || "已检测到官方来源。") :
        "预定时间已过 · 正在等待官方来源"
    );
    setPair(card.querySelector(".wnx-go"), "Open live details", "查看实时详情");
  }

  function uniqueEventNames(rows) {
    var seen = {};
    return (rows || []).map(function (row) {
      return String(row.type || row.label || "").toUpperCase();
    }).filter(function (name) {
      if (!name || seen[name]) return false;
      seen[name] = true;
      return true;
    });
  }

  function shortEventDate(value, chinese) {
    var parts = String(value || "").split("-");
    var month = Number(parts[1]);
    var day = Number(parts[2]);
    if (!month || !day) return String(value || "");
    if (chinese) return month + "月" + day + "日";
    var months = [
      "Jan", "Feb", "Mar", "Apr", "May", "Jun",
      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ];
    return months[month - 1] + " " + day;
  }

  function activeReleaseGroup(publications, awaiting) {
    var rows = (publications || []).concat(awaiting || []).filter(function (row) {
      return Boolean(row && row.date);
    });
    if (!rows.length) return null;
    var dates = rows.map(function (row) { return row.date; }).sort();
    var date = dates[dates.length - 1];
    var groupPublications = (publications || []).filter(function (row) {
      return row.date === date;
    });
    var groupAwaiting = (awaiting || []).filter(function (row) {
      return row.date === date;
    });
    var verified = groupPublications.filter(function (row) {
      return row.data_ready === true;
    });
    var extracting = groupPublications.filter(function (row) {
      return row.data_ready !== true;
    });
    return {
      date: date,
      publications: groupPublications,
      awaiting: groupAwaiting,
      verified: verified,
      extracting: extracting,
      total: groupPublications.length + groupAwaiting.length,
      names: uniqueEventNames(groupPublications.concat(groupAwaiting))
    };
  }

  function releaseGroupSummary(group) {
    if (!group) return null;
    var verified = group.verified.length;
    var extracting = group.extracting.length;
    var awaiting = group.awaiting.length;
    var enParts = [];
    var zhParts = [];
    if (verified) {
      enParts.push(verified + " verified " + (verified === 1 ? "result" : "results"));
      zhParts.push(verified + " 个结果已核验");
    }
    if (extracting) {
      enParts.push(extracting + " " + (extracting === 1 ? "publication" : "publications") +
        " extracting");
      zhParts.push(extracting + " 个官方发布正在提取");
    }
    if (awaiting) {
      enParts.push(awaiting + " awaiting official " +
        (awaiting === 1 ? "source" : "sources"));
      zhParts.push(awaiting + " 个正在等待官方来源");
    }
    var namesEn = group.names.join(", ");
    var namesZh = group.names.join("、");
    return {
      en: shortEventDate(group.date, false) + " · " + enParts.join(", ") +
        (namesEn ? " — " + namesEn : ""),
      zh: shortEventDate(group.date, true) + " · " + zhParts.join("、") +
        (namesZh ? " — " + namesZh : ""),
      badgeEn: verified && !extracting && !awaiting ?
        verified + " live" :
        ([verified ? verified + " live" : "",
          extracting ? extracting + " parsing" : "",
          awaiting ? awaiting + " checking" : ""].filter(Boolean).join(" · ")),
      badgeZh: verified && !extracting && !awaiting ?
        verified + " 个实时" :
        ([verified ? verified + " 个已核验" : "",
          extracting ? extracting + " 个提取中" : "",
          awaiting ? awaiting + " 个核验中" : ""].filter(Boolean).join(" · "))
    };
  }

  function patchEventsFaceGroup(group) {
    var face = document.querySelector("#sx-events-v2 .mx5-card-face");
    if (!face) return;
    var summary = releaseGroupSummary(group);
    face.classList.add("mx-live-event-face");
    face.setAttribute("data-live-state",
      group.awaiting.length || group.extracting.length ? "detected" : "verified");
    setPair(
      face.querySelector(".mx5-card-title"),
      group.awaiting.length || group.extracting.length ?
        "Live release status" : group.verified.length + " official results · live",
      group.awaiting.length || group.extracting.length ?
        "实时发布状态" : group.verified.length + " 个官方结果 · 实时"
    );
    setPair(face.querySelector(".mx5-events-sub"), summary.en, summary.zh);
    setPair(face.querySelector(".mx5-card-badge"), summary.badgeEn, summary.badgeZh);
  }

  function patchWhereNextGroup(group) {
    var card = document.querySelector('.wnx-card[href="#dlg-events"]');
    if (!card) return;
    var summary = releaseGroupSummary(group);
    setPair(card.querySelector(".wnx-kicker"), "Same-day releases", "同日发布");
    setPair(
      card.querySelector(".wnx-state"),
      group.awaiting.length || group.extracting.length ?
        "Live release status" : group.verified.length + " official results · live",
      group.awaiting.length || group.extracting.length ?
        "实时发布状态" : group.verified.length + " 个官方结果 · 实时"
    );
    setPair(card.querySelector(".wnx-line"), summary.en, summary.zh);
    setPair(card.querySelector(".wnx-go"), "Open all live details", "查看全部实时详情");
  }

  function patchFedPath(row, published) {
    if (String(row.type || "").toUpperCase() !== "FOMC") return;
    var actual = row.actual || {};
    var verified = published && row.data_ready === true;
    var face = document.querySelector("#sx-v5-fed .mx5-card");
    if (face) {
      var result = face.querySelector(".mx-live-fed-result");
      if (!result) {
        result = languagePair("mx-live-fed-result", "", "");
        var title = face.querySelector(".mx5-card-title");
        if (title && title.parentNode) title.parentNode.insertBefore(result, title.nextSibling);
        else face.insertBefore(result, face.firstChild);
      }
      result.classList.toggle("awaiting", !verified);
      setPair(
        result,
        published ?
          (actual.headline_en || "Official FOMC statement detected · extracting decision") :
          "FOMC scheduled time passed · verifying official source",
        published ? (actual.headline_zh || "已检测到 FOMC 官方声明 · 正在提取决议") :
          "FOMC 预定时间已过 · 正在核验官方来源"
      );
    }

    var dialogBody = document.querySelector("#dlg-fed .mx5-dlg-body");
    if (!dialogBody) return;
    var dialogResult = document.getElementById("mx-live-fed-decision");
    if (dialogResult && dialogResult.parentNode) {
      dialogResult.parentNode.removeChild(dialogResult);
    }
    dialogResult = published ?
      renderPublicationCard(row) :
      renderAwaitingCard(row, { built: "" });
    dialogResult.id = "mx-live-fed-decision";
    dialogResult.style.marginBottom = "16px";
    dialogBody.insertBefore(dialogResult, dialogBody.firstChild);
  }

  function patchActionPlan(row, verified) {
    var actual = row.actual || {};
    // The stance word belongs to the SENTENCE, not to a chip. It used to ship in
    // a `.mx5-action-verb` span that has no CSS rule anywhere in the repo, so the
    // span was an inline no-op with no trailing space and the row rendered
    // "ResultGDP released — see verified outcome." / "结果GDP…". Every other
    // "What To Do Now" row is a plain one-line sentence, so fold the word in and
    // drop the span rather than inventing a chip style for one live row.
    var stanceEn = verified ? "Result: " : "Status: ";
    var stanceZh = verified ? "结果：" : "状态：";
    // Only the FALLBACK differs by state; a supplied summary is used either way,
    // as before. The verified fallback now matches the wording the generic .l-en
    // sweep below already uses — "Result: … facts are being extracted" asserted
    // a result and then denied having one.
    var bodyEn = actual.summary_en || ((row.label || row.type) + (verified ?
      " released — see verified outcome." :
      " publication detected — verified facts are being extracted."));
    var bodyZh = actual.summary_zh || ((row.label_zh || row.label || row.type) +
      (verified ? "已发布 — 查看核验结果。" : "官方发布已检测 — 正在提取核验信息。"));
    list(document.querySelectorAll(".mx5-action-label")).forEach(function (label) {
      var text = String(label.textContent || "").toLowerCase();
      if (text.indexOf(String(row.type || "").toLowerCase()) < 0 &&
          text.indexOf(String(row.label || "").toLowerCase()) < 0) return;
      label.textContent = "";
      var english = document.createElement("span");
      english.className = "l-en";
      english.appendChild(document.createTextNode(stanceEn + bodyEn));
      var chinese = document.createElement("span");
      chinese.className = "l-zh";
      chinese.appendChild(document.createTextNode(stanceZh + bodyZh));
      label.appendChild(english);
      label.appendChild(chinese);
      // Ownership sentinel for the generic .l-en sweep in patchProspectiveCopy.
      // The retired span was load-bearing there — it was how that sweep knew to
      // leave these rows alone. Without a replacement, any summary carrying a
      // prospective word ("GDP rose 2.1% today") makes the sweep overwrite this
      // row with its own generic fallback, on this poll and every later one.
      label.setAttribute("data-live-action-plan", "1");
      label.classList.add("mx-live-resolved");
    });
  }

  function rowMatchesText(row, value) {
    var text = String(value || "").toLowerCase();
    var eventType = String(row.type || "").toLowerCase();
    var label = String(row.label || "").toLowerCase();
    return Boolean((eventType && text.indexOf(eventType) >= 0) ||
      (label && text.indexOf(label) >= 0));
  }

  function patchMarketStateEvent(row, verified) {
    var actual = row.actual || {};
    list(document.querySelectorAll('.ms-sig[data-ms-dlg="dlg-events"]'))
      .forEach(function (signal) {
        if (!rowMatchesText(row, signal.textContent)) return;
        setPair(
          signal.querySelector(".ms-sig-title"),
          verified ? "Official release published — outcome verified" :
            "Official publication detected — result verification underway",
          verified ? "官方发布已公布 — 结果已核验" :
            "已检测到官方发布 — 正在核验结果"
        );
        setPair(
          signal.querySelector(".ms-sig-detail"),
          actual.summary_en || ((row.label || row.type) +
            " publication detected; verified facts are being extracted."),
          actual.summary_zh || ((row.label_zh || row.label || row.type) +
            "官方发布已检测；正在提取核验信息。")
        );
        setPair(
          signal.querySelector(".ms-sig-what"),
          verified ?
            "The scheduled event is resolved. Use the official result above; the pre-release volatility warning is no longer active." :
            "The scheduled time has passed and the official publication is present. The pre-release warning is retired while facts are verified.",
          verified ?
            "该预定事件已结束。请以上述官方结果为准；发布前的波动警告不再有效。" :
            "预定时间已过且官方发布已出现。发布前警告已结束，结果信息正在核验。"
        );
        var edge = signal.querySelector(".ms-sig-edge");
        if (edge) edge.textContent = "";
        setPair(
          edge,
          verified ?
            "Verified official result — assess the market reaction, not the stale pre-release setup." :
            "Official document detected — do not infer the result until deterministic extraction completes.",
          verified ?
            "官方结果已核验 — 现在应评估市场反应，而非过时的发布前情景。" :
            "已检测到官方文件 — 确定性提取完成前请勿推断结果。"
        );
        setPair(signal.querySelector(".ms-sig-jump"), "View result →", "查看结果 →");
        signal.classList.remove("sev-warn");
        signal.classList.add("sev-info", "mx-live-resolved");
      });
    list(document.querySelectorAll(".v2chip")).forEach(function (chip) {
      var text = String(chip.textContent || "").toLowerCase();
      if (text.indexOf(String(row.type || "").toLowerCase()) < 0) return;
      setPair(
        chip,
        (row.label || row.type) + " · OUT",
        (row.label_zh || row.type || row.label) + " · 已发布"
      );
      chip.classList.add("mx-live-resolved");
    });
  }

  function patchAIBrief(row, verified) {
    if (String(row.type || "").toUpperCase() !== "FOMC") return;
    var actual = row.actual || {};
    list(document.querySelectorAll(".aib2-watch-row")).forEach(function (watch) {
      if (String(watch.textContent || "").toLowerCase().indexOf(
        String(row.type || "").toLowerCase()
      ) < 0) return;
      setPair(
        watch.querySelector(".aib2-watch-body"),
        verified ?
          "FOMC result: " + (actual.summary_en || "official decision released.") :
          "FOMC statement detected; decision facts are being verified.",
        verified ?
          "FOMC 结果：" + (actual.summary_zh || "官方决议已发布。") :
          "已检测到 FOMC 声明；正在核验决议信息。"
      );
      watch.classList.add("mx-live-resolved");
    });
    list(document.querySelectorAll(".aib2-cat")).forEach(function (catalyst) {
      if (String(catalyst.textContent || "").toLowerCase().indexOf(
        String(row.type || "").toLowerCase()
      ) < 0) return;
      setPair(
        catalyst,
        (row.date || "") + (verified ? " · FOMC result · OUT" :
          " · FOMC statement · VERIFYING"),
        (row.date || "") + (verified ? " · FOMC 结果 · 已发布" :
          " · FOMC 声明 · 核验中")
      );
      catalyst.classList.add("mx-live-resolved");
    });
    var catalystRead = document.querySelector(".aib2-cat-read");
    if (catalystRead && (
      /FOMC (?:decision|statement)/i.test(catalystRead.textContent || "") ||
      catalystRead.getAttribute("data-live-event-id") === String(row.event_id || "")
    )) {
      setPair(
        catalystRead,
        verified ?
          "The FOMC decision is out: " +
            (actual.summary_en || "see the verified official result.") +
            " Review the live Events calendar for the next scheduled catalysts." :
          "The official FOMC statement is present, but its decision facts are still being verified. Review the live Events calendar for status.",
        verified ?
          "FOMC 决议已发布：" +
            (actual.summary_zh || "请查看已核验的官方结果。") +
            " 后续预定催化剂请查看实时事件日历。" :
          "FOMC 官方声明已出现，但决议信息仍在核验中。请查看实时事件日历了解状态。"
      );
      catalystRead.setAttribute("data-live-event-id", String(row.event_id || ""));
      catalystRead.classList.add("mx-live-resolved");
    }
  }

  function patchAlertSurfaces(row, verified) {
    var actual = row.actual || {};
    list(document.querySelectorAll(".mx5-alert-item.warn")).forEach(function (alert) {
      if (!rowMatchesText(row, alert.textContent)) return;
      setPair(
        alert.querySelector(".mx5-alert-title"),
        verified ? "Official release published — outcome verified" :
          "Official publication detected — result verification underway",
        verified ? "官方发布已公布 — 结果已核验" :
          "已检测到官方发布 — 正在核验结果"
      );
      setPair(
        alert.querySelector(".mx5-alert-detail"),
        actual.summary_en || ((row.label || row.type) +
          " publication detected; verified facts are being extracted."),
        actual.summary_zh || ((row.label_zh || row.label || row.type) +
          "官方发布已检测；正在提取核验信息。")
      );
      alert.classList.add("mx-live-resolved");
    });

    var dialog = document.getElementById("dlg-news");
    if (!dialog) return;
    function updateDialogContainer(container) {
      var englishNodes = list(container.querySelectorAll(".l-en"));
      var titleEnglish = englishNodes.filter(function (node) {
        return /major event on deck|official (?:release|publication)/.test(
          String(node.textContent || "").toLowerCase()
        );
      })[0];
      if (titleEnglish) {
        setPair(
          titleEnglish.parentNode,
          verified ? "Official release published — outcome verified" :
            "Official publication detected — result verification underway",
          verified ? "官方发布已公布 — 结果已核验" :
            "已检测到官方发布 — 正在核验结果"
        );
      }
      var detailEnglish = englishNodes.filter(function (node) {
        return node !== titleEnglish && rowMatchesText(row, node.textContent);
      })[0];
      if (detailEnglish) {
        setPair(
          detailEnglish.parentNode,
          actual.summary_en || ((row.label || row.type) +
            " publication detected; verified facts are being extracted."),
          actual.summary_zh || ((row.label_zh || row.label || row.type) +
            "官方发布已检测；正在提取核验信息。")
        );
      }
      container.setAttribute("data-live-event-container", "true");
      container.setAttribute("data-live-event-id", String(row.event_id || ""));
      container.classList.add("mx-live-resolved");
    }
    list(dialog.querySelectorAll("[data-live-event-container]")).forEach(
      function (container) {
        if (container.getAttribute("data-live-event-id") ===
            String(row.event_id || "")) updateDialogContainer(container);
      }
    );
    list(dialog.querySelectorAll(".l-en")).forEach(function (english) {
      if (!/major event on deck|event-risk window/.test(
        String(english.textContent || "").toLowerCase()
      )) return;
      var container = english.parentNode;
      for (var depth = 0; container && container !== dialog && depth < 6; depth += 1) {
        if (rowMatchesText(row, container.textContent)) {
          var titleEnglish = list(container.querySelectorAll(".l-en")).filter(
            function (node) {
              return /major event on deck/.test(
                String(node.textContent || "").toLowerCase()
              );
            }
          )[0];
          if (titleEnglish) {
            updateDialogContainer(container);
          }
          break;
        }
        container = container.parentNode;
      }
    });
  }

  function patchProspectiveCopy(row, published) {
    if (!published) return;
    var actual = row.actual || {};
    var verified = row.data_ready === true;
    patchActionPlan(row, verified);
    patchMarketStateEvent(row, verified);
    patchAIBrief(row, verified);
    patchAlertSurfaces(row, verified);
    var key = String(row.type || "").toLowerCase();
    var label = String(row.label || "").toLowerCase();
    list(document.querySelectorAll(".l-en")).forEach(function (english) {
      var text = String(english.textContent || "");
      var lower = text.toLowerCase();
      var namesEvent = (key && lower.indexOf(key) >= 0) ||
        (label && lower.indexOf(label) >= 0);
      var isProspective = /today|ahead|expect noise|big print|event-risk window|rate decision:/.test(lower);
      var parent = english.parentNode;
      var isTagged = parent && parent.getAttribute &&
        parent.getAttribute("data-live-event-id") === String(row.event_id || "");
      // patchActionPlan owns the "What To Do Now" rows and has already written a
      // stance line there; this sweep must not flatten it back to the generic
      // fallback. The signal used to be the presence of the row's
      // `.mx5-action-verb` span — retired with the CSS-less chip, so the marker
      // patchActionPlan sets on the label carries it instead.
      var ownedByActionPlan = parent && parent.getAttribute &&
        parent.getAttribute("data-live-action-plan") === "1";
      if (!namesEvent || (!isProspective && !isTagged) || ownedByActionPlan) return;
      english.textContent = verified ?
        (actual.summary_en ||
          ((row.label || row.type) + " released — see verified outcome.")) :
        ((row.label || row.type) +
          " publication detected — verified facts are being extracted.");
      var chinese = parent && parent.querySelector ? parent.querySelector(".l-zh") : null;
      if (chinese) {
        chinese.textContent = verified ?
          (actual.summary_zh ||
            ((row.label_zh || row.label || row.type) + "已发布 — 查看核验结果。")) :
          ((row.label_zh || row.label || row.type) +
            "官方发布已检测 — 正在提取核验信息。");
      }
      if (parent && parent.classList) {
        parent.classList.add("mx-live-resolved");
        parent.setAttribute("data-live-event-id", String(row.event_id || ""));
      }
    });
    var alertsBadge = document.querySelector("#sx-news-v2 .mx5-card-badge");
    if (alertsBadge) {
      setPair(
        alertsBadge,
        verified ? "Live update" : "Verifying",
        verified ? "实时更新" : "核验中"
      );
    }
  }

  function ensureRadarBanner() {
    var radar = document.getElementById("release-radar") || document.getElementById("rr-inline");
    if (!radar) return null;
    var banner = document.getElementById("rr-live-publication");
    if (banner) return banner;
    banner = document.createElement("div");
    banner.id = "rr-live-publication";
    banner.hidden = true;
    banner.style.cssText =
      "margin:0 0 10px;padding:8px 10px;border:1px solid var(--line);" +
      "border-radius:9px;background:var(--panel2);font-size:11px;line-height:1.45";
    radar.insertBefore(banner, radar.firstChild);
    return banner;
  }

  function eventHasPassed(row, now) {
    var today = easternDateKey(now);
    if (row.date < today) return true;
    if (row.date > today) return false;
    var clock = String(row.time_et || "00:00").split(":");
    var parts = easternParts(now);
    return (Number(parts.hour) * 60 + Number(parts.minute)) >=
      (Number(clock[0]) * 60 + Number(clock[1] || 0));
  }

  function recentPublications(payload, now) {
    var cutoff = now.getTime() - (24 * 60 * 60 * 1000);
    return (payload.publications || []).filter(function (row) {
      if (["published", "published_unparsed"].indexOf(row.status) < 0) return false;
      var detected = new Date(row.detected_at || row.date + "T23:59:59Z").getTime();
      return !isNaN(detected) &&
        (row.status === "published_unparsed" || detected >= cutoff);
    }).sort(function (left, right) {
      return new Date(left.detected_at || 0).getTime() -
        new Date(right.detected_at || 0).getTime();
    });
  }

  function awaitingEvents(payload, now, publishedKeys) {
    var rows = payload.events || payload.due || payload.upcoming || [];
    return rows.filter(function (row) {
      var key = row.event_id ?
        "event:" + row.event_id :
        row.type + ":" + row.date;
      var lifecycleRequiresAttention = [
        "awaiting_publication",
        "published_unparsed",
        "verification_delayed"
      ].indexOf(String(row.status || "")) >= 0;
      return !publishedKeys[key] && (
        lifecycleRequiresAttention ||
        (row.date === easternDateKey(now) && eventHasPassed(row, now))
      );
    });
  }

  function payloadIsFresh(payload, now) {
    var built = new Date(payload && payload.built || "").getTime();
    var current = (now || new Date()).getTime();
    return !isNaN(built) && built <= current + POLL_MS &&
      current - built <= STALE_AFTER_MS;
  }

  function radarState(publications, awaiting) {
    var group = activeReleaseGroup(publications, awaiting);
    if (group && group.total > 1) {
      var summary = releaseGroupSummary(group);
      return {
        kind: group.awaiting.length ? "awaiting" : "published",
        en: summary.en,
        zh: summary.zh,
        count: group.total,
        date: group.date
      };
    }
    if (group) {
      publications = group.publications;
      awaiting = group.awaiting;
    }
    if (awaiting.length) {
      return {
        kind: "awaiting",
        en: "Scheduled time passed · verifying official source — " +
          awaiting.map(function (row) { return row.type; }).join(", "),
        zh: "预定时间已过 · 正在核验官方来源 — " +
          awaiting.map(function (row) { return row.type; }).join("、")
      };
    }
    if (publications.length) {
      var latest = publications[publications.length - 1];
      var actual = latest.actual || {};
      return {
        kind: "published",
        en: actual.headline_en || ("Official publication detected · " + latest.type),
        zh: actual.headline_zh || ("已检测到官方发布 · " + latest.type)
      };
    }
    return { kind: "empty", en: "", zh: "" };
  }

  function markFeedFresh() {
    feedFreshness = "fresh";
    if (document.documentElement) {
      document.documentElement.setAttribute("data-release-live-freshness", "fresh");
    }
    list(document.querySelectorAll(".mx-live-fed-result.stale")).forEach(
      function (node) { node.classList.remove("stale"); }
    );
  }

  function markFeedStale() {
    feedFreshness = "stale";
    if (document.documentElement) {
      document.documentElement.setAttribute("data-release-live-freshness", "stale");
    }
    if (!document.querySelector || !document.querySelectorAll) return;
    var face = document.querySelector("#sx-events-v2 .mx5-card-face.mx-live-event-face");
    if (face) {
      var faceState = face.getAttribute("data-live-state") || "awaiting";
      setPair(
        face.querySelector(".mx5-card-title"),
        faceState === "verified" ? "Last verified result" :
          (faceState === "detected" ? "Last detected publication" :
            "Event status unavailable"),
        faceState === "verified" ? "上次核验结果" :
          (faceState === "detected" ? "上次检测到的官方发布" :
            "事件状态暂不可用")
      );
      setPair(face.querySelector(".mx5-card-badge"), "Update delayed", "更新延迟");
    }
    list(document.querySelectorAll(".mx-live-event-card.published .mx-live-event-pill"))
      .forEach(function (pill) {
        var card = pill.closest(".mx-live-event-card");
        var verified = card &&
          card.getAttribute("data-live-verified") === "true";
        setPair(
          pill,
          verified ? "Official result · last verified" :
            "Official publication · verification delayed",
          verified ? "官方结果 · 上次核验" : "官方发布 · 核验延迟"
        );
      });
    list(document.querySelectorAll(".mx-live-event-card.awaiting .mx-live-event-pill"))
      .forEach(function (pill) {
        setPair(pill, "Event status · update delayed", "事件状态 · 更新延迟");
      });
    list(document.querySelectorAll(".mx-live-fed-result")).forEach(
      function (node) { node.classList.add("stale"); }
    );
    var alertsBadge = document.querySelector("#sx-news-v2 .mx5-card-badge");
    if (alertsBadge) setPair(alertsBadge, "Update delayed", "更新延迟");
    var banner = ensureRadarBanner();
    if (banner) {
      setPair(
        banner,
        "Live event feed delayed · showing the last known state",
        "实时事件数据延迟 · 当前显示上次已知状态"
      );
      banner.hidden = false;
    }
  }

  function notePollFailure(now) {
    missedPolls += 1;
    var current = (now || new Date()).getTime();
    if (!lastSuccessfulPollAt || missedPolls >= 3 ||
        current - lastSuccessfulPollAt >= STALE_AFTER_MS) {
      markFeedStale();
    }
    return feedFreshness;
  }

  function trackPrimaryState(hasPrimary) {
    var expired = hadLivePrimary && !hasPrimary;
    hadLivePrimary = Boolean(hasPrimary);
    return expired;
  }

  function expireLiveState() {
    var face = document.querySelector("#sx-events-v2 .mx5-card-face");
    if (face) {
      face.classList.remove("mx-live-event-face");
      face.removeAttribute("data-live-state");
      setPair(face.querySelector(".mx5-card-title"), "Upcoming events", "近期事件");
      setPair(face.querySelector(".mx5-events-sub"),
        "No active live result · open the current schedule",
        "当前无实时结果 · 打开最新日历");
      setPair(face.querySelector(".mx5-card-badge"), "Schedule", "日历");
    }
    var whereNext = document.querySelector('.wnx-card[href="#dlg-events"]');
    if (whereNext) {
      setPair(whereNext.querySelector(".wnx-kicker"), "Event calendar", "事件日历");
      setPair(whereNext.querySelector(".wnx-state"), "No active live result", "当前无实时结果");
      setPair(whereNext.querySelector(".wnx-line"), "Open the current schedule", "打开最新日历");
      setPair(whereNext.querySelector(".wnx-go"), "Open events", "查看事件");
    }
    list(document.querySelectorAll(".mx-live-fed-result, #mx-live-fed-decision"))
      .forEach(function (node) {
        if (node.parentNode) node.parentNode.removeChild(node);
      });
    list(document.querySelectorAll(".mx5-dlg-cal-card.is-published, .mx5-dlg-cal-card.is-awaiting"))
      .forEach(function (card) {
        card.classList.remove("is-published", "is-awaiting");
        var badge = card.querySelector(".mx5-dlg-cal-badge");
        if (badge) {
          badge.classList.remove("live-out", "live-wait");
          setPair(badge, "PAST", "已结束");
        }
        list(card.querySelectorAll(".mx-live-cal-outcome, .mx-live-cal-source"))
          .forEach(function (node) {
            if (node.parentNode) node.parentNode.removeChild(node);
          });
      });
    list(document.querySelectorAll(".mx5-tl-item.mx-live-resolved")).forEach(
      function (item) {
        item.classList.remove("mx-live-resolved");
        var badge = item.querySelector(".mx5-tl-badge");
        if (badge) {
          badge.classList.remove("live-out", "live-wait");
          setPair(badge, "PAST", "已结束");
        }
        var dot = item.querySelector(".mx5-tl-dot");
        if (dot) dot.classList.remove("live-out-dot");
      }
    );
    var alertsBadge = document.querySelector("#sx-news-v2 .mx5-card-badge");
    if (alertsBadge) setPair(alertsBadge, "Last verified", "上次核验");
  }

  function render(payload, nowValue) {
    var now = nowValue instanceof Date ? nowValue : new Date();
    if (!payload || !Array.isArray(payload.publications || []) ||
        !payloadIsFresh(payload, now)) {
      notePollFailure(now);
      return false;
    }
    lastSuccessfulPollAt = now.getTime();
    missedPolls = 0;
    markFeedFresh();
    ensureStyles();
    var publications = recentPublications(payload, now);
    var publishedKeys = {};
    publications.forEach(function (row) {
      publishedKeys[row.type + ":" + row.date] = true;
      if (row.event_id) publishedKeys["event:" + row.event_id] = true;
    });
    var awaiting = awaitingEvents(payload, now, publishedKeys);
    var panel = ensureOutcomePanel();
    if (panel) {
      panel.textContent = "";
      publications.forEach(function (row) {
        panel.appendChild(renderPublicationCard(row));
      });
      awaiting.forEach(function (row) {
        panel.appendChild(renderAwaitingCard(row, payload));
      });
      panel.hidden = publications.length === 0 && awaiting.length === 0;
    }

    publications.forEach(function (row) {
      patchCalendar(row, true);
      patchTimeline(row, true);
      patchFedPath(row, true);
      patchProspectiveCopy(row, true);
    });
    awaiting.forEach(function (row) {
      patchCalendar(row, false);
      patchTimeline(row, false);
      patchFedPath(row, false);
    });
    var group = activeReleaseGroup(publications, awaiting);
    var primary = group ?
      (group.awaiting[0] || group.publications[group.publications.length - 1]) :
      null;
    if (group && group.total > 1) {
      patchEventsFaceGroup(group);
      patchWhereNextGroup(group);
    } else if (primary) {
      var isPublished = group ?
        (group.awaiting.length === 0 && group.publications.length > 0) :
        (awaiting.length === 0 && publications.length > 0);
      patchEventsFace(primary, isPublished);
      patchWhereNext(primary, isPublished);
    }
    if (trackPrimaryState(Boolean(group || primary))) expireLiveState();

    var banner = ensureRadarBanner();
    if (banner) {
      var radar = radarState(publications, awaiting);
      setPair(banner, radar.en, radar.zh);
      banner.hidden = radar.kind === "empty";
    }
    return true;
  }

  function poll() {
    fetch(ENDPOINT, { cache: "no-store", credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(render)
      .catch(function () {
        /* Keep the baked dashboard usable, but never leave a false green "Live". */
        notePollFailure();
      });
  }

  function start() {
    poll();
    if (!timer) timer = window.setInterval(poll, POLL_MS);
  }

  window.__mmReleasePublicationTest = {
    easternDateKey: easternDateKey,
    officialReleaseTime: officialReleaseTime,
    eventHasPassed: eventHasPassed,
    safeOfficialUrl: safeOfficialUrl,
    payloadIsFresh: payloadIsFresh,
    recentPublications: recentPublications,
    awaitingEvents: awaitingEvents,
    rowMatchesText: rowMatchesText,
    activeReleaseGroup: activeReleaseGroup,
    releaseGroupSummary: releaseGroupSummary,
    radarState: radarState,
    trackPrimaryState: trackPrimaryState,
    patchActionPlan: patchActionPlan,
    patchProspectiveCopy: patchProspectiveCopy,
    notePollFailure: notePollFailure,
    freshness: function () { return feedFreshness; },
    render: render
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
