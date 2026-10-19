'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const Module = require('node:module');

const ROOT = __dirname;
const CASE_ROOT = path.resolve(ROOT, '..');
const CASE_MANIFEST_PATH = path.join(ROOT, 'review-source-freeze.json');
const CARD_PATH = path.join(ROOT, 'controller-v2-card.json');
const READY_PATH = path.join(CASE_ROOT, 'stutter-runtime-execution-ready.json');
const TRANSCRIPT_PATH = path.join(CASE_ROOT, 'stutter-runtime-gdb-transcript.json');
const FIXTURE_PATH = path.join(ROOT, 'response-fixtures-v2.json');
const MODULE_PATH = path.join(ROOT, 'controller-v2.js.txt');
const RETAINED_TRANSCRIPT_SHA256 = '1617ba0bde61ca2bafe2d4603ae5d8f295c21b8efd3ef921d3f092b7560fef20';
const READY_SHA256 = 'db2a0a27ea209aec02d13f55654c8056d6c47870a2b957c56ce61b5cc70f0787';
const EXPECTED_READS = 23;
const EXPECTED_READ_BYTES = 27724;
const OWNED_SOURCES = [
  'analysis-v2.py.txt', 'controller-v2.js.txt', 'lifecycle-regression-v2.cjs',
  'response-fixtures-v2.json', 'response-regression-v2.cjs', 'run-controller-v2-offline.ps1'
];
const EXPECTED_CASES = [
  'retained_attach_signal_unknown_rejected_before_reads',
  'valid_conditional_sequence_measured_reads_and_handoff',
  'structured_error_prevents_launch',
  'ambiguous_launch_host_session_tracked',
  'malformed_launch_after_child_unknown_cleanup',
  'wrong_owner_rejected',
  'missing_final_identity_rejected',
  'wrong_handoff_ack_rejected',
  'stale_handoff_rejected',
  'checkpoint_wrong_stop_reason_rejected',
  'stalled_session_creation_marks_unresolved',
  'stalled_batch_deadline',
  'stalled_cleanup_retains_ownership',
  'cleanup_false_ack_retains_ownership',
  'final_write_failure_visible',
  'duplicate_attempt_preserves_original',
  'missing_trace_coverage_not_product_failure',
  'one_ignored_helper_descriptor_within_eight_stops',
  'second_helper_descriptor_rejected'
];

function sha256(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function insist(condition, message) { if (!condition) throw new Error(message); }
function readJson(file) { return JSON.parse(fs.readFileSync(file, 'utf8')); }
function makeEnvelope(results) {
  return {
    isError: false,
    content: results.map((result) => ({ type: 'text', text: JSON.stringify(result) })),
    structuredContent: { result: clone(results) }
  };
}
function registerLine(values) {
  return `pc=${values.pc.toString(16).padStart(4, '0')} dp=${values.dp.toString(16).padStart(2, '0')} x=${values.x.toString(16).padStart(4, '0')} y=${values.y.toString(16).padStart(4, '0')} u=${values.u.toString(16).padStart(4, '0')}\n`;
}
function processIdentity(ready) {
  return { pid: 7301, exe: ready.plan.launch_argv[0], start_ticks: '73010001', argv: ready.plan.launch_argv.slice() };
}
function mapsEqual(left, right) {
  if (!left || !right) return false;
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return JSON.stringify(leftKeys) === JSON.stringify(rightKeys) && leftKeys.every((key) => left[key] === right[key]);
}
function stoppedAck(transcript, stopped) {
  const retained = transcript.find((entry) => entry.operation === 'stop_session')?.response;
  insist(retained && Array.isArray(retained.content) && retained.content[0]?.type === 'text', 'retained stop-session response is absent');
  const response = clone(retained);
  const body = JSON.parse(response.content[0].text);
  body.stopped = stopped;
  response.content[0].text = JSON.stringify(body, null, 2);
  return response;
}

function loadController() {
  const source = fs.readFileSync(MODULE_PATH, 'utf8');
  const inert = new Module(MODULE_PATH, module);
  inert.filename = MODULE_PATH;
  inert.paths = Module._nodeModulePaths(ROOT);
  inert._compile(source, MODULE_PATH);
  return inert.exports;
}

function verifyFreeze(card, ready, manifest, attemptDir) {
  insist(card.execution_freeze && card.execution_freeze.files_sha256, 'parent execution_freeze.files_sha256 is absent');
  const expected = card.execution_freeze.files_sha256;
  const names = Object.keys(expected).sort();
  insist(JSON.stringify(names) === JSON.stringify(OWNED_SOURCES), 'execution_freeze.files_sha256 must contain exactly the six owned sources');
  const actual = {};
  for (const name of OWNED_SOURCES) actual[name] = sha256(fs.readFileSync(path.join(ROOT, name)));
  for (const name of OWNED_SOURCES) insist(actual[name].toLowerCase() === expected[name].toLowerCase(), `frozen source mismatch: ${name}`);
  insist(manifest.retained_sha256['stutter-runtime-execution-ready.json'] === READY_SHA256, 'pinned Ready source hash differs from the independent literal');
  insist(sha256(fs.readFileSync(READY_PATH)) === READY_SHA256, 'Ready assignment hash mismatch');
  insist(sha256(fs.readFileSync(TRANSCRIPT_PATH)) === RETAINED_TRANSCRIPT_SHA256, 'retained response transcript hash mismatch');
  const responseRunPath = path.join(attemptDir, 'response.run.json');
  const responseRun = readJson(responseRunPath);
  insist(responseRun.phase === 'response' && responseRun.status === 'PASS', 'matching successful frozen response phase is required');
  insist(mapsEqual(responseRun.sourceHashes, expected), 'response phase source hash map differs from current freeze');
  insist(responseRun.cardSha256 === sha256(fs.readFileSync(CARD_PATH)), 'response result was produced for a different frozen card');
  insist(responseRun.preservation?.after === true, 'response phase did not preserve protected inputs');
  insist(ready.ticket === 'FEAT-010' && ready.identity_phase.checkpoints.length === 6, 'reviewed Ready identity phase is not the six-checkpoint assignment');
  return { expected, actual, responseRun };
}

function buildAdapter(controller, ready, transcript, scenario) {
  let now = 0;
  const owner = processIdentity(ready);
  const calls = [];
  const readRecordsSeen = [];
  const checkpointRegisters = {
    C002: { pc: 0xC002, dp: 0x00, x: 0x0000, y: 0x0000, u: 0x0000 },
    enemy_pre: { pc: 0x0350, dp: 0x02, x: 0xC800, y: 0x0800, u: 0x0000 },
    enemy_post: { pc: 0x0375, dp: 0x02, x: 0x0000, y: 0x0000, u: 0x0000 },
    helper_pre: { pc: 0x03D4, dp: 0x02, x: 334, y: 0x06B2, u: 0xC802 },
    helper_post: { pc: 0x042A, dp: 0x02, x: 0x0000, y: 0x0800, u: 0x0000 },
    B080: { pc: 0xB080, dp: 0x00, x: 0x0000, y: 0x0000, u: 0x0000 }
  };
  const helperCandidate = { pc: 0x03D4, dp: 0x02, x: 0x0000, y: 0x06B2, u: 0xC802 };
  let helperDescriptorCount = 0;
  let listenerChecks = 0;
  const launchIdentity = () => ({ pid: owner.pid, exe: owner.exe, start_ticks: owner.start_ticks, argv: owner.argv.slice() });
  const outputFor = (command, output = '') => ({ command, output, error: false });
  const actualAttach = transcript.find((entry) => Array.isArray(entry.commands) && entry.commands[0] === 'target remote 127.0.0.1:65520').response;

  const adapter = {
    clock: { now: () => now },
    async reserveAttempt() {
      calls.push('reserveAttempt');
      if (scenario.duplicateAttempt) return { reserved: false, attemptId: 'prior-attempt' };
      return { reserved: true, attemptId: `mock-${scenario.id}` };
    },
    async validatePreflight() { calls.push('validatePreflight'); return { ok: true, kind: 'CONDITIONAL_MOCK_ONLY' }; },
    async validateInitialTrace() { calls.push('validateInitialTrace'); return { ok: true, kind: 'CONDITIONAL_MOCK_ONLY' }; },
    async startSession() {
      calls.push('startSession');
      if (scenario.stallSession) return new Promise(() => {});
      return { isError: false, content: [{ type: 'text', text: JSON.stringify({ session_id: `mock-session-${scenario.id}` }) }] };
    },
    async batch({ commands, reads }) {
      calls.push(`batch:${commands[0]}`);
      if (scenario.stallConfigBatch && commands[0] === 'show architecture') return new Promise(() => {});
      if (scenario.structuredError && commands[0] === 'show architecture') {
        const good = commands.map((command, index) => outputFor(command, index === 0 ? 'The target architecture is set to "auto" (currently "m6809").\n' : ''));
        return { isError: false, content: good.map((entry) => ({ type: 'text', text: JSON.stringify(entry) })), structuredContent: { error: true, result: good } };
      }
      if (commands[0] === 'show architecture') {
        return makeEnvelope(commands.map((command, index) => outputFor(command, index === 0 ? 'The target architecture is set to "auto" (currently "m6809").\n' : '')));
      }
      if (commands[0] === 'target remote 127.0.0.1:65520') {
        if (scenario.retainedAttach) return clone(actualAttach);
        return makeEnvelope([
          outputFor(commands[0], 'Remote debugging using 127.0.0.1:65520\n0x0000057c in ?? ()\n[Stopped: in ??]\n'),
          outputFor(commands[1], registerLine({ pc: 0x057c, dp: 0x02, x: 0xa2b2, y: 0xa359, u: 0xe937 }))
        ]);
      }
      if (commands[0] === controller.STATUS_COMMAND) {
        const status = scenario.retainedAttach ? 'status unavailable\n' : 'received status S02\n';
        return makeEnvelope([outputFor(commands[0], status)]);
      }
      if (commands[0] === 'info breakpoints') return makeEnvelope([outputFor(commands[0], 'No breakpoints or watchpoints.\n')]);
      if (commands[0] === 'delete breakpoints') {
        return makeEnvelope(commands.map((command) => outputFor(command, 'Deleted breakpoint(s).\n')));
      }
      if (commands.includes('detach')) return makeEnvelope(commands.map((command) => outputFor(command, '')));
      if (reads) return makeEnvelope(commands.map((command) => outputFor(command, '')));
      if (commands.length === 3 && commands[2] === controller.REGISTER_COMMAND) {
        const checkpoint = controller.CHECKPOINTS.find((entry) => entry.arm === commands[0]);
        if (!checkpoint) throw new Error(`unexpected checkpoint arm: ${commands[0]}`);
        let registers = checkpointRegisters[checkpoint.name];
        if (checkpoint.name === 'helper_pre' && scenario.oneIgnoredHelper) {
          helperDescriptorCount += 1;
          registers = helperCandidate;
        }
        if (checkpoint.name === 'helper_pre' && scenario.secondHelper) {
          helperDescriptorCount += 1;
          registers = helperCandidate;
        }
        const stop = scenario.wrongStopAt === checkpoint.name ? '[Stopped: signal-received, SIGINT]\n' : '[Stopped: breakpoint-hit, breakpoint 1]\n';
        return makeEnvelope([
          outputFor(commands[0], ''),
          outputFor(commands[1], stop),
          outputFor(commands[2], registerLine(registers))
        ]);
      }
      if (commands.length === 2 && commands[0] === 'continue' && commands[1] === controller.REGISTER_COMMAND) {
        const registers = scenario.secondHelper && helperDescriptorCount > 0
          ? helperCandidate : checkpointRegisters.helper_pre;
        return makeEnvelope([outputFor(commands[0], '[Stopped: breakpoint-hit, breakpoint 2]\n'), outputFor(commands[1], registerLine(registers))]);
      }
      throw new Error(`unexpected mocked batch: ${commands.join(' | ')}`);
    },
    async launch() {
      calls.push('launch');
      if (scenario.ambiguousLaunch) return { ambiguous: true, pending: true, hostCommandSessionId: 'host-session-v2-fixed' };
      if (scenario.malformedLaunch) return { exit_code: 0, status: 'STARTED', stdout: '{"status":"STARTED"}' };
      return { exit_code: 0, status: 'STARTED', ...launchIdentity() };
    },
    async inspectOwner() {
      calls.push('inspectOwner');
      const actual = launchIdentity();
      if (scenario.wrongOwner) actual.start_ticks = 'reused-pid-different-start';
      return actual;
    },
    async inspectListener() {
      calls.push('inspectListener');
      listenerChecks += 1;
      return launchIdentity();
    },
    async validateCheckpoint({ checkpoint, reads }) {
      calls.push(`validateCheckpoint:${checkpoint.name}`);
      const readRecords = reads.map((read) => ({ name: read.name, address: read.address, length: read.length, file: read.file, complete: true, bytesRead: read.length }));
      readRecordsSeen.push(...readRecords);
      return {
        ok: true, kind: 'CONDITIONAL_MOCK_ONLY', readRecords,
        readCommands: readRecords.length,
        readBytes: readRecords.reduce((sum, record) => sum + record.bytesRead, 0),
        sourceMatch: true, destinationMatch: true, parMatch: true
      };
    },
    async recordHelperCandidate() { calls.push('recordHelperCandidate'); return { recorded: true }; },
    async finalIdentity({ checkpoints, reads }) {
      calls.push('finalIdentity');
      if (scenario.missingFinalIdentity) return { ok: true, kind: 'CONDITIONAL_MOCK_ONLY', identity_complete: false, checkpoints: checkpoints.length, readCommands: reads.count, readBytes: reads.bytes };
      return { ok: true, kind: 'CONDITIONAL_MOCK_ONLY', identity_complete: true, checkpoints: checkpoints.length, readCommands: reads.count, readBytes: reads.bytes };
    },
    async handoff(request) {
      calls.push('handoff');
      const acknowledged = launchIdentity();
      if (scenario.wrongHandoff) acknowledged.pid += 1;
      return {
        acknowledged: true, process: acknowledged, checkpoint: 'B080', breakpoints_remaining: 0,
        identity_complete: true, phaseStartMs: request.phaseStartMs,
        acceptedAtMs: scenario.staleHandoff ? request.phaseStartMs + 1001 : now + 1
      };
    },
    async stopSession() {
      calls.push('stopSession');
      if (scenario.cleanupFalseAck || scenario.stallCleanup) return stoppedAck(transcript, false);
      return stoppedAck(transcript, true);
    },
    async abortChild({ process }) {
      calls.push('abortChild');
      if (scenario.stallCleanup) return new Promise(() => {});
      return { exit_code: 0, status: 'ABORTED', pid: process.pid, start_ticks: process.start_ticks };
    },
    async finishTrace() {
      calls.push('finishTrace');
      return {
        process: { ...launchIdentity(), exited: true },
        coverage: !scenario.missingTraceCoverage,
        mockOnly: true,
        cpuInstructions: 0
      };
    },
    async finalize({ attemptId }) {
      calls.push('finalize');
      return { written: !scenario.finalWriteFailure, attemptId };
    }
  };

  const stalledStages = [];
  if (scenario.stallSession) stalledStages.push('startSession');
  if (scenario.stallConfigBatch) stalledStages.push('configurationBatch');
  if (scenario.stallCleanup) stalledStages.push('abortChild');
  adapter.awaitUntil = async (pending, deadline, stage) => {
    if (stalledStages.includes(stage)) {
      now = deadline;
      pending.then(() => undefined, () => undefined);
      return { status: 'deadline' };
    }
    const value = await pending;
    now += 1;
    if (now > deadline) { now = deadline + 1; return { status: 'deadline' }; }
    return { status: 'resolved', value };
  };
  return { adapter, calls, readRecordsSeen, get now() { return now; }, get listenerChecks() { return listenerChecks; } };
}

async function main() {
  const attemptDir = process.argv[2];
  insist(typeof attemptDir === 'string' && attemptDir.length > 0, 'wrapper attempt directory argument is required');
  const card = readJson(CARD_PATH);
  const ready = readJson(READY_PATH);
  const manifest = readJson(CASE_MANIFEST_PATH);
  const fixture = readJson(FIXTURE_PATH);
  insist(JSON.stringify(card.lifecycle_card.required_cases) === JSON.stringify(EXPECTED_CASES), 'lifecycle required_cases differs from the independent literal card list');
  const transcriptBytes = fs.readFileSync(TRANSCRIPT_PATH);
  insist(sha256(transcriptBytes) === RETAINED_TRANSCRIPT_SHA256, 'retained transcript SHA-256 mismatch');
  insist(fixture.provenance.transcript.sha256 === RETAINED_TRANSCRIPT_SHA256, 'response fixture transcript pin mismatch');
  const freeze = verifyFreeze(card, ready, manifest, attemptDir);
  const controller = loadController();
  const transcript = JSON.parse(transcriptBytes.toString('utf8'));
  const actualAttach = transcript.find((entry) => Array.isArray(entry.commands) && entry.commands[0] === 'target remote 127.0.0.1:65520');
  insist(actualAttach, 'retained attach response is absent');

  const cases = [];
  async function runCase(id, scenario, check) {
    const env = buildAdapter(controller, ready, transcript, { id, ...scenario });
    let report = null;
    try {
      report = await controller.runFixedController(env.adapter, {
        reviewedReady: ready,
        expectedFrozenSources: freeze.expected,
        actualFrozenSources: freeze.actual,
        expectedReadySha256: READY_SHA256,
        actualReadySha256: sha256(fs.readFileSync(READY_PATH))
      });
      check(report, env);
    } catch (error) {
      error.caseEvidence = {
        caseId: id,
        report: report ? {
          status: report.status,
          classification: report.classification,
          productAssertion: report.productAssertion,
          ownership: report.ownership,
          firstFailureEvidence: report.firstFailureEvidence,
          cleanup: report.cleanup,
          reads: report.reads,
          checkpoints: report.checkpoints,
          stops: report.stops,
          handoff: report.handoff
        } : null,
        mockedCalls: env.calls.slice()
      };
      throw error;
    }
    cases.push({ id, status: 'PASS', classification: report.classification, reportStatus: report.status, firstFailureStage: report.firstFailureEvidence?.stage || null });
    return { report, env };
  }
  function ownership(report, key) { return report.ownership[key]; }
  function state(report, key) { return ownership(report, key)?.state; }
  function assertFirstFailure(report, stage, responsePresent) {
    insist(report.firstFailureEvidence && report.firstFailureEvidence.stage === stage, `first failure stage must be ${stage}`);
    if (responsePresent) insist(report.firstFailureEvidence.response && typeof report.firstFailureEvidence.response === 'object', `first failure response must be preserved for ${stage}`);
    else insist(report.firstFailureEvidence.error && typeof report.firstFailureEvidence.error.message === 'string', `first failure details must be retained for ${stage}`);
  }

  await runCase('retained_attach_signal_unknown_rejected_before_reads', { retainedAttach: true }, (report, env) => {
    insist(report.productAssertion === 'NOT_EVALUATED' && report.reads.requestedCommands === 0, 'retained unknown signal must reject before memory reads');
    insist(env.calls.some((call) => call === 'launch') && !env.calls.some((call) => call.startsWith('batch:dump binary memory')), 'controller must reach attach after mock launch, then stop before read batches');
    insist(state(report, 'child') === 'released' && state(report, 'session') === 'released', 'owned mock child/session cleanup must be acknowledged');
    assertFirstFailure(report, 'statusBatch', true);
  });
  await runCase('valid_conditional_sequence_measured_reads_and_handoff', {}, (report, env) => {
    insist(report.status === 'CONDITIONAL_COMPLETE' && report.classification === 'CONDITIONAL_MOCK_ONLY', 'complete mock sequence must remain conditionally labeled');
    insist(report.productAssertion === 'NOT_EVALUATED' && report.runtimeIdentityProved === false && report.serviceCancellationProved === false, 'mock path must not claim product or runtime proof');
    insist(report.reads.requestedCommands === EXPECTED_READS && report.reads.requestedBytes === EXPECTED_READ_BYTES, 'requested read count/bytes differ from the independent Ready literal');
    insist(report.reads.completedCommands === EXPECTED_READS && report.reads.completedBytes === EXPECTED_READ_BYTES, 'completed read count/bytes differ from typed mock records');
    insist(report.checkpoints.join('|') === 'C002|enemy_pre|enemy_post|helper_pre|helper_post|B080', 'six checkpoint sequence differs from the independent literal');
    insist(report.stops === 7 && report.handoff.acknowledged === true && report.handoff.checkpoint === 'B080', 'normal path stop cap or handoff differs from the independent literal');
    insist(env.listenerChecks === 2, 'exact listener owner must be rechecked after attach and status before reads');
    insist(state(report, 'child') === 'released' && state(report, 'session') === 'released', 'valid fixture cleanup must retain positive acknowledgements');
  });
  await runCase('structured_error_prevents_launch', { structuredError: true }, (report, env) => {
    insist(!env.calls.includes('launch'), 'structured configuration error must reject before launch');
    insist(report.reads.requestedCommands === 0 && state(report, 'session') === 'released', 'pre-launch error must perform acknowledged session cleanup only');
    assertFirstFailure(report, 'configurationBatch', true);
  });
  await runCase('ambiguous_launch_host_session_tracked', { ambiguousLaunch: true }, (report, env) => {
    insist(state(report, 'hostCommand') === 'unresolved' && ownership(report, 'hostCommand').sessionId === 'host-session-v2-fixed', 'ambiguous host command session ID and ownership must remain visible');
    insist(state(report, 'child') === 'unresolved' && ownership(report, 'child').intent === true && !env.calls.includes('abortChild'), 'unknown child ownership must not trigger broad abort');
    insist(ownership(report, 'session').id === 'mock-session-ambiguous_launch_host_session_tracked', 'session ID must remain in ownership details');
    assertFirstFailure(report, 'launch', true);
  });
  await runCase('malformed_launch_after_child_unknown_cleanup', { malformedLaunch: true }, (report, env) => {
    insist(state(report, 'child') === 'unresolved' && ownership(report, 'child').identity === null, 'malformed launch must retain unknown child ownership without inventing identity');
    insist(!env.calls.includes('abortChild') && state(report, 'session') === 'released', 'no unbound abort is allowed; known session cleanup is acknowledged');
    assertFirstFailure(report, 'launch', true);
  });
  await runCase('wrong_owner_rejected', { wrongOwner: true }, (report, env) => {
    insist(report.reads.requestedCommands === 0 && state(report, 'child') === 'unresolved', 'wrong observed owner must reject before reads and preserve uncertainty');
    insist(!env.calls.includes('abortChild') && state(report, 'session') === 'released', 'owner mismatch must not abort a possibly different process');
    assertFirstFailure(report, 'inspectOwner', true);
  });
  await runCase('missing_final_identity_rejected', { missingFinalIdentity: true }, (report, env) => {
    insist(report.status === 'REJECTED' && report.handoff === null, 'missing final identity must block handoff');
    insist(report.checkpoints.length === 6 && report.reads.completedCommands === EXPECTED_READS, 'failure occurs after all conditional checkpoint reads');
    insist(!env.calls.includes('handoff') && state(report, 'child') === 'released' && state(report, 'session') === 'released', 'failed final identity must clean up both owned resources');
    assertFirstFailure(report, 'finalIdentity', true);
  });
  await runCase('wrong_handoff_ack_rejected', { wrongHandoff: true }, (report, env) => {
    insist(report.status === 'REJECTED' && report.handoff === null, 'wrong process handoff acknowledgement must be rejected');
    insist(env.calls.includes('handoff') && !env.calls.includes('finishTrace'), 'wrong handoff must prevent trace completion');
    insist(state(report, 'child') === 'released' && state(report, 'session') === 'released', 'wrong handoff path must clean up exact mock ownership');
    assertFirstFailure(report, 'handoff', true);
  });
  await runCase('stale_handoff_rejected', { staleHandoff: true }, (report) => {
    insist(report.status === 'REJECTED' && report.handoff === null, 'stale handoff acknowledgement must be rejected');
    insist(report.firstFailureEvidence.error.code === 'HANDOFF_STALE', 'stale handoff rejection code differs from the independent expectation');
    assertFirstFailure(report, 'handoff', true);
  });
  await runCase('checkpoint_wrong_stop_reason_rejected', { wrongStopAt: 'C002' }, (report) => {
    insist(report.checkpoints.length === 0 && report.reads.requestedCommands === 0, 'wrong stop reason must block admission and reads');
    insist(report.firstFailureEvidence.error.code === 'STOP_REASON_MISMATCH', 'wrong stop reason must fail the exact first-component check');
    insist(state(report, 'child') === 'released' && state(report, 'session') === 'released', 'wrong stop reason path must perform acknowledged cleanup');
    assertFirstFailure(report, 'checkpoint:C002', true);
  });
  await runCase('stalled_session_creation_marks_unresolved', { stallSession: true }, (report, env) => {
    insist(state(report, 'session') === 'unresolved' && ownership(report, 'session').intent === true && ownership(report, 'session').id === null, 'stalled creation must preserve intent and unknown session ownership');
    insist(state(report, 'child') === 'none' && !env.calls.includes('launch'), 'stalled session creation must prevent launch');
    assertFirstFailure(report, 'startSession', false);
  });
  await runCase('stalled_batch_deadline', { stallConfigBatch: true }, (report, env) => {
    insist(report.firstFailureEvidence.error.code === 'DEADLINE' && report.firstFailureEvidence.stage === 'configurationBatch', 'stalled batch must fail at its absolute work deadline');
    insist(state(report, 'session') === 'released' && env.calls.includes('stopSession'), 'bounded cleanup must use remaining total deadline');
    assertFirstFailure(report, 'configurationBatch', false);
  });
  await runCase('stalled_cleanup_retains_ownership', { stallCleanup: true }, (report) => {
    insist(report.status === 'EVIDENCE_UNRESOLVED' && report.classification === 'EVIDENCE_FAILURE', 'elapsed total deadline must make final evidence explicitly unresolved');
    insist(state(report, 'child') === 'unresolved' && state(report, 'session') === 'unresolved', 'stalled cleanup cannot imply cancellation');
    insist(report.ownership.session.id === 'mock-session-stalled_cleanup_retains_ownership', 'unresolved session ID must be retained');
    assertFirstFailure(report, 'stopSessionAfterDetach', true);
  });
  await runCase('cleanup_false_ack_retains_ownership', { cleanupFalseAck: true }, (report) => {
    insist(state(report, 'session') === 'unresolved' && report.ownership.session.id === 'mock-session-cleanup_false_ack_retains_ownership', 'nested stopped:false must retain session ownership and its ID');
    insist(state(report, 'child') === 'released' && report.cleanup.evidence.some((item) => item.stage === 'stopSessionAfterDetach'), 'cleanup acknowledgement failure evidence must be retained');
    const isStoppedFalse = (text) => JSON.parse(text).stopped === false;
    insist(isStoppedFalse(report.firstFailureEvidence.response.content[0].text), 'first failure must retain the nested stopped:false response before cleanup');
    insist(isStoppedFalse(JSON.stringify({ stopped: false }, null, 2)), 'pretty stopped:false JSON must satisfy the semantic assertion');
    insist(isStoppedFalse(JSON.stringify({ stopped: false })), 'compact stopped:false JSON must satisfy the semantic assertion');
    insist(!isStoppedFalse(JSON.stringify({ stopped: true })), 'stopped:true JSON must fail the semantic assertion');
    let directFalseCode = null;
    try { controller.decodeStoppedAck(stoppedAck(transcript, false)); }
    catch (error) { directFalseCode = error.code; }
    insist(directFalseCode === 'STOP_ACK_FALSE', 'direct stopped:false fixture must reject with the typed STOP_ACK_FALSE code');
    insist(report.firstFailureEvidence.error.code === 'STOP_ACK_FALSE', 'nested stopped:false fixture must reject with the typed STOP_ACK_FALSE code');
    assertFirstFailure(report, 'stopSessionAfterDetach', true);
  });
  await runCase('final_write_failure_visible', { finalWriteFailure: true }, (report) => {
    insist(report.status === 'EVIDENCE_FAILURE' && report.classification === 'EVIDENCE_FAILURE', 'failed final evidence write must be visible');
    insist(report.evidence.finalized === false && report.evidence.failure, 'failed finalization must not be reported as written');
    insist(state(report, 'session') === 'released' && state(report, 'child') === 'released', 'evidence failure does not erase positive ownership cleanup');
    assertFirstFailure(report, 'finalizeEvidence', true);
  });
  await runCase('duplicate_attempt_preserves_original', { duplicateAttempt: true }, (report, env) => {
    insist(report.status === 'SETUP_REJECTED' && report.evidence.reserved === false, 'duplicate exclusive reservation must reject before evidence mutation');
    insist(env.calls.length === 1 && env.calls[0] === 'reserveAttempt', 'duplicate reservation must call no tools or finalizer');
    insist(report.evidence.failure.includes('left untouched'), 'existing attempt evidence must be reported as preserved');
  });
  await runCase('missing_trace_coverage_not_product_failure', { missingTraceCoverage: true }, (report) => {
    insist(report.status === 'INCOMPLETE_COVERAGE' && report.classification === 'MISSING_COVERAGE', 'missing trace coverage must remain a separate classification');
    insist(report.productAssertion === 'NOT_EVALUATED' && report.coverage === 'MISSING_COVERAGE', 'missing mock trace coverage must not become a product assertion');
    insist(state(report, 'session') === 'released' && state(report, 'child') === 'released', 'missing coverage path must retain completed mock cleanup');
  });
  await runCase('one_ignored_helper_descriptor_within_eight_stops', { oneIgnoredHelper: true }, (report) => {
    insist(report.status === 'CONDITIONAL_COMPLETE' && report.stops === 8, 'one ignored helper descriptor must remain within the fixed eight-stop cap');
    insist(report.reads.requestedCommands === EXPECTED_READS && report.reads.completedBytes === EXPECTED_READ_BYTES, 'one ignored descriptor must preserve the 23-read/27724-byte recipe');
    insist(report.checkpoints.length === 6 && report.handoff.acknowledged, 'single ignored descriptor path must reach the same six-checkpoint handoff');
  });
  await runCase('second_helper_descriptor_rejected', { secondHelper: true }, (report) => {
    insist(report.status === 'REJECTED' && report.firstFailureEvidence.error.code === 'SECOND_HELPER_DESCRIPTOR', 'second helper descriptor must be rejected');
    insist(report.reads.requestedCommands === 9 && report.checkpoints.join('|') === 'C002|enemy_pre|enemy_post', 'second descriptor must stop before helper_pre admission/read');
    insist(state(report, 'child') === 'released' && state(report, 'session') === 'released', 'second descriptor rejection must clean up known ownership');
    assertFirstFailure(report, 'helperDescriptorContinuation', true);
  });

  insist(JSON.stringify(cases.map((item) => item.id)) === JSON.stringify(EXPECTED_CASES), 'executed lifecycle cases differ from the independent literal list');
  process.stdout.write(`${JSON.stringify({
    schema: 'ladybug.feat010.controller-v2.lifecycle.v1',
    status: 'PASS',
    qualification: 'CONDITIONAL_MOCK_WIRING_ONLY',
    sourceHashes: freeze.actual,
    readySha256: READY_SHA256,
    retainedTranscriptSha256: RETAINED_TRANSCRIPT_SHA256,
    expectedReadCommands: EXPECTED_READS,
    expectedReadBytes: EXPECTED_READ_BYTES,
    expectedCases: EXPECTED_CASES,
    cases,
    productAssertion: 'NOT_EVALUATED',
    runtimeIdentityProved: false,
    serviceCancellationProved: false,
    maintenanceStatusGrammar: 'Synthetic contract fixture only; native output format was not observed or qualified'
  })}\n`);
}

main().catch((error) => {
  process.stdout.write(`${JSON.stringify({ schema: 'ladybug.feat010.controller-v2.lifecycle.v1', status: 'FAIL', firstFailure: String(error?.message || error), failingCase: error?.caseEvidence || null })}\n`);
  process.exitCode = 1;
});
