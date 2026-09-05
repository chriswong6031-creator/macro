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
        if (candidate !== htmlFile) {
          loadedAssets.set(relativeRepoPath(repoRoot, candidate), sha256Bytes(bytes));
        }
        await route.fulfill({
          status: 200,
          body: bytes,
          contentType: MIME[path.extname(candidate).toLowerCase()] || "application/octet-stream",
        });
      });

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
      rows.push({
        state: state.name,
        locale: state.locale,
        theme: state.theme,
        javascript_enabled: state.javascriptEnabled !== false,
        composer: state.composerMode || "loaded",
        ...(screenshotBinding ? {screenshot: screenshotBinding} : {}),
        ...layout,
      });
      await context.close();
    }
  } finally {
    await browser.close();
  }

  const payload = {
    schema: "mastermind.stock_dashboard_mobile_layout.v1",
    proof_class: "browser_fixture_proof_reproducible",
    claims: {
      source_contract: "not_assessed_by_this_receipt",
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
