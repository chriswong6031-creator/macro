#!/usr/bin/env python3
"""Selector contract. Never silently pick .first when cardinality is 1."""
from __future__ import annotations

RESOLVE_JS = r"""
(specs) => {
  const vis = (el) => {
    if (!el) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const txt = (el) => ((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
  const boxes = (el) => {
    const r = el.getBoundingClientRect();
    const sx = window.scrollX || 0, sy = window.scrollY || 0;
    const vb = {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
    return {
      viewport_box: vb,
      page_box: {x: Math.round(r.x + sx), y: Math.round(r.y + sy), w: vb.w, h: vb.h, scrollX: sx, scrollY: sy}
    };
  };
  const query = (strategy) => {
    if (!strategy) return {nodes: [], selector: null, error: 'no_strategy'};
    const type = strategy.type || 'css';
    const value = strategy.value || '';
    let nodes = [];
    try {
      if (type === 'css') {
        nodes = Array.from(document.querySelectorAll(value));
      } else if (type === 'css_and_text') {
        nodes = Array.from(document.querySelectorAll(value));
        const needle = (strategy.text_contains || '').toLowerCase();
        const exact = (strategy.text_exact || '').toLowerCase();
        nodes = nodes.filter((el) => {
          const t = txt(el).toLowerCase();
          if (exact) return t === exact || t.startsWith(exact);
          if (needle) return t.includes(needle);
          return true;
        });
      } else if (type === 'aria') {
        const role = strategy.role || '*';
        const name = (strategy.name || '').toLowerCase();
        const sel = role === '*' ? '[aria-label],button,a,input,[role]' : `[role="${role}"], ${role}`;
        nodes = Array.from(document.querySelectorAll(sel));
        if (name) {
          nodes = nodes.filter((el) => {
            const acc = (el.getAttribute('aria-label') || txt(el) || '').toLowerCase();
            return acc.includes(name);
          });
        }
      } else {
        return {nodes: [], selector: value, error: 'unknown_strategy'};
      }
    } catch (e) {
      return {nodes: [], selector: value, error: String(e)};
    }
    return {nodes, selector: value, error: null};
  };

  const resolveOne = (spec) => {
    const requested = spec.selector_strategy || (spec.selector ? {type: 'css', value: spec.selector} : null);
    const expected = spec.expected_cardinality == null ? 1 : spec.expected_cardinality;
    let used = requested;
    let q = query(used);
    let usedFallback = false;
    if (expected === 1 && q.nodes.length !== 1 && spec.fallback_strategy) {
      const fb = query(spec.fallback_strategy);
      if (fb.nodes.length === 1) {
        q = fb;
        used = spec.fallback_strategy;
        usedFallback = true;
      }
    }
    const matchCount = q.nodes.length;
    let status = 'RESOLVED';
    let selected = null;
    let index = null;
    if (expected === 1) {
      if (matchCount !== 1) {
        status = 'UNRESOLVED';
      } else {
        selected = q.nodes[0];
        index = 0;
      }
    } else if (matchCount === 0) {
      status = 'UNRESOLVED';
    } else {
      selected = q.nodes[0];
      index = 0;
    }
    const item = {
      stable_id: spec.stable_id || spec.id,
      human_label: spec.human_label || spec.label || null,
      evidence_section: spec.evidence_section || spec.section || null,
      required: !!spec.required,
      selector_requested: requested ? (requested.value || null) : (spec.selector || null),
      selector_used: used ? (used.value || null) : null,
      selector_strategy_used: used ? (used.type || 'css') : null,
      used_fallback: usedFallback,
      match_count: matchCount,
      selected_match_index: index,
      expected_cardinality: expected,
      visible: vis(selected),
      found: !!selected,
      resolution_status: status,
      semantic_role: spec.semantic_role || spec.role_hint || null,
      source_hint: spec.source_hint || null,
      tag: selected ? selected.tagName.toLowerCase() : null,
      href: selected ? selected.getAttribute('href') : null,
      className: selected ? selected.className : null,
      aria_expanded: selected ? selected.getAttribute('aria-expanded') : null,
      aria_pressed: selected ? selected.getAttribute('aria-pressed') : null,
      aria_selected: selected ? selected.getAttribute('aria-selected') : null,
      open: selected && 'open' in selected ? !!selected.open : null,
      visible_label: selected ? txt(selected).slice(0, 240) : null,
      query_error: q.error
    };
    if (selected) Object.assign(item, boxes(selected));
    else { item.viewport_box = null; item.page_box = null; }
    return item;
  };

  return (specs || []).map(resolveOne);
}
"""


SECTION_CHILDREN_JS = r"""
(spec) => {
  const el = spec.selector ? document.querySelector(spec.selector) : null;
  if (!el) return {major_children: [], major_controls: []};
  const kids = [];
  for (const c of Array.from(el.children).slice(0, 16)) {
    if (['SCRIPT', 'STYLE', 'LINK'].includes(c.tagName)) continue;
    kids.push({
      tag: c.tagName.toLowerCase(),
      id: c.id || null,
      cls: (c.className || '').toString().slice(0, 80),
      text: ((c.innerText || '').replace(/\s+/g, ' ').trim()).slice(0, 90)
    });
  }
  const controls = [];
  el.querySelectorAll('a, button, [role="button"], [role="tab"], summary, input, select').forEach((c, i) => {
    if (i > 24) return;
    const t = ((c.getAttribute('aria-label') || c.innerText || '').replace(/\s+/g, ' ').trim()).slice(0, 80);
    if (!t) return;
    controls.push({tag: c.tagName.toLowerCase(), id: c.id || null, text: t});
  });
  return {major_children: kids, major_controls: controls};
}
"""


def as_resolve_spec(item: dict) -> dict:
    """Normalize config or legacy catalog entries into the resolver contract."""
    strategy = item.get("selector_strategy")
    if not strategy and item.get("selector"):
        strategy = {"type": "css", "value": item["selector"]}
    return {
        "stable_id": item.get("stable_id") or item.get("id"),
        "human_label": item.get("human_label") or item.get("label"),
        "selector_strategy": strategy,
        "selector": item.get("selector"),
        "expected_cardinality": item.get("expected_cardinality", 1),
        "evidence_section": item.get("evidence_section") or item.get("section"),
        "required": item.get("required", False),
        "fallback_strategy": item.get("fallback_strategy"),
        "source_hint": item.get("source_hint"),
        "semantic_role": item.get("semantic_role") or item.get("role_hint"),
    }
