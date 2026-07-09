/* Slate — core: utilities, state model, persistence (localStorage + IndexedDB) */
'use strict';

/* ---------- tiny DOM helpers (no innerHTML with user data, ever) ---------- */
const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}
function svgIcon(pathD, size, strokeW) {
  const ns = 'http://www.w3.org/2000/svg';
  const s = document.createElementNS(ns, 'svg');
  s.setAttribute('viewBox', '0 0 16 16');
  s.setAttribute('width', size || 14);
  s.setAttribute('height', size || 14);
  const p = document.createElementNS(ns, 'path');
  p.setAttribute('d', pathD);
  p.setAttribute('fill', 'none');
  p.setAttribute('stroke', 'currentColor');
  p.setAttribute('stroke-width', strokeW || 1.5);
  p.setAttribute('stroke-linecap', 'round');
  p.setAttribute('stroke-linejoin', 'round');
  s.appendChild(p);
  return s;
}
const ICONS = {
  plus: 'M8 3v10M3 8h10',
  dots: 'M3.2 8h.01M8 8h.01M12.8 8h.01',
  check: 'M3.5 8.5l3 3 6-7',
  x: 'M4 4l8 8M12 4l-8 8',
  clock: 'M8 4.5V8l2.3 1.6M14 8A6 6 0 1 1 2 8a6 6 0 0 1 12 0z',
  text: 'M3 5h10M3 8h10M3 11h6',
  tag: 'M2.5 7.5l6-5.4 5 .4.4 5-6 5.4a1.2 1.2 0 0 1-1.7 0l-3.7-3.7a1.2 1.2 0 0 1 0-1.7zM10.5 5.5h.01',
  file: 'M4 1.8h5L12.2 5v9.2H4zM9 1.8V5h3.2',
  restore: 'M2.8 6.5A5.5 5.5 0 1 1 2.5 9M2.8 6.5V3M2.8 6.5H6.3',
  trash: 'M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5',
  download: 'M8 2.5v8M4.8 7.3L8 10.5l3.2-3.2M3 13h10',
  upload: 'M8 10.5v-8M4.8 5.7L8 2.5l3.2 3.2M3 13h10',
  pencil: 'M9.8 2.8l3.4 3.4-7.6 7.6-3.9.5.5-3.9zM8.6 4l3.4 3.4',
};

function debounce(fn, ms) {
  let t;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  d.flush = (...a) => { clearTimeout(t); fn(...a); };
  return d;
}
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : 'id-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function fmtDate(iso) { // '2026-06-20' -> 'Jun 20' (adds year if not current)
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  const opts = { month: 'short', day: 'numeric' };
  if (y !== new Date().getFullYear()) opts.year = 'numeric';
  return dt.toLocaleDateString(undefined, opts);
}
function todayISO() {
  const n = new Date();
  return n.getFullYear() + '-' + String(n.getMonth() + 1).padStart(2, '0') + '-' + String(n.getDate()).padStart(2, '0');
}
function dueStatus(iso) { // 'overdue' | 'today' | 'later'
  if (!iso) return '';
  const t = todayISO();
  return iso < t ? 'overdue' : iso === t ? 'today' : 'later';
}
function fmtSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(0) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

/* ---------- color system ---------- */
const CARD_COLORS = ['c1', 'c2', 'c3', 'c4', 'c5', 'c6', 'c7', 'c8'];
const COLOR_NAMES = { c1: 'Rose', c2: 'Ember', c3: 'Amber', c4: 'Moss', c5: 'Sea', c6: 'Sky', c7: 'Iris', c8: 'Plum' };
function tagColor(name) { // deterministic tag color from name
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return CARD_COLORS[h % CARD_COLORS.length];
}

/* ---------- state ---------- */
const LS_KEY = 'slate.state.v1';
let state = null;
let zCounter = 10;

function newCard(title) {
  return { id: uid(), t: title, d: '', color: null, tags: [], due: null, at: [], created: Date.now(), completed: null };
}
function newBoard(name, x, y) {
  return { id: uid(), name: name, x: Math.round(x), y: Math.round(y), cards: [], done: [], showDone: false };
}
function newWorkspace(name) {
  return { id: uid(), name: name, scroll: { x: 0, y: 0 }, boards: [] };
}
function newCategory(name) {
  return { id: uid(), name: name, notes: [] };
}
function newNote(text) {
  return { id: uid(), text: text, created: Date.now() };
}

/* additive defaults for states saved before a feature existed, plus shape
   normalization — this is the single choke point for loadState AND import,
   so a malformed payload can never reach a renderer */
function migrateState(s) {
  if (!s.view) s.view = 'tasks';
  if (!s.brain || !Array.isArray(s.brain.categories)) {
    s.brain = { categories: [] };
  }
  s.brain.categories = s.brain.categories
    .filter(c => c && typeof c === 'object' && !Array.isArray(c))
    .map(c => ({
      id: typeof c.id === 'string' ? c.id : uid(),
      name: (typeof c.name === 'string' && c.name.trim()) ? c.name : 'Untitled',
      notes: (Array.isArray(c.notes) ? c.notes : [])
        .filter(n => n && typeof n === 'object' && typeof n.text === 'string')
        .map(n => ({
          id: typeof n.id === 'string' ? n.id : uid(),
          text: n.text,
          created: typeof n.created === 'number' ? n.created : Date.now(),
        })),
    }));
  return s;
}

function seedState() {
  const ws = newWorkspace('Personal');
  const b1 = newBoard('Today', 60, 40);
  b1.cards = [newCard('Click me to add details, colors and tags'), newCard('Drag me onto another board'), newCard('Click my circle when I’m done')];
  b1.cards[0].d = 'Cards can hold a description, a due date, tags, a color, and any files you drop on them.';
  b1.cards[0].color = 'c6';
  const b2 = newBoard('This week', 420, 40);
  const c1 = newCard('Plan the week');
  c1.tags = ['planning'];
  c1.due = todayISO();
  const c2 = newCard('Drop an image or file onto any card');
  c2.color = 'c4';
  b2.cards = [c1, c2];
  const b3 = newBoard('Ideas', 780, 40);
  b3.cards = [newCard('Double-click the background to make a new board'), newCard('Drag boards anywhere — press Tidy to snap them into a grid')];
  ws.boards = [b1, b2, b3];
  const cat = newCategory('How this works');
  const seedNote = newNote('Double-click the Brain board to write down something you’ve learned, file it under a topic, and it’s saved here instantly. The board itself clears every time you leave — a fresh page for fresh thoughts.');
  cat.notes = [seedNote];
  return {
    v: 1,
    theme: (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light',
    view: 'tasks',
    activeWs: ws.id,
    ws: [ws],
    brain: { categories: [cat] },
    _files: null, // inline attachment fallback when IndexedDB is unavailable
  };
}

let recoveryKey = null; // set when unreadable saved data was stashed instead of clobbered
function loadState() {
  let raw = null;
  try {
    raw = localStorage.getItem(LS_KEY);
    if (raw) {
      const s = JSON.parse(raw);
      if (s && s.v === 1 && Array.isArray(s.ws) && s.ws.length) return migrateState(s);
    }
  } catch (e) { console.warn('Slate: could not load saved state', e); }
  if (raw) {
    // never clobber unreadable data: keep it under a recovery key before reseeding
    try {
      localStorage.setItem(LS_KEY + '.recovery', raw);
      recoveryKey = LS_KEY + '.recovery';
    } catch (e) { console.error('Slate: could not stash unreadable state', e); }
  }
  return seedState();
}

const save = debounce(saveNow, 150);
function saveNow() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(state));
  } catch (e) {
    console.error('Slate: save failed', e);
    if (typeof toast === 'function') toast('Storage is full — remove some attachments or export a backup', { tone: 'danger' });
  }
}
window.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') save.flush(); });
window.addEventListener('pagehide', () => save.flush());

/* ---------- state accessors ---------- */
function activeWs() { return state.ws.find(w => w.id === state.activeWs) || state.ws[0]; }
function findBoard(boardId) { return activeWs().boards.find(b => b.id === boardId); }
function findCard(cardId) {
  for (const b of activeWs().boards) {
    let i = b.cards.findIndex(c => c.id === cardId);
    if (i >= 0) return { board: b, card: b.cards[i], index: i, done: false };
    i = b.done.findIndex(c => c.id === cardId);
    if (i >= 0) return { board: b, card: b.done[i], index: i, done: true };
  }
  return null;
}

/* ---------- IndexedDB attachment store (dataURL strings keyed by id) ---------- */
let idb = null;
let idbReady = null;
function openIDB() {
  if (idbReady) return idbReady;
  idbReady = new Promise((resolve) => {
    try {
      const req = indexedDB.open('slate-db', 1);
      req.onupgradeneeded = () => { req.result.createObjectStore('files'); };
      req.onsuccess = () => { idb = req.result; resolve(true); };
      req.onerror = () => { console.warn('Slate: IndexedDB unavailable, falling back to inline storage'); resolve(false); };
    } catch (e) { resolve(false); }
  });
  return idbReady;
}
async function filePut(id, dataUrl) {
  if (await openIDB()) {
    return new Promise((resolve, reject) => {
      const tx = idb.transaction('files', 'readwrite');
      tx.objectStore('files').put(dataUrl, id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }
  if (!state._files) state._files = {};
  state._files[id] = dataUrl;
  save();
}
async function fileGet(id) {
  if (await openIDB()) {
    return new Promise((resolve) => {
      const tx = idb.transaction('files', 'readonly');
      const rq = tx.objectStore('files').get(id);
      rq.onsuccess = () => resolve(rq.result || (state._files && state._files[id]) || null);
      rq.onerror = () => resolve((state._files && state._files[id]) || null);
    });
  }
  return (state._files && state._files[id]) || null;
}
async function fileDel(id) {
  if (await openIDB()) {
    const tx = idb.transaction('files', 'readwrite');
    tx.objectStore('files').delete(id);
  }
  if (state._files) { delete state._files[id]; save(); }
}
async function fileAll() {
  const out = {};
  if (await openIDB()) {
    await new Promise((resolve) => {
      const tx = idb.transaction('files', 'readonly');
      const rq = tx.objectStore('files').openCursor();
      rq.onsuccess = () => {
        const cur = rq.result;
        if (cur) { out[cur.key] = cur.value; cur.continue(); } else resolve();
      };
      rq.onerror = () => resolve();
    });
  }
  if (state._files) Object.assign(out, state._files);
  return out;
}

/* ---------- attachment helpers ---------- */
function dataUrlToBlob(dataUrl, forceType) {
  const [head, body] = dataUrl.split(',');
  const mime = (head.match(/data:([^;]+)/) || [])[1] || 'application/octet-stream';
  const bin = atob(body);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type: forceType || mime });
}
function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}
function makeThumb(dataUrl, maxPx) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, (maxPx || 160) / Math.max(img.width, img.height));
      const w = Math.max(1, Math.round(img.width * scale));
      const h = Math.max(1, Math.round(img.height * scale));
      const cv = document.createElement('canvas');
      cv.width = w; cv.height = h;
      cv.getContext('2d').drawImage(img, 0, 0, w, h);
      try { resolve(cv.toDataURL('image/jpeg', 0.82)); } catch (e) { resolve(null); }
    };
    img.onerror = () => resolve(null);
    img.src = dataUrl;
  });
}
const MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024;

async function addAttachmentsToCard(card, fileList) {
  const files = Array.from(fileList || []);
  let added = 0;
  for (const f of files) {
    if (f.size > MAX_ATTACHMENT_BYTES) {
      toast('"' + f.name + '" is over 20 MB — skipped', { tone: 'danger' });
      continue;
    }
    try {
      const dataUrl = await readFileAsDataURL(f);
      const att = { id: uid(), name: f.name, mime: f.type || 'application/octet-stream', size: f.size, thumb: null };
      if (/^image\//.test(att.mime)) att.thumb = await makeThumb(dataUrl, 160);
      await filePut(att.id, dataUrl);
      card.at.push(att);
      added++;
    } catch (e) {
      console.error('Slate: attach failed', e);
      toast('Could not attach "' + f.name + '"', { tone: 'danger' });
    }
  }
  if (added) save();
  return added;
}
/* garbage-collect attachment blobs no longer referenced by any card (runs once at startup) */
async function gcAttachments() {
  try {
    const referenced = new Set();
    for (const w of state.ws)
      for (const b of w.boards)
        for (const c of b.cards.concat(b.done))
          for (const a of c.at) referenced.add(a.id);
    const stored = await fileAll();
    for (const id of Object.keys(stored)) {
      if (!referenced.has(id)) await fileDel(id);
    }
  } catch (e) { /* best-effort */ }
}

async function openAttachment(att) {
  const dataUrl = await fileGet(att.id);
  if (!dataUrl) { toast('File data is missing', { tone: 'danger' }); return; }
  if (/^image\//.test(att.mime)) { openLightbox(att, dataUrl); return; }
  // only inert types render in a tab (blob type forced from the whitelisted mime so a
  // spoofed dataURL header cannot smuggle text/html); everything else downloads
  const inert = att.mime === 'application/pdf' || att.mime === 'text/plain';
  let url;
  try {
    url = URL.createObjectURL(dataUrlToBlob(dataUrl, inert ? att.mime : 'application/octet-stream'));
  } catch (e) {
    toast('File data is corrupt', { tone: 'danger' });
    return;
  }
  if (inert) {
    window.open(url, '_blank', 'noopener');
  } else {
    const a = document.createElement('a');
    a.href = url; a.download = att.name;
    document.body.appendChild(a); a.click(); a.remove();
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
