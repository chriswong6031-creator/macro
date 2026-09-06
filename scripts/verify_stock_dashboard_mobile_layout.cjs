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
      "[--composer FILE] [--browser FILE] [--out FILE] [--screenshot-dir DIR]\n"
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

function relativeRepoPath(repoRoot, filename) {
  const relative = path.relative(repoRoot, filename);
  if (!relative || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) {
    usage(`receipt input is outside the repository: ${filename}`);
  }
  return relative.split(path.sep).join("/");
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

async function mobileBehavior(page, market, composerMode, javascriptEnabled) {
  const prefix = market === "hk" ? "hk" : "ca";
  const version = market === "hk" ? "hk-v37" : "ca-v36";
  const basic = await page.evaluate(({prefix, version, market}) => {
    const visible = (el) => {
      const style = getComputedStyle(el);
      return style.display !== "none" && style.visibility !== "hidden" && el.getClientRects().length > 0;
    };
    const tabs = Array.from(document.querySelectorAll(`[data-${prefix}-an-lane]`)).map((tab) => {
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
    };
    result.source_contract.pass = selectedSources.length === 1 && source === initialSource && activeSource === source &&
      JSON.stringify(result.source_contract.expected_grid) === JSON.stringify(result.source_contract.visible_grid) &&
      resultCopy.includes(`${expectedCards.length} actionable cards shown`);
    result.prophet_chrome.pass = result.prophet_chrome.title_count === 1 && result.prophet_chrome.result_count === 1 &&
      result.prophet_chrome.owner_context_count === 1 && result.prophet_chrome.vintage_count === 1 &&
      result.prophet_chrome.help_count === 1 && result.prophet_chrome.legacy_view_count === 0;
    result.view_owner.pass = result.view_owner.control_count === 1 && result.view_owner.button_count === 2 &&
      result.view_owner.selected === "grid" && result.view_owner.table_disabled === !stockTableReady;
    result.pass = tabs.length === 4 && tabs.every((tab) => tab.title && /^\d+$/.test(tab.count.trim()) && tab.title_fully_visible) &&
      visibleLanes.length === 1 && visibleLanes[0] === "buy" && activeRows.length <= 3 &&
      result.known_membership_hook && /2\s*·\s*Prophet/.test(result.known_copy) &&
      !result.unknown_membership_hook && result.unknown_route &&
      !result.generic_showmore_attribute && result.generic_showmore_bar_count === 0 &&
      (market !== "ca" || (result.quote_state === "unavailable" && /Quotes unavailable/.test(result.quote_copy))) &&
      result.source_contract.pass && result.prophet_chrome.pass && result.view_owner.pass;
    return result;
  }, {prefix, version, market});

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
    const more = page.locator(`[data-${prefix}-an-lane-body="buy"] .${version}-an-more`);
    const before = await page.locator(`[data-${prefix}-an-lane-body="buy"] .${version}-an-row-w`).count();
    if (await more.count()) await more.click();
    const after = await page.locator(`[data-${prefix}-an-lane-body="buy"] .${version}-an-row-w`).count();
    const visibleAfter = await page.evaluate(({prefix}) => Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`))
      .filter((el) => getComputedStyle(el).display !== "none" && el.getClientRects().length > 0)
      .map((el) => el.getAttribute(`data-${prefix}-an-lane-body`)), {prefix});
    basic.view_all = {
      before,
      after,
      active_only: visibleAfter.length === 1 && visibleAfter[0] === "buy",
      pass: before === 3 && after === 4 && visibleAfter.length === 1 && visibleAfter[0] === "buy",
    };
  } else if (composerMode !== "pending") {
    await page.locator(`[data-${prefix}-an-lane="near"]`).click();
    await page.waitForTimeout(50);
    const fallback = await page.evaluate(({prefix}) => Array.from(document.querySelectorAll(`[data-${prefix}-an-lane-body]`))
      .filter((el) => getComputedStyle(el).display !== "none" && el.getClientRects().length > 0)
      .map((el) => el.getAttribute(`data-${prefix}-an-lane-body`)), {prefix});
    basic.static_anchor_fallback = {
      visible_lanes: fallback,
      pass: fallback.length === 1 && fallback[0] === "near",
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
  basic.exercised_lanes = exercised;
  basic.pass = basic.pass && exercised.every((row) => row.pass) &&
    (!basic.view_all || basic.view_all.pass) &&
    (!basic.static_anchor_fallback || basic.static_anchor_fallback.pass) &&
    (!basic.view_transition || basic.view_transition.pass);
  return basic;
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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const htmlFile = realFile(args.html, "--html");
  const siteDir = realDir(args["site-dir"], "--site-dir");
  const repoRoot = path.dirname(siteDir);
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

  async function installRoutes(context, composerMode) {
    await context.route("**/*", async (route) => {
      const url = new URL(route.request().url());
      if (path.basename(url.pathname) === composer && composerMode === "failed") {
        await route.fulfill({status: 503, body: "composer unavailable"});
        return;
      }
      if (path.basename(url.pathname) === composer && composerMode === "pending") {
        await new Promise((resolve) => setTimeout(resolve, 2500));
      }
      const relative = url.pathname.replace(/^\/+/, "");
      const fixtureCandidate = path.resolve(fixtureAssetsDir, relative);
      const fixtureOverride = fixtureCandidate.startsWith(fixtureAssetsDir + path.sep) &&
        fs.existsSync(fixtureCandidate) && fs.statSync(fixtureCandidate).isFile();
      const candidate = url.pathname === fixtureBinding.route
        ? htmlFile
        : fixtureOverride ? fixtureCandidate : path.resolve(siteDir, relative);
      if (candidate !== htmlFile &&
          !candidate.startsWith(siteDir + path.sep) &&
          !candidate.startsWith(fixtureAssetsDir + path.sep)) {
        await route.fulfill({status: 403, body: ""});
        return;
      }
      if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
        await route.fulfill({status: 404, body: ""});
        return;
      }
      const bytes = fs.readFileSync(candidate);
      if (candidate !== htmlFile) loadedAssets.set(relativeRepoPath(repoRoot, candidate), sha256Bytes(bytes));
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
        await context.addInitScript(({locale, theme}) => {
          localStorage.setItem("lang", locale);
          localStorage.setItem("theme", theme);
        }, {locale: state.locale, theme: state.theme});
      }
      await installRoutes(context, state.composerMode || "loaded");

      const page = await context.newPage();
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
      const screenshot = await page.screenshot({fullPage: true});
      let screenshotBinding = null;
      if (screenshotDir && ["js-disabled", "composer-failed"].includes(state.name)) {
        const screenshotFile = path.resolve(
          screenshotDir,
          `${fixtureBinding.market}-${state.name}-${state.theme}-390.png`
        );
        if (path.dirname(screenshotFile) !== screenshotDir) usage("invalid screenshot output path");
        fs.writeFileSync(screenshotFile, screenshot);
        screenshotBinding = {
          path: relativeRepoPath(repoRoot, screenshotFile),
          sha256: sha256Bytes(screenshot),
        };
      }
      layout.screenshot_width = pngWidth(screenshot);
      layout.pass = !layout.horizontal_overflow &&
        layout.elements_wider_than_viewport === 0 && layout.screenshot_width === 390;
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
        ...(screenshotBinding ? {screenshot: screenshotBinding} : {}),
        behavior,
        ...layout,
      });
      await context.close();
    }

    const desktopContext = await browser.newContext({
      viewport: {width: 1440, height: 900},
      deviceScaleFactor: 1,
    });
    await desktopContext.addInitScript(() => {
      localStorage.setItem("lang", "en");
      localStorage.setItem("theme", "dark");
    });
    await installRoutes(desktopContext, "loaded");
    const desktopPage = await desktopContext.newPage();
    await desktopPage.goto(new URL(fixtureBinding.route, "http://stock-dashboard.invalid").href, {waitUntil: "load", timeout: 30000});
    await desktopPage.waitForTimeout(1500);
    var desktop = await desktopBehavior(desktopPage, fixtureBinding.market);
    await desktopContext.close();
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
    input_html: {
      path: fixtureBinding.output,
      route: fixtureBinding.route,
      sha256: fixtureBinding.htmlSha256,
    },
    construction_inputs: fixtureBinding.constructionInputs,
    loaded_assets: Object.fromEntries(Array.from(loadedAssets.entries()).sort()),
    viewport: {width: 390, height: 844, device_scale_factor: 1},
    desktop_viewport: {width: 1440, height: 900, device_scale_factor: 1},
    acceptance: "390px layout; one mobile action lane; typed action membership; desktop <=3 rows/lane and action panel <=240px; one Prophet chrome/view owner; truthful first-frame source; Top/All x Grid/Table identity/order; persisted Table startup; group/clear/resize manifest identity; no generic showmore owner; typed Canada quote states",
    desktop,
    pass: rows.every((row) => row.pass) && desktop.pass,
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
