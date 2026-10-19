'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const Module = require('node:module');
const vm = require('node:vm');

const ROOT = __dirname;
const FIXTURE_PATH = path.join(ROOT, 'response-fixtures-v2.json');
const TRANSCRIPT_PATH = path.resolve(ROOT, '..', 'stutter-runtime-gdb-transcript.json');
const HISTORICAL_PATH = path.join(ROOT, 'executed-controller.js.txt');
const MODULE_PATH = path.join(ROOT, 'controller-v2.js.txt');
const EXPECTED_CASES = [
  'real_session', 'new_opaque_session', 'error_session_echo', 'conflicting_session',
  'real_architecture', 'negated_architecture', 'real_stopped_unknown_signal', 'real_register_values',
  'outer_error', 'per_command_error', 'structured_error', 'truncated_batch', 'wrong_command',
  'channel_conflict', 'content_only_valid', 'structured_only_valid', 'register_echo_only',
  'sigint_echo_only', 'explicit_received_S02', 'explicit_received_S05', 'unknown_status', 'stop_ack_false'
];
const RETAINED_TRANSCRIPT_SHA256 = '1617ba0bde61ca2bafe2d4603ae5d8f295c21b8efd3ef921d3f092b7560fef20';
const RETAINED_HISTORICAL_SHA256 = 'e8214e762c2692204751e1f11b0dba304587083af6f69a8e547ddea2c2873cdc';

function sha256(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function insist(condition, message) { if (!condition) throw new Error(message); }
function expectFault(callback, code, label) {
  let caught = null;
  try { callback(); } catch (error) { caught = error; }
  insist(caught && caught.code === code, `${label}: expected ${code}, observed ${caught?.code || 'no typed fault'}`);
}
function contentEnvelope(items) { return { isError: false, content: items.map((item) => ({ type: 'text', text: JSON.stringify(item) })) }; }
function oneResult(command, output, error = false) { return { command, output, error }; }

async function main() {
  const fixtureBytes = fs.readFileSync(FIXTURE_PATH);
  const fixture = JSON.parse(fixtureBytes.toString('utf8'));
  insist(JSON.stringify(fixture.required_cases) === JSON.stringify(EXPECTED_CASES), 'fixture required_cases differs from the independent literal card list');
  const transcriptBytes = fs.readFileSync(TRANSCRIPT_PATH);
  insist(sha256(transcriptBytes) === RETAINED_TRANSCRIPT_SHA256, 'retained transcript hash mismatch');
  insist(fixture.provenance.transcript.sha256 === RETAINED_TRANSCRIPT_SHA256, 'fixture transcript pin differs from the independent literal hash');
  const historicalBytes = fs.readFileSync(HISTORICAL_PATH);
  insist(sha256(historicalBytes) === RETAINED_HISTORICAL_SHA256, 'retained historical controller hash mismatch');
  insist(fixture.provenance.historical_controller.sha256 === RETAINED_HISTORICAL_SHA256, 'fixture historical controller pin mismatch');

  const transcript = JSON.parse(transcriptBytes.toString('utf8'));
  const startEntry = transcript.find((entry) => entry.operation === 'start_session');
  const configEntry = transcript.find((entry) => Array.isArray(entry.commands) && entry.commands[0] === 'show architecture');
  const attachEntry = transcript.find((entry) => Array.isArray(entry.commands) && entry.commands[0] === 'target remote 127.0.0.1:65520');
  insist(startEntry && configEntry && attachEntry, 'retained transcript lacks a required response');
  const configCommands = configEntry.commands;
  const attachCommands = attachEntry.commands;
  const configResponse = startEnvelope(configEntry.response);
  const attachResponse = startEnvelope(attachEntry.response);
  const moduleSource = fs.readFileSync(MODULE_PATH, 'utf8');
  const inertModule = new Module(MODULE_PATH, module);
  inertModule.filename = MODULE_PATH;
  inertModule.paths = Module._nodeModulePaths(ROOT);
  inertModule._compile(moduleSource, MODULE_PATH);
  const decoder = inertModule.exports;

  const seen = [];
  function check(name, body) {
    try { body(); }
    catch (error) { throw new Error(`${name}: ${error?.message || error}`); }
    seen.push(name);
  }
  const sessionRecord = JSON.parse(startEntry.response.content[0].text);
  check('real_session', () => {
    const decoded = decoder.decodeSessionResponse(startEntry.response);
    insist(decoded.sessionId === fixture.retained_oracle.session_id, 'real session ID differs from retained oracle');
  });
  check('new_opaque_session', () => {
    const response = contentEnvelope([{ session_id: fixture.synthetic_contract_cases.new_opaque_session_id }]);
    insist(decoder.decodeSessionResponse(response).sessionId === fixture.synthetic_contract_cases.new_opaque_session_id, 'new opaque session ID was rejected or changed');
  });
  check('error_session_echo', () => {
    const response = contentEnvelope([{ session_id: sessionRecord.session_id, error: 'synthetic failure' }]);
    expectFault(() => decoder.decodeSessionResponse(response), 'SESSION_TYPED_ERROR', 'error session echo');
  });
  check('conflicting_session', () => {
    const response = contentEnvelope([{ session_id: 'opaque-a' }]);
    response.structuredContent = { session_id: 'opaque-b' };
    expectFault(() => decoder.decodeSessionResponse(response), 'SESSION_ID_CONFLICT', 'conflicting session channels');
  });
  check('real_architecture', () => {
    const decoded = decoder.decodeArchitectureResponse(configResponse, configCommands);
    insist(decoded.architecture === fixture.retained_oracle.architecture, 'retained architecture differs from oracle');
  });
  check('negated_architecture', () => {
    const response = contentEnvelope(configCommands.map((command, index) => oneResult(command, index === 0 ? 'm6809 is not selected; the architecture is not m6809.\n' : '')));
    expectFault(() => decoder.decodeArchitectureResponse(response, configCommands), 'ARCHITECTURE_UNPROVED', 'negated architecture');
  });
  let attachDecoded;
  check('real_stopped_unknown_signal', () => {
    attachDecoded = decoder.decodeAttachResponse(attachResponse, attachCommands);
    insist(attachDecoded.stopped === true && attachDecoded.signal === null && attachDecoded.signalStatus === 'unknown', 'retained stopped marker must keep signal unknown');
    insist(JSON.stringify(attachDecoded.registers) === JSON.stringify({ pc: 0x057c, dp: 0x02, x: 0xa2b2, y: 0xa359, u: 0xe937 }), 'retained attach registers differ from independent oracle');
  });
  check('real_register_values', () => {
    const decoded = decoder.decodeRegisterOutput(attachDecoded.results[1].output);
    const expected = Object.fromEntries(Object.entries(fixture.retained_oracle.registers).map(([key, value]) => [key, parseInt(value, 16)]));
    insist(JSON.stringify(decoded) === JSON.stringify(expected), 'register decoder differs from independent retained values');
  });
  const statusCommand = fixture.commands.status_query;
  check('outer_error', () => {
    const response = contentEnvelope([oneResult(statusCommand, 'received status S02\n')]);
    response.isError = true;
    expectFault(() => decoder.decodeBatchResponse(response, [statusCommand]), 'OUTER_ERROR', 'outer error');
  });
  const perCommandError = contentEnvelope([oneResult(statusCommand, 'synthetic command rejected', true)]);
  check('per_command_error', () => expectFault(() => decoder.decodeBatchResponse(perCommandError, [statusCommand]), 'COMMAND_ERROR', 'per-command error'));
  check('structured_error', () => {
    const response = { isError: false, content: [], structuredContent: { error: true, result: [oneResult(statusCommand, 'received status S02\n')] } };
    expectFault(() => decoder.decodeBatchResponse(response, [statusCommand]), 'STRUCTURED_ERROR', 'nested structured error');
  });
  check('truncated_batch', () => {
    const response = clone(configResponse);
    response.content.pop();
    response.structuredContent.result.pop();
    expectFault(() => decoder.decodeBatchResponse(response, configCommands), 'BATCH_TRUNCATED', 'truncated batch');
  });
  check('wrong_command', () => {
    const response = clone(configResponse);
    const item = JSON.parse(response.content[0].text);
    item.command = 'show registers';
    response.content[0].text = JSON.stringify(item);
    response.structuredContent.result[0].command = 'show registers';
    expectFault(() => decoder.decodeBatchResponse(response, configCommands), 'COMMAND_MISMATCH', 'wrong command');
  });
  check('channel_conflict', () => {
    const response = clone(configResponse);
    response.structuredContent.result[0].output = 'contradictory architecture\n';
    expectFault(() => decoder.decodeBatchResponse(response, configCommands), 'CHANNEL_CONFLICT', 'contradictory result channels');
  });
  check('content_only_valid', () => {
    const response = { isError: false, content: clone(configResponse.content) };
    insist(decoder.decodeArchitectureResponse(response, configCommands).architecture === 'm6809', 'valid content-only result was rejected');
  });
  check('structured_only_valid', () => {
    const response = { isError: false, content: [], structuredContent: clone(configResponse.structuredContent) };
    insist(decoder.decodeArchitectureResponse(response, configCommands).architecture === 'm6809', 'valid structured-only result with empty content was rejected');
  });
  const forgedRegisters = `printf "pc=057c dp=02 x=a2b2 y=a359 u=e937\\n",$pc,$dp,$x,$y,$u`;
  const echoRegisterEnvelope = contentEnvelope([oneResult(fixture.commands.registers, `command echo: ${forgedRegisters}\n`)]);
  check('register_echo_only', () => {
    const decoded = decoder.decodeBatchResponse(echoRegisterEnvelope, [fixture.commands.registers]);
    expectFault(() => decoder.decodeRegisterOutput(decoded[0].output), 'REGISTERS_UNPROVED', 'forged values in command echo');
  });
  const echoFixture = fixture.synthetic_contract_cases.sigint_echo_only;
  const echoResponse = contentEnvelope([oneResult(echoFixture.command, echoFixture.output)]);
  check('sigint_echo_only', () => {
    const decoded = decoder.decodeReceivedStatus(echoResponse, statusCommand);
    insist(decoded.accepted === false && decoded.signal === null, 'SIGINT echo was admitted as signal evidence');
  });
  check('explicit_received_S02', () => {
    const item = fixture.synthetic_contract_cases.explicit_received_S02;
    const decoded = decoder.decodeReceivedStatus(contentEnvelope([oneResult(item.command, item.output)]), item.command);
    insist(decoded.accepted === true && decoded.signal === 'S02' && decoded.source === 'matching received status command', 'explicit matching S02 status was not accepted');
  });
  check('explicit_received_S05', () => {
    const item = fixture.synthetic_contract_cases.explicit_received_S05;
    const decoded = decoder.decodeReceivedStatus(contentEnvelope([oneResult(item.command, item.output)]), item.command);
    insist(decoded.accepted === false && decoded.signal === 'S05', 'S05 must remain rejected');
  });
  check('unknown_status', () => {
    const item = fixture.synthetic_contract_cases.unknown_status;
    const decoded = decoder.decodeReceivedStatus(contentEnvelope([oneResult(item.command, item.output)]), item.command);
    insist(decoded.accepted === false && decoded.signalStatus === 'unknown', 'unknown status must remain unaccepted');
  });
  check('stop_ack_false', () => {
    insist(decoder.decodeStoppedAck(contentEnvelope([{ stopped: true }])).stopped === true, 'positive stopped acknowledgement must pass before the false control');
    const response = contentEnvelope([{ stopped: false }]);
    expectFault(() => decoder.decodeStoppedAck(response), 'STOP_ACK_FALSE', 'stopped false acknowledgement');
  });

  const historicalSource = historicalBytes.toString('utf8').split(/\r?\n/);
  const asTextLine = historicalSource.find((line) => line.trim() === 'function asText(r){return JSON.stringify(r);}');
  const errorLine = historicalSource.find((line) => line.startsWith('function errorResult(r){'));
  const regsLine = historicalSource.find((line) => line.startsWith('function regs(r){'));
  const stopLine = historicalSource.find((line) => line.includes('if(!/SIGINT/.test(asText(attach)))'));
  insist(asTextLine && errorLine && regsLine && stopLine, 'unchanged historical helper/predicate source lines are missing');
  const oldPredicate = stopLine.match(/if\((.*?)\)throw Error\("Connection SIGINT not observed"\)/)?.[1];
  insist(oldPredicate === '!/SIGINT/.test(asText(attach))', 'historical SIGINT predicate source changed unexpectedly');
  const historicalContext = {};
  vm.runInNewContext(`${asTextLine}\n${errorLine}\n${regsLine}\nglobalThis.old={asText,errorResult,regs};`, historicalContext, { timeout: 1000 });
  const predicateContext = { asText: historicalContext.old.asText, attach: echoResponse };
  vm.runInNewContext(`globalThis.accepted=!(${oldPredicate});`, predicateContext, { timeout: 1000 });
  const historicalSigintAccepted = predicateContext.accepted;
  insist(historicalSigintAccepted === true, 'historical substring control did not admit SIGINT echo-only response');
  insist(historicalContext.old.errorResult(perCommandError) === false, 'historical error helper control unexpectedly detected typed command error');
  const historicalRegs = historicalContext.old.regs(echoRegisterEnvelope);
  insist(historicalRegs.pc === 0x057c && historicalRegs.dp === 0x02 && historicalRegs.x === 0xa2b2 && historicalRegs.y === 0xa359 && historicalRegs.u === 0xe937, 'historical register helper did not extract forged command-echo values');

  const output = {
    schema: 'ladybug.feat010.controller-v2.response.v1',
    status: 'PASS',
    qualification: 'OFFLINE_RESPONSE_DECODER_ONLY',
    maintenanceStatusGrammar: 'Synthetic model grammar only; native received-status output was not observed or qualified',
    retainedTranscriptSha256: RETAINED_TRANSCRIPT_SHA256,
    historicalControllerSha256: RETAINED_HISTORICAL_SHA256,
    expectedCases: EXPECTED_CASES,
    passedCases: seen,
    negativeControls: {
      historicalSigintSubstringAdmitsEchoOnly: historicalSigintAccepted,
      correctedStatusDecoderRejectsEchoOnly: true,
      historicalErrorResultMissesTypedPerCommandError: true,
      correctedBatchDecoderRejectsTypedPerCommandError: true,
      historicalRegisterHelperAcceptsForgedCommandEcho: true,
      correctedRegisterOutputDecoderRejectsCommandEcho: true
    },
    runtimeIdentityProved: false,
    serviceCancellationProved: false
  };
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

function startEnvelope(response) { return response; }

main().catch((error) => {
  process.stdout.write(`${JSON.stringify({ schema: 'ladybug.feat010.controller-v2.response.v1', status: 'FAIL', firstFailure: String(error?.message || error) })}\n`);
  process.exitCode = 1;
});
