#!/usr/bin/env node
/* Runs the SHIPPED board-hydration merge (the BOARD_STAGES / groupKey /
 * stageRank / mergeBoardCards block sliced out of the rendered us_stocks shell
 * by tests/test_us_board_hydration_merge.py) against a stub DOM, and prints the
 * resulting group structure as JSON.
 *
 * Why a hand-rolled stub and not jsdom: this repo has no node package manifest
 * and no jsdom on the box (checked 2026-08-20), and the sibling
 * tests/biocatalyst_hydration_harness.js already establishes the "stub exactly
 * the DOM the runtime touches" pattern. Its stub sets innerHTML as TEXT, which
 * cannot drive a function whose whole job is re-parenting parsed elements — so
 * this one adds a deliberately narrow parser.
 *
 * PARSER SCOPE, on purpose: the board grid is a FLAT sequence of top-level
 * elements (stage/lane headings and `<a class="pvcard">` cards). Only that top
 * level is modelled — each element keeps its own tag + attributes and its inner
 * markup stays an opaque string, because mergeBoardCards never reads inside a
 * card. Nesting is resolved by counting the element's OWN tag name, so the
 * arbitrary <div>/<span>/<svg> soup inside a card cannot confuse it.
 *
 * usage: node us_board_hydrate_harness.js <scenario.json> <merge.js>
 *   scenario: {shell: "<html of the grid's children>", payload: "<cards_html>"}
 */
'use strict';

var fs = require('fs');
var scenario = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
var mergeJs = fs.readFileSync(process.argv[3], 'utf8');

var VOID = { br: 1, hr: 1, img: 1, input: 1, meta: 1, link: 1, path: 1, circle: 1, use: 1 };

function classSet(cn) { return String(cn || '').trim().split(/\s+/).filter(Boolean); }

function makeNode(tag, attrs, inner) {
  var node = {
    nodeType: 1,
    tagName: String(tag).toUpperCase(),
    attributes: attrs || {},
    childNodes: [],
    parentNode: null,
    _inner: inner || ''
  };
  node.className = node.attributes['class'] || '';
  node.classList = {
    contains: function (n) { return classSet(node.className).indexOf(n) >= 0; }
  };
  node.getAttribute = function (n) {
    if (n === 'class') return node.className || null;
    return Object.prototype.hasOwnProperty.call(node.attributes, n) ? node.attributes[n] : null;
  };
  node.setAttribute = function (n, v) {
    node.attributes[n] = String(v);
    if (n === 'class') node.className = String(v);
  };
  node.appendChild = function (child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = node;
    node.childNodes.push(child);
    return child;
  };
  node.removeChild = function (child) {
    node.childNodes = node.childNodes.filter(function (c) { return c !== child; });
    child.parentNode = null;
    return child;
  };
  node.insertBefore = function (child, ref) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = node;
    if (ref == null) { node.childNodes.push(child); return child; }
    var i = node.childNodes.indexOf(ref);
    if (i < 0) node.childNodes.push(child); else node.childNodes.splice(i, 0, child);
    return child;
  };
  function sibling(offset) {
    if (!node.parentNode) return null;
    var i = node.parentNode.childNodes.indexOf(node);
    return node.parentNode.childNodes[i + offset] || null;
  }
  /* No text nodes are modelled, so nextSibling === nextElementSibling. In a real
     DOM nextSibling may be inter-element whitespace; inserting before that
     whitespace still lands after the same last card, which is all the runtime
     relies on. */
  Object.defineProperty(node, 'nextElementSibling', { get: function () { return sibling(1); } });
  Object.defineProperty(node, 'nextSibling', { get: function () { return sibling(1); } });
  Object.defineProperty(node, 'children', { get: function () { return node.childNodes.slice(); } });
  Object.defineProperty(node, 'firstElementChild', { get: function () { return node.childNodes[0] || null; } });
  Object.defineProperty(node, 'innerHTML', {
    get: function () { return node._inner; },
    set: function (html) {
      node.childNodes.forEach(function (c) { c.parentNode = null; });
      node.childNodes = [];
      node._inner = String(html);
      parseTopLevel(String(html)).forEach(function (c) { node.appendChild(c); });
    }
  });
  node.querySelectorAll = function (sel) {
    var wanted = String(sel).split(',').map(function (s) { return s.trim().replace(/^\./, ''); });
    var out = [];
    node.childNodes.forEach(function (c) {
      if (wanted.some(function (w) { return c.classList.contains(w); })) out.push(c);
      out = out.concat([].slice.call(c.querySelectorAll(sel)));
    });
    return out;
  };
  node.querySelector = function (sel) { return node.querySelectorAll(sel)[0] || null; };
  return node;
}

var OPEN_RE = /<([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>/;
var ATTR_RE = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"/g;

function parseAttrs(raw) {
  var attrs = {}, m;
  ATTR_RE.lastIndex = 0;
  while ((m = ATTR_RE.exec(raw))) attrs[m[1]] = m[2];
  return attrs;
}

/* Split `html` into its TOP-LEVEL elements. Depth is counted on the element's
   own tag name only, so a card's inner markup is skipped wholesale. */
function parseTopLevel(html) {
  var out = [], rest = String(html);
  while (rest.length) {
    var m = OPEN_RE.exec(rest);
    if (!m) break;
    var tag = m[1], attrRaw = m[2], start = m.index, openEnd = start + m[0].length;
    if (VOID[tag.toLowerCase()] || /\/\s*$/.test(attrRaw)) {
      out.push(makeNode(tag, parseAttrs(attrRaw), ''));
      rest = rest.slice(openEnd);
      continue;
    }
    var depth = 1, i = openEnd, inner = null, close = null;
    var opener = new RegExp('<' + tag + '(?=[\\s/>])', 'gi');
    var closer = new RegExp('</' + tag + '\\s*>', 'gi');
    while (depth > 0) {
      closer.lastIndex = i;
      var c = closer.exec(rest);
      if (!c) break;
      opener.lastIndex = i;
      var extra = 0, o;
      while ((o = opener.exec(rest)) && o.index < c.index) extra += 1;
      depth += extra - 1;
      i = c.index + c[0].length;
      if (depth === 0) { inner = rest.slice(openEnd, c.index); close = i; }
    }
    if (inner === null) { inner = rest.slice(openEnd); close = rest.length; }
    out.push(makeNode(tag, parseAttrs(attrRaw), inner));
    rest = rest.slice(close);
  }
  return out;
}

var document = { createElement: function (tag) { return makeNode(tag, {}, ''); } };

var grid = makeNode('div', { 'class': 'nbgrid' }, '');
grid.innerHTML = scenario.shell || '';

/* eval, not require: the merge block is sliced out of the rendered page and has
   no module shape. `document` above is captured by closure. */
// eslint-disable-next-line no-eval
eval(mergeJs + '\n;this.__merge = mergeBoardCards; this.__key = groupKey;');
var merge = this.__merge, key = this.__key;

merge(grid, scenario.payload || '');

/* A card is `.pvcard`, NOT "anything groupKey() gave no key to" — a heading that
   carries no join key (an old payload predating data-lane) has no key either,
   and lumping it in with the cards would report a dropped-card count that is
   really a fallback heading. */
function isCard(el) { return el.classList.contains('pvcard'); }

var groups = [], cur = null, loose = [];
grid.children.forEach(function (el) {
  var k = key(el);
  if (k !== null) { cur = { key: k, tickers: [] }; groups.push(cur); return; }
  if (!isCard(el)) return;                       // keyless heading — counted below
  var tk = /<span class="nb-tk[^"]*"[^>]*>([^<]*)</.exec(el.innerHTML);
  var name = tk ? tk[1].trim() : (el.getAttribute('data-ticker') || '?');
  if (cur) cur.tickers.push(name); else loose.push(name);
});

process.stdout.write(JSON.stringify({
  groups: groups,
  looseBeforeFirstHeading: loose,
  headings: grid.querySelectorAll('.nb-stage-hd,.nb-lane-hd').length,
  cards: grid.children.filter(isCard).length
}));
