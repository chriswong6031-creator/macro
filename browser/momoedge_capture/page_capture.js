"use strict";

/*
 * This function is serialized by chrome.scripting.executeScript into the page's
 * MAIN world. It is deliberately self-contained: it calls the page's existing
 * authenticated runtime, but never reads browser authentication state, request
 * metadata, or storage. The only intercepted data is the matched signals
 * response body and status.
 */
async function captureFreshMomoEdgeSignals() {
  "use strict";

  const MAX_RESPONSE_BYTES = 600000;
  const SIGNALS_ORIGIN = "https://pojiqfeemksvocnaellu.supabase.co";
  const SIGNALS_PATH = "/rest/v1/signals";
  const REQUEST_CONTRACT = "signals_active_plus_source_today_closed_fresh_fetch/v1";
  const RESPONSE_SCHEMA = "momoedge_signals_json_array/v1";

  if (
    window.location.origin !== "https://momoedge.ai" ||
    !["/terminal", "/terminal.html"].includes(window.location.pathname)
  ) {
    return {
      schema: "options.momoedge_browser_page_capture/v1",
      disposition: "unavailable",
      reason: "page_origin_path_mismatch",
      capture: null,
    };
  }

  function pageClock() {
    const epochMs = performance.timeOrigin + performance.now();
    return {
      utc: new Date(epochMs).toISOString(),
      epoch_ms: Number(epochMs.toFixed(3)),
    };
  }

  function unavailable(reason) {
    return {
      schema: "options.momoedge_browser_page_capture/v1",
      disposition: "unavailable",
      reason: reason,
      capture: null,
    };
  }

  function normalizeKey(key) {
    return String(key).toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  function containsSensitiveKey(value) {
    const markers = [
      "auth",
      "bearer",
      "cookie",
      "csrf",
      "xsrf",
      "setcookie",
      "accesstoken",
      "refreshtoken",
      "idtoken",
      "password",
      "passwd",
      "secret",
      "apikey",
      "credential",
      "credentials",
      "session",
      "sessionid",
      "clientsecret",
      "privatekey",
      "jwt",
      "localstorage",
      "sessionstorage",
      "token",
    ];
    const stack = [value];
    while (stack.length) {
      const current = stack.pop();
      if (Array.isArray(current)) {
        for (const item of current) stack.push(item);
        continue;
      }
      if (!current || typeof current !== "object") continue;
      for (const [key, child] of Object.entries(current)) {
        const normalized = normalizeKey(key);
        if (
          markers.some((marker) => normalized.includes(marker))
        ) {
          return true;
        }
        stack.push(child);
      }
    }
    return false;
  }

  function jsonValueIsBounded(value) {
    const stack = [{ value: value, depth: 0 }];
    let nodes = 0;
    while (stack.length) {
      const current = stack.pop();
      nodes += 1;
      if (nodes > 50000 || current.depth > 32) return false;
      if (typeof current.value === "number" && !Number.isFinite(current.value)) return false;
      if (typeof current.value === "string" && current.value.length > 100000) return false;
      if (Array.isArray(current.value)) {
        for (const child of current.value) stack.push({ value: child, depth: current.depth + 1 });
      } else if (current.value && typeof current.value === "object") {
        for (const [key, child] of Object.entries(current.value)) {
          if (String(key).length > 128) return false;
          stack.push({ value: child, depth: current.depth + 1 });
        }
      }
    }
    return true;
  }

  function stableSourceId(value) {
    if (typeof value === "string") {
      return (
        value.length > 0 &&
        value.length <= 256 &&
        value.trim().length > 0 &&
        !/[\u0000-\u001f\u007f]/.test(value)
      ) ? value : null;
    }
    return Number.isSafeInteger(value) ? String(value) : null;
  }

  function requestUrl(input) {
    if (typeof input === "string") return input;
    if (input instanceof URL) return input.href;
    if (input && typeof input.url === "string") return input.url;
    return "";
  }

  function requestMethod(input, init) {
    if (init && typeof init.method === "string") return init.method.toUpperCase();
    if (input && typeof input.method === "string") return input.method.toUpperCase();
    return "GET";
  }

  function zonedParts(epochMs, timeZone) {
    const formatter = new Intl.DateTimeFormat("en-US-u-hc-h23", {
      timeZone: timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
    const values = {};
    for (const part of formatter.formatToParts(new Date(epochMs))) {
      if (part.type !== "literal") values[part.type] = Number(part.value);
    }
    return values;
  }

  function sourceClosedCutoffAt(nowMs) {
    const current = zonedParts(nowMs, "America/New_York");
    const pad = (value) => String(value).padStart(2, "0");
    // Freeze the current page's lexical cutoff exactly. The source uses a
    // month heuristic, not the real DST transition calendar; this observer
    // records that limitation and never promotes it to complete-NY-day proof.
    const offset = current.month >= 3 && current.month <= 11 ? "-04:00" : "-05:00";
    return `${current.year}-${pad(current.month)}-${pad(current.day)}T00:00:00${offset}`;
  }

  function matchSignalsRequest(input, init) {
    if (requestMethod(input, init) !== "GET") return null;
    let parsed;
    try {
      parsed = new URL(requestUrl(input), window.location.href);
    } catch (_) {
      return null;
    }
    if (parsed.origin !== SIGNALS_ORIGIN || parsed.pathname !== SIGNALS_PATH) return null;
    const parameterNames = Array.from(parsed.searchParams.keys()).sort();
    if (parameterNames.length !== 2 || parameterNames[0] !== "or" || parameterNames[1] !== "order") {
      return null;
    }
    const scope = parsed.searchParams.get("or") || "";
    const order = parsed.searchParams.get("order") || "";
    const cutoffMatch = scope.match(
      /^\(is_active\.eq\.true,and\(is_active\.eq\.false,closed_at\.gte\.([^)]+)\)\)$/,
    );
    if (!cutoffMatch) return null;
    if (order !== "sort_order.asc") return null;
    if (cutoffMatch[1] !== sourceClosedCutoffAt(Date.now())) return null;
    return { source_closed_cutoff_at: cutoffMatch[1] };
  }

  async function readBoundedBody(response) {
    const clone = response.clone();
    if (!clone.body || typeof clone.body.getReader !== "function") {
      return { too_large: true, bytes: null };
    }
    const reader = clone.body.getReader();
    const chunks = [];
    let size = 0;
    while (true) {
      const next = await reader.read();
      if (next.done) break;
      size += next.value.byteLength;
      if (size > MAX_RESPONSE_BYTES) {
        void reader.cancel().catch(() => {});
        return { too_large: true, bytes: null };
      }
      chunks.push(next.value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    return { too_large: false, bytes: bytes };
  }

  function bytesToBase64(bytes) {
    let binary = "";
    const chunkSize = 0x8000;
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      binary += String.fromCharCode.apply(null, bytes.subarray(offset, offset + chunkSize));
    }
    return btoa(binary);
  }

  async function sha256Hex(bytes) {
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    return Array.from(digest, (value) => value.toString(16).padStart(2, "0")).join("");
  }

  function validTimestamp(value) {
    return (
      typeof value === "string" &&
      /(?:Z|[+-]\d\d:\d\d)$/.test(value) &&
      !Number.isNaN(Date.parse(value))
    );
  }

  function validateRows(rows, closedCutoff) {
    if (!Array.isArray(rows)) return { ok: false };
    const cutoffMs = Date.parse(closedCutoff);
    let activeCount = 0;
    let closedCount = 0;
    const ids = [];
    const uniqueIds = new Set();
    for (const row of rows) {
      if (!row || typeof row !== "object" || Array.isArray(row)) return { ok: false };
      const id = stableSourceId(row.id);
      if (id === null) return { ok: false };
      if (typeof row.is_active !== "boolean") return { ok: false };
      if (!validTimestamp(row.created_at)) return { ok: false };
      if (row.is_active) {
        activeCount += 1;
      } else {
        if (!validTimestamp(row.closed_at) || Date.parse(row.closed_at) < cutoffMs) return { ok: false };
        closedCount += 1;
      }
      if (uniqueIds.has(id)) return { ok: false };
      uniqueIds.add(id);
      ids.push(id);
    }
    ids.sort();
    return { ok: true, activeCount, closedCount, ids };
  }

  const runtime = window.MomoEdge && window.MomoEdge.signals;
  if (!runtime || typeof runtime.loadSignals !== "function") {
    return unavailable("page_runtime_missing");
  }
  if (typeof window.fetch !== "function") return unavailable("page_fetch_missing");

  const originalFetch = window.fetch;
  const matched = [];
  let wrapperRestored = false;

  async function wrappedFetch(input, init) {
    const requestScope = matchSignalsRequest(input, init);
    if (!requestScope) return originalFetch.call(this, input, init);
    const requestStarted = pageClock();
    let noStoreInit;
    if (init === undefined || init === null) {
      noStoreInit = { cache: "no-store" };
    } else if (typeof init === "object" || typeof init === "function") {
      // Preserve RequestInit opaquely. In particular, do not enumerate or read
      // headers, credentials, or any page-owned getter while forcing a network
      // revalidation policy for this exact fetch invocation.
      noStoreInit = Object.create(init);
      Object.defineProperty(noStoreInit, "cache", {
        value: "no-store",
        enumerable: true,
        configurable: false,
        writable: false,
      });
    } else {
      return originalFetch.call(this, input, init);
    }
    const response = await originalFetch.call(this, input, noStoreInit);
    const bounded = await readBoundedBody(response);
    const responseCompleted = pageClock();
    matched.push({
      request_scope: requestScope,
      request_started: requestStarted,
      response_completed: responseCompleted,
      status: response.status,
      bytes: bounded.bytes,
      too_large: bounded.too_large,
    });
    return response;
  }

  window.fetch = wrappedFetch;
  try {
    let timeoutId;
    await Promise.race([
      Promise.resolve(runtime.loadSignals()),
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => reject(new Error("capture_timeout")), 30000);
      }),
    ]).finally(() => clearTimeout(timeoutId));
  } catch (error) {
    if (window.fetch === wrappedFetch) {
      window.fetch = originalFetch;
      wrapperRestored = true;
    }
    return unavailable(error && error.message === "capture_timeout" ? "capture_timeout" : "page_load_failed");
  } finally {
    if (window.fetch === wrappedFetch) {
      window.fetch = originalFetch;
      wrapperRestored = true;
    }
  }

  if (!wrapperRestored || window.fetch !== originalFetch) return unavailable("fetch_wrapper_restore_failed");
  if (matched.length === 0) return unavailable("fresh_request_not_observed");
  if (matched.length !== 1) return unavailable("multiple_matching_responses");

  const observed = matched[0];
  if (observed.status < 200 || observed.status >= 300) return unavailable("http_error");
  if (observed.too_large || !observed.bytes) return unavailable("response_too_large");

  let rows;
  try {
    rows = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(observed.bytes));
  } catch (_) {
    return unavailable("invalid_response_json");
  }
  if (!jsonValueIsBounded(rows)) return unavailable("invalid_response_shape");
  if (containsSensitiveKey(rows)) return unavailable("sensitive_key_rejected");

  const validated = validateRows(rows, observed.request_scope.source_closed_cutoff_at);
  if (!validated.ok) return unavailable("invalid_response_shape");

  const runtimeRows = Array.isArray(runtime.SIGNALS)
    ? runtime.SIGNALS
    : (Array.isArray(window.SIGNALS) ? window.SIGNALS : null);
  if (!runtimeRows || runtimeRows.some((row) => row && row._isFallback === true)) {
    return unavailable("runtime_fallback_or_missing");
  }
  const runtimeIds = runtimeRows
    .map((row) => row && row.id)
    .filter((id) => id !== null && id !== undefined)
    .map(String)
    .sort();
  if (
    runtimeIds.length !== validated.ids.length ||
    runtimeIds.some((id, index) => id !== validated.ids[index])
  ) {
    return unavailable("runtime_response_mismatch");
  }

  return {
    schema: "options.momoedge_browser_page_capture/v1",
    disposition: "fresh_response",
    reason: null,
    capture: {
      request_contract: REQUEST_CONTRACT,
      response_schema: RESPONSE_SCHEMA,
      source_closed_cutoff_at: observed.request_scope.source_closed_cutoff_at,
      request_started_at: observed.request_started,
      response_completed_at: observed.response_completed,
      http_status: observed.status,
      response_body_base64: bytesToBase64(observed.bytes),
      response_byte_count: observed.bytes.length,
      response_sha256: await sha256Hex(observed.bytes),
      row_count: rows.length,
      active_count: validated.activeCount,
      closed_count: validated.closedCount,
      proof: {
        fresh_request_observed: true,
        active_and_source_today_closed_scope: true,
        complete_new_york_day_proven: false,
        runtime_response_reconciled: true,
        sensitive_keys_absent: true,
        fetch_wrapper_restored: true,
      },
    },
  };
}
