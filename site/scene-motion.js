/*
 * MastermindX scene motion
 * ------------------------
 * Small, declarative choreography for the public landing and product pages.
 * A scene only advances while it is visible, the tab is active, motion is
 * allowed, and Save-Data is off. CSS owns the drawings; this file owns time.
 */
(function () {
  'use strict';

  var root = document.documentElement;
  var path = location.pathname;
  var file = path.split('/').pop() || 'index.html';
  var reduced = matchMedia('(prefers-reduced-motion: reduce)');
  var still = /(?:^|[?&])still(?:=1|=true|&|$)/i.test(location.search) ||
    root.classList.contains('still');
  var saveData = !!(navigator.connection && navigator.connection.saveData);
  var staticMode = still || reduced.matches || saveData;
  var page = file === 'market-dashboards.html' ? 'dashboards' :
    file === 'mastermind-ai.html' ? 'mastermind-ai' :
    file === 'market-terminal.html' ? 'market-terminal' : 'landing';

  var phaseTimes = {
    observe: 1250,
    reason: 1750,
    resolve: 1900,
    hold: 3200,
    reset: 500
  };

  var selectors = {
    landing: [
      '#f-terminal', '#f-prophet', '#f-rotations', '#f-filings', '#f-sits', '#f-funds',
      '#f-beyond', '#ai'
    ],
    dashboards: [
      '.phero .pstage', '#regime', '#lanes', '#rotations', '#filings',
      '#flow', '#china', '#record', '#beyond', '#nightly'
    ],
    'mastermind-ai': [
      '.phero .pstage', '#everywhere', '#grounded', '#receipts', '#stance',
      '#draws', 'section.feature#lanes'
    ],
    'market-terminal': [
      '.phero .pstage', '#charting', '#watchlists', '#dossier',
      '#signals', '#options', '#ai'
    ]
  };

  root.dataset.motionPage = page;
  root.classList.add('mm-motion-ready');
  if (staticMode) root.classList.add('mm-motion-static');

  function uniqueScenes() {
    var seen = [];
    (selectors[page] || []).forEach(function (selector) {
      document.querySelectorAll(selector).forEach(function (node) {
        if (seen.indexOf(node) < 0) seen.push(node);
      });
    });
    return seen;
  }

  function labelScene(scene, index) {
    scene.dataset.mmScene = String(index + 1);
    scene.dataset.mmPhase = staticMode ? 'resolve' : 'idle';
    scene.style.setProperty('--mm-scene-index', index);

    scene.querySelectorAll(
      '.md-tile,.fi-row,.md-tr,.md-mk,.md-rc,.md-as,.md-eb,.md-oc,' +
      '.ma-node,.ma-tag,.ma-steps>li,.ma-st,.ma-cite,.ma-outline>li,' +
      '.mt-row,.mt-k,.mt-dn,.cd,.r,.thm,.mt-tf .pn,.mt-wl .gp,' +
      '.mt-dos .tabs span,.mt-dos .fr,.mt-read .seg,.mt-read .c,' +
      '.mt-gx .sr,.mt-fl .fr,.mt-tools span,.mt-thread>.msg'
    ).forEach(function (item, itemIndex) {
      item.style.setProperty('--mm-i', itemIndex);
    });

    var demo = scene.matches('.pstage') ? scene :
      scene.querySelector('.demo,.ph-belt');
    if (demo) {
      demo.classList.add('mm-stage');
      var rail = document.createElement('span');
      rail.className = 'mm-phase-rail';
      rail.setAttribute('aria-hidden', 'true');
      rail.innerHTML = '<i></i><i></i><i></i>';
      demo.appendChild(rail);
    }
  }

  var scenes = uniqueScenes();
  scenes.forEach(labelScene);

  if (!scenes.length || staticMode) return;

  var state = new Map();
  var phases = ['observe', 'reason', 'resolve', 'hold', 'reset'];

  function clear(scene) {
    var entry = state.get(scene);
    if (!entry) return;
    if (entry.timer) clearTimeout(entry.timer);
    entry.timer = 0;
  }

  function canRun(scene) {
    var entry = state.get(scene);
    return !!entry && entry.visible && !document.hidden && !staticMode;
  }

  function schedule(scene, delay) {
    clear(scene);
    var entry = state.get(scene);
    if (!entry || !canRun(scene)) return;
    entry.timer = setTimeout(function () {
      advance(scene);
    }, delay);
  }

  function advance(scene) {
    if (!canRun(scene)) return;
    var entry = state.get(scene);
    entry.phase = (entry.phase + 1) % phases.length;
    var phase = phases[entry.phase];

    if (phase === 'reset') {
      scene.dataset.mmPhase = 'idle';
      scene.classList.remove('mm-scene-live');
      scene.dispatchEvent(new CustomEvent('mm:phase', {
        detail: { phase: 'idle' }
      }));
      schedule(scene, phaseTimes.reset);
      return;
    }

    scene.dataset.mmPhase = phase;
    scene.classList.add('mm-scene-live');
    scene.style.setProperty('--mm-cycle', String(entry.cycles));
    scene.dispatchEvent(new CustomEvent('mm:phase', {
      detail: { phase: phase, cycle: entry.cycles }
    }));

    if (phase === 'hold') entry.cycles += 1;
    schedule(scene, phaseTimes[phase]);
  }

  function start(scene) {
    var entry = state.get(scene);
    if (!entry || !canRun(scene) || entry.timer) return;
    if (scene.dataset.mmPhase === 'idle') {
      entry.phase = -1;
      advance(scene);
    } else {
      schedule(scene, phaseTimes[scene.dataset.mmPhase] || 800);
    }
  }

  function pause(scene) {
    clear(scene);
    scene.classList.remove('mm-scene-live');
  }

  scenes.forEach(function (scene) {
    state.set(scene, { visible: false, timer: 0, phase: -1, cycles: 0 });
  });

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      var scene = entry.target;
      var sceneState = state.get(scene);
      if (!sceneState) return;
      sceneState.visible = entry.isIntersecting && entry.intersectionRatio >= 0.12;
      scene.classList.toggle('mm-scene-visible', sceneState.visible);
      if (sceneState.visible) start(scene);
      else pause(scene);
    });
  }, { rootMargin: '80px 0px 80px', threshold: [0, 0.12, 0.35] });

  scenes.forEach(function (scene) { observer.observe(scene); });

  document.addEventListener('visibilitychange', function () {
    scenes.forEach(function (scene) {
      if (document.hidden) pause(scene);
      else start(scene);
    });
  });

  function lockToStatic(event) {
    if (!event.matches) return;
    staticMode = true;
    root.classList.add('mm-motion-static');
    scenes.forEach(function (scene) {
      pause(scene);
      scene.dataset.mmPhase = 'resolve';
    });
  }

  if (reduced.addEventListener) reduced.addEventListener('change', lockToStatic);
  else if (reduced.addListener) reduced.addListener(lockToStatic);
})();
