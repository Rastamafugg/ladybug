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
    'CLAIM_COLLISION_PRESERVES_BYTES'
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
    Q01 = @('valid','owner','session','generation','token','sequence','boolean','mi_error','current_state','cause_id')
    Q02 = @('capture_hash','formatted_attach_is_unknown','no_native_signal_field')
    Q03 = @('same_raw_event','different_hypothetical_cause','same_event_only_classification')
    Q04 = @('exclusive_claim','collision_preserved','pinned_allowlist','popen_type_preserved','popen_denied','no_real_factory')
    Q05 = @('baseline-zero','baseline-connection','baseline-bool','baseline-string','baseline-null','baseline-missing','baseline-nonce','baseline-owner','baseline-session','baseline-generation','baseline-stream','baseline-duplicate','baseline-malformed','baseline-truncated','baseline-python','baseline-api','baseline-mi-error','baseline-token','baseline-invalidated')
    R01 = @('startup','claim','baseline','attach','fresh_attach_state','pre_continue_state','breakpoint','continue','fresh_continue_state','reader_count','raw_count','process_exit','reader_exit','no_cause_claim')
    R02 = @('historical_source_pin','missing_claim_api','missing_exec_api','missing_stop_api','not_setup_failure')
    R03 = @('literal_hash','empty_connections_once','one_connection_once','exact_zero_stdout','exact_one_stdout','module_restored','no_io')
    R04 = @('baseline-control-zero','baseline-control-connection','baseline-control-bool','baseline-control-string','baseline-control-null','baseline-control-missing','baseline-control-nonce','baseline-control-owner','baseline-control-session','baseline-control-generation','baseline-control-stream','baseline-control-duplicate','baseline-control-malformed','baseline-control-truncated','baseline-control-python','baseline-control-api','baseline-control-mi-error','baseline-control-token','baseline-control-invalidated')
    R05 = @('preclaim_user_send','preclaim_interrupt','stale_stop','buffered_output','no_retroactive_claim')
    R06 = @('wrong_token','duplicate_result','pre_result_prompt','mi_error','no_validated_result')
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
$script:LaunchAllowlist = @('wsl.exe', $script:PythonPath, '-B', 'stop-q.py', '--supervisor')
$script:GoReserveMs = 10000
$script:DriverWaitReserveMs = 2500
$script:EvidenceReserveMs = 1500
$script:ProtocolLineMaximumCharacters = 262144
$script:ProtocolLineMaximumBytes = 262144
$script:Driver = $null
$script:DriverStarted = $false
$script:DriverIdentity = $null
$script:StdoutTask = $null
$script:StderrTask = $null
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
$script:ClaimPath = Join-Path $script:EvidenceDirectory ($Phase + '.claim')
$script:ReceiptPath = Join-Path $script:EvidenceDirectory ($Phase + '.json')
$script:OverrunPath = Join-Path $script:EvidenceDirectory ($Phase + '-overrun.json')
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
    if ($Value.schema -cne 'ladybug.feat010.controller-integration.freeze.v1' -or $Value.runtime_ready -isnot [bool] -or $Value.runtime_ready -ne $false -or -not (Test-ExactInteger $Value.runtime_attempts_authorized) -or $Value.runtime_attempts_authorized -ne 0 -or $Value.installation_authorized -isnot [bool] -or $Value.installation_authorized -ne $false) { return $false }
    if ($Value.qualification_dispatch_authorized -isnot [bool] -or $Value.qualification_dispatch_authorized -ne $true) { return $false }
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
    if (-not (Test-ObjectShape $Claim @('exclusive','collision_preserved','launch_allowlist'))) { return $false }
    if ($Claim.exclusive -isnot [bool] -or $Claim.exclusive -ne $true -or $Claim.collision_preserved -isnot [bool] -or $Claim.collision_preserved -ne $true) { return $false }
    return (Test-StringArray $Claim.launch_allowlist $script:LaunchAllowlist)
}

function Test-AdmissionEnvelope {
    param([object]$Record, [string]$ExpectedPhase, [string]$Nonce, [string]$Manifest, [string]$Ticket, [object]$Sources, [object]$Fixtures, [object]$ReadInputs, [int]$MaximumMs, [ref]$Reason)
    $Reason.Value = 'READY rejected'
    $keys = @('kind','phase','nonce','manifest_sha256','ticket_sha256','source_sha256','fixture_sha256','read_inputs_sha256','supervisor_identity','supervisor_elapsed_ms')
    if (-not (Test-ObjectShape $Record $keys)) { return $false }
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
        if (-not (Test-ObjectShape $control @('id','status','observed')) -or $control.id -cne $expected[$i] -or ($control.status -cne 'PASS' -and ($Complete -or $control.status -cne 'FAIL'))) { return $false }
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
        if (-not (Test-ObjectShape $case @('case_id','expected','status','observations')) -or $case.case_id -cne $expectedIds[$i] -or $case.expected -cne $script:ExpectedByCase[$expectedIds[$i]]) { return $false }
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
    if ($null -eq $Terminal -or $Terminal.status -cne 'SUBJECT_COMPLETE') { return $false }
    if (-not (Test-ExactBoolean $DriverWaitConfirmed) -or $DriverWaitConfirmed -ne $true -or -not (Test-ExactInteger $DriverExitCode) -or $DriverExitCode -ne 0) { return $false }
    if (-not (Test-ExactBoolean $PreservationEqual) -or $PreservationEqual -ne $true -or -not (Test-ExactBoolean $FinalizationComplete) -or $FinalizationComplete -ne $true) { return $false }
    if (-not (Test-ExactInteger $ElapsedMs) -or $ElapsedMs -lt 0 -or $ElapsedMs -gt $MaximumMs -or -not (Test-ExactInteger $Terminal.phase_elapsed_ms) -or $Terminal.phase_elapsed_ms -gt $MaximumMs) { return $false }
    if ($null -ne $Context -and $Context.phase -ceq 'stop-observation-compatibility') {
        if (-not (Test-HostC06 $Context.host_case $Terminal $DriverWaitConfirmed $DriverExitCode $PreservationEqual)) { return $false }
    }
    $Reason.Value = $null
    return $true
}

function Get-FileSha256 {
    param([string]$Path)
    if (-not [System.IO.File]::Exists($Path)) { throw ('pinned file is missing: ' + $Path) }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
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

function Read-ProtocolLine {
    param([int]$DeadlineElapsedMs, [string]$Label)
    $remaining = $DeadlineElapsedMs - [int]$script:Clock.ElapsedMilliseconds
    if ($remaining -le 0) { throw ($Label + ' deadline expired before read') }
    $script:StdoutTask = $script:Driver.StandardOutput.ReadLineAsync()
    $script:StdoutReadPending = $true
    try { $completed = $script:StdoutTask.Wait($remaining) } catch { throw ($Label + ' stream read failed: ' + $_.Exception.Message) }
    if (-not $completed) { throw ($Label + ' timed out at the phase boundary') }
    try { $line = $script:StdoutTask.GetAwaiter().GetResult() } catch { throw ($Label + ' stream read failed: ' + $_.Exception.Message) }
    $script:StdoutReadPending = $false
    if ($null -ne $line -and -not (Test-ProtocolLineWithinLimit $line)) {
        [void]$script:ProtocolLines.Add((Limit-RetainedText $line 65536))
        throw ($Label + ' JSON line exceeded the bounded 262144-byte protocol-line limit')
    }
    [void]$script:ProtocolLines.Add($line)
    return Read-JsonLine $line $Label
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
            $expected = if ($id -match '(_VALID$|^PREV_VALID$|^TERM_FAIL_UNCONFIRMED_NULL_EXIT$)') { 'ACCEPT' } else { 'REJECT' }
            [void]$rows.Add([pscustomobject]@{ id = $id; expected = $expected; observed = $expected; status = 'PASS'; reason = 'synthetic retained-shape oracle row' })
        }
    }
    return @($rows.ToArray())
}

function New-SyntheticRetainedProof {
    $records = New-SyntheticRecords 'stop-observation-admission'
    $hostClaim = [pscustomobject]@{ exclusive = $true; collision_preserved = $true; launch_allowlist = $script:LaunchAllowlist }
    $started = [DateTime]::UtcNow.ToString('o')
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
        evidence_write_started_elapsed_ms = 100; evidence_written_utc = [DateTime]::UtcNow.ToString('o')
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
            if (-not (Test-ObjectShape $row @('id','expected','observed','status','original_sha256','after_sha256')) -or $row.id -cne $id -or $row.expected -cne 'REJECT_AND_PRESERVE' -or $row.observed -cne 'REJECT_AND_PRESERVE' -or $row.status -cne 'PASS' -or -not (Test-Sha256 $row.original_sha256) -or $row.original_sha256 -cne $row.after_sha256) { return $false }
        } else {
            if (-not (Test-ObjectShape $row @('id','expected','observed','status','reason')) -or $row.id -cne $id -or $row.status -cne 'PASS') { return $false }
            $expected = if ($id -match '(_VALID$|^PREV_VALID$|^TERM_FAIL_UNCONFIRMED_NULL_EXIT$)') { 'ACCEPT' } else { 'REJECT' }
            if ($row.expected -cne $expected -or $row.observed -cne $expected -or ($null -ne $row.reason -and $row.reason -isnot [string])) { return $false }
        }
    }
    return $true
}

function Test-RetainedPhaseEvidence {
    param([object]$Claim, [object]$Receipt, [string]$ExpectedPhase, [string]$Manifest, [string]$Ticket, [object]$Sources, [object]$Fixtures, [object]$ReadInputs, [object]$ExpectedPreservation, [ref]$Reason)
    $Reason.Value = 'retained phase evidence rejected'
    $claimKeys = @('phase','nonce','manifest_sha256','attempt','started_utc')
    if (-not (Test-ObjectShape $Claim $claimKeys) -or $Claim.phase -cne $ExpectedPhase -or $Claim.nonce -isnot [string] -or $Claim.nonce -cnotmatch '^[0-9a-f]{32}$' -or $Claim.manifest_sha256 -cne $Manifest -or -not (Test-ExactInteger $Claim.attempt) -or $Claim.attempt -ne 1 -or $Claim.started_utc -isnot [string]) { return $false }
    $receiptKeys = @('schema','phase','attempt','nonce','manifest_sha256','ticket_sha256','source_sha256','fixture_sha256','read_inputs_sha256','status','admitted','host_claim','host_oracle','host_cases','ready','terminal','worker_exit','driver_exit_confirmed','driver_exit_code','driver_is_wsl_only','protocol_records','protocol_lines','stderr','stdout_tail','failure_category','failure_message','failure_detail','transport_failure_category','transport_failure_message','transport_failure_detail','preservation','preservation_equal','subject_complete','go_budget_ms','elapsed_ms','maximum_ms','evidence_write_started_elapsed_ms','evidence_written_utc')
    if (-not (Test-ObjectShape $Receipt $receiptKeys) -or $Receipt.schema -cne 'ladybug.feat010.sro.host-phase-evidence.v1' -or $Receipt.phase -cne $ExpectedPhase -or -not (Test-ExactInteger $Receipt.attempt) -or $Receipt.attempt -ne 1 -or $Receipt.nonce -cne $Claim.nonce -or $Receipt.manifest_sha256 -cne $Manifest -or $Receipt.ticket_sha256 -cne $Ticket) { return $false }
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
    } else {
        $accepted = Test-FinalAdmission $Value.terminal $Context $Value.driver_wait $Value.driver_exit $Value.preservation_equal $Value.finalized $Value.elapsed_ms 30000 ([ref]$reason)
    }
    $passed = (($accepted -eq $ExpectedAccepted))
    return [pscustomobject]@{ id = $Id; expected = $(if ($ExpectedAccepted) { 'ACCEPT' } else { 'REJECT' }); observed = $(if ($accepted) { 'ACCEPT' } else { 'REJECT' }); status = $(if ($passed) { 'PASS' } else { 'FAIL' }); reason = $reason }
}

function Invoke-HostOracle {
    param([object]$ActualHostClaim, [string]$ClaimPath, [string]$Nonce)
    $context = New-SyntheticRecords 'stop-observation-admission'
    $results = New-Object System.Collections.ArrayList
    [void]$results.Add((Invoke-OracleControl 'READY_VALID' 'ready' $context.ready $true $context))
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
        [void]$results.Add((Invoke-OracleControl $id 'ready' $copy $false $context))
    }
    [void]$results.Add((Invoke-OracleControl 'TERMINAL_VALID' 'terminal' $context.terminal $true $context))
    $workerWaitUnknown = Copy-JsonValue $context.terminal
    $workerWaitUnknown.status = 'FAIL'
    $workerWaitUnknown.worker_exit.wait_confirmed = $false
    $workerWaitUnknown.worker_exit.returncode = $null
    $workerWaitUnknown.cases = @()
    $workerWaitUnknown.failure = [pscustomobject]@{ category = 'TIMEOUT'; case_id = $null; subcontrol = $null; message = 'worker wait deadline expired'; observed = [pscustomobject]@{ wait_confirmed = $false } }
    [void]$results.Add((Invoke-OracleControl 'TERM_FAIL_UNCONFIRMED_NULL_EXIT' 'terminal' $workerWaitUnknown $true $context))
    $workerWaitInventedZero = Copy-JsonValue $workerWaitUnknown
    $workerWaitInventedZero.worker_exit.returncode = 0
    [void]$results.Add((Invoke-OracleControl 'TERM_FAIL_UNCONFIRMED_ZERO_EXIT' 'terminal' $workerWaitInventedZero $false $context))
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
        [void]$results.Add((Invoke-OracleControl $id 'terminal' $copy $false $context))
    }
    $finalContext = [pscustomobject]@{ phase = $context.ready.phase; nonce = $context.nonce; manifest = $context.manifest; ticket = $context.ticket; snapshot = $context.snapshot; ready = $context.ready }
    $finalValid = [pscustomobject]@{ terminal = $context.terminal; driver_wait = $true; driver_exit = 0; preservation_equal = $true; finalized = $true; elapsed_ms = 100 }
    [void]$results.Add((Invoke-OracleControl 'FINAL_VALID' 'final' $finalValid $true $finalContext))
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
        [void]$results.Add((Invoke-OracleControl $id 'final' $copy $false $finalContext))
    }
    $compatibility = New-SyntheticRecords 'stop-observation-compatibility'
    $compatibilityCase = New-HostC06 $compatibility.terminal $true 0 $true
    $compatibilityContext = [pscustomobject]@{ phase = 'stop-observation-compatibility'; host_case = $compatibilityCase }
    $finalC06 = [pscustomobject]@{ terminal = $compatibility.terminal; driver_wait = $true; driver_exit = 0; preservation_equal = $true; finalized = $true; elapsed_ms = 100 }
    [void]$results.Add((Invoke-OracleControl 'FINAL_C06_VALID' 'final' $finalC06 $true $compatibilityContext))
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
        [void]$results.Add((Invoke-OracleControl $id 'final' $copy $false $contextCopy))
    }
    $jsonVectors = @(
        [pscustomobject]@{ id = 'JSON_UNIQUE_VALID'; text = '{"name":"escaped \"quote\"","nested":[true,false,null,{"key":"\u0078"}]}' ; expected = $true },
        [pscustomobject]@{ id = 'JSON_DUPLICATE_KEY'; text = '{"x":1,"x":2}'; expected = $false },
        [pscustomobject]@{ id = 'JSON_ESCAPED_DUPLICATE_KEY'; text = '{"x":1,"\u0078":2}'; expected = $false },
        [pscustomobject]@{ id = 'JSON_NESTED_DUPLICATE_KEY'; text = '{"outer":{"n":1,"n":2}}'; expected = $false },
        [pscustomobject]@{ id = 'JSON_MALFORMED'; text = '{"x":]'; expected = $false }
    )
    foreach ($vector in $jsonVectors) { [void]$results.Add((Invoke-OracleControl $vector.id 'json' $vector.text $vector.expected $null)) }
    $retained = New-SyntheticRetainedProof
    $retainedContext = [pscustomobject]@{ manifest = $retained.receipt.manifest_sha256; ticket = $retained.receipt.ticket_sha256; snapshot = $retained.snapshot }
    [void]$results.Add((Invoke-OracleControl 'PREV_VALID' 'retained' $retained $true $retainedContext))
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
        [void]$results.Add((Invoke-OracleControl $id 'retained' $copy $false $retainedContext))
    }
    if (-not (Test-HostClaim $ActualHostClaim)) { throw 'host claim object failed its actual claim validator' }
    $collision = $script:ClaimCollision
    $collisionPassed = ($null -ne $collision -and $collision.rejected -is [bool] -and $collision.rejected -eq $true -and $collision.original_preserved -is [bool] -and $collision.original_preserved -eq $true)
    $collisionRow = [pscustomobject]@{ id = 'CLAIM_COLLISION_PRESERVES_BYTES'; expected = 'REJECT_AND_PRESERVE'; observed = $(if ($collisionPassed) { 'REJECT_AND_PRESERVE' } else { 'MISMATCH' }); status = $(if ($collisionPassed) { 'PASS' } else { 'FAIL' }); original_sha256 = $collision.original_sha256; after_sha256 = $collision.after_sha256 }
    [void]$results.Add($collisionRow)
    if (@($results | Where-Object { $_.status -cne 'PASS' }).Count -gt 0) { throw 'host-oracle negative or collision control failed' }
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
    $beforeBytes = [System.IO.File]::ReadAllBytes($Path)
    $beforeHash = Get-BytesSha256 $beforeBytes
    $rejected = $false
    try { Write-NewUtf8File $Path ('COLLISION-' + $Nonce) }
    catch [System.IO.IOException] { $rejected = $true }
    if (-not [System.IO.File]::Exists($Path)) { throw 'claim collision removed the original claim' }
    $afterHash = Get-BytesSha256 ([System.IO.File]::ReadAllBytes($Path))
    return [pscustomobject]@{ rejected = [bool]$rejected; original_preserved = [bool]($beforeHash -ceq $afterHash); original_sha256 = $beforeHash; after_sha256 = $afterHash }
}

function Test-HostC06 {
    param([object]$Case, [object]$Terminal, [object]$DriverWait, [object]$DriverExit, [object]$PreservationEqual)
    if (-not (Test-ObjectShape $Case @('case_id','expected','status','observations')) -or $Case.case_id -cne 'C06' -or $Case.expected -cne $script:ExpectedByCase.C06 -or $Case.status -cne 'PASS') { return $false }
    if ($null -eq $Case.observations -or $Case.observations -is [string] -or $Case.observations -is [System.Array]) { return $false }
    $controlsProperty = $Case.observations.PSObject.Properties['subcontrols']
    if ($null -eq $controlsProperty -or $controlsProperty.Value -isnot [System.Array]) { return $false }
    $controls = @($controlsProperty.Value)
    $expectedIds = @($script:CaseSubcontrols.C06)
    if ($controls.Count -ne $expectedIds.Count) { return $false }
    for ($i = 0; $i -lt $expectedIds.Count; $i++) {
        if (-not (Test-ObjectShape $controls[$i] @('id','status','observed')) -or $controls[$i].id -cne $expectedIds[$i] -or $controls[$i].status -cne 'PASS' -or $controls[$i].observed -isnot [bool] -or $controls[$i].observed -ne $true) { return $false }
    }
    if (-not (Test-ObjectShape $Case.observations @('subcontrols','worker_exit','wsl_wait_confirmed','wsl_exit_code','preservation_equal'))) { return $false }
    if (-not (Test-ObjectShape $Case.observations.worker_exit @('wait_confirmed','returncode')) -or $Case.observations.worker_exit.wait_confirmed -isnot [bool] -or $Case.observations.worker_exit.wait_confirmed -ne $Terminal.worker_exit.wait_confirmed -or -not (Test-ExactInteger $Case.observations.worker_exit.returncode) -or $Case.observations.worker_exit.returncode -ne $Terminal.worker_exit.returncode) { return $false }
    if ($Case.observations.wsl_wait_confirmed -isnot [bool] -or $Case.observations.wsl_wait_confirmed -ne $DriverWait -or -not (Test-ExactInteger $Case.observations.wsl_exit_code) -or $Case.observations.wsl_exit_code -ne $DriverExit -or $Case.observations.preservation_equal -isnot [bool] -or $Case.observations.preservation_equal -ne $PreservationEqual) { return $false }
    return ($Terminal.status -ceq 'SUBJECT_COMPLETE' -and (Test-ExactBoolean $Terminal.worker_exit.wait_confirmed) -and $Terminal.worker_exit.wait_confirmed -eq $true -and (Test-ExactInteger $Terminal.worker_exit.returncode) -and $Terminal.worker_exit.returncode -eq 0 -and (Test-ExactBoolean $DriverWait) -and $DriverWait -eq $true -and (Test-ExactInteger $DriverExit) -and $DriverExit -eq 0 -and (Test-ExactBoolean $PreservationEqual) -and $PreservationEqual -eq $true)
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
        $receiptPath = Join-Path $script:EvidenceDirectory ($prior + '.json')
        $claimPath = Join-Path $script:EvidenceDirectory ($prior + '.claim')
        $overrunPath = Join-Path $script:EvidenceDirectory ($prior + '-overrun.json')
        if (-not [System.IO.File]::Exists($receiptPath) -or -not [System.IO.File]::Exists($claimPath) -or [System.IO.File]::Exists($overrunPath)) { throw ('matching predecessor PASS is absent or invalid: ' + $prior) }
        try {
            $encoding = New-Object System.Text.UTF8Encoding($false, $true)
            $claimRaw = [System.IO.File]::ReadAllText($claimPath, $encoding)
            $receiptRaw = [System.IO.File]::ReadAllText($receiptPath, $encoding)
            if (-not (Test-JsonWithUniqueKeys $claimRaw) -or -not (Test-JsonWithUniqueKeys $receiptRaw)) { throw 'claim or receipt contained malformed JSON or duplicate object keys' }
            $claim = ConvertFrom-Json -InputObject $claimRaw -ErrorAction Stop
            $receipt = ConvertFrom-Json -InputObject $receiptRaw -ErrorAction Stop
        } catch { throw ('predecessor evidence is not valid unique-key UTF-8 JSON: ' + $prior + ': ' + $_.Exception.Message) }
        $reason = $null
        if (-not (Test-RetainedPhaseEvidence $claim $receipt $prior $Manifest $Ticket $Sources $Fixtures $ReadInputs $script:HostBefore ([ref]$reason))) { throw ('predecessor evidence failed strict nested admission: ' + $prior + ': ' + $reason) }
    }
}

function Read-AndValidateFreeze {
    if (-not [System.IO.File]::Exists($script:FreezePath)) { throw 'integration freeze is missing' }
    $script:ManifestSha256 = Get-FileSha256 $script:FreezePath
    $raw = [System.IO.File]::ReadAllText($script:FreezePath, (New-Object System.Text.UTF8Encoding($false, $true)))
    if (-not (Test-JsonWithUniqueKeys $raw)) { throw 'integration freeze contains malformed JSON or duplicate object keys' }
    try { $script:Freeze = ConvertFrom-Json -InputObject $raw -ErrorAction Stop } catch { throw ('integration freeze JSON is invalid: ' + $_.Exception.Message) }
    $reason = $null
    if (-not (Test-FreezeEnvelope $script:Freeze ([ref]$reason))) { throw ('parent freeze is not fully authorized for this one-shot source-profile gate: ' + $reason) }
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
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'wsl.exe'
    $scriptPath = '/mnt/e/projects/ladybug/repro/feat010-menu-clock-repair-20261018/controller-integration-20261019/stop-q.py'
    $psi.Arguments = '--exec ' + $script:PythonPath + ' -B ' + $scriptPath + ' --supervisor'
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
        requested_image = 'wsl.exe'
        pid = $driverPid
        start_time_utc_ticks = $driverStartTicks
        capture_error = $driverIdentityError
    }
    $script:StderrTask = $script:Driver.StandardError.ReadToEndAsync()
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
    if (-not (Test-AdmissionEnvelope $ready $Phase $Nonce $script:ManifestSha256 $script:TicketSha256 ([pscustomobject]$script:SourceSha256) ([pscustomobject]$script:FixtureSha256) ([pscustomobject]$script:ReadInputsSha256) $phaseLimit ([ref]$reason)) { throw ('supervisor READY rejected: ' + $reason) }
    $script:ReadyRecord = $ready
    $remaining = [int][Math]::Floor($terminalCutoff - $script:Clock.ElapsedMilliseconds)
    if ($remaining -le 0) { throw 'phase preflight left no positive relative GO budget' }
    $script:GoBudgetMs = $remaining
    $go = [pscustomobject]@{ kind = 'GO'; phase = $Phase; nonce = $Nonce; manifest_sha256 = $script:ManifestSha256; remaining_ms = $remaining }
    Write-ProtocolLine $go
    $script:Driver.StandardInput.Close()
    $script:TerminalRecord = Read-ProtocolLine $terminalCutoff 'TERMINAL'
}

function Limit-RetainedText {
    param([string]$Value, [int]$MaximumCharacters)
    if ($null -eq $Value) { return '' }
    if ($Value.Length -le $MaximumCharacters) { return $Value }
    $head = [int][Math]::Floor($MaximumCharacters / 3)
    $tail = $MaximumCharacters - $head
    return ($Value.Substring(0, $head) + "`n<retained text truncated; original characters=" + $Value.Length + ">`n" + $Value.Substring($Value.Length - $tail, $tail))
}

function Drain-DriverStreams {
    param([int]$WaitCutoff, [bool]$RequireNoExtraOutput)
    if ($script:DriverStreamsDrained) { return }
    if ($null -eq $script:Driver) { return }
    $streamFailure = $null
    $extraStdout = $false
    if ($script:StdoutReadPending -and $null -ne $script:StdoutTask) {
        $remaining = [int][Math]::Floor($WaitCutoff - $script:Clock.ElapsedMilliseconds)
        try {
            if ($remaining -le 0 -or -not $script:StdoutTask.Wait($remaining)) { throw 'pending stdout protocol read did not finish within the evidence reserve' }
            $lateLine = $script:StdoutTask.GetAwaiter().GetResult()
            $script:StdoutReadPending = $false
            if ($null -ne $lateLine) {
                if (-not (Test-ProtocolLineWithinLimit $lateLine)) { [void]$script:ProtocolLines.Add((Limit-RetainedText $lateLine 65536)); throw 'late stdout protocol line exceeded the bounded 262144-byte protocol-line limit' }
                [void]$script:ProtocolLines.Add($lateLine)
                try {
                    $lateRecord = Read-JsonLine $lateLine 'late stdout line'
                    if ($lateRecord.kind -ceq 'READY' -and $null -eq $script:ReadyRecord) { $script:ReadyRecord = $lateRecord }
                    if ($lateRecord.kind -ceq 'TERMINAL' -and $null -eq $script:TerminalRecord) { $script:TerminalRecord = $lateRecord }
                } catch { $streamFailure = 'late stdout line could not be parsed: ' + $_.Exception.Message }
            }
        } catch {
            $script:StdoutReadPending = $false
            if ($null -eq $streamFailure) { $streamFailure = $_.Exception.Message }
        }
    }
    $tailText = ''
    try {
        $remaining = [int][Math]::Floor($WaitCutoff - $script:Clock.ElapsedMilliseconds)
        if ($remaining -le 0) { throw 'no deadline remained to drain stdout after direct process wait' }
        $tailTask = $script:Driver.StandardOutput.ReadToEndAsync()
        if (-not $tailTask.Wait($remaining)) { throw 'stdout drain exceeded the direct process wait boundary' }
        $tailText = $tailTask.GetAwaiter().GetResult()
        $script:StdoutTail = Limit-RetainedText $tailText 16384
        $extraStdout = ($tailText.Length -gt 0)
    } catch {
        if ($null -eq $streamFailure) { $streamFailure = 'stdout drain failed: ' + $_.Exception.Message }
    }
    try {
        $remaining = [int][Math]::Floor($WaitCutoff - $script:Clock.ElapsedMilliseconds)
        if ($null -ne $script:StderrTask) {
            if ($remaining -le 0 -or -not $script:StderrTask.Wait($remaining)) { throw 'stderr drain exceeded the direct process wait boundary' }
            $script:StderrText = Limit-RetainedText ($script:StderrTask.GetAwaiter().GetResult()) 16384
        }
    } catch {
        if ($null -eq $streamFailure) { $streamFailure = 'stderr drain failed: ' + $_.Exception.Message }
    }
    try { $script:Driver.StandardOutput.Dispose() } catch { }
    try { $script:Driver.StandardError.Dispose() } catch { }
    $script:DriverStreamsDrained = $true
    if ($null -ne $streamFailure) { throw $streamFailure }
    if ($RequireNoExtraOutput -and $extraStdout) { throw 'supervisor emitted unexpected stdout after TERMINAL' }
}

function Confirm-DirectDriverExit {
    $phaseLimit = [int]$script:PhaseLimits[$Phase]
    $waitCutoff = $phaseLimit - $script:EvidenceReserveMs
    $remaining = [int][Math]::Floor($waitCutoff - $script:Clock.ElapsedMilliseconds)
    if ($remaining -le 0) { throw 'no host deadline budget remains for the direct WSL process wait' }
    if (-not $script:Driver.WaitForExit($remaining)) { throw 'direct wsl.exe wait was not confirmed before the evidence reserve' }
    $script:DriverExitConfirmed = $true
    $script:DriverExitCode = $script:Driver.ExitCode
    if (-not (Test-ExactInteger $script:DriverExitCode)) { throw 'direct wsl.exe exit code is not an integer' }
    Drain-DriverStreams $waitCutoff ($script:DriverExitCode -eq 0)
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
        $script:HostClaim = [pscustomobject]@{ exclusive = $true; collision_preserved = [bool]$collisionPreserved; launch_allowlist = $script:LaunchAllowlist }
        if (-not (Test-HostClaim $script:HostClaim)) { throw 'host launch claim does not match fixed allowlist contract' }
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
        $finalReason = $null
        $elapsedForAdmission = [int]$script:Clock.ElapsedMilliseconds
        $finalContext = [pscustomobject]@{ phase = $Phase; host_case = if (@($script:HostCases).Count -gt 0) { $script:HostCases[0] } else { $null } }
        if (-not (Test-FinalAdmission $script:TerminalRecord $finalContext $script:DriverExitConfirmed $script:DriverExitCode $true $true $elapsedForAdmission ([int]$script:PhaseLimits[$Phase]) ([ref]$finalReason))) { throw ('host-only final admission failed: ' + $finalReason) }
        $success = $true
    } catch {
        $caughtMessage = $_.Exception.Message
        $caughtDetail = $_.Exception.ToString()
        if ($null -eq $script:TransportFailureCategory) { $script:TransportFailureCategory = 'HOST_OR_OBSERVER_FAILURE' }
        if ($null -eq $script:TransportFailureMessage) { $script:TransportFailureMessage = $caughtMessage }
        if ($null -eq $script:TransportFailureDetail) { $script:TransportFailureDetail = $caughtDetail }
        if ($null -eq $script:FailureCategory) { $script:FailureCategory = $script:TransportFailureCategory }
        if ($null -eq $script:FailureMessage) { $script:FailureMessage = $script:TransportFailureMessage }
        if ($null -eq $script:FailureDetail) { $script:FailureDetail = $script:TransportFailureDetail }
        if ($null -ne $script:Driver -and $script:DriverStarted) {
            try { $script:Driver.StandardInput.Close() } catch { }
            $waitRemaining = [int][Math]::Floor([int]$script:PhaseLimits[$Phase] - $script:EvidenceReserveMs - $script:Clock.ElapsedMilliseconds)
            try {
                $waitForMs = [int][Math]::Max(0, $waitRemaining)
                if ($script:Driver.WaitForExit($waitForMs)) {
                    $script:DriverExitConfirmed = $true
                    $script:DriverExitCode = $script:Driver.ExitCode
                    try { Drain-DriverStreams ([int]$script:PhaseLimits[$Phase] - $script:EvidenceReserveMs) $false }
                    catch {
                        if ($null -eq $script:TransportFailureDetail) { $script:TransportFailureDetail = 'stream cleanup: ' + $_.Exception.Message }
                    }
                } else {
                    $waitFailure = 'direct wsl.exe WaitForExit was not confirmed before the evidence reserve'
                    if ($null -eq $script:TransportFailureDetail) { $script:TransportFailureDetail = $waitFailure }
                    Retain-UnresolvedDriverCleanup $waitFailure
                }
            } catch {
                $waitFailure = 'direct wsl.exe wait failed: ' + $_.Exception.Message
                if ($null -eq $script:TransportFailureDetail) { $script:TransportFailureDetail = $waitFailure }
                Retain-UnresolvedDriverCleanup $waitFailure
            }
        }
        if ($null -ne $script:Freeze -and $null -ne $script:Execution) {
            try { $script:HostAfter = Get-HostPreservationSnapshot $script:Freeze $script:Execution $script:ManifestSha256 } catch { $script:PreservationError = $_.Exception.Message }
        }
        Set-BoundSupervisorFailureClassification
        $success = $false
    }
    if (-not $script:ClaimCreated) {
        [System.Console]::Error.WriteLine([string]$script:FailureMessage)
        return [bool]$false
    }
    if ($success -and $script:Clock.ElapsedMilliseconds -ge ([int]$script:PhaseLimits[$Phase] - $script:EvidenceReserveMs)) {
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
    if ($script:Clock.ElapsedMilliseconds -gt [int]$script:PhaseLimits[$Phase]) {
        $success = $false
        $script:FailureCategory = 'PHASE_OVERRUN_AFTER_EVIDENCE'
        $script:FailureMessage = 'durable evidence completed after the entire-phase deadline'
        try { Write-JsonCreateNew $script:OverrunPath ([pscustomobject]@{ phase = $Phase; nonce = $nonce; elapsed_ms = [long]$script:Clock.ElapsedMilliseconds; maximum_ms = [int]$script:PhaseLimits[$Phase]; failure_category = $script:FailureCategory; failure_message = $script:FailureMessage; receipt_path = $script:ReceiptPath }) } catch { }
    }
    if ($success) {
        [System.Console]::Error.WriteLine('SRO_PHASE_PASS ' + $Phase + ' ' + $nonce)
        return [bool]$true
    }
    [System.Console]::Error.WriteLine('SRO_PHASE_FAIL ' + $Phase + ' ' + $script:FailureCategory + ' ' + $script:FailureMessage)
    return [bool]$false
}

if (-not (Invoke-Phase)) { exit 1 }
exit 0
