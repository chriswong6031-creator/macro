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
const path = require("path");

function usage(message) {
  if (message) process.stderr.write(`error: ${message}\n`);
  process.stderr.write(
    "usage: verify_stock_dashboard_mobile_layout.cjs " +
      "--html FILE --site-dir DIR [--composer FILE] [--browser FILE] [--out FILE]\n"
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
  if (!parsed.html || !parsed["site-dir"]) usage("--html and --site-dir are required");
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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const htmlFile = realFile(args.html, "--html");
  const siteDir = realDir(args["site-dir"], "--site-dir");
  const composer = args.composer || "hk-stock-v36.js";
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
  const states = [
    {name: "en-dark", locale: "en", theme: "dark"},
    {name: "en-light", locale: "en", theme: "light"},
    {name: "zh-dark", locale: "zh", theme: "dark"},
    {name: "zh-light", locale: "zh", theme: "light"},
    {name: "js-disabled", locale: "en", theme: "dark", javascriptEnabled: false},
    {name: "composer-failed", locale: "en", theme: "dark", composerMode: "failed"},
    {name: "composer-pending", locale: "en", theme: "dark", composerMode: "pending"},
  ];
  const rows = [];

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
      await context.route("**/*", async (route) => {
        const url = new URL(route.request().url());
        if (path.basename(url.pathname) === composer && state.composerMode === "failed") {
          await route.fulfill({status: 503, body: "composer unavailable"});
          return;
        }
        if (path.basename(url.pathname) === composer && state.composerMode === "pending") {
          await new Promise((resolve) => setTimeout(resolve, 2500));
        }
        const candidate = url.pathname === "/hk_stocks.html"
          ? htmlFile
          : path.resolve(siteDir, url.pathname.replace(/^\/+/, ""));
        if (candidate !== htmlFile && !candidate.startsWith(siteDir + path.sep)) {
          await route.fulfill({status: 403, body: ""});
          return;
        }
        if (!fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
          await route.fulfill({status: 404, body: ""});
          return;
        }
        await route.fulfill({
          status: 200,
          body: fs.readFileSync(candidate),
          contentType: MIME[path.extname(candidate).toLowerCase()] || "application/octet-stream",
        });
      });

      const page = await context.newPage();
      const waitUntil = state.composerMode === "pending" ? "commit" : "load";
      await page.goto("http://stock-dashboard.invalid/hk_stocks.html", {waitUntil, timeout: 30000});
      await page.waitForTimeout(state.composerMode === "pending" ? 500 : 750);
      if (state.javascriptEnabled !== false && state.composerMode !== "pending") {
        await page.evaluate(({locale, theme}) => {
          if (typeof window.setLang === "function") window.setLang(locale);
          else document.documentElement.setAttribute("data-lang", locale);
          if (typeof window.setTheme === "function") window.setTheme(theme);
          else document.documentElement.setAttribute("data-theme", theme);
        }, {locale: state.locale, theme: state.theme});
        await page.waitForTimeout(250);
      }
      const layout = await page.evaluate(`(${LAYOUT_SCRIPT})()`);
      const screenshot = await page.screenshot({fullPage: true});
      layout.screenshot_width = pngWidth(screenshot);
      layout.pass = !layout.horizontal_overflow &&
        layout.elements_wider_than_viewport === 0 && layout.screenshot_width === 390;
      rows.push({
        state: state.name,
        locale: state.locale,
        theme: state.theme,
        javascript_enabled: state.javascriptEnabled !== false,
        composer: state.composerMode || "loaded",
        ...layout,
      });
      await context.close();
    }
  } finally {
    await browser.close();
  }

  const payload = {
    schema: "mastermind.stock_dashboard_mobile_layout.v1",
    html: htmlFile,
    viewport: {width: 390, height: 844, device_scale_factor: 1},
    acceptance: "scroll_width <= client_width; elements_wider_than_viewport == 0; screenshot_width == 390",
    pass: rows.every((row) => row.pass),
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
