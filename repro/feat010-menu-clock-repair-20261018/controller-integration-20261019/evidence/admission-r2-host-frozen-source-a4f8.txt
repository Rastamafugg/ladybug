param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('stop-observation-admission', 'stop-observation-reader', 'stop-observation-compatibility')]
    [string]$Phase
)

$ErrorActionPreference = 'Stop'
$script:Clock = [System.Diagnostics.Stopwatch]::StartNew()
$script:Root = $PSScriptRoot
$script:ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$script:EvidenceDirectory = Join-Path $PSScriptRoot 'evidence'
$script:FreezePath = Join-Path $PSScriptRoot 'integration-freeze.json'
$script:FileScalarDescriptorPath = Join-Path $PSScriptRoot 'evidence\sro-qualification-case-contract.json'
$script:FileScalarDescriptorSha256 = '493ffe9524977bb07376f55ef521a4d5e691539be5b7624f6194bab2d36043c0'
$script:MaximumHostJsonBytes = 16777216
$script:MaximumHostJsonUnits = 16777216
$script:HostReadChunkBytes = 4096
$script:TicketPath = Join-Path $script:ProjectRoot 'wiki\internal\tickets\feat-010-attract-menu-free-start.html'
$script:TranscriptPath = Join-Path $script:ProjectRoot 'repro\feat010-menu-clock-repair-20261018\stutter-runtime-gdb-transcript.json'
$script:QualifiedRoot = Join-Path $script:ProjectRoot 'repro\feat010-menu-clock-repair-20261018\controller-service-lease-c16-fixture-recovery-20261019'
$script:PythonPath = '/home/rastamafugg/.local/share/uv/tools/gdb-mcp/bin/python'
$script:PythonResolved = '/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12'
$script:PythonSha256 = '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900'
$script:TranscriptSha256 = '1617ba0bde61ca2bafe2d4603ae5d8f295c21b8efd3ef921d3f092b7560fef20'
$script:SourcePaths = @('service/gdb.py', 'service/server.py', 'stop-q.py', 'run-integration-q.ps1')
$script:FixturePaths = @(
    'evidence/sro-qualification-case-contract.json',
    'evidence/sro-baseline-independent-fixtures.json',
    'evidence/sro-stop-independent-fixtures.json',
    'evidence/sro-natural-sequence-fixture.json',
    'evidence/sro-producer-literal-fixture.json'
)
$script:ReadInputPaths = @('stutter-runtime-gdb-transcript.json')
$script:QualifiedInputPaths = @(
    'baseline/gdb.py.txt', 'baseline/server.py.txt', 'candidate/gdb.py', 'candidate/server.py',
    'service-q.py', 'run-service-q.ps1', 'service-q-freeze.json'
)
$script:PhaseOrder = @('stop-observation-admission', 'stop-observation-reader', 'stop-observation-compatibility')
$script:PhaseLimits = @{
    'stop-observation-admission' = 30000
    'stop-observation-reader' = 60000
    'stop-observation-compatibility' = 60000
}
$script:PhaseCaseIds = @{
    'stop-observation-admission' = @('Q01', 'Q02', 'Q03', 'Q04', 'Q05')
    'stop-observation-reader' = @('R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07', 'R08', 'R09', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15', 'R16')
    'stop-observation-compatibility' = @('C01', 'C02', 'C03', 'C04', 'C05', 'C06')
}
$script:HostOracleRowIds = @(
    'READY_VALID', 'READY_WRONG_NONCE', 'READY_WRONG_MANIFEST', 'READY_WRONG_SOURCE', 'READY_WRONG_FIXTURE', 'READY_WRONG_READ_INPUT', 'READY_WRONG_TICKET', 'READY_BOOL_ELAPSED', 'READY_MISSING_IDENTITY',
    'TERMINAL_VALID', 'TERM_FAIL_UNCONFIRMED_NULL_EXIT', 'TERM_FAIL_UNCONFIRMED_ZERO_EXIT', 'TERM_WRONG_NONCE', 'TERM_WRONG_PHASE', 'TERM_WORKER_WAIT_FALSE', 'TERM_WORKER_BOOL_EXIT', 'TERM_WORKER_NONZERO_EXIT', 'TERM_MISSING_WORKER_EXIT', 'TERM_MISSING_WORKER_RETURN', 'TERM_MISSING_CASE', 'TERM_DUPLICATE_CASE', 'TERM_WRONG_CASE_ORDER', 'TERM_MISSING_SUBCONTROL', 'TERM_DUPLICATE_SUBCONTROL', 'TERM_BOOL_COUNTER', 'TERM_REAL_CALL', 'TERM_PRESERVATION_MISMATCH', 'TERM_OVER_DEADLINE', 'TERM_MISSING_OUTER_FIELD',
    'FINAL_VALID', 'FINAL_DRIVER_WAIT_FALSE', 'FINAL_DRIVER_BOOL_EXIT', 'FINAL_DRIVER_NONZERO_EXIT', 'FINAL_MISSING_DRIVER_WAIT', 'FINAL_MISSING_DRIVER_CODE', 'FINAL_CLEANUP_FALSE', 'FINAL_EVIDENCE_NOT_FINAL', 'FINAL_MISSING_FINALIZATION', 'FINAL_OVER_DEADLINE',
    'FINAL_C06_VALID', 'FINAL_C06_MISSING', 'FINAL_C06_WORKER_WAIT_FALSE', 'FINAL_C06_DRIVER_WAIT_FALSE', 'FINAL_C06_MISSING_CONTROL', 'FINAL_C06_DUPLICATE_CONTROL', 'FINAL_C06_PRESERVATION_FALSE',
    'JSON_UNIQUE_VALID', 'JSON_DUPLICATE_KEY', 'JSON_ESCAPED_DUPLICATE_KEY', 'JSON_NESTED_DUPLICATE_KEY', 'JSON_MALFORMED',
    'PREV_VALID', 'PREV_MISSING_READY', 'PREV_MISSING_CASE', 'PREV_MISSING_HOST_ORACLE', 'PREV_ALTERED_CLAIM_NONCE', 'PREV_ALTERED_TERMINAL_BINDING', 'PREV_ALTERED_FINAL_ADMISSION', 'PREV_ALTERED_HOST_ORACLE', 'PREV_DUPLICATE_HOST_ORACLE',
    'CLAIM_VALID', 'CLAIM_CHANGED_ARGUMENT', 'CLAIM_CHANGED_PATH',
    'READY_EXTRA_FIELD', 'READY_FLOAT_ELAPSED', 'TERM_EXTRA_FIELD', 'TERM_FLOAT_PHASE_ELAPSED', 'FINAL_FLOAT_ELAPSED',
    'PREV_JSON_TIMESTAMP_ROUNDTRIP', 'PREV_JSON_TIMESTAMP_TYPED_NEGATIVE',
    'STREAM_STDOUT_PROTOCOL_OVERSIZE_NO_NEWLINE', 'STREAM_STDERR_CAP_NO_NEWLINE', 'STREAM_STDOUT_TAIL_OVERSIZE_NO_NEWLINE',
    'FINAL_POSTWRITE_ADMISSION_FAILURE', 'FINAL_MARKER_WRITE_FAILURE_NONZERO', 'CLAIM_COLLISION_PRESERVES_BYTES',
    'FILE_EXACT_CAP', 'FILE_OVER_CAP_STOP', 'FILE_UTF8_SPLIT_BOM', 'FILE_UTF8_INVALID', 'FILE_EMPTY_JSON_REJECT',
    'STR_FREEZE_FIELDS', 'STR_READY_FIELDS', 'STR_TERMINAL_FIELDS', 'STR_CASE_FIELDS', 'STR_SUBCONTROL_FIELDS',
    'STR_ORACLE_FIELDS', 'STR_C06_FIELDS', 'STR_FINAL_FIELDS', 'STR_RETAINED_FIELDS'
)
$script:WorkerCaseIds = @{
    'stop-observation-admission' = @('Q01', 'Q02', 'Q03', 'Q04', 'Q05')
    'stop-observation-reader' = @('R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07', 'R08', 'R09', 'R10', 'R11', 'R12', 'R13', 'R14', 'R15', 'R16')
    'stop-observation-compatibility' = @('C01', 'C02', 'C03', 'C04', 'C05')
}
$script:ExpectedByCase = @{
    Q01 = 'ORACLE_DISCRIMINATES'; Q02 = 'REJECT_NATIVE_UNKNOWN_SIGNAL'; Q03 = 'IDENTICAL_SESSION_EVENT_ONLY'; Q04 = 'ADMISSION_EXCLUSIVE_AND_CONTAINED'; Q05 = 'BASELINE_ORACLE_DISCRIMINATES'
    R01 = 'VALIDATED_OBSERVATIONS_AND_BOTH_EXITS'; R02 = 'MISSING_CAPABILITY_NOT_SETUP_FAILURE'; R03 = 'EXACT_SINGLE_CALL_TYPED_PAYLOAD'; R04 = 'ONLY_STRICT_BOUND_INTEGER_ZERO_ACCEPTED'
    R05 = 'NO_RETROACTIVE_ADMISSION'; R06 = 'NO_FALSE_RESULT_OR_STOP_PROOF'; R07 = 'UNKNOWN_ATTACH_AND_VALID_BREAKPOINT'; R08 = 'NO_VALIDATED_STOP'
    R09 = 'NO_VALIDATED_STOP'; R10 = 'VALIDATED_OBSERVATION'; R11 = 'NO_VALIDATED_STOP'; R12 = 'FRESH_CLAIM_ONLY_ZERO_LEGACY_WRITES_ONE_READER'
    R13 = 'TAINT_RETAIN_FAILURE_NO_EVICTION'; R14 = 'NO_LATE_ADMISSION_ONE_ENCLOSING_DEADLINE'; R15 = 'OWNER_ADDRESSABLE_INVALIDATED_CLEANUP'
    R16 = 'PROCESS_TRUE_READER_FALSE_CLEANUP_FALSE_RETAIN_HANDLE'; C01 = 'UNCHANGED_SCHEMA_INTEGER_WAIT_ZERO_COUNTERS'; C02 = 'RAISE_RETAIN_REGISTRY_NO_FALSE_EXIT'
    C03 = 'UNCHANGED_RESPONSE_AND_TIMEOUT_CONTRACT'; C04 = 'SEPARATE_EXITS_NO_REVIVAL_NO_SECOND_READER'; C05 = 'NO_OBSERVER_CREATED'; C06 = 'DIRECT_EXITS_CONFIRMED_NO_REAL_SUBJECT'
}
$script:FailureCategories = @('ASSERTION','SETUP','TIMEOUT','CONTAINMENT','PROTOCOL','INTERNAL','MISSING_COVERAGE','CLEANUP')
$script:CaseSubcontrols = @{
    Q01 = @('valid','owner','session','generation','token','sequence','boolean','mi_error','current_state','cause_id','coherent_copy','command','nested_generation','nested_type','error_code','overflow_evidence','extra_field','float')
    Q02 = @('capture_hash','formatted_attach_is_unknown','no_native_signal_field')
    Q03 = @('same_raw_event','different_hypothetical_cause','same_event_only_classification')
    Q04 = @('exclusive_claim','collision_preserved','pinned_allowlist','popen_type_preserved','popen_denied','no_real_factory','changed_argument_rejected','changed_path_rejected')
    Q05 = @('baseline-zero','baseline-connection','baseline-bool','baseline-string','baseline-null','baseline-missing','baseline-nonce','baseline-owner','baseline-session','baseline-generation','baseline-stream','baseline-duplicate','baseline-malformed','baseline-truncated','baseline-python','baseline-api','baseline-mi-error','baseline-token','baseline-invalidated')
    R01 = @('startup','claim','baseline','attach','fresh_attach_state','pre_continue_state','breakpoint','continue','fresh_continue_state','reader_count','raw_count','process_exit','reader_exit','no_cause_claim','exception_before_call_capture_cleanup','exception_after_call_capture_cleanup','token_and_prompt_text','tokenized_error_text','console_stream_text','stop_text')
    R02 = @('historical_source_pin','missing_claim_api','missing_exec_api','missing_stop_api','not_setup_failure')
    R03 = @('literal_hash','empty_connections_once','one_connection_once','exact_zero_stdout','exact_one_stdout','module_restored','no_io','module_replacement_rejected','module_removal_rejected')
    R04 = @('baseline-control-zero','baseline-control-connection','baseline-control-bool','baseline-control-string','baseline-control-null','baseline-control-missing','baseline-control-nonce','baseline-control-owner','baseline-control-session','baseline-control-generation','baseline-control-stream','baseline-control-duplicate','baseline-control-malformed','baseline-control-truncated','baseline-control-python','baseline-control-api','baseline-control-mi-error','baseline-control-token','baseline-control-invalidated')
    R05 = @('preclaim_user_send','preclaim_interrupt','stale_stop','buffered_output','no_retroactive_claim')
    R06 = @('wrong_token','duplicate_result','pre_result_prompt','mi_error','no_validated_result','connected_without_separator_valid','empty_payload_rejected','oversized_result_protocol_partial')
    R07 = @('attach_missing_sigint_unknown','continue_without_signal_valid_breakpoint','event_only')
    R08 = @('wrong_breakpoint','disabled_breakpoint','missing_breakpoint','missing_query','no_continue_write')
    R09 = @('wrong_hit_number','wrong_thread','wrong_pc','running_state','unsupported_state','generation_change')
    R10 = @('enabled_pre_resume','expected_disposition','deleted_after_hit_allowed','fresh_pc')
    R11 = @('multiple_stops_ambiguous','delayed_event_after_invalidation','wrong_owner_no_write')
    R12 = @('activity_before_claim','claim_pending_gate','postclaim_send_rejected','postclaim_interrupt_rejected','repeat_claim','single_reader','zero_legacy_delta')
    R13 = @('record_cap','byte_cap','tainted','first_overflow_retained','no_eviction')
    R14 = @('operation_lock','transaction_lock','drain','read','query','no_late_admission')
    R15 = @('lost_claim_reply','owner_retained','pending_command_invalidated','cleanup_confirmed','late_reply_no_revival')
    R16 = @('process_exit_true','reader_exit_false','cleanup_false','registry_retained','later_reader_join')
    C01 = @('legacy_start_schema','legacy_send','legacy_stop_schema','wait_integer_zero','no_escalation')
    C02 = @('legacy_response_schema','unknown_stop','unresolved_raises','registry_retained','fixture_released')
    C03 = @('one_command_write','one_deadline','timeout_result','no_late_write')
    C04 = @('claimed_close_invalidates','late_reply_rejected','repeat_stop_idempotent','one_reader','separate_exit_truth')
    C05 = @('prestart_tombstone','delayed_start_rejected','zero_factory','no_observer_reference')
    C06 = @('worker_wait_confirmed','worker_exit_zero','wsl_wait_confirmed','wsl_exit_zero','preservation_equal')
}
$script:LaunchArgv = @('wsl.exe', '--exec', $script:PythonPath, '-B', '/mnt/e/projects/ladybug/repro/feat010-menu-clock-repair-20261018/controller-integration-20261019/stop-q.py', '--supervisor')
$script:GoReserveMs = 10000
$script:DriverWaitReserveMs = 2500
$script:EvidenceReserveMs = 1500
$script:ProtocolLineMaximumCharacters = 262144
$script:ProtocolLineMaximumBytes = 262144
$script:Driver = $null
$script:DriverStarted = $false
$script:DriverIdentity = $null
$script:StdoutState = $null
$script:StderrState = $null
$script:DriverStreamCapture = [pscustomobject]@{ stdout = $null; stderr = $null }
$script:ProtocolRecords = New-Object System.Collections.ArrayList
$script:ProtocolLines = New-Object System.Collections.ArrayList
$script:FailureCategory = $null
$script:FailureMessage = $null
$script:FailureDetail = $null
$script:TransportFailureCategory = $null
$script:TransportFailureMessage = $null
$script:TransportFailureDetail = $null
$script:Freeze = $null
$script:Execution = $null
$script:ManifestSha256 = $null
$script:TicketSha256 = $null
$script:SourceSha256 = [ordered]@{}
$script:FixtureSha256 = [ordered]@{}
$script:ReadInputsSha256 = [ordered]@{}
$script:HostBefore = $null
$script:HostAfter = $null
$script:HostRuntime = $null
$script:EvidenceNamePrefix = 'admission-r2-'
$script:ClaimPath = Join-Path $script:EvidenceDirectory ($script:EvidenceNamePrefix + $Phase + '.claim')
$script:ReceiptPath = Join-Path $script:EvidenceDirectory ($script:EvidenceNamePrefix + $Phase + '.json')
$script:OverrunPath = Join-Path $script:EvidenceDirectory ($script:EvidenceNamePrefix + $Phase + '-overrun.json')
$script:ClaimCreated = $false
$script:DriverExitConfirmed = $false
$script:DriverExitCode = $null
$script:GoBudgetMs = $null
$script:ReadyRecord = $null
$script:TerminalRecord = $null
$script:HostClaim = $null
$script:PhaseNonce = $null
$script:ClaimCollision = $null
$script:StderrText = ''
$script:StdoutTail = ''
$script:StdoutReadPending = $false
$script:DriverStreamsDrained = $false
$script:HostCases = @()
$script:HostOracle = @()
$script:PreservationError = $null
$script:FileScalarDescriptor = $null
$script:BoundedReadFailures = New-Object System.Collections.ArrayList

function Get-PropertyNames {
    param([object]$Value)
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [System.Array]) { return @() }
    return @($Value.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
}

function Test-ObjectShape {
    param([object]$Value, [string[]]$Names)
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [System.Array]) { return $false }
    $actual = @(Get-PropertyNames $Value)
    $expected = @($Names | Sort-Object)
    if ($actual.Count -ne $expected.Count) { return $false }
    for ($i = 0; $i -lt $expected.Count; $i++) { if ($actual[$i] -cne $expected[$i]) { return $false } }
    return $true
}

function Test-HasProperties {
    param([object]$Value, [string[]]$Names)
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [System.Array]) { return $false }
    foreach ($name in $Names) { if ($null -eq $Value.PSObject.Properties[$name]) { return $false } }
    return $true
}

function Test-ExactInteger {
    param([object]$Value)
    if ($null -eq $Value -or $Value -is [bool]) { return $false }
    return ($Value -is [int] -or $Value -is [long])
}

function Test-ExactBoolean {
    param([object]$Value)
    return ($Value -is [bool])
}

function Test-Sha256 {
    param([object]$Value)
    return ($Value -is [string] -and $Value -cmatch '^[0-9a-f]{64}$')
}

function Test-HashObject {
    param([object]$Actual, [object]$Expected)
    if ($null -eq $Actual -or $Actual -is [string] -or $Actual -is [System.Array] -or $null -eq $Expected) { return $false }
    $expectedNames = @(Get-PropertyNames $Expected)
    $actualNames = @(Get-PropertyNames $Actual)
    if ($expectedNames.Count -ne $actualNames.Count) { return $false }
    for ($i = 0; $i -lt $expectedNames.Count; $i++) {
        $name = $expectedNames[$i]
        if ($actualNames[$i] -cne $name) { return $false }
        $left = $Actual.PSObject.Properties[$name].Value
        $right = $Expected.PSObject.Properties[$name].Value
        if ($left -isnot [string] -or $right -isnot [string] -or $left -cne $right) { return $false }
    }
    return $true
}

function Test-JsonValueEqual {
    param([object]$Left, [object]$Right)
    if ($null -eq $Left -or $null -eq $Right) { return ($null -eq $Left -and $null -eq $Right) }
    if ($Left -is [System.Array] -or $Right -is [System.Array]) {
        if ($Left -isnot [System.Array] -or $Right -isnot [System.Array]) { return $false }
        $leftItems = @($Left); $rightItems = @($Right)
        if ($leftItems.Count -ne $rightItems.Count) { return $false }
        for ($i = 0; $i -lt $leftItems.Count; $i++) { if (-not (Test-JsonValueEqual $leftItems[$i] $rightItems[$i])) { return $false } }
        return $true
    }
    if ((Test-ExactInteger $Left) -or (Test-ExactInteger $Right)) {
        return ((Test-ExactInteger $Left) -and (Test-ExactInteger $Right) -and [long]$Left -eq [long]$Right)
    }
    if ($Left -is [string] -or $Right -is [string] -or $Left -is [bool] -or $Right -is [bool]) {
        return ($Left.GetType() -eq $Right.GetType() -and $Left -ceq $Right)
    }
    if ($Left -is [ValueType] -or $Right -is [ValueType]) {
        return ($Left.GetType() -eq $Right.GetType() -and $Left -eq $Right)
    }
    $leftNames = @(Get-PropertyNames $Left); $rightNames = @(Get-PropertyNames $Right)
    if ($leftNames.Count -ne $rightNames.Count) { return $false }
    for ($i = 0; $i -lt $leftNames.Count; $i++) {
        if ($leftNames[$i] -cne $rightNames[$i]) { return $false }
        if (-not (Test-JsonValueEqual $Left.PSObject.Properties[$leftNames[$i]].Value $Right.PSObject.Properties[$rightNames[$i]].Value)) { return $false }
    }
    return $true
}

function Test-StringArray {
    param([object]$Value, [string[]]$Expected)
    if ($Value -isnot [System.Array]) { return $false }
    $items = @($Value)
    if ($items.Count -ne $Expected.Count) { return $false }
    for ($i = 0; $i -lt $Expected.Count; $i++) { if ($items[$i] -isnot [string] -or $items[$i] -cne $Expected[$i]) { return $false } }
    return $true
}

function Test-Identity {
    param([object]$Value)
    if (-not (Test-ObjectShape $Value @('pid','start_ticks','executable','executable_sha256'))) { return $false }
    if (-not (Test-ExactInteger $Value.pid) -or $Value.pid -le 0 -or -not (Test-ExactInteger $Value.start_ticks) -or $Value.start_ticks -le 0) { return $false }
    return ($Value.executable -is [string] -and $Value.executable -ceq $script:PythonResolved -and $Value.executable_sha256 -is [string] -and $Value.executable_sha256 -ceq $script:PythonSha256)
}

function Test-IdentityEqual {
    param([object]$Left, [object]$Right)
    if (-not (Test-Identity $Left) -or -not (Test-Identity $Right)) { return $false }
    return ($Left.pid -eq $Right.pid -and $Left.start_ticks -eq $Right.start_ticks -and $Left.executable -ceq $Right.executable -and $Left.executable_sha256 -ceq $Right.executable_sha256)
}

function Test-MapKeysAndHashes {
    param([object]$Value, [string[]]$ExpectedNames)
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [System.Array]) { return $false }
    $names = @(Get-PropertyNames $Value)
    $expected = @($ExpectedNames | Sort-Object)
    if ($names.Count -ne $expected.Count) { return $false }
    for ($i = 0; $i -lt $expected.Count; $i++) {
        if ($names[$i] -cne $expected[$i] -or -not (Test-Sha256 $Value.PSObject.Properties[$expected[$i]].Value)) { return $false }
    }
    return $true
}

function Test-FreezeEnvelope {
    param([object]$Value, [ref]$Reason)
    $Reason.Value = 'freeze envelope rejected'
    if (-not (Test-HasProperties $Value @('schema','status','runtime_ready','runtime_attempts_authorized','installation_authorized','qualification_dispatch_authorized','python','protected_count','protected_files_sha256','qualified_service_root','qualified_seven_inputs_sha256','execution_freeze'))) { return $false }
    if ($Value.schema -isnot [string] -or $Value.status -isnot [string] -or $Value.python.path -isnot [string] -or $Value.python.resolved -isnot [string] -or $Value.python.sha256 -isnot [string] -or $Value.qualified_service_root -isnot [string]) { return $false }
    if ($Value.schema -cne 'ladybug.feat010.controller-integration.freeze.v1' -or $Value.runtime_ready -isnot [bool] -or $Value.runtime_ready -ne $false -or -not (Test-ExactInteger $Value.runtime_attempts_authorized) -or $Value.runtime_attempts_authorized -ne 0 -or $Value.installation_authorized -isnot [bool] -or $Value.installation_authorized -ne $false) { return $false }
    if ($Value.qualification_dispatch_authorized -isnot [bool] -or $Value.qualification_dispatch_authorized -ne $true) { return $false }
    if (-not (Test-HasProperties $Value @('recovery_preflight'))) { return $false }
    $hostPins = $Value.recovery_preflight
    if (-not (Test-HasProperties $hostPins @('host_path','host_sha256','ps_version','wsl_path','wsl_sha256')) -or
        $hostPins.host_path -isnot [string] -or $hostPins.host_path.Length -eq 0 -or -not (Test-Sha256 $hostPins.host_sha256) -or
        $hostPins.ps_version -isnot [string] -or $hostPins.ps_version.Length -eq 0 -or
        $hostPins.wsl_path -isnot [string] -or $hostPins.wsl_path.Length -eq 0 -or -not (Test-Sha256 $hostPins.wsl_sha256)) { return $false }
    if (-not (Test-ObjectShape $Value.python @('path','resolved','sha256')) -or $Value.python.path -cne $script:PythonPath -or $Value.python.resolved -cne $script:PythonResolved -or $Value.python.sha256 -cne $script:PythonSha256) { return $false }
    if (-not (Test-ExactInteger $Value.protected_count) -or $Value.protected_count -ne 199 -or $null -eq $Value.protected_files_sha256) { return $false }
    $protectedNames = @(Get-PropertyNames $Value.protected_files_sha256)
    if ($protectedNames.Count -ne 199 -or -not (Test-MapKeysAndHashes $Value.protected_files_sha256 $protectedNames)) { return $false }
    foreach ($protectedPath in $protectedNames) { if ($protectedPath -notmatch '^(?i:E:/projects/ladybug/|E:\\projects\\ladybug\\)') { return $false } }
    if ($Value.qualified_service_root -isnot [string] -or [System.IO.Path]::GetFullPath($Value.qualified_service_root) -cne [System.IO.Path]::GetFullPath($script:QualifiedRoot)) { return $false }
    if (-not (Test-MapKeysAndHashes $Value.qualified_seven_inputs_sha256 $script:QualifiedInputPaths)) { return $false }
    $execution = $Value.execution_freeze
    if (-not (Test-ObjectShape $execution @('authorized','source_sha256','fixture_sha256','read_inputs_sha256','ticket_sha256','phases')) -or $execution.authorized -isnot [bool] -or $execution.authorized -ne $true) { return $false }
    if (-not (Test-MapKeysAndHashes $execution.source_sha256 $script:SourcePaths) -or -not (Test-MapKeysAndHashes $execution.fixture_sha256 $script:FixturePaths) -or -not (Test-MapKeysAndHashes $execution.read_inputs_sha256 $script:ReadInputPaths) -or -not (Test-Sha256 $execution.ticket_sha256)) { return $false }
    if (-not (Test-ObjectShape $execution.phases $script:PhaseOrder)) { return $false }
    $freezeCaseIds = @{
        'stop-observation-admission' = $script:PhaseCaseIds['stop-observation-admission']
        'stop-observation-reader' = $script:PhaseCaseIds['stop-observation-reader']
        'stop-observation-compatibility' = $script:PhaseCaseIds['stop-observation-compatibility']
    }
    foreach ($name in $script:PhaseOrder) {
        $phase = $execution.phases.PSObject.Properties[$name].Value
        if (-not (Test-ObjectShape $phase @('maximum_ms','attempts','case_ids')) -or -not (Test-ExactInteger $phase.maximum_ms) -or $phase.maximum_ms -ne $script:PhaseLimits[$name] -or -not (Test-ExactInteger $phase.attempts) -or $phase.attempts -ne 1 -or -not (Test-StringArray $phase.case_ids $freezeCaseIds[$name])) { return $false }
    }
    $Reason.Value = $null
    return $true
}

function Test-HostClaim {
    param([object]$Claim)
    if (-not (Test-ObjectShape $Claim @('exclusive','collision_preserved','launch_argv'))) { return $false }
    if ($Claim.exclusive -isnot [bool] -or $Claim.exclusive -ne $true -or $Claim.collision_preserved -isnot [bool] -or $Claim.collision_preserved -ne $true) { return $false }
    return (Test-StringArray $Claim.launch_argv $script:LaunchArgv)
}

function Test-AdmissionEnvelope {
    param([object]$Record, [string]$ExpectedPhase, [string]$Nonce, [string]$Manifest, [string]$Ticket, [object]$Sources, [object]$Fixtures, [object]$ReadInputs, [int]$MaximumMs, [ref]$Reason)
    $Reason.Value = 'READY rejected'
    $keys = @('kind','phase','nonce','manifest_sha256','ticket_sha256','source_sha256','fixture_sha256','read_inputs_sha256','supervisor_identity','supervisor_elapsed_ms')
    if (-not (Test-ObjectShape $Record $keys)) { return $false }
    foreach ($name in @('kind','phase','nonce','manifest_sha256','ticket_sha256')) { if ($Record.PSObject.Properties[$name].Value -isnot [string]) { return $false } }
    if ($Record.kind -cne 'READY' -or $Record.phase -cne $ExpectedPhase -or $Record.nonce -cne $Nonce -or $Record.manifest_sha256 -cne $Manifest -or $Record.ticket_sha256 -cne $Ticket) { return $false }
    if (-not (Test-HashObject $Record.source_sha256 $Sources) -or -not (Test-HashObject $Record.fixture_sha256 $Fixtures) -or -not (Test-HashObject $Record.read_inputs_sha256 $ReadInputs)) { return $false }
    if (-not (Test-Identity $Record.supervisor_identity) -or -not (Test-ExactInteger $Record.supervisor_elapsed_ms) -or $Record.supervisor_elapsed_ms -lt 0 -or $Record.supervisor_elapsed_ms -gt $MaximumMs) { return $false }
    $Reason.Value = $null
    return $true
}

function Test-SubcontrolRows {
    param([object]$Case, [string]$CaseId, [bool]$Complete)
    if ($null -eq $Case.observations -or $Case.observations -is [string] -or $Case.observations -is [System.Array]) { return $false }
    $controlsProperty = $Case.observations.PSObject.Properties['subcontrols']
    if ($null -eq $controlsProperty) { return (-not $Complete) }
    if ($controlsProperty.Value -isnot [System.Array]) { return $false }
    $controls = @($controlsProperty.Value)
    $expected = @($script:CaseSubcontrols[$CaseId])
    if ($Complete -and $controls.Count -ne $expected.Count) { return $false }
    if (-not $Complete -and $controls.Count -gt $expected.Count) { return $false }
    for ($i = 0; $i -lt $controls.Count; $i++) {
        $control = $controls[$i]
        if (-not (Test-ObjectShape $control @('id','status','observed')) -or $control.id -isnot [string] -or $control.status -isnot [string] -or $control.id -cne $expected[$i] -or ($control.status -cne 'PASS' -and ($Complete -or $control.status -cne 'FAIL'))) { return $false }
    }
    return $true
}

function Test-PreservationSnapshot {
    param([object]$Value)
    $keys = @('source_sha256','fixture_sha256','read_inputs_sha256','ticket_sha256','manifest_sha256','protected_files_sha256','qualified_seven_inputs_sha256','python_sha256')
    if (-not (Test-ObjectShape $Value $keys)) { return $false }
    $protectedNames = @(Get-PropertyNames $Value.protected_files_sha256)
    return ((Test-MapKeysAndHashes $Value.source_sha256 $script:SourcePaths) -and
        (Test-MapKeysAndHashes $Value.fixture_sha256 $script:FixturePaths) -and
        (Test-MapKeysAndHashes $Value.read_inputs_sha256 $script:ReadInputPaths) -and
        (Test-Sha256 $Value.ticket_sha256) -and (Test-Sha256 $Value.manifest_sha256) -and
        (Test-Sha256 $Value.python_sha256) -and ($protectedNames.Count -eq 199) -and
        (Test-MapKeysAndHashes $Value.protected_files_sha256 $protectedNames) -and
        (Test-MapKeysAndHashes $Value.qualified_seven_inputs_sha256 $script:QualifiedInputPaths))
}

function Test-PreservationEqual {
    param([object]$Left, [object]$Right)
    if (-not (Test-PreservationSnapshot $Left) -or -not (Test-PreservationSnapshot $Right)) { return $false }
    foreach ($name in @('source_sha256','fixture_sha256','read_inputs_sha256','protected_files_sha256','qualified_seven_inputs_sha256')) {
        if (-not (Test-HashObject $Left.PSObject.Properties[$name].Value $Right.PSObject.Properties[$name].Value)) { return $false }
    }
    foreach ($name in @('ticket_sha256','manifest_sha256','python_sha256')) {
        if ($Left.PSObject.Properties[$name].Value -cne $Right.PSObject.Properties[$name].Value) { return $false }
    }
    return $true
}

function Test-TerminalRecord {
    param([object]$Record, [string]$ExpectedPhase, [string]$Nonce, [string]$Manifest, [string]$Ticket, [object]$Sources, [object]$Fixtures, [object]$ReadInputs, [object]$Supervisor, [int]$MaximumMs, [ref]$Reason)
    $Reason.Value = 'TERMINAL rejected'
    $outer = @('kind','phase','nonce','manifest_sha256','ticket_sha256','source_sha256','fixture_sha256','read_inputs_sha256','status','phase_elapsed_ms','supervisor_identity','worker_identity','worker_exit','cases','ledgers','preservation','failure')
    if (-not (Test-ObjectShape $Record $outer)) { return $false }
    foreach ($name in @('kind','phase','nonce','manifest_sha256','ticket_sha256','status')) { if ($Record.PSObject.Properties[$name].Value -isnot [string]) { return $false } }
    if ($Record.kind -cne 'TERMINAL' -or $Record.phase -cne $ExpectedPhase -or $Record.nonce -cne $Nonce -or $Record.manifest_sha256 -cne $Manifest -or $Record.ticket_sha256 -cne $Ticket) { return $false }
    if (-not (Test-HashObject $Record.source_sha256 $Sources) -or -not (Test-HashObject $Record.fixture_sha256 $Fixtures) -or -not (Test-HashObject $Record.read_inputs_sha256 $ReadInputs)) { return $false }
    if ($Record.status -cne 'SUBJECT_COMPLETE' -and $Record.status -cne 'FAIL') { return $false }
    if (-not (Test-ExactInteger $Record.phase_elapsed_ms) -or $Record.phase_elapsed_ms -lt 0 -or $Record.phase_elapsed_ms -gt $MaximumMs) { return $false }
    if (-not (Test-IdentityEqual $Record.supervisor_identity $Supervisor) -or -not (Test-Identity $Record.worker_identity) -or $Record.worker_identity.pid -eq $Record.supervisor_identity.pid) { return $false }
    if (-not (Test-ObjectShape $Record.worker_exit @('wait_confirmed','returncode')) -or -not (Test-ExactBoolean $Record.worker_exit.wait_confirmed)) { return $false }
    if ($Record.worker_exit.wait_confirmed) {
        if (-not (Test-ExactInteger $Record.worker_exit.returncode)) { return $false }
    } elseif ($null -ne $Record.worker_exit.returncode) { return $false }
    $ledgerNames = @('service_calls','factory_calls','reader_count','raw_record_count','real_factory_calls','real_gdb_calls','real_network_calls')
    $ledger = $Record.ledgers
    if (-not (Test-ObjectShape $ledger $ledgerNames) -or $ledger.service_calls -isnot [System.Array] -or $ledger.factory_calls -isnot [System.Array]) { return $false }
    foreach ($counter in @('reader_count','raw_record_count','real_factory_calls','real_gdb_calls','real_network_calls')) {
        if (-not (Test-ExactInteger $ledger.PSObject.Properties[$counter].Value) -or $ledger.PSObject.Properties[$counter].Value -lt 0) { return $false }
    }
    if ($ledger.real_factory_calls -ne 0 -or $ledger.real_gdb_calls -ne 0 -or $ledger.real_network_calls -ne 0) { return $false }
    if (-not (Test-ObjectShape $Record.preservation @('before','after')) -or -not (Test-PreservationSnapshot $Record.preservation.before) -or -not (Test-PreservationSnapshot $Record.preservation.after) -or -not (Test-PreservationEqual $Record.preservation.before $Record.preservation.after)) { return $false }
    if ($Record.failure -ne $null) {
        if (-not (Test-ObjectShape $Record.failure @('category','case_id','subcontrol','message','observed'))) { return $false }
        if ($Record.failure.category -isnot [string] -or $script:FailureCategories -cnotcontains $Record.failure.category -or $Record.failure.message -isnot [string]) { return $false }
        if ($null -eq $Record.failure.case_id) {
            if ($null -ne $Record.failure.subcontrol) { return $false }
        } else {
            if ($Record.failure.case_id -isnot [string] -or $Record.failure.subcontrol -isnot [string] -or $script:WorkerCaseIds[$ExpectedPhase] -cnotcontains $Record.failure.case_id -or $script:CaseSubcontrols[$Record.failure.case_id] -cnotcontains $Record.failure.subcontrol) { return $false }
        }
    }
    $expectedIds = @($script:WorkerCaseIds[$ExpectedPhase])
    if ($Record.cases -isnot [System.Array]) { return $false }
    $cases = @($Record.cases)
    if ($Record.status -ceq 'SUBJECT_COMPLETE' -and $cases.Count -ne $expectedIds.Count) { return $false }
    if ($cases.Count -gt $expectedIds.Count) { return $false }
    for ($i = 0; $i -lt $cases.Count; $i++) {
        $case = $cases[$i]
        if (-not (Test-ObjectShape $case @('case_id','expected','status','observations')) -or $case.case_id -isnot [string] -or $case.expected -isnot [string] -or $case.status -isnot [string] -or $case.case_id -cne $expectedIds[$i] -or $case.expected -cne $script:ExpectedByCase[$expectedIds[$i]]) { return $false }
        if ($case.status -cne 'PASS' -and $case.status -cne 'FAIL') { return $false }
        $completeCase = ($Record.status -ceq 'SUBJECT_COMPLETE')
        if ($completeCase -and $case.status -cne 'PASS') { return $false }
        if (-not (Test-SubcontrolRows $case $case.case_id $completeCase)) { return $false }
    }
    if ($Record.status -ceq 'SUBJECT_COMPLETE') {
        if ($Record.worker_exit.wait_confirmed -ne $true -or $Record.worker_exit.returncode -ne 0 -or $Record.failure -ne $null) { return $false }
    } elseif ($null -eq $Record.failure) { return $false }
    $Reason.Value = $null
    return $true
}

function Test-FinalAdmission {
    param([object]$Terminal, [object]$Context, [object]$DriverWaitConfirmed, [object]$DriverExitCode, [object]$PreservationEqual, [object]$FinalizationComplete, [object]$ElapsedMs, [int]$MaximumMs, [ref]$Reason)
    $Reason.Value = 'final admission rejected'
    if ($null -eq $Terminal -or $Terminal.status -isnot [string] -or $Terminal.status -cne 'SUBJECT_COMPLETE') { return $false }
    if ($null -ne $Context -and $Context.phase -isnot [string]) { return $false }
    if (-not (Test-ExactBoolean $DriverWaitConfirmed) -or $DriverWaitConfirmed -ne $true -or -not (Test-ExactInteger $DriverExitCode) -or $DriverExitCode -ne 0) { return $false }
    if (-not (Test-ExactBoolean $PreservationEqual) -or $PreservationEqual -ne $true -or -not (Test-ExactBoolean $FinalizationComplete) -or $FinalizationComplete -ne $true) { return $false }
    if (-not (Test-ExactInteger $ElapsedMs) -or $ElapsedMs -lt 0 -or $ElapsedMs -gt $MaximumMs -or -not (Test-ExactInteger $Terminal.phase_elapsed_ms) -or $Terminal.phase_elapsed_ms -gt $MaximumMs) { return $false }
    if ($null -ne $Context -and $Context.phase -ceq 'stop-observation-compatibility') {
        if (-not (Test-HostC06 $Context.host_case $Terminal $DriverWaitConfirmed $DriverExitCode $PreservationEqual)) { return $false }
    }
    $Reason.Value = $null
    return $true
}

function Get-PostWriteFinalOutcome {
    param([object]$PostWriteAdmissionPassed, [object]$OverrunMarkerWritten)
    $admitted = (Test-ExactBoolean $PostWriteAdmissionPassed) -and $PostWriteAdmissionPassed -eq $true
    $markerWritten = (Test-ExactBoolean $OverrunMarkerWritten) -and $OverrunMarkerWritten -eq $true
    $success = ($admitted -and $markerWritten)
    return [pscustomobject]@{
        success = [bool]$success
        pass_marker_allowed = [bool]$success
        exit_code = if ($success) { 0 } else { 1 }
    }
}

function Get-FileSha256 {
    param([string]$Path)
    if (-not [System.IO.File]::Exists($Path)) { throw ('pinned file is missing: ' + $Path) }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-HostRuntimePin {
    param([object]$Freeze)
    $pins = $Freeze.recovery_preflight
    $process = [System.Diagnostics.Process]::GetCurrentProcess()
    $actualHostPath = [System.IO.Path]::GetFullPath($process.MainModule.FileName)
    $expectedHostPath = [System.IO.Path]::GetFullPath([string]$pins.host_path)
    if (-not [string]::Equals($actualHostPath, $expectedHostPath, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'current PowerShell image path differs from the parent runtime pin' }
    $actualPowerShellVersion = [string]$PSVersionTable.PSVersion.ToString()
    if ($actualPowerShellVersion -cne [string]$pins.ps_version) { throw 'current Windows PowerShell version differs from the parent runtime pin' }
    $wslCommand = Get-Command -Name 'wsl.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $actualWslPath = [System.IO.Path]::GetFullPath([string]$wslCommand.Source)
    $expectedWslPath = [System.IO.Path]::GetFullPath([string]$pins.wsl_path)
    if (-not [string]::Equals($actualWslPath, $expectedWslPath, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'resolved wsl.exe path differs from the parent runtime pin' }
    $actualHostHash = Get-FileSha256 $actualHostPath
    $actualWslHash = Get-FileSha256 $actualWslPath
    if ($actualHostHash -cne [string]$pins.host_sha256 -or $actualWslHash -cne [string]$pins.wsl_sha256) { throw 'PowerShell or wsl.exe image hash differs from the parent runtime pin' }
    $script:HostRuntime = [pscustomobject]@{
        host_path = $actualHostPath; host_sha256 = $actualHostHash; ps_version = $actualPowerShellVersion
        wsl_path = $actualWslPath; wsl_sha256 = $actualWslHash
    }
}

function Resolve-ProtectedPath {
    param([string]$RawPath)
    if ($RawPath -isnot [string] -or $RawPath -notmatch '^(?i:E:/projects/ladybug/|E:\\projects\\ladybug\\)') { throw ('protected path is outside the pinned workspace: ' + $RawPath) }
    $candidate = [System.IO.Path]::GetFullPath($RawPath.Replace('/', '\'))
    $root = [System.IO.Path]::GetFullPath('E:\projects\ladybug')
    if (-not $candidate.StartsWith($root + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw ('protected path escaped the pinned workspace: ' + $RawPath) }
    return $candidate
}

function Get-HostPreservationSnapshot {
    param([object]$Freeze, [object]$Execution, [string]$ManifestSha)
    $sources = [ordered]@{}
    foreach ($relative in $script:SourcePaths) {
        $actual = Get-FileSha256 (Join-Path $script:Root ($relative -replace '/', '\'))
        $expected = [string]$Execution.source_sha256.PSObject.Properties[$relative].Value
        if ($actual -cne $expected) { throw ('source changed from parent freeze: ' + $relative) }
        $sources[$relative] = $actual
    }
    $fixtures = [ordered]@{}
    foreach ($relative in $script:FixturePaths) {
        $actual = Get-FileSha256 (Join-Path $script:Root ($relative -replace '/', '\'))
        $expected = [string]$Execution.fixture_sha256.PSObject.Properties[$relative].Value
        if ($actual -cne $expected) { throw ('fixture changed from parent freeze: ' + $relative) }
        $fixtures[$relative] = $actual
    }
    $readInputs = [ordered]@{}
    $actualTranscript = Get-FileSha256 $script:TranscriptPath
    $expectedTranscript = [string]$Execution.read_inputs_sha256.PSObject.Properties[$script:ReadInputPaths[0]].Value
    if ($actualTranscript -cne $expectedTranscript -or $actualTranscript -cne $script:TranscriptSha256) { throw 'retained unknown-signal transcript differs from its independent pin' }
    $readInputs[$script:ReadInputPaths[0]] = $actualTranscript
    $ticket = Get-FileSha256 $script:TicketPath
    if ($ticket -cne $Execution.ticket_sha256) { throw 'canonical FEAT-010 ticket hash differs from execution freeze' }
    $manifest = Get-FileSha256 $script:FreezePath
    if ($manifest -cne $ManifestSha) { throw 'integration freeze changed during the phase' }
    $protected = [ordered]@{}
    foreach ($raw in @(Get-PropertyNames $Freeze.protected_files_sha256)) {
        $path = Resolve-ProtectedPath $raw
        $actual = Get-FileSha256 $path
        $expected = [string]$Freeze.protected_files_sha256.PSObject.Properties[$raw].Value
        if ($actual -cne $expected) { throw ('protected source changed from parent freeze: ' + $raw) }
        $protected[$raw] = $actual
    }
    if ($protected.Count -ne 199) { throw 'protected file map is not the exact 199-path set' }
    $qualified = [ordered]@{}
    foreach ($relative in $script:QualifiedInputPaths) {
        $actual = Get-FileSha256 (Join-Path $script:QualifiedRoot ($relative -replace '/', '\'))
        $expected = [string]$Freeze.qualified_seven_inputs_sha256.PSObject.Properties[$relative].Value
        if ($actual -cne $expected) { throw ('qualified historical input changed: ' + $relative) }
        $qualified[$relative] = $actual
    }
    return [pscustomobject]@{
        source_sha256 = [pscustomobject]$sources
        fixture_sha256 = [pscustomobject]$fixtures
        read_inputs_sha256 = [pscustomobject]$readInputs
        ticket_sha256 = $ticket
        manifest_sha256 = $manifest
        protected_files_sha256 = [pscustomobject]$protected
        qualified_seven_inputs_sha256 = [pscustomobject]$qualified
        python_sha256 = [string]$Freeze.python.sha256
    }
}

function Write-NewUtf8File {
    param([string]$Path, [string]$Text)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $stream = New-Object System.IO.FileStream($Path, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $bytes = $encoding.GetBytes($Text)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
}

function Write-JsonCreateNew {
    param([string]$Path, [object]$Value)
    $json = ConvertTo-Json -InputObject $Value -Depth 100 -Compress
    Write-NewUtf8File $Path ($json + "`n")
}

function Skip-JsonWhitespace {
    param([string]$Json, [ref]$Index)
    while ($Index.Value -lt $Json.Length) {
        $code = [int][char]$Json[$Index.Value]
        if ($code -eq 0x20 -or $code -eq 0x09 -or $code -eq 0x0a -or $code -eq 0x0d) { $Index.Value = [int]$Index.Value + 1 }
        else { break }
    }
}

function Read-JsonStringToken {
    param([string]$Json, [ref]$Index)
    if ($Index.Value -ge $Json.Length -or $Json[$Index.Value] -cne '"') { throw 'JSON string token did not begin with a quote' }
    $Index.Value = [int]$Index.Value + 1
    $builder = New-Object System.Text.StringBuilder
    while ($Index.Value -lt $Json.Length) {
        $current = $Json[$Index.Value]
        $Index.Value = [int]$Index.Value + 1
        if ($current -ceq '"') { return $builder.ToString() }
        if ([int][char]$current -lt 0x20) { throw 'JSON string contains an unescaped control character' }
        if ($current -cne '\') { [void]$builder.Append($current); continue }
        if ($Index.Value -ge $Json.Length) { throw 'JSON string ends after an escape marker' }
        $escape = $Json[$Index.Value]
        $Index.Value = [int]$Index.Value + 1
        switch -CaseSensitive ($escape) {
            '"' { [void]$builder.Append('"') }
            '\' { [void]$builder.Append('\') }
            '/' { [void]$builder.Append('/') }
            'b' { [void]$builder.Append([char]0x08) }
            'f' { [void]$builder.Append([char]0x0c) }
            'n' { [void]$builder.Append([char]0x0a) }
            'r' { [void]$builder.Append([char]0x0d) }
            't' { [void]$builder.Append([char]0x09) }
            'u' {
                if ($Index.Value + 4 -gt $Json.Length) { throw 'JSON unicode escape is truncated' }
                $hex = $Json.Substring($Index.Value, 4)
                if ($hex -cnotmatch '^[0-9a-fA-F]{4}$') { throw 'JSON unicode escape is malformed' }
                [void]$builder.Append([char][Convert]::ToInt32($hex, 16))
                $Index.Value = [int]$Index.Value + 4
            }
            default { throw 'JSON string contains an unsupported escape' }
        }
    }
    throw 'JSON string token is unterminated'
}

function Test-JsonValueWithUniqueKeys {
    param([string]$Json, [ref]$Index, [int]$Depth)
    if ($Depth -gt 128) { return $false }
    Skip-JsonWhitespace $Json $Index
    if ($Index.Value -ge $Json.Length) { return $false }
    $current = $Json[$Index.Value]
    if ($current -ceq '"') {
        try { $discard = Read-JsonStringToken $Json $Index; return $true } catch { return $false }
    }
    if ($current -ceq '{') {
        $Index.Value = [int]$Index.Value + 1
        Skip-JsonWhitespace $Json $Index
        if ($Index.Value -lt $Json.Length -and $Json[$Index.Value] -ceq '}') { $Index.Value = [int]$Index.Value + 1; return $true }
        $keys = [System.Collections.Generic.Dictionary[string,bool]]::new([System.StringComparer]::Ordinal)
        while ($Index.Value -lt $Json.Length) {
            Skip-JsonWhitespace $Json $Index
            if ($Index.Value -ge $Json.Length -or $Json[$Index.Value] -cne '"') { return $false }
            try { $key = Read-JsonStringToken $Json $Index } catch { return $false }
            if ($keys.ContainsKey($key)) { return $false }
            $keys.Add($key, $true)
            Skip-JsonWhitespace $Json $Index
            if ($Index.Value -ge $Json.Length -or $Json[$Index.Value] -cne ':') { return $false }
            $Index.Value = [int]$Index.Value + 1
            if (-not (Test-JsonValueWithUniqueKeys $Json $Index ($Depth + 1))) { return $false }
            Skip-JsonWhitespace $Json $Index
            if ($Index.Value -ge $Json.Length) { return $false }
            if ($Json[$Index.Value] -ceq '}') { $Index.Value = [int]$Index.Value + 1; return $true }
            if ($Json[$Index.Value] -cne ',') { return $false }
            $Index.Value = [int]$Index.Value + 1
        }
        return $false
    }
    if ($current -ceq '[') {
        $Index.Value = [int]$Index.Value + 1
        Skip-JsonWhitespace $Json $Index
        if ($Index.Value -lt $Json.Length -and $Json[$Index.Value] -ceq ']') { $Index.Value = [int]$Index.Value + 1; return $true }
        while ($Index.Value -lt $Json.Length) {
            if (-not (Test-JsonValueWithUniqueKeys $Json $Index ($Depth + 1))) { return $false }
            Skip-JsonWhitespace $Json $Index
            if ($Index.Value -ge $Json.Length) { return $false }
            if ($Json[$Index.Value] -ceq ']') { $Index.Value = [int]$Index.Value + 1; return $true }
            if ($Json[$Index.Value] -cne ',') { return $false }
            $Index.Value = [int]$Index.Value + 1
        }
        return $false
    }
    foreach ($literal in @('true','false','null')) {
        if ($Index.Value + $literal.Length -le $Json.Length -and [string]::CompareOrdinal($Json, $Index.Value, $literal, 0, $literal.Length) -eq 0) {
            $Index.Value = [int]$Index.Value + $literal.Length
            return $true
        }
    }
    $numberMatch = [System.Text.RegularExpressions.Regex]::Match($Json.Substring($Index.Value), '^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', [System.Text.RegularExpressions.RegexOptions]::CultureInvariant)
    if (-not $numberMatch.Success) { return $false }
    $Index.Value = [int]$Index.Value + $numberMatch.Length
    return $true
}

function Test-JsonWithUniqueKeys {
    param([string]$Json, [int]$MaximumCharacters = 16777216)
    if ($Json -isnot [string] -or $Json.Length -eq 0 -or $Json.Length -gt $MaximumCharacters) { return $false }
    $index = 0
    if (-not (Test-JsonValueWithUniqueKeys $Json ([ref]$index) 0)) { return $false }
    Skip-JsonWhitespace $Json ([ref]$index)
    return ($index -eq $Json.Length)
}

function Get-HostReadCutoffElapsed {
    $maximum = [int]$script:PhaseLimits[$Phase]
    return [long]($maximum - $script:GoReserveMs - $script:DriverWaitReserveMs - $script:EvidenceReserveMs)
}

function Register-BoundedReadFailure {
    param([string]$Stage, [string]$Path, [object]$Observation, [string]$FailureKind)
    if ($null -eq $Observation -or ($Observation.accepted -and [string]::IsNullOrEmpty($FailureKind))) { return }
    if ($script:BoundedReadFailures.Count -ge 12) { return }
    [void]$script:BoundedReadFailures.Add([pscustomobject]@{
        stage = Limit-CleanupDetail $Stage; path = Limit-CleanupDetail $Path
        rejection = if ($Observation.accepted) { [string]$FailureKind } else { [string]$Observation.rejection }
        position = [long]$Observation.position; actual_position = [long]$Observation.actual_position
        retained_bytes = [long]$Observation.retained_bytes; text_units = $Observation.text_units
        whole_document_decode_attempted = [bool]$Observation.whole_document_decode_attempted
        sha256 = [string]$Observation.sha256; prefix_b64 = [string]$Observation.prefix_b64
    })
}

function Read-BoundedUtf8Stream {
    param([System.IO.Stream]$Stream, [long]$CutoffElapsed, [bool]$DecodeDocument)
    $retained = [System.IO.MemoryStream]::new([int]$script:MaximumHostJsonBytes)
    $chunk = New-Object byte[] $script:HostReadChunkBytes
    $position = [long]0
    $overLimit = $false
    $readFailure = $null
    try {
        while ($true) {
            if ($script:Clock.ElapsedMilliseconds -ge $CutoffElapsed) { $readFailure = 'READ_DEADLINE'; break }
            $request = [int][Math]::Min([long]$script:HostReadChunkBytes, ([long]$script:MaximumHostJsonBytes - $position + 1))
            try { $count = $Stream.Read($chunk, 0, $request) } catch { $readFailure = 'READ_ERROR'; break }
            if ($count -eq 0) {
                if ($script:Clock.ElapsedMilliseconds -ge $CutoffElapsed) { $readFailure = 'READ_DEADLINE' }
                break
            }
            $keep = [int][Math]::Min([long]$count, ([long]$script:MaximumHostJsonBytes - $position))
            if ($keep -gt 0) {
                $retained.Write($chunk, 0, $keep)
                $position += $keep
            }
            if ($count -gt $keep) {
                $position += 1
                $overLimit = $true
            }
            if ($script:Clock.ElapsedMilliseconds -ge $CutoffElapsed) { $readFailure = 'READ_DEADLINE'; break }
            if ($overLimit) { break }
        }
        $retainedBytes = [int]$retained.Length
        $raw = $retained.GetBuffer()
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            $digest = $hasher.ComputeHash($raw, 0, $retainedBytes)
            $sha256 = ([System.BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
        } finally { $hasher.Dispose() }
        $sampleCount = [int][Math]::Min(32, $retainedBytes)
        $prefixB64 = [System.Convert]::ToBase64String($raw, 0, $sampleCount)
        $actualPosition = [long]$position
        try { $actualPosition = [long]$Stream.Position } catch { }
        if ($null -eq $readFailure -and $script:Clock.ElapsedMilliseconds -ge $CutoffElapsed) { $readFailure = 'READ_DEADLINE' }
        $base = @{
            accepted = $false; rejection = $null; position = [long]$position; actual_position = $actualPosition
            retained_bytes = [long]$retainedBytes; text = $null; text_units = $null
            whole_document_decode_attempted = $false; sha256 = $sha256; prefix_b64 = $prefixB64
        }
        if ($null -ne $readFailure) { $base.rejection = $readFailure; return [pscustomobject]$base }
        if ($overLimit) { $base.rejection = 'BYTE_LIMIT_BEFORE_DECODE'; return [pscustomobject]$base }
        if (-not $DecodeDocument) { $base.accepted = $true; return [pscustomobject]$base }
        $offset = 0
        if ($retainedBytes -ge 3 -and $raw[0] -eq 239 -and $raw[1] -eq 187 -and $raw[2] -eq 191) { $offset = 3 }
        if ($script:Clock.ElapsedMilliseconds -ge $CutoffElapsed) { $base.rejection = 'READ_DEADLINE'; return [pscustomobject]$base }
        $base.whole_document_decode_attempted = $true
        try { $text = (New-Object System.Text.UTF8Encoding($false, $true)).GetString($raw, $offset, ($retainedBytes - $offset)) }
        catch [System.Text.DecoderFallbackException] { $base.rejection = 'STRICT_UTF8'; return [pscustomobject]$base }
        $base.text_units = [int]$text.Length
        if ($text.Length -gt $script:MaximumHostJsonUnits) { $base.rejection = 'UTF16_UNIT_LIMIT'; return [pscustomobject]$base }
        if ($text.Length -eq 0) { $base.rejection = 'EMPTY_JSON_OBJECT'; $base.text = ''; return [pscustomobject]$base }
        $base.accepted = $true
        $base.text = $text
        return [pscustomobject]$base
    } finally { $retained.Dispose() }
}

function Read-BoundedUtf8File {
    param([string]$Path, [string]$Stage, [bool]$DecodeDocument)
    $observation = $null
    try { $stream = [System.IO.File]::OpenRead($Path) }
    catch {
        $observation = [pscustomobject]@{
            accepted = $false; rejection = 'OPEN_ERROR'; position = [long]0; actual_position = [long]0
            retained_bytes = [long]0; text = $null; text_units = $null; whole_document_decode_attempted = $false
            sha256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'; prefix_b64 = ''
        }
        Register-BoundedReadFailure $Stage $Path $observation
        return ,$observation
    }
    try { $observation = Read-BoundedUtf8Stream $stream (Get-HostReadCutoffElapsed) $DecodeDocument }
    finally { $stream.Dispose() }
    Register-BoundedReadFailure $Stage $Path $observation
    return ,$observation
}

function ConvertFrom-BoundedHostJson {
    param([object]$Observation, [string]$Label)
    if ($null -eq $Observation -or -not $Observation.accepted -or $Observation.text -isnot [string]) { throw ($Label + ' bounded read rejected: ' + $Observation.rejection) }
    if (-not (Test-JsonWithUniqueKeys $Observation.text)) {
        Register-BoundedReadFailure ($Label + ' JSON validation') $Label $Observation 'JSON_MALFORMED_OR_DUPLICATE_KEY'
        throw ($Label + ' contained malformed JSON or duplicate object keys')
    }
    try { return (ConvertFrom-Json -InputObject $Observation.text -ErrorAction Stop) }
    catch {
        Register-BoundedReadFailure ($Label + ' JSON conversion') $Label $Observation 'JSON_CONVERSION_ERROR'
        throw ($Label + ' JSON is invalid: ' + $_.Exception.Message)
    }
}

function Test-ProtocolLineWithinLimit {
    param([string]$Line)
    if ($null -eq $Line -or $Line.Length -gt $script:ProtocolLineMaximumCharacters) { return $false }
    try {
        $encoding = New-Object System.Text.UTF8Encoding($false, $true)
        return ($encoding.GetByteCount($Line) -le $script:ProtocolLineMaximumBytes)
    } catch { return $false }
}

function Read-JsonLine {
    param([string]$Line, [string]$Label)
    if ($null -eq $Line -or $Line.Length -eq 0) { throw ($Label + ' was blank or EOF') }
    if (-not (Test-JsonWithUniqueKeys $Line $script:ProtocolLineMaximumCharacters)) { throw ($Label + ' contained malformed JSON or duplicate object keys') }
    try { $record = ConvertFrom-Json -InputObject $Line -ErrorAction Stop } catch { throw ($Label + ' was not one valid JSON object: ' + $_.Exception.Message) }
    if ($null -eq $record -or $record -is [string] -or $record -is [System.Array]) { throw ($Label + ' was not an object') }
    [void]$script:ProtocolRecords.Add($record)
    return $record
}

function New-StreamPumpState {
    param([System.IO.Stream]$Stream, [string]$Name, [int]$MaximumRetainedCharacters)
    $encoding = New-Object System.Text.UTF8Encoding($false, $false)
    return [pscustomobject]@{
        name = $Name; stream = $Stream; buffer = (New-Object byte[] 4096); task = $null
        offset = 0; count = 0; eof = $false; read_error = $null
        observed_bytes = [long]0; hash = [System.Security.Cryptography.SHA256]::Create(); hash_final = $false; sha256 = $null
        decoder = $encoding.GetDecoder(); retained = (New-Object System.Text.StringBuilder); tail = (New-Object System.Text.StringBuilder)
        maximum_characters = $MaximumRetainedCharacters; truncated = $false
        mode = if ($Name -ceq 'stdout') { 'protocol' } else { 'diagnostic' }
        line = (New-Object System.IO.MemoryStream); pending_cr = $false; protocol_overflow = $false; protocol_error = $false; protocol_line_bytes = [long]0; protocol_overflow_observed_bytes = [long]0; partial_protocol = $null; extra_stdout = $false
    }
}

function Complete-StreamHash {
    param([object]$State)
    if ($State.hash_final) { return }
    $empty = New-Object byte[] 0
    [void]$State.hash.TransformFinalBlock($empty, 0, 0)
    $State.sha256 = [System.BitConverter]::ToString($State.hash.Hash).Replace('-', '').ToLowerInvariant()
    $State.hash_final = $true
}

function Add-StreamRetainedText {
    param([object]$State, [string]$Text)
    if ($null -eq $Text -or $Text.Length -eq 0) { return }
    $maximum = [int]$State.maximum_characters
    if (-not $State.truncated -and $State.retained.Length + $Text.Length -le $maximum) {
        [void]$State.retained.Append($Text)
        return
    }
    if (-not $State.truncated) {
        $combined = $State.retained.ToString() + $Text
        $headCount = [int][Math]::Floor($maximum / 2)
        $tailCount = $maximum - $headCount
        [void]$State.retained.Clear()
        [void]$State.tail.Clear()
        [void]$State.retained.Append($combined.Substring(0, $headCount))
        [void]$State.tail.Append($combined.Substring([Math]::Max(0, $combined.Length - $tailCount)))
        $State.truncated = $true
        return
    }
    [void]$State.tail.Append($Text)
    $tailMaximum = [int][Math]::Ceiling($maximum / 2)
    if ($State.tail.Length -gt $tailMaximum) { [void]$State.tail.Remove(0, $State.tail.Length - $tailMaximum) }
}

function Complete-StreamDecoder {
    param([object]$State)
    if ($State.name -ceq 'stdout' -and $State.mode -ceq 'protocol') { return }
    $characters = New-Object char[] 16
    $empty = New-Object byte[] 0
    $count = $State.decoder.GetChars($empty, 0, 0, $characters, 0, $true)
    if ($count -gt 0) { Add-StreamRetainedText $State (New-Object System.String($characters, 0, $count)) }
}

function Complete-StreamRead {
    param([object]$State)
    if ($null -eq $State.task -or -not $State.task.IsCompleted) { return }
    $task = $State.task
    $State.task = $null
    try { $readCount = [int]$task.GetAwaiter().GetResult() }
    catch {
        $State.read_error = $_.Exception.Message
        Complete-StreamHash $State
        Complete-StreamDecoder $State
        return
    }
    if ($readCount -eq 0) {
        $State.eof = $true
        Complete-StreamHash $State
        Complete-StreamDecoder $State
        return
    }
    [void]$State.hash.TransformBlock($State.buffer, 0, $readCount, $State.buffer, 0)
    $State.observed_bytes = [long]$State.observed_bytes + $readCount
    $State.offset = 0
    $State.count = $readCount
}

function Start-StreamRead {
    param([object]$State)
    if ($State.offset -lt $State.count) { return }
    $State.offset = 0
    $State.count = 0
    if ($State.eof -or $null -ne $State.read_error -or $null -ne $State.task) { return }
    try { $State.task = $State.stream.ReadAsync($State.buffer, 0, $State.buffer.Length) }
    catch {
        $State.read_error = $_.Exception.Message
        Complete-StreamHash $State
        Complete-StreamDecoder $State
    }
}

function Consume-StreamTextChunk {
    param([object]$State)
    if ($State.offset -ge $State.count) { return }
    $remaining = $State.count - $State.offset
    $characters = New-Object char[] 8192
    $decoded = $State.decoder.GetChars($State.buffer, $State.offset, $remaining, $characters, 0, $false)
    $State.offset = $State.count
    if ($decoded -gt 0) { Add-StreamRetainedText $State (New-Object System.String($characters, 0, $decoded)) }
    if ($State.name -ceq 'stdout' -and $remaining -gt 0) { $State.extra_stdout = $true }
}

function Save-PartialProtocolPrefix {
    param([object]$State, [long]$ObservedLineBytes, [bool]$NewlineSeen = $false)
    if ($null -ne $State.partial_protocol) { return }
    $raw = $State.line.ToArray()
    $prefixBytes = [int][Math]::Min(16384, $raw.Length)
    $sample = New-Object byte[] $prefixBytes
    if ($prefixBytes -gt 0) { [System.Array]::Copy($raw, 0, $sample, 0, $prefixBytes) }
    $State.partial_protocol = [pscustomobject]@{
        line_bytes_observed_at_failure = [long]$ObservedLineBytes
        retained_line_prefix_bytes = [int]$raw.Length
        retained_line_prefix_sha256 = Get-BytesSha256 $raw
        sample_bytes = $prefixBytes
        sample_base64 = [System.Convert]::ToBase64String($sample)
        sample_sha256 = Get-BytesSha256 $sample
        newline_seen = [bool]$NewlineSeen; stream_eof = $null; observed_stream_bytes = [long]$State.observed_bytes
    }
}

function Get-ProtocolLineFromBuffer {
    param([object]$State, [string]$Label)
    while ($State.offset -lt $State.count) {
        $byte = [int]$State.buffer[$State.offset]
        $State.offset++
        if ($byte -eq 10) {
            $State.pending_cr = $false
            $lineBytes = $State.line.ToArray()
            try { $line = (New-Object System.Text.UTF8Encoding($false, $true)).GetString($lineBytes) }
            catch {
                $State.protocol_error = $true
                Save-PartialProtocolPrefix $State ([long]$lineBytes.Length) $true
                throw ($Label + ' was not valid UTF-8 protocol data')
            }
            $State.line.SetLength(0)
            $State.protocol_line_bytes = [long]0
            if (-not (Test-ProtocolLineWithinLimit $line)) { throw ($Label + ' JSON line exceeded the bounded 262144-byte or character limit') }
            [void]$script:ProtocolLines.Add($line)
            try { $record = Read-JsonLine $line $Label }
            catch { $State.protocol_error = $true; throw }
            if ($record.kind -ceq 'TERMINAL') { $State.mode = 'tail' }
            return $record
        }
        if ($State.pending_cr) {
            if ($State.line.Length -ge $script:ProtocolLineMaximumBytes) { $State.protocol_overflow = $true; $State.protocol_overflow_observed_bytes = [long]$State.protocol_line_bytes + 2; Save-PartialProtocolPrefix $State $State.protocol_overflow_observed_bytes; throw ($Label + ' JSON line exceeded the bounded 262144-byte protocol limit') }
            $State.line.WriteByte([byte]13)
            $State.protocol_line_bytes++
            $State.pending_cr = $false
        }
        if ($byte -eq 13) { $State.pending_cr = $true; continue }
        if ($State.line.Length -ge $script:ProtocolLineMaximumBytes) { $State.protocol_overflow = $true; $State.protocol_overflow_observed_bytes = [long]$State.protocol_line_bytes + 1; Save-PartialProtocolPrefix $State $State.protocol_overflow_observed_bytes; throw ($Label + ' JSON line exceeded the bounded 262144-byte protocol limit') }
        $State.line.WriteByte([byte]$byte)
        $State.protocol_line_bytes++
    }
    return $null
}

function Get-StreamRetainedText {
    param([object]$State)
    if ($null -eq $State) { return '' }
    if (-not $State.truncated) { return $State.retained.ToString() }
    $marker = "`n<stream truncated; observed_bytes=$($State.observed_bytes); sha256=$($State.sha256); eof=$($State.eof)>`n"
    $available = [int]$State.maximum_characters - $marker.Length
    if ($available -lt 0) { $marker = $marker.Substring(0, [int]$State.maximum_characters); $available = 0 }
    $headCount = [int][Math]::Min($State.retained.Length, [Math]::Floor($available / 2))
    $tailCount = [int][Math]::Min($State.tail.Length, $available - $headCount)
    $head = if ($headCount -gt 0) { $State.retained.ToString(0, $headCount) } else { '' }
    $tail = if ($tailCount -gt 0) { $State.tail.ToString($State.tail.Length - $tailCount, $tailCount) } else { '' }
    return ($head + $marker + $tail)
}

function Get-StreamCaptureSummary {
    param([object]$State)
    if ($null -eq $State) { return $null }
    if (-not $State.hash_final) { Complete-StreamHash $State }
    $retainedText = Get-StreamRetainedText $State
    return [pscustomobject]@{
        observed_bytes = [long]$State.observed_bytes; sha256 = [string]$State.sha256
        eof = [bool]$State.eof; partial = [bool](-not $State.eof)
        retained_characters = [int]$retainedText.Length; truncated = [bool]$State.truncated
        protocol_overflow = [bool]$State.protocol_overflow; unexpected_stdout = [bool]$State.extra_stdout
        read_error = if ($null -ne $State.read_error) { Limit-CleanupDetail ([string]$State.read_error) } else { $null }
    }
}

function Invoke-StreamOracleControl {
    param([string]$Id)
    $name = if ($Id -ceq 'STREAM_STDERR_CAP_NO_NEWLINE') { 'stderr' } else { 'stdout' }
    $count = if ($Id -ceq 'STREAM_STDOUT_PROTOCOL_OVERSIZE_NO_NEWLINE') { 262145 } else { 16385 }
    $fill = if ($Id -ceq 'STREAM_STDOUT_PROTOCOL_OVERSIZE_NO_NEWLINE') { 65 } elseif ($Id -ceq 'STREAM_STDERR_CAP_NO_NEWLINE') { 83 } else { 84 }
    $bytes = New-Object byte[] $count
    for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = [byte]$fill }
    $memory = New-Object System.IO.MemoryStream
    $memory.Write($bytes, 0, $bytes.Length)
    $memory.Position = 0
    $state = New-StreamPumpState $memory $name 16384
    if ($Id -ceq 'STREAM_STDOUT_TAIL_OVERSIZE_NO_NEWLINE') { $state.mode = 'tail' }
    $classification = 'ACCEPT'
    $failure = $null
    while (-not $state.eof) {
        Start-StreamRead $state
        if ($null -eq $state.task) { $failure = 'stream fixture ended without EOF state'; break }
        $remaining = [int][Math]::Floor([int]$script:PhaseLimits[$Phase] - $script:EvidenceReserveMs - $script:Clock.ElapsedMilliseconds)
        if ($remaining -le 0 -or -not $state.task.Wait($remaining)) { $failure = 'bounded host stream control reached the existing phase cutoff'; break }
        Complete-StreamRead $state
        if ($null -ne $state.read_error) { $failure = $state.read_error; break }
        if ($name -ceq 'stdout' -and $state.mode -ceq 'protocol' -and $state.offset -lt $state.count) {
            try { [void](Get-ProtocolLineFromBuffer $state 'stream oracle') }
            catch {
                if ($state.protocol_overflow) {
                    $classification = 'PROTOCOL'
                    Save-PartialProtocolPrefix $state $state.protocol_overflow_observed_bytes
                    $state.mode = 'tail'
                    $state.pending_cr = $false
                    $state.line.SetLength(0)
                } else { $failure = $_.Exception.Message }
            }
        }
        if ($state.offset -lt $state.count) { Consume-StreamTextChunk $state }
    }
    $summary = Get-StreamCaptureSummary $state
    $expectedHash = Get-BytesSha256 $bytes
    $passed = ($null -eq $failure -and $summary.observed_bytes -eq $count -and $summary.sha256 -ceq $expectedHash -and $summary.eof -and -not $summary.partial -and $summary.retained_characters -le 16384)
    if ($Id -ceq 'STREAM_STDOUT_PROTOCOL_OVERSIZE_NO_NEWLINE') {
        $passed = ($passed -and $classification -ceq 'PROTOCOL' -and $state.protocol_overflow -and $state.line.Length -eq 0 -and
            $null -ne $state.partial_protocol -and $state.partial_protocol.retained_line_prefix_bytes -eq 262144 -and
            $state.partial_protocol.line_bytes_observed_at_failure -eq 262145 -and $state.partial_protocol.sample_bytes -eq 16384 -and
            $state.partial_protocol.newline_seen -eq $false -and $summary.unexpected_stdout -eq $false)
    } elseif ($Id -ceq 'STREAM_STDERR_CAP_NO_NEWLINE') {
        $passed = ($passed -and $state.truncated -and -not $summary.unexpected_stdout -and -not $state.protocol_overflow)
    } else {
        $passed = ($passed -and $summary.unexpected_stdout -and $state.truncated -and -not $state.protocol_overflow)
        $classification = if ($summary.unexpected_stdout) { 'PROTOCOL' } else { 'ACCEPT' }
        $passed = ($passed -and $classification -ceq 'PROTOCOL')
    }
    $expected = Get-HostOracleExpected $Id
    $observed = if ($passed) { $expected } else { 'MISMATCH' }
    $reason = [pscustomobject]@{ classification = $classification; failure = $failure; stream = $summary; partial_protocol = $state.partial_protocol }
    $memory.Dispose()
    return [pscustomobject]@{ id = $Id; expected = $expected; observed = $observed; status = $(if ($passed) { 'PASS' } else { 'FAIL' }); reason = (ConvertTo-Json -InputObject $reason -Depth 8 -Compress) }
}

function Read-ProtocolLine {
    param([int]$DeadlineElapsedMs, [string]$Label)
    $stdout = $script:StdoutState
    $stderr = $script:StderrState
    if ($null -eq $stdout -or $null -eq $stderr) { throw 'bounded stream pumps were not initialized before protocol read' }
    while ($true) {
        if ([int]$script:Clock.ElapsedMilliseconds -ge $DeadlineElapsedMs) { throw ($Label + ' timed out at its absolute phase cutoff') }
        foreach ($state in @($stderr, $stdout)) { Complete-StreamRead $state }
        if ($null -ne $stderr.read_error) { throw ('stderr stream read failed: ' + $stderr.read_error) }
        if ($stderr.offset -lt $stderr.count) { Consume-StreamTextChunk $stderr }
        if ($null -ne $stdout.read_error) { throw ($Label + ' stream read failed: ' + $stdout.read_error) }
        if ($stdout.mode -cne 'protocol') { throw ($Label + ' was requested after stdout entered bounded tail capture') }
        if ($stdout.offset -lt $stdout.count) {
            $record = Get-ProtocolLineFromBuffer $stdout $Label
            if ($null -ne $record) { return $record }
        }
        if ($stdout.eof -and $stdout.offset -ge $stdout.count) {
            if ($stdout.pending_cr) {
                $stdout.pending_cr = $false
                if ($stdout.line.Length -ge $script:ProtocolLineMaximumBytes) { $stdout.protocol_overflow = $true; $stdout.protocol_overflow_observed_bytes = [long]$stdout.protocol_line_bytes + 1; Save-PartialProtocolPrefix $stdout $stdout.protocol_overflow_observed_bytes; throw ($Label + ' JSON line exceeded the bounded 262144-byte protocol limit') }
                $stdout.line.WriteByte([byte]13)
                $stdout.protocol_line_bytes++
            }
            if ($stdout.line.Length -gt 0) { throw ($Label + ' ended before its required newline') }
            throw ($Label + ' reached stdout EOF before a record')
        }
        Start-StreamRead $stderr
        Start-StreamRead $stdout
        $tasks = @()
        if ($null -ne $stdout.task) { $tasks += [System.Threading.Tasks.Task]$stdout.task }
        if ($null -ne $stderr.task) { $tasks += [System.Threading.Tasks.Task]$stderr.task }
        if ($tasks.Count -eq 0) { throw ($Label + ' has no pending bounded stream read') }
        $remaining = [int][Math]::Floor($DeadlineElapsedMs - $script:Clock.ElapsedMilliseconds)
        if ($remaining -le 0) { throw ($Label + ' timed out at its absolute phase cutoff') }
        try { $completedIndex = [System.Threading.Tasks.Task]::WaitAny([System.Threading.Tasks.Task[]]$tasks, $remaining) }
        catch { throw ($Label + ' stream wait failed: ' + $_.Exception.Message) }
        if ($completedIndex -lt 0) { throw ($Label + ' timed out at its absolute phase cutoff') }
    }
}

function Write-ProtocolLine {
    param([object]$Value)
    $json = ConvertTo-Json -InputObject $Value -Depth 100 -Compress
    $script:Driver.StandardInput.WriteLine($json)
    $script:Driver.StandardInput.Flush()
}

function Get-SyntheticSnapshot {
    $sources = [ordered]@{}; foreach ($path in $script:SourcePaths) { $sources[$path] = ('a' * 64) }
    $fixtures = [ordered]@{}; foreach ($path in $script:FixturePaths) { $fixtures[$path] = ('b' * 64) }
    $readInputs = [ordered]@{}; $readInputs[$script:ReadInputPaths[0]] = ('c' * 64)
    $protected = [ordered]@{}; for ($i = 0; $i -lt 199; $i++) { $protected[('E:/projects/ladybug/synthetic/protected-' + $i.ToString('D3') + '.bin')] = ('d' * 64) }
    $qualified = [ordered]@{}; foreach ($path in $script:QualifiedInputPaths) { $qualified[$path] = ('e' * 64) }
    return [pscustomobject]@{
        source_sha256 = [pscustomobject]$sources; fixture_sha256 = [pscustomobject]$fixtures; read_inputs_sha256 = [pscustomobject]$readInputs
        ticket_sha256 = ('f' * 64); manifest_sha256 = ('0' * 64); protected_files_sha256 = [pscustomobject]$protected
        qualified_seven_inputs_sha256 = [pscustomobject]$qualified; python_sha256 = $script:PythonSha256
    }
}

function Copy-JsonValue {
    param([object]$Value)
    return (ConvertFrom-Json -InputObject (ConvertTo-Json -InputObject $Value -Depth 100 -Compress) -ErrorAction Stop)
}

function ConvertFrom-HostEvidenceJson {
    param([string]$Json)
    $value = ConvertFrom-Json -InputObject $Json -ErrorAction Stop
    foreach ($name in @('started_utc','evidence_written_utc')) {
        $property = $value.PSObject.Properties[$name]
        if ($null -eq $property) { continue }
        $pattern = '"' + [regex]::Escape($name) + '"\s*:\s*"([^"\\]*)"'
        $match = [regex]::Match($Json, $pattern)
        if (-not $match.Success) { throw ('host evidence timestamp was not a plain JSON string: ' + $name) }
        $property.Value = $match.Groups[1].Value
    }
    return $value
}

function New-SyntheticCase {
    param([string]$CaseId)
    $controls = New-Object System.Collections.ArrayList
    foreach ($controlId in $script:CaseSubcontrols[$CaseId]) {
        [void]$controls.Add([pscustomobject]@{ id = $controlId; status = 'PASS'; observed = [pscustomobject]@{ fixture = 'independent-positive' } })
    }
    return [pscustomobject]@{
        case_id = $CaseId; expected = $script:ExpectedByCase[$CaseId]; status = 'PASS'
        observations = [pscustomobject]@{ subcontrols = @($controls.ToArray()); oracle_fixture = 'independent host-authored synthetic record' }
    }
}

function New-SyntheticRecords {
    param([string]$SyntheticPhase)
    $nonce = '0123456789abcdef0123456789abcdef'
    $manifest = '0' * 64
    $ticket = 'f' * 64
    $snapshot = Get-SyntheticSnapshot
    $supervisor = [pscustomobject]@{ pid = 1001; start_ticks = 9001; executable = $script:PythonResolved; executable_sha256 = $script:PythonSha256 }
    $worker = [pscustomobject]@{ pid = 1002; start_ticks = 9002; executable = $script:PythonResolved; executable_sha256 = $script:PythonSha256 }
    $ready = [pscustomobject]@{
        kind = 'READY'; phase = $SyntheticPhase; nonce = $nonce; manifest_sha256 = $manifest; ticket_sha256 = $ticket
        source_sha256 = $snapshot.source_sha256; fixture_sha256 = $snapshot.fixture_sha256; read_inputs_sha256 = $snapshot.read_inputs_sha256
        supervisor_identity = $supervisor; supervisor_elapsed_ms = 4
    }
    $cases = New-Object System.Collections.ArrayList
    foreach ($caseId in $script:WorkerCaseIds[$SyntheticPhase]) { [void]$cases.Add((New-SyntheticCase $caseId)) }
    $terminal = [pscustomobject]@{
        kind = 'TERMINAL'; phase = $SyntheticPhase; nonce = $nonce; manifest_sha256 = $manifest; ticket_sha256 = $ticket
        source_sha256 = $snapshot.source_sha256; fixture_sha256 = $snapshot.fixture_sha256; read_inputs_sha256 = $snapshot.read_inputs_sha256
        status = 'SUBJECT_COMPLETE'; phase_elapsed_ms = 80; supervisor_identity = $supervisor; worker_identity = $worker
        worker_exit = [pscustomobject]@{ wait_confirmed = $true; returncode = 0 }; cases = @($cases.ToArray())
        ledgers = [pscustomobject]@{ service_calls = @(); factory_calls = @(); reader_count = 0; raw_record_count = 0; real_factory_calls = 0; real_gdb_calls = 0; real_network_calls = 0 }
        preservation = [pscustomobject]@{ before = $snapshot; after = (Copy-JsonValue $snapshot) }; failure = $null
    }
    return [pscustomobject]@{ nonce = $nonce; manifest = $manifest; ticket = $ticket; snapshot = $snapshot; ready = $ready; terminal = $terminal }
}

function New-SyntheticOracleRows {
    $rows = New-Object System.Collections.ArrayList
    foreach ($id in $script:HostOracleRowIds) {
        if ($id -ceq 'CLAIM_COLLISION_PRESERVES_BYTES') {
            [void]$rows.Add([pscustomobject]@{ id = $id; expected = 'REJECT_AND_PRESERVE'; observed = 'REJECT_AND_PRESERVE'; status = 'PASS'; original_sha256 = ('a' * 64); after_sha256 = ('a' * 64) })
        } else {
            $expected = Get-HostOracleExpected $id
            [void]$rows.Add([pscustomobject]@{ id = $id; expected = $expected; observed = $expected; status = 'PASS'; reason = 'synthetic retained-shape oracle row' })
        }
    }
    return @($rows.ToArray())
}

function New-SyntheticRetainedProof {
    $records = New-SyntheticRecords 'stop-observation-admission'
    $hostClaim = [pscustomobject]@{ exclusive = $true; collision_preserved = $true; launch_argv = $script:LaunchArgv }
    $started = '2026-10-20T12:34:56.1234567Z'
    $claim = [pscustomobject]@{ phase = 'stop-observation-admission'; nonce = $records.nonce; manifest_sha256 = $records.manifest; attempt = 1; started_utc = $started }
    $receipt = [pscustomobject]@{
        schema = 'ladybug.feat010.sro.host-phase-evidence.v1'; phase = 'stop-observation-admission'; attempt = 1; nonce = $records.nonce
        manifest_sha256 = $records.manifest; ticket_sha256 = $records.ticket
        source_sha256 = $records.snapshot.source_sha256; fixture_sha256 = $records.snapshot.fixture_sha256; read_inputs_sha256 = $records.snapshot.read_inputs_sha256
        status = 'PASS'; admitted = $true; host_claim = $hostClaim; host_oracle = (New-SyntheticOracleRows); host_cases = @()
        ready = $records.ready; terminal = $records.terminal; worker_exit = $records.terminal.worker_exit
        driver_exit_confirmed = $true; driver_exit_code = 0; driver_is_wsl_only = $true
        protocol_records = @($records.ready, $records.terminal)
        protocol_lines = @((ConvertTo-Json -InputObject $records.ready -Depth 100 -Compress), (ConvertTo-Json -InputObject $records.terminal -Depth 100 -Compress))
        stderr = ''; stdout_tail = ''; failure_category = $null; failure_message = $null; failure_detail = $null
        transport_failure_category = $null; transport_failure_message = $null; transport_failure_detail = $null
        preservation = [pscustomobject]@{ before = $records.snapshot; after = (Copy-JsonValue $records.snapshot) }
        preservation_equal = $true; subject_complete = $true; go_budget_ms = 20000; elapsed_ms = 100; maximum_ms = 30000
        evidence_write_started_elapsed_ms = 100; evidence_written_utc = $started
    }
    return [pscustomobject]@{ claim = $claim; receipt = $receipt; snapshot = $records.snapshot }
}

function Test-HostOracleProof {
    param([object]$Rows)
    if ($Rows -isnot [System.Array]) { return $false }
    $actual = @($Rows)
    if ($actual.Count -ne $script:HostOracleRowIds.Count) { return $false }
    for ($i = 0; $i -lt $script:HostOracleRowIds.Count; $i++) {
        $row = $actual[$i]
        $id = $script:HostOracleRowIds[$i]
        if ($id -ceq 'CLAIM_COLLISION_PRESERVES_BYTES') {
            if (-not (Test-ObjectShape $row @('id','expected','observed','status','original_sha256','after_sha256')) -or $row.id -isnot [string] -or $row.expected -isnot [string] -or $row.observed -isnot [string] -or $row.status -isnot [string] -or $row.id -cne $id -or $row.expected -cne 'REJECT_AND_PRESERVE' -or $row.observed -cne 'REJECT_AND_PRESERVE' -or $row.status -cne 'PASS' -or -not (Test-Sha256 $row.original_sha256) -or $row.original_sha256 -cne $row.after_sha256) { return $false }
        } else {
            if (-not (Test-ObjectShape $row @('id','expected','observed','status','reason')) -or $row.id -isnot [string] -or $row.expected -isnot [string] -or $row.observed -isnot [string] -or $row.status -isnot [string] -or $row.id -cne $id -or $row.status -cne 'PASS') { return $false }
            $expected = Get-HostOracleExpected $id
            if ($row.expected -cne $expected -or $row.observed -cne $expected -or ($null -ne $row.reason -and $row.reason -isnot [string])) { return $false }
        }
    }
    return $true
}

function Get-HostOracleExpected {
    param([string]$Id)
    if ($Id -match '(_VALID$|^PREV_VALID$|^TERM_FAIL_UNCONFIRMED_NULL_EXIT$|^PREV_JSON_TIMESTAMP_ROUNDTRIP$|^STREAM_STDERR_CAP_NO_NEWLINE$|^FILE_EXACT_CAP$|^FILE_UTF8_SPLIT_BOM$)') { return 'ACCEPT' }
    return 'REJECT'
}

function Test-RetainedPhaseClaim {
    param([object]$Claim, [string]$ExpectedPhase, [string]$Manifest, [ref]$Reason)
    $Reason.Value = 'retained phase claim rejected'
    $claimKeys = @('phase','nonce','manifest_sha256','attempt','started_utc')
    if (-not (Test-ObjectShape $Claim $claimKeys)) { return $false }
    foreach ($name in @('phase','nonce','manifest_sha256','started_utc')) { if ($Claim.PSObject.Properties[$name].Value -isnot [string]) { return $false } }
    if ($Claim.phase -cne $ExpectedPhase -or $Claim.nonce -cnotmatch '^[0-9a-f]{32}$' -or $Claim.manifest_sha256 -cne $Manifest -or -not (Test-ExactInteger $Claim.attempt) -or $Claim.attempt -ne 1) { return $false }
    $Reason.Value = $null
    return $true
}

function Test-RetainedPhaseEvidence {
    param([object]$Claim, [object]$Receipt, [string]$ExpectedPhase, [string]$Manifest, [string]$Ticket, [object]$Sources, [object]$Fixtures, [object]$ReadInputs, [object]$ExpectedPreservation, [ref]$Reason)
    $Reason.Value = 'retained phase evidence rejected'
    $claimReason = $null
    if (-not (Test-RetainedPhaseClaim $Claim $ExpectedPhase $Manifest ([ref]$claimReason))) { return $false }
    $receiptKeys = @('schema','phase','attempt','nonce','manifest_sha256','ticket_sha256','source_sha256','fixture_sha256','read_inputs_sha256','status','admitted','host_claim','host_oracle','host_cases','ready','terminal','worker_exit','driver_exit_confirmed','driver_exit_code','driver_is_wsl_only','protocol_records','protocol_lines','stderr','stdout_tail','failure_category','failure_message','failure_detail','transport_failure_category','transport_failure_message','transport_failure_detail','preservation','preservation_equal','subject_complete','go_budget_ms','elapsed_ms','maximum_ms','evidence_write_started_elapsed_ms','evidence_written_utc')
    if (-not (Test-ObjectShape $Receipt $receiptKeys)) { return $false }
    foreach ($name in @('schema','phase','nonce','manifest_sha256','ticket_sha256','status','evidence_written_utc','stderr','stdout_tail')) { if ($Receipt.PSObject.Properties[$name].Value -isnot [string]) { return $false } }
    if ($Receipt.schema -cne 'ladybug.feat010.sro.host-phase-evidence.v1' -or $Receipt.phase -cne $ExpectedPhase -or -not (Test-ExactInteger $Receipt.attempt) -or $Receipt.attempt -ne 1 -or $Receipt.nonce -cne $Claim.nonce -or $Receipt.manifest_sha256 -cne $Manifest -or $Receipt.ticket_sha256 -cne $Ticket) { return $false }
    if (-not (Test-HashObject $Receipt.source_sha256 $Sources) -or -not (Test-HashObject $Receipt.fixture_sha256 $Fixtures) -or -not (Test-HashObject $Receipt.read_inputs_sha256 $ReadInputs)) { return $false }
    if ($Receipt.status -cne 'PASS' -or -not (Test-ExactBoolean $Receipt.admitted) -or $Receipt.admitted -ne $true -or -not (Test-HostClaim $Receipt.host_claim)) { return $false }
    $maximum = [int]$script:PhaseLimits[$ExpectedPhase]
    $readyReason = $null
    if (-not (Test-AdmissionEnvelope $Receipt.ready $ExpectedPhase $Claim.nonce $Manifest $Ticket $Sources $Fixtures $ReadInputs $maximum ([ref]$readyReason))) { return $false }
    $terminalReason = $null
    if (-not (Test-TerminalRecord $Receipt.terminal $ExpectedPhase $Claim.nonce $Manifest $Ticket $Sources $Fixtures $ReadInputs $Receipt.ready.supervisor_identity $maximum ([ref]$terminalReason)) -or $Receipt.terminal.status -cne 'SUBJECT_COMPLETE') { return $false }
    if (-not (Test-ObjectShape $Receipt.worker_exit @('wait_confirmed','returncode')) -or $Receipt.worker_exit.wait_confirmed -isnot [bool] -or $Receipt.worker_exit.wait_confirmed -ne $Receipt.terminal.worker_exit.wait_confirmed -or -not (Test-ExactInteger $Receipt.worker_exit.returncode) -or $Receipt.worker_exit.returncode -ne $Receipt.terminal.worker_exit.returncode) { return $false }
    if (-not (Test-ExactBoolean $Receipt.driver_exit_confirmed) -or $Receipt.driver_exit_confirmed -ne $true -or -not (Test-ExactInteger $Receipt.driver_exit_code) -or $Receipt.driver_exit_code -ne 0 -or -not (Test-ExactBoolean $Receipt.driver_is_wsl_only) -or $Receipt.driver_is_wsl_only -ne $true) { return $false }
    if (-not (Test-ExactBoolean $Receipt.preservation_equal) -or $Receipt.preservation_equal -ne $true -or -not (Test-ObjectShape $Receipt.preservation @('before','after')) -or -not (Test-PreservationEqual $Receipt.preservation.before $ExpectedPreservation) -or -not (Test-PreservationEqual $Receipt.preservation.after $ExpectedPreservation) -or -not (Test-PreservationEqual $Receipt.terminal.preservation.before $ExpectedPreservation) -or -not (Test-PreservationEqual $Receipt.terminal.preservation.after $ExpectedPreservation)) { return $false }
    if (-not (Test-ExactBoolean $Receipt.subject_complete) -or $Receipt.subject_complete -ne $true -or -not (Test-ExactInteger $Receipt.go_budget_ms) -or $Receipt.go_budget_ms -le 0 -or $Receipt.go_budget_ms -gt $maximum) { return $false }
    foreach ($field in @('elapsed_ms','maximum_ms','evidence_write_started_elapsed_ms')) { if (-not (Test-ExactInteger $Receipt.PSObject.Properties[$field].Value)) { return $false } }
    if ($Receipt.elapsed_ms -lt 0 -or $Receipt.elapsed_ms -gt $maximum -or $Receipt.maximum_ms -ne $maximum -or $Receipt.evidence_write_started_elapsed_ms -ne $Receipt.elapsed_ms -or $Receipt.terminal.phase_elapsed_ms -gt $Receipt.elapsed_ms) { return $false }
    if ($Receipt.evidence_written_utc -isnot [string] -or $Receipt.stderr -isnot [string] -or $Receipt.stdout_tail -cne '' -or $Receipt.failure_category -ne $null -or $Receipt.failure_message -ne $null -or $Receipt.failure_detail -ne $null -or $Receipt.transport_failure_category -ne $null -or $Receipt.transport_failure_message -ne $null -or $Receipt.transport_failure_detail -ne $null) { return $false }
    if ($Receipt.protocol_records -isnot [System.Array] -or @($Receipt.protocol_records).Count -ne 2 -or $Receipt.protocol_lines -isnot [System.Array] -or @($Receipt.protocol_lines).Count -ne 2) { return $false }
    if (-not (Test-JsonValueEqual $Receipt.protocol_records[0] $Receipt.ready) -or -not (Test-JsonValueEqual $Receipt.protocol_records[1] $Receipt.terminal)) { return $false }
    if (-not (Test-AdmissionEnvelope $Receipt.protocol_records[0] $ExpectedPhase $Claim.nonce $Manifest $Ticket $Sources $Fixtures $ReadInputs $maximum ([ref]$readyReason)) -or -not (Test-TerminalRecord $Receipt.protocol_records[1] $ExpectedPhase $Claim.nonce $Manifest $Ticket $Sources $Fixtures $ReadInputs $Receipt.ready.supervisor_identity $maximum ([ref]$terminalReason))) { return $false }
    $protocolLines = @($Receipt.protocol_lines)
    for ($lineIndex = 0; $lineIndex -lt $protocolLines.Count; $lineIndex++) {
        $line = $protocolLines[$lineIndex]
        if ($line -isnot [string] -or $line.Length -eq 0 -or -not (Test-ProtocolLineWithinLimit $line)) { return $false }
        if (-not (Test-JsonWithUniqueKeys $line $script:ProtocolLineMaximumCharacters)) { return $false }
        try { $lineRecord = ConvertFrom-Json -InputObject $line -ErrorAction Stop } catch { return $false }
        if ($lineRecord.kind -ceq 'READY') {
            if ($lineIndex -ne 0 -or -not (Test-JsonValueEqual $lineRecord $Receipt.ready) -or -not (Test-AdmissionEnvelope $lineRecord $ExpectedPhase $Claim.nonce $Manifest $Ticket $Sources $Fixtures $ReadInputs $maximum ([ref]$readyReason))) { return $false }
        } elseif ($lineRecord.kind -ceq 'TERMINAL') {
            if ($lineIndex -ne 1 -or -not (Test-JsonValueEqual $lineRecord $Receipt.terminal) -or -not (Test-TerminalRecord $lineRecord $ExpectedPhase $Claim.nonce $Manifest $Ticket $Sources $Fixtures $ReadInputs $Receipt.ready.supervisor_identity $maximum ([ref]$terminalReason))) { return $false }
        } else { return $false }
    }
    if ($ExpectedPhase -ceq 'stop-observation-admission') {
        if (-not (Test-HostOracleProof $Receipt.host_oracle) -or @($Receipt.host_cases).Count -ne 0) { return $false }
    } elseif (@($Receipt.host_oracle).Count -ne 0) { return $false }
    if ($ExpectedPhase -ceq 'stop-observation-compatibility') {
        if (@($Receipt.host_cases).Count -ne 1 -or -not (Test-HostC06 $Receipt.host_cases[0] $Receipt.terminal $Receipt.driver_exit_confirmed $Receipt.driver_exit_code $Receipt.preservation_equal)) { return $false }
    } elseif (@($Receipt.host_cases).Count -ne 0) { return $false }
    $finalContext = [pscustomobject]@{ phase = $ExpectedPhase; host_case = if (@($Receipt.host_cases).Count -eq 1) { $Receipt.host_cases[0] } else { $null } }
    $finalReason = $null
    if (-not (Test-FinalAdmission $Receipt.terminal $finalContext $Receipt.driver_exit_confirmed $Receipt.driver_exit_code $Receipt.preservation_equal $Receipt.admitted $Receipt.elapsed_ms $maximum ([ref]$finalReason))) { return $false }
    $Reason.Value = $null
    return $true
}

function Invoke-OracleControl {
    param([string]$Id, [string]$Validator, [object]$Value, [bool]$ExpectedAccepted, [object]$Context)
    $reason = $null
    if ($Validator -ceq 'ready') {
        $accepted = Test-AdmissionEnvelope $Value $Context.phase $Context.nonce $Context.manifest $Context.ticket $Context.snapshot.source_sha256 $Context.snapshot.fixture_sha256 $Context.snapshot.read_inputs_sha256 30000 ([ref]$reason)
    } elseif ($Validator -ceq 'terminal') {
        $accepted = Test-TerminalRecord $Value $Context.phase $Context.nonce $Context.manifest $Context.ticket $Context.snapshot.source_sha256 $Context.snapshot.fixture_sha256 $Context.snapshot.read_inputs_sha256 $Context.ready.supervisor_identity 30000 ([ref]$reason)
    } elseif ($Validator -ceq 'retained') {
        $accepted = Test-RetainedPhaseEvidence $Value.claim $Value.receipt 'stop-observation-admission' $Context.manifest $Context.ticket $Context.snapshot.source_sha256 $Context.snapshot.fixture_sha256 $Context.snapshot.read_inputs_sha256 $Context.snapshot ([ref]$reason)
    } elseif ($Validator -ceq 'json') {
        $accepted = Test-JsonWithUniqueKeys $Value $script:ProtocolLineMaximumCharacters
    } elseif ($Validator -ceq 'claim') {
        $accepted = Test-HostClaim $Value
    } else {
        $accepted = Test-FinalAdmission $Value.terminal $Context $Value.driver_wait $Value.driver_exit $Value.preservation_equal $Value.finalized $Value.elapsed_ms 30000 ([ref]$reason)
    }
    $passed = (($accepted -eq $ExpectedAccepted))
    return [pscustomobject]@{ id = $Id; expected = $(if ($ExpectedAccepted) { 'ACCEPT' } else { 'REJECT' }); observed = $(if ($accepted) { 'ACCEPT' } else { 'REJECT' }); status = $(if ($passed) { 'PASS' } else { 'FAIL' }); reason = $reason }
}

function New-AdmissionVectorStream {
    param([object]$Vector)
    switch ($Vector.input_kind) {
        'repeat_byte' {
            $text = [System.String]::new([char][byte]$Vector.input_byte, [int]$Vector.input_count)
            $bytes = [System.Text.Encoding]::ASCII.GetBytes($text)
            return [System.IO.MemoryStream]::new($bytes, $false)
        }
        'bom_repeat_suffix' {
            $bytes = New-Object System.Collections.Generic.List[byte]
            foreach ($item in $Vector.prefix_bytes) { $bytes.Add([byte]$item) }
            for ($index = 0; $index -lt [int]$Vector.repeat_count; $index++) { $bytes.Add([byte]$Vector.repeat_byte) }
            foreach ($item in $Vector.suffix_bytes) { $bytes.Add([byte]$item) }
            return [System.IO.MemoryStream]::new($bytes.ToArray(), $false)
        }
        'literal_bytes' {
            $bytes = New-Object System.Collections.Generic.List[byte]
            foreach ($item in $Vector.input_bytes) { $bytes.Add([byte]$item) }
            return [System.IO.MemoryStream]::new($bytes.ToArray(), $false)
        }
        default { throw ('unsupported descriptor file-reader vector: ' + $Vector.input_kind) }
    }
}

function Invoke-AdmissionFileVector {
    param([object]$Vector)
    $stream = $null
    $observation = $null
    $actualPosition = $null
    try {
        $stream = New-AdmissionVectorStream $Vector
        $observation = Read-BoundedUtf8Stream $stream (Get-HostReadCutoffElapsed) $true
        $actualPosition = [long]$stream.Position
    } catch {
        $reason = 'stage=vector_read;error=' + (Limit-CleanupDetail $_.Exception.Message)
        if ($null -ne $observation) {
            $reason += ';position=' + [string]$observation.position + ';actual_position=' + [string]$observation.actual_position + ';retained=' + [string]$observation.retained_bytes + ';units=' + [string]$observation.text_units + ';decode=' + [string]$observation.whole_document_decode_attempted + ';rejection=' + [string]$observation.rejection + ';sha256=' + [string]$observation.sha256 + ';prefix_b64=' + [string]$observation.prefix_b64
        } else { $reason += ';observation=unavailable' }
        return [pscustomobject]@{ id = [string]$Vector.id; expected = [string]$Vector.expected; observed = 'UNKNOWN'; status = 'FAIL'; reason = $reason }
    } finally { if ($null -ne $stream) { $stream.Dispose() } }
    $acceptedExpected = ($Vector.expected -ceq 'ACCEPT')
    $passed = ($observation.accepted -eq $acceptedExpected -and $observation.position -eq $Vector.expected_position -and $actualPosition -eq $Vector.expected_position)
    if ($acceptedExpected) {
        $passed = $passed -and $observation.retained_bytes -eq $Vector.expected_retained_bytes -and $observation.text_units -eq $Vector.expected_text_units -and $observation.whole_document_decode_attempted
        if ($Vector.expected_text -ceq 'ASCII_A_REPEAT') {
            $passed = $passed -and $observation.text.Length -eq $Vector.expected_text_units -and $observation.text.Trim([char[]]@('A')).Length -eq 0
        } elseif ($Vector.expected_text -ceq 'ASCII_A_4092_THEN_U00E9_Z') {
            $passed = $passed -and $observation.text.Length -eq $Vector.expected_text_units -and
                $observation.text.Substring(0, [int]$Vector.repeat_count).Trim([char[]]@('A')).Length -eq 0 -and
                [int][char]$observation.text[[int]$Vector.repeat_count] -eq 233 -and $observation.text.Substring($observation.text.Length - 1) -ceq 'Z'
        } else { $passed = $false }
    } else {
        $passed = $passed -and $observation.rejection -ceq $Vector.rejection
        if ($null -ne $Vector.maximum_retained_bytes) { $passed = $passed -and $observation.retained_bytes -le $Vector.maximum_retained_bytes }
        if ($null -ne $Vector.whole_document_decode_allowed) { $passed = $passed -and $observation.whole_document_decode_attempted -eq $Vector.whole_document_decode_allowed }
        if ($null -ne $Vector.expected_text_units) { $passed = $passed -and $observation.text_units -eq $Vector.expected_text_units }
        if ($Vector.id -ceq 'FILE_EMPTY_JSON_REJECT') { $passed = $passed -and $observation.whole_document_decode_attempted -and $observation.text_units -eq 0 }
    }
    $reason = 'position=' + $observation.position + ';actual_position=' + $actualPosition + ';retained=' + $observation.retained_bytes + ';units=' + $observation.text_units + ';decode=' + $observation.whole_document_decode_attempted + ';rejection=' + $observation.rejection + ';sha256=' + $observation.sha256 + ';prefix_b64=' + $observation.prefix_b64
    return [pscustomobject]@{
        id = [string]$Vector.id; expected = [string]$Vector.expected
        observed = if ($observation.accepted) { 'ACCEPT' } else { 'REJECT' }
        status = if ($passed) { 'PASS' } else { 'FAIL' }; reason = $reason
    }
}

function Get-HostScalarPathValue {
    param([object]$Value, [string]$Path)
    $current = $Value
    foreach ($part in $Path.Split('.')) {
        if ($null -eq $current) { return $null }
        if ($current -is [System.Array]) {
            if ($part -notmatch '^\d+$' -or [int]$part -ge $current.Count) { return $null }
            $current = $current[[int]$part]
        } else {
            $property = $current.PSObject.Properties[$part]
            if ($null -eq $property) { return $null }
            $current = $property.Value
        }
    }
    return ,$current
}

function Set-HostScalarPathValue {
    param([object]$Value, [string]$Path, [object]$NewValue)
    $parts = $Path.Split('.')
    $current = $Value
    for ($i = 0; $i -lt ($parts.Length - 1); $i++) {
        $part = $parts[$i]
        if ($null -eq $current) { return $false }
        if ($current -is [System.Array]) {
            if ($part -notmatch '^\d+$' -or [int]$part -ge $current.Count) { return $false }
            $current = $current[[int]$part]
        } else {
            $property = $current.PSObject.Properties[$part]
            if ($null -eq $property) { return $false }
            $current = $property.Value
        }
    }
    $last = $parts[$parts.Length - 1]
    if ($current -is [System.Array]) {
        if ($last -notmatch '^\d+$' -or [int]$last -ge $current.Count) { return $false }
        $current[[int]$last] = $NewValue
        return $true
    }
    $target = $current.PSObject.Properties[$last]
    if ($null -eq $target) { return $false }
    $target.Value = $NewValue
    return $true
}

function Copy-HostScalarProbeValue {
    param([object]$Value, [string]$Family)
    if ($Family -ceq 'STR_RETAINED_FIELDS') {
        $claimJson = ConvertTo-Json -InputObject $Value.claim -Depth 100 -Compress
        $receiptJson = ConvertTo-Json -InputObject $Value.receipt -Depth 100 -Compress
        return [pscustomobject]@{
            claim = ConvertFrom-HostEvidenceJson $claimJson
            receipt = ConvertFrom-HostEvidenceJson $receiptJson
            snapshot = Copy-JsonValue $Value.snapshot
        }
    }
    return Copy-JsonValue $Value
}

function Test-HostScalarProbe {
    param([string]$Family, [object]$Value, [object]$Context, [string]$Variant)
    $reason = $null
    switch ($Family) {
        'STR_FREEZE_FIELDS' { return (Test-FreezeEnvelope $Value ([ref]$reason)) }
        'STR_READY_FIELDS' {
            return (Test-AdmissionEnvelope $Value $Context.phase $Context.nonce $Context.manifest $Context.ticket $Context.snapshot.source_sha256 $Context.snapshot.fixture_sha256 $Context.snapshot.read_inputs_sha256 30000 ([ref]$reason))
        }
        'STR_TERMINAL_FIELDS' {
            return (Test-TerminalRecord $Value $Context.phase $Context.nonce $Context.manifest $Context.ticket $Context.snapshot.source_sha256 $Context.snapshot.fixture_sha256 $Context.snapshot.read_inputs_sha256 $Context.ready.supervisor_identity 30000 ([ref]$reason))
        }
        'STR_CASE_FIELDS' { return (Test-TerminalRecord $Value.terminal $Context.phase $Context.nonce $Context.manifest $Context.ticket $Context.snapshot.source_sha256 $Context.snapshot.fixture_sha256 $Context.snapshot.read_inputs_sha256 $Context.ready.supervisor_identity 30000 ([ref]$reason)) }
        'STR_SUBCONTROL_FIELDS' { return (Test-TerminalRecord $Value.terminal $Context.phase $Context.nonce $Context.manifest $Context.ticket $Context.snapshot.source_sha256 $Context.snapshot.fixture_sha256 $Context.snapshot.read_inputs_sha256 $Context.ready.supervisor_identity 30000 ([ref]$reason)) }
        'STR_ORACLE_FIELDS' { return (Test-HostOracleProof $Value.rows) }
        'STR_C06_FIELDS' { return (Test-HostC06 $Value.case $Value.terminal $true 0 $true) }
        'STR_FINAL_FIELDS' { return (Test-FinalAdmission $Value.terminal $Value.context $true 0 $true $true 100 30000 ([ref]$reason)) }
        'STR_RETAINED_FIELDS' { return (Test-RetainedPhaseEvidence $Value.claim $Value.receipt 'stop-observation-admission' $Context.manifest $Context.ticket $Context.snapshot.source_sha256 $Context.snapshot.fixture_sha256 $Context.snapshot.read_inputs_sha256 $Context.snapshot ([ref]$reason)) }
        default { return $false }
    }
}

function Invoke-HostScalarFamilyControl {
    param([string]$Family, [string[]]$Members, [object[]]$Variants, [object]$Context)
    $orderedEvidence = New-Object System.Collections.ArrayList
    foreach ($variant in $Variants) {
        foreach ($member in $Members) {
            $probePath = $member
            if ($null -ne $variant.paths -and $variant.paths.ContainsKey($member)) { $probePath = [string]$variant.paths[$member] }
            try {
                $baseline = Copy-HostScalarProbeValue $variant.value $Family
                $baselineAccepted = Test-HostScalarProbe $Family $baseline $Context $variant.label
            } catch {
                [void]$orderedEvidence.Add(($variant.label + ':' + $member + '=BASELINE_ERROR:' + (Limit-CleanupDetail $_.Exception.Message)))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            if (-not $baselineAccepted) {
                [void]$orderedEvidence.Add(($variant.label + ':' + $member + '=BASELINE_REJECT;mutation=NOT_ATTEMPTED'))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            try { $original = Get-HostScalarPathValue $baseline $probePath }
            catch {
                [void]$orderedEvidence.Add(($variant.label + ':' + $member + '=PATH_READ_ERROR:' + (Limit-CleanupDetail $_.Exception.Message)))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            if ($original -isnot [string]) {
                [void]$orderedEvidence.Add(($variant.label + ':' + $member + '=BASELINE_MEMBER_NOT_STRING;mutation=NOT_ATTEMPTED'))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            try {
                $mutation = Copy-HostScalarProbeValue $variant.value $Family
                $mutationMade = Set-HostScalarPathValue -Value $mutation -Path $probePath -NewValue ([object[]]@([string]$original))
            } catch {
                [void]$orderedEvidence.Add(($variant.label + ':' + $member + '=MUTATION_SETUP_ERROR:' + (Limit-CleanupDetail $_.Exception.Message)))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            if (-not $mutationMade) {
                [void]$orderedEvidence.Add(($variant.label + ':' + $member + '=MUTATION_PATH_MISSING'))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            try { $mutatedAccepted = Test-HostScalarProbe $Family $mutation $Context $variant.label }
            catch {
                [void]$orderedEvidence.Add(($variant.label + ':' + $member + '=MUTATION_VALIDATOR_ERROR:' + (Limit-CleanupDetail $_.Exception.Message)))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            [void]$orderedEvidence.Add(($variant.label + ':' + $member + '=ACCEPT/' + $(if (-not $mutatedAccepted) { 'REJECT' } else { 'MUTATION_ACCEPT' })))
            if ($mutatedAccepted) { return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'ACCEPT'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) } }
        }
    }
    if ($Family -ceq 'STR_READY_FIELDS') {
        $typeValues = @(
            [pscustomobject]@{ name = 'empty_array'; value = [object[]]@() },
            [pscustomobject]@{ name = 'null'; value = $null },
            [pscustomobject]@{ name = 'boolean'; value = $true },
            [pscustomobject]@{ name = 'integer'; value = [int]7 },
            [pscustomobject]@{ name = 'float'; value = [double]7.25 },
            [pscustomobject]@{ name = 'object'; value = [pscustomobject]@{ marker = 'not-a-string' } }
        )
        foreach ($typeCase in $typeValues) {
            try {
                $baseline = Copy-HostScalarProbeValue $Variants[0].value $Family
                $baselineAccepted = Test-HostScalarProbe $Family $baseline $Context $Variants[0].label
            } catch {
                [void]$orderedEvidence.Add(('kind<' + $typeCase.name + '>=BASELINE_ERROR:' + (Limit-CleanupDetail $_.Exception.Message)))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            if (-not $baselineAccepted) {
                [void]$orderedEvidence.Add(('kind<' + $typeCase.name + '>=BASELINE_REJECT;mutation=NOT_ATTEMPTED'))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            try {
                $mutation = Copy-HostScalarProbeValue $Variants[0].value $Family
                $mutationMade = Set-HostScalarPathValue -Value $mutation -Path 'kind' -NewValue $typeCase.value
            } catch {
                [void]$orderedEvidence.Add(('kind<' + $typeCase.name + '>=MUTATION_SETUP_ERROR:' + (Limit-CleanupDetail $_.Exception.Message)))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            if (-not $mutationMade) {
                [void]$orderedEvidence.Add(('kind<' + $typeCase.name + '>=MUTATION_PATH_MISSING'))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            try { $mutatedAccepted = Test-HostScalarProbe $Family $mutation $Context $Variants[0].label }
            catch {
                [void]$orderedEvidence.Add(('kind<' + $typeCase.name + '>=MUTATION_VALIDATOR_ERROR:' + (Limit-CleanupDetail $_.Exception.Message)))
                return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'UNKNOWN'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) }
            }
            [void]$orderedEvidence.Add(('kind<' + $typeCase.name + '>=ACCEPT/' + $(if (-not $mutatedAccepted) { 'REJECT' } else { 'MUTATION_ACCEPT' })))
            if ($mutatedAccepted) { return [pscustomobject]@{ id = $Family; expected = 'REJECT'; observed = 'ACCEPT'; status = 'FAIL'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray())) } }
        }
    }
    $expected = 'REJECT'
    return [pscustomobject]@{
        id = $Family; expected = $expected; observed = $expected
        status = 'PASS'; reason = [string]::Join(';', [string[]]@($orderedEvidence.ToArray()))
    }
}

function Add-HostOracleControlResult {
    param([System.Collections.ArrayList]$Results, [object]$Row)
    [void]$Results.Add($Row)
    $script:HostOracle = @($Results.ToArray())
    if ($Row.status -cne 'PASS') { throw ('host-oracle control failed: ' + (ConvertTo-Json -InputObject $Row -Depth 10 -Compress)) }
}

function Invoke-HostOracle {
    param([object]$ActualHostClaim, [string]$ClaimPath, [string]$Nonce)
    $context = New-SyntheticRecords 'stop-observation-admission'
    $results = New-Object System.Collections.ArrayList
    Add-HostOracleControlResult $results (Invoke-OracleControl 'READY_VALID' 'ready' $context.ready $true $context)
    foreach ($id in @('READY_WRONG_NONCE','READY_WRONG_MANIFEST','READY_WRONG_SOURCE','READY_WRONG_FIXTURE','READY_WRONG_READ_INPUT','READY_WRONG_TICKET','READY_BOOL_ELAPSED','READY_MISSING_IDENTITY')) {
        $copy = Copy-JsonValue $context.ready
        switch ($id) {
            'READY_WRONG_NONCE' { $copy.nonce = 'ffffffffffffffffffffffffffffffff' }
            'READY_WRONG_MANIFEST' { $copy.manifest_sha256 = '1' * 64 }
            'READY_WRONG_SOURCE' { $copy.source_sha256.'service/gdb.py' = '1' * 64 }
            'READY_WRONG_FIXTURE' { $copy.fixture_sha256.'evidence/sro-stop-independent-fixtures.json' = '1' * 64 }
            'READY_WRONG_READ_INPUT' { $copy.read_inputs_sha256.'stutter-runtime-gdb-transcript.json' = '1' * 64 }
            'READY_WRONG_TICKET' { $copy.ticket_sha256 = '1' * 64 }
            'READY_BOOL_ELAPSED' { $copy.supervisor_elapsed_ms = $true }
            'READY_MISSING_IDENTITY' { $copy.PSObject.Properties.Remove('supervisor_identity') }
        }
        Add-HostOracleControlResult $results (Invoke-OracleControl $id 'ready' $copy $false $context)
    }
    Add-HostOracleControlResult $results (Invoke-OracleControl 'TERMINAL_VALID' 'terminal' $context.terminal $true $context)
    $workerWaitUnknown = Copy-JsonValue $context.terminal
    $workerWaitUnknown.status = 'FAIL'
    $workerWaitUnknown.worker_exit.wait_confirmed = $false
    $workerWaitUnknown.worker_exit.returncode = $null
    $workerWaitUnknown.cases = @()
    $workerWaitUnknown.failure = [pscustomobject]@{ category = 'TIMEOUT'; case_id = $null; subcontrol = $null; message = 'worker wait deadline expired'; observed = [pscustomobject]@{ wait_confirmed = $false } }
    Add-HostOracleControlResult $results (Invoke-OracleControl 'TERM_FAIL_UNCONFIRMED_NULL_EXIT' 'terminal' $workerWaitUnknown $true $context)
    $workerWaitInventedZero = Copy-JsonValue $workerWaitUnknown
    $workerWaitInventedZero.worker_exit.returncode = 0
    Add-HostOracleControlResult $results (Invoke-OracleControl 'TERM_FAIL_UNCONFIRMED_ZERO_EXIT' 'terminal' $workerWaitInventedZero $false $context)
    foreach ($id in @('TERM_WRONG_NONCE','TERM_WRONG_PHASE','TERM_WORKER_WAIT_FALSE','TERM_WORKER_BOOL_EXIT','TERM_WORKER_NONZERO_EXIT','TERM_MISSING_WORKER_EXIT','TERM_MISSING_WORKER_RETURN','TERM_MISSING_CASE','TERM_DUPLICATE_CASE','TERM_WRONG_CASE_ORDER','TERM_MISSING_SUBCONTROL','TERM_DUPLICATE_SUBCONTROL','TERM_BOOL_COUNTER','TERM_REAL_CALL','TERM_PRESERVATION_MISMATCH','TERM_OVER_DEADLINE','TERM_MISSING_OUTER_FIELD')) {
        $copy = Copy-JsonValue $context.terminal
        switch ($id) {
            'TERM_WRONG_NONCE' { $copy.nonce = 'ffffffffffffffffffffffffffffffff' }
            'TERM_WRONG_PHASE' { $copy.phase = 'stop-observation-reader' }
            'TERM_WORKER_WAIT_FALSE' { $copy.worker_exit.wait_confirmed = $false; $copy.worker_exit.returncode = $null }
            'TERM_WORKER_BOOL_EXIT' { $copy.worker_exit.returncode = $true }
            'TERM_WORKER_NONZERO_EXIT' { $copy.worker_exit.returncode = 1 }
            'TERM_MISSING_WORKER_EXIT' { $copy.PSObject.Properties.Remove('worker_exit') }
            'TERM_MISSING_WORKER_RETURN' { $copy.worker_exit.PSObject.Properties.Remove('returncode') }
            'TERM_MISSING_CASE' { $copy.cases = @($copy.cases | Select-Object -First 4) }
            'TERM_DUPLICATE_CASE' { $copy.cases[1] = Copy-JsonValue $copy.cases[0] }
            'TERM_WRONG_CASE_ORDER' { $swap = $copy.cases[0]; $copy.cases[0] = $copy.cases[1]; $copy.cases[1] = $swap }
            'TERM_MISSING_SUBCONTROL' { $copy.cases[0].observations.subcontrols = @($copy.cases[0].observations.subcontrols | Select-Object -First 9) }
            'TERM_DUPLICATE_SUBCONTROL' { $copy.cases[0].observations.subcontrols[1] = Copy-JsonValue $copy.cases[0].observations.subcontrols[0] }
            'TERM_BOOL_COUNTER' { $copy.ledgers.reader_count = $true }
            'TERM_REAL_CALL' { $copy.ledgers.real_network_calls = 1 }
            'TERM_PRESERVATION_MISMATCH' { $copy.preservation.after.ticket_sha256 = '1' * 64 }
            'TERM_OVER_DEADLINE' { $copy.phase_elapsed_ms = 30001 }
            'TERM_MISSING_OUTER_FIELD' { $copy.PSObject.Properties.Remove('worker_identity') }
        }
        Add-HostOracleControlResult $results (Invoke-OracleControl $id 'terminal' $copy $false $context)
    }
    $finalContext = [pscustomobject]@{ phase = $context.ready.phase; nonce = $context.nonce; manifest = $context.manifest; ticket = $context.ticket; snapshot = $context.snapshot; ready = $context.ready }
    $finalValid = [pscustomobject]@{ terminal = $context.terminal; driver_wait = $true; driver_exit = 0; preservation_equal = $true; finalized = $true; elapsed_ms = 100 }
    Add-HostOracleControlResult $results (Invoke-OracleControl 'FINAL_VALID' 'final' $finalValid $true $finalContext)
    foreach ($id in @('FINAL_DRIVER_WAIT_FALSE','FINAL_DRIVER_BOOL_EXIT','FINAL_DRIVER_NONZERO_EXIT','FINAL_MISSING_DRIVER_WAIT','FINAL_MISSING_DRIVER_CODE','FINAL_CLEANUP_FALSE','FINAL_EVIDENCE_NOT_FINAL','FINAL_MISSING_FINALIZATION','FINAL_OVER_DEADLINE')) {
        $copy = Copy-JsonValue $finalValid
        switch ($id) {
            'FINAL_DRIVER_WAIT_FALSE' { $copy.driver_wait = $false }
            'FINAL_DRIVER_BOOL_EXIT' { $copy.driver_exit = $true }
            'FINAL_DRIVER_NONZERO_EXIT' { $copy.driver_exit = 1 }
            'FINAL_MISSING_DRIVER_WAIT' { $copy.PSObject.Properties.Remove('driver_wait') }
            'FINAL_MISSING_DRIVER_CODE' { $copy.PSObject.Properties.Remove('driver_exit') }
            'FINAL_CLEANUP_FALSE' { $copy.preservation_equal = $false }
            'FINAL_EVIDENCE_NOT_FINAL' { $copy.finalized = $false }
            'FINAL_MISSING_FINALIZATION' { $copy.PSObject.Properties.Remove('finalized') }
            'FINAL_OVER_DEADLINE' { $copy.elapsed_ms = 30001 }
        }
        Add-HostOracleControlResult $results (Invoke-OracleControl $id 'final' $copy $false $finalContext)
    }
    $compatibility = New-SyntheticRecords 'stop-observation-compatibility'
    $compatibilityCase = New-HostC06 $compatibility.terminal $true 0 $true
    $compatibilityContext = [pscustomobject]@{ phase = 'stop-observation-compatibility'; host_case = $compatibilityCase }
    $finalC06 = [pscustomobject]@{ terminal = $compatibility.terminal; driver_wait = $true; driver_exit = 0; preservation_equal = $true; finalized = $true; elapsed_ms = 100 }
    Add-HostOracleControlResult $results (Invoke-OracleControl 'FINAL_C06_VALID' 'final' $finalC06 $true $compatibilityContext)
    foreach ($id in @('FINAL_C06_MISSING','FINAL_C06_WORKER_WAIT_FALSE','FINAL_C06_DRIVER_WAIT_FALSE','FINAL_C06_MISSING_CONTROL','FINAL_C06_DUPLICATE_CONTROL','FINAL_C06_PRESERVATION_FALSE')) {
        $copy = Copy-JsonValue $finalC06
        $contextCopy = Copy-JsonValue $compatibilityContext
        switch ($id) {
            'FINAL_C06_MISSING' { $contextCopy.host_case = $null }
            'FINAL_C06_WORKER_WAIT_FALSE' { $contextCopy.host_case.observations.worker_exit.wait_confirmed = $false }
            'FINAL_C06_DRIVER_WAIT_FALSE' { $contextCopy.host_case.observations.wsl_wait_confirmed = $false }
            'FINAL_C06_MISSING_CONTROL' { $contextCopy.host_case.observations.subcontrols = @($contextCopy.host_case.observations.subcontrols | Select-Object -First 4) }
            'FINAL_C06_DUPLICATE_CONTROL' { $contextCopy.host_case.observations.subcontrols[1] = Copy-JsonValue $contextCopy.host_case.observations.subcontrols[0] }
            'FINAL_C06_PRESERVATION_FALSE' { $contextCopy.host_case.observations.preservation_equal = $false }
        }
        Add-HostOracleControlResult $results (Invoke-OracleControl $id 'final' $copy $false $contextCopy)
    }
    $jsonVectors = @(
        [pscustomobject]@{ id = 'JSON_UNIQUE_VALID'; text = '{"name":"escaped \"quote\"","nested":[true,false,null,{"key":"\u0078"}]}' ; expected = $true },
        [pscustomobject]@{ id = 'JSON_DUPLICATE_KEY'; text = '{"x":1,"x":2}'; expected = $false },
        [pscustomobject]@{ id = 'JSON_ESCAPED_DUPLICATE_KEY'; text = '{"x":1,"\u0078":2}'; expected = $false },
        [pscustomobject]@{ id = 'JSON_NESTED_DUPLICATE_KEY'; text = '{"outer":{"n":1,"n":2}}'; expected = $false },
        [pscustomobject]@{ id = 'JSON_MALFORMED'; text = '{"x":]'; expected = $false }
    )
    foreach ($vector in $jsonVectors) { Add-HostOracleControlResult $results (Invoke-OracleControl $vector.id 'json' $vector.text $vector.expected $null) }
    $retained = New-SyntheticRetainedProof
    $retainedContext = [pscustomobject]@{ manifest = $retained.receipt.manifest_sha256; ticket = $retained.receipt.ticket_sha256; snapshot = $retained.snapshot }
    Add-HostOracleControlResult $results (Invoke-OracleControl 'PREV_VALID' 'retained' $retained $true $retainedContext)
    foreach ($id in @('PREV_MISSING_READY','PREV_MISSING_CASE','PREV_MISSING_HOST_ORACLE','PREV_ALTERED_CLAIM_NONCE','PREV_ALTERED_TERMINAL_BINDING','PREV_ALTERED_FINAL_ADMISSION','PREV_ALTERED_HOST_ORACLE','PREV_DUPLICATE_HOST_ORACLE')) {
        $copy = Copy-JsonValue $retained
        switch ($id) {
            'PREV_MISSING_READY' { $copy.receipt.PSObject.Properties.Remove('ready') }
            'PREV_MISSING_CASE' { $copy.receipt.terminal.cases = @($copy.receipt.terminal.cases | Select-Object -First 4) }
            'PREV_MISSING_HOST_ORACLE' { $copy.receipt.host_oracle = @($copy.receipt.host_oracle | Select-Object -First ($copy.receipt.host_oracle.Count - 1)) }
            'PREV_ALTERED_CLAIM_NONCE' { $copy.claim.nonce = 'ffffffffffffffffffffffffffffffff' }
            'PREV_ALTERED_TERMINAL_BINDING' { $copy.receipt.terminal.nonce = 'ffffffffffffffffffffffffffffffff' }
            'PREV_ALTERED_FINAL_ADMISSION' { $copy.receipt.driver_exit_confirmed = $false }
            'PREV_ALTERED_HOST_ORACLE' { $copy.receipt.host_oracle[0].observed = 'REJECT' }
            'PREV_DUPLICATE_HOST_ORACLE' { $copy.receipt.host_oracle[1] = Copy-JsonValue $copy.receipt.host_oracle[0] }
        }
        Add-HostOracleControlResult $results (Invoke-OracleControl $id 'retained' $copy $false $retainedContext)
    }
    Add-HostOracleControlResult $results (Invoke-OracleControl 'CLAIM_VALID' 'claim' $ActualHostClaim $true $context)
    foreach ($id in @('CLAIM_CHANGED_ARGUMENT','CLAIM_CHANGED_PATH')) {
        $copy = Copy-JsonValue $ActualHostClaim
        $argv = @($copy.launch_argv)
        if ($id -ceq 'CLAIM_CHANGED_ARGUMENT') { $argv[5] = '--version' } else { $argv[4] = '/mnt/e/projects/ladybug/repro/changed/stop-q.py' }
        $copy.launch_argv = $argv
        Add-HostOracleControlResult $results (Invoke-OracleControl $id 'claim' $copy $false $context)
    }
    foreach ($id in @('READY_EXTRA_FIELD','READY_FLOAT_ELAPSED')) {
        $copy = Copy-JsonValue $context.ready
        if ($id -ceq 'READY_EXTRA_FIELD') { Add-Member -InputObject $copy -MemberType NoteProperty -Name extra_field -Value $true }
        else { $copy.supervisor_elapsed_ms = [double]4.25 }
        Add-HostOracleControlResult $results (Invoke-OracleControl $id 'ready' $copy $false $context)
    }
    foreach ($id in @('TERM_EXTRA_FIELD','TERM_FLOAT_PHASE_ELAPSED')) {
        $copy = Copy-JsonValue $context.terminal
        if ($id -ceq 'TERM_EXTRA_FIELD') { Add-Member -InputObject $copy -MemberType NoteProperty -Name extra_field -Value $true }
        else { $copy.phase_elapsed_ms = [double]80.5 }
        Add-HostOracleControlResult $results (Invoke-OracleControl $id 'terminal' $copy $false $context)
    }
    $floatFinal = Copy-JsonValue $finalValid
    $floatFinal.elapsed_ms = [double]100.5
    Add-HostOracleControlResult $results (Invoke-OracleControl 'FINAL_FLOAT_ELAPSED' 'final' $floatFinal $false $finalContext)
    $claimJson = ConvertTo-Json -InputObject $retained.claim -Depth 100 -Compress
    $receiptJson = ConvertTo-Json -InputObject $retained.receipt -Depth 100 -Compress
    $roundtrip = [pscustomobject]@{
        claim = ConvertFrom-HostEvidenceJson $claimJson
        receipt = ConvertFrom-HostEvidenceJson $receiptJson
    }
    $roundtripAccepted = ($roundtrip.claim.started_utc -is [string] -and $roundtrip.claim.started_utc -ceq $retained.claim.started_utc -and
        $roundtrip.receipt.evidence_written_utc -is [string] -and $roundtrip.receipt.evidence_written_utc -ceq $retained.receipt.evidence_written_utc)
    if ($roundtripAccepted) { Add-HostOracleControlResult $results (Invoke-OracleControl 'PREV_JSON_TIMESTAMP_ROUNDTRIP' 'retained' $roundtrip $true $retainedContext) }
    else { Add-HostOracleControlResult $results ([pscustomobject]@{ id = 'PREV_JSON_TIMESTAMP_ROUNDTRIP'; expected = 'ACCEPT'; observed = 'REJECT'; status = 'FAIL'; reason = 'timestamp string type or value changed during actual host JSON round trip' }) }
    $typedTimestamp = [pscustomobject]@{ claim = (Copy-JsonValue $retained.claim); receipt = (Copy-JsonValue $retained.receipt) }
    $typedTimestamp.claim.started_utc = [DateTime]::UtcNow
    Add-HostOracleControlResult $results (Invoke-OracleControl 'PREV_JSON_TIMESTAMP_TYPED_NEGATIVE' 'retained' $typedTimestamp $false $retainedContext)
    foreach ($id in @('STREAM_STDOUT_PROTOCOL_OVERSIZE_NO_NEWLINE','STREAM_STDERR_CAP_NO_NEWLINE','STREAM_STDOUT_TAIL_OVERSIZE_NO_NEWLINE')) {
        Add-HostOracleControlResult $results (Invoke-StreamOracleControl $id)
    }
    foreach ($id in @('FINAL_POSTWRITE_ADMISSION_FAILURE','FINAL_MARKER_WRITE_FAILURE_NONZERO')) {
        $markerWrite = ($id -ceq 'FINAL_POSTWRITE_ADMISSION_FAILURE')
        $outcome = Get-PostWriteFinalOutcome $false $markerWrite
        $controlPassed = (-not $outcome.pass_marker_allowed -and -not $outcome.success -and $outcome.exit_code -ne 0)
        Add-HostOracleControlResult $results ([pscustomobject]@{ id = $id; expected = 'REJECT'; observed = $(if ($controlPassed) { 'REJECT' } else { 'ACCEPT' }); status = $(if ($controlPassed) { 'PASS' } else { 'FAIL' }); reason = 'post-write failure cannot authorize PASS; enclosing host returns failure for parent-observed exit' })
    }
    if (-not (Test-HostClaim $ActualHostClaim)) { throw 'host claim object failed its actual claim validator' }
    $collision = $script:ClaimCollision
    $collisionPassed = ($null -ne $collision -and $collision.rejected -is [bool] -and $collision.rejected -eq $true -and $collision.original_preserved -is [bool] -and $collision.original_preserved -eq $true)
    $collisionRow = [pscustomobject]@{ id = 'CLAIM_COLLISION_PRESERVES_BYTES'; expected = 'REJECT_AND_PRESERVE'; observed = $(if ($collisionPassed) { 'REJECT_AND_PRESERVE' } else { 'MISMATCH' }); status = $(if ($collisionPassed) { 'PASS' } else { 'FAIL' }); original_sha256 = $collision.original_sha256; after_sha256 = $collision.after_sha256 }
    Add-HostOracleControlResult $results $collisionRow

    foreach ($vector in $script:FileScalarDescriptor.file_vectors) { Add-HostOracleControlResult $results (Invoke-AdmissionFileVector $vector) }

    $failTerminal = Copy-JsonValue $workerWaitUnknown
    $terminalVariants = @(
        [pscustomobject]@{ label = 'SUBJECT_COMPLETE'; value = $context.terminal },
        [pscustomobject]@{ label = 'FAIL'; value = $failTerminal }
    )
    $caseProbe = [pscustomobject]@{ terminal = $context.terminal }
    $subcontrolProbe = [pscustomobject]@{ terminal = $context.terminal }
    $ordinaryOracle = [pscustomobject]@{ rows = (New-SyntheticOracleRows) }
    $collisionOracle = [pscustomobject]@{ rows = Copy-JsonValue $ordinaryOracle.rows }
    $collisionIndex = [Array]::IndexOf([string[]]$script:HostOracleRowIds, 'CLAIM_COLLISION_PRESERVES_BYTES')
    $compatibility = New-SyntheticRecords 'stop-observation-compatibility'
    $compatibilityCase = New-HostC06 $compatibility.terminal $true 0 $true
    $c06Probe = [pscustomobject]@{ case = $compatibilityCase; terminal = $compatibility.terminal }
    $finalContext = [pscustomobject]@{ phase = 'stop-observation-compatibility'; host_case = $compatibilityCase }
    $finalProbe = [pscustomobject]@{ terminal = $compatibility.terminal; context = $finalContext }
    $retainedProbe = New-SyntheticRetainedProof
    $retainedContext = [pscustomobject]@{ manifest = $retainedProbe.receipt.manifest_sha256; ticket = $retainedProbe.receipt.ticket_sha256; snapshot = $retainedProbe.snapshot }
    $familyVariants = @{
        STR_FREEZE_FIELDS = @([pscustomobject]@{ label = 'admitted-freeze'; value = $script:Freeze })
        STR_READY_FIELDS = @([pscustomobject]@{ label = 'READY'; value = $context.ready })
        STR_TERMINAL_FIELDS = $terminalVariants
        STR_CASE_FIELDS = @([pscustomobject]@{ label = 'SUBJECT_COMPLETE'; value = $caseProbe })
        STR_SUBCONTROL_FIELDS = @([pscustomobject]@{ label = 'SUBJECT_COMPLETE'; value = $subcontrolProbe })
        STR_ORACLE_FIELDS = @(
            [pscustomobject]@{ label = 'ordinary'; value = $ordinaryOracle; paths = $null },
            [pscustomobject]@{ label = 'collision'; value = $collisionOracle; paths = $null }
        )
        STR_C06_FIELDS = @([pscustomobject]@{ label = 'C06'; value = $c06Probe })
        STR_FINAL_FIELDS = @([pscustomobject]@{ label = 'compatibility'; value = $finalProbe })
        STR_RETAINED_FIELDS = @([pscustomobject]@{ label = 'admission-r2'; value = $retainedProbe })
    }
    $familyOrder = @('STR_FREEZE_FIELDS','STR_READY_FIELDS','STR_TERMINAL_FIELDS','STR_CASE_FIELDS','STR_SUBCONTROL_FIELDS','STR_ORACLE_FIELDS','STR_C06_FIELDS','STR_FINAL_FIELDS','STR_RETAINED_FIELDS')
    foreach ($family in $familyOrder) {
        $members = [string[]]@($script:FileScalarDescriptor.scalar_families.PSObject.Properties[$family].Value)
        $variants = @($familyVariants[$family])
        if ($family -ceq 'STR_ORACLE_FIELDS') {
            $ordinaryPaths = @{}; $collisionPaths = @{}
            foreach ($member in $members) {
                $ordinaryPaths[$member] = 'rows.0.' + $member
                $collisionPaths[$member] = 'rows.' + $collisionIndex + '.' + $member
            }
            $variants = @(
                [pscustomobject]@{ label = 'ordinary'; value = $ordinaryOracle; paths = $ordinaryPaths },
                [pscustomobject]@{ label = 'collision'; value = $collisionOracle; paths = $collisionPaths }
            )
        }
        if ($family -ceq 'STR_C06_FIELDS') {
            $c06Paths = @{}
            foreach ($member in $members) {
                if ($member.StartsWith('case.')) { $c06Paths[$member] = $member }
                elseif ($member.StartsWith('control.')) { $c06Paths[$member] = 'case.observations.subcontrols.0.' + $member.Substring(8) }
                else { $c06Paths[$member] = 'terminal.' + $member.Substring('terminal.'.Length) }
            }
            $variants = @([pscustomobject]@{ label = 'C06'; value = $c06Probe; paths = $c06Paths })
        }
        if ($family -ceq 'STR_CASE_FIELDS') {
            $mapped = @{}; foreach ($member in $members) { $mapped[$member] = 'terminal.cases.0.' + $member }
            $variants = @([pscustomobject]@{ label = 'SUBJECT_COMPLETE'; value = $caseProbe; paths = $mapped })
        }
        if ($family -ceq 'STR_SUBCONTROL_FIELDS') {
            $mapped = @{}; foreach ($member in $members) { $mapped[$member] = 'terminal.cases.0.observations.subcontrols.0.' + $member }
            $variants = @([pscustomobject]@{ label = 'SUBJECT_COMPLETE'; value = $subcontrolProbe; paths = $mapped })
        }
        if ($family -ceq 'STR_FINAL_FIELDS') {
            $mapped = @{}; foreach ($member in $members) { $mapped[$member] = $member }
            $variants = @([pscustomobject]@{ label = 'compatibility'; value = $finalProbe; paths = $mapped })
        }
        if ($family -ceq 'STR_RETAINED_FIELDS') {
            $mapped = @{}; foreach ($member in $members) { $mapped[$member] = $member }
            $variants = @([pscustomobject]@{ label = 'admission-r2'; value = $retainedProbe; paths = $mapped })
        }
        if ($family -ceq 'STR_FREEZE_FIELDS' -or $family -ceq 'STR_READY_FIELDS' -or $family -ceq 'STR_TERMINAL_FIELDS') {
            foreach ($variant in $variants) { $variant | Add-Member -NotePropertyName paths -NotePropertyValue @{} -Force }
            foreach ($variant in $variants) { foreach ($member in $members) { $variant.paths[$member] = $member } }
        }
        $probeVariants = New-Object System.Collections.ArrayList
        foreach ($variant in $variants) {
            $probeValue = $variant.value
            if ($family -ceq 'STR_ORACLE_FIELDS') { $probeValue = $variant.value }
            if ($family -ceq 'STR_C06_FIELDS') { $probeValue = $variant.value }
            if ($family -ceq 'STR_CASE_FIELDS' -or $family -ceq 'STR_SUBCONTROL_FIELDS') { $probeValue = $variant.value }
            if ($family -ceq 'STR_FINAL_FIELDS') { $probeValue = $variant.value }
            if ($family -ceq 'STR_RETAINED_FIELDS') { $probeValue = $variant.value }
            [void]$probeVariants.Add([pscustomobject]@{ label = $variant.label; value = $probeValue; paths = $variant.paths })
        }
        if ($family -ceq 'STR_FREEZE_FIELDS') { $validatorContext = $null }
        elseif ($family -ceq 'STR_RETAINED_FIELDS') { $validatorContext = $retainedContext }
        else { $validatorContext = $context }
        Add-HostOracleControlResult $results (Invoke-HostScalarFamilyControl $family $members ([object[]]@($probeVariants.ToArray())) $validatorContext)
    }
    if (@($results | Where-Object { $_.status -cne 'PASS' }).Count -gt 0) {
        $failedRows = @($results | Where-Object { $_.status -cne 'PASS' })
        throw ('host-oracle controls failed: ' + (ConvertTo-Json -InputObject $failedRows -Depth 10 -Compress))
    }
    $rows = @($results.ToArray())
    if (-not (Test-HostOracleProof $rows)) { throw 'host-oracle row set is incomplete, duplicated, reordered, or mistyped' }
    return $rows
}

function Write-PhaseClaim {
    param([string]$Path, [string]$PhaseName, [string]$Nonce, [string]$Manifest)
    $claim = [pscustomobject]@{ phase = $PhaseName; nonce = $Nonce; manifest_sha256 = $Manifest; attempt = 1; started_utc = [DateTime]::UtcNow.ToString('o') }
    Write-JsonCreateNew $Path $claim
    return $claim
}

function Get-BytesSha256 {
    param([byte[]]$Bytes)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return [System.BitConverter]::ToString($sha.ComputeHash($Bytes)).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Test-ClaimCollisionPreservation {
    param([string]$Path, [string]$Nonce)
    if (-not [System.IO.File]::Exists($Path)) { throw 'exclusive phase claim is absent before collision control' }
    $beforeRead = Read-BoundedUtf8File $Path 'claim collision before' $false
    if (-not $beforeRead.accepted) { throw ('claim collision original bounded raw read failed: ' + $beforeRead.rejection) }
    $beforeHash = [string]$beforeRead.sha256
    $rejected = $false
    try { Write-NewUtf8File $Path ('COLLISION-' + $Nonce) }
    catch [System.IO.IOException] { $rejected = $true }
    if (-not [System.IO.File]::Exists($Path)) { throw 'claim collision removed the original claim' }
    $afterRead = Read-BoundedUtf8File $Path 'claim collision after' $false
    if (-not $afterRead.accepted) { throw ('claim collision preserved-file bounded raw read failed: ' + $afterRead.rejection) }
    $afterHash = [string]$afterRead.sha256
    return [pscustomobject]@{ rejected = [bool]$rejected; original_preserved = [bool]($beforeHash -ceq $afterHash); original_sha256 = $beforeHash; after_sha256 = $afterHash }
}

function Test-HostC06 {
    param([object]$Case, [object]$Terminal, [object]$DriverWait, [object]$DriverExit, [object]$PreservationEqual)
    if (-not (Test-ObjectShape $Case @('case_id','expected','status','observations')) -or $Case.case_id -isnot [string] -or $Case.expected -isnot [string] -or $Case.status -isnot [string] -or $Case.case_id -cne 'C06' -or $Case.expected -cne $script:ExpectedByCase.C06 -or $Case.status -cne 'PASS') { return $false }
    if ($null -eq $Case.observations -or $Case.observations -is [string] -or $Case.observations -is [System.Array]) { return $false }
    $controlsProperty = $Case.observations.PSObject.Properties['subcontrols']
    if ($null -eq $controlsProperty -or $controlsProperty.Value -isnot [System.Array]) { return $false }
    $controls = @($controlsProperty.Value)
    $expectedIds = @($script:CaseSubcontrols.C06)
    if ($controls.Count -ne $expectedIds.Count) { return $false }
    for ($i = 0; $i -lt $expectedIds.Count; $i++) {
        if (-not (Test-ObjectShape $controls[$i] @('id','status','observed')) -or $controls[$i].id -isnot [string] -or $controls[$i].status -isnot [string] -or $controls[$i].id -cne $expectedIds[$i] -or $controls[$i].status -cne 'PASS' -or $controls[$i].observed -isnot [bool] -or $controls[$i].observed -ne $true) { return $false }
    }
    if (-not (Test-ObjectShape $Case.observations @('subcontrols','worker_exit','wsl_wait_confirmed','wsl_exit_code','preservation_equal'))) { return $false }
    if (-not (Test-ObjectShape $Case.observations.worker_exit @('wait_confirmed','returncode')) -or $Case.observations.worker_exit.wait_confirmed -isnot [bool] -or $Case.observations.worker_exit.wait_confirmed -ne $Terminal.worker_exit.wait_confirmed -or -not (Test-ExactInteger $Case.observations.worker_exit.returncode) -or $Case.observations.worker_exit.returncode -ne $Terminal.worker_exit.returncode) { return $false }
    if ($Case.observations.wsl_wait_confirmed -isnot [bool] -or $Case.observations.wsl_wait_confirmed -ne $DriverWait -or -not (Test-ExactInteger $Case.observations.wsl_exit_code) -or $Case.observations.wsl_exit_code -ne $DriverExit -or $Case.observations.preservation_equal -isnot [bool] -or $Case.observations.preservation_equal -ne $PreservationEqual) { return $false }
    return ($Terminal.status -is [string] -and $Terminal.status -ceq 'SUBJECT_COMPLETE' -and (Test-ExactBoolean $Terminal.worker_exit.wait_confirmed) -and $Terminal.worker_exit.wait_confirmed -eq $true -and (Test-ExactInteger $Terminal.worker_exit.returncode) -and $Terminal.worker_exit.returncode -eq 0 -and (Test-ExactBoolean $DriverWait) -and $DriverWait -eq $true -and (Test-ExactInteger $DriverExit) -and $DriverExit -eq 0 -and (Test-ExactBoolean $PreservationEqual) -and $PreservationEqual -eq $true)
}

function New-HostC06 {
    param([object]$Terminal, [bool]$DriverWait, [object]$DriverExit, [bool]$PreservationEqual)
    $workerWait = (Test-ExactBoolean $Terminal.worker_exit.wait_confirmed) -and $Terminal.worker_exit.wait_confirmed -eq $true
    $workerZero = (Test-ExactInteger $Terminal.worker_exit.returncode) -and $Terminal.worker_exit.returncode -eq 0
    $driverWaited = (Test-ExactBoolean $DriverWait) -and $DriverWait -eq $true
    $driverZero = (Test-ExactInteger $DriverExit) -and $DriverExit -eq 0
    $samePins = (Test-ExactBoolean $PreservationEqual) -and $PreservationEqual -eq $true
    $values = @($workerWait,$workerZero,$driverWaited,$driverZero,$samePins)
    $controls = New-Object System.Collections.ArrayList
    $ids = @($script:CaseSubcontrols.C06)
    for ($i = 0; $i -lt $ids.Count; $i++) { [void]$controls.Add([pscustomobject]@{ id = $ids[$i]; status = $(if ($values[$i]) { 'PASS' } else { 'FAIL' }); observed = [bool]$values[$i] }) }
    return [pscustomobject]@{
        case_id = 'C06'; expected = $script:ExpectedByCase.C06; status = $(if (@($values | Where-Object { -not $_ }).Count -eq 0) { 'PASS' } else { 'FAIL' })
        observations = [pscustomobject]@{ subcontrols = @($controls.ToArray()); worker_exit = $Terminal.worker_exit; wsl_wait_confirmed = $DriverWait; wsl_exit_code = $DriverExit; preservation_equal = $PreservationEqual }
    }
}

function Assert-PreviousPhase {
    param([string]$CurrentPhase, [string]$Manifest, [string]$Ticket, [object]$Sources, [object]$Fixtures, [object]$ReadInputs)
    $index = [Array]::IndexOf($script:PhaseOrder, $CurrentPhase)
    if ($index -le 0) { return }
    for ($i = 0; $i -lt $index; $i++) {
        $prior = $script:PhaseOrder[$i]
        $receiptPath = Join-Path $script:EvidenceDirectory ($script:EvidenceNamePrefix + $prior + '.json')
        $claimPath = Join-Path $script:EvidenceDirectory ($script:EvidenceNamePrefix + $prior + '.claim')
        $overrunPath = Join-Path $script:EvidenceDirectory ($script:EvidenceNamePrefix + $prior + '-overrun.json')
        if (-not [System.IO.File]::Exists($claimPath) -or [System.IO.File]::Exists($overrunPath)) { throw ('matching predecessor claim is absent or invalid: ' + $prior) }
        try {
            $claimRead = Read-BoundedUtf8File $claimPath ('predecessor claim ' + $prior) $true
            if (-not $claimRead.accepted) { throw ('claim bounded read rejected: ' + $claimRead.rejection) }
            if (-not (Test-JsonWithUniqueKeys $claimRead.text)) {
                Register-BoundedReadFailure ('predecessor claim ' + $prior + ' JSON validation') $claimPath $claimRead 'JSON_MALFORMED_OR_DUPLICATE_KEY'
                throw 'claim contained malformed JSON or duplicate object keys'
            }
            try { $claim = ConvertFrom-HostEvidenceJson $claimRead.text }
            catch {
                Register-BoundedReadFailure ('predecessor claim ' + $prior + ' JSON conversion') $claimPath $claimRead 'JSON_CONVERSION_ERROR'
                throw
            }
        } catch { throw ('predecessor claim is not valid unique-key UTF-8 JSON: ' + $prior + ': ' + $_.Exception.Message) }
        $claimReason = $null
        if (-not (Test-RetainedPhaseClaim $claim $prior $Manifest ([ref]$claimReason))) {
            Register-BoundedReadFailure ('predecessor claim ' + $prior + ' schema admission') $claimPath $claimRead ('CLAIM_SCHEMA_OR_BINDING_REJECT:' + $claimReason)
            throw ('predecessor claim failed strict shape/string/binding admission: ' + $prior + ': ' + $claimReason)
        }
        if (-not [System.IO.File]::Exists($receiptPath)) { throw ('matching predecessor PASS receipt is absent: ' + $prior) }
        try {
            $receiptRead = Read-BoundedUtf8File $receiptPath ('predecessor receipt ' + $prior) $true
            if (-not $receiptRead.accepted) { throw ('receipt bounded read rejected: ' + $receiptRead.rejection) }
            if (-not (Test-JsonWithUniqueKeys $receiptRead.text)) {
                Register-BoundedReadFailure ('predecessor receipt ' + $prior + ' JSON validation') $receiptPath $receiptRead 'JSON_MALFORMED_OR_DUPLICATE_KEY'
                throw 'receipt contained malformed JSON or duplicate object keys'
            }
            try { $receipt = ConvertFrom-HostEvidenceJson $receiptRead.text }
            catch {
                Register-BoundedReadFailure ('predecessor receipt ' + $prior + ' JSON conversion') $receiptPath $receiptRead 'JSON_CONVERSION_ERROR'
                throw
            }
        } catch { throw ('predecessor receipt is not valid unique-key UTF-8 JSON: ' + $prior + ': ' + $_.Exception.Message) }
        $reason = $null
        $retainedAccepted = $false
        try { $retainedAccepted = Test-RetainedPhaseEvidence $claim $receipt $prior $Manifest $Ticket $Sources $Fixtures $ReadInputs $script:HostBefore ([ref]$reason) }
        catch { $reason = 'validator exception: ' + (Limit-CleanupDetail $_.Exception.Message) }
        if (-not $retainedAccepted) {
            $failureKind = if ($reason -like 'validator exception:*') { 'RETAINED_ADMISSION_EXCEPTION' } else { 'RETAINED_SCHEMA_ADMISSION_REJECT:' + $reason }
            Register-BoundedReadFailure ('predecessor claim ' + $prior + ' retained admission') $claimPath $claimRead $failureKind
            Register-BoundedReadFailure ('predecessor receipt ' + $prior + ' retained admission') $receiptPath $receiptRead $failureKind
            throw ('predecessor evidence failed strict nested admission: ' + $prior + ': ' + $reason)
        }
    }
}

function Read-AndValidateFreeze {
    if (-not [System.IO.File]::Exists($script:FreezePath)) { throw 'integration freeze is missing' }
    $freezeRead = Read-BoundedUtf8File $script:FreezePath 'execution freeze' $true
    if (-not $freezeRead.accepted) { throw ('integration freeze bounded read rejected: ' + $freezeRead.rejection) }
    $script:ManifestSha256 = [string]$freezeRead.sha256
    $script:Freeze = ConvertFrom-BoundedHostJson $freezeRead 'integration freeze'
    $reason = $null
    if (-not (Test-FreezeEnvelope $script:Freeze ([ref]$reason))) {
        Register-BoundedReadFailure 'execution freeze schema admission' $script:FreezePath $freezeRead ('FREEZE_SCHEMA_REJECT:' + $reason)
        throw ('parent freeze is not fully authorized for this one-shot source-profile gate: ' + $reason)
    }
    $descriptorRead = Read-BoundedUtf8File $script:FileScalarDescriptorPath 'file-scalar admission descriptor' $true
    if (-not $descriptorRead.accepted) { throw ('file-scalar admission descriptor bounded read rejected: ' + $descriptorRead.rejection) }
    if ($descriptorRead.sha256 -cne $script:FileScalarDescriptorSha256) {
        Register-BoundedReadFailure 'file-scalar descriptor pin admission' $script:FileScalarDescriptorPath $descriptorRead 'DESCRIPTOR_SHA256_MISMATCH'
        throw 'file-scalar admission descriptor differs from its reviewed source pin'
    }
    $descriptorDocument = ConvertFrom-BoundedHostJson $descriptorRead 'file-scalar admission descriptor'
    $admission = $descriptorDocument.file_scalar_admission_r2
    $requiredFamilyCounts = [ordered]@{
        STR_FREEZE_FIELDS = 6; STR_READY_FIELDS = 5; STR_TERMINAL_FIELDS = 6; STR_CASE_FIELDS = 3; STR_SUBCONTROL_FIELDS = 2
        STR_ORACLE_FIELDS = 4; STR_C06_FIELDS = 6; STR_FINAL_FIELDS = 2; STR_RETAINED_FIELDS = 13
    }
    if ($null -eq $admission -or $admission.schema -cne 'ladybug.feat010.file-scalar-admission-r2.expectations.v1' -or
        $admission.maximum_bytes -ne $script:MaximumHostJsonBytes -or $admission.maximum_utf16_units -ne $script:MaximumHostJsonUnits -or
        $admission.chunk_maximum_bytes -ne $script:HostReadChunkBytes -or $admission.host_row_total -ne 90 -or
        $admission.fresh_evidence_prefix -cne 'admission-r2-' -or $admission.runtime_authorized -ne $false) {
        Register-BoundedReadFailure 'file-scalar descriptor schema admission' $script:FileScalarDescriptorPath $descriptorRead 'DESCRIPTOR_SCHEMA_OR_LIMITS_REJECT'
        throw 'file-scalar admission descriptor identity or fixed limits differ from the approved contract'
    }
    if (-not (Test-ObjectShape $admission.worker_control_totals @('Q','R','C_worker','C_host')) -or $admission.worker_control_totals.Q -ne 51 -or $admission.worker_control_totals.R -ne 115 -or $admission.worker_control_totals.C_worker -ne 23 -or $admission.worker_control_totals.C_host -ne 5 -or $admission.file_vectors -isnot [System.Array] -or $admission.file_vectors.Count -ne 5) {
        Register-BoundedReadFailure 'file-scalar descriptor inventory admission' $script:FileScalarDescriptorPath $descriptorRead 'DESCRIPTOR_WORKER_TOTALS_OR_VECTOR_COUNT_REJECT'
        throw 'file-scalar admission descriptor worker totals or vector count differ from the approved contract'
    }
    foreach ($family in $requiredFamilyCounts.Keys) {
        $property = $admission.scalar_families.PSObject.Properties[$family]
        if ($null -eq $property -or $property.Value -isnot [System.Array] -or $property.Value.Count -ne $requiredFamilyCounts[$family]) {
            Register-BoundedReadFailure 'file-scalar descriptor family inventory admission' $script:FileScalarDescriptorPath $descriptorRead ('DESCRIPTOR_FAMILY_INVENTORY_REJECT:' + $family)
            throw ('file-scalar admission descriptor member inventory differs: ' + $family)
        }
    }
    $script:FileScalarDescriptor = $admission
    try { Assert-HostRuntimePin $script:Freeze }
    catch {
        Register-BoundedReadFailure 'execution freeze runtime pin admission' $script:FreezePath $freezeRead 'FREEZE_RUNTIME_PIN_REJECT'
        throw
    }
    $script:Execution = $script:Freeze.execution_freeze
    $script:TicketSha256 = [string]$script:Execution.ticket_sha256
    if ((Get-FileSha256 $script:TicketPath) -cne $script:TicketSha256) { throw 'canonical FEAT-010 ticket differs from execution freeze' }
    foreach ($path in $script:SourcePaths) { $script:SourceSha256[$path] = Get-FileSha256 (Join-Path $script:Root ($path -replace '/', '\')) }
    foreach ($path in $script:FixturePaths) { $script:FixtureSha256[$path] = Get-FileSha256 (Join-Path $script:Root ($path -replace '/', '\')) }
    foreach ($path in $script:ReadInputPaths) { $script:ReadInputsSha256[$path] = Get-FileSha256 $script:TranscriptPath }
    if (-not (Test-HashObject ([pscustomobject]$script:SourceSha256) $script:Execution.source_sha256) -or -not (Test-HashObject ([pscustomobject]$script:FixtureSha256) $script:Execution.fixture_sha256) -or -not (Test-HashObject ([pscustomobject]$script:ReadInputsSha256) $script:Execution.read_inputs_sha256)) { throw 'current source, fixture or read-only input hashes differ from parent freeze' }
    if ($script:ReadInputsSha256[$script:ReadInputPaths[0]] -cne $script:TranscriptSha256) { throw 'retained unknown-signal transcript pin differs from reviewed source contract' }
    $script:HostBefore = Get-HostPreservationSnapshot $script:Freeze $script:Execution $script:ManifestSha256
    Assert-PreviousPhase $Phase $script:ManifestSha256 $script:TicketSha256 ([pscustomobject]$script:SourceSha256) ([pscustomobject]$script:FixtureSha256) ([pscustomobject]$script:ReadInputsSha256)
}

function Start-PinnedSupervisor {
    if ($null -eq $script:HostRuntime -or -not (Test-StringArray $script:HostClaim.launch_argv $script:LaunchArgv) -or $script:LaunchArgv[0] -cne 'wsl.exe') { throw 'actual launch vector is not the checked parent-bound six-token claim' }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $script:HostRuntime.wsl_path
    $psi.Arguments = [string]::Join(' ', [string[]]@($script:LaunchArgv[1..($script:LaunchArgv.Count - 1)]))
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardInputEncoding = New-Object System.Text.UTF8Encoding($false)
    $psi.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false, $true)
    $psi.StandardErrorEncoding = New-Object System.Text.UTF8Encoding($false, $true)
    $script:Driver = New-Object System.Diagnostics.Process
    $script:Driver.StartInfo = $psi
    if (-not $script:Driver.Start()) { throw 'direct wsl.exe process did not start' }
    $script:DriverStarted = $true
    $driverPid = $null
    $driverStartTicks = $null
    $driverIdentityError = $null
    try { $driverPid = [int]$script:Driver.Id } catch { $driverIdentityError = 'PID capture failed: ' + $_.Exception.Message }
    try { $driverStartTicks = [long]$script:Driver.StartTime.ToUniversalTime().Ticks }
    catch {
        if ($null -eq $driverIdentityError) { $driverIdentityError = 'start-time capture failed: ' + $_.Exception.Message }
        else { $driverIdentityError += '; start-time capture failed: ' + $_.Exception.Message }
    }
    $script:DriverIdentity = [pscustomobject]@{
        requested_image = $script:HostRuntime.wsl_path
        pid = $driverPid
        start_time_utc_ticks = $driverStartTicks
        capture_error = $driverIdentityError
    }
    $script:StdoutState = New-StreamPumpState $script:Driver.StandardOutput.BaseStream 'stdout' 16384
    $script:StderrState = New-StreamPumpState $script:Driver.StandardError.BaseStream 'stderr' 16384
    Start-StreamRead $script:StdoutState
    Start-StreamRead $script:StderrState
}

function Retain-UnresolvedDriverCleanup {
    param([string]$WaitError)
    $lastMarker = $null
    if ($null -ne $script:TerminalRecord) { $lastMarker = 'TERMINAL' }
    elseif ($null -ne $script:ReadyRecord) { $lastMarker = 'READY' }
    $detail = [pscustomobject]@{
        direct_driver_identity = $script:DriverIdentity
        direct_driver_wait_confirmed = $false
        direct_driver_exit_code = $null
        cleanup_status = 'UNRESOLVED'
        last_proven_protocol_marker = $lastMarker
        protocol_records = @($script:ProtocolRecords.ToArray())
        protocol_lines = @($script:ProtocolLines.ToArray())
        stream_capture = $script:DriverStreamCapture
        stdout_read_pending = [bool]$script:StdoutReadPending
        wait_error = $WaitError
    }
    $priorDetail = $script:TransportFailureDetail
    $script:TransportFailureDetail = ConvertTo-Json -InputObject ([pscustomobject]@{ prior_transport_detail = $priorDetail; unresolved_cleanup = $detail }) -Depth 40 -Compress
}

function Send-InitAndGo {
    param([string]$Nonce)
    $init = [pscustomobject]@{
        kind = 'INIT'; phase = $Phase; nonce = $Nonce; manifest_sha256 = $script:ManifestSha256; ticket_sha256 = $script:TicketSha256
        source_sha256 = [pscustomobject]$script:SourceSha256; fixture_sha256 = [pscustomobject]$script:FixtureSha256
        read_inputs_sha256 = [pscustomobject]$script:ReadInputsSha256; host_claim = $script:HostClaim
    }
    if (-not (Test-ObjectShape $init @('kind','phase','nonce','manifest_sha256','ticket_sha256','source_sha256','fixture_sha256','read_inputs_sha256','host_claim'))) { throw 'host INIT did not match fixed outer key contract' }
    Write-ProtocolLine $init
    $phaseLimit = [int]$script:PhaseLimits[$Phase]
    $terminalCutoff = $phaseLimit - $script:DriverWaitReserveMs - $script:EvidenceReserveMs
    $ready = Read-ProtocolLine $terminalCutoff 'READY'
    $reason = $null
    if (-not (Test-AdmissionEnvelope $ready $Phase $Nonce $script:ManifestSha256 $script:TicketSha256 ([pscustomobject]$script:SourceSha256) ([pscustomobject]$script:FixtureSha256) ([pscustomobject]$script:ReadInputsSha256) $phaseLimit ([ref]$reason))) { throw ('supervisor READY rejected: ' + $reason) }
    $script:ReadyRecord = $ready
    $remaining = [int][Math]::Floor($terminalCutoff - $script:Clock.ElapsedMilliseconds)
    if ($remaining -le 0) { throw 'phase preflight left no positive relative GO budget' }
    $script:GoBudgetMs = $remaining
    $go = [pscustomobject]@{ kind = 'GO'; phase = $Phase; nonce = $Nonce; manifest_sha256 = $script:ManifestSha256; remaining_ms = $remaining }
    Write-ProtocolLine $go
    $script:Driver.StandardInput.Close()
    $script:TerminalRecord = Read-ProtocolLine $terminalCutoff 'TERMINAL'
}

function Switch-StdoutToTail {
    if ($null -eq $script:StdoutState -or $script:StdoutState.mode -ceq 'tail') { return }
    if ($script:StdoutState.line.Length -gt 0 -or $script:StdoutState.pending_cr) {
        $observedLineBytes = [long]$script:StdoutState.protocol_line_bytes
        if ($script:StdoutState.pending_cr) { $observedLineBytes++ }
        Save-PartialProtocolPrefix $script:StdoutState $observedLineBytes
    }
    $script:StdoutState.mode = 'tail'
    $script:StdoutState.pending_cr = $false
    $script:StdoutState.line.SetLength(0)
}

function Set-DriverStreamCapture {
    $script:StdoutReadPending = ($null -ne $script:StdoutState -and $null -ne $script:StdoutState.task)
    if ($null -ne $script:StdoutState.partial_protocol) {
        $script:StdoutState.partial_protocol.stream_eof = [bool]$script:StdoutState.eof
        $script:StdoutState.partial_protocol.observed_stream_bytes = [long]$script:StdoutState.observed_bytes
    }
    $script:DriverStreamCapture = [pscustomobject]@{
        stdout = Get-StreamCaptureSummary $script:StdoutState
        stderr = Get-StreamCaptureSummary $script:StderrState
    }
    $script:StdoutTail = Get-StreamRetainedText $script:StdoutState
    $script:StderrText = Get-StreamRetainedText $script:StderrState
}

function Limit-CleanupDetail {
    param([string]$Text)
    if ($null -eq $Text) { return '' }
    if ($Text.Length -le 4096) { return $Text }
    $marker = '<cleanup detail truncated>'
    return ($Text.Substring(0, 4096 - $marker.Length) + $marker)
}

function Capture-DriverFailureEvidence {
    param([string]$PrimaryError, [string]$CleanupError)
    $streamSummaryError = $null
    try { Set-DriverStreamCapture } catch { $streamSummaryError = $_.Exception.Message }
    $protocolFailure = ($null -ne $script:StdoutState -and ($script:StdoutState.protocol_overflow -or $script:StdoutState.protocol_error -or $script:StdoutState.extra_stdout))
    if ($protocolFailure) {
        $script:TransportFailureCategory = 'PROTOCOL'
        $script:FailureCategory = 'PROTOCOL'
    }
    $cleanupDetail = $CleanupError
    if ($null -ne $streamSummaryError) { $cleanupDetail = [string]$cleanupDetail + '; stream summary failed: ' + $streamSummaryError }
    $detail = [pscustomobject]@{
        primary_error = $PrimaryError
        bound_failure_detail = $script:FailureDetail
        cleanup_secondary_error = Limit-CleanupDetail $cleanupDetail
        observed_streams = $script:DriverStreamCapture
        partial_protocol = if ($null -ne $script:StdoutState) { $script:StdoutState.partial_protocol } else { $null }
        bounded_file_reads = @($script:BoundedReadFailures.ToArray())
    }
    $combined = ConvertTo-Json -InputObject $detail -Depth 20 -Compress
    $script:TransportFailureDetail = $combined
    $script:FailureDetail = $combined
}

function Pump-DriverUntilExit {
    param([int]$WaitCutoff)
    if ($null -eq $script:Driver -or $null -eq $script:StdoutState -or $null -eq $script:StderrState) { return $false }
    Switch-StdoutToTail
    while ($true) {
        foreach ($state in @($script:StdoutState, $script:StderrState)) {
            Complete-StreamRead $state
            if ($state.offset -lt $state.count) { Consume-StreamTextChunk $state }
            Start-StreamRead $state
        }
        try {
            if ($script:Driver.WaitForExit(0)) {
                $script:DriverExitConfirmed = $true
                $script:DriverExitCode = $script:Driver.ExitCode
            }
        } catch { $script:DriverIdentity.capture_error = 'exit observation failed: ' + $_.Exception.Message }
        if ($script:DriverExitConfirmed -and $script:StdoutState.eof -and $script:StdoutState.offset -ge $script:StdoutState.count -and $script:StderrState.eof -and $script:StderrState.offset -ge $script:StderrState.count) { return $true }
        $remaining = [int][Math]::Floor($WaitCutoff - $script:Clock.ElapsedMilliseconds)
        if ($remaining -le 0) { return $false }
        $tasks = @()
        if ($null -ne $script:StdoutState.task) { $tasks += [System.Threading.Tasks.Task]$script:StdoutState.task }
        if ($null -ne $script:StderrState.task) { $tasks += [System.Threading.Tasks.Task]$script:StderrState.task }
        $slice = [int][Math]::Min(50, $remaining)
        if ($tasks.Count -gt 0) {
            try { [void][System.Threading.Tasks.Task]::WaitAny([System.Threading.Tasks.Task[]]$tasks, $slice) }
            catch { return $false }
        } else {
            try { [void]$script:Driver.WaitForExit($slice) } catch { return $false }
        }
    }
}

function Drain-DriverStreams {
    param([int]$WaitCutoff, [bool]$RequireNoExtraOutput)
    if ($script:DriverStreamsDrained) { return }
    if ($null -eq $script:Driver) { return }
    $reapedAndDrained = Pump-DriverUntilExit $WaitCutoff
    Set-DriverStreamCapture
    $script:DriverStreamsDrained = ($script:StdoutState.eof -and $script:StderrState.eof -and $script:StdoutState.offset -ge $script:StdoutState.count -and $script:StderrState.offset -ge $script:StderrState.count)
    if ($null -ne $script:StdoutState.read_error) { throw ('stdout stream drain failed: ' + $script:StdoutState.read_error) }
    if ($null -ne $script:StderrState.read_error) { throw ('stderr stream drain failed: ' + $script:StderrState.read_error) }
    if (-not $reapedAndDrained) { throw 'direct wsl.exe exit and both bounded stream EOFs were not confirmed before the evidence reserve' }
    if (-not $script:DriverStreamsDrained) { throw 'stdout or stderr did not reach EOF before the evidence reserve' }
    if ($RequireNoExtraOutput -and $script:StdoutState.extra_stdout) {
        throw ('supervisor emitted unexpected stdout after TERMINAL: ' + (ConvertTo-Json -InputObject $script:DriverStreamCapture.stdout -Compress))
    }
    try { $script:Driver.StandardOutput.Dispose() } catch { }
    try { $script:Driver.StandardError.Dispose() } catch { }
}

function Confirm-DirectDriverExit {
    $phaseLimit = [int]$script:PhaseLimits[$Phase]
    $waitCutoff = $phaseLimit - $script:EvidenceReserveMs
    $remaining = [int][Math]::Floor($waitCutoff - $script:Clock.ElapsedMilliseconds)
    if ($remaining -le 0) { throw 'no host deadline budget remains for the direct WSL process and stream wait' }
    Drain-DriverStreams $waitCutoff $true
    if (-not (Test-ExactInteger $script:DriverExitCode)) { throw 'direct wsl.exe exit code is not an integer' }
    if ($script:DriverExitCode -ne 0) { throw ('direct wsl.exe exited nonzero: ' + $script:DriverExitCode) }
}

function Test-PhaseTerminal {
    $reason = $null
    $maximum = [int]$script:PhaseLimits[$Phase]
    if (-not (Test-TerminalRecord $script:TerminalRecord $Phase $script:PhaseNonce $script:ManifestSha256 $script:TicketSha256 ([pscustomobject]$script:SourceSha256) ([pscustomobject]$script:FixtureSha256) ([pscustomobject]$script:ReadInputsSha256) $script:ReadyRecord.supervisor_identity $maximum ([ref]$reason))) { throw ('TERMINAL failed strict typed and binding admission: ' + $reason) }
    if ($script:TerminalRecord.status -cne 'SUBJECT_COMPLETE') { throw ('supervisor retained structured failure: ' + (ConvertTo-Json -InputObject $script:TerminalRecord.failure -Depth 30 -Compress)) }
    if (-not (Test-IdentityEqual $script:TerminalRecord.supervisor_identity $script:ReadyRecord.supervisor_identity)) { throw 'READY and TERMINAL supervisor identities differ' }
    if (-not (Test-PreservationEqual $script:TerminalRecord.preservation.before $script:HostBefore) -or -not (Test-PreservationEqual $script:TerminalRecord.preservation.after $script:HostAfter)) { throw 'supervisor preservation snapshots differ from host before/after pins' }
}

function Set-BoundSupervisorFailureClassification {
    if ($null -eq $script:TerminalRecord -or $null -eq $script:ReadyRecord -or $script:TerminalRecord.status -cne 'FAIL') { return }
    $reason = $null
    $valid = Test-TerminalRecord $script:TerminalRecord $Phase $script:PhaseNonce $script:ManifestSha256 $script:TicketSha256 ([pscustomobject]$script:SourceSha256) ([pscustomobject]$script:FixtureSha256) ([pscustomobject]$script:ReadInputsSha256) $script:ReadyRecord.supervisor_identity ([int]$script:PhaseLimits[$Phase]) ([ref]$reason)
    if (-not $valid -or -not (Test-IdentityEqual $script:TerminalRecord.supervisor_identity $script:ReadyRecord.supervisor_identity)) { return }
    if ($null -eq $script:HostBefore -or -not (Test-PreservationEqual $script:TerminalRecord.preservation.before $script:HostBefore)) { return }
    if ($script:TerminalRecord.failure.category -isnot [string] -or $script:TerminalRecord.failure.category.Length -eq 0) { return }
    $script:FailureCategory = $script:TerminalRecord.failure.category
    $script:FailureMessage = $script:TerminalRecord.failure.message
    $script:FailureDetail = ConvertTo-Json -InputObject ([pscustomobject]@{ supervisor_failure = $script:TerminalRecord.failure; transport_failure_category = $script:TransportFailureCategory; transport_failure_message = $script:TransportFailureMessage }) -Depth 30 -Compress
}

function New-PhaseReceipt {
    param([string]$Status, [string]$Nonce)
    $preservation = [pscustomobject]@{ before = $script:HostBefore; after = $script:HostAfter }
    $equal = ($null -ne $script:HostBefore -and $null -ne $script:HostAfter -and (Test-PreservationEqual $script:HostBefore $script:HostAfter))
    $terminalGood = ($null -ne $script:TerminalRecord -and $script:TerminalRecord.status -ceq 'SUBJECT_COMPLETE')
    $elapsed = [int][Math]::Min([int]::MaxValue, $script:Clock.ElapsedMilliseconds)
    $receipt = [pscustomobject]@{
        schema = 'ladybug.feat010.sro.host-phase-evidence.v1'; phase = $Phase; attempt = 1; nonce = $Nonce
        manifest_sha256 = $script:ManifestSha256; ticket_sha256 = $script:TicketSha256
        source_sha256 = [pscustomobject]$script:SourceSha256; fixture_sha256 = [pscustomobject]$script:FixtureSha256; read_inputs_sha256 = [pscustomobject]$script:ReadInputsSha256
        status = $Status; admitted = ($Status -ceq 'PASS'); host_claim = $script:HostClaim; host_oracle = @($script:HostOracle); host_cases = @($script:HostCases)
        ready = $script:ReadyRecord; terminal = $script:TerminalRecord
        worker_exit = if ($null -ne $script:TerminalRecord) { $script:TerminalRecord.worker_exit } else { $null }
        driver_exit_confirmed = [bool]$script:DriverExitConfirmed; driver_exit_code = $script:DriverExitCode; driver_is_wsl_only = $true
        protocol_records = @($script:ProtocolRecords.ToArray()); protocol_lines = @($script:ProtocolLines.ToArray()); stderr = $script:StderrText; stdout_tail = $script:StdoutTail
        failure_category = $script:FailureCategory; failure_message = $script:FailureMessage; failure_detail = $script:FailureDetail
        transport_failure_category = $script:TransportFailureCategory; transport_failure_message = $script:TransportFailureMessage; transport_failure_detail = $script:TransportFailureDetail
        preservation = $preservation; preservation_equal = [bool]$equal; subject_complete = [bool]$terminalGood
        go_budget_ms = $script:GoBudgetMs; elapsed_ms = $elapsed; maximum_ms = [int]$script:PhaseLimits[$Phase]
        evidence_write_started_elapsed_ms = $elapsed; evidence_written_utc = [DateTime]::UtcNow.ToString('o')
    }
    return $receipt
}

function Invoke-Phase {
    $nonce = [Guid]::NewGuid().ToString('N').ToLowerInvariant()
    $script:PhaseNonce = $nonce
    $success = $false
    $claimObject = $null
    try {
        if (-not [System.IO.Directory]::Exists($script:EvidenceDirectory)) { throw 'parent evidence directory is missing' }
        Read-AndValidateFreeze
        $priorClaim = $script:ClaimPath
        if ([System.IO.File]::Exists($priorClaim) -or [System.IO.File]::Exists($script:ReceiptPath) -or [System.IO.File]::Exists($script:OverrunPath)) { throw 'one-shot phase claim/result already exists; collision preserved and no retry is allowed' }
        $claimObject = Write-PhaseClaim $script:ClaimPath $Phase $nonce $script:ManifestSha256
        $script:ClaimCreated = $true
        $script:ClaimCollision = Test-ClaimCollisionPreservation $script:ClaimPath $nonce
        $collisionPreserved = ($script:ClaimCollision.rejected -and $script:ClaimCollision.original_preserved)
        $script:HostClaim = [pscustomobject]@{ exclusive = $true; collision_preserved = [bool]$collisionPreserved; launch_argv = $script:LaunchArgv }
        if (-not (Test-HostClaim $script:HostClaim)) { throw 'host launch claim does not match fixed exact argv contract' }
        if ($Phase -ceq 'stop-observation-admission') { $script:HostOracle = Invoke-HostOracle $script:HostClaim $script:ClaimPath $nonce }
        $remainingPreflight = ([int]$script:PhaseLimits[$Phase] - $script:GoReserveMs - $script:DriverWaitReserveMs - $script:EvidenceReserveMs) - [int]$script:Clock.ElapsedMilliseconds
        if ($remainingPreflight -le 0) { throw 'preflight exceeded the fixed phase budget reserve' }
        Start-PinnedSupervisor
        Send-InitAndGo $nonce
        Confirm-DirectDriverExit
        $script:HostAfter = Get-HostPreservationSnapshot $script:Freeze $script:Execution $script:ManifestSha256
        if (-not (Test-PreservationEqual $script:HostBefore $script:HostAfter)) { throw 'host before/after preservation hashes differ' }
        Test-PhaseTerminal
        if ($Phase -ceq 'stop-observation-compatibility') {
            $script:HostCases = @(New-HostC06 $script:TerminalRecord $script:DriverExitConfirmed $script:DriverExitCode $true)
            if (@($script:HostCases).Count -ne 1 -or -not (Test-HostC06 $script:HostCases[0] $script:TerminalRecord $script:DriverExitConfirmed $script:DriverExitCode $true)) { throw 'host-derived C06 cleanup proof failed' }
        }
        if (-not (Test-ExactBoolean $script:DriverExitConfirmed) -or $script:DriverExitConfirmed -ne $true -or -not (Test-ExactInteger $script:DriverExitCode) -or $script:DriverExitCode -ne 0) { throw 'prewrite subject checks lack a confirmed direct WSL exit zero' }
        if (-not (Test-PreservationEqual $script:HostBefore $script:HostAfter)) { throw 'prewrite subject checks lack equal preservation snapshots' }
        $prewriteElapsed = [long][Math]::Ceiling($script:Clock.Elapsed.TotalMilliseconds)
        if ($prewriteElapsed -ge ([int]$script:PhaseLimits[$Phase] - $script:EvidenceReserveMs)) { throw 'prewrite subject checks left no reserved time for durable evidence' }
        $success = $true
    } catch {
        $caughtMessage = $_.Exception.Message
        $caughtDetail = $_.Exception.ToString()
        if ($null -eq $script:TransportFailureCategory) {
            $script:TransportFailureCategory = if ($null -ne $script:StdoutState -and ($script:StdoutState.protocol_overflow -or $script:StdoutState.protocol_error -or $script:StdoutState.extra_stdout)) { 'PROTOCOL' } else { 'HOST_OR_OBSERVER_FAILURE' }
        }
        if ($null -eq $script:TransportFailureMessage) { $script:TransportFailureMessage = $caughtMessage }
        if ($null -eq $script:TransportFailureDetail) { $script:TransportFailureDetail = $caughtDetail }
        if ($null -eq $script:FailureCategory) { $script:FailureCategory = $script:TransportFailureCategory }
        if ($null -eq $script:FailureMessage) { $script:FailureMessage = $script:TransportFailureMessage }
        if ($null -eq $script:FailureDetail) { $script:FailureDetail = $script:TransportFailureDetail }
        $cleanupError = $null
        if ($null -ne $script:Driver -and $script:DriverStarted) {
            try { $script:Driver.StandardInput.Close() } catch { }
            try {
                Drain-DriverStreams ([int]$script:PhaseLimits[$Phase] - $script:EvidenceReserveMs) $false
            } catch {
                $cleanupError = $_.Exception.ToString()
                if ($null -eq $script:TransportFailureDetail) { $script:TransportFailureDetail = 'bounded stream cleanup: ' + $_.Exception.Message }
            }
            if (-not $script:DriverExitConfirmed) {
                $waitFailure = 'direct wsl.exe exit was not confirmed before the existing evidence reserve'
                if ($null -eq $script:TransportFailureDetail) { $script:TransportFailureDetail = $waitFailure }
                Retain-UnresolvedDriverCleanup $waitFailure
            }
        }
        if ($null -ne $script:Freeze -and $null -ne $script:Execution) {
            try { $script:HostAfter = Get-HostPreservationSnapshot $script:Freeze $script:Execution $script:ManifestSha256 } catch { $script:PreservationError = $_.Exception.Message }
        }
        Set-BoundSupervisorFailureClassification
        Capture-DriverFailureEvidence $caughtDetail $cleanupError
        $success = $false
    }
    if (-not $script:ClaimCreated) {
        [System.Console]::Error.WriteLine((Limit-CleanupDetail ([string]$script:FailureMessage)))
        if ($script:BoundedReadFailures.Count -gt 0) {
            $lastReadFailures = @($script:BoundedReadFailures.ToArray() | Select-Object -Last 2)
            $compactReadFailures = New-Object System.Collections.ArrayList
            foreach ($failure in $lastReadFailures) {
                $stage = [string]$failure.stage
                $path = [string]$failure.path
                $rejection = [string]$failure.rejection
                if ($stage.Length -gt 128) { $stage = $stage.Substring(0, 128) }
                if ($path.Length -gt 256) { $path = $path.Substring(0, 256) }
                if ($rejection.Length -gt 128) { $rejection = $rejection.Substring(0, 128) }
                [void]$compactReadFailures.Add([pscustomobject]@{
                    stage = $stage; path = $path; rejection = $rejection
                    position = $failure.position; actual_position = $failure.actual_position
                    retained_bytes = $failure.retained_bytes; text_units = $failure.text_units
                    whole_document_decode_attempted = $failure.whole_document_decode_attempted
                    sha256 = $failure.sha256; prefix_b64 = $failure.prefix_b64
                })
            }
            $boundedReadSummary = ConvertTo-Json -InputObject @($compactReadFailures.ToArray()) -Depth 5 -Compress
            [System.Console]::Error.WriteLine('bounded_file_reads=' + [string]$boundedReadSummary)
        }
        return [bool]$false
    }
    if ($success -and [Math]::Ceiling($script:Clock.Elapsed.TotalMilliseconds) -ge ([int]$script:PhaseLimits[$Phase] - $script:EvidenceReserveMs)) {
        $success = $false
        $script:FailureCategory = 'PHASE_DEADLINE'
        $script:FailureMessage = 'phase left no reserved time to finalize durable evidence'
    }
    $receiptStatus = if ($success) { 'PASS' } else { 'FAIL' }
    $receipt = New-PhaseReceipt $receiptStatus $nonce
    if ($null -ne $script:PreservationError) { $receipt.preservation_error = $script:PreservationError }
    try {
        Write-JsonCreateNew $script:ReceiptPath $receipt
    } catch {
        $success = $false
        $script:FailureCategory = 'EVIDENCE_FINALIZATION_FAILURE'
        $finalizationError = $_.Exception.Message
        $script:FailureMessage = $finalizationError
        $script:FailureDetail = $_.Exception.ToString()
        try { Write-JsonCreateNew $script:OverrunPath ([pscustomobject]@{ phase = $Phase; nonce = $nonce; failure_category = $script:FailureCategory; failure_message = $script:FailureMessage; failure_detail = $script:FailureDetail; receipt_path = $script:ReceiptPath }) } catch { }
        [System.Console]::Error.WriteLine('phase evidence could not be finalized: ' + $finalizationError)
        return [bool]$false
    }
    if ($success) {
        $postWriteAdmission = $true
        $overrunMarkerWritten = $true
        $elapsedAfterWrite = [long][Math]::Ceiling($script:Clock.Elapsed.TotalMilliseconds)
        $finalizationComplete = [System.IO.File]::Exists($script:ReceiptPath)
        $finalContext = [pscustomobject]@{ phase = $Phase; host_case = if (@($script:HostCases).Count -gt 0) { $script:HostCases[0] } else { $null } }
        $finalReason = $null
        $postWriteAdmission = Test-FinalAdmission $script:TerminalRecord $finalContext $script:DriverExitConfirmed $script:DriverExitCode ([bool](Test-PreservationEqual $script:HostBefore $script:HostAfter)) $finalizationComplete $elapsedAfterWrite ([int]$script:PhaseLimits[$Phase]) ([ref]$finalReason)
        $elapsedAfterAdmission = [long][Math]::Ceiling($script:Clock.Elapsed.TotalMilliseconds)
        if ($postWriteAdmission -and $elapsedAfterAdmission -gt [int]$script:PhaseLimits[$Phase]) {
            $postWriteAdmission = $false
            $elapsedAfterWrite = $elapsedAfterAdmission
            $finalReason = 'host final-admission evaluation crossed the entire-phase deadline'
        }
        if (-not $postWriteAdmission) {
            $success = $false
            $script:FailureCategory = if ($elapsedAfterWrite -gt [int]$script:PhaseLimits[$Phase]) { 'PHASE_OVERRUN_AFTER_EVIDENCE' } else { 'FINAL_ADMISSION_FAILURE' }
            $script:FailureMessage = 'post-write final admission failed: ' + $finalReason
            $script:FailureDetail = ConvertTo-Json -InputObject ([pscustomobject]@{ elapsed_after_write_ms = $elapsedAfterWrite; finalization_complete = [bool]$finalizationComplete; reason = $finalReason; receipt_path = $script:ReceiptPath }) -Depth 20 -Compress
            try {
                Write-JsonCreateNew $script:OverrunPath ([pscustomobject]@{ phase = $Phase; nonce = $nonce; elapsed_ms = $elapsedAfterWrite; maximum_ms = [int]$script:PhaseLimits[$Phase]; failure_category = $script:FailureCategory; failure_message = $script:FailureMessage; failure_detail = $script:FailureDetail; receipt_path = $script:ReceiptPath })
            } catch {
                $overrunMarkerWritten = $false
                $script:TransportFailureCategory = 'EVIDENCE_FINALIZATION_FAILURE'
                $script:TransportFailureMessage = 'post-write final admission failed and its exclusive overrun marker could not be retained'
                $script:TransportFailureDetail = $_.Exception.ToString()
                $script:FailureCategory = $script:TransportFailureCategory
                $script:FailureMessage = $script:TransportFailureMessage
                $script:FailureDetail = ConvertTo-Json -InputObject ([pscustomobject]@{ final_admission = $finalReason; marker_write_error = $script:TransportFailureDetail; receipt_path = $script:ReceiptPath }) -Depth 20 -Compress
            }
        }
        $finalOutcome = Get-PostWriteFinalOutcome $postWriteAdmission $overrunMarkerWritten
        if (-not $finalOutcome.success) { $success = $false }
    }
    if ($success -and (Get-PostWriteFinalOutcome $true $true).pass_marker_allowed) {
        [System.Console]::Error.WriteLine('SRO_PHASE_PASS ' + $Phase + ' ' + $nonce)
        return [bool]$true
    }
    [System.Console]::Error.WriteLine('SRO_PHASE_FAIL ' + $Phase + ' ' + $script:FailureCategory + ' ' + $script:FailureMessage)
    return [bool]$false
}

if (-not (Invoke-Phase)) { exit 1 }
exit 0
