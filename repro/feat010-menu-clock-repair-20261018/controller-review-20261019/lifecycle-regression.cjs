#!/usr/bin/env node
"use strict";

// Offline historical-controller characterization. Every runtime tool is mocked.
// This script never executes the guard, launches a child, opens a socket, or
// writes evidence files. Its synthetic positive cases are conditional harness
// coverage only; they do not qualify the live runtime path.

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const vm = require("node:vm");

const HERE = __dirname;
const TICKET = path.resolve(HERE, "..");
const controllerPath = path.join(HERE, "executed-controller.js.txt");
const readyPath = path.join(TICKET, "stutter-runtime-execution-ready.json");
const transcriptPath = path.join(TICKET, "stutter-runtime-gdb-transcript.json");
const resultPath = path.join(TICKET, "stutter-runtime-execution-result.json");
const statePath = path.join(TICKET, "stutter-runtime-state.json");
const guardPath = path.join(TICKET, "stutter-runtime-guard.py.txt");

const pinnedSha256 = {
  "executed-controller.js.txt": "e8214e762c2692204751e1f11b0dba304587083af6f69a8e547ddea2c2873cdc",
  "stutter-runtime-execution-ready.json": "db2a0a27ea209aec02d13f55654c8056d6c47870a2b957c56ce61b5cc70f0787",
  "stutter-runtime-gdb-transcript.json": "1617ba0bde61ca2bafe2d4603ae5d8f295c21b8efd3ef921d3f092b7560fef20",
  "stutter-runtime-execution-result.json": "ca3515047cbb1fbb943e59ee92e1ede429e198b2d08557f758d5666f703ea865",
  "stutter-runtime-state.json": "c1c5d50a07b457edb05bab248cd12e04be5ca78c1ff2fdf28c673af9b807eaaa",
  "stutter-runtime-guard.py.txt": "70460d25d0f20cb2946dbf49a8684dabd5e1653b96bfe78aedf465969d89a0f0"
};

function readUtf8(file) {
  return fs.readFileSync(file, "utf8");
}

function sha256(data) {
  return crypto.createHash("sha256").update(data).digest("hex");
}

const sourceText = readUtf8(controllerPath);
const readyText = readUtf8(readyPath);
const transcriptText = readUtf8(transcriptPath);
const recordedResultText = readUtf8(resultPath);
const stateText = readUtf8(statePath);
const guardText = readUtf8(guardPath);
const ready = JSON.parse(readyText);
const transcript = JSON.parse(transcriptText);
const recordedResult = JSON.parse(recordedResultText);
const recordedState = JSON.parse(stateText);

const sourceDigests = {
  "executed-controller.js.txt": sha256(sourceText),
  "stutter-runtime-execution-ready.json": sha256(readyText),
  "stutter-runtime-gdb-transcript.json": sha256(transcriptText),
  "stutter-runtime-execution-result.json": sha256(recordedResultText),
  "stutter-runtime-state.json": sha256(stateText),
  "stutter-runtime-guard.py.txt": sha256(guardText)
};

for (const [name, expected] of Object.entries(pinnedSha256)) {
  if (expected && sourceDigests[name] !== expected) {
    throw new Error(`${name} SHA-256 changed: ${sourceDigests[name]}`);
  }
}

const retainedStart = transcript.find(x => x.operation === "start_session").response;
const retainedConfiguration = transcript.find(x => x.commands?.[0] === "show architecture").response;
const retainedAttach = transcript.find(x => x.commands?.[0] === "target remote 127.0.0.1:65520").response;
const retainedAbort = transcript.find(x => x.operation === "abort").response;
const retainedStop = transcript.find(x => x.operation === "stop_session").response;

if (!retainedStart || !retainedConfiguration || !retainedAttach || !retainedAbort || !retainedStop) {
  throw new Error("Retained transcript is missing a required exact response fixture");
}

const sourceLine = (needle, occurrence = 1) => {
  const lines = sourceText.split(/\r?\n/);
  let count = 0;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(needle) && ++count === occurrence) return i + 1;
  }
  return null;
};

function immediate() {
  return new Promise(resolve => setImmediate(resolve));
}

function commandName(command) {
  const m = command.match(/stutter-runtime-[A-Za-z0-9-]+\.(?:json|log)/);
  return m ? m[0] : "unclassified-host-command";
}

function registerLine(regs) {
  const hex = value => Number(value || 0).toString(16).padStart(4, "0").slice(-4);
  const byte = value => Number(value || 0).toString(16).padStart(2, "0").slice(-2);
  return `pc=${hex(regs.pc)} dp=${byte(regs.dp)} x=${hex(regs.x)} y=${hex(regs.y)} u=${hex(regs.u)}\n`;
}

function batchEnvelope(commands, output = "") {
  return {
    content: [{ type: "text", text: JSON.stringify({ command: commands.join("\n"), output, error: false }) }],
    structuredContent: { result: commands.map(command => ({ command, output, error: false })) },
    isError: false
  };
}

function expectedRegisters(step) {
  const e = step.expected;
  return {
    pc: e.pc ?? 0x0350,
    dp: e.dp ?? 0x02,
    x: e.x ?? 0x0000,
    y: e.y ?? 0x0000,
    u: e.u ?? 0x0000
  };
}

function stepForArm(commands) {
  return ready.identity_phase.checkpoints.find(s => commands.includes(s.arm)) || null;
}

function ownObserved(result, env) {
  const identity = result?.identity || null;
  const trace = result?.trace || null;
  return {
    resultStored: Boolean(result),
    identityVerdict: identity?.verdict ?? null,
    identityReason: identity?.reason ?? null,
    identityLastProven: identity?.last_proven ?? null,
    traceVerdict: trace?.verdict ?? trace?.kind ?? null,
    traceReason: trace?.reason ?? null,
    traceStarted: identity?.trace_started ?? (trace?.trace_started ?? null),
    startCalls: env.calls.filter(x => x.kind === "host" && x.command.includes(" --start ")).length,
    abortCalls: env.calls.filter(x => x.kind === "host" && x.command.includes(" --abort")).length,
    handoffCalls: env.calls.filter(x => x.kind === "host" && x.command.includes(" --handoff ")).length,
    checkpointChecks: env.calls.filter(x => x.kind === "host" && x.command.includes(" --check ")).length,
    gdbStops: env.calls.filter(x => x.kind === "gdb" && x.commands.some(c => c === "continue" || c.includes("target remote"))).length,
    gdbSessionStops: env.calls.filter(x => x.kind === "stop_session").length,
    finalWrites: env.calls.filter(x => x.kind === "host" && x.command.includes("stutter-runtime-execution-result.json")).length,
    captureWrites: env.calls.filter(x => x.kind === "host" && x.command.includes("stutter-runtime-captures.json")).length,
    writeStdinCalls: env.calls.filter(x => x.kind === "write_stdin").length,
    cleanupStatusInResult: result?.cleanup ?? result?.cleanup_status ?? null,
    cleanupErrorEntries: (env.stored.runtimeTranscript || []).filter(x => x.cleanup_error).length,
    abortNonzeroResponses: (env.stored.runtimeTranscript || []).filter(x => x.operation === "abort" && x.response?.exit_code > 0).length,
    stopFalseResponses: (env.stored.runtimeTranscript || []).filter(x => x.operation === "stop_session" && JSON.stringify(x.response).includes('"stopped":false')).length,
    outputCount: env.output.length,
    childCreatedByFixture: env.childCreated,
    launchedFlagNeverObservable: env.launchReturnWasAmbiguous && env.abortCalls === 0
  };
}

async function runController(name, options = {}) {
  const startMs = 1000000;
  const clock = { now: startMs };
  const calls = [];
  const output = [];
  const stored = Object.create(null);
  const env = {
    name, clock, calls, output, stored, childCreated: false,
    launchReturnWasAmbiguous: false, abortCalls: 0, stepIndex: 0,
    helperCandidateFirst: false, helperCandidateContinue: false,
    checkIndex: 0, pending: false, settled: false, value: undefined,
    thrown: null, options, initialPhaseStartMs: startMs, tracePhaseStartMs: null
  };

  function record(kind, detail = {}) {
    calls.push({ kind, ...detail });
  }

  function hostResult(command, extra = {}) {
    const name = commandName(command);
    record("host", { command, file: name });

    if (command.includes(" --start ")) {
      const startArg = Number(command.match(/--start\s+(-?\d+)/)?.[1] || startMs);
      if (options.startRejectedExisting) return { exit_code: 2, output: "SETUP_REJECTED: one-shot attempt artifact already exists" };
      if (options.launchSessionId) {
        env.childCreated = true;
        env.launchReturnWasAmbiguous = true;
        return { session_id: "offline-host-launch-session", output: "", exit_code: null };
      }
      if (options.malformedLaunchJson) {
        env.childCreated = true;
        env.launchReturnWasAmbiguous = true;
        return { exit_code: 0, output: "{\"status\":\"STARTED\",\"pid\":" };
      }
      if (options.launchAcknowledgmentUnknown) {
        env.childCreated = true;
        env.launchReturnWasAmbiguous = true;
        return { exit_code: 0, output: JSON.stringify({ status: "UNKNOWN", pid: options.syntheticPid || 424242, start_ticks: "offline-ticks" }) };
      }
      if (options.launchMetadataMissing) {
        env.childCreated = true;
        return { exit_code: 0, output: JSON.stringify({ status: "STARTED" }) };
      }
      env.childCreated = true;
      return { exit_code: 0, output: JSON.stringify({ status: "STARTED", pid: options.syntheticPid || 424242, start_ticks: "offline-ticks", phase_start_ms: startArg }) };
    }

    if (command.includes("Owned listener not ready")) {
      const state = options.listenerState || {
        pid: options.syntheticPid || 424242,
        exe: ready.plan.launch_argv[0],
        argv: ready.plan.launch_argv,
        start_ticks: "offline-ticks"
      };
      return { exit_code: 0, output: JSON.stringify(state) };
    }

    if (command.includes(" --check ")) {
      const expected = ready.identity_phase.checkpoints.map(s => s.name);
      const cp = expected[env.checkIndex++] || "UNEXPECTED";
      if (options.checkFailAt === cp) return { exit_code: 2, output: `SETUP_REJECTED: synthetic ${cp} source-byte mismatch` };
      if (options.delayCheckAt === cp) clock.now += options.delayCheckMs;
      if (clock.now - startMs >= 52000) return { exit_code: 2, output: `SETUP_REJECTED: synthetic identity work deadline at ${cp}` };
      return { exit_code: 0, output: JSON.stringify({ verified_through: cp, identity_complete: cp === "B080" }) };
    }

    if (command.includes(" --handoff ")) {
      const epoch = Number(command.match(/--handoff\s+(-?\d+)/)?.[1] || 0);
      env.tracePhaseStartMs = epoch;
      if (options.delayBeforeHandoffMs) clock.now += options.delayBeforeHandoffMs;
      const age = clock.now - epoch;
      if (options.launchMetadataMissing) {
        return { exit_code: 2, output: "SETUP_REJECTED: synthetic handoff PID/start_ticks were missing" };
      }
      if (age < 0 || age > 1000 || clock.now - startMs >= 52000) {
        return { exit_code: 2, output: "SETUP_REJECTED: single B080 handoff validation failed" };
      }
      return { exit_code: 0, output: JSON.stringify({ status: "HANDOFF_ACCEPTED", pid: options.syntheticPid || 424242, phase_start_ms: epoch }) };
    }

    if (command.includes(" --abort")) {
      env.abortCalls++;
      if (options.abortFailure) return { exit_code: 1, output: "synthetic abort refused" };
      if (options.actualResponses) return retainedAbort;
      return { exit_code: 0, output: JSON.stringify({ status: "ABORTED", pid: options.syntheticPid || 424242 }) };
    }

    if (command.includes("OWNED_PROCESS_EXITED") || command.includes("time.time()<end")) {
      if (options.waitReturnsHostSession) return { session_id: "offline-trace-wait-session", output: "", exit_code: null };
      return { exit_code: 0, output: "OWNED_PROCESS_EXITED" };
    }

    if ((command.includes("ANALYSIS_PYTHON") || command.includes("adapt_first_window") || command.includes("runpy")) && options.traceAnalysisFailure) {
      return { exit_code: 1, output: "synthetic trace-analysis assertion failed" };
    }
    if (command.includes("ANALYSIS_PYTHON") || command.includes("adapt_first_window") || command.includes("runpy")) {
      return { exit_code: 0, output: JSON.stringify({ kind: "INCOMPLETE_COVERAGE", reason: "synthetic offline trace fixture", cpu_instructions: 1, elapsed_seconds: 0.01 }) };
    }

    if (command.includes("NO_EARLY_TRACE")) return { exit_code: 0, output: "NO_EARLY_TRACE" };

    if (command.includes("stutter-runtime-captures.json") && options.captureWriteSessionId) {
      env.launchReturnWasAmbiguous = true;
      return { session_id: "offline-host-capture-write-session", output: "", exit_code: null };
    }
    if (command.includes("stutter-runtime-captures.json") && options.captureWriteFailure) {
      return { exit_code: 1, output: "synthetic evidence write denied" };
    }
    if (command.includes("stutter-runtime-execution-result.json") && options.finalWriteFailure) {
      return { exit_code: 1, output: "synthetic final evidence disk-full" };
    }
    if (options.attemptWriteFailure && command.includes("stutter-runtime-identity-attempt.json")) {
      return { exit_code: 1, output: "synthetic attempt evidence write denied" };
    }
    return { exit_code: 0, output: "" };
  }

  const tools = {
    exec_command: async args => {
      if (options.hangHostCommand && args.cmd.includes(options.hangHostCommand)) return new Promise(() => {});
      if (args.cmd.includes(" --start ")) clock.now += 200;
      else if (args.cmd.includes(" --abort")) clock.now += options.actualResponses ? 395 : 1;
      else if (args.cmd.includes("stutter-runtime-execution-result.json")) clock.now += 1;
      else clock.now += 1;
      return hostResult(args.cmd);
    },
    write_stdin: async args => {
      record("write_stdin", { session_id: args.session_id });
      if (options.hangWriteStdin) return new Promise(() => {});
      return { exit_code: 0, output: "OWNED_PROCESS_EXITED" };
    },
    mcp__gdb_mcp__start_session: async args => {
      record("start_session", { args });
      if (options.hangStartSession) return new Promise(() => {});
      clock.now += options.actualResponses ? 939 : 1;
      return options.actualResponses ? retainedStart : { content: [{ type: "text", text: JSON.stringify({ session_id: "offline-gdb-session", binary: null }) }], isError: false };
    },
    mcp__gdb_mcp__batch_commands: async args => {
      const commands = args.commands;
      record("gdb", { commands, session_id: args.session_id, timeout: args.timeout });
      if (options.hangGdbAt && commands.some(x => x.includes(options.hangGdbAt))) return new Promise(() => {});

      if (JSON.stringify(commands) === JSON.stringify(ready.identity_phase.configuration_commands)) {
        if (options.structuredArchitectureError) {
          return { isError: false, structuredContent: { error: true, message: "RPC failed while echoing configured m6809 architecture" } };
        }
        clock.now += options.actualResponses ? 38 : 1;
        return options.actualResponses ? retainedConfiguration : batchEnvelope(commands, "The target architecture is set to \"auto\" (currently \"m6809\").\n");
      }

      if (commands[0] === ready.identity_phase.attach) {
        if (options.actualResponses) {
          clock.now += 2427;
          return retainedAttach;
        }
        const signal = options.syntheticSignal === false ? "[Stopped: in ??]" : "[Stopped: SIGINT]";
        return batchEnvelope(commands, `Remote debugging using 127.0.0.1:65520\n0x0000c002 in ?? ()\n${signal}\n${registerLine({ pc: 0xc002, dp: 0, x: 0, y: 0, u: 0 })}`);
      }

      const step = stepForArm(commands);
      if (step) {
        env.stepIndex = ready.identity_phase.checkpoints.indexOf(step);
        if (step.name === "helper_pre" && options.helperCandidate) {
          env.helperCandidateFirst = true;
          return batchEnvelope(commands, registerLine({ pc: 0x03d4, dp: 2, x: 0x0100, y: 0x06b2, u: 0xdead }));
        }
        return batchEnvelope(commands, registerLine(expectedRegisters(step)));
      }

      if (env.helperCandidateFirst && commands[0] === "continue") {
        env.helperCandidateFirst = false;
        env.helperCandidateContinue = true;
        const helper = ready.identity_phase.checkpoints.find(s => s.name === "helper_pre");
        const regs = expectedRegisters(helper);
        if (options.secondHelperCandidate) regs.x = 0x014d;
        return batchEnvelope(commands, registerLine(regs));
      }

      if (commands.some(c => c.startsWith("dump binary memory"))) return batchEnvelope(commands, "");
      if (commands[0] === "info breakpoints") return batchEnvelope(commands, options.breakpointsRemain ? "Num Type Disp Enb Address What\n1 breakpoint keep y 0x0000b080\n" : "No breakpoints or watchpoints.\n");
      if (commands.includes("detach") && options.detachFailure) return { isError: true, content: [{ type: "text", text: "synthetic detach error" }] };
      return batchEnvelope(commands, commands.includes("detach") ? "Inferior detached.\n" : "");
    },
    mcp__gdb_mcp__stop_session: async args => {
      record("stop_session", { session_id: args.session_id });
      if (options.hangStopSession) return new Promise(() => {});
      if (options.stopSessionFalse) return { content: [{ type: "text", text: JSON.stringify({ stopped: false }) }], isError: false };
      if (options.actualResponses) {
        clock.now += 212;
        return retainedStop;
      }
      return { content: [{ type: "text", text: JSON.stringify({ stopped: true }) }], isError: false };
    }
  };

  const context = vm.createContext({
    load: key => key === "runtimeReady" ? ready : undefined,
    tools,
    Date: { now: () => clock.now },
    store: (key, value) => { stored[key] = value; },
    notify: value => { output.push({ kind: "notify", value: String(value) }); },
    text: value => { output.push({ kind: "text", value: typeof value === "string" ? value : JSON.stringify(value) }); }
  }, { name: `offline-${name}` });

  const wrapped = `(async () => {\n${sourceText}\n})()`;
  const script = new vm.Script(wrapped, { filename: "executed-controller.js.txt" });
  const execution = script.runInContext(context);
  execution.then(value => { env.settled = true; env.value = value; }, error => { env.settled = true; env.thrown = String(error?.stack || error); });

  for (let i = 0; i < 24 && !env.settled; i++) await immediate();
  if (!env.settled) {
    const before = clock.now;
    const phaseStartMs = env.tracePhaseStartMs ?? startMs;
    clock.now = Math.max(clock.now, phaseStartMs + 60000);
    for (let i = 0; i < 2; i++) await immediate();
    env.pending = !env.settled;
    env.pendingAtFakePhaseElapsedMs = clock.now - phaseStartMs;
    env.pendingPhaseStartMs = phaseStartMs;
    env.clockBeforePendingBoundary = before;
  }

  return { env, observed: ownObserved(stored.runtimeRunResult, env), runtimeResult: stored.runtimeRunResult || null };
}

function sameSubset(actual, expected) {
  for (const [key, value] of Object.entries(expected)) {
    if (JSON.stringify(actual[key]) !== JSON.stringify(value)) return false;
  }
  return true;
}

async function observe(name, options, expected, why) {
  const run = await runController(name, options);
  const actual = run.observed;
  const passed = sameSubset(actual, expected);
  return {
    name, passed, expected, observed: actual, finding: why,
    pending: run.env.pending || false,
    error: run.env.thrown || null,
    runtimeResult: run.runtimeResult
  };
}

async function pendingCase(name, options, expected, why) {
  const run = await runController(name, options);
  const actual = run.observed;
  const observed = {
    pending: run.env.pending,
    pendingPhase: run.env.tracePhaseStartMs === null ? "R-I" : "R-T",
    pendingPhaseStartMs: run.env.tracePhaseStartMs ?? run.env.initialPhaseStartMs,
    pendingAtFakePhaseElapsedMs: run.env.pendingAtFakePhaseElapsedMs ?? null,
    ...actual
  };
  const passed = sameSubset(observed, expected);
  return { name, passed, expected, observed, finding: why, error: run.env.thrown || null, runtimeResult: run.runtimeResult };
}

async function main() {
  const cases = [];
  const exactActualRegisterText = JSON.stringify(retainedAttach);
  const actualStopHasUnknownSignal = !/SIGINT/.test(exactActualRegisterText) && /0x0000057c|pc=057c/.test(exactActualRegisterText);
  const alreadyRecorded = recordedResult.identity?.reason === "Connection SIGINT not observed" && recordedResult.trace?.verdict === "NOT_RUN";
  if (!actualStopHasUnknownSignal || !alreadyRecorded || recordedState.phase !== "ABORTED") {
    throw new Error("Retained actual-response fixture no longer matches the recorded R-I rejection");
  }

  cases.push(await observe("retained_actual_attach_rejection", { actualResponses: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", identityReason: "Connection SIGINT not observed",
    identityLastProven: null, traceVerdict: "NOT_RUN", startCalls: 1, abortCalls: 1,
    handoffCalls: 0, checkpointChecks: 0, gdbSessionStops: 1, finalWrites: 1
  }, "Exact retained GDB envelopes reproduce the observed prefix. The stop is rendered without a signal label, so no checkpoint read occurs; recorded live result remains setup/observer rejection, not a game assertion."));

  cases.push(await observe("synthetic_complete_sequence_conditional_only", {}, {
    resultStored: true, identityVerdict: "IDENTITY_PASS", identityLastProven: "B080",
    traceVerdict: "INCOMPLETE_COVERAGE", startCalls: 1, abortCalls: 0,
    handoffCalls: 1, checkpointChecks: 6, gdbSessionStops: 1, finalWrites: 1
  }, "Synthetic SIGINT, register, guard-admission, handoff, and trace responses exercise the whole orchestration branch. This is conditional offline characterization only and cannot establish live signal, bytes, PID, mapping, trace, or feature validity."));

  cases.push(await observe("one_ignored_helper_descriptor_within_stop_cap", { helperCandidate: true }, {
    resultStored: true, identityVerdict: "IDENTITY_PASS", identityLastProven: "B080",
    traceVerdict: "INCOMPLETE_COVERAGE", checkpointChecks: 6, handoffCalls: 1
  }, "The synthetic first helper stop is a nonmatching 03D4 descriptor and the next stop matches; the controller spends the allowed eighth target stop and advances."));

  cases.push(await observe("second_helper_descriptor_rejected", { helperCandidate: true, secondHelperCandidate: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", identityLastProven: "enemy_post",
    handoffCalls: 0, checkpointChecks: 3, abortCalls: 1
  }, "A second nonmatching 03D4 descriptor is rejected before helper_pre admission. The offline case tests the controller's one-extra-stop boundary; it does not run the Python guard."));

  cases.push(await observe("structured_architecture_error_echoing_m6809", { structuredArchitectureError: true, syntheticSignal: false }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", identityReason: "Connection SIGINT not observed",
    startCalls: 1, abortCalls: 1
  }, "A response with isError=false and structuredContent.error=true that also echoes m6809 passes the controller's text-contains architecture check and reaches guest launch. It is rejected only later at the synthetic attach gate."));

  cases.push(await observe("host_session_id_on_launch", { launchSessionId: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", startCalls: 1,
    abortCalls: 0, handoffCalls: 0, gdbSessionStops: 1
  }, "The mocked host command reports an active session after child creation. shell() throws before launchedMeta is parsed and launched becomes true, so catch skips --abort; no write_stdin observes or reaps that host session."));

  cases.push(await observe("malformed_launch_json_after_child_creation", { malformedLaunchJson: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", startCalls: 1,
    abortCalls: 0, handoffCalls: 0, gdbSessionStops: 1
  }, "A child-created fixture with truncated STARTED JSON fails at JSON.parse before launched=true and cannot reach guard --abort. The guard watchdog is a fallback, not verified immediate cleanup."));

  cases.push(await observe("guard_launch_ack_unknown_after_child_creation", { launchAcknowledgmentUnknown: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", startCalls: 1,
    childCreatedByFixture: true, launchedFlagNeverObservable: true,
    abortCalls: 0, handoffCalls: 0, gdbSessionStops: 1
  }, "A child-created fixture returns valid JSON with an unrecognized status. The controller throws before setting launched=true, so its catch skips --abort despite the fixture's child-created premise; the guard watchdog remains an unqualified fallback."));

  cases.push(await observe("started_ack_missing_process_metadata_rejected_at_handoff", { launchMetadataMissing: true }, {
    resultStored: true, identityVerdict: "IDENTITY_PASS", identityLastProven: "B080",
    traceVerdict: "SETUP_REJECTED", handoffCalls: 1, abortCalls: 1,
    checkpointChecks: 6, gdbSessionStops: 1
  }, "A STARTED status with missing PID/start_ticks is not type-checked or compared with listener state before R-I reaches IDENTITY_PASS. The synthetic guard mock rejects the later handoff; this characterizes controller flow, not a live guard response."));

  cases.push(await observe("attempt_evidence_write_failure", { attemptWriteFailure: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", startCalls: 0,
    abortCalls: 0, handoffCalls: 0, gdbSessionStops: 0, finalWrites: 1
  }, "A failed initial attempt-evidence write rejects before GDB session or guest launch. The finally block still writes fixed final evidence paths and does not validate that write's exit status."));

  cases.push(await observe("host_session_id_on_capture_write", { captureWriteSessionId: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", identityLastProven: null,
    checkpointChecks: 0, abortCalls: 1, gdbSessionStops: 1, writeStdinCalls: 0
  }, "A host session response during capture serialization is treated as command failure; the pending write session is not tracked or cancelled, while guard abort and GDB stop are attempted."));

  cases.push(await observe("capture_evidence_write_failure", { captureWriteFailure: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", checkpointChecks: 0,
    abortCalls: 1, gdbSessionStops: 1, finalWrites: 1
  }, "A failed checkpoint evidence write prevents guard admission, records the host-command error in the identity failure reason, then attempts cleanup and the final result write."));

  cases.push(await observe("handoff_rejected_after_trace_clock_age", { delayBeforeHandoffMs: 1001 }, {
    resultStored: true, identityVerdict: "IDENTITY_PASS", identityLastProven: "B080",
    traceVerdict: "SETUP_REJECTED", handoffCalls: 1, abortCalls: 1, gdbSessionStops: 1
  }, "The guard mock rejects a handoff older than the Ready 1000 ms freshness limit. The controller classifies R-T setup rejection and aborts the owned process; no trace analysis runs."));

  cases.push(await observe("identity_deadline_expires_before_handoff", { delayCheckAt: "B080", delayCheckMs: 52001 }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", identityLastProven: "helper_post",
    handoffCalls: 0, abortCalls: 1, traceVerdict: "NOT_RUN"
  }, "The guard mock rejects B080 admission at the fixed 52-second work edge. The phase does not advance and no R-T handoff is issued."));

  cases.push(await pendingCase("gdb_callback_never_returns", { hangGdbAt: "show architecture" }, {
    pending: true, pendingPhase: "R-I", pendingAtFakePhaseElapsedMs: 60000, resultStored: false,
    startCalls: 0, abortCalls: 0, handoffCalls: 0, finalWrites: 0
  }, "A never-resolving mocked GDB callback leaves the whole controller pending after the fake 60-second boundary. The controller's per-command timeout argument does not cancel this Promise, and finally does not run."));

  cases.push(await pendingCase("gdb_start_session_never_returns", { hangStartSession: true }, {
    pending: true, pendingPhase: "R-I", pendingAtFakePhaseElapsedMs: 60000, resultStored: false,
    startCalls: 0, abortCalls: 0, handoffCalls: 0, gdbSessionStops: 0, finalWrites: 0
  }, "A never-resolving start_session callback leaves the controller pending before any guest launch or final evidence write. This mock does not model the service's possible partially created but unregistered process."));

  cases.push(await pendingCase("cleanup_stop_session_never_returns", { actualResponses: true, hangStopSession: true }, {
    pending: true, pendingPhase: "R-I", pendingAtFakePhaseElapsedMs: 60000, resultStored: false,
    startCalls: 1, abortCalls: 1, handoffCalls: 0, finalWrites: 0
  }, "The exact retained attach failure reaches cleanup; an unresolved stop_session prevents catch/finally completion, so no final result/transcript is written before the fake 60-second boundary."));

  cases.push(await observe("cleanup_return_values_not_verified", { actualResponses: true, abortFailure: true, stopSessionFalse: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", abortCalls: 1,
    gdbSessionStops: 1, finalWrites: 1, cleanupStatusInResult: null,
    cleanupErrorEntries: 0, abortNonzeroResponses: 1, stopFalseResponses: 1
  }, "Nonzero abort and stopped:false are returned but ignored. The controller stores and prints SETUP_REJECTED without recording cleanup as failed or confirming process/session closure."));

  cases.push(await observe("final_evidence_write_failure_unchecked", { actualResponses: true, finalWriteFailure: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", finalWrites: 1,
    outputCount: 2
  }, "The finally block's final WriteAllText result has exit_code=1, but the controller neither checks it nor changes the stored result; it prints a result whose durable evidence write failed."));

  cases.push(await observe("detach_error_after_accepted_handoff", { detachFailure: true }, {
    resultStored: true, identityVerdict: "IDENTITY_PASS", traceVerdict: "SETUP_REJECTED",
    traceStarted: true, handoffCalls: 1, abortCalls: 1, gdbSessionStops: 1
  }, "A synthetic detach error after accepted B080 handoff is classified in R-T, followed by an abort and stop-session attempt. No second trace or retry is issued."));

  cases.push(await pendingCase("host_wait_write_stdin_never_returns", { waitReturnsHostSession: true, hangWriteStdin: true }, {
    pending: true, pendingPhase: "R-T", pendingAtFakePhaseElapsedMs: 60000, resultStored: false,
    handoffCalls: 1, writeStdinCalls: 1, abortCalls: 0, gdbSessionStops: 1, finalWrites: 0
  }, "After a conditional synthetic handoff and GDB detach, the host trace-wait returns a session_id and write_stdin never resolves. The controller remains pending at the fake 60-second boundary; this does not validate a live process wait."));

  cases.push(await observe("trace_analysis_command_failure", { traceAnalysisFailure: true }, {
    resultStored: true, identityVerdict: "IDENTITY_PASS", traceVerdict: "SETUP_REJECTED",
    traceStarted: true, handoffCalls: 1, abortCalls: 1, gdbSessionStops: 1, finalWrites: 1
  }, "A synthetic analysis command failure after handoff is recorded as R-T setup rejection, followed by owner abort and controller finalization. The mock does not execute the Python analysis or validate output artifacts."));

  cases.push(await observe("existing_one_shot_guard_rejection", { startRejectedExisting: true }, {
    resultStored: true, identityVerdict: "SETUP_REJECTED", startCalls: 1,
    abortCalls: 0, handoffCalls: 0, gdbSessionStops: 1, finalWrites: 1
  }, "The mock guard rejects a second --start. Controller does not retry, but its finally writer still targets the existing result/transcript paths; the invocation-level one-shot guard does not protect those evidence files."));

  const failures = cases.filter(x => !x.passed);
  const summary = {
    schema: "ladybug.feat010.lifecycle-characterization.v1",
    status: failures.length ? "FAIL" : "PASS",
    meaning: "PASS means the recovered source matched the offline controller-flow expectations. Synthetic register values are derived from Ready expected metadata, so deep-path passes are not an independent register or byte-admission oracle, controller correctness, runtime evidence, or acceptance.",
    ticket: "FEAT-010",
    assignment: "Ready High-risk lifecycle review; R-I/R-T remain paused after the retained R-I setup rejection.",
    executionBoundary: "All tools mocked in a Node VM. No child_process, host process, network, GDB, emulator, guard execution, build, or filesystem writes.",
    runtimeEvidence: "Only retained exact responses establish the recorded R-I prefix. Synthetic positive cases are conditional orchestration tests and do not establish live validity.",
    sourceHashes: sourceDigests,
    transcriptionProvenance: "executed-controller.js.txt is the exact original custom_tool_call.input recovered from the current-thread rollout (call_7de95861e0304b9196174e1535fd9f51, 2026-10-19T01:12:06.802Z; 9409 bytes; SHA-256 e8214e762c2692204751e1f11b0dba304587083af6f69a8e547ddea2c2873cdc). The archived file is byte-identical to that recovered input. It was not in the pre-dispatch source freeze/qualification, so this recovery does not retroactively qualify it.",
    retainedEnvelopeSources: {
      startSession: { file: "../stutter-runtime-gdb-transcript.json", entry: "operation=start_session", sessionId: "8c1206c5" },
      configuration: { file: "../stutter-runtime-gdb-transcript.json", entry: "commands[0]=show architecture" },
      attach: { file: "../stutter-runtime-gdb-transcript.json", entry: "commands[0]=target remote 127.0.0.1:65520", renderedSignal: "unknown; literal SIGINT absent" },
      abort: { file: "../stutter-runtime-gdb-transcript.json", entry: "operation=abort", result: "ABORTED, pid 1967" },
      stopSession: { file: "../stutter-runtime-gdb-transcript.json", entry: "operation=stop_session", result: "stopped:true" }
    },
    testCount: cases.length,
    failedCharacterizations: failures.length,
    cases
  };
  process.stdout.write(JSON.stringify(summary) + "\n");
  if (failures.length) process.exitCode = 1;
}

main().catch(error => {
  process.stderr.write(JSON.stringify({ schema: "ladybug.feat010.lifecycle-characterization.v1", status: "HARNESS_ERROR", error: String(error?.stack || error) }) + "\n");
  process.exitCode = 2;
});
