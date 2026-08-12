"use strict";

const MOMOEDGE_OBSERVE = Object.freeze({
  extensionVersion: "0.1.0",
  observationSchema: "options.momoedge_browser_observation/v1",
  nativeHost: "com.mastermind.optionsnbbocohort.momoedge_observe",
  alarmName: "momoedge-observe-300s",
  terminalUrlPattern: "https://momoedge.ai/terminal*",
  cadenceMs: 300000,
  authority: Object.freeze({
    may_count_coverage: false,
    may_enroll: false,
    may_score: false,
    may_rank: false,
    may_size: false,
    may_gate: false,
  }),
});

function nextMomoEdgeGridMs(nowMs) {
  return Math.floor(nowMs / MOMOEDGE_OBSERVE.cadenceMs) * MOMOEDGE_OBSERVE.cadenceMs + MOMOEDGE_OBSERVE.cadenceMs;
}

function momoEdgeIso(epochMs) {
  return new Date(epochMs).toISOString();
}

function unavailablePageCapture(reason) {
  return {
    schema: "options.momoedge_browser_page_capture/v1",
    disposition: "unavailable",
    reason: reason,
    capture: null,
  };
}

function buildMomoEdgeObservation(scheduledAt, attemptedAt, completedAt, pageCapture) {
  return {
    schema: MOMOEDGE_OBSERVE.observationSchema,
    mode: "observe_only",
    extension_version: MOMOEDGE_OBSERVE.extensionVersion,
    scheduled_at: scheduledAt,
    attempted_at: attemptedAt,
    completed_at: completedAt,
    disposition: pageCapture.disposition,
    reason: pageCapture.reason,
    capture: pageCapture.capture,
    coverage_eligible: false,
    authority: { ...MOMOEDGE_OBSERVE.authority },
  };
}

function isAcceptedMomoEdgeAck(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const expected = [
    "accepted",
    "coverage_eligible",
    "created",
    "disposition",
    "journal_sha256",
    "raw_sha256",
    "reason",
    "schema",
  ];
  const actual = Object.keys(value).sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) return false;
  const digest = (candidate) => typeof candidate === "string" && /^[a-f0-9]{64}$/.test(candidate);
  const common = (
    value.schema === "options.momoedge_browser_native_ack/v1" &&
    value.accepted === true &&
    typeof value.created === "boolean" &&
    ["fresh_response", "unavailable"].includes(value.disposition) &&
    digest(value.journal_sha256) &&
    value.coverage_eligible === false
  );
  if (!common) return false;
  if (value.disposition === "fresh_response") {
    return value.reason === null && digest(value.raw_sha256);
  }
  return typeof value.reason === "string" && value.reason.length > 0 && value.raw_sha256 === null;
}
