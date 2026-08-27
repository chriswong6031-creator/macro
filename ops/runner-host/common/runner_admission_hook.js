"use strict";

// GitHub executes .js runner hooks with the runner's own absolute Node binary.
// Keep the policy in the adjacent root-owned Python file, but pass only the
// immutable GitHub facts and a profile derived from this root-owned filename.
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const profiles = {
  "mastermind-ci-admission-pc-ci.js": "pc-ci",
  "mastermind-ci-admission-pc-render.js": "pc-render",
  "runner_admission_m1_canary.js": "m1-canary",
};
const profile = profiles[path.basename(process.argv[1] || "")];
if (!profile) {
  console.error("::error title=runner-admission::unknown root-owned hook profile");
  process.exit(78);
}

const environment = {
  PATH: "/usr/bin:/bin",
  HOME: "/nonexistent",
  MASTERMIND_CI_PROFILE: profile,
};
for (const key of [
  "GITHUB_REPOSITORY",
  "GITHUB_EVENT_NAME",
  "GITHUB_REF",
  "GITHUB_WORKFLOW_REF",
  "GITHUB_JOB",
  "GITHUB_EVENT_PATH",
]) {
  environment[key] = process.env[key] || "";
}

const script = path.join(path.dirname(process.argv[1]), "runner_admission.py");
const result = spawnSync("/usr/bin/python3", ["-I", script], {
  env: environment,
  stdio: "inherit",
});
if (result.error || result.signal || !Number.isInteger(result.status)) {
  console.error("::error title=runner-admission::policy process failed closed");
  process.exit(78);
}
process.exit(result.status);
