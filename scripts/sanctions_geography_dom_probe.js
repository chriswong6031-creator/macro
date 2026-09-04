#!/usr/bin/env node
"use strict";

/* Executes the production selection/filter and language-refresh code against a
   deliberately small DOM. This repo has no Node package manifest or jsdom; the
   same hand-rolled, dependency-free harness shape is used by existing JS
   contract tests. The probe exits non-zero on any behavioral regression and
   prints one machine-readable observation object on success. */

var fs = require("fs");
var vm = require("vm");
var nodeCrypto = require("crypto");

function Classes(initial) {
  this.values = new Set(String(initial || "").split(/\s+/).filter(Boolean));
}
Classes.prototype.contains = function (name) { return this.values.has(name); };
Classes.prototype.toggle = function (name, force) {
  if (force) { this.values.add(name); } else { this.values.delete(name); }
};
Classes.prototype.remove = function (name) { this.values.delete(name); };

function Node(classes) {
  this.attrs = {};
  this.classList = new Classes(classes);
}
Node.prototype.getAttribute = function (name) {
  return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null;
};
Node.prototype.setAttribute = function (name, value) { this.attrs[name] = String(value); };
Node.prototype.hasAttribute = function (name) {
  return Object.prototype.hasOwnProperty.call(this.attrs, name);
};

var us = new Node("sg-geo is-pick");
us.setAttribute("data-geo-id", "840");
us.setAttribute("data-name-en", "United States: 2 listed entries with a published address here");
us.setAttribute("data-name-zh", "United States：2 条名单记录在此有公开地址");
us.setAttribute("tabindex", "0");
us.setAttribute("aria-disabled", "false");
us.setAttribute("aria-pressed", "true");

var ca = new Node("sg-geo is-pick");
ca.setAttribute("data-geo-id", "124");
ca.setAttribute("data-name-en", "Canada: 1 listed entry with a published address here");
ca.setAttribute("data-name-zh", "Canada：1 条名单记录在此有公开地址");
ca.setAttribute("tabindex", "0");
ca.setAttribute("aria-disabled", "false");

var map = new Node();
map.querySelectorAll = function (selector) {
  if (selector === ".sg-geo") { return [us, ca]; }
  if (selector === ".sg-geo.is-pick") { return [us, ca]; }
  return [];
};

var view = new Node();
view.value = "resolved";
view.options = [];
var root = {
  querySelector: function (selector) {
    if (selector === "[data-sg-map]") { return map; }
    if (selector === "[data-sg-view]") { return view; }
    return null;
  }
};
var documentStub = {
  documentElement: {
    attrs: { "data-lang": "en" },
    getAttribute: function (name) { return this.attrs[name] || null; }
  },
  querySelector: function (selector) { return selector === "[data-sg-root]" ? root : null; }
};
var windowStub = {
  __SANCTIONS_GEOGRAPHY_TEST__: true,
  d3: null,
  topojson: null,
  crypto: nodeCrypto.webcrypto,
  location: { href: "https://example.test/sanctions-geography.html", origin: "https://example.test" }
};
var shardPayload = {
  schema_version: "mastermind.sanctions_geography.v1",
  parser_revision: "probe",
  projection_id: "sha256:probe",
  source_identity: "probe-source",
  geo_id: "840",
  entries: [{ uid: "101", entity_type: "Entity", programs: [], addresses: [] }]
};
var shardBody = Buffer.from(JSON.stringify(shardPayload), "utf8");
var shardHash = nodeCrypto.createHash("sha256").update(shardBody).digest("hex");
var shardRequests = 0;
function fetchStub(url) {
  shardRequests += 1;
  if (url !== "https://example.test/sanctions-geography-entries/840.json" &&
      url !== "https://example.test/sanctions-geography-entries/124.json") {
    return Promise.reject(new Error("unexpected shard URL: " + url));
  }
  var view = shardBody.buffer.slice(shardBody.byteOffset, shardBody.byteOffset + shardBody.byteLength);
  return Promise.resolve({ ok: true, status: 200, arrayBuffer: function () { return Promise.resolve(view); } });
}

var sourcePath = process.argv[2];
if (!sourcePath) { throw new Error("usage: sanctions_geography_dom_probe.js <production-js>"); }
vm.runInNewContext(fs.readFileSync(sourcePath, "utf8"), {
  window: windowStub,
  document: documentStub,
  console: console,
  Set: Set,
  String: String,
  Number: Number,
  Object: Object,
  Array: Array,
  Math: Math,
  Date: Date,
  isFinite: isFinite,
  Promise: Promise,
  Uint8Array: Uint8Array,
  TextDecoder: TextDecoder,
  URL: URL,
  fetch: fetchStub
}, { filename: sourcePath });

var behavior = windowStub.__sanctionsGeographyBehavior;
if (!behavior) { throw new Error("production behavior seam was not exposed"); }
behavior.setProjection({
  schema_version: "mastermind.sanctions_geography.v1",
  parser_revision: "probe",
  projection_id: "sha256:probe",
  source_identity: "probe-source",
  countries: [
    { geo_id: "840", country: "United States", entry_types: ["Entity"] },
    { geo_id: "124", country: "Canada", entry_types: ["Entity"] }
  ],
  entry_shards: { by_geo: {
    "840": {
      path: "sanctions-geography-entries/840.json",
      sha256: shardHash,
      entries: 1,
      bytes: shardBody.byteLength
    },
    "124": {
      path: "sanctions-geography-entries/124.json",
      sha256: "0".repeat(64),
      entries: 1,
      bytes: shardBody.byteLength
    }
  } }
});
behavior.setSelected("840");
behavior.syncMap([{ geo_id: "124" }]);

documentStub.documentElement.attrs["data-lang"] = "zh";
behavior.applyLang();

var initialShardRequests = shardRequests;
behavior.loadSelectedEntries("840").then(function (entries) {
  var result = {
    selection_cleared: behavior.getSelected() === null ? 1 : 0,
    dimmed_keyboard_reachable: us.getAttribute("tabindex") === "-1" ? 0 : 1,
    zh_map_name_applied: us.getAttribute("aria-label") === us.getAttribute("data-name-zh"),
    initial_shard_requests: initialShardRequests,
    selection_shard_requests: shardRequests - initialShardRequests,
    selected_entries_loaded: entries.length,
    tampered_shard_refused: false,
    tampered_shard_state_error: false
  };
  behavior.setSelected("124");
  return behavior.loadSelectedEntries("124").then(function () {
    result.tampered_shard_refused = false;
  }, function () {
    result.tampered_shard_refused = true;
  }).then(function () {
    result.tampered_shard_state_error = behavior.getShardStatus("124") === "error";
    if (result.selection_cleared !== 1 || result.dimmed_keyboard_reachable !== 0 ||
        result.zh_map_name_applied !== true || result.initial_shard_requests !== 0 ||
        result.selection_shard_requests !== 1 || result.selected_entries_loaded !== 1 ||
        result.tampered_shard_refused !== true || result.tampered_shard_state_error !== true) {
      process.stderr.write(JSON.stringify(result) + "\n");
      process.exit(1);
    }
    process.stdout.write(JSON.stringify(result) + "\n");
  });
}).catch(function (error) {
  process.stderr.write(String(error && error.stack ? error.stack : error) + "\n");
  process.exit(1);
});
