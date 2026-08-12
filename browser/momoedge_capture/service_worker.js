"use strict";

importScripts("projection.js", "page_capture.js");

let captureInFlight = false;

function armMomoEdgeAlarm() {
  chrome.alarms.get(MOMOEDGE_OBSERVE.alarmName, (existing) => {
    if (chrome.runtime.lastError || existing) return;
    const next = nextMomoEdgeGridMs(Date.now());
    chrome.alarms.create(MOMOEDGE_OBSERVE.alarmName, {
      when: next,
      periodInMinutes: 5,
    });
  });
}

function sendObservationToNativeHost(observation) {
  function sendOnce() {
    return new Promise((resolve) => {
      chrome.runtime.sendNativeMessage(MOMOEDGE_OBSERVE.nativeHost, observation, (response) => {
        if (chrome.runtime.lastError) {
          resolve(null);
          return;
        }
        resolve(response || null);
      });
    });
  }
  return sendOnce().then(async (first) => {
    if (isAcceptedMomoEdgeAck(first)) return first;
    await new Promise((resolve) => setTimeout(resolve, 500));
    const second = await sendOnce();
    return isAcceptedMomoEdgeAck(second) ? second : null;
  });
}

async function selectTerminalTab() {
  const tabs = await chrome.tabs.query({ url: MOMOEDGE_OBSERVE.terminalUrlPattern });
  const usable = tabs.filter((tab) => Number.isInteger(tab.id) && !tab.discarded);
  usable.sort((left, right) => left.id - right.id);
  return usable.length ? usable[0] : null;
}

async function captureSlot(alarm) {
  const scheduledMs = Math.floor(alarm.scheduledTime / MOMOEDGE_OBSERVE.cadenceMs) * MOMOEDGE_OBSERVE.cadenceMs;
  const scheduledAt = momoEdgeIso(scheduledMs);
  const attemptedAt = momoEdgeIso(Date.now());
  let pageCapture;

  if (Date.now() - scheduledMs > 120000) {
    pageCapture = unavailablePageCapture("alarm_late");
  } else if (captureInFlight) {
    pageCapture = unavailablePageCapture("capture_in_flight");
  } else {
    captureInFlight = true;
    try {
      const tab = await selectTerminalTab();
      if (!tab) {
        pageCapture = unavailablePageCapture("no_matching_tab");
      } else if (tab.status !== "complete") {
        pageCapture = unavailablePageCapture("tab_not_ready");
      } else {
        const execution = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          world: "MAIN",
          func: captureFreshMomoEdgeSignals,
        });
        pageCapture = execution && execution[0] && execution[0].result
          ? execution[0].result
          : unavailablePageCapture("page_execution_failed");
      }
    } catch (_) {
      pageCapture = unavailablePageCapture("page_execution_failed");
    } finally {
      captureInFlight = false;
    }
  }

  const completedAt = momoEdgeIso(Date.now());
  const observation = buildMomoEdgeObservation(
    scheduledAt,
    attemptedAt,
    completedAt,
    pageCapture,
  );
  await sendObservationToNativeHost(observation);
}

chrome.runtime.onInstalled.addListener(armMomoEdgeAlarm);
chrome.runtime.onStartup.addListener(armMomoEdgeAlarm);
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === MOMOEDGE_OBSERVE.alarmName) void captureSlot(alarm);
});

armMomoEdgeAlarm();
