/* ontology.js — F04-X1 WTI Live Trace client.
   Paired plain-copy asset: templates/ontology.js and site/ontology.js must stay
   byte-identical (scripts/check_template_site_sync.py).

   This file is the ONLY place a current value enters the page. The shell that
   ships to the public CDN contains none, and nothing read here is written back
   to any browser store — the response is `private, no-store` on the wire, and
   persisting it client-side would undo that in one line.

   The vocabulary rules this file follows are product law, not style:
     * no internal state names, study names or raw slugs reach the reader; every
       leg is named by its own bilingual title
     * no refutation language on a user surface. The chain's falsifiers are real
       and keep evaluating, but they are presented as what we are watching, not
       as a thesis being refuted
     * an unavailable comparison is stated as unavailable. "Nothing changed" is
       a different claim and this data cannot support it */
(function () {
  "use strict";

  var API = "/api/ontology/explorer/v1";
  var OPS = { gt: "\u003e", lt: "\u003c", gte: "\u2265", lte: "\u2264",
    eq: "=", ne: "\u2260" };
  var root = document.getElementById("ox-root");
  if (!root) return;

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  /* Both languages are always emitted; CSS decides which one paints. Building
     one language from a runtime flag would leave the other absent from the DOM
     and break the instant language toggle the rest of the site relies on. */
  function bi(pair, tag) {
    var frag = document.createDocumentFragment();
    var en = el(tag || "span", "l-en", (pair && pair.en) || "");
    var zh = el(tag || "span", "l-zh", (pair && (pair.zh || pair.en)) || "");
    frag.appendChild(en);
    frag.appendChild(zh);
    return frag;
  }

  function say(en, zh) { return bi({ en: en, zh: zh }); }

  function withAuth(headers) {
    headers = headers || {};
    if (!(window.MDXAuth && window.MDXAuth.client)) return Promise.resolve(headers);
    return window.MDXAuth.client()
      .then(function (client) { return client.auth.getSession(); })
      .then(function (result) {
        var token = result && result.data && result.data.session
          && result.data.session.access_token;
        if (token) headers.Authorization = "Bearer " + token;
        return headers;
      })
      .catch(function () { return headers; });
  }

  function gate(titleEn, titleZh, bodyEn, bodyZh, ctaEn, ctaZh, href) {
    var box = el("section", "ox-gate");
    var h = el("h2");
    h.appendChild(say(titleEn, titleZh));
    var p = el("p");
    p.appendChild(say(bodyEn, bodyZh));
    box.appendChild(h);
    box.appendChild(p);
    if (href) {
      var a = el("a", "ox-cta");
      a.href = href;
      a.appendChild(say(ctaEn, ctaZh));
      box.appendChild(a);
    }
    root.textContent = "";
    root.appendChild(box);
  }

  function legVerdict(leg) {
    if (leg.observation === "unobserved") return say("No current reading", "暂无当前读数");
    if (leg.confirmed === true) return say("Met", "已满足");
    if (leg.confirmed === false) return say("Not met", "未满足");
    return say("Unresolved", "无法判定");
  }

  function renderRail(snapshot) {
    var rail = el("ol", "rail");
    var blockingId = snapshot.first_blocking_leg && snapshot.first_blocking_leg.node_id;
    var hopByFrom = {};
    (snapshot.path.hops || []).forEach(function (hop) { hopByFrom[hop.from] = hop; });

    snapshot.path.legs.forEach(function (leg) {
      var station = el("li", "station");
      station.setAttribute("data-leg",
        leg.observation === "unobserved" ? "unobserved" : String(leg.confirmed === true));
      if (leg.node_id === blockingId) station.setAttribute("data-blocking", "1");
      var hop = hopByFrom[leg.node_id];
      /* The terminal station has no outbound hop. Saying "true" would claim a
         confirmed link that does not exist; "none" says there is nothing there. */
      station.setAttribute("data-link", hop ? String(hop.confirmed === true) : "none");

      var top = el("div", "st-top");
      top.appendChild(el("span", "st-dot"));
      top.appendChild(el("span", "st-break"));
      station.appendChild(top);

      var body = el("div", "st-body");
      body.appendChild(el("div", "st-idx", String(leg.index).padStart(2, "0")));
      var name = el("div", "st-name");
      name.appendChild(bi(leg.title));
      body.appendChild(name);
      var verdict = el("div", "st-verdict");
      verdict.appendChild(legVerdict(leg));
      body.appendChild(verdict);
      station.appendChild(body);
      rail.appendChild(station);
    });
    return rail;
  }

  function stance(snapshot) {
    var blocking = snapshot.first_blocking_leg;
    var name = blocking ? blocking.title : null;
    if (snapshot.state.code === "active") {
      return say("Every step on this path is currently met.", "该路径的每个环节当前均已满足。");
    }
    if (snapshot.state.code === "unknown") {
      return say("Part of this path has no current reading, so its state cannot be called.",
        "该路径部分环节暂无当前读数，因此无法判定其状态。");
    }
    if (snapshot.contradiction) {
      var frag = document.createDocumentFragment();
      frag.appendChild(say("The path is not running. The first step that is not met is ",
        "该路径未在运行。首个未满足的环节是"));
      frag.appendChild(bi(name));
      frag.appendChild(say(
        " — and a later step reading true does not start it.",
        "——后段环节为真并不能使其启动。"));
      return frag;
    }
    var simple = document.createDocumentFragment();
    simple.appendChild(say("The path is not running. The first step that is not met is ",
      "该路径未在运行。首个未满足的环节是"));
    simple.appendChild(bi(name));
    simple.appendChild(say(".", "。"));
    return simple;
  }

  function card(titleEn, titleZh, tone) {
    var box = el("article", "ox-card");
    if (tone) box.setAttribute("data-tone", tone);
    var h = el("h2");
    h.appendChild(say(titleEn, titleZh));
    box.appendChild(h);
    return box;
  }

  function renderWhatChanged(snapshot) {
    var box = card("What changed", "有何变化");
    var p = el("p");
    if (snapshot.what_changed.status === "recorded_transition") {
      var item = snapshot.what_changed.items[0];
      p.appendChild(say("A transition was recorded on " + (item.asof || "an earlier date") + ".",
        "已于 " + (item.asof || "较早日期") + " 记录到一次状态转换。"));
    } else {
      p.className = "ox-unavailable";
      p.appendChild(say(
        "No transition has been recorded for this path, so there is no earlier accepted "
        + "reading to compare against. The comparison is unavailable — that is not the "
        + "same as the conditions having held still.",
        "该路径尚无已记录的状态转换，因此没有可比对的既往认定读数。"
        + "比较不可用——这与条件未发生变动并非同一回事。"));
    }
    box.appendChild(p);
    return box;
  }

  function renderWhyItMatters(snapshot) {
    var box = card("Why it matters", "为何重要");
    var p = el("p");
    var first = (snapshot.why_it_matters.legs || [])[0];
    if (first && first.mechanism) {
      /* The mechanism note comes from the knowledge file and does not end in a
         full stop. Appending the caution to the same sentence ran the two
         together into one ungrammatical line, so the caution gets its own
         paragraph — which is also where it belongs in the reading order. */
      p.appendChild(bi(first.mechanism));
      box.appendChild(p);
      var caution = el("p", "ox-note");
      caution.appendChild(say("That describes how the steps are meant to connect. It is "
        + "not a measurement that they are connecting now.",
        "以上说明的是各环节理论上的连接方式，并非当前确实连通的度量。"));
      box.appendChild(caution);
      return box;
    }
    p.appendChild(say("No mechanism note is published for this path.",
      "该路径未发布机制说明。"));
    box.appendChild(p);
    return box;
  }

  function renderBlocking(snapshot) {
    var blocking = snapshot.first_blocking_leg;
    if (!blocking) {
      var okBox = card("Why it does not fire", "为何未触发");
      var okP = el("p");
      okP.appendChild(say("Every step is met; nothing is blocking this path.",
        "所有环节均已满足，该路径当前没有阻断点。"));
      okBox.appendChild(okP);
      return okBox;
    }
    var box = card("Why it does not fire", "为何未触发", "blocked");
    var p = el("p");
    var strong = el("strong");
    strong.appendChild(bi(blocking.title));
    p.appendChild(say("The path stops at step " + blocking.index + ", ", "路径止于第 "
      + blocking.index + " 环节，"));
    p.appendChild(strong);
    p.appendChild(blocking.reason === "not_observed"
      ? say(", which has no current reading.", "，该环节暂无当前读数。")
      : say(", whose condition is not met.", "，该环节条件未满足。"));
    if (snapshot.contradiction) {
      p.appendChild(say(" A later step does read true. That reading has its own causes; "
        + "it is not evidence for the earlier step.",
        "后段确有环节读数为真。该读数有其自身成因，并不构成前段环节的证据。"));
    }
    box.appendChild(p);
    return box;
  }

  function renderNextAction(snapshot) {
    var box = card("Next", "下一步", "watch");
    var p = el("p");
    p.appendChild(bi(snapshot.next_action.label));
    box.appendChild(p);
    return box;
  }

  function detail(summaryEn, summaryZh) {
    var d = el("details", "ox-detail");
    var s = el("summary");
    s.appendChild(say(summaryEn, summaryZh));
    d.appendChild(s);
    return d;
  }

  function renderLegDetail(snapshot) {
    var d = detail("Inspect each step: readings, timing and what we are watching",
      "查看各环节：读数、时间窗口与我们正在观察的条件");
    snapshot.path.legs.forEach(function (leg) {
      var box = el("div", "ox-leg");
      var h = el("h3");
      h.appendChild(bi(leg.title));
      box.appendChild(h);
      var kv = el("dl", "ox-kv");
      (leg.receipts || []).forEach(function (receipt) {
        var dt = el("dt", null, receipt.series + " · " + receipt.metric
          + (receipt.window ? " " + receipt.window + "d" : ""));
        var dd = el("dd", null, receipt.value + "  ("
          + (OPS[receipt.op] || receipt.op) + " " + receipt.threshold + ")");
        kv.appendChild(dt);
        kv.appendChild(dd);
      });
      if (!(leg.receipts || []).length) {
        var dt2 = el("dt");
        dt2.appendChild(say("Reading", "读数"));
        var dd2 = el("dd");
        dd2.appendChild(say("not published", "未发布"));
        kv.appendChild(dt2);
        kv.appendChild(dd2);
      }
      box.appendChild(kv);
      d.appendChild(box);
    });

    if ((snapshot.invalidators || []).length) {
      var watch = el("div", "ox-leg");
      var wh = el("h3");
      wh.appendChild(say("What we are watching", "我们正在观察"));
      watch.appendChild(wh);
      /* Owner notes are shown only when the composer cleared them. When it did
         not, the condition itself is shown as facts — which is what the reader
         needs anyway, and never carries refutation wording, a raw node id, or
         untranslated English into the Chinese view. */
      snapshot.invalidators.forEach(function (item) {
        var row = el("p", "ox-note");
        if (item.note) {
          row.appendChild(bi(item.note));
        } else if (item.watched && item.watched.series) {
          var w = item.watched;
          row.textContent = w.series + (w.vs ? " vs " + w.vs : "")
            + " \u00b7 " + w.metric + (w.window ? " " + w.window + "d" : "")
            + " " + (OPS[w.op] || w.op) + " " + w.value;
        } else {
          return;
        }
        watch.appendChild(row);
      });
      d.appendChild(watch);
    }
    return d;
  }

  function renderSourceDetail(snapshot) {
    var d = detail("Source and timing", "数据来源与时间");
    var kv = el("dl", "ox-kv");
    function row(labelEn, labelZh, value) {
      var dt = el("dt");
      dt.appendChild(say(labelEn, labelZh));
      kv.appendChild(dt);
      kv.appendChild(el("dd", null, value));
    }
    row("Effective as of", "数据截至", snapshot.source.asof || "—");
    row("Artifact built", "产物构建于", snapshot.source.built || "—");
    row("Read receipt", "读取凭证", (snapshot.source.source_manifest_hash || "—").slice(0, 23));
    d.appendChild(kv);

    var freshness = el("p", "ox-note");
    freshness.appendChild(bi(snapshot.source.freshness.note));
    d.appendChild(freshness);

    if (snapshot.evidence.k1.status !== "available") {
      var k1 = el("p", "ox-note");
      k1.appendChild(say(
        "Formal evidence links are not available for this reading: the current summary is "
        + "a derived view that the evidence contract does not accept as a citable source, "
        + "and no recorded transition exists to link to instead.",
        "本次读数无法提供正式证据链接：当前汇总属于派生视图，"
        + "证据契约不接受其作为可引用来源，且亦无已记录的状态转换可供引用。"));
      d.appendChild(k1);
    }
    if ((snapshot.gaps || []).length) {
      var gaps = el("p", "ox-note");
      gaps.appendChild(say("Not everything this path needs was published: "
        + snapshot.gaps.length + " item(s) are missing and are named above rather than "
        + "filled in.", "该路径所需信息并未全部发布：缺失 " + snapshot.gaps.length
        + " 项，已在上文具名列出，未作填补。"));
      d.appendChild(gaps);
    }
    return d;
  }

  function render(snapshot) {
    root.textContent = "";
    root.classList.remove("ox-skeleton");

    var hero = el("header", "ox-hero");
    var eyebrow = el("p", "ox-eyebrow");
    eyebrow.appendChild(bi(snapshot.path.title));
    hero.appendChild(eyebrow);

    var stateRow = el("div", "ox-state");
    stateRow.setAttribute("data-state", snapshot.state.code);
    var word = el("span", "ox-state-word");
    word.appendChild(bi(snapshot.state.label));
    stateRow.appendChild(word);
    var asof = el("span", "ox-asof", snapshot.source.asof || "");
    stateRow.appendChild(asof);
    hero.appendChild(stateRow);

    var stanceP = el("p", "ox-stance");
    stanceP.appendChild(stance(snapshot));
    hero.appendChild(stanceP);
    root.appendChild(hero);

    root.appendChild(renderRail(snapshot));

    var answers = el("section", "ox-answers");
    answers.appendChild(renderWhatChanged(snapshot));
    answers.appendChild(renderWhyItMatters(snapshot));
    answers.appendChild(renderBlocking(snapshot));
    answers.appendChild(renderNextAction(snapshot));
    root.appendChild(answers);

    root.appendChild(renderLegDetail(snapshot));
    root.appendChild(renderSourceDetail(snapshot));
  }

  function load() {
    withAuth({ Accept: "application/json" })
      .then(function (headers) {
        return fetch(API, {
          credentials: "same-origin",
          cache: "no-store",
          headers: headers
        });
      })
      .then(function (response) {
        if (response.status === 401) {
          gate("Sign in to see the current trace", "登录后查看当前追踪",
            "This page describes the product. The current reading is served only to a "
            + "signed-in account.",
            "本页面介绍该产品。当前读数仅向已登录账户提供。",
            "Sign in", "登录", "/?signin=1");
          return null;
        }
        if (response.status === 403) {
          gate("Included with full access", "包含于完整访问权限",
            "Your account is signed in but does not include this desk yet.",
            "您的账户已登录，但尚未包含此功能。",
            "See plans", "查看方案", "/plans.html?upgrade=1");
          return null;
        }
        if (!response.ok) {
          gate("The current reading is unavailable", "当前读数不可用",
            "An upstream source could not be read, so there is nothing current to show. "
            + "No earlier reading is shown in its place, because a stale state read as "
            + "the current one is worse than none.",
            "上游数据源无法读取，因此暂无可展示的当前内容。"
            + "此处不会以既往读数替代——将过时状态当作当前状态更糟。",
            null, null, null);
          return null;
        }
        return response.json();
      })
      .then(function (snapshot) { if (snapshot) render(snapshot); })
      .catch(function () {
        gate("The current reading is unavailable", "当前读数不可用",
          "The request for the current reading did not complete.",
          "获取当前读数的请求未能完成。", null, null, null);
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
