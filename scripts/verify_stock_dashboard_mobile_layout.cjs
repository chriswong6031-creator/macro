#!/usr/bin/env node
"use strict";

/*
 * Fail-closed 390px browser receipt for the Prophet stock-dashboard shell.
 *
 * The verifier serves one explicitly rendered HTML artifact plus its checked-in
 * site assets from an isolated origin. It covers EN/ZH x dark/light and the
 * JS-disabled, composer-failed, and composer-pending first frames. A run fails
 * when the document itself scrolls horizontally, any visible element is wider
 * than the viewport, or a full-page PNG is wider than 390px. Failed rows carry
 * stable selectors and the layout properties needed to find the owning rule.
 */

const fs = require("fs");
const crypto = require("crypto");
const path = require("path");

function usage(message) {
  if (message) process.stderr.write(`error: ${message}\n`);
  process.stderr.write(
    "usage: verify_stock_dashboard_mobile_layout.cjs " +
      "--html FILE --site-dir DIR --fixture-receipt FILE --fixture-assets-dir DIR " +
      "[--composer FILE] [--browser FILE] [--out FILE] [--screenshot-dir DIR] " +
      "[--historical-head SHA] [--historical-tree SHA]\n"
  );
  process.exit(2);
}

function parseArgs(argv) {
  const parsed = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!key || !key.startsWith("--") || i + 1 >= argv.length) usage("invalid arguments");
    parsed[key.slice(2)] = argv[i + 1];
  }
  if (!parsed.html || !parsed["site-dir"] || !parsed["fixture-receipt"] ||
      !parsed["fixture-assets-dir"]) {
    usage("--html, --site-dir, --fixture-receipt, and --fixture-assets-dir are required");
  }
  return parsed;
}

function realFile(value, label) {
  const resolved = path.resolve(value);
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isFile()) usage(`${label} is not a file: ${resolved}`);
  return resolved;
}

function realDir(value, label) {
  const resolved = path.resolve(value);
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) usage(`${label} is not a directory: ${resolved}`);
  return resolved;
}

function sha256Bytes(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function sha256File(filename) {
  return sha256Bytes(fs.readFileSync(filename));
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${canonicalJson(value[key])}`
    ).join(",")}}`;
  }
  return JSON.stringify(value);
}

function bindCanonicalReceipt(row, label) {
  const canonicalization = "utf-8 JSON; sort_keys=true; separators=(',', ':'); no trailing newline";
  if (!row || row.canonicalization !== canonicalization ||
      !Number.isInteger(row.bytes) || typeof row.sha256 !== "string" ||
      !row.payload || typeof row.payload !== "object") {
    usage(`fixture receipt carries a malformed ${label}`);
  }
  const bytes = Buffer.from(canonicalJson(row.payload), "utf8");
  if (bytes.length !== row.bytes || sha256Bytes(bytes) !== row.sha256) {
    usage(`fixture receipt ${label} canonical binding mismatch`);
  }
  return row;
}

function relativeRepoPath(repoRoot, filename) {
  const relative = path.relative(repoRoot, filename);
  if (!relative || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) {
    usage(`receipt input is outside the repository: ${filename}`);
  }
  return relative.split(path.sep).join("/");
}

function bindHistoricalReceipt(args, repoRoot) {
  const head = args["historical-head"];
  const tree = args["historical-tree"];
  if (!head && !tree) return null;
  if (!/^[0-9a-f]{40}$/.test(head || "")) {
    usage("--historical-head must be an exact lowercase 40-character Git SHA");
  }
  if (!/^[0-9a-f]{40}$/.test(tree || "")) {
    usage("--historical-tree must accompany --historical-head as an exact lowercase 40-character Git SHA");
  }
  if (!args.out) usage("--historical-head requires --out so the prior receipt can be bound before replacement");
  const receiptFile = realFile(args.out, "existing --out historical receipt");
  let receipt;
  const bytes = fs.readFileSync(receiptFile);
  try {
    receipt = JSON.parse(bytes.toString("utf8"));
  } catch (error) {
    usage(`existing --out historical receipt is not valid JSON: ${error.message}`);
  }
  if (receipt.schema !== "mastermind.stock_dashboard_mobile_layout.v1" ||
      receipt.proof_class !== "browser_fixture_proof_reproducible" ||
      typeof receipt.pass !== "boolean") {
    usage("existing --out is not a prior stock-dashboard browser receipt");
  }
  if (receipt.historical_baseline) {
    const baseline = receipt.historical_baseline;
    if (baseline.schema !== "mastermind.stock_dashboard_browser_historical_baseline.v1" ||
        baseline.candidate_head !== head || baseline.candidate_tree !== tree ||
        !baseline.receipt || baseline.receipt.path !== relativeRepoPath(repoRoot, receiptFile) ||
        !Array.isArray(baseline.screenshots) || baseline.screenshots.length !== 2 ||
        !/^[0-9a-f]{64}$/.test(baseline.receipt.sha256 || "")) {
      usage("existing --out carries a conflicting historical baseline");
    }
    return baseline;
  }
  const states = Array.isArray(receipt.states) ? receipt.states.length : 0;
  const expansion = Array.isArray(receipt.expansion_reachability && receipt.expansion_reachability.cases)
    ? receipt.expansion_reachability.cases.length : 0;
  const fragment = Array.isArray(receipt.fragment_navigation && receipt.fragment_navigation.cases)
    ? receipt.fragment_navigation.cases.length : 0;
  const desktop = Array.isArray(receipt.desktop && receipt.desktop.sequence)
    ? receipt.desktop.sequence.length : 0;
  const screenshots = Array.isArray(receipt.states)
    ? receipt.states.filter((row) => row && row.screenshot).map((row) => ({
      state: row.state,
      path: row.screenshot.path,
      sha256: row.screenshot.sha256,
    })) : [];
  for (const screenshot of screenshots) {
    const filename = path.resolve(repoRoot, screenshot.path || "");
    if (!filename.startsWith(repoRoot + path.sep) ||
        !fs.existsSync(filename) || !fs.statSync(filename).isFile() ||
        sha256File(filename) !== screenshot.sha256) {
      usage(`historical screenshot binding is unavailable: ${screenshot.path || "missing path"}`);
    }
  }
  return {
    schema: "mastermind.stock_dashboard_browser_historical_baseline.v1",
    candidate_head: head,
    candidate_tree: tree,
    receipt: {
      path: relativeRepoPath(repoRoot, receiptFile),
      sha256: sha256Bytes(bytes),
      recovery: `git show ${head}:${relativeRepoPath(repoRoot, receiptFile)}`,
    },
    proof_class: receipt.proof_class,
    claims: receipt.claims,
    verifier: receipt.verifier,
    browser: receipt.browser,
    input_html: receipt.input_html,
    screenshots,
    result: {
      pass: receipt.pass,
      state_cases: states,
      expansion_cases: expansion,
      fragment_cases: fragment,
      desktop_sequence_cases: desktop,
      total_cases: states + expansion + fragment + desktop,
      bound_screenshots: screenshots.length,
    },
  };
}

function bindFixtureReceipt(receiptFile, htmlFile, repoRoot) {
  let receipt;
  try {
    receipt = JSON.parse(fs.readFileSync(receiptFile, "utf8"));
  } catch (error) {
    usage(`--fixture-receipt is not valid JSON: ${error.message}`);
  }
  if (receipt.schema !== "mastermind.stock_dashboard_rendered_fixture.v1" ||
      receipt.proof_class !== "rendered_fixture") {
    usage("--fixture-receipt is not a rendered stock-dashboard fixture receipt");
  }
  const htmlSha256 = sha256File(htmlFile);
  const matches = Object.entries(receipt.markets || {}).filter(
    ([, market]) => market && market.output_sha256 === htmlSha256
  );
  if (matches.length !== 1) {
    usage(`rendered HTML hash must match exactly one fixture market; matched ${matches.length}`);
  }
  const [market, binding] = matches[0];
  if (typeof binding.route !== "string" || !/^\/[^?#]+\.html$/.test(binding.route) ||
      typeof binding.output !== "string" || path.posix.basename(binding.route) !== binding.output) {
    usage(`fixture receipt carries an invalid ${market} route/output binding`);
  }
  const expectedOwnerCases = ["normal", "watch-only", "null-buy"];
  if (!binding.owner_cases ||
      JSON.stringify(Object.keys(binding.owner_cases).sort()) !== JSON.stringify(expectedOwnerCases.slice().sort())) {
    usage(`fixture receipt must carry the closed ${market} owner-case set`);
  }
  const ownerCases = {};
  for (const ownerCase of expectedOwnerCases) {
    const row = binding.owner_cases[ownerCase];
    if (!row || row.route !== binding.route || typeof row.output !== "string" ||
        path.basename(row.output) !== row.output || !row.output.endsWith(".html") ||
        typeof row.output_sha256 !== "string" || !row.owner_population) {
      usage(`fixture receipt carries a malformed ${market}/${ownerCase} owner case`);
    }
    const filename = path.resolve(path.dirname(htmlFile), row.output);
    if (path.dirname(filename) !== path.dirname(htmlFile) ||
        !fs.existsSync(filename) || !fs.statSync(filename).isFile()) {
      usage(`rendered owner-case HTML is missing: ${row.output}`);
    }
    if (sha256File(filename) !== row.output_sha256) {
      usage(`rendered owner-case HTML hash mismatch: ${row.output}`);
    }
    const transform = bindCanonicalReceipt(row.input_transform, `${market}/${ownerCase} input transform`);
    if (transform.payload.schema !== "mastermind.stock_dashboard_owner_case.v1" ||
        transform.payload.market !== market || transform.payload.owner_case !== ownerCase) {
      usage(`fixture receipt carries the wrong ${market}/${ownerCase} transform identity`);
    }
    ownerCases[ownerCase] = {...row, filename};
  }
  if (ownerCases.normal.filename !== htmlFile ||
      ownerCases.normal.output_sha256 !== htmlSha256) {
    usage(`--html must bind the normal ${market} owner case`);
  }
  const membershipOverlay = bindCanonicalReceipt(
    binding.diagnostic_membership_overlay,
    `${market} diagnostic membership overlay`
  );
  if (membershipOverlay.payload.schema !== "mastermind.stock_dashboard_membership_overlay.v1" ||
      membershipOverlay.payload.market !== market ||
      membershipOverlay.payload.owner_case !== "normal" ||
      membershipOverlay.payload.classification !== "browser_contract_fixture_only") {
    usage(`fixture receipt carries the wrong ${market} membership-overlay identity`);
  }
  const constructionInputs = {};
  for (const item of binding.inputs || []) {
    if (!item || typeof item.path !== "string" || typeof item.sha256 !== "string") {
      usage(`fixture receipt carries a malformed ${market} input row`);
    }
    const filename = path.resolve(repoRoot, item.path);
    if (relativeRepoPath(repoRoot, filename) !== item.path) {
      usage(`fixture receipt input is not canonical: ${item.path}`);
    }
    if (!fs.existsSync(filename) || !fs.statSync(filename).isFile()) {
      usage(`fixture receipt input is missing: ${item.path}`);
    }
    const actual = sha256File(filename);
    if (actual !== item.sha256) {
      usage(`fixture receipt input hash mismatch: ${item.path}`);
    }
    constructionInputs[item.path] = actual;
  }
  return {
    market,
    route: binding.route,
    output: binding.output,
    htmlSha256,
    ownerCases,
    membershipOverlay,
    receipt: {
      path: relativeRepoPath(repoRoot, receiptFile),
      sha256: sha256File(receiptFile),
    },
    constructionInputs,
  };
}

const MIME = {
  ".css": "text/css",
  ".gif": "image/gif",
  ".html": "text/html",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "text/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

const MARKET_COMPOSERS = {
  hk: "hk-stock-v36.js",
  ca: "canada-stock-v36.js",
};

function pngWidth(bytes) {
  return bytes.length >= 24 && bytes.subarray(1, 4).toString("ascii") === "PNG"
    ? bytes.readUInt32BE(16)
    : null;
}

const LAYOUT_SCRIPT = `() => {
  const root = document.documentElement;
  const viewportWidth = root.clientWidth;
  const visible = (el) => {
    const style = getComputedStyle(el);
    return style.display !== "none" && style.visibility !== "hidden" && el.getClientRects().length > 0;
  };
  const stableSelector = (el) => {
    if (el.id) return "#" + CSS.escape(el.id);
    const parts = [];
    let cursor = el;
    while (cursor && cursor.nodeType === 1 && cursor !== document.body) {
      let part = cursor.tagName.toLowerCase();
      const classes = Array.from(cursor.classList).filter((name) => /^[A-Za-z_-][A-Za-z0-9_-]*$/.test(name)).slice(0, 3);
      if (classes.length) part += "." + classes.map((name) => CSS.escape(name)).join(".");
      const parent = cursor.parentElement;
      if (parent && parent.querySelectorAll(":scope > " + part).length > 1) {
        const peers = Array.from(parent.children).filter((node) => node.tagName === cursor.tagName);
        part += ":nth-of-type(" + (peers.indexOf(cursor) + 1) + ")";
      }
      parts.unshift(part);
      if (cursor.parentElement && cursor.parentElement.id) {
        parts.unshift("#" + CSS.escape(cursor.parentElement.id));
        break;
      }
      cursor = parent;
    }
    return parts.join(" > ");
  };
  const ownerSelector = (el) => {
    const owner = el.closest("#hk-screener, .flows-grid, .hk-v37-panel, .panel, .tbl-scroll, .mx-stockdash--hk");
    return owner ? stableSelector(owner) : null;
  };
  const round = (value) => Math.round(value * 100) / 100;
  const inspect = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return {
      selector: stableSelector(el),
      tag: el.tagName.toLowerCase(),
      class_name: el.className && typeof el.className === "string" ? el.className : "",
      rect: {left: round(rect.left), right: round(rect.right), width: round(rect.width)},
      computed: {
        width: style.width,
        min_width: style.minWidth,
        max_width: style.maxWidth,
        overflow: style.overflow,
        overflow_x: style.overflowX,
        white_space: style.whiteSpace,
      },
      nearest_governed_owner: ownerSelector(el),
    };
  };
  const elements = Array.from(document.querySelectorAll("body *")).filter(visible);
  const wider = elements.filter((el) => el.getBoundingClientRect().width > viewportWidth + 1);
  const clippedByLocalOwner = (el) => {
    let cursor = el.parentElement;
    while (cursor && cursor !== document.body) {
      const style = getComputedStyle(cursor);
      if (["auto", "scroll", "hidden", "clip"].includes(style.overflowX)) {
        const rect = cursor.getBoundingClientRect();
        if (rect.left >= -1 && rect.right <= viewportWidth + 1) return true;
      }
      cursor = cursor.parentElement;
    }
    return false;
  };
  const edgeOverflow = root.scrollWidth > viewportWidth ? elements.filter((el) => {
    const rect = el.getBoundingClientRect();
    return (rect.left < -1 || rect.right > viewportWidth + 1) && !clippedByLocalOwner(el);
  }) : [];
  const offenders = Array.from(new Set(wider.concat(edgeOverflow))).map(inspect);
  return {
    client_width: viewportWidth,
    scroll_width: root.scrollWidth,
    horizontal_overflow: root.scrollWidth > viewportWidth,
    elements_wider_than_viewport: wider.length,
    offenders,
  };
}`;

async function installPageInit(context, market, locale, theme) {
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  await context.addInitScript(({prefix, version, locale, theme}) => {
    localStorage.setItem("lang", locale);
    localStorage.setItem("theme", theme);

    /* Capture the parser-owned action graph after parsing, but before the
       delayed entitled composer executes. Object references and a child-list
       observer make node preservation a real identity proof: equal markup or
       equal hashes cannot disguise replacement. */
    function immutablePayload(host, controls, lanes, lists, rows) {
      return {
        host_id: host.id,
        controls: controls.map((control) => ({
          lane: control.getAttribute(`data-${prefix}-an-lane`),
          href: control.getAttribute("href"),
          owner_default: control.getAttribute(`data-${prefix}-an-default`),
          title: (control.querySelector(`.${version}-an-seg-t`) || control).textContent.trim(),
          count: (control.querySelector("b") || {}).textContent || "",
        })),
        lanes: lanes.map((lane, index) => ({
          id: lane.id,
          key: lane.getAttribute(`data-${prefix}-an-lane-body`),
          list_classes: Array.from(lists[index].classList).filter((name) => name !== "is-collapsed").sort(),
          rows: rows[index].map((row) => ({
            action_id: row.getAttribute("data-action-id"),
            has_rpop: row.hasAttribute("data-rpop"),
            decision_payload: !!row.querySelector(".rp-src"),
            route: (row.querySelector(`.${version}-an-go`) || {}).getAttribute?.("href") || null,
            membership_kind: (row.querySelector(`[data-${prefix}-lead-kind]`) || {}).getAttribute?.(`data-${prefix}-lead-kind`) || null,
            membership_id: (row.querySelector(`[data-${prefix}-lead-id]`) || {}).getAttribute?.(`data-${prefix}-lead-id`) || null,
            html: row.innerHTML,
          })),
        })),
      };
    }

    function captureStaticGraph() {
      const host = document.querySelector(`#${version}-an-body`);
      if (!host || host.classList.contains("is-enhanced")) return false;
      const controls = Array.from(host.querySelectorAll(`[data-${prefix}-an-lane]`));
      const lanes = Array.from(host.querySelectorAll(`[data-${prefix}-an-lane-body]`));
      const lists = lanes.map((lane) => lane.querySelector(`.${version}-an-list`));
      if (controls.length !== 4 || lanes.length !== 4 || lists.some((list) => !list)) return false;
      const rows = lanes.map((lane) => Array.from(lane.querySelectorAll(`.${version}-an-row-w`)));
      const probe = {
        captured: true,
        captured_before_composer: !host.classList.contains("is-enhanced") &&
          !host.querySelector('[role="tablist"], [role="tab"]'),
        host,
        controls,
        lanes,
        lists,
        rows,
        childListMutations: 0,
      };
      probe.snapshot = () => immutablePayload(host, controls, lanes, lists, rows);
      probe.payloadBefore = probe.snapshot();
      probe.observer = new MutationObserver((records) => {
        probe.childListMutations += records.filter((record) => record.type === "childList").length;
      });
      probe.observer.observe(host, {childList: true, subtree: true});
      window.__wtaonStaticProbe = probe;
      return true;
    }

    window.__wtaonStaticProbe = {captured: false, childListMutations: null};
    document.addEventListener("DOMContentLoaded", captureStaticGraph, {once: true});
  }, {prefix, version, locale, theme});
}

function staticAxisHtml(filename, locale, theme) {
  if (!['en', 'zh'].includes(locale) || !['dark', 'light'].includes(theme)) {
    usage(`invalid static language/theme axis: ${locale}/${theme}`);
  }
  const source = fs.readFileSync(filename, "utf8");
  const marker = '<html lang="en">';
  if (source.split(marker).length !== 2) {
    usage(`static-axis HTML requires exactly one ${marker}: ${filename}`);
  }
  const replacement = `<html lang="${locale}" data-lang="${locale}" data-theme="${theme}">`;
  const bytes = Buffer.from(source.replace(marker, replacement), "utf8");
  return {
    bytes,
    receipt: {
      classification: "browser_fixture_static_axis_only",
      operation: `replace ${marker} with ${replacement}`,
      source_sha256: sha256File(filename),
      output_sha256: sha256Bytes(bytes),
      output_bytes: bytes.length,
    },
  };
}

async function installDiagnosticMembershipOverlay(context, market, overlayBinding) {
  const composerFlag = market === "hk" ? "__mmHKStockV36" : "__mmCanadaStockV36";
  const composerFilename = MARKET_COMPOSERS[market];
  const payload = overlayBinding.payload;
  await context.addInitScript(({payload, composerFlag, composerFilename}) => {
    const nativeParse = JSON.parse;
    const probe = {
      installed: false,
      consumed: false,
      restored: false,
      error: null,
      original_text: null,
      control: null,
      control_parent: null,
      member_rows: payload.composer_rows,
    };
    window.__p0bMembershipOverlay = probe;

    /* Return the admitted rows only to the exact entitled composer's parseRows
       call. StockTable and every other JSON consumer receive the untouched
       server bytes, so the diagnostic cannot widen the rendered table. */
    JSON.parse = function (text, ...args) {
      const parsed = nativeParse.call(JSON, text, ...args);
      try {
        const data = document.querySelector("#stocktable-data");
        const stack = String(new Error().stack || "");
        if (!probe.consumed && data && text === data.textContent &&
            stack.includes(composerFilename) && parsed && Array.isArray(parsed.rows)) {
          probe.original_text = data.textContent;
          parsed.rows = parsed.rows.concat(payload.composer_rows);
          probe.consumed = true;
        }
      } catch (error) {
        probe.error = String(error && error.message || error);
      }
      return parsed;
    };

    function enableControl() {
      const control = document.querySelector(payload.control.selector);
      if (!control) {
        probe.error = "diagnostic control missing";
        return;
      }
      payload.control.remove_attributes.forEach((name) => control.removeAttribute(name));
      Object.entries(payload.control.set_attributes).forEach(([name, value]) =>
        control.setAttribute(name, value)
      );
      probe.control = control;
      probe.control_parent = control.parentElement;
      probe.installed = true;
    }
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", enableControl, {once: true});
    } else {
      enableControl();
    }

    const restore = setInterval(() => {
      if (!window[composerFlag] || !probe.consumed) return;
      clearInterval(restore);
      JSON.parse = nativeParse;
      probe.restored = true;
    }, 10);
    setTimeout(() => {
      if (!probe.restored) {
        clearInterval(restore);
        JSON.parse = nativeParse;
        probe.error = probe.error || "composer did not consume overlay before timeout";
      }
    }, 5000);
  }, {payload, composerFlag, composerFilename});
}

async function nodeIdentityProof(page, market) {
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  const proof = await page.evaluate(({prefix, version}) => {
    const probe = window.__wtaonStaticProbe;
    if (!probe || !probe.captured) return {captured: false, pass: false};
    const host = document.querySelector(`#${version}-an-body`);
    const controls = Array.from(host.querySelectorAll(`[data-${prefix}-an-lane]`));
    const lanes = Array.from(host.querySelectorAll(`[data-${prefix}-an-lane-body]`));
    const lists = lanes.map((lane) => lane.querySelector(`.${version}-an-list`));
    const rows = lanes.map((lane) => Array.from(lane.querySelectorAll(`.${version}-an-row-w`)));
    const sameArray = (before, after) => before.length === after.length &&
      before.every((node, index) => node === after[index]);
    const sameRows = probe.rows.length === rows.length &&
      probe.rows.every((laneRows, index) => sameArray(laneRows, rows[index]));
    return {
      captured: true,
      captured_before_composer: probe.captured_before_composer,
      same_host: probe.host === host,
      same_controls: sameArray(probe.controls, controls),
      same_lanes: sameArray(probe.lanes, lanes),
      same_lists: sameArray(probe.lists, lists),
      same_rows: sameRows,
      child_list_mutations: probe.childListMutations,
      payload_before: probe.payloadBefore,
      payload_after: probe.snapshot(),
    };
  }, {prefix, version});
  if (!proof.captured) return proof;
  proof.payload_hash_before = sha256Bytes(Buffer.from(JSON.stringify(proof.payload_before)));
  proof.payload_hash_after = sha256Bytes(Buffer.from(JSON.stringify(proof.payload_after)));
  delete proof.payload_before;
  delete proof.payload_after;
  proof.pass = proof.captured_before_composer && proof.same_host && proof.same_controls &&
    proof.same_lanes && proof.same_lists && proof.same_rows && proof.child_list_mutations === 0 &&
    proof.payload_hash_before === proof.payload_hash_after;
  return proof;
}

async function expansionReachabilityProof(browser, market, route, installRoutes) {
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  const modes = [
    {name: "js-disabled", javascriptEnabled: false},
    {name: "composer-failed", composerMode: "failed"},
    {name: "composer-pending", composerMode: "pending"},
    {name: "loaded", composerMode: "loaded"},
  ];
  const cases = [];

  for (const width of [390, 1440]) {
    for (const mode of modes) {
      const context = await browser.newContext({
        viewport: {width, height: 900},
        deviceScaleFactor: 1,
        javaScriptEnabled: mode.javascriptEnabled !== false,
      });
      if (mode.javascriptEnabled !== false) {
        await installPageInit(context, market, "en", "dark");
      }
      await installRoutes(context, mode.composerMode || "loaded");
      const page = await context.newPage();
      const consoleExceptions = [];
      page.on("pageerror", (error) => consoleExceptions.push(
        String(error && (error.stack || error.message) || error)
      ));

      try {
        await page.goto(new URL(route, "http://stock-dashboard.invalid").href, {
          waitUntil: mode.composerMode === "pending" ? "commit" : "load",
          timeout: 30000,
        });
        await page.locator(`[data-${prefix}-an-lane-body="buy"]`).waitFor();
        await page.waitForTimeout(mode.composerMode === "pending" ? 500 : 750);

        const snapshot = () => page.evaluate(({prefix, version}) => {
          const visible = (el) => !!el && getComputedStyle(el).display !== "none" &&
            getComputedStyle(el).visibility !== "hidden" && el.getClientRects().length > 0;
          const lane = document.querySelector(`[data-${prefix}-an-lane-body="buy"]`);
          const disclosure = lane && lane.querySelector(`details[data-${prefix}-an-disclosure]`);
          const summary = lane && lane.querySelector(`[data-${prefix}-an-view]`);
          const rows = lane ? Array.from(lane.querySelectorAll(`.${version}-an-row-w`)) : [];
          const payload = rows.map((row) => ({
            action_id: row.getAttribute("data-action-id"),
            has_rpop: row.hasAttribute("data-rpop"),
            decision_payload: !!row.querySelector(".rp-src"),
            route: (row.querySelector(`.${version}-an-go`) || {}).getAttribute?.("href") || null,
            html: row.innerHTML,
          }));
          if (!window.__wtaonExpansionProbe) {
            const probe = {
              lane,
              disclosure,
              summary,
              rows,
              payload,
              childListMutations: 0,
            };
            if (lane) {
              probe.observer = new MutationObserver((records) => {
                probe.childListMutations += records.filter((record) => record.type === "childList").length;
              });
              probe.observer.observe(lane, {childList: true, subtree: true});
            }
            window.__wtaonExpansionProbe = probe;
          }
          const probe = window.__wtaonExpansionProbe;
          const sameRows = probe.rows.length === rows.length &&
            probe.rows.every((row, index) => row === rows[index]);
          const labels = summary ? Array.from(summary.querySelectorAll(".lm-show, .lm-hide")) : [];
          return {
            total: rows.length,
            visible: rows.filter(visible).length,
            visible_ids: rows.filter(visible).map((row) => row.getAttribute("data-action-id")),
            rich_rows: payload.filter((row) => row.has_rpop && row.decision_payload && row.route).length,
            disclosure_count: lane ? lane.querySelectorAll(`details[data-${prefix}-an-disclosure]`).length : 0,
            disclosure_open: !!(disclosure && disclosure.open),
            summary_tag: summary ? summary.tagName : null,
            summary_visible_text: labels.filter(visible).map((node) => node.textContent.trim()).join(" "),
            focus_on_summary: document.activeElement === summary,
            other_open_count: Array.from(document.querySelectorAll(`details[data-${prefix}-an-disclosure][open]`))
              .filter((node) => node !== disclosure).length,
            same_lane: probe.lane === lane,
            same_disclosure: probe.disclosure === disclosure,
            same_summary: probe.summary === summary,
            same_rows: sameRows,
            same_payload: JSON.stringify(probe.payload) === JSON.stringify(payload),
            child_list_mutations: probe.childListMutations,
            viewport_width: document.documentElement.clientWidth,
            document_width: document.documentElement.scrollWidth,
          };
        }, {prefix, version});

        const before = await snapshot();
        const summary = page.locator(
          `[data-${prefix}-an-lane-body="buy"] [data-${prefix}-an-view]`
        );
        if (await summary.count()) {
          await summary.focus();
          await summary.click();
        }
        await page.waitForTimeout(30);
        const afterClick = await snapshot();
        if (await summary.count()) await summary.click();
        await page.waitForTimeout(30);
        const afterClickClose = await snapshot();
        if (await summary.count()) {
          await summary.focus();
          await page.keyboard.press("Enter");
        }
        await page.waitForTimeout(30);
        const afterEnter = await snapshot();
        if (await summary.count()) await page.keyboard.press("Enter");
        await page.waitForTimeout(30);
        const afterEnterClose = await snapshot();
        if (await summary.count()) await page.keyboard.press("Space");
        await page.waitForTimeout(30);
        const afterSpace = await snapshot();

        const closed = (state) => state.visible === 3 && !state.disclosure_open &&
          /View all.*\d+/.test(state.summary_visible_text);
        const open = (state) => state.visible === state.total && state.total > 3 &&
          state.disclosure_open && /Show fewer/.test(state.summary_visible_text) &&
          state.focus_on_summary && state.other_open_count === 0 &&
          state.same_lane && state.same_disclosure && state.same_summary && state.same_rows &&
          state.same_payload && state.child_list_mutations === 0 &&
          state.document_width <= state.viewport_width;
        const result = {
          market,
          viewport_width: width,
          mode: mode.name,
          before,
          after_click: afterClick,
          after_click_close: afterClickClose,
          after_enter: afterEnter,
          after_enter_close: afterEnterClose,
          after_space: afterSpace,
          console_exceptions: consoleExceptions,
        };
        result.pass = before.total > 3 && before.rich_rows === before.total &&
          before.disclosure_count === 1 && before.summary_tag === "SUMMARY" &&
          closed(before) && open(afterClick) && closed(afterClickClose) &&
          open(afterEnter) && closed(afterEnterClose) && open(afterSpace) &&
          consoleExceptions.length === 0;
        cases.push(result);
      } finally {
        await context.close();
      }
    }
  }

  return {
    expected_cases: 8,
    passed_cases: cases.filter((row) => row.pass).length,
    cases,
    pass: cases.length === 8 && cases.every((row) => row.pass),
  };
}

async function mobileBehavior(page, market, composerMode, javascriptEnabled) {
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  const basic = await page.evaluate(({prefix, version, market}) => {
    const visible = (el) => {
      const style = getComputedStyle(el);
      return style.display !== "none" && style.visibility !== "hidden" && el.getClientRects().length > 0;
    };
    const tabNodes = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane]`));
    const tabs = tabNodes.map((tab) => {
      const title = tab.querySelector(`.${version}-an-seg-t`) || tab;
      return {
        lane: tab.getAttribute(`data-${prefix}-an-lane`),
        title: title.textContent.trim(),
        count: (tab.querySelector("b") || {}).textContent || "",
        selected: tab.getAttribute("aria-selected") === "true",
        title_fully_visible: title.scrollWidth <= title.clientWidth + 1 && getComputedStyle(title).textOverflow === "clip",
      };
    });
    const lanes = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`));
    const visibleLanes = lanes.filter(visible).map((lane) => lane.getAttribute(`data-${prefix}-an-lane-body`));
    const activeRows = lanes.filter(visible).flatMap((lane) =>
      Array.from(lane.querySelectorAll(`.${version}-an-row-w`)).filter(visible)
    );
    const known = document.querySelector(`.${version}-an-row-w[data-action-id="FIXTURE-SECTOR"]`);
    const unknown = document.querySelector(`.${version}-an-row-w[data-action-id="FIXTURE-FINANCE"]`);
    const host = document.querySelector(market === "hk" ? "#standouts .nbgrid" : "#standouts .cards");
    const quote = market === "ca" ? document.querySelector("#ca-v36-quote-status") : null;
    const prophet = document.querySelector(`#${version}-prophet`);
    const cards = host ? Array.from(host.querySelectorAll(".pvcard")) : [];
    const cardId = (card) => String(card.getAttribute("data-ticker") || "").trim().toUpperCase();
    const selectedSources = prophet ? Array.from(prophet.querySelectorAll(`[data-${prefix}-source][aria-selected="true"]`)) : [];
    const initialSource = prophet ? prophet.getAttribute("data-initial-source") : null;
    const activeSource = prophet ? prophet.getAttribute("data-active-source") : null;
    const source = selectedSources.length === 1 ? selectedSources[0].getAttribute(`data-${prefix}-source`) : null;
    const expectedCards = source === "top"
      ? (market === "hk" ? cards.filter((card) => card.classList.contains("pv-featured")) : cards.slice(0, 5))
      : cards;
    const visibleCards = cards.filter(visible);
    const resultNode = document.querySelector(`#${version}-result`);
    const resultCopy = resultNode ? resultNode.textContent.replace(/\s+/g, " ").trim() : "";
    const viewControls = prophet ? Array.from(prophet.querySelectorAll("[data-prophet-view-control]")) : [];
    const viewButtons = viewControls.length === 1
      ? Array.from(viewControls[0].querySelectorAll(`[data-${prefix}-view]`)) : [];
    const selectedViews = viewButtons.filter((button) => button.getAttribute("aria-selected") === "true");
    const tableButton = viewButtons.find((button) => button.getAttribute(`data-${prefix}-view`) === "table");
    const stockTableReady = !!(window.StockTable && typeof window.StockTable._setView === "function");
    const identity = (items) => items.map(cardId);
    const laneKey = (lane) => lane.getAttribute(`data-${prefix}-an-lane-body`);
    const ownerIdentities = Object.fromEntries(lanes.map((lane) => [
      laneKey(lane),
      Array.from(lane.querySelectorAll(`.${version}-an-row-w`)).map((row) => row.getAttribute("data-action-id")),
    ]));
    const ownerCounts = Object.fromEntries(Object.entries(ownerIdentities).map(([lane, ids]) => [lane, ids.length]));
    const actionHost = document.querySelector(`#${version}-an-body`);
    const enhanced = !!(actionHost && actionHost.classList.contains("is-enhanced"));
    const selectedTabs = tabNodes.filter((tab) => tab.getAttribute("aria-selected") === "true");
    const targetLane = lanes.find((lane) => `#${lane.id}` === location.hash);
    const defaultTab = tabNodes.find((tab) => tab.getAttribute(`data-${prefix}-an-default`) === "true");
    const effectiveLane = enhanced
      ? (selectedTabs[0] && selectedTabs[0].getAttribute(`data-${prefix}-an-lane`))
      : (targetLane && targetLane.getAttribute(`data-${prefix}-an-lane-body`)) ||
        (defaultTab && defaultTab.getAttribute(`data-${prefix}-an-lane`));
    const controls = tabNodes.map((tab) => tab.getAttribute("aria-controls"));
    const controlsValid = tabNodes.every((tab) => {
      const target = document.getElementById(tab.getAttribute("aria-controls") || "");
      return !!target && target.getAttribute(`data-${prefix}-an-lane-body`) === tab.getAttribute(`data-${prefix}-an-lane`);
    });
    const staticSemantics = {
      container_role: actionHost && actionHost.querySelector(`.${version}-an-seg`)?.getAttribute("role"),
      tab_roles: tabNodes.map((tab) => tab.getAttribute("role")),
      aria_selected: tabNodes.map((tab) => tab.getAttribute("aria-selected")),
      aria_current: tabNodes.map((tab) => tab.getAttribute("aria-current")),
      aria_controls: controls,
    };
    const result = {
      tabs,
      visible_lanes: visibleLanes,
      active_row_count: activeRows.length,
      known_membership_hook: !!(known && known.querySelector(`[data-${prefix}-lead-id="FIXTURE-SECTOR"]`)),
      known_copy: known ? known.textContent.replace(/\s+/g, " ").trim() : "",
      unknown_membership_hook: !!(unknown && unknown.querySelector(`[data-${prefix}-lead-id]`)),
      unknown_route: !!(unknown && unknown.querySelector('a[href="sectors/FIXTURE-FINANCE.html"], a[href="sectors/fixture-finance.html"]')),
      generic_showmore_attribute: !!(host && (host.hasAttribute("data-showmore") || host.hasAttribute("data-showmore-rows"))),
      generic_showmore_bar_count: host ? host.querySelectorAll(".sm-bar").length : 0,
      quote_state: quote ? quote.getAttribute("data-quote-state") : null,
      quote_copy: quote ? quote.textContent.replace(/\s+/g, " ").trim() : null,
      source_contract: {
        initial_source: initialSource,
        active_source: activeSource,
        selected_source: source,
        expected_grid: identity(expectedCards),
        visible_grid: identity(visibleCards),
        result_copy: resultCopy,
      },
      prophet_chrome: {
        title_count: prophet ? prophet.querySelectorAll(`:scope > .${version}-sec-hd h2`).length : 0,
        result_count: prophet ? prophet.querySelectorAll(`#${version}-result`).length : 0,
        owner_context_count: prophet ? prophet.querySelectorAll("[data-prophet-owner-context]").length : 0,
        vintage_count: prophet ? prophet.querySelectorAll("[data-prophet-vintage]").length : 0,
        help_count: prophet ? prophet.querySelectorAll("[data-prophet-help]").length : 0,
        legacy_view_count: prophet ? prophet.querySelectorAll("#st-view-toggle, #st-btn-grid, #st-btn-table").length : 0,
      },
      view_owner: {
        control_count: viewControls.length,
        button_count: viewButtons.length,
        selected: selectedViews.length === 1 ? selectedViews[0].getAttribute(`data-${prefix}-view`) : null,
        table_disabled: !!(tableButton && tableButton.disabled),
        stocktable_ready: stockTableReady,
      },
      wtaon: {
        enhanced,
        selected_lane_key: effectiveLane || null,
        selector_count: actionHost ? actionHost.querySelectorAll(`.${version}-an-seg[role="tablist"]`).length : 0,
        button_count: tabNodes.length,
        visible_lane_body_count: visibleLanes.length,
        per_lane_owner_count: ownerCounts,
        rendered_visible_row_count: activeRows.length,
        expanded: !!lanes.find((lane) => {
          return !!lane.querySelector(`details[data-${prefix}-an-disclosure][open]`);
        }),
        focus_keyboard: {exercised: false, sequence: [], focus_visible: [], enter: false, space: false, pass: true},
        aria_controls: {unique: new Set(controls.filter(Boolean)).size, valid: controlsValid},
        static_semantics: staticSemantics,
        owner_identity_order: ownerIdentities,
      },
    };
    result.source_contract.pass = selectedSources.length === 1 && source === initialSource && activeSource === source &&
      JSON.stringify(result.source_contract.expected_grid) === JSON.stringify(result.source_contract.visible_grid) &&
      resultCopy.includes(`${expectedCards.length} actionable cards shown`);
    result.prophet_chrome.pass = result.prophet_chrome.title_count === 1 && result.prophet_chrome.result_count === 1 &&
      result.prophet_chrome.owner_context_count === 1 && result.prophet_chrome.vintage_count === 1 &&
      result.prophet_chrome.help_count === 1 && result.prophet_chrome.legacy_view_count === 0;
    result.view_owner.pass = result.view_owner.control_count === 1 && result.view_owner.button_count === 2 &&
      result.view_owner.selected === "grid" && result.view_owner.table_disabled === !stockTableReady;
    const staticSemanticsHonest = !staticSemantics.container_role &&
      staticSemantics.tab_roles.every((value) => value === null) &&
      staticSemantics.aria_selected.every((value) => value === null) &&
      staticSemantics.aria_current.every((value) => value === null) &&
      staticSemantics.aria_controls.every((value) => value === null);
    result.wtaon.pass = result.wtaon.selected_lane_key === "buy" &&
      result.wtaon.button_count === 4 && result.wtaon.visible_lane_body_count === 1 &&
      (enhanced
        ? result.wtaon.selector_count === 1 && selectedTabs.length === 1 &&
          result.wtaon.aria_controls.unique === 4 && result.wtaon.aria_controls.valid
        : result.wtaon.selector_count === 0 && staticSemanticsHonest);
    result.pass = tabs.length === 4 && tabs.every((tab) => tab.title && /^\d+$/.test(tab.count.trim()) && tab.title_fully_visible) &&
      visibleLanes.length === 1 && visibleLanes[0] === "buy" && activeRows.length <= 3 &&
      result.known_membership_hook && /2\s*·\s*Prophet/.test(result.known_copy) &&
      !result.unknown_membership_hook && result.unknown_route &&
      !result.generic_showmore_attribute && result.generic_showmore_bar_count === 0 &&
      (market !== "ca" || (result.quote_state === "unavailable" && /Quotes unavailable/.test(result.quote_copy))) &&
      result.source_contract.pass && result.prophet_chrome.pass && result.view_owner.pass && result.wtaon.pass;
    return result;
  }, {prefix, version, market});

  const beforeIdentity = basic.wtaon.owner_identity_order;
  basic.wtaon.identity_hashes = {
    before: sha256Bytes(Buffer.from(JSON.stringify(beforeIdentity))),
    after: null,
  };
  delete basic.wtaon.owner_identity_order;

  const exercised = [];
  if (javascriptEnabled && composerMode === "loaded") {
    const sourceBefore = await page.locator(`[data-${prefix}-source][aria-selected="true"]`).getAttribute(`data-${prefix}-source`);
    for (const lane of ["near", "wait", "avoid", "buy"]) {
      await page.locator(`[data-${prefix}-an-lane="${lane}"]`).click();
      const state = await page.evaluate(({prefix, lane, sourceBefore}) => {
        const visible = (el) => getComputedStyle(el).display !== "none" && el.getClientRects().length > 0;
        const visibleLanes = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`))
          .filter(visible).map((el) => el.getAttribute(`data-${prefix}-an-lane-body`));
        const source = document.querySelector(`[data-${prefix}-source][aria-selected="true"]`);
        return {
          lane,
          visible_lanes: visibleLanes,
          source_unchanged: !!source && source.getAttribute(`data-${prefix}-source`) === sourceBefore,
        };
      }, {prefix, lane, sourceBefore});
      state.pass = state.visible_lanes.length === 1 && state.visible_lanes[0] === lane && state.source_unchanged;
      exercised.push(state);
    }

    const keyboardSequence = [];
    const focusVisibility = [];
    const buyTab = page.locator(`[data-${prefix}-an-lane="buy"]`);
    await buyTab.focus();
    for (const key of ["ArrowRight", "End", "Home", "ArrowLeft", "ArrowLeft"]) {
      await page.keyboard.press(key);
      const keyState = await page.evaluate(({prefix}) => {
        const selected = document.querySelector(`[data-${prefix}-an-lane][aria-selected="true"]`);
        const focused = document.activeElement && document.activeElement.closest(`[data-${prefix}-an-lane]`);
        const selectedLane = selected && selected.getAttribute(`data-${prefix}-an-lane`);
        const focusedLane = focused && focused.getAttribute(`data-${prefix}-an-lane`);
        const focusStyle = focused ? getComputedStyle(focused) : null;
        return {
          lane: selectedLane === focusedLane ? selectedLane : null,
          visible: !!focusStyle && focusStyle.outlineStyle !== "none" && parseFloat(focusStyle.outlineWidth) > 0,
        };
      }, {prefix});
      keyboardSequence.push(keyState.lane);
      focusVisibility.push(keyState.visible);
    }
    await page.keyboard.press("Enter");
    const enterWorked = await page.evaluate(({prefix}) => {
      const selected = document.querySelector(`[data-${prefix}-an-lane][aria-selected="true"]`);
      return !!selected && selected.getAttribute(`data-${prefix}-an-lane`) === "wait";
    }, {prefix});
    await page.keyboard.press("Space");
    const spaceWorked = await page.evaluate(({prefix}) => {
      const selected = document.querySelector(`[data-${prefix}-an-lane][aria-selected="true"]`);
      return !!selected && selected.getAttribute(`data-${prefix}-an-lane`) === "wait";
    }, {prefix});
    basic.wtaon.focus_keyboard = {
      exercised: true,
      sequence: keyboardSequence,
      focus_visible: focusVisibility,
      enter: enterWorked,
      space: spaceWorked,
      pass: JSON.stringify(keyboardSequence) === JSON.stringify(["near", "avoid", "buy", "avoid", "wait"]) &&
        focusVisibility.length === keyboardSequence.length && focusVisibility.every(Boolean) && enterWorked && spaceWorked,
    };
    await buyTab.click();

    const more = page.locator(`[data-${prefix}-an-lane-body="buy"] .${version}-an-more`);
    const visibleRowCounts = () => page.evaluate(({prefix, version}) => Object.fromEntries(
      Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`)).map((lane) => [
        lane.getAttribute(`data-${prefix}-an-lane-body`),
        Array.from(lane.querySelectorAll(`.${version}-an-row-w`)).filter((row) =>
          getComputedStyle(row).display !== "none" && row.getClientRects().length > 0
        ).length,
      ])
    ), {prefix, version});
    const beforeCounts = await visibleRowCounts();
    if (await more.count()) {
      await more.focus();
      await page.evaluate(({prefix, version}) => {
        const summary = document.querySelector(`[data-${prefix}-an-lane-body="buy"] .${version}-an-more`);
        const list = document.querySelector(`[data-${prefix}-an-lane-body="buy"] .${version}-an-list`);
        const disclosure = document.querySelector(`[data-${prefix}-an-lane-body="buy"] details[data-${prefix}-an-disclosure]`);
        window.__wtaonViewAllProbe = {
          summary,
          disclosure,
          list,
          parent: disclosure && disclosure.parentNode,
        };
      }, {prefix, version});
      await more.click();
    }
    const afterCounts = await visibleRowCounts();
    const viewAllOwnership = await page.evaluate(({prefix, version}) => {
      const probe = window.__wtaonViewAllProbe || {};
      const lane = document.querySelector(`[data-${prefix}-an-lane-body="buy"]`);
      const summary = lane && lane.querySelector(`.${version}-an-more`);
      const list = lane && lane.querySelector(`.${version}-an-list`);
      const disclosure = lane && lane.querySelector(`details[data-${prefix}-an-disclosure]`);
      return {
        same_summary: probe.summary === summary,
        same_disclosure: probe.disclosure === disclosure,
        same_list: probe.list === list,
        same_parent: probe.parent === (disclosure && disclosure.parentNode),
        focus_retained: document.activeElement === summary,
        disclosure_stayed_in_lane: !!(lane && disclosure && lane.contains(disclosure)),
        list_stayed_in_lane: !!(lane && list && lane.contains(list)),
        global_overlay_count: document.querySelectorAll(".lst-ovl.is-open, .lst-ovl-body > .hk-v37-an-list, .lst-ovl-body > .ca-v36-an-list").length,
      };
    }, {prefix, version});
    await page.locator(`[data-${prefix}-an-lane="near"]`).click();
    const awayExpansion = await page.evaluate(({prefix}) => {
      const selected = document.querySelector(`[data-${prefix}-an-lane][aria-selected="true"]`);
      const expanded = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`))
        .filter((lane) => lane.querySelector(`details[data-${prefix}-an-disclosure][open]`))
        .map((lane) => lane.getAttribute(`data-${prefix}-an-lane-body`));
      return {
        selected: selected && selected.getAttribute(`data-${prefix}-an-lane`),
        expanded_lanes: expanded,
      };
    }, {prefix});
    await buyTab.click();
    const expansion = await page.evaluate(({prefix}) => {
      const lanes = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`));
      const visible = (el) => getComputedStyle(el).display !== "none" && el.getClientRects().length > 0;
      return {
        visible_lanes: lanes.filter(visible).map((el) => el.getAttribute(`data-${prefix}-an-lane-body`)),
        expanded_lanes: lanes.filter((lane) => lane.querySelector(`details[data-${prefix}-an-disclosure][open]`))
          .map((lane) => lane.getAttribute(`data-${prefix}-an-lane-body`)),
      };
    }, {prefix});
    basic.view_all = {
      before: beforeCounts.buy,
      after: afterCounts.buy,
      per_lane_before: beforeCounts,
      per_lane_after: afterCounts,
      active_only: expansion.visible_lanes.length === 1 && expansion.visible_lanes[0] === "buy" &&
        JSON.stringify(expansion.expanded_lanes) === JSON.stringify(["buy"]),
      lane_local_after_switch: awayExpansion.selected === "near" &&
        JSON.stringify(awayExpansion.expanded_lanes) === JSON.stringify(["buy"]),
      ownership: viewAllOwnership,
      pass: beforeCounts.buy === 3 && afterCounts.buy === 4 &&
        Object.entries(afterCounts).every(([lane, count]) => lane === "buy" || count === beforeCounts[lane]) &&
        expansion.visible_lanes.length === 1 && expansion.visible_lanes[0] === "buy" &&
        JSON.stringify(expansion.expanded_lanes) === JSON.stringify(["buy"]) &&
        awayExpansion.selected === "near" &&
        JSON.stringify(awayExpansion.expanded_lanes) === JSON.stringify(["buy"]) &&
        viewAllOwnership.same_summary && viewAllOwnership.same_disclosure &&
        viewAllOwnership.same_list && viewAllOwnership.same_parent &&
        viewAllOwnership.focus_retained && viewAllOwnership.disclosure_stayed_in_lane &&
        viewAllOwnership.list_stayed_in_lane &&
        viewAllOwnership.global_overlay_count === 0,
    };
    basic.wtaon.expanded = expansion.expanded_lanes.length === 1 && expansion.expanded_lanes[0] === "buy";
    basic.wtaon.rendered_visible_row_count = afterCounts.buy;
  } else {
    const fallbackCases = [];
    for (const lane of ["buy", "near", "wait", "avoid"]) {
      await page.locator(`[data-${prefix}-an-lane="${lane}"]`).click();
      await page.waitForTimeout(30);
      const fallback = await page.evaluate(({prefix, version, lane}) => {
        const visible = (el) => getComputedStyle(el).display !== "none" && el.getClientRects().length > 0;
        const controls = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane]`));
        const lanes = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`));
        const target = controls.find((control) => control.getAttribute(`data-${prefix}-an-lane`) === lane);
        const signature = (control) => {
          const style = getComputedStyle(control);
          return [style.backgroundColor, style.color, style.borderTopColor, style.boxShadow].join("|");
        };
        const targetSignature = target ? signature(target) : null;
        const highlighted = controls.filter((control) => signature(control) === targetSignature);
        const body = document.querySelector(`#${version}-an-body`);
        const laneBody = lanes.find((node) => node.getAttribute(`data-${prefix}-an-lane-body`) === lane);
        const count = Number((target && target.querySelector("b") || {}).textContent || NaN);
        const rowCount = laneBody ? laneBody.querySelectorAll(`.${version}-an-row-w`).length : -1;
        return {
          lane,
          visible_lane_keys: lanes.filter(visible).map((node) => node.getAttribute(`data-${prefix}-an-lane-body`)),
          highlighted_control: highlighted.length === 1 ? highlighted[0].getAttribute(`data-${prefix}-an-lane`) : null,
          url_fragment: location.hash,
          owner_count: count,
          owner_row_count: rowCount,
          enhanced: !!(body && body.classList.contains("is-enhanced")),
          semantics: {
            container_role: body && body.querySelector(`.${version}-an-seg`)?.getAttribute("role"),
            tab_roles: controls.map((control) => control.getAttribute("role")),
            aria_selected: controls.map((control) => control.getAttribute("aria-selected")),
            aria_current: controls.map((control) => control.getAttribute("aria-current")),
            aria_controls: controls.map((control) => control.getAttribute("aria-controls")),
          },
        };
      }, {prefix, version, lane});
      const semantics = fallback.semantics;
      fallback.pass = fallback.visible_lane_keys.length === 1 && fallback.visible_lane_keys[0] === lane &&
        fallback.highlighted_control === lane && fallback.url_fragment ===
          `#${lane === "near" ? "anv2-pull" : lane === "wait" ? "anv2-bot" : lane === "avoid" ? "anv2-red" : "anv2-buy"}` &&
        fallback.owner_count === fallback.owner_row_count && !fallback.enhanced && !semantics.container_role &&
        semantics.tab_roles.every((value) => value === null) &&
        semantics.aria_selected.every((value) => value === null) &&
        semantics.aria_current.every((value) => value === null) &&
        semantics.aria_controls.every((value) => value === null);
      fallbackCases.push(fallback);
    }
    basic.static_anchor_fallback = {
      cases: fallbackCases,
      pass: fallbackCases.length === 4 && fallbackCases.every((row) => row.pass),
    };
  }
  if (javascriptEnabled && composerMode !== "pending") {
    const tableButton = page.locator(`[data-${prefix}-view="table"]`);
    if (await tableButton.count() && !(await tableButton.isDisabled())) {
      await tableButton.click();
      await page.waitForTimeout(50);
      const tableState = await page.evaluate(({market, prefix, version}) => {
        const visible = (el) => getComputedStyle(el).display !== "none" && el.getClientRects().length > 0;
        const prophet = document.querySelector(`#${version}-prophet`);
        const cardHost = document.querySelector(market === "hk" ? "#standouts .nbgrid" : "#standouts .cards");
        const cards = cardHost ? Array.from(cardHost.querySelectorAll(".pvcard")) : [];
        const source = prophet && prophet.querySelector(`[data-${prefix}-source][aria-selected="true"]`);
        const sourceName = source ? source.getAttribute(`data-${prefix}-source`) : null;
        const expected = sourceName === "top"
          ? (market === "hk" ? cards.filter((card) => card.classList.contains("pv-featured")) : cards.slice(0, 5))
          : cards;
        const expectedIds = expected.map((card) => String(card.getAttribute("data-ticker") || "").trim().toUpperCase());
        const tableRows = Array.from(document.querySelectorAll("#stocktable-wrap tbody tr")).filter(visible);
        const tableIds = tableRows.map((row) => String(row.getAttribute("data-ticker") || "").trim().toUpperCase());
        const selectedViews = prophet ? Array.from(prophet.querySelectorAll(`[data-${prefix}-view][aria-selected="true"]`)) : [];
        const board = document.querySelector("#standouts");
        return {
          source: sourceName,
          expected: expectedIds,
          visible_table: tableIds,
          selected_view: selectedViews.length === 1 ? selectedViews[0].getAttribute(`data-${prefix}-view`) : null,
          owner_active_view: prophet ? prophet.getAttribute("data-active-view") : null,
          table_mode: !!(board && board.classList.contains("st-table-mode")),
          control_count: prophet ? prophet.querySelectorAll("[data-prophet-view-control]").length : 0,
        };
      }, {market, prefix, version});
      tableState.pass = tableState.selected_view === "table" && tableState.owner_active_view === "table" &&
        tableState.table_mode && tableState.control_count === 1 &&
        JSON.stringify(tableState.expected) === JSON.stringify(tableState.visible_table);
      await page.locator(`[data-${prefix}-view="grid"]`).click();
      await page.waitForTimeout(50);
      const gridRestored = await page.evaluate(({prefix, version}) => {
        const prophet = document.querySelector(`#${version}-prophet`);
        const board = document.querySelector("#standouts");
        const selected = prophet && prophet.querySelector(`[data-${prefix}-view][aria-selected="true"]`);
        return !!selected && selected.getAttribute(`data-${prefix}-view`) === "grid" &&
          prophet.getAttribute("data-active-view") === "grid" && !!board && !board.classList.contains("st-table-mode");
      }, {prefix, version});
      basic.view_transition = {...tableState, grid_restored: gridRestored, pass: tableState.pass && gridRestored};
    }
  }
  const afterIdentity = await page.evaluate(({prefix, version}) => Object.fromEntries(
    Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`)).map((lane) => [
      lane.getAttribute(`data-${prefix}-an-lane-body`),
      Array.from(lane.querySelectorAll(`.${version}-an-row-w`)).map((row) => row.getAttribute("data-action-id")),
    ])
  ), {prefix, version});
  basic.wtaon.identity_hashes.after = sha256Bytes(Buffer.from(JSON.stringify(afterIdentity)));
  basic.wtaon.node_identity = javascriptEnabled
    ? await nodeIdentityProof(page, market)
    : {captured: false, reason: "javascript_disabled", pass: true};
  basic.wtaon.pass = basic.wtaon.pass && basic.wtaon.focus_keyboard.pass &&
    basic.wtaon.identity_hashes.before === basic.wtaon.identity_hashes.after &&
    basic.wtaon.node_identity.pass;
  basic.exercised_lanes = exercised;
  basic.pass = basic.pass && exercised.every((row) => row.pass) &&
    (!basic.view_all || basic.view_all.pass) &&
    (!basic.static_anchor_fallback || basic.static_anchor_fallback.pass) &&
    (!basic.view_transition || basic.view_transition.pass) && basic.wtaon.pass;
  return basic;
}

async function fragmentNavigationProof(browser, market, route, installRoutes) {
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  const context = await browser.newContext({viewport: {width: 390, height: 844}, deviceScaleFactor: 1});
  await installPageInit(context, market, "en", "dark");
  await installRoutes(context, "loaded");

  async function waitForComposer(page) {
    await page.waitForFunction(({version}) => {
      const host = document.querySelector(`#${version}-an-body`);
      return !!(host && host.classList.contains("is-enhanced"));
    }, {version}, {timeout: 5000});
    await page.waitForTimeout(50);
  }

  async function inspect(page, label, expectedLane, expectedHash, focusRequired) {
    const state = await page.evaluate(({prefix, version, label}) => {
      const visible = (node) => getComputedStyle(node).display !== "none" && node.getClientRects().length > 0;
      const host = document.querySelector(`#${version}-an-body`);
      const controls = Array.from(host.querySelectorAll(`[data-${prefix}-an-lane]`));
      const lanes = Array.from(host.querySelectorAll(`[data-${prefix}-an-lane-body]`));
      const selected = controls.filter((control) => control.getAttribute("aria-selected") === "true");
      const current = lanes.filter((lane) => lane.classList.contains("is-current"));
      const shown = lanes.filter(visible);
      const focused = document.activeElement && document.activeElement.closest &&
        document.activeElement.closest(`[data-${prefix}-an-lane]`);
      return {
        label,
        url_fragment: location.hash,
        internal_active_key: host.getAttribute("data-active-lane"),
        selected_keys: selected.map((node) => node.getAttribute(`data-${prefix}-an-lane`)),
        current_keys: current.map((node) => node.getAttribute(`data-${prefix}-an-lane-body`)),
        visible_keys: shown.map((node) => node.getAttribute(`data-${prefix}-an-lane-body`)),
        focused_key: focused ? focused.getAttribute(`data-${prefix}-an-lane`) : null,
        selector_roles: host.querySelectorAll(`.${version}-an-seg[role="tablist"]`).length,
        tab_roles: controls.filter((node) => node.getAttribute("role") === "tab").length,
        controls_valid: controls.every((control) => {
          const lane = document.getElementById(control.getAttribute("aria-controls") || "");
          return !!lane && lane.getAttribute(`data-${prefix}-an-lane-body`) ===
            control.getAttribute(`data-${prefix}-an-lane`);
        }),
      };
    }, {prefix, version, label});
    state.focus_required = focusRequired;
    state.pass = state.url_fragment === expectedHash && state.internal_active_key === expectedLane &&
      JSON.stringify(state.selected_keys) === JSON.stringify([expectedLane]) &&
      JSON.stringify(state.current_keys) === JSON.stringify([expectedLane]) &&
      JSON.stringify(state.visible_keys) === JSON.stringify([expectedLane]) &&
      (!focusRequired || state.focused_key === expectedLane) && state.selector_roles === 1 &&
      state.tab_roles === 4 && state.controls_valid;
    return state;
  }

  const errors = [];
  try {
    const validPage = await context.newPage();
    validPage.on("pageerror", (error) => errors.push(String(error && (error.stack || error.message) || error)));
    const validUrl = new URL(route, "http://stock-dashboard.invalid");
    validUrl.hash = "anv2-pull";
    await validPage.goto(validUrl.href, {waitUntil: "load", timeout: 30000});
    await waitForComposer(validPage);
    const cases = [await inspect(validPage, "direct-valid", "near", "#anv2-pull", false)];

    await validPage.locator(`[data-${prefix}-an-lane="wait"]`).click();
    cases.push(await inspect(validPage, "click-with-fragment", "wait", "#anv2-bot", true));
    await validPage.locator(`[data-${prefix}-an-lane="avoid"]`).click();
    cases.push(await inspect(validPage, "second-click", "avoid", "#anv2-red", true));
    await validPage.goBack();
    await validPage.waitForTimeout(50);
    cases.push(await inspect(validPage, "back", "wait", "#anv2-bot", true));
    await validPage.goForward();
    await validPage.waitForTimeout(50);
    cases.push(await inspect(validPage, "forward", "avoid", "#anv2-red", true));
    const validIdentity = await nodeIdentityProof(validPage, market);

    const invalidPage = await context.newPage();
    invalidPage.on("pageerror", (error) => errors.push(String(error && (error.stack || error.message) || error)));
    const invalidUrl = new URL(route, "http://stock-dashboard.invalid");
    invalidUrl.hash = "anv2-unknown";
    await invalidPage.goto(invalidUrl.href, {waitUntil: "load", timeout: 30000});
    await waitForComposer(invalidPage);
    const invalid = await inspect(invalidPage, "direct-invalid", "buy", "#anv2-buy", false);
    const invalidIdentity = await nodeIdentityProof(invalidPage, market);
    return {
      cases: cases.concat([invalid]),
      node_identity: {valid_page: validIdentity, invalid_page: invalidIdentity},
      console_exceptions: errors,
      pass: cases.concat([invalid]).every((row) => row.pass) &&
        validIdentity.pass && invalidIdentity.pass && errors.length === 0,
    };
  } finally {
    await context.close();
  }
}

async function desktopBehavior(page, market) {
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  const hostSelector = market === "hk" ? "#standouts .nbgrid" : "#standouts .cards";
  async function manifest(label) {
    return page.evaluate(({label, market, prefix, hostSelector}) => {
      const cards = Array.from(document.querySelectorAll(`${hostSelector} .pvcard`));
      const rowsNode = document.querySelector("#stocktable-data");
      let rows = [];
      try { rows = JSON.parse((rowsNode && rowsNode.textContent) || "{}").rows || []; } catch (_error) {}
      const sourceNode = document.querySelector(`[data-${prefix}-source][aria-selected="true"]`);
      const source = sourceNode ? sourceNode.getAttribute(`data-${prefix}-source`) : null;
      let expected = cards.slice();
      if (source === "top") {
        expected = market === "hk" ? cards.filter((card) => card.classList.contains("pv-featured")) : cards.slice(0, 5);
      }
      const filter = document.querySelector(`[data-${prefix}-lead-id="FIXTURE-SECTOR"].is-active`);
      if (filter) {
        const members = new Set(rows.filter((row) => row && row.sector === "Fixture sector")
          .map((row) => String(row.ticker || "").trim().toUpperCase()));
        expected = expected.filter((card) => members.has(String(card.getAttribute("data-ticker") || "").trim().toUpperCase()));
      }
      const names = (items) => items.map((card) => String(card.getAttribute("data-ticker") || "").trim().toUpperCase());
      const actual = cards.filter((card) => !card.hidden && getComputedStyle(card).display !== "none");
      const selectedSmHidden = expected.filter((card) => card.classList.contains("sm-hidden"));
      const viewNodes = Array.from(document.querySelectorAll(`[data-${prefix}-view][aria-selected="true"]`));
      const view = viewNodes.length === 1 ? viewNodes[0].getAttribute(`data-${prefix}-view`) : null;
      const board = document.querySelector("#standouts");
      const visible = (el) => !!el && getComputedStyle(el).display !== "none" && el.getClientRects().length > 0;
      const tableRows = Array.from(document.querySelectorAll("#stocktable-wrap tbody tr")).filter(visible);
      const tableIds = tableRows.map((row) => String(row.getAttribute("data-ticker") || "").trim().toUpperCase());
      const expectedIds = names(expected);
      const tableIdentity = view !== "table" || JSON.stringify(expectedIds) === JSON.stringify(tableIds);
      const viewConsistent = (view === "table") === !!(board && board.classList.contains("st-table-mode"));
      const result = document.querySelector(`#${market === "hk" ? "hk-v37" : "ca-v36"}-result`);
      const resultCopy = result ? result.textContent.replace(/\s+/g, " ").trim() : "";
      return {
        label,
        source,
        filter: !!filter,
        expected: expectedIds,
        visible: names(actual),
        view,
        visible_table: tableIds,
        owner_active_source: document.querySelector(`#${market === "hk" ? "hk-v37" : "ca-v36"}-prophet`)?.getAttribute("data-active-source") || null,
        owner_active_view: document.querySelector(`#${market === "hk" ? "hk-v37" : "ca-v36"}-prophet`)?.getAttribute("data-active-view") || null,
        view_control_count: document.querySelectorAll(`#${market === "hk" ? "hk-v37" : "ca-v36"}-prophet [data-prophet-view-control]`).length,
        table_mode: !!(board && board.classList.contains("st-table-mode")),
        table_visible: visible(document.querySelector("#stocktable-wrap")),
        grid_visible: visible(document.querySelector("#standouts .nb-grid-section")),
        result_copy: resultCopy,
        selected_sm_hidden: names(selectedSmHidden),
        pass: JSON.stringify(expectedIds) === JSON.stringify(names(actual)) && selectedSmHidden.length === 0 &&
          tableIdentity && viewConsistent && viewNodes.length === 1 &&
          document.querySelectorAll(`#${market === "hk" ? "hk-v37" : "ca-v36"}-prophet [data-prophet-view-control]`).length === 1 &&
          document.querySelector(`#${market === "hk" ? "hk-v37" : "ca-v36"}-prophet`)?.getAttribute("data-active-source") === source &&
          document.querySelector(`#${market === "hk" ? "hk-v37" : "ca-v36"}-prophet`)?.getAttribute("data-active-view") === view &&
          (view === "table" ? visible(document.querySelector("#stocktable-wrap")) && !visible(document.querySelector("#standouts .nb-grid-section"))
            : !visible(document.querySelector("#stocktable-wrap")) && visible(document.querySelector("#standouts .nb-grid-section"))) &&
          resultCopy.includes(`${expectedIds.length} actionable cards shown`),
      };
    }, {label, market, prefix, hostSelector});
  }

  const initial = await page.evaluate(({market, prefix, version, hostSelector}) => {
    const panel = document.querySelector(`#${version}-actnow`);
    const prophet = document.querySelector(`#${version}-prophet`);
    const lanes = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`));
    const visible = (el) => getComputedStyle(el).display !== "none" && el.getClientRects().length > 0;
    const laneRows = Object.fromEntries(lanes.map((lane) => [
      lane.getAttribute(`data-${prefix}-an-lane-body`),
      Array.from(lane.querySelectorAll(`.${version}-an-row-w`)).filter(visible).length,
    ]));
    const host = document.querySelector(hostSelector);
    const selectedSources = prophet ? Array.from(prophet.querySelectorAll(`[data-${prefix}-source][aria-selected="true"]`)) : [];
    return {
      action_panel_height: panel ? Math.round(panel.getBoundingClientRect().height * 100) / 100 : null,
      prophet_top: prophet ? Math.round(prophet.getBoundingClientRect().top * 100) / 100 : null,
      lane_rows: laneRows,
      visible_lane_count: lanes.filter(visible).length,
      generic_showmore_attribute: !!(host && (host.hasAttribute("data-showmore") || host.hasAttribute("data-showmore-rows"))),
      generic_showmore_bar_count: host ? host.querySelectorAll(".sm-bar").length : 0,
      initial_source: prophet ? prophet.getAttribute("data-initial-source") : null,
      selected_source: selectedSources.length === 1 ? selectedSources[0].getAttribute(`data-${prefix}-source`) : null,
      title_count: prophet ? prophet.querySelectorAll(`:scope > .${version}-sec-hd h2`).length : 0,
      result_count: prophet ? prophet.querySelectorAll(`#${version}-result`).length : 0,
      owner_context_count: prophet ? prophet.querySelectorAll("[data-prophet-owner-context]").length : 0,
      vintage_count: prophet ? prophet.querySelectorAll("[data-prophet-vintage]").length : 0,
      help_count: prophet ? prophet.querySelectorAll("[data-prophet-help]").length : 0,
      view_control_count: prophet ? prophet.querySelectorAll("[data-prophet-view-control]").length : 0,
      legacy_view_count: prophet ? prophet.querySelectorAll("#st-view-toggle, #st-btn-grid, #st-btn-table").length : 0,
    };
  }, {market, prefix, version, hostSelector});
  initial.source_manifest = await manifest("initial-grid");
  initial.pass = initial.action_panel_height !== null && initial.action_panel_height <= 240 &&
    initial.prophet_top !== null && initial.prophet_top < 900 && initial.visible_lane_count === 4 &&
    Object.values(initial.lane_rows).every((count) => count <= 3) &&
    !initial.generic_showmore_attribute && initial.generic_showmore_bar_count === 0 &&
    initial.initial_source === initial.selected_source && initial.title_count === 1 && initial.result_count === 1 &&
    initial.owner_context_count === 1 && initial.vintage_count === 1 && initial.help_count === 1 &&
    initial.view_control_count === 1 && initial.legacy_view_count === 0 && initial.source_manifest.pass;

  const sequence = [];
  await page.locator(`[data-${prefix}-view="table"]`).click();
  await page.waitForTimeout(50);
  sequence.push(await manifest("initial-table"));
  await page.reload({waitUntil: "load", timeout: 30000});
  await page.waitForTimeout(1500);
  const persistedTable = await manifest("persisted-table-startup");
  persistedTable.persisted_view = await page.evaluate(({prefix}) => localStorage.getItem(`mdx_stocktable_${prefix}_view`), {prefix});
  persistedTable.pass = persistedTable.pass && persistedTable.view === "table" && persistedTable.persisted_view === "table";
  sequence.push(persistedTable);
  await page.locator(`[data-${prefix}-view="grid"]`).click();
  await page.locator(`[data-${prefix}-source="top"]`).click();
  sequence.push(await manifest("top-grid"));
  await page.locator(`[data-${prefix}-view="table"]`).click();
  sequence.push(await manifest("top-table"));
  await page.locator(`[data-${prefix}-view="grid"]`).click();
  await page.locator(`[data-${prefix}-source="all"]`).click();
  sequence.push(await manifest("all-grid"));
  await page.locator(`[data-${prefix}-view="table"]`).click();
  sequence.push(await manifest("all-table"));
  await page.locator(`[data-${prefix}-view="grid"]`).click();
  await page.locator(`[data-${prefix}-lead-id="FIXTURE-SECTOR"]`).first().click();
  const sourceAfterGroup = await page.locator(`[data-${prefix}-source][aria-selected="true"]`).getAttribute(`data-${prefix}-source`);
  const group = await manifest("group");
  group.source_unchanged = sourceAfterGroup === "all";
  group.pass = group.pass && group.source_unchanged && group.visible.length === 2;
  sequence.push(group);
  await page.locator(`#${version}-filter`).click();
  sequence.push(await manifest("clear"));
  await page.setViewportSize({width: 390, height: 844});
  sequence.push(await manifest("resized-390"));
  await page.setViewportSize({width: 1440, height: 900});
  sequence.push(await manifest("resized-1440"));

  await page.evaluate((hostSelector) => {
    const card = document.querySelector(`${hostSelector} .pvcard:not([hidden])`);
    if (card) {
      card.classList.add("sm-hidden");
      card.style.animationDelay = "999s";
    }
  }, hostSelector);
  await page.locator(`[data-${prefix}-source="top"]`).click();
  await page.locator(`[data-${prefix}-source="all"]`).click();
  const healed = await manifest("legacy-class-healed");
  const delayResidue = await page.evaluate((hostSelector) => Array.from(document.querySelectorAll(`${hostSelector} .pvcard`))
    .some((card) => card.style.animationDelay), hostSelector);
  healed.animation_delay_residue = delayResidue;
  healed.pass = healed.pass && !delayResidue;
  sequence.push(healed);

  let quoteCases = [];
  if (market === "ca") {
    const quoteCellsBefore = await page.evaluate(() => ({
      cards: Array.from(document.querySelectorAll('#ca-v36-card-grid .nb-px[data-mkt="ca"]')).map((el) => el.textContent),
      table: Array.from(document.querySelectorAll('#stocktable-wrap .ca-v36-table-live .nb-px')).map((el) => el.textContent),
    }));
    const cases = [
      {name: "missing", value: null, title: null, expected: "unavailable"},
      {name: "malformed", value: "1", title: "untyped fixture", expected: "unavailable"},
      {name: "live", value: "1", title: "live · fixture-feed · 0m ago", expected: "live"},
      {name: "delayed", value: "delayed", title: "≥15-min delayed · fixture-feed · 15m ago", expected: "delayed"},
      {name: "stale", value: "stale", title: "stale · fixture-feed · 45m ago", expected: "stale"},
      {name: "closed", value: "closed", title: "market closed · fixture-feed · 45m ago", expected: "closed"},
    ];
    for (const fixtureCase of cases) {
      await page.evaluate((fixtureCase) => {
        document.querySelectorAll('#ca-v36-card-grid .nb-px[data-mkt="ca"]').forEach((node) => {
          if (fixtureCase.value === null) node.removeAttribute("data-live");
          else node.setAttribute("data-live", fixtureCase.value);
          if (fixtureCase.title === null) node.removeAttribute("title");
          else node.setAttribute("title", fixtureCase.title);
        });
      }, fixtureCase);
      await page.waitForTimeout(50);
      const observed = await page.evaluate(() => {
        const status = document.querySelector("#ca-v36-quote-status");
        return {
          state: status && status.getAttribute("data-quote-state"),
          copy: status ? status.textContent.replace(/\s+/g, " ").trim() : "",
          candidate_count: document.querySelectorAll("#ca-v36-card-grid .pvcard").length,
        };
      });
      const hasBasis = ["live", "delayed", "stale", "closed"].includes(fixtureCase.expected)
        ? observed.copy.includes("fixture-feed") : true;
      quoteCases.push({
        name: fixtureCase.name,
        expected: fixtureCase.expected,
        ...observed,
        pass: observed.state === fixtureCase.expected && hasBasis && observed.candidate_count > 0 &&
          (fixtureCase.expected !== "unavailable" || !observed.copy.includes("2026-09-03")),
      });
    }
    const quoteCellsAfter = await page.evaluate(() => ({
      cards: Array.from(document.querySelectorAll('#ca-v36-card-grid .nb-px[data-mkt="ca"]')).map((el) => el.textContent),
      table: Array.from(document.querySelectorAll('#stocktable-wrap .ca-v36-table-live .nb-px')).map((el) => el.textContent),
    }));
    quoteCases.push({
      name: "quote-cells-preserved",
      before: quoteCellsBefore,
      after: quoteCellsAfter,
      pass: JSON.stringify(quoteCellsBefore) === JSON.stringify(quoteCellsAfter) && quoteCellsBefore.cards.length > 0,
    });
  }

  return {
    viewport: {width: 1440, height: 900},
    initial,
    sequence,
    quote_cases: quoteCases,
    pass: initial.pass && sequence.every((row) => row.pass) && quoteCases.every((row) => row.pass),
  };
}

async function ownerProjectionSnapshot(page, market, overlayPayload) {
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  return page.evaluate(({market, prefix, version, overlayPayload}) => {
    const visible = (el) => {
      if (!el) return false;
      const style = getComputedStyle(el);
      return style.display !== "none" && style.visibility !== "hidden" &&
        el.getClientRects().length > 0;
    };
    const clean = (value) => String(value || "").replace(/\s+/g, " ").trim();
    const hashTicker = (href) => {
      const raw = String(href || "");
      const index = raw.indexOf("#");
      if (index < 0) return "";
      try { return decodeURIComponent(raw.slice(index + 1)).trim().toUpperCase(); }
      catch (_error) { return raw.slice(index + 1).trim().toUpperCase(); }
    };
    const root = document.querySelector(`#${version}`);
    const prophet = document.querySelector(`#${version}-prophet`);
    const owner = document.querySelector(
      market === "hk" ? "#hk-owner-population-proof" : "#ca-v36-card-grid"
    );
    const host = document.querySelector(
      market === "hk" ? "#standouts .nbgrid" : "#standouts .cards"
    );
    const cards = host ? Array.from(host.querySelectorAll(".pvcard")) : [];
    const cardId = (card) => String(card.getAttribute("data-ticker") || "").trim().toUpperCase();
    const empty = document.querySelector(`#${version}-grid-empty`);
    const result = document.querySelector(`#${version}-result`);
    const watchLinks = Array.from(document.querySelectorAll(
      "#standouts .watch-strip .watch-grid a[href]"
    ));
    const sourceButtons = prophet
      ? Array.from(prophet.querySelectorAll(`[data-${prefix}-source]`)) : [];
    const selectedSources = sourceButtons.filter(
      (button) => button.getAttribute("aria-selected") === "true"
    );
    const filter = document.querySelector(`#${version}-filter`);
    const actionControl = overlayPayload
      ? document.querySelector(overlayPayload.control.selector) : null;
    const actionRow = actionControl && actionControl.closest("[data-action-id]");
    const research = actionRow && actionRow.querySelector(".anv2-name-link[href]");
    const overlayProbe = window.__p0bMembershipOverlay;
    const stocktableData = document.querySelector("#stocktable-data");
    const tableRows = Array.from(document.querySelectorAll("#stocktable-wrap tbody tr"));
    const tableIds = tableRows.map((row) => {
      const direct = row.getAttribute("data-ticker");
      if (direct) return direct.trim().toUpperCase();
      const link = row.querySelector("a.stf-tkr");
      return clean(link && link.textContent).toUpperCase();
    }).filter(Boolean);
    const memberProof = overlayPayload ? overlayPayload.members.map((member) => {
      const links = Array.from(document.querySelectorAll("#standouts a[href]"))
        .filter((link) => hashTicker(link.getAttribute("href")) === member.ticker);
      const cardMatch = cards.some((card) => cardId(card) === member.ticker);
      const expectedOwnerAnchor = links.some((link) => member.owner_lane === "watch"
        ? !!link.closest(".watch-grid")
        : !!link.closest("[data-stage]"));
      return {
        ticker: member.ticker,
        owner_lane: member.owner_lane,
        anchor_count: links.length,
        expected_owner_anchor: expectedOwnerAnchor,
        actionable_card: cardMatch,
        pass: links.length > 0 && expectedOwnerAnchor && !cardMatch,
      };
    }) : [];
    const panelStyle = prophet ? getComputedStyle(prophet) : null;
    const languageProbe = document.querySelector(`#${version}-result .l-${
      document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"
    }`);
    return {
      html: {
        lang: document.documentElement.getAttribute("lang"),
        data_lang: document.documentElement.getAttribute("data-lang") || "en",
        data_theme: document.documentElement.getAttribute("data-theme") || "dark",
        language_probe_visible: visible(languageProbe),
      },
      main_count: document.querySelectorAll("main").length,
      enhanced: !!(root && root.getAttribute(`data-${prefix}-enhanced`) === "true"),
      source_owner_state: prophet && prophet.getAttribute("data-source-owner-state"),
      initial_source: prophet && prophet.getAttribute("data-initial-source"),
      active_source: prophet && prophet.getAttribute("data-active-source"),
      selected_source: selectedSources.length === 1
        ? selectedSources[0].getAttribute(`data-${prefix}-source`) : null,
      source_selection_count: selectedSources.length,
      top_disabled: !!(sourceButtons.find(
        (button) => button.getAttribute(`data-${prefix}-source`) === "top"
      ) || {}).disabled,
      owner_population: {
        board: owner && owner.getAttribute(
          market === "hk" ? "data-owner-board-population" : "data-owner-population"
        ),
        watch: owner && owner.getAttribute("data-owner-watch-population"),
        unique_total: owner && owner.getAttribute("data-owner-unique-population"),
      },
      card_ids: cards.map(cardId),
      visible_card_ids: cards.filter(visible).map(cardId),
      table_ids: tableIds,
      watch: watchLinks.map((link) => ({
        ticker: hashTicker(link.getAttribute("href")),
        href: link.getAttribute("href"),
        visible: visible(link),
      })),
      grid_empty: {
        hidden_attribute: !!(empty && empty.hidden),
        visible: visible(empty),
        copy: clean(empty && empty.innerText),
      },
      result_copy: clean(result && result.innerText),
      static_owner_states: Array.from(document.querySelectorAll(
        `#${version}-prophet .${version}-static-state, #${version}-prophet [data-prophet-owner-state]`
      )).map((node) => ({copy: clean(node.innerText), visible: visible(node)})),
      filter: {
        visible: visible(filter),
        copy: clean(filter && filter.innerText),
      },
      active_group_count: root
        ? root.querySelectorAll(`[data-${prefix}-lead-id].is-active`).length : 0,
      research_href: research && research.getAttribute("href"),
      material: panelStyle ? {
        background_color: panelStyle.backgroundColor,
        border_color: panelStyle.borderColor,
        box_shadow: panelStyle.boxShadow,
      } : null,
      overlay: overlayPayload ? {
        installed: !!(overlayProbe && overlayProbe.installed),
        restored: !!(overlayProbe && overlayProbe.restored),
        error: overlayProbe && overlayProbe.error,
        same_control: !!(overlayProbe && overlayProbe.control === actionControl),
        same_control_parent: !!(
          overlayProbe && actionControl && overlayProbe.control_parent === actionControl.parentElement
        ),
        source_json_restored: !!(
          overlayProbe && stocktableData && stocktableData.textContent === overlayProbe.original_text
        ),
        member_proof: memberProof,
      } : null,
    };
  }, {market, prefix, version, overlayPayload});
}

function ownerPopulationMatches(observed, expected) {
  const value = (raw) => raw === null ? null
    : /^\d+$/.test(String(raw)) ? Number(raw) : Number.NaN;
  return value(observed.board) === expected.board &&
    value(observed.watch) === expected.watch &&
    value(observed.unique_total) === expected.unique_total;
}

async function ownerProjectionMatrix(
  browser,
  fixtureBinding,
  installRoutes,
  screenshotDir,
  repoRoot
) {
  const market = fixtureBinding.market;
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  const locales = ["en", "zh"];
  const themes = ["dark", "light"];
  const widths = [390, 1440];
  const primaryModes = ["loaded", "js-disabled"];
  const controlModes = ["composer-failed", "composer-pending"];
  const ownerCases = ["normal", "watch-only", "null-buy"];
  const cases = [];

  async function runCase(ownerCase, mode, locale, theme, width, proofSet) {
    const javascriptEnabled = mode !== "js-disabled";
    const composerMode = mode === "composer-failed" ? "failed"
      : mode === "composer-pending" ? "pending" : "loaded";
    const overlayBinding = ownerCase === "normal" && mode === "loaded"
      ? fixtureBinding.membershipOverlay : null;
    const context = await browser.newContext({
      viewport: {width, height: width === 390 ? 844 : 900},
      deviceScaleFactor: 1,
      javaScriptEnabled: javascriptEnabled,
      reducedMotion: "reduce",
    });
    if (javascriptEnabled) {
      await installPageInit(context, market, locale, theme);
      if (overlayBinding) {
        await installDiagnosticMembershipOverlay(context, market, overlayBinding);
      }
    }
    const staticAxes = javascriptEnabled ? null : {locale, theme};
    await installRoutes(context, composerMode, ownerCase, staticAxes);
    const page = await context.newPage();
    const consoleExceptions = [];
    page.on("pageerror", (error) => consoleExceptions.push(
      String(error && (error.stack || error.message) || error)
    ));
    const row = {
      proof_set: proofSet,
      market,
      owner_case: ownerCase,
      mode,
      locale,
      theme,
      viewport: {width, height: width === 390 ? 844 : 900},
      javascript_enabled: javascriptEnabled,
      composer: composerMode,
      source_html: {
        output: fixtureBinding.ownerCases[ownerCase].output,
        sha256: fixtureBinding.ownerCases[ownerCase].output_sha256,
      },
      served_html_transform: staticAxes
        ? staticAxisHtml(fixtureBinding.ownerCases[ownerCase].filename, locale, theme).receipt
        : null,
      membership_overlay_sha256: overlayBinding ? overlayBinding.sha256 : null,
      transition: {attempted: false, reason: "not a loaded normal-owner case"},
    };

    try {
      const pageUrl = new URL(fixtureBinding.route, "http://stock-dashboard.invalid");
      await page.goto(pageUrl.href, {
        waitUntil: composerMode === "pending" ? "commit" : "load",
        timeout: 30000,
      });
      await page.waitForTimeout(composerMode === "pending" ? 500 : 750);
      if (javascriptEnabled && composerMode !== "pending") {
        await page.evaluate(({locale, theme}) => {
          if (typeof window.setLang === "function") window.setLang(locale);
          else document.documentElement.setAttribute("data-lang", locale);
          if (typeof window.setTheme === "function") window.setTheme(theme);
          else document.documentElement.setAttribute("data-theme", theme);
        }, {locale, theme});
        await page.waitForTimeout(composerMode === "loaded" ? 1400 : 50);
      }
      if (overlayBinding) {
        await page.waitForFunction(() => {
          const probe = window.__p0bMembershipOverlay;
          return !!(probe && (probe.restored || probe.error));
        }, null, {timeout: 5000});
      }

      row.initial = await ownerProjectionSnapshot(
        page, market, overlayBinding && overlayBinding.payload
      );
      row.layout = await page.evaluate(`(${LAYOUT_SCRIPT})()`);
      row.duplicate_ids = await page.evaluate(() => {
        const counts = new Map();
        document.querySelectorAll("[id]").forEach((node) =>
          counts.set(node.id, (counts.get(node.id) || 0) + 1)
        );
        return Array.from(counts.entries()).filter(([, count]) => count > 1)
          .map(([id, count]) => ({id, count}));
      });

      if (overlayBinding) {
        row.transition = {attempted: true};
        const sourceBefore = row.initial.selected_source;
        const cardsBefore = row.initial.card_ids;
        const watchBefore = row.initial.watch;
        const tableBefore = row.initial.table_ids;
        const diagnosticControl = page.locator(overlayBinding.payload.control.selector);
        const activationMethod = width === 390 ? "keyboard-enter" : "pointer-click";
        if (activationMethod === "keyboard-enter") {
          /* The shared row-pop touch preview intentionally owns the first
             physical tap on a coarse/mobile row. Native button keyboard
             activation reaches the same delegated production handler. */
          await diagnosticControl.focus();
          await page.keyboard.press("Enter");
        } else {
          await diagnosticControl.click({timeout: 5000});
        }
        await page.waitForTimeout(50);
        const selected = await ownerProjectionSnapshot(page, market, overlayBinding.payload);
        await page.locator(`#${version}-filter`).click({timeout: 5000});
        await page.waitForTimeout(50);
        const cleared = await ownerProjectionSnapshot(page, market, overlayBinding.payload);
        const selectedCopy = locale === "zh"
          ? "当前领先筛选下无可操作卡片；匹配的观察/阶段名单仍保留在下方。"
          : "No actionable cards match this leadership filter; matching watch/stage names remain below.";
        row.transition = {
          attempted: true,
          activation_method: activationMethod,
          selected,
          cleared,
          source_unchanged: selected.selected_source === sourceBefore &&
            cleared.selected_source === sourceBefore,
          card_identity_unchanged: JSON.stringify(selected.card_ids) === JSON.stringify(cardsBefore) &&
            JSON.stringify(cleared.card_ids) === JSON.stringify(cardsBefore),
          watch_identity_unchanged: JSON.stringify(selected.watch) === JSON.stringify(watchBefore) &&
            JSON.stringify(cleared.watch) === JSON.stringify(watchBefore),
          table_identity_unchanged: JSON.stringify(selected.table_ids) === JSON.stringify(tableBefore) &&
            JSON.stringify(cleared.table_ids) === JSON.stringify(tableBefore),
          pass: selected.visible_card_ids.length === 0 && selected.grid_empty.visible &&
            selected.grid_empty.copy === selectedCopy && selected.filter.visible &&
            selected.active_group_count >= 1 &&
            selected.research_href === overlayBinding.payload.group.research_href &&
            selected.overlay.installed && selected.overlay.restored && !selected.overlay.error &&
            selected.overlay.same_control && selected.overlay.same_control_parent &&
            selected.overlay.source_json_restored &&
            selected.overlay.member_proof.every((proof) => proof.pass) &&
            !cleared.grid_empty.visible && !cleared.filter.visible &&
            cleared.visible_card_ids.length === row.initial.visible_card_ids.length &&
            selected.selected_source === sourceBefore && cleared.selected_source === sourceBefore &&
            JSON.stringify(selected.card_ids) === JSON.stringify(cardsBefore) &&
            JSON.stringify(cleared.card_ids) === JSON.stringify(cardsBefore) &&
            JSON.stringify(selected.watch) === JSON.stringify(watchBefore) &&
            JSON.stringify(cleared.watch) === JSON.stringify(watchBefore) &&
            JSON.stringify(selected.table_ids) === JSON.stringify(tableBefore) &&
            JSON.stringify(cleared.table_ids) === JSON.stringify(tableBefore),
        };
      } else if (mode === "js-disabled") {
        row.transition = {attempted: false, reason: "javascript disabled; no interaction claimed"};
      } else if (composerMode !== "loaded") {
        row.transition = {attempted: false, reason: `composer ${composerMode}; no interaction claimed`};
      }

      row.owner_zero_projection = {
        exercised: false,
        reason: "owner case is not loaded watch-only",
      };
      if (ownerCase === "watch-only" && mode === "loaded") {
        if (row.initial.selected_source === "top") {
          const expectedTopCopy = locale === "zh"
            ? "当前暂无首选。" : "No Top Picks right now.";
          await page.locator(`[data-${prefix}-source="all"]`).click({timeout: 5000});
          await page.waitForTimeout(50);
          const explicitAll = await ownerProjectionSnapshot(page, market, null);
          row.owner_zero_projection = {
            exercised: true,
            initial_source: row.initial.selected_source,
            initial_top_empty: row.initial.grid_empty,
            explicit_all: explicitAll,
            pass: row.initial.grid_empty.visible &&
              row.initial.grid_empty.copy === expectedTopCopy &&
              explicitAll.selected_source === "all" &&
              explicitAll.visible_card_ids.length === 0 &&
              explicitAll.grid_empty.hidden_attribute && !explicitAll.grid_empty.visible &&
              explicitAll.watch.length === row.initial.watch.length &&
              explicitAll.result_copy === row.initial.result_copy,
          };
        } else {
          row.owner_zero_projection = {
            exercised: false,
            reason: "server owner already selected All",
            explicit_all: row.initial,
            pass: row.initial.selected_source === "all" &&
              row.initial.grid_empty.hidden_attribute && !row.initial.grid_empty.visible,
          };
        }
      }

      if (ownerCase === "watch-only" && mode === "loaded") {
        const screenshot = await page.screenshot({
          fullPage: true,
          animations: "disabled",
          caret: "hide",
        });
        const filename = `owner-empty-${market}-watch-only-${locale}-${theme}-${width}.png`;
        const binding = {
          filename,
          width: pngWidth(screenshot),
          sha256: sha256Bytes(screenshot),
        };
        if (screenshotDir) {
          const screenshotFile = path.resolve(screenshotDir, filename);
          if (path.dirname(screenshotFile) !== screenshotDir) usage("invalid owner-empty screenshot path");
          fs.writeFileSync(screenshotFile, screenshot);
          binding.path = relativeRepoPath(repoRoot, screenshotFile);
        }
        row.screenshot = binding;
      }

      const expectedBinding = fixtureBinding.ownerCases[ownerCase];
      const expectedPopulation = expectedBinding.owner_population;
      const expectedWatch = expectedBinding.input_transform.payload
        .rendered_owner_identities.watch || [];
      const expectedCardCount = ownerCase === "normal"
        ? expectedBinding.input_transform.payload.rendered_owner_identities.buy.length : 0;
      const expectedOwnerState = ownerCase === "null-buy" ? "unavailable" : "available";
      const expectedEnhanced = composerMode === "loaded" && javascriptEnabled;
      const languageCopy = locale === "zh"
        ? row.initial.result_copy.includes("显示")
        : row.initial.result_copy.includes("actionable cards shown");
      const emptyOwnerTruth = ownerCase === "null-buy"
        ? (locale === "zh"
          ? row.initial.result_copy.includes("阶段榜单暂不可用")
          : row.initial.result_copy.includes("stage board unavailable"))
        : (locale === "zh"
          ? row.initial.result_copy.includes("当前共")
          : row.initial.result_copy.includes("current names"));
      const screenshotPass = ownerCase !== "watch-only" || mode !== "loaded" ||
        (row.screenshot && row.screenshot.width === width &&
          (!screenshotDir || !!row.screenshot.path));
      const gridTruthPass = ownerCase === "watch-only" && mode === "loaded"
        ? row.owner_zero_projection.pass
        : row.initial.grid_empty.hidden_attribute && !row.initial.grid_empty.visible;
      row.console_exceptions = consoleExceptions;
      row.pass = row.initial.main_count === 1 &&
        row.initial.html.data_lang === locale && row.initial.html.data_theme === theme &&
        row.initial.html.language_probe_visible &&
        row.initial.source_owner_state === expectedOwnerState &&
        row.initial.source_selection_count === 1 &&
        row.initial.card_ids.length === expectedCardCount &&
        (ownerCase === "normal" ? row.initial.visible_card_ids.length > 0 : row.initial.visible_card_ids.length === 0) &&
        gridTruthPass &&
        ownerPopulationMatches(row.initial.owner_population, expectedPopulation) &&
        JSON.stringify(row.initial.watch.map((item) => item.ticker)) === JSON.stringify(expectedWatch) &&
        row.initial.watch.every((item) => item.visible && !!item.href) &&
        row.initial.enhanced === expectedEnhanced && languageCopy && emptyOwnerTruth &&
        (ownerCase === "null-buy" ? row.initial.top_disabled : true) &&
        !row.layout.horizontal_overflow && row.layout.elements_wider_than_viewport === 0 &&
        row.layout.client_width === width && row.duplicate_ids.length === 0 &&
        consoleExceptions.length === 0 && screenshotPass &&
        (!overlayBinding || row.transition.pass);
    } catch (error) {
      row.execution_error = String(error && (error.stack || error.message) || error);
      row.console_exceptions = consoleExceptions;
      row.pass = false;
    } finally {
      await context.close();
    }
    cases.push(row);
  }

  for (const locale of locales) {
    for (const theme of themes) {
      for (const width of widths) {
        for (const ownerCase of ownerCases) {
          for (const mode of primaryModes) {
            await runCase(ownerCase, mode, locale, theme, width, "primary");
          }
        }
        for (const mode of controlModes) {
          await runCase("watch-only", mode, locale, theme, width, "degraded-control");
        }
      }
    }
  }

  const watchScreenshots = cases.filter((row) =>
    row.owner_case === "watch-only" && row.mode === "loaded" && row.screenshot
  );
  const themePairs = [];
  for (const locale of locales) {
    for (const width of widths) {
      const dark = watchScreenshots.find((row) =>
        row.locale === locale && row.theme === "dark" && row.viewport.width === width
      );
      const light = watchScreenshots.find((row) =>
        row.locale === locale && row.theme === "light" && row.viewport.width === width
      );
      const darkMaterial = dark && dark.initial.material;
      const lightMaterial = light && light.initial.material;
      themePairs.push({
        locale,
        viewport_width: width,
        dark: darkMaterial,
        light: lightMaterial,
        pass: !!(darkMaterial && lightMaterial) &&
          JSON.stringify(darkMaterial) !== JSON.stringify(lightMaterial),
      });
    }
  }
  const primary = cases.filter((row) => row.proof_set === "primary");
  const controls = cases.filter((row) => row.proof_set === "degraded-control");
  return {
    contract: {
      markets_in_receipt: 1,
      languages: locales,
      themes,
      viewport_widths: widths,
      owner_cases: ownerCases,
      primary_modes: primaryModes,
      degraded_control_owner_case: "watch-only",
      degraded_control_modes: controlModes,
      browser_motion_preference: "reduce",
      screenshot_animation_policy: "disabled",
      screenshot_caret_policy: "hide",
      expected_primary_cases: 48,
      expected_degraded_control_cases: 16,
      expected_total_cases: 64,
      expected_loaded_watch_only_screenshots: 8,
    },
    membership_overlay: {
      canonicalization: fixtureBinding.membershipOverlay.canonicalization,
      bytes: fixtureBinding.membershipOverlay.bytes,
      sha256: fixtureBinding.membershipOverlay.sha256,
      payload: fixtureBinding.membershipOverlay.payload,
    },
    primary_passed: primary.filter((row) => row.pass).length,
    degraded_controls_passed: controls.filter((row) => row.pass).length,
    screenshot_count: watchScreenshots.length,
    theme_art_direction_pairs: themePairs,
    cases,
    pass: primary.length === 48 && controls.length === 16 && cases.length === 64 &&
      primary.every((row) => row.pass) && controls.every((row) => row.pass) &&
      watchScreenshots.length === 8 && themePairs.every((row) => row.pass),
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const htmlFile = realFile(args.html, "--html");
  const siteDir = realDir(args["site-dir"], "--site-dir");
  const repoRoot = path.dirname(siteDir);
  const historicalBaseline = bindHistoricalReceipt(args, repoRoot);
  const fixtureReceiptFile = realFile(args["fixture-receipt"], "--fixture-receipt");
  const fixtureAssetsDir = realDir(args["fixture-assets-dir"], "--fixture-assets-dir");
  const fixtureAssetsRoot = relativeRepoPath(repoRoot, fixtureAssetsDir);
  const fixtureBinding = bindFixtureReceipt(fixtureReceiptFile, htmlFile, repoRoot);
  const composer = args.composer || MARKET_COMPOSERS[fixtureBinding.market];
  if (!composer || path.basename(composer) !== composer) {
    usage(`no safe composer filename for fixture market: ${fixtureBinding.market}`);
  }
  const screenshotDir = args["screenshot-dir"]
    ? realDir(args["screenshot-dir"], "--screenshot-dir")
    : null;
  const loadedAssets = new Map();
  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch (error) {
    process.stderr.write(`verifier_unavailable: playwright is not importable: ${error.message}\n`);
    process.exit(2);
  }

  const launch = {headless: true};
  if (args.browser) launch.executablePath = realFile(args.browser, "--browser");
  const browser = await chromium.launch(launch);
  const browserVersion = browser.version();
  const states = [
    {name: "en-dark", locale: "en", theme: "dark"},
    {name: "en-light", locale: "en", theme: "light"},
    {name: "zh-dark", locale: "zh", theme: "dark"},
    {name: "zh-light", locale: "zh", theme: "light"},
    {name: "js-disabled", locale: "en", theme: "dark", javascriptEnabled: false},
    {name: "composer-failed", locale: "en", theme: "light", composerMode: "failed"},
    {name: "composer-pending", locale: "en", theme: "dark", composerMode: "pending"},
  ];
  const rows = [];

  async function installRoutes(context, composerMode, ownerCase = "normal", staticAxes = null) {
    const ownerBinding = fixtureBinding.ownerCases[ownerCase];
    if (!ownerBinding) usage(`unknown rendered owner case: ${ownerCase}`);
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (path.basename(url.pathname) === composer && composerMode === "failed") {
        await route.fulfill({status: 503, body: "composer unavailable"});
        return;
      }
      if (path.basename(url.pathname) === composer && composerMode === "pending") {
        await new Promise((resolve) => setTimeout(resolve, 10000));
      } else if (path.basename(url.pathname) === composer && composerMode === "loaded") {
        await new Promise((resolve) => setTimeout(resolve, 150));
      }
      const relative = url.pathname.replace(/^\/+/, "");
      const fixtureCandidate = path.resolve(fixtureAssetsDir, relative);
      const fixtureOverride = fixtureCandidate.startsWith(fixtureAssetsDir + path.sep) &&
        fs.existsSync(fixtureCandidate) && fs.statSync(fixtureCandidate).isFile();
      const candidate = url.pathname === fixtureBinding.route
        ? ownerBinding.filename
        : fixtureOverride ? fixtureCandidate : path.resolve(siteDir, relative);
      if (candidate !== ownerBinding.filename &&
          !candidate.startsWith(siteDir + path.sep) &&
          !candidate.startsWith(fixtureAssetsDir + path.sep)) {
        await route.fulfill({status: 403, body: ""});
        return;
      }
      if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
        await route.fulfill({status: 404, body: ""});
        return;
      }
      const bytes = candidate === ownerBinding.filename && staticAxes
        ? staticAxisHtml(candidate, staticAxes.locale, staticAxes.theme).bytes
        : fs.readFileSync(candidate);
      if (candidate !== ownerBinding.filename) loadedAssets.set(relativeRepoPath(repoRoot, candidate), sha256Bytes(bytes));
      await route.fulfill({
        status: 200,
        body: bytes,
        contentType: MIME[path.extname(candidate).toLowerCase()] || "application/octet-stream",
      });
    });
  }

  try {
    for (const state of states) {
      const context = await browser.newContext({
        viewport: {width: 390, height: 844},
        deviceScaleFactor: 1,
        javaScriptEnabled: state.javascriptEnabled !== false,
      });
      if (state.javascriptEnabled !== false) {
        await installPageInit(context, fixtureBinding.market, state.locale, state.theme);
      }
      await installRoutes(context, state.composerMode || "loaded");

      const page = await context.newPage();
      const consoleExceptions = [];
      page.on("pageerror", (error) => consoleExceptions.push(String(error && (error.stack || error.message) || error)));
      const waitUntil = state.composerMode === "pending" ? "commit" : "load";
      const pageUrl = new URL(fixtureBinding.route, "http://stock-dashboard.invalid");
      await page.goto(pageUrl.href, {waitUntil, timeout: 30000});
      await page.waitForTimeout(state.composerMode === "pending" ? 500 : 750);
      if (state.javascriptEnabled !== false && state.composerMode !== "pending") {
        await page.evaluate(({locale, theme}) => {
          if (typeof window.setLang === "function") window.setLang(locale);
          else document.documentElement.setAttribute("data-lang", locale);
          if (typeof window.setTheme === "function") window.setTheme(theme);
          else document.documentElement.setAttribute("data-theme", theme);
        }, {locale: state.locale, theme: state.theme});
        // theme.js keeps its sun/moon flourish alive for roughly 1100ms.
        // Measure and persist the settled state, never the transition frame.
        await page.waitForTimeout(1400);
      }
      const layout = await page.evaluate(`(${LAYOUT_SCRIPT})()`);
      layout.duplicate_ids = await page.evaluate(() => {
        const counts = new Map();
        document.querySelectorAll("[id]").forEach((node) => counts.set(node.id, (counts.get(node.id) || 0) + 1));
        return Array.from(counts.entries()).filter(([, count]) => count > 1).map(([id, count]) => ({id, count}));
      });
      layout.console_exceptions = consoleExceptions;
      const screenshot = await page.screenshot({fullPage: true});
      layout.screenshot_width = pngWidth(screenshot);
      layout.pass = !layout.horizontal_overflow &&
        layout.elements_wider_than_viewport === 0 && layout.screenshot_width === 390 &&
        layout.duplicate_ids.length === 0 && layout.console_exceptions.length === 0;
      const behavior = await mobileBehavior(
        page,
        fixtureBinding.market,
        state.composerMode || "loaded",
        state.javascriptEnabled !== false
      );
      layout.pass = layout.pass && behavior.pass;
      rows.push({
        state: state.name,
        locale: state.locale,
        theme: state.theme,
        javascript_enabled: state.javascriptEnabled !== false,
        composer: state.composerMode || "loaded",
        behavior,
        ...layout,
      });
      await context.close();
    }

    var expansionReachability = await expansionReachabilityProof(
      browser,
      fixtureBinding.market,
      fixtureBinding.route,
      installRoutes
    );

    var fragmentNavigation = await fragmentNavigationProof(
      browser,
      fixtureBinding.market,
      fixtureBinding.route,
      installRoutes
    );

    const desktopContext = await browser.newContext({
      viewport: {width: 1440, height: 900},
      deviceScaleFactor: 1,
    });
    await installPageInit(desktopContext, fixtureBinding.market, "en", "dark");
    await installRoutes(desktopContext, "loaded");
    const desktopPage = await desktopContext.newPage();
    await desktopPage.goto(new URL(fixtureBinding.route, "http://stock-dashboard.invalid").href, {waitUntil: "load", timeout: 30000});
    await desktopPage.waitForTimeout(1500);
    var desktop = await desktopBehavior(desktopPage, fixtureBinding.market);
    await desktopContext.close();

    var ownerProjection = await ownerProjectionMatrix(
      browser,
      fixtureBinding,
      installRoutes,
      screenshotDir,
      repoRoot
    );
  } finally {
    await browser.close();
  }

  const payload = {
    schema: "mastermind.stock_dashboard_mobile_layout.v1",
    proof_class: "browser_fixture_proof_reproducible",
    claims: {
      source_contract: "browser_fixture",
      browser_fixture: "reproducible",
      canonical_build: "unavailable",
      production: "none",
    },
    verifier: {
      path: relativeRepoPath(repoRoot, path.resolve(__filename)),
      sha256: sha256File(path.resolve(__filename)),
    },
    browser: {
      engine: "chromium",
      version: browserVersion,
    },
    fixture_receipt: fixtureBinding.receipt,
    fixture_assets_root: fixtureAssetsRoot,
    fixture_market: fixtureBinding.market,
    ...(historicalBaseline ? {historical_baseline: historicalBaseline} : {}),
    input_html: {
      path: fixtureBinding.output,
      route: fixtureBinding.route,
      sha256: fixtureBinding.htmlSha256,
    },
    rendered_owner_cases: Object.fromEntries(
      Object.entries(fixtureBinding.ownerCases).map(([ownerCase, binding]) => [
        ownerCase,
        {
          route: binding.route,
          output: binding.output,
          output_sha256: binding.output_sha256,
          owner_population: binding.owner_population,
          input_transform: binding.input_transform,
        },
      ])
    ),
    construction_inputs: fixtureBinding.constructionInputs,
    loaded_assets: Object.fromEntries(Array.from(loadedAssets.entries()).sort()),
    viewport: {width: 390, height: 844, device_scale_factor: 1},
    desktop_viewport: {width: 1440, height: 900, device_scale_factor: 1},
    acceptance: "390px layout; server-owned four-anchor degraded fallback without false tab semantics; composer upgrades the same nodes in place; one mobile action lane in loaded/disabled/failed/pending states; deterministic owner counts and controls; valid/invalid/direct/back/forward fragment reconciliation; 390/1440 x disabled/failed/pending/loaded native click+Enter+Space disclosure reachability with stable row nodes/payload and lane-local state; desktop <=3 rows/lane and action panel <=240px; one Prophet chrome/view owner; truthful first-frame source; Top/All x Grid/Table identity/order; persisted Table startup; group/clear/resize manifest identity; typed Canada quote states; closed normal/watch-only/null-buy owner projection matrix across EN/ZH x dark/light x 390/1440 x loaded/JS-disabled plus failed/pending watch-only controls; exact admitted known-group membership overlay; selected/clear card-only projection without source, card, table, watch, anchor, or research-route mutation; zero duplicate ids and console exceptions",
    expansion_reachability: expansionReachability,
    fragment_navigation: fragmentNavigation,
    desktop,
    owner_projection_matrix: ownerProjection,
    pass: rows.every((row) => row.pass) && expansionReachability.pass &&
      fragmentNavigation.pass && desktop.pass && ownerProjection.pass,
    states: rows,
  };
  const encoded = JSON.stringify(payload, null, 2) + "\n";
  if (args.out) fs.writeFileSync(path.resolve(args.out), encoded);
  process.stdout.write(encoded);
  process.exit(payload.pass ? 0 : 1);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(2);
});
