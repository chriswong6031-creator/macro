/* Slate — Brain: ephemeral capture board + permanent topic library.
   Notes are saved into their topic the moment they're filed ("shadow push");
   the capture board itself is session-only and wipes on refresh/close. */
'use strict';

let brainTab = 'board';                 // 'board' | 'library' (session only)
let captureNotes = [];                  // [{id, x, y}] — refs to saved notes, session only
let brainScroll = { x: 0, y: 0 };       // capture-board scroll, session only
let activeBnoteComposer = null;         // open composer element (survives re-renders)
const BNOTE_W = 340;

/* ---------- lookups ---------- */
function findNote(noteId) {
  for (const cat of state.brain.categories) {
    const i = cat.notes.findIndex(n => n.id === noteId);
    if (i >= 0) return { cat, note: cat.notes[i], index: i };
  }
  return null;
}
function findCat(catId) { return state.brain.categories.find(c => c.id === catId); }
function catColor(cat) { return tagColor(cat.name); }

/* ---------- rendering ---------- */
let lastBrainTabRendered = null; // scroll resets only when a tab is ENTERED, not on in-place re-renders
function renderBrain() {
  const entering = lastBrainTabRendered !== brainTab;
  lastBrainTabRendered = brainTab;
  if (brainTab === 'library') renderLibrary(entering);
  else renderCaptureBoard();
  if (entering) fadeIn($('#viewport'));
}

function renderCaptureBoard() {
  const canvas = $('#canvas');
  canvas.style.width = CANVAS_W + 'px';
  canvas.style.height = CANVAS_H + 'px';
  canvas.textContent = '';
  captureNotes = captureNotes.filter(ref => findNote(ref.id)); // drop refs to deleted notes
  for (const ref of captureNotes) {
    const f = findNote(ref.id);
    const node = bnoteEl(f.note);
    node.style.left = ref.x + 'px';
    node.style.top = ref.y + 'px';
    canvas.appendChild(node);
  }
  if (activeBnoteComposer) canvas.appendChild(activeBnoteComposer);
  const hint = $('#hint');
  hint.textContent = 'Double-click anywhere to write down something you’ve learned';
  hint.hidden = captureNotes.length > 0 || !!activeBnoteComposer;
  const vp = $('#viewport');
  vp.scrollLeft = brainScroll.x;
  vp.scrollTop = brainScroll.y;
}

function renderLibrary(resetScroll) {
  const lib = $('#library');
  lib.textContent = '';
  $('#hint').hidden = true;
  const cats = state.brain.categories;
  const total = cats.reduce((n, c) => n + c.notes.length, 0);
  const head = el('div', 'library-head');
  head.appendChild(el('h1', 'library-title', 'Library'));
  head.appendChild(el('span', 'library-count', total + (total === 1 ? ' note' : ' notes') + ' · ' + cats.length + (cats.length === 1 ? ' topic' : ' topics')));
  lib.appendChild(head);
  if (!cats.length) {
    const empty = el('div', 'library-empty');
    empty.appendChild(el('div', 'library-empty-title', 'Nothing saved yet'));
    empty.appendChild(el('div', 'library-empty-sub', 'Write your first note on the Board — it lands here, filed under its topic.'));
    lib.appendChild(empty);
  } else {
    const grid = el('div', 'library-grid');
    for (const cat of cats) grid.appendChild(paneEl(cat));
    lib.appendChild(grid);
  }
  if (resetScroll) {
    $('#viewport').scrollTop = 0;
    $('#viewport').scrollLeft = 0;
  }
}

function bnoteEl(note) {
  const f = findNote(note.id);
  const color = f ? catColor(f.cat) : null;
  const root = el('article', 'bnote' + (color ? ' tint-' + color : ''));
  root.dataset.id = note.id;
  root.appendChild(el('div', 'bnote-text', note.text));
  const foot = el('div', 'bnote-foot');
  if (f) foot.appendChild(el('span', 'chip tag-chip tint-' + color, f.cat.name));
  const saved = el('span', 'bnote-saved');
  saved.appendChild(svgIcon(ICONS.check, 10, 2.2));
  saved.appendChild(el('span', null, 'Saved'));
  foot.appendChild(saved);
  root.appendChild(foot);
  return root;
}

function paneEl(cat) {
  const color = catColor(cat);
  const root = el('section', 'pane');
  root.dataset.id = cat.id;
  const head = el('header', 'pane-head');
  head.appendChild(el('span', 'pane-dot tint-' + color));
  const title = el('h2', 'pane-title', cat.name);
  title.title = 'Double-click to rename';
  const count = el('span', 'board-count', String(cat.notes.length));
  const menu = el('button', 'ghost-btn pane-menu-btn');
  menu.title = 'Topic actions';
  menu.appendChild(svgIcon(ICONS.dots, 15, 2.2));
  head.append(title, count, menu);
  root.appendChild(head);
  const list = el('div', 'pane-notes');
  if (!cat.notes.length) list.appendChild(el('div', 'pane-empty', 'Nothing filed here yet'));
  for (const n of cat.notes) {
    const p = el('article', 'pnote');
    p.dataset.id = n.id;
    p.appendChild(el('div', 'pnote-text', n.text));
    p.appendChild(el('div', 'pnote-date', new Date(n.created).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })));
    list.appendChild(p);
  }
  root.appendChild(list);
  return root;
}

/* ---------- the shadow push ---------- */
function flyToLibrary(fromEl) {
  const target = $('#brainTabs .seg-btn[data-tab="library"]');
  if (!target || !fromEl) return;
  const a = fromEl.getBoundingClientRect();
  const b = target.getBoundingClientRect();
  const g = el('div', 'fly-ghost');
  g.style.left = a.left + 'px';
  g.style.top = a.top + 'px';
  g.style.width = a.width + 'px';
  g.style.height = a.height + 'px';
  document.body.appendChild(g);
  g.getBoundingClientRect();
  const dx = (b.left + b.width / 2) - (a.left + a.width / 2);
  const dy = (b.top + b.height / 2) - (a.top + a.height / 2);
  g.style.transform = 'translate(' + dx + 'px,' + dy + 'px) scale(0.05)';
  g.style.opacity = '0.2';
  setTimeout(() => {
    g.remove();
    target.classList.add('pulse');
    setTimeout(() => target.classList.remove('pulse'), 420);
  }, 560);
}

/* ---------- note composer (double-click / FAB) ---------- */
function openBnoteComposer(x, y) {
  if (activeBnoteComposer) { $('textarea', activeBnoteComposer).focus(); return; }
  const canvas = $('#canvas');
  const comp = el('article', 'bnote composing');
  comp.style.left = clamp(x, 8, CANVAS_W - BNOTE_W - 8) + 'px';
  comp.style.top = clamp(y, 8, CANVAS_H - 260) + 'px';

  const ta = el('textarea', 'bnote-input');
  ta.rows = 3;
  ta.placeholder = 'Write down what you’ve learned…';
  comp.appendChild(ta);

  comp.appendChild(el('div', 'bnote-label', 'File under'));
  const topics = el('div', 'bnote-topics');
  comp.appendChild(topics);
  const newTopic = el('input', 'bnote-newtopic');
  newTopic.placeholder = state.brain.categories.length ? 'New topic…' : 'Name a topic…';
  newTopic.maxLength = 40;
  comp.appendChild(newTopic);

  const actions = el('div', 'bnote-actions');
  const saveBtn = el('button', 'primary-btn', 'Save');
  const needMsg = el('span', 'bnote-need');
  const cancel = el('button', 'ghost-btn');
  cancel.title = 'Discard';
  cancel.appendChild(svgIcon(ICONS.x, 13, 1.7));
  actions.append(saveBtn, needMsg, cancel);
  comp.appendChild(actions);

  let selectedCatId = null;
  function renderTopics() {
    topics.textContent = '';
    const pending = newTopic.value.trim();
    for (const cat of state.brain.categories) {
      const chip = el('button', 'chip tag-chip topic-chip tint-' + catColor(cat) + (cat.id === selectedCatId && !pending ? ' active' : ''), cat.name);
      chip.addEventListener('click', () => {
        selectedCatId = cat.id;
        newTopic.value = '';
        renderTopics();
        refresh();
      });
      topics.appendChild(chip);
    }
    if (pending) {
      const chip = el('span', 'chip tag-chip topic-chip active tint-' + tagColor(pending), pending);
      topics.appendChild(chip);
    }
  }
  function refresh() {
    const hasText = !!ta.value.trim();
    const hasTopic = !!(newTopic.value.trim() || selectedCatId);
    saveBtn.disabled = !(hasText && hasTopic);
    needMsg.textContent = hasText && !hasTopic ? 'Pick a topic to save' : '';
  }
  ta.addEventListener('input', refresh);
  newTopic.addEventListener('input', () => { renderTopics(); refresh(); });
  newTopic.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); ta.focus(); }
    if (e.key === 'Escape') discard();
  });
  renderTopics();
  refresh();
  autoGrow(ta);

  function submit() {
    const text = ta.value.trim();
    const pending = newTopic.value.trim();
    if (!text || (!pending && !selectedCatId)) return;
    let cat;
    if (pending) {
      cat = state.brain.categories.find(c => c.name.toLowerCase() === pending.toLowerCase());
      if (!cat) { cat = newCategory(pending); state.brain.categories.push(cat); }
    } else {
      cat = findCat(selectedCatId);
      if (!cat) return;
    }
    const note = newNote(text);
    cat.notes.unshift(note);   // saved permanently, right now
    save();
    captureNotes.push({ id: note.id, x: parseInt(comp.style.left, 10), y: parseInt(comp.style.top, 10) });
    const savedNode = bnoteEl(note);
    savedNode.style.left = comp.style.left;
    savedNode.style.top = comp.style.top;
    savedNode.classList.add('bnote-enter');
    comp.replaceWith(savedNode);
    activeBnoteComposer = null;
    flyToLibrary(savedNode);
  }
  function discard() {
    comp.remove();
    activeBnoteComposer = null;
    $('#hint').hidden = captureNotes.length > 0;
  }
  saveBtn.addEventListener('click', submit);
  cancel.addEventListener('click', discard);
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); }
    if (e.key === 'Escape') discard();
  });

  activeBnoteComposer = comp;
  canvas.appendChild(comp);
  $('#hint').hidden = true;
  ta.focus();
}

/* ---------- note modal (edit / re-file / delete) ---------- */
function openNoteModal(noteId) {
  const f = findNote(noteId);
  if (!f) return;
  const note = f.note;
  let cat = f.cat;
  const root = $('#modalRoot');
  root.textContent = '';

  const backdrop = el('div', 'modal-backdrop');
  const modal = el('div', 'modal tint-' + catColor(cat));
  modal.appendChild(el('div', 'modal-accent'));
  const body = el('div', 'modal-body');
  modal.appendChild(body);

  const ta = el('textarea', 'bnote-edit');
  ta.value = note.text;
  ta.placeholder = 'Your note';
  ta.addEventListener('input', () => { if (ta.value.trim()) note.text = ta.value.trim(); save(); });
  ta.addEventListener('blur', () => { if (!ta.value.trim()) ta.value = note.text; });
  body.appendChild(ta);
  autoGrow(ta);

  const topicSec = el('div', 'modal-section');
  topicSec.appendChild(el('div', 'modal-label', 'Topic'));
  const chips = el('div', 'bnote-topics');
  topicSec.appendChild(chips);
  const newTopic = el('input', 'bnote-newtopic');
  newTopic.placeholder = 'Move to a new topic…';
  newTopic.maxLength = 40;
  topicSec.appendChild(newTopic);
  body.appendChild(topicSec);

  function moveTo(target) {
    if (target === cat) return;
    const i = cat.notes.indexOf(note);
    if (i >= 0) cat.notes.splice(i, 1);
    target.notes.unshift(note);
    cat = target;
    save();
    modal.className = 'modal tint-' + catColor(cat);
    renderChips();
  }
  function renderChips() {
    chips.textContent = '';
    for (const c of state.brain.categories) {
      const chip = el('button', 'chip tag-chip topic-chip tint-' + catColor(c) + (c === cat ? ' active' : ''), c.name);
      chip.addEventListener('click', () => moveTo(c));
      chips.appendChild(chip);
    }
  }
  newTopic.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const name = newTopic.value.trim();
    if (!name) return;
    let target = state.brain.categories.find(c => c.name.toLowerCase() === name.toLowerCase());
    if (!target) { target = newCategory(name); state.brain.categories.push(target); }
    newTopic.value = '';
    moveTo(target);
  });
  renderChips();

  const foot = el('div', 'modal-foot');
  const stamp = el('span', 'modal-stamp', 'Saved ' + new Date(note.created).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }));
  const del = el('button', 'ghost-btn danger');
  del.appendChild(svgIcon(ICONS.trash, 13, 1.5));
  del.appendChild(el('span', null, 'Delete'));
  del.addEventListener('click', () => {
    closeModal();
    const holder = cat;
    const idx = holder.notes.indexOf(note);
    if (idx >= 0) holder.notes.splice(idx, 1);
    const capRef = captureNotes.find(r => r.id === note.id);
    captureNotes = captureNotes.filter(r => r.id !== note.id);
    save();
    renderAll();
    undoableToast('Note deleted', () => {
      holder.notes.splice(clamp(idx, 0, holder.notes.length), 0, note);
      if (capRef) captureNotes.push(capRef);
    });
  });
  foot.append(del, stamp);
  modal.appendChild(foot);

  backdrop.appendChild(modal);
  root.appendChild(backdrop);
  requestAnimationFrame(() => backdrop.classList.add('show'));

  let closed = false;
  function closeModal() {
    if (closed) return;
    closed = true;
    backdrop.classList.remove('show');
    setTimeout(() => backdrop.remove(), 180);
    window.removeEventListener('keydown', onKey);
    save.flush();
    if (state.view === 'brain') renderAll();
  }
  backdrop.addEventListener('mousedown', (e) => { if (e.target === backdrop) closeModal(); });
  function onKey(e) { if (e.key === 'Escape' && !activePopoverClose) closeModal(); }
  window.addEventListener('keydown', onKey);
  ta.focus();
  ta.setSelectionRange(ta.value.length, ta.value.length);
}

/* ---------- pane menu (rename / delete topic) ---------- */
function startPaneRename(paneNode, cat) {
  const titleEl = $('.pane-title', paneNode);
  const input = el('input', 'board-title-input');
  input.value = cat.name;
  input.maxLength = 40;
  titleEl.replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const commit = () => {
    if (done) return;
    done = true;
    const v = input.value.trim();
    if (v && v !== cat.name) {
      const dup = state.brain.categories.find(c => c !== cat && c.name.toLowerCase() === v.toLowerCase());
      if (dup) toast('A topic named "' + dup.name + '" already exists', { tone: 'danger' });
      else cat.name = v;
    }
    save();
    renderLibrary();
  };
  input.addEventListener('blur', commit);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = cat.name; input.blur(); }
  });
}

function openPaneMenu(anchor, cat) {
  openPopover(anchor, (pop, close) => {
    pop.appendChild(popItem('Rename topic', ICONS.pencil, () => {
      close();
      const node = $('.pane[data-id="' + cat.id + '"]');
      if (node) startPaneRename(node, cat);
    }));
    pop.appendChild(popItem('Delete topic', ICONS.trash, () => {
      close();
      const idx = state.brain.categories.indexOf(cat);
      state.brain.categories.splice(idx, 1);
      captureNotes = captureNotes.filter(r => !cat.notes.some(n => n.id === r.id));
      save();
      renderLibrary();
      const n = cat.notes.length;
      const msg = n ? 'Topic "' + cat.name + '" and ' + n + (n === 1 ? ' note' : ' notes') + ' deleted'
        : 'Topic "' + cat.name + '" deleted';
      undoableToast(msg,
        () => state.brain.categories.splice(clamp(idx, 0, state.brain.categories.length), 0, cat));
    }, 'danger'));
  });
}

/* ---------- interactions ---------- */
(function brainInteractions() {
  const canvas = $('#canvas');
  const vp = $('#viewport');

  canvas.addEventListener('dblclick', (e) => {
    if (state.view !== 'brain' || brainTab !== 'board') return;
    if (e.target !== canvas) return;
    const r = canvas.getBoundingClientRect();
    openBnoteComposer(e.clientX - r.left - BNOTE_W / 2, e.clientY - r.top - 20);
  });

  $('#fabCapture').addEventListener('click', () => {
    if (activeBnoteComposer) { $('textarea', activeBnoteComposer).focus(); return; }
    const x = vp.scrollLeft + vp.clientWidth / 2 - BNOTE_W / 2;
    const y = vp.scrollTop + Math.min(vp.clientHeight / 3, 220);
    openBnoteComposer(x, y);
    const comp = activeBnoteComposer;
    if (comp) comp.scrollIntoView({ block: 'center', inline: 'center' });
  });

  /* drag saved notes around the capture board */
  let d = null;
  let suppressClick = false;
  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || state.view !== 'brain') return;
    const node = e.target.closest('.bnote');
    if (!node || node.classList.contains('composing')) return;
    if (e.target.closest('button, input, textarea')) return;
    d = { node, sx: e.clientX, sy: e.clientY, ox: parseInt(node.style.left, 10), oy: parseInt(node.style.top, 10), h: node.offsetHeight, moved: false };
  });
  window.addEventListener('pointermove', (e) => {
    if (!d) return;
    const dx = e.clientX - d.sx, dy = e.clientY - d.sy;
    if (!d.moved && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    if (!d.moved) { d.moved = true; d.node.classList.add('bnote-dragging'); document.body.classList.add('dragging-any'); lockTouchScroll(); }
    d.node.style.left = clamp(d.ox + dx, 0, CANVAS_W - BNOTE_W) + 'px';
    d.node.style.top = clamp(d.oy + dy, 0, CANVAS_H - Math.max(60, d.h)) + 'px';
    autoscrollViewport(e);
  });
  function finishBnoteDrag(revert) {
    if (revert) { d.node.style.left = d.ox + 'px'; d.node.style.top = d.oy + 'px'; }
    else {
      const ref = captureNotes.find(r => r.id === d.node.dataset.id);
      if (ref) { ref.x = parseInt(d.node.style.left, 10); ref.y = parseInt(d.node.style.top, 10); }
    }
    d.node.classList.remove('bnote-dragging');
    document.body.classList.remove('dragging-any');
    unlockTouchScroll();
    stopAutoscroll();
    suppressClick = !revert && d.moved; // pointercancel produces no click to swallow
    d = null;
  }
  window.addEventListener('pointerup', () => { if (d) finishBnoteDrag(false); });
  window.addEventListener('pointercancel', () => { if (d) finishBnoteDrag(true); });

  canvas.addEventListener('click', (e) => {
    if (state.view !== 'brain') return;
    if (suppressClick) { suppressClick = false; return; }
    const node = e.target.closest('.bnote');
    if (!node || node.classList.contains('composing')) return;
    if (e.target.closest('button, input, textarea')) return;
    openNoteModal(node.dataset.id);
  });

  /* library delegation */
  $('#library').addEventListener('click', (e) => {
    const menuBtn = e.target.closest('.pane-menu-btn');
    if (menuBtn) {
      const cat = findCat(menuBtn.closest('.pane').dataset.id);
      if (cat) openPaneMenu(menuBtn, cat);
      return;
    }
    const pn = e.target.closest('.pnote');
    if (pn) openNoteModal(pn.dataset.id);
  });
  $('#library').addEventListener('dblclick', (e) => {
    const titleEl = e.target.closest('.pane-title');
    if (!titleEl) return;
    const pane = titleEl.closest('.pane');
    const cat = findCat(pane.dataset.id);
    if (cat) startPaneRename(pane, cat);
  });
})();
