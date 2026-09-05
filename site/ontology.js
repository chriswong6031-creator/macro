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
  var LEG_DETAIL_ID = "ox-steps";
  var legDetail = null;

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

  /* aria-busy must be cleared on every terminal state, success or failure. A
     screen reader parked on a page that finished loading an ERROR is still
     being told the region is updating, so it waits for a result that already
     came and went. */
  function settle() {
    root.setAttribute("aria-busy", "false");
    root.classList.remove("ox-skeleton");
  }

  /* The house sign-in convention carries the page to come back to:
     `?signin=1&ret=<root-relative path>`, consumed by onboard.js:retTarget(),
     which accepts same-origin "/..." only. Without it a reader who came here
     for one specific trace is dropped on the hub after signing in and has to
     find their way back — the bounce is the product's, so the return is too. */
  function signinHref() {
    var here = "/ontology.html";
    try {
      var path = location.pathname + location.search;
      if (path.charAt(0) === "/" && path.slice(0, 2) !== "//") here = path;
    } catch (e) { /* keep the static fallback */ }
    return "/?signin=1&ret=" + encodeURIComponent(here);
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
    settle();
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

  /* Three facts the reader needs before trusting anything below: how much of
     the path was actually read, how old those readings are, and what this page
     cannot verify. Compact by design — the full receipts live in Study, and a
     diagnostic wall in the first viewport buries the answer it is qualifying. */
  function renderMeta(snapshot) {
    var meta = el("p", "ox-meta");
    var cov = snapshot.state.coverage;

    var covSpan = el("span", "ox-meta-item");
    if (cov.legs_unobserved && cov.legs_unobserved.length) {
      covSpan.setAttribute("data-flag", "1");
      covSpan.appendChild(say(
        cov.legs_observed + " of " + cov.legs_declared + " steps have a current reading",
        cov.legs_declared + " 个环节中有 " + cov.legs_observed + " 个具备当前读数"));
    } else {
      covSpan.appendChild(say("All " + cov.legs_declared + " steps have a current reading",
        "全部 " + cov.legs_declared + " 个环节均有当前读数"));
    }
    meta.appendChild(covSpan);

    var fresh = snapshot.source.freshness;
    var age = el("span", "ox-meta-item");
    if (fresh.observation_asof && fresh.observation_age_days != null) {
      age.appendChild(say(
        "Readings dated " + fresh.observation_asof + " ("
          + (fresh.observation_age_days === 0 ? "today"
             : fresh.observation_age_days === 1 ? "1 day ago"
             : fresh.observation_age_days + " days ago") + ")",
        "读数日期 " + fresh.observation_asof + "（"
          + (fresh.observation_age_days === 0 ? "今日"
             : fresh.observation_age_days + " 天前") + "）"));
    } else {
      age.setAttribute("data-flag", "1");
      age.appendChild(say("Reading date not published", "读数日期未发布"));
    }
    meta.appendChild(age);

    if (fresh.status === "verification_unavailable") {
      var unc = el("span", "ox-meta-item");
      unc.setAttribute("data-flag", "1");
      unc.appendChild(say("Not verified against the published page",
        "未与已发布页面比对核验"));
      meta.appendChild(unc);
    }
    return meta;
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

  function reducedMotion() {
    return !!(window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }

  /* The action actually performs the thing its label promises: it opens the
     step-by-step section, brings the named step into view and moves focus onto
     it, so a keyboard or screen-reader user lands where a sighted user is
     looking. The target id is stable and derived from the owner's node id, so
     the anchor survives a re-render and can be linked to directly. */
  function focusLeg(nodeId) {
    var target = document.getElementById("ox-leg-" + nodeId);
    if (!target) return false;
    var wasClosed = !!(legDetail && !legDetail.open);
    if (wasClosed) legDetail.open = true;
    /* Opening a <details> reveals content that has not been laid out yet, so a
       scroll issued in the same tick measures the pre-open position and lands
       somewhere else entirely — measured: the step ended up 200px below the
       fold. Wait for the frame that includes the newly revealed content. */
    var inView = function () {
      var box = target.getBoundingClientRect();
      return box.top >= 0 && box.bottom <= (window.innerHeight
        || document.documentElement.clientHeight);
    };
    var go = function () {
      if (!target.scrollIntoView) { target.focus({ preventScroll: true }); return; }
      var smooth = !reducedMotion();
      target.scrollIntoView(smooth
        ? { block: "center", behavior: "smooth" }
        : { block: "center" });
      target.focus({ preventScroll: true });
      /* Smooth scrolling is an animation, and an animation is not a guarantee:
         a hidden or throttled tab never runs it, and a competing scroll can
         interrupt it — measured, the step stayed 200px below the fold while the
         focus ring sat on something the reader could not see. Motion is the
         enhancement; arriving is the requirement, so the destination is checked
         and corrected without it. */
      if (!smooth) return;
      window.setTimeout(function () {
        if (!inView()) target.scrollIntoView({ block: "center" });
      }, 500);
    };
    if (!wasClosed) {
      go();
      return true;
    }
    /* rAF is the right clock for "after the next paint", but a background or
       hidden tab throttles it to nothing — measured here: the callback never
       ran and the action silently did half its job. A timeout is racing it so
       the action always completes; whichever wins, `go` runs once. */
    var done = false;
    var once = function () { if (done) return; done = true; go(); };
    if (window.requestAnimationFrame) {
      window.requestAnimationFrame(function () { window.requestAnimationFrame(once); });
    }
    window.setTimeout(once, 60);
    return true;
  }

  /* The canonical surface is always reachable, in every state. It used to be
     offered only by the one action branch that fires when nothing is blocking
     and nothing is unobserved — a rare case — which left the ordinary dormant
     reader with the link present solely inside <noscript>, i.e. exactly where
     the reader who can see the page never looks. This path is a real page that
     carries every chain the owners publish, so it is a genuine continuation
     rather than a courtesy link. */
  function transmissionLink() {
    var p = el("p", "ox-more");
    var a = el("a");
    a.href = "transmission.html";
    a.appendChild(say("See this path among all the owners publish",
      "在所有者发布的全部路径中查看本条"));
    p.appendChild(a);
    return p;
  }

  function renderNextAction(snapshot) {
    var action = snapshot.next_action;
    var box = card("Next", "下一步", "watch");

    if (action.handler === "focus_leg" && action.target) {
      var button = el("button", "ox-action");
      button.type = "button";
      button.setAttribute("aria-controls", LEG_DETAIL_ID);
      button.appendChild(bi(action.label));
      button.addEventListener("click", function () {
        if (!focusLeg(action.target)) {
          /* The step this action names is not on the page. Silently doing
             nothing would leave the reader clicking a dead control, so the
             button states that instead of pretending it worked. */
          button.disabled = true;
          button.textContent = "";
          button.appendChild(say("That step is not on this page",
            "该环节不在本页面上"));
        }
      });
      box.appendChild(button);
      var hint = el("p", "ox-note");
      hint.appendChild(say("Opens the step-by-step readings below.",
        "将展开下方的逐环节读数。"));
      box.appendChild(hint);
      box.appendChild(transmissionLink());
      return box;
    }

    var link = el("a", "ox-action");
    link.href = "transmission.html";
    link.appendChild(bi(action.label));
    box.appendChild(link);
    var note = el("p", "ox-note");
    note.appendChild(say("The transmission overview carries every path the owners "
      + "publish, not only this one.",
      "传导链总览页面涵盖所有者发布的全部路径，而不仅是本条。"));
    box.appendChild(note);
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
    d.id = LEG_DETAIL_ID;
    snapshot.path.legs.forEach(function (leg) {
      var box = el("div", "ox-leg");
      box.id = "ox-leg-" + leg.node_id;
      /* -1 keeps the step out of the tab order — it is a destination, not a
         control — while still allowing focus() to land on it. */
      box.tabIndex = -1;
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

  var GAP_TEXT = {
    node_incomplete: { en: "a step the owners have not finished recording",
      zh: "所有者尚未记录完整的环节" },
    node_unresolved: { en: "a step the owners have not resolved",
      zh: "所有者尚未判定的环节" },
    node_unjudged: { en: "a step recorded without a verdict",
      zh: "已记录但未给出判定的环节" },
    node_unreadable: { en: "a step whose verdict could not be read",
      zh: "判定无法读取的环节" },
    node_undeclared: { en: "a step referenced by the path but never declared",
      zh: "路径引用但从未声明的环节" },
    path_incomplete: { en: "part of the path the walk never reached",
      zh: "遍历未触及的路径片段" },
    build_stamp_unparseable: { en: "a build stamp this page could not read",
      zh: "本页面无法解析的构建时间戳" },
    build_stamp_in_future: { en: "a build stamp dated ahead of now",
      zh: "时间戳晚于当前时刻的构建记录" },
    text_withheld: { en: "an owner note held back from this page",
      zh: "未在本页面展示的所有者备注" },
    text_untranslated: { en: "an owner note published in one language only",
      zh: "仅以单一语言发布的所有者备注" },
    episode_ledger_truncated: { en: "a change history longer than this page reads",
      zh: "长度超出本页面读取上限的变更历史" }
  };

  function gapLabel(gap) {
    var known = GAP_TEXT[gap.kind];
    if (known) return say(known.en, known.zh);
    /* An unmapped kind is still disclosed. Hiding it because this page has no
       sentence for it would turn a known gap into a silent one. */
    return say(gap.kind.replace(/_/g, " "), gap.kind.replace(/_/g, " "));
  }

  function renderExposure(snapshot) {
    var screens = snapshot.exposure_screens || [];
    if (!screens.length) return null;
    var d = detail("What this path bears on", "该路径涉及什么");
    var lead = el("p", "ox-note");
    lead.appendChild(say(
      "The owners flag these as the exposures this path would run through. They are "
      + "descriptions of where the mechanism lands, not a list of names, a screen you "
      + "can run, or a suggestion to act.",
      "所有者将以下项标注为该路径可能传导至的敞口类别。它们是机制落点的描述，"
      + "并非标的名单、可直接运行的筛选器，也不构成任何操作建议。"));
    d.appendChild(lead);
    screens.forEach(function (screen) {
      var box = el("div", "ox-leg");
      var h = el("h3");
      h.appendChild(bi(screen.label));
      box.appendChild(h);
      if (screen.note) {
        var note = el("p", "ox-note");
        note.appendChild(bi(screen.note));
        box.appendChild(note);
      }
      d.appendChild(box);
    });
    return d;
  }

  function renderSourceDetail(snapshot) {
    var d = detail("Study: where every number on this page came from",
      "溯源：本页面每个数字的来源");
    var src = snapshot.source;

    var kv = el("dl", "ox-kv");
    function row(labelEn, labelZh, value) {
      var dt = el("dt");
      dt.appendChild(say(labelEn, labelZh));
      kv.appendChild(dt);
      kv.appendChild(el("dd", null, value));
    }
    row("Effective as of", "数据截至", src.asof || "—");
    row("Artifact built", "产物构建于", src.built || "—");
    row("Composed at", "本次生成于", snapshot.generated_at || "—");
    row("Path revision", "路径版本", src.rev == null ? "—" : String(src.rev));
    row("Owner state schema", "所有者状态模式", src.state_schema || "—");
    row("Composed by", "生成方法", src.composer_method || "—");
    row("Snapshot contract", "快照契约", snapshot.schema || "—");
    d.appendChild(kv);

    /* The full digest, not a prefix. A truncated hash cannot be recomputed
       against, which is the only thing a read receipt is for. */
    var manifest = el("p", "ox-hash");
    manifest.appendChild(say("Read manifest", "读取清单"));
    manifest.appendChild(el("code", null, src.source_manifest_hash || "—"));
    d.appendChild(manifest);
    var manifestNote = el("p", "ox-note");
    manifestNote.appendChild(say(
      "That digest binds the composing method above together with the exact bytes of "
      + "every file read below. It identifies this read; it is not a signature by the "
      + "owners of the data.",
      "该摘要将上述生成方法与下列各文件本次读取的确切字节绑定在一起。"
      + "它用于标识本次读取，并非数据所有者的签名。"));
    d.appendChild(manifestNote);

    var readsBox = el("div", "ox-leg");
    var rh = el("h3");
    rh.appendChild(say("Files read for this answer", "为本次回答读取的文件"));
    readsBox.appendChild(rh);
    (src.reads || []).forEach(function (read) {
      var line = el("p", "ox-hash");
      line.appendChild(el("span", "ox-hash-path", read.path));
      line.appendChild(el("code", null, "sha256:" + read.sha256));
      line.appendChild(el("span", "ox-hash-size", read.bytes + " B"));
      readsBox.appendChild(line);
    });
    if (!(src.reads || []).length) {
      var none = el("p", "ox-note");
      none.appendChild(say("No read receipts were recorded.", "未记录任何读取凭证。"));
      readsBox.appendChild(none);
    }
    d.appendChild(readsBox);

    var freshness = el("p", "ox-note");
    freshness.appendChild(bi(src.freshness.note));
    d.appendChild(freshness);

    var k1 = snapshot.evidence.k1;
    if (k1.status !== "available") {
      var k1p = el("p", "ox-note");
      if (k1.reason_code === "eligible_transition_not_k1_resolved") {
        k1p.appendChild(say(
          "The owners have recorded " + k1.recorded_transitions + " transition(s) for this "
          + "path, but this page resolved none of them into a formal evidence reference, so "
          + "none is cited. A recorded transition is not itself a reference.",
          "所有者已记录该路径的 " + k1.recorded_transitions + " 次状态转换，"
          + "但本页面未将其中任何一次解析为正式证据引用，故不予引用。"
          + "已记录的状态转换本身并不构成引用。"));
      } else {
        k1p.appendChild(say(
          "No formal evidence reference is cited for this reading. The current summary is a "
          + "derived view the evidence contract does not accept as a citable source, and no "
          + "recorded transition exists to cite instead. The readings above come straight "
          + "from the owner fields, with the read receipts listed here.",
          "本次读数未引用正式证据。当前汇总属于派生视图，证据契约不接受其作为可引用来源，"
          + "亦无已记录的状态转换可供引用。上文读数直接取自所有者字段，"
          + "其读取凭证已在此列出。"));
      }
      d.appendChild(k1p);
    }

    if (snapshot.display_permission
        && snapshot.display_permission.status !== "determined") {
      var perm = el("p", "ox-note");
      perm.appendChild(say(
        "Whether the underlying sources may be redistributed is not determined on this "
        + "page. Access to this reading is controlled by your account, which is a "
        + "different question.",
        "本页面不判定底层数据源是否可再分发。本次读数的访问权限由您的账户控制，"
        + "两者并非同一问题。"));
      d.appendChild(perm);
    }

    /* Two different things end up in `gaps` and calling them both "missing"
       would be inaccurate: something the owners never published, and something
       they published that this surface refused to print. Both are named
       individually — a count tells the reader something is absent without ever
       letting them find out what. */
    var missing = (snapshot.gaps || []).filter(function (g) {
      return g.kind !== "text_withheld" && g.kind !== "text_untranslated";
    });
    var withheld = (snapshot.gaps || []).filter(function (g) {
      return g.kind === "text_withheld" || g.kind === "text_untranslated";
    });

    function gapList(items, headEn, headZh) {
      var box = el("div", "ox-leg");
      var h = el("h3");
      h.appendChild(say(headEn, headZh));
      box.appendChild(h);
      var ul = el("ul", "ox-gaps");
      items.forEach(function (gap) {
        var li = el("li");
        li.appendChild(gapLabel(gap));
        /* The reader-facing location only. `gap.where` is the machine field
           path — it names internal fields and, for the watch list, carries the
           refutation family this page does not print. Making a gap reachable
           must not smuggle either onto the surface. */
        if (gap.where_label) {
          var where = el("span", "ox-gap-where");
          where.appendChild(bi(gap.where_label));
          li.appendChild(where);
        }
        if (gap.reason_label) {
          var why = el("span", "ox-gap-why");
          why.appendChild(bi(gap.reason_label));
          li.appendChild(why);
        }
        ul.appendChild(li);
      });
      box.appendChild(ul);
      return box;
    }

    if (missing.length) {
      var mBox = gapList(missing,
        "Published by the owners incompletely", "所有者发布不完整之处");
      var mNote = el("p", "ox-note");
      mNote.appendChild(say("These are named rather than filled in.",
        "以上各项仅具名列出，未作填补。"));
      mBox.appendChild(mNote);
      d.appendChild(mBox);
    }
    if (withheld.length) {
      var wBox = gapList(withheld, "Published, but not shown here", "已发布但未在此展示");
      var wNote = el("p", "ox-note");
      wNote.appendChild(say(
        "This page held these back — the wording would not meet its standard for "
        + "reader-facing text. The condition each one describes is shown with its step.",
        "本页面主动保留了以上内容——其措辞不符合本页面面向读者文本的标准。"
        + "其所描述的条件已随对应环节展示。"));
      wBox.appendChild(wNote);
      d.appendChild(wBox);
    }
    return d;
  }

  function render(snapshot) {
    root.textContent = "";

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
    hero.appendChild(renderMeta(snapshot));
    root.appendChild(hero);

    root.appendChild(renderRail(snapshot));

    var answers = el("section", "ox-answers");
    answers.appendChild(renderWhatChanged(snapshot));
    answers.appendChild(renderWhyItMatters(snapshot));
    answers.appendChild(renderBlocking(snapshot));
    answers.appendChild(renderNextAction(snapshot));
    root.appendChild(answers);

    legDetail = renderLegDetail(snapshot);
    root.appendChild(legDetail);
    var exposure = renderExposure(snapshot);
    if (exposure) root.appendChild(exposure);
    root.appendChild(renderSourceDetail(snapshot));
    settle();
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
            "Sign in", "登录", signinHref());
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
