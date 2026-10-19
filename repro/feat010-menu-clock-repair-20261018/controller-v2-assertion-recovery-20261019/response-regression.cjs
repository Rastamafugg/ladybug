'use strict';

// Offline historical-response characterization. This reads only its fixed
// local fixtures/evidence and writes one JSON document to stdout.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const auditDir = __dirname;
const fixturePath = path.join(auditDir, 'response-fixtures.json');
const fixtures = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));

function readBoundFile(binding) {
  const filePath = path.resolve(auditDir, binding.path);
  const bytes = fs.readFileSync(filePath);
  const digest = crypto.createHash('sha256').update(bytes).digest('hex');
  assert.equal(digest, binding.sha256.toLowerCase(), `SHA256 mismatch: ${binding.path}`);
  return { filePath, bytes, digest };
}

for (const binding of Object.values(fixtures.provenance)) readBoundFile(binding);
const transcript = JSON.parse(readBoundFile(fixtures.provenance.transcript).bytes.toString('utf8'));
const controller = readBoundFile(fixtures.provenance.controllerTranscription).bytes.toString('utf8');
const sourceProvenance = JSON.parse(readBoundFile(fixtures.provenance.sourceProvenance).bytes.toString('utf8'));
const runtimeResult = JSON.parse(readBoundFile(fixtures.provenance.runtimeResult).bytes.toString('utf8'));
const parentQa = JSON.parse(readBoundFile(fixtures.provenance.parentQa).bytes.toString('utf8'));
assert.equal(sourceProvenance.archived_controller, 'executed-controller.js.txt');
const recoveredControllerCall = sourceProvenance.recovered_calls.find((call) => call.kind === 'controller');
assert.ok(recoveredControllerCall, 'original controller tool call was not recovered');
assert.equal(recoveredControllerCall.call_id, fixtures.provenance.controllerTranscription.recoveredCallId);
assert.equal(recoveredControllerCall.timestamp, fixtures.provenance.controllerTranscription.recoveredTimestamp);
assert.equal(recoveredControllerCall.sha256, fixtures.provenance.controllerTranscription.sha256);
assert.equal(recoveredControllerCall.bytes, fixtures.provenance.controllerTranscription.bytes);
assert.equal(recoveredControllerCall.formatted_copy_differed, false);
assert.match(sourceProvenance.limit, /not included in pre-dispatch source freeze\/qualification/i);
assert.equal(runtimeResult.identity.verdict, 'SETUP_REJECTED');
assert.equal(parentQa.code_identity_proved, false);
assert.equal(transcript.length, 5);

const selected = Object.fromEntries(Object.entries(fixtures.provenance.transcript.selectors)
  .map(([name, index]) => [name, transcript[index]]));
const startEnvelope = selected.startSession.response;
const configurationCall = selected.configuration;
const architectureEnvelope = configurationCall.response;
const attachCall = selected.attachAndRegisters;
const attachEnvelope = attachCall.response;

function parseTextContent(response) {
  if (!Array.isArray(response.content)) throw new Error('missing content array');
  return response.content.map((item) => {
    if (item?.type !== 'text' || typeof item.text !== 'string') throw new Error('missing text content');
    return JSON.parse(item.text);
  });
}

function checkedResults(response) {
  if (!response || response.isError !== false) throw new Error('outer MCP envelope is not successful');
  const contentResults = parseTextContent(response);
  const structuredResults = response.structuredContent?.result;
  if (!Array.isArray(structuredResults)) throw new Error('missing structured result array');
  assert.deepEqual(contentResults, structuredResults, 'MCP content and structured result disagree');
  for (const item of structuredResults) {
    if (item?.error !== false) throw new Error('command result has an error');
  }
  return structuredResults;
}

// Independent baseline oracle: command identity and explicit output fields are
// read from the retained structured result, with duplicate-channel agreement.
const sessionRecord = JSON.parse(startEnvelope.content[0].text);
assert.equal(startEnvelope.isError, false);
assert.equal(sessionRecord.session_id, fixtures.baselineOracle.sessionId);
assert.equal(configurationCall.commands[0], fixtures.expectedCommands.architecture);
const architectureResults = checkedResults(architectureEnvelope);
assert.match(architectureResults[0].output, /currently\s+"m6809"/);
assert.equal(attachCall.commands.length, fixtures.expectedCommands.attach.length);
assert.deepEqual(attachCall.commands, fixtures.expectedCommands.attach);
const attachResults = checkedResults(attachEnvelope);
assert.match(attachResults[0].output, /Remote debugging using 127\.0\.0\.1:65520/);
assert.match(attachResults[0].output, /\[Stopped:/);
assert.doesNotMatch(attachResults[0].output, /SIGINT|S02|S05/);
assert.equal(attachCall.commands.includes('maintenance packet ?'), false);
assert.equal(attachResults[1].command, fixtures.expectedCommands.registerCommand);
const registerMatch = /^pc=([0-9a-f]{4}) dp=([0-9a-f]{2}) x=([0-9a-f]{4}) y=([0-9a-f]{4}) u=([0-9a-f]{4})\s*$/im.exec(attachResults[1].output);
assert.ok(registerMatch, 'explicit register command output is absent');
const baselineRegisters = Object.fromEntries(['pc', 'dp', 'x', 'y', 'u']
  .map((name, index) => [name, registerMatch[index + 1].toLowerCase()]));
assert.deepEqual(baselineRegisters, fixtures.baselineOracle.registers);
assert.equal(fixtures.baselineOracle.stopped, true);
assert.equal(fixtures.baselineOracle.signal, null);
assert.equal(fixtures.baselineOracle.identityComplete, false);

const sourceLines = controller.split(/\r?\n/);
function exactFunctionLine(name) {
  const index = sourceLines.findIndex((line) => new RegExp(`^\\s*(?:async\\s+)?function\\s+${name}\\(`).test(line));
  if (index < 0) throw new Error(`historical function not found: ${name}`);
  return { line: index + 1, source: sourceLines[index] };
}
const historicalLines = Object.fromEntries(['asText', 'errorResult', 'findSid', 'gdb', 'regs']
  .map((name) => [name, exactFunctionLine(name)]));
const architectureLine = sourceLines.find((line) => line.includes('if(!asText(conf).includes("m6809"))'));
const stopLine = sourceLines.find((line) => line.includes('if(!/SIGINT/.test(asText(attach)))'));
if (!architectureLine || !stopLine) throw new Error('historical gate expression not found');
const architectureReject = architectureLine.match(/if\((.*?)\)throw Error\("Architecture not proved m6809"\)/)?.[1];
const stopReject = stopLine.match(/if\((.*?)\)throw Error\("Connection SIGINT not observed"\)/)?.[1];
if (!architectureReject || !stopReject) throw new Error('historical predicate extraction failed');

const toolCalls = [];
let mockedBatchCalls = 0;
const mockEpochMs = 1_797_000_000_000;
const mockTools = {
  exec_command: async () => { throw new Error('unexpected mocked exec_command call'); },
  write_stdin: async () => { throw new Error('unexpected mocked write_stdin call'); },
  mcp__gdb_mcp__start_session: async () => { throw new Error('unexpected mocked start_session call'); },
  mcp__gdb_mcp__batch_commands: async (args) => {
    mockedBatchCalls++;
    toolCalls.push({ method: 'mcp__gdb_mcp__batch_commands', args: JSON.parse(JSON.stringify(args)) });
    return mockContext.mockResponse;
  },
  mcp__gdb_mcp__stop_session: async () => { throw new Error('unexpected mocked stop_session call'); }
};
const mockContext = vm.createContext({
  JSON,
  Object,
  Error,
  Date: { now: () => mockEpochMs },
  tools: mockTools,
  phase: 'OFFLINE-CHARACTERIZATION',
  phaseStart: mockEpochMs,
  sid: fixtures.baselineOracle.sessionId,
  transcript: [],
  checkBudget: () => {},
  remaining: () => 52,
  mockResponse: null
});
for (const name of ['asText', 'errorResult', 'findSid', 'gdb', 'regs']) {
  vm.runInContext(historicalLines[name].source, mockContext, { timeout: 250 });
}

function clone(value) { return JSON.parse(JSON.stringify(value)); }
function applyMutation(response, mutation) {
  if (mutation.op === 'deleteTop') {
    delete response[mutation.field];
    return;
  }
  if (mutation.op === 'topField') {
    response[mutation.field] = mutation.value;
    return;
  }
  if (mutation.op === 'sessionField') {
    const record = JSON.parse(response.content[0].text);
    record[mutation.field] = mutation.value;
    response.content[0].text = JSON.stringify(record, null, 2);
    return;
  }
  if (mutation.op === 'resultField') {
    const result = response.structuredContent?.result?.[mutation.index];
    if (!result) throw new Error(`missing structured result ${mutation.index}`);
    result[mutation.field] = mutation.value;
    if (mutation.mirrorContent && response.content?.[mutation.index]?.type === 'text') {
      const contentResult = JSON.parse(response.content[mutation.index].text);
      contentResult[mutation.field] = mutation.value;
      response.content[mutation.index].text = JSON.stringify(contentResult, null, 2);
    }
    return;
  }
  throw new Error(`unknown mutation operation: ${mutation.op}`);
}

function oldArchitectureAccepted(response) {
  mockContext.conf = response;
  return !vm.runInContext(architectureReject, mockContext, { timeout: 100 });
}
function oldSignalAccepted(response) {
  mockContext.attach = response;
  return !vm.runInContext(stopReject, mockContext, { timeout: 100 });
}
function formatRegisters(value) {
  const registers = JSON.parse(JSON.stringify(value));
  return Object.fromEntries(Object.entries(registers).map(([name, number]) =>
    [name, number.toString(16).padStart(name === 'dp' ? 2 : 4, '0')]));
}
async function oldGdbResult(response) {
  toolCalls.length = 0;
  mockContext.mockResponse = response;
  mockContext.transcript = [];
  try {
    await vm.runInContext('gdb(["fixture command"])', mockContext, { timeout: 250 });
    return 'accept';
  } catch {
    return 'reject';
  }
}

function baseFor(source) {
  if (source === 'startSession') return clone(startEnvelope);
  if (source === 'configuration') return clone(architectureEnvelope);
  if (source === 'attachAndRegisters') return clone(attachEnvelope);
  throw new Error(`unknown fixture source: ${source}`);
}

const reportCases = [];
for (const testCase of fixtures.cases) {
  const response = baseFor(testCase.source);
  for (const mutation of testCase.mutations) applyMutation(response, mutation);
  const observed = {};

  if (testCase.source === 'startSession') {
    const sessionId = mockContext.findSid(response);
    observed.sessionId = sessionId;
    observed.sessionAdmitted = Boolean(sessionId);
  } else if (testCase.source === 'configuration') {
    observed.architectureAccept = oldArchitectureAccepted(response);
  } else {
    observed.errorResult = Boolean(mockContext.errorResult(response));
    observed.gdb = await oldGdbResult(response);
    observed.signalAccept = oldSignalAccepted(response);
    try {
      observed.registers = formatRegisters(mockContext.regs(response));
    } catch {
      observed.registers = null;
    }
  }

  for (const [field, expected] of Object.entries(testCase.historical)) {
    assert.deepEqual(observed[field], expected, `${testCase.id}: historical ${field} changed`);
  }

  const differences = [];
  function compareBoolean(field, expected, actual) {
    if (expected === undefined || actual === undefined || expected === actual) return;
    differences.push({ field, class: expected ? 'FALSE_REJECT' : 'FALSE_ACCEPT', expected, observed: actual });
  }
  compareBoolean('sessionAccept', testCase.oracle.sessionAccept, observed.sessionAdmitted);
  compareBoolean('architectureAccept', testCase.oracle.architectureAccept, observed.architectureAccept);
  compareBoolean('responseAccept', testCase.oracle.responseAccept, observed.gdb === 'accept');
  compareBoolean('signalAccept', testCase.oracle.signalAccept, observed.signalAccept);
  if (testCase.oracle.sessionId && observed.sessionId !== testCase.oracle.sessionId) {
    differences.push({ field: 'sessionId', class: 'WRONG_SESSION_ID', expected: testCase.oracle.sessionId, observed: observed.sessionId });
  }
  if (testCase.oracle.registers && JSON.stringify(testCase.oracle.registers) !== JSON.stringify(observed.registers)) {
    differences.push({ field: 'registers', class: 'WRONG_REGISTER_VALUES', expected: testCase.oracle.registers, observed: observed.registers });
  }
  if (testCase.oracle.registers === null && observed.registers) {
    differences.push({ field: 'registers', class: 'FALSE_ACCEPT', expected: null, observed: observed.registers });
  }
  reportCases.push({ id: testCase.id, source: testCase.source, oracle: testCase.oracle, historical: observed, differences });
}

const tally = { cases: reportCases.length, falseAcceptAssertions: 0, falseRejectAssertions: 0, wrongSessionIdAssertions: 0, wrongRegisterAssertions: 0, matchingCases: 0 };
for (const item of reportCases) {
  for (const difference of item.differences) {
    if (difference.class === 'FALSE_ACCEPT') tally.falseAcceptAssertions++;
    else if (difference.class === 'FALSE_REJECT') tally.falseRejectAssertions++;
    else if (difference.class === 'WRONG_SESSION_ID') tally.wrongSessionIdAssertions++;
    else if (difference.class === 'WRONG_REGISTER_VALUES') tally.wrongRegisterAssertions++;
  }
  if (item.differences.length === 0) tally.matchingCases++;
}

const output = {
  kind: 'offline_historical_response_characterization',
  ticket: fixtures.ticket,
  status: 'NON_GATING_CHARACTERIZATION_ONLY',
  baseline: {
    transcriptPath: fixtures.provenance.transcript.path,
    transcriptSha256: fixtures.provenance.transcript.sha256.toLowerCase(),
    controllerTranscriptionSha256: fixtures.provenance.controllerTranscription.sha256.toLowerCase(),
    sessionId: sessionRecord.session_id,
    architecture: 'm6809',
    stopped: true,
    signal: 'unknown',
    registers: baselineRegisters,
    identityComplete: false,
    controllerSourceProvenance: 'exact original tool input recovered and byte-matched; not included in pre-dispatch freeze/qualification'
  },
  sourceLines: Object.fromEntries(Object.entries(historicalLines).map(([name, detail]) => [name, detail.line]).concat([
    ['architectureGate', sourceLines.indexOf(architectureLine) + 1],
    ['signalGate', sourceLines.indexOf(stopLine) + 1]
  ])),
  mockedExecution: {
    realToolCalls: 0,
    mockedBatchCommandCalls: mockedBatchCalls,
    mockedMethods: ['exec_command', 'write_stdin', 'mcp__gdb_mcp__start_session', 'mcp__gdb_mcp__batch_commands', 'mcp__gdb_mcp__stop_session'],
    processOrNetworkCalls: 0,
    emulatorOrLiveGdbCalls: 0,
    filesystemWrites: 0
  },
  tally,
  cases: reportCases
};
console.log(JSON.stringify(output));
