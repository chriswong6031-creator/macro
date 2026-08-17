#!/usr/bin/env node
'use strict';

var fs = require('fs');
var scenario = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
var runtimeJs = fs.readFileSync(process.argv[3], 'utf8');

function classSet(className) {
  return String(className || '').trim().split(/\s+/).filter(Boolean);
}

function makeNode(tag, attrs) {
  attrs = attrs || {};
  var node = {
    tagName: String(tag || 'div').toUpperCase(),
    id: attrs.id || '',
    name: attrs.name || '',
    type: attrs.type || '',
    className: attrs.class || attrs.className || '',
    hidden: !!attrs.hidden,
    disabled: false,
    value: attrs.value || '',
    placeholder: '',
    tabIndex: 0,
    parentNode: null,
    childNodes: [],
    style: {},
    dataset: {},
    attributes: {},
    listeners: {},
    label: '',
    selectedIndex: 0
  };
  node.classList = {
    add: function (name) {
      var parts = classSet(node.className);
      if (parts.indexOf(name) < 0) parts.push(name);
      node.className = parts.join(' ');
    },
    remove: function (name) {
      node.className = classSet(node.className).filter(function (item) { return item !== name; }).join(' ');
    },
    toggle: function (name, force) {
      var has = classSet(node.className).indexOf(name) >= 0;
      var on = force == null ? !has : !!force;
      if (on) node.classList.add(name); else node.classList.remove(name);
    },
    contains: function (name) { return classSet(node.className).indexOf(name) >= 0; }
  };
  node.setAttribute = function (name, value) {
    value = String(value);
    node.attributes[name] = value;
    if (name === 'id') node.id = value;
    if (name === 'class') node.className = value;
    if (name.slice(0, 5) === 'data-') node.dataset[name.slice(5).replace(/-([a-z])/g, function (_, ch) { return ch.toUpperCase(); })] = value;
  };
  node.getAttribute = function (name) {
    if (name === 'id') return node.id || null;
    if (name === 'class') return node.className || null;
    if (Object.prototype.hasOwnProperty.call(node.attributes, name)) return node.attributes[name];
    if (name.slice(0, 5) === 'data-') {
      var key = name.slice(5).replace(/-([a-z])/g, function (_, ch) { return ch.toUpperCase(); });
      return node.dataset[key] == null ? null : String(node.dataset[key]);
    }
    return null;
  };
  node.removeAttribute = function (name) {
    delete node.attributes[name];
    if (name.slice(0, 5) === 'data-') {
      var key = name.slice(5).replace(/-([a-z])/g, function (_, ch) { return ch.toUpperCase(); });
      delete node.dataset[key];
    }
  };
  node.appendChild = function (child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = node;
    node.childNodes.push(child);
    return child;
  };
  node.removeChild = function (child) {
    node.childNodes = node.childNodes.filter(function (item) { return item !== child; });
    child.parentNode = null;
    return child;
  };
  node.contains = function (other) {
    if (other === node) return true;
    return node.childNodes.some(function (child) { return child.contains && child.contains(other); });
  };
  node.addEventListener = function (name, fn) {
    (node.listeners[name] = node.listeners[name] || []).push(fn);
  };
  node.removeEventListener = function (name, fn) {
    node.listeners[name] = (node.listeners[name] || []).filter(function (item) { return item !== fn; });
  };
  node.dispatchEvent = function (event) {
    event = event || {};
    event.target = event.target || node;
    event.currentTarget = node;
    event.preventDefault = event.preventDefault || function () { event.defaultPrevented = true; };
    (node.listeners[event.type || event] || []).forEach(function (fn) { fn.call(node, event); });
  };
  node.focus = function () { document.activeElement = node; };
  node.blur = function () {};
  node.click = function () { node.dispatchEvent({ type: 'click', target: node }); };
  node.querySelector = function (sel) { return queryAll(node, sel)[0] || null; };
  node.querySelectorAll = function (sel) { return queryAll(node, sel); };
  Object.defineProperty(node, 'firstChild', { get: function () { return node.childNodes[0] || null; } });
  Object.defineProperty(node, 'lastChild', { get: function () { return node.childNodes[node.childNodes.length - 1] || null; } });
  Object.defineProperty(node, 'children', { get: function () { return node.childNodes.slice(); } });
  Object.defineProperty(node, 'options', {
    get: function () { return node.childNodes.filter(function (child) { return child.tagName === 'OPTION' || child.tagName === 'OPTGROUP'; }).reduce(function (list, child) {
      if (child.tagName === 'OPTGROUP') return list.concat(child.childNodes.filter(function (item) { return item.tagName === 'OPTION'; }));
      list.push(child);
      return list;
    }, []); }
  });
  Object.defineProperty(node, 'textContent', {
    get: function () {
      if (!node.childNodes.length) return node._text || '';
      return node.childNodes.map(function (child) { return child.textContent; }).join('');
    },
    set: function (value) {
      node.childNodes = [];
      node._text = value == null ? '' : String(value);
    }
  });
  Object.defineProperty(node, 'innerHTML', {
    get: function () { return node.textContent; },
    set: function (value) { node.textContent = value; }
  });
  Object.defineProperty(node, 'offsetParent', { get: function () { return node.hidden ? null : node.parentNode || document.body; } });
  Object.keys(attrs).forEach(function (key) {
    if (key === 'class' || key === 'className' || key === 'id' || key === 'hidden' || key === 'value' || key === 'type') return;
    node.setAttribute(key, attrs[key]);
  });
  if (attrs.id) node.id = attrs.id;
  if (attrs['data-mode']) node.setAttribute('data-mode', attrs['data-mode']);
  if (attrs['data-window']) node.setAttribute('data-window', attrs['data-window']);
  return node;
}

function matchSel(node, sel) {
  sel = String(sel || '').trim();
  if (!sel) return false;
  if (sel.charAt(0) === '#') return node.id === sel.slice(1);
  if (sel.charAt(0) === '.') return classSet(node.className).indexOf(sel.slice(1)) >= 0;
  var attr = sel.match(/^([a-z][\w-]*)?\[([^=\]]+)="([^"]*)"\]$/i);
  if (attr) {
    if (attr[1] && node.tagName !== attr[1].toUpperCase()) return false;
    return node.getAttribute(attr[2]) === attr[3];
  }
  var tagged = sel.match(/^([a-z][\w-]*)$/i);
  if (tagged) return node.tagName === tagged[1].toUpperCase();
  if (sel.indexOf('.') === 0) return false;
  var combo = sel.match(/^([a-z][\w-]*)\.([\w-]+)$/i);
  if (combo) return node.tagName === combo[1].toUpperCase() && classSet(node.className).indexOf(combo[2]) >= 0;
  return false;
}

function walk(node, visit) {
  visit(node);
  node.childNodes.forEach(function (child) { walk(child, visit); });
}

function queryAll(root, selector) {
  var parts = String(selector || '').split(',').map(function (item) { return item.trim(); }).filter(Boolean);
  var found = [];
  parts.forEach(function (part) {
    var tokens = part.split(/\s+/);
    var pool = [root];
    tokens.forEach(function (token, index) {
      var next = [];
      pool.forEach(function (start) {
        walk(start, function (node) {
          if ((index === 0 ? true : node !== start) && matchSel(node, token)) next.push(node);
        });
      });
      pool = next;
    });
    pool.forEach(function (node) { if (found.indexOf(node) < 0) found.push(node); });
  });
  found.item = function (i) { return found[i]; };
  return found;
}

var byId = {};
function attach(node) { if (node.id) byId[node.id] = node; return node; }

var html = makeNode('html');
html.setAttribute('data-lang', scenario.lang || 'en');
var body = makeNode('body');
body.className = 'bci-page';
html.appendChild(body);

function el(tag, attrs, children) {
  var node = attach(makeNode(tag, attrs || {}));
  (children || []).forEach(function (child) { node.appendChild(typeof child === 'string' ? makeNode('#text') && null : child); });
  return node;
}

function textNode(tag, attrs, text) {
  var node = attach(makeNode(tag, attrs || {}));
  node.textContent = text || '';
  return node;
}

function spanPair(en, zh) {
  var wrap = makeNode('span');
  var english = makeNode('span', { class: 'l-en' }); english.textContent = en;
  var chinese = makeNode('span', { class: 'l-zh' }); chinese.textContent = zh;
  wrap.appendChild(english); wrap.appendChild(chinese);
  return wrap;
}

var workspace = attach(makeNode('main', { id: 'bci-workspace', class: 'bci-workspace' }));
workspace.dataset.state = 'loading';
workspace.setAttribute('data-state', 'loading');
var runStatus = makeNode('div', { class: 'bci-run-status' });
runStatus.appendChild(textNode('span', { id: 'bci-status-label' }, 'Connecting'));
runStatus.appendChild(textNode('span', { id: 'bci-status-detail' }, ''));
var refresh = attach(makeNode('button', { id: 'bci-refresh' }));
runStatus.appendChild(refresh);
workspace.appendChild(runStatus);

var modeControl = attach(makeNode('div', { id: 'bci-mode-control' }));
['milestones', 'screen', 'peers', 'changes', 'prospective'].forEach(function (mode, index) {
  var button = attach(makeNode('button', { id: 'bci-mode-' + mode, class: 'bci-mode' + (index === 0 ? ' is-active' : '') }));
  button.setAttribute('data-mode', mode);
  button.id = 'bci-mode-' + mode;
  modeControl.appendChild(button);
});
workspace.appendChild(modeControl);

var windowControl = attach(makeNode('fieldset', { id: 'bci-window-control' }));
windowControl.appendChild(textNode('legend', { id: 'bci-window-label' }, 'Record window'));
var windowOptions = makeNode('div', { class: 'bci-window-options' });
['30', '90', '180', 'all'].forEach(function (value) {
  var button = makeNode('button', { class: 'bci-window' + (value === '90' ? ' is-active' : '') });
  button.setAttribute('data-window', value);
  windowOptions.appendChild(button);
});
windowControl.appendChild(windowOptions);
workspace.appendChild(windowControl);

function labeledControl(id, forId, tag) {
  var label = makeNode('label');
  if (id) { label.id = id; attach(label); }
  label.setAttribute('for', forId);
  var caption = makeNode('span', { class: 'bci-control-label' });
  if (forId === 'bci-change-kind-filter') {
    caption.id = 'bci-change-kind-label';
    attach(caption);
  }
  caption.appendChild(spanPair('Label', '标签'));
  label.appendChild(caption);
  var control = attach(makeNode(tag || 'select', { id: forId }));
  if (tag === 'select') {
    var opt = makeNode('option'); opt.value = ''; opt.textContent = ''; control.appendChild(opt);
  }
  label.appendChild(control);
  workspace.appendChild(label);
  return control;
}

labeledControl('bci-field-control', 'bci-field-filter', 'select');
labeledControl('bci-change-kind-control', 'bci-change-kind-filter', 'select');
labeledControl('bci-review-control', 'bci-review-filter', 'select');
labeledControl('', 'bci-search', 'input');
labeledControl('', 'bci-phase-filter', 'select');
labeledControl('', 'bci-status-filter', 'select');
labeledControl('', 'bci-condition-filter', 'input');
var screenControls = attach(makeNode('div', { id: 'bci-screen-controls' }));
labeledControl('', 'bci-sponsor-filter', 'input');
labeledControl('', 'bci-intervention-filter', 'input');
labeledControl('', 'bci-study-type-filter', 'select');
screenControls.appendChild(attach(makeNode('input', { id: 'bci-pc-from' })));
screenControls.appendChild(attach(makeNode('input', { id: 'bci-pc-to' })));
workspace.appendChild(screenControls);
var cohort = attach(makeNode('div', { id: 'bci-cohort' }));
cohort.appendChild(attach(makeNode('textarea', { id: 'bci-cohort-input' })));
cohort.appendChild(attach(makeNode('button', { id: 'bci-cohort-run', class: 'bci-cohort-run' })));
workspace.appendChild(cohort);
workspace.appendChild(attach(makeNode('button', { id: 'bci-clear' })));
workspace.appendChild(attach(makeNode('button', { id: 'bci-brain-launch' })));
workspace.appendChild(textNode('p', { id: 'bci-source-note-copy' }, ''));
workspace.appendChild(attach(makeNode('div', { id: 'bci-facets' })));

var queuePane = attach(makeNode('section', { id: 'bci-queue-pane' }));
queuePane.appendChild(textNode('p', { id: 'bci-queue-kicker' }, ''));
queuePane.appendChild(textNode('h2', { id: 'bci-queue-title' }, ''));
queuePane.appendChild(textNode('p', { id: 'bci-queue-subtitle' }, ''));
queuePane.appendChild(textNode('div', { id: 'bci-asof' }, ''));
var decision = attach(makeNode('div', { id: 'bci-decision' }));
decision.appendChild(textNode('span', { id: 'bci-decision-stance' }, ''));
decision.appendChild(textNode('p', { id: 'bci-decision-why' }, ''));
queuePane.appendChild(decision);
var braid = attach(makeNode('section', { id: 'bci-braid' }));
braid.appendChild(attach(makeNode('div', { id: 'bci-braid-plot' })));
braid.appendChild(attach(makeNode('div', { id: 'bci-braid-scale' })));
braid.appendChild(textNode('span', { id: 'bci-braid-unit' }, ''));
braid.appendChild(textNode('p', { id: 'bci-braid-readout' }, ''));
braid.appendChild(textNode('p', { id: 'bci-braid-foot' }, ''));
braid.appendChild(attach(makeNode('ul', { id: 'bci-braid-list' })));
queuePane.appendChild(braid);
queuePane.appendChild(attach(makeNode('div', { id: 'bci-query-chips' })));
queuePane.appendChild(textNode('div', { id: 'bci-state-notice' }, ''));
queuePane.appendChild(textNode('p', { id: 'bci-page-status' }, ''));
queuePane.appendChild(attach(makeNode('div', { id: 'bci-queue' })));
queuePane.appendChild(textNode('p', { id: 'bci-panel-foot' }, ''));
var footer = attach(makeNode('div', { id: 'bci-queue-footer' }));
var loadMore = attach(makeNode('button', { id: 'bci-load-more' }));
loadMore.appendChild(spanPair('Load more', '加载更多'));
footer.appendChild(loadMore);
queuePane.appendChild(footer);
workspace.appendChild(queuePane);

var inspector = attach(makeNode('aside', { id: 'bci-inspector-pane' }));
inspector.appendChild(textNode('h2', { id: 'bci-inspector-title' }, ''));
inspector.appendChild(attach(makeNode('button', { id: 'bci-inspector-close' })));
inspector.appendChild(attach(makeNode('div', { id: 'bci-inspector-body' })));
workspace.appendChild(inspector);
workspace.appendChild(attach(makeNode('div', { id: 'bci-scrim' })));
body.appendChild(workspace);

var documentListeners = {};
var document = {
  documentElement: html,
  body: body,
  readyState: 'complete',
  activeElement: body,
  getElementById: function (id) { return byId[id] || null; },
  querySelector: function (sel) { return queryAll(html, sel)[0] || null; },
  querySelectorAll: function (sel) { return queryAll(html, sel); },
  createElement: function (tag) { return makeNode(tag); },
  createTextNode: function (value) {
    var node = makeNode('#text');
    node.tagName = '#TEXT';
    node.textContent = value == null ? '' : String(value);
    return node;
  },
  contains: function (node) { return !!(node && body.contains(node)); },
  addEventListener: function (name, fn) { (documentListeners[name] = documentListeners[name] || []).push(fn); },
  removeEventListener: function () {}
};

var location = {
  href: 'https://www.mastermind-x.com/biocatalyst.html' + (scenario.search || ''),
  pathname: '/biocatalyst.html',
  search: scenario.search || '',
  hash: ''
};
var history = {
  replaceState: function (_state, _title, url) {
    var parsed = new URL(url, 'https://www.mastermind-x.com');
    location.href = parsed.href;
    location.pathname = parsed.pathname;
    location.search = parsed.search;
    location.hash = parsed.hash;
  }
};

function routeFor(url) {
  var path = String(url || '').split('?')[0];
  var table = scenario.routes || {};
  var keys = Object.keys(table);
  for (var i = 0; i < keys.length; i += 1) {
    if (path === keys[i] || path.indexOf(keys[i]) === 0) return table[keys[i]];
  }
  return { status: 503, body: '{"detail":"missing fixture"}', contentType: 'application/json' };
}

var fetchCalls = [];
function fetch(url) {
  fetchCalls.push(String(url));
  var route = routeFor(url);
  var status = route.status == null ? 200 : route.status;
  var body = route.body == null ? '' : String(route.body);
  var contentType = route.contentType || (status === 200 ? 'application/json' : 'application/json');
  var headers = { get: function (name) { return String(name).toLowerCase() === 'content-type' ? contentType : null; } };
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status: status,
    headers: headers,
    text: function () { return Promise.resolve(body); },
    json: function () { return Promise.resolve(JSON.parse(body)); }
  });
}

var window = {
  location: location,
  history: history,
  document: document,
  fetch: fetch,
  MDXAuth: null,
  MMBrain: null,
  matchMedia: function () { return { matches: false, addEventListener: function () {}, addListener: function () {} }; },
  addEventListener: function () {},
  innerWidth: 1440
};
window.window = window;
global.document = document;
global.window = window;
global.fetch = fetch;
global.HTMLElement = function () {};
global.Node = function () {};

eval(runtimeJs);

function snapshot() {
  return {
    workspaceState: workspace.dataset.state || workspace.getAttribute('data-state'),
    decisionState: decision.getAttribute('data-state'),
    status: byId['bci-status-label'].textContent,
    statusDetail: byId['bci-status-detail'].textContent,
    notice: byId['bci-state-notice'].textContent,
    queue: byId['bci-queue'].textContent,
    inspector: byId['bci-inspector-body'].textContent,
    inspectorTitle: byId['bci-inspector-title'].textContent,
    subtitle: byId['bci-queue-subtitle'].textContent,
    stance: byId['bci-decision-stance'].textContent,
    why: byId['bci-decision-why'].textContent,
    fetchCalls: fetchCalls.slice()
  };
}

function settled(state) {
  return ['locked', 'empty', 'ready', 'integrity_block', 'source_outage', 'unavailable', 'generation-restarted', 'withheld'].indexOf(state) >= 0;
}

function waitFor(predicate, leftover) {
  leftover = leftover == null ? 80 : leftover;
  return new Promise(function (resolve, reject) {
    function tick() {
      if (predicate()) return resolve();
      if (leftover <= 0) return reject(new Error('timed out waiting for hydration; state=' + (workspace.dataset.state || workspace.getAttribute('data-state'))));
      leftover -= 1;
      setTimeout(tick, 0);
    }
    tick();
  });
}

waitFor(function () { return settled(workspace.dataset.state || workspace.getAttribute('data-state')); }).then(function () {
  var first = snapshot();
  if (scenario.secondRoutes) scenario.routes = scenario.secondRoutes;
  if (scenario.clickRefresh) {
    byId['bci-refresh'].click();
  } else if (scenario.clickMode) {
    var button = byId['bci-mode-' + scenario.clickMode];
    button.click();
  } else if (scenario.clickTrial) {
    var row = document.querySelector('[data-trial-id="' + scenario.clickTrial + '"]');
    if (!row) throw new Error('no trial row for ' + scenario.clickTrial);
    row.click();
  } else {
    process.stdout.write(JSON.stringify({ first: first, second: null }));
    return;
  }
  var callsBefore = first.fetchCalls.length;
  return waitFor(function () {
    if (scenario.clickTrial) {
      var body = byId['bci-inspector-body'].textContent || '';
      return fetchCalls.length > callsBefore &&
        body.indexOf('Reading the current official record') < 0 &&
        body.indexOf('正在读取当前官方记录') < 0;
    }
    var state = workspace.dataset.state || workspace.getAttribute('data-state');
    return settled(state) && fetchCalls.length > callsBefore;
  }).then(function () {
    process.stdout.write(JSON.stringify({ first: first, second: snapshot() }));
  }, function () {
    process.stdout.write(JSON.stringify({ first: first, second: snapshot() }));
  });
}).catch(function (error) {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
