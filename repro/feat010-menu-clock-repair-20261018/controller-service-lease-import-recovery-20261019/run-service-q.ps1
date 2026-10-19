param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('baseline', 'candidate')]
    [string]$Phase
)

$phaseClock = [System.Diagnostics.Stopwatch]::StartNew()
$ErrorActionPreference = 'Stop'
$script:PhaseLimitMs = 60000
$script:HostFinalizeReserveMs = 6000
$script:GoReserveMs = 7000
$script:TerminalStopAtMs = $script:PhaseLimitMs - $script:HostFinalizeReserveMs
$script:Driver = $null
$script:DriverStarted = $false
$script:PendingStdout = $null
$script:EvidenceDirectory = Join-Path $PSScriptRoot 'evidence'
$script:ProtocolLines = New-Object System.Collections.ArrayList
$script:PhaseNonce = [Guid]::NewGuid().ToString('N').ToLowerInvariant()
$script:FailureCategory = $null
$script:FailureMessage = $null
$script:FailureDetail = $null
$script:FinalStatus = 'FAIL'
$script:Terminal = $null
$script:Ready = $null
$script:WorkerAck = $null
$script:ManifestSha256 = $null
$script:SourceSha256 = [ordered]@{}
$script:TicketSha256 = $null
$script:PreservationStart = $null
$script:PreservationEnd = $null
$script:PreservationError = $null
$script:InstalledSourceSha256 = [ordered]@{}
$script:FreezePath = $null
$script:TicketPath = $null
$script:Freeze = $null
$script:BaselineEvidenceSha256 = $null
$script:ClaimPath = Join-Path $script:EvidenceDirectory ('service-q-' + $Phase + '.claim')
$script:EvidencePath = Join-Path $script:EvidenceDirectory ('service-q-' + $Phase + '.json')
$script:ClaimCreated = $false
$script:O01 = $null
$script:O02 = $null
$script:O03 = $null
$script:BaselinePrecondition = 'NOT_REQUIRED'
$script:WslStdout = New-Object System.Collections.ArrayList
$script:WslStderr = ''
$script:DriverExitCode = $null
$script:DriverExitConfirmed = $false
$script:remainingMs = 0
$stderrTask = $null
$script:WorkerCleanupStatus = 'NOT_STARTED'
$script:ExpectedInputPaths = @(
    'baseline/gdb.py.txt',
    'baseline/server.py.txt',
    'candidate/gdb.py',
    'candidate/server.py',
    'service-q.py',
    'run-service-q.ps1'
)
$script:BaselineCases = @(
    [pscustomobject]@{ case_id = 'B01'; status = 'PASS' },
    [pscustomobject]@{ case_id = 'B02'; status = 'BASELINE_DEFECT_DETECTED' },
    [pscustomobject]@{ case_id = 'B03'; status = 'BASELINE_DEFECT_DETECTED' },
    [pscustomobject]@{ case_id = 'B04'; status = 'BASELINE_DEFECT_DETECTED' }
)
$script:CandidateCases = @(
    'C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08',
    'C09', 'C10', 'C11', 'C12', 'C13', 'C14', 'C15', 'C16'
)

function Get-PropertyNames {
    param([object]$Value)
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [System.Array]) {
        return @()
    }
    return @($Value.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object)
}

function Test-ObjectShape {
    param([object]$Value, [string[]]$Names)
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [System.Array]) {
        return $false
    }
    $actual = @(Get-PropertyNames $Value)
    $expected = @($Names | Sort-Object)
    if ($actual.Count -ne $expected.Count) { return $false }
    for ($index = 0; $index -lt $expected.Count; $index++) {
        if ($actual[$index] -cne $expected[$index]) { return $false }
    }
    return $true
}

function Test-HasProperties {
    param([object]$Value, [string[]]$Names)
    if ($null -eq $Value -or $Value -is [string] -or $Value -is [System.Array]) { return $false }
    foreach ($name in $Names) {
        if ($null -eq $Value.PSObject.Properties[$name]) { return $false }
    }
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
    if ($null -eq $Actual -or $Actual -is [string] -or $Actual -is [System.Array]) { return $false }
    if ($Expected -is [System.Collections.IDictionary]) {
        $expectedNames = @($Expected.Keys | Sort-Object)
    } else {
        $expectedNames = @(Get-PropertyNames $Expected)
    }
    $actualNames = @(Get-PropertyNames $Actual)
    if ($expectedNames.Count -ne $actualNames.Count) { return $false }
    for ($index = 0; $index -lt $expectedNames.Count; $index++) {
        $name = $expectedNames[$index]
        if ($actualNames[$index] -cne $name) { return $false }
        $property = $Actual.PSObject.Properties[$name]
        if ($Expected -is [System.Collections.IDictionary]) { $expectedValue = $Expected[$name] }
        else { $expectedValue = $Expected.PSObject.Properties[$name].Value }
        if ($null -eq $property -or $property.Value -isnot [string] -or $property.Value -cne $expectedValue) { return $false }
    }
    return $true
}

function Get-HostPreservationSnapshot {
    param([object]$FreezeObject)
    $sources = [ordered]@{}
    foreach ($relativePath in $script:ExpectedInputPaths) {
        $path = Join-Path $PSScriptRoot ($relativePath -replace '/', '\')
        if (-not [System.IO.File]::Exists($path)) { throw ('preservation source is missing: ' + $relativePath) }
        $digest = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($digest -cne $script:SourceSha256[$relativePath]) { throw ('preservation source changed: ' + $relativePath) }
        $sources[$relativePath] = $digest
    }
    $manifest = (Get-FileHash -LiteralPath $script:FreezePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($manifest -cne $script:ManifestSha256) { throw 'preservation manifest changed' }
    $ticket = (Get-FileHash -LiteralPath $script:TicketPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ticket -cne $script:TicketSha256) { throw 'preservation canonical ticket changed' }
    $protectedExpected = $FreezeObject.protected_files_sha256
    $protectedNames = @(Get-PropertyNames $protectedExpected)
    if ($protectedNames.Count -ne 153) { throw 'freeze protected_files_sha256 is not the fixed 153-file set' }
    $protected = [ordered]@{}
    foreach ($absolutePath in $protectedNames) {
        $expected = [string]$protectedExpected.PSObject.Properties[$absolutePath].Value
        if (-not (Test-Sha256 $expected) -or -not [System.IO.File]::Exists($absolutePath)) { throw ('protected file is missing or has invalid pin: ' + $absolutePath) }
        $actual = (Get-FileHash -LiteralPath $absolutePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -cne $expected) { throw ('protected file differs from parent freeze: ' + $absolutePath) }
        $protected[$absolutePath] = $actual
    }
    return [pscustomobject]@{
        sources = [pscustomobject]$sources
        manifest_sha256 = $manifest
        ticket_sha256 = $ticket
        protected_files_sha256 = [pscustomobject]$protected
    }
}

function Test-PreservationEqual {
    param([object]$Left, [object]$Right)
    if (-not (Test-ObjectShape $Left @('sources', 'manifest_sha256', 'ticket_sha256', 'protected_files_sha256')) -or -not (Test-ObjectShape $Right @('sources', 'manifest_sha256', 'ticket_sha256', 'protected_files_sha256'))) { return $false }
    return ($Left.manifest_sha256 -ceq $Right.manifest_sha256 -and $Left.ticket_sha256 -ceq $Right.ticket_sha256 -and (Test-HashObject $Left.sources $Right.sources) -and (Test-HashObject $Left.protected_files_sha256 $Right.protected_files_sha256))
}

function Test-ExactIntegerMap {
    param([object]$Actual, [System.Collections.IDictionary]$Expected)
    if ($null -eq $Actual -or $Actual -is [string] -or $Actual -is [System.Array]) { return $false }
    $expectedNames = @($Expected.Keys | Sort-Object)
    $actualNames = @(Get-PropertyNames $Actual)
    if ($actualNames.Count -ne $expectedNames.Count) { return $false }
    for ($index = 0; $index -lt $expectedNames.Count; $index++) {
        $name = $expectedNames[$index]
        if ($actualNames[$index] -cne $name) { return $false }
        $actualValue = $Actual.PSObject.Properties[$name].Value
        if (-not (Test-ExactInteger $actualValue) -or $actualValue -ne $Expected[$name]) { return $false }
    }
    return $true
}

function Test-Identity {
    param([object]$Identity)
    if (-not (Test-ObjectShape $Identity @('pid', 'start_ticks', 'executable', 'executable_sha256'))) { return $false }
    if (-not (Test-ExactInteger $Identity.pid) -or $Identity.pid -le 0) { return $false }
    if (-not (Test-ExactInteger $Identity.start_ticks) -or $Identity.start_ticks -le 0) { return $false }
    if ($Identity.executable -cne '/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12') { return $false }
    return ($Identity.executable_sha256 -ceq '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900')
}

function Test-IdentityEqual {
    param([object]$Left, [object]$Right)
    if (Test-Identity $Left) { $leftIdentity = $Left }
    else {
        if (-not (Test-ObjectShape $Left @('pid', 'start_ticks', 'executable', 'executable_sha256', 'wait_confirmed', 'returncode')) -or -not (Test-ExactBoolean $Left.wait_confirmed) -or $Left.wait_confirmed -ne $true -or -not (Test-ExactInteger $Left.returncode)) { return $false }
        $leftIdentity = $Left
    }
    if (Test-Identity $Right) { $rightIdentity = $Right }
    else {
        if (-not (Test-ObjectShape $Right @('pid', 'start_ticks', 'executable', 'executable_sha256', 'wait_confirmed', 'returncode')) -or -not (Test-ExactBoolean $Right.wait_confirmed) -or $Right.wait_confirmed -ne $true -or -not (Test-ExactInteger $Right.returncode)) { return $false }
        $rightIdentity = $Right
    }
    if ($leftIdentity.executable -cne '/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12' -or $leftIdentity.executable_sha256 -cne '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900') { return $false }
    if ($rightIdentity.executable -cne '/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12' -or $rightIdentity.executable_sha256 -cne '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900') { return $false }
    return ($leftIdentity.pid -eq $rightIdentity.pid -and $leftIdentity.start_ticks -eq $rightIdentity.start_ticks -and $leftIdentity.executable -ceq $rightIdentity.executable -and $leftIdentity.executable_sha256 -ceq $rightIdentity.executable_sha256)
}

function Test-AdmissionEnvelope {
    param(
        [object]$Record,
        [string]$ExpectedPhase,
        [string]$ExpectedNonce,
        [string]$ExpectedManifest,
        [System.Collections.IDictionary]$ExpectedSources,
        [string]$ExpectedTicket,
        [System.Collections.IDictionary]$ExpectedInstalled,
        [long]$MaximumPhaseMs
    )
    $terminalFields = @('kind', 'phase', 'nonce', 'manifest_sha256', 'source_sha256', 'ticket_sha256', 'status', 'o03', 'worker', 'worker_ack', 'supervisor', 'ready_supervisor_elapsed_ms', 'supervisor_elapsed_ms', 'phase_elapsed_ms', 'installed_source_sha256', 'post_hashes', 'preservation_failure')
    if (-not (Test-ObjectShape $Record $terminalFields)) { return $false }
    if ($Record.kind -cne 'TERMINAL' -or $Record.phase -cne $ExpectedPhase -or $Record.nonce -cne $ExpectedNonce) { return $false }
    if ($Record.manifest_sha256 -cne $ExpectedManifest -or $Record.ticket_sha256 -cne $ExpectedTicket) { return $false }
    if (-not (Test-HashObject $Record.source_sha256 $ExpectedSources)) { return $false }
    if (-not (Test-Identity $Record.supervisor)) { return $false }
    if (-not (Test-ExactInteger $Record.ready_supervisor_elapsed_ms) -or $Record.ready_supervisor_elapsed_ms -lt 0 -or $Record.ready_supervisor_elapsed_ms -gt $MaximumPhaseMs) { return $false }
    if (-not (Test-ExactInteger $Record.supervisor_elapsed_ms) -or $Record.supervisor_elapsed_ms -lt $Record.ready_supervisor_elapsed_ms -or $Record.supervisor_elapsed_ms -gt $MaximumPhaseMs) { return $false }
    if (-not (Test-ExactInteger $Record.phase_elapsed_ms) -or $Record.phase_elapsed_ms -lt 0 -or $Record.phase_elapsed_ms -gt $MaximumPhaseMs -or $Record.phase_elapsed_ms -gt $Record.supervisor_elapsed_ms) { return $false }
    if (-not (Test-HashObject $Record.installed_source_sha256 $ExpectedInstalled)) { return $false }
    if ($null -ne $Record.preservation_failure) { return $false }
    if (-not (Test-ObjectShape $Record.post_hashes @('source_sha256', 'ticket_sha256', 'manifest_sha256', 'installed_source_sha256', 'interpreter_sha256'))) { return $false }
    if (-not (Test-HashObject $Record.post_hashes.source_sha256 $ExpectedSources)) { return $false }
    if ($Record.post_hashes.ticket_sha256 -cne $ExpectedTicket -or $Record.post_hashes.manifest_sha256 -cne $ExpectedManifest -or $Record.post_hashes.interpreter_sha256 -cne '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900') { return $false }
    if (-not (Test-HashObject $Record.post_hashes.installed_source_sha256 $ExpectedInstalled)) { return $false }
    if (-not (Test-ObjectShape $Record.worker_ack @('pid', 'start_ticks', 'executable', 'executable_sha256', 'wait_confirmed', 'returncode'))) { return $false }
    if (-not (Test-ExactInteger $Record.worker_ack.pid) -or $Record.worker_ack.pid -le 0) { return $false }
    if (-not (Test-ExactInteger $Record.worker_ack.start_ticks) -or $Record.worker_ack.start_ticks -le 0) { return $false }
    if ($Record.worker_ack.executable -cne '/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12') { return $false }
    if ($Record.worker_ack.executable_sha256 -cne '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900') { return $false }
    if (-not (Test-ExactBoolean $Record.worker_ack.wait_confirmed) -or $Record.worker_ack.wait_confirmed -ne $true) { return $false }
    if (-not (Test-ExactInteger $Record.worker_ack.returncode)) { return $false }
    if (-not (Test-ObjectShape $Record.worker @('status', 'identity', 'wait_confirmed', 'returncode', 'outcome', 'stderr', 'stdout'))) { return $false }
    if ($Record.worker.status -cne 'PASS' -or -not (Test-Identity $Record.worker.identity)) { return $false }
    if (-not (Test-IdentityEqual $Record.worker.identity $Record.worker_ack)) { return $false }
    if (-not (Test-ExactBoolean $Record.worker.wait_confirmed) -or $Record.worker.wait_confirmed -ne $true) { return $false }
    if (-not (Test-ExactInteger $Record.worker.returncode) -or $Record.worker.returncode -ne $Record.worker_ack.returncode) { return $false }
    return $true
}

function Test-CaseSet {
    param([object]$Cases, [string]$ExpectedPhase)
    if ($Cases -isnot [System.Array]) { return $false }
    if ($ExpectedPhase -eq 'baseline') {
        $expected = $script:BaselineCases
    } else {
        $expected = @($script:CandidateCases | ForEach-Object { [pscustomobject]@{ case_id = $_; status = 'PASS' } })
    }
    if ($Cases.Count -ne $expected.Count) { return $false }
    for ($index = 0; $index -lt $expected.Count; $index++) {
        if (-not (Test-ObjectShape $Cases[$index] @('case_id', 'status', 'observations'))) { return $false }
        if ($Cases[$index].case_id -cne $expected[$index].case_id -or $Cases[$index].status -cne $expected[$index].status) { return $false }
        $observation = $Cases[$index].observations
        if (-not (Test-HasProperties $observation @('factory_call_count', 'fake_processes', 'subject_calls'))) { return $false }
        $caseId = [string]$Cases[$index].case_id
        $wantSpawn = if ($caseId -eq 'C04') { 0 } else { 1 }
        if ($ExpectedPhase -eq 'baseline') { $wantSpawn = 1 }
        if (-not (Test-ExactInteger $observation.factory_call_count) -or $observation.factory_call_count -ne $wantSpawn) { return $false }
        if ($observation.fake_processes -isnot [System.Array] -or $observation.fake_processes.Count -ne $wantSpawn) { return $false }
        if ($observation.subject_calls -isnot [System.Array] -or $observation.subject_calls.Count -lt 1) { return $false }
        $booleanFields = @('stopped', 'live_unregistered_process', 'exit_confirmed_by_close', 'lease_registered_before_factory_completion', 'exit_confirmed', 'same_snapshot', 'caller_cancelled', 'session_id_retained', 'formatted_error_seen', 'caller_cancelled_while_factory_pending', 'late_handle_retained', 'fixture_released', 'fixture_release_after_record', 'response_collection_reached', 'command_written', 'tainted', 'later_command_written', 'collection_deadline_exceeded', 'registry_retained_before_fixture_release', 'exit_confirmed_before_fixture_release', 'same_cleanup_task', 'normal_legacy_start_send_stop')
        foreach ($field in $booleanFields) {
            $property = $observation.PSObject.Properties[$field]
            if ($null -ne $property -and -not (Test-ExactBoolean $property.Value)) { return $false }
        }
        $integerFields = @('spawn_count', 'wait_calls', 'session_count', 'invalid_spawn_delta', 'returncode', 'factory_delay_ms', 'banner_stage_delay_ms', 'setup_drain_delay_ms', 'shared_budget_ms', 'lock_delay_ms', 'drain_delay_ms', 'collection_release_ms', 'terminate_calls', 'kill_calls', 'wait_calls_before_fixture_release', 'returncode_before_fixture_release')
        foreach ($field in $integerFields) {
            $property = $observation.PSObject.Properties[$field]
            if ($null -ne $property -and $null -ne $property.Value -and -not (Test-ExactInteger $property.Value)) { return $false }
        }
        $sawEntry = $false
        foreach ($call in $observation.subject_calls) {
            if (-not (Test-ObjectShape $call @('method', 'event')) -and -not (Test-ObjectShape $call @('method', 'event', 'exception_type', 'exception')) -and -not (Test-ObjectShape $call @('method', 'event', 'result_type'))) { return $false }
            if ($call.method -isnot [string] -or $call.method -notmatch '^(GdbManager|GdbSession|server)\.' -or $call.event -notin @('enter', 'return', 'raise')) { return $false }
            if ($call.event -eq 'enter') { $sawEntry = $true }
        }
        if (-not $sawEntry) { return $false }
        $expectedWaits = 1
        $expectedTerm = 0
        $expectedKill = 0
        if ($caseId -in @('B02', 'B04')) { $expectedWaits = 0 }
        if ($caseId -eq 'B03') { $expectedWaits = 2; $expectedTerm = 1; $expectedKill = 1 }
        if ($caseId -in @('C13', 'C14', 'C15', 'C16')) { $expectedTerm = 1; $expectedKill = 1 }
        foreach ($process in $observation.fake_processes) {
            if (-not (Test-ObjectShape $process @('returncode', 'wait_calls', 'terminate_calls', 'kill_calls', 'drain_calls', 'writes', 'events'))) { return $false }
            if (-not (Test-ExactInteger $process.wait_calls) -or $process.wait_calls -ne $expectedWaits -or -not (Test-ExactInteger $process.terminate_calls) -or $process.terminate_calls -ne $expectedTerm -or -not (Test-ExactInteger $process.kill_calls) -or $process.kill_calls -ne $expectedKill -or -not (Test-ExactInteger $process.drain_calls) -or $process.drain_calls -lt 0) { return $false }
            if ($null -ne $process.returncode -and -not (Test-ExactInteger $process.returncode)) { return $false }
            if ($process.writes -isnot [System.Array] -or $process.events -isnot [System.Array]) { return $false }
            if ($caseId -eq 'C14' -and $process.returncode -ne -9) { return $false }
        }
        switch ($caseId) {
            'B01' { if ($observation.stopped -ne $true -or $observation.spawn_count -ne 1 -or $observation.wait_calls -ne 1) { return $false } }
            'B02' { if ($observation.live_unregistered_process -ne $true -or $observation.session_count -ne 0 -or $observation.fake_processes[0].returncode -ne $null) { return $false } }
            'B03' { if ($observation.exit_confirmed_by_close -ne $false -or $observation.wait_calls_before_fixture_release -ne 2 -or $observation.kill_calls -ne 1 -or $observation.fake_processes[0].returncode -ne $null) { return $false } }
            'B04' { if ($observation.registry_count_after_failure -ne 0 -or $observation.fake_processes[0].returncode -ne $null) { return $false } }
            'C01' { if ($observation.invalid_spawn_delta -ne 0 -or $observation.lease_registered_before_factory_completion -ne $true -or $observation.active -cne 'ACTIVE' -or $observation.stopped -cne 'EXITED' -or $observation.exit_confirmed -ne $true -or $observation.returncode -ne 0 -or $observation.returncode_type -cne 'int') { return $false } }
            'C02' { if ($observation.same_snapshot -ne $true -or $observation.state -cne 'EXITED' -or $observation.captured_launch -isnot [System.Array] -or $observation.captured_launch.Count -ne 3 -or $observation.captured_launch[0] -cne 'fixture.bin' -or $observation.captured_launch[1] -isnot [System.Array] -or $observation.captured_launch[1].Count -ne 1 -or $observation.captured_launch[1][0] -cne 'captured-argument' -or $null -ne $observation.captured_launch[2] -or $observation.mutated_caller_args -isnot [System.Array] -or $observation.mutated_caller_args.Count -ne 2 -or $observation.mutated_caller_args[1] -cne 'mutated-after-capture' -or $observation.setup_writes -isnot [System.Array] -or $observation.setup_writes -notcontains 'set args captured-argument') { return $false } }
            'C03' { if ($observation.conflict_state -cne 'OWNER_CONFLICT' -or $observation.spawn_delta -ne 0) { return $false } }
            'C04' { if ($observation.stop_state -cne 'CANCELLED_BEFORE_START' -or $observation.delayed_state -cne 'CANCELLED_BEFORE_START' -or $observation.spawn_count -ne 0) { return $false } }
            'C05' { if ($observation.caller_cancelled -ne $true -or $observation.session_id_retained -ne $true -or $observation.state -cne 'EXITED') { return $false } }
            'C06' { if ($observation.startup_state -cne 'UNRESOLVED' -or $observation.session_id_retained -ne $true -or $observation.stop_state -cne 'EXITED') { return $false } }
            'C07' { if ($observation.formatted_error_seen -ne $true -or $observation.startup_state -cne 'UNRESOLVED' -or $observation.stop_state -cne 'EXITED') { return $false } }
            'C08' { if ($observation.caller_cancelled_while_factory_pending -ne $true -or $observation.pending_state -cne 'UNRESOLVED' -or $observation.late_handle_retained -ne $true -or $observation.final_state -cne 'EXITED' -or $observation.fixture_released -ne $true) { return $false } }
            'C09' { if ($observation.startup_state -cne 'UNRESOLVED' -or $observation.response_collection_reached -ne $false -or $observation.factory_delay_ms -ne 350 -or $observation.banner_stage_delay_ms -ne 350 -or $observation.setup_drain_delay_ms -ne 350 -or $observation.deadline_failure.exception_type -cne 'GdbError' -or $observation.deadline_failure.exception -notmatch '(?i)deadline') { return $false } }
            'C10' { if ($observation.command_written -ne $false) { return $false } }
            'C11' { if ($observation.later_command_written -ne $false -or $observation.tainted -ne $true -or $observation.stop_state -cne 'EXITED') { return $false } }
            'C12' { if ($observation.shared_budget_ms -ne 1000 -or $observation.lock_delay_ms -ne 350 -or $observation.drain_delay_ms -ne 400 -or $observation.collection_release_ms -ne 1100 -or $observation.collection_deadline_exceeded -ne $true -or $observation.tainted -ne $true -or $observation.observed_exception -notmatch '(?i)deadline') { return $false } }
            'C13' { if ($observation.registry_retained_before_fixture_release -ne $true -or $observation.exit_confirmed_before_fixture_release -ne $false -or $null -ne $observation.returncode_before_fixture_release -or $observation.fixture_release_after_record -ne $true) { return $false } }
            'C14' { if ($observation.returncode -ne -9 -or $observation.terminate_calls -ne 1 -or $observation.kill_calls -ne 1 -or $observation.wait_calls -ne 1 -or $observation.repeat_state -cne 'EXITED') { return $false } }
            'C15' { if ($observation.first_state -cne 'UNRESOLVED' -or $observation.second_state -cne 'UNRESOLVED' -or $observation.same_cleanup_task -ne $true -or $observation.kill_calls -ne 1 -or $observation.fixture_released -ne $true) { return $false } }
        }
        if ($caseId -eq 'C16') {
            if ($observation.normal_legacy_start_send_stop -ne $true -or -not (Test-ExactBoolean $observation.normal_legacy_start_send_stop) -or $observation.fixture_release_after_record -ne $true -or -not (Test-ObjectShape $observation.normal_legacy_counts @('spawn_count', 'wait_calls', 'terminate_calls', 'kill_calls'))) { return $false }
            foreach ($field in @('spawn_count', 'wait_calls', 'terminate_calls', 'kill_calls')) { if (-not (Test-ExactInteger $observation.normal_legacy_counts.PSObject.Properties[$field].Value)) { return $false } }
            if ($observation.normal_legacy_counts.spawn_count -ne 1 -or $observation.normal_legacy_counts.wait_calls -ne 1 -or $observation.normal_legacy_counts.terminate_calls -ne 0 -or $observation.normal_legacy_counts.kill_calls -ne 0) { return $false }
        }
    }
    return $true
}

function Test-TerminalRecord {
    param(
        [object]$Record,
        [string]$ExpectedPhase,
        [string]$ExpectedNonce,
        [string]$ExpectedManifest,
        [System.Collections.IDictionary]$ExpectedSources,
        [string]$ExpectedTicket,
        [System.Collections.IDictionary]$ExpectedInstalled,
        [object]$ExpectedSupervisor,
        [long]$MaximumPhaseMs,
        [object]$DriverExitCode,
        [object]$DriverExitConfirmed,
        [ref]$Reason
    )
    $Reason.Value = 'admission envelope mismatch'
    if (-not (Test-AdmissionEnvelope $Record $ExpectedPhase $ExpectedNonce $ExpectedManifest $ExpectedSources $ExpectedTicket $ExpectedInstalled $MaximumPhaseMs)) { return $false }
    if (-not (Test-IdentityEqual $Record.supervisor $ExpectedSupervisor)) { $Reason.Value = 'terminal supervisor identity differs from READY'; return $false }
    if (-not (Test-ExactBoolean $DriverExitConfirmed) -or $DriverExitConfirmed -ne $true -or -not (Test-ExactInteger $DriverExitCode) -or $DriverExitCode -ne 0) { $Reason.Value = 'WSL driver exit was not confirmed'; return $false }
    if ($Record.status -cne 'PASS' -or $Record.worker_ack.returncode -ne 0) {
        $Reason.Value = 'terminal or worker process did not pass'
        return $false
    }
    $outcome = $Record.worker.outcome
    if (-not (Test-ObjectShape $outcome @('kind', 'phase', 'nonce', 'manifest_sha256', 'source_sha256', 'ticket_sha256', 'status', 'cases', 'o04', 'factory_calls', 'denied_unexpected_factory', 'service_subprocess_calls'))) {
        $Reason.Value = 'worker outcome object shape mismatch'
        return $false
    }
    if ($outcome.kind -cne 'RESULT' -or $outcome.phase -cne $ExpectedPhase -or $outcome.nonce -cne $ExpectedNonce -or $outcome.status -cne 'PASS') {
        $Reason.Value = 'worker result phase/nonce/status mismatch'
        return $false
    }
    if ($outcome.manifest_sha256 -cne $ExpectedManifest -or $outcome.ticket_sha256 -cne $ExpectedTicket -or -not (Test-HashObject $outcome.source_sha256 $ExpectedSources)) {
        $Reason.Value = 'worker result source binding mismatch'
        return $false
    }
    if (-not (Test-CaseSet $outcome.cases $ExpectedPhase)) {
        $Reason.Value = 'fixed card set or expected card status mismatch'
        return $false
    }
    $expectedFactoryTotal = if ($ExpectedPhase -eq 'baseline') { 4 } else { 15 }
    if (-not (Test-ExactInteger $outcome.factory_calls) -or $outcome.factory_calls -ne $expectedFactoryTotal -or -not (Test-ExactInteger $outcome.service_subprocess_calls) -or $outcome.service_subprocess_calls -ne $expectedFactoryTotal -or -not (Test-ExactInteger $outcome.denied_unexpected_factory) -or $outcome.denied_unexpected_factory -ne 0) {
        $Reason.Value = 'service process-factory counters are invalid'
        return $false
    }
    if (-not (Test-ObjectShape $outcome.o04 @('status', 'denied_counts', 'real_calls', 'popen_denial_phases', 'popen_denials', 'annotation_controls')) -or $outcome.o04.status -cne 'PASS' -or -not (Test-ExactInteger $outcome.o04.real_calls) -or $outcome.o04.real_calls -ne 0 -or -not (Test-ExactInteger $outcome.o04.popen_denials) -or $outcome.o04.popen_denials -ne 2) {
        $Reason.Value = 'O04 deny-hook result is invalid'
        return $false
    }
    if ($outcome.o04.popen_denial_phases -isnot [System.Array] -or $outcome.o04.popen_denial_phases.Count -ne 2 -or $outcome.o04.popen_denial_phases[0] -cne 'before_import' -or $outcome.o04.popen_denial_phases[1] -cne 'after_import') {
        $Reason.Value = 'O04 Popen denial phases do not bracket actual source import'
        return $false
    }
    if (-not (Test-ObjectShape $outcome.o04.annotation_controls @('safe_class_accepts_bytes', 'installed_class_accepts_bytes', 'broken_function_rejected', 'broken_function_error_type', 'broken_function_error')) -or -not (Test-ExactBoolean $outcome.o04.annotation_controls.safe_class_accepts_bytes) -or $outcome.o04.annotation_controls.safe_class_accepts_bytes -ne $true -or -not (Test-ExactBoolean $outcome.o04.annotation_controls.installed_class_accepts_bytes) -or $outcome.o04.annotation_controls.installed_class_accepts_bytes -ne $true -or -not (Test-ExactBoolean $outcome.o04.annotation_controls.broken_function_rejected) -or $outcome.o04.annotation_controls.broken_function_rejected -ne $true -or $outcome.o04.annotation_controls.broken_function_error_type -cne 'TypeError' -or $outcome.o04.annotation_controls.broken_function_error -cne "'function' object is not subscriptable") {
        $Reason.Value = 'O04 safe generic and broken function annotation controls differ from fixed expectations'
        return $false
    }
    $denyExpected = @{
        'asyncio.create_subprocess_shell' = 1
        'os.system' = 1
        'socket.bind' = 1
        'socket.connect' = 1
        'socket.getaddrinfo' = 1
        'socket.listen' = 1
        'socket.sendmsg' = 1
        'socket.sendto' = 1
        'subprocess.Popen' = 2
        'subprocess.run' = 1
    }
    if (-not (Test-ExactIntegerMap $outcome.o04.denied_counts $denyExpected)) {
        $Reason.Value = 'O04 exact denied-operation counters mismatch'
        return $false
    }
    if ($ExpectedPhase -eq 'baseline') {
        if (-not (Test-ObjectShape $Record.o03 @('status', 'identity', 'cleanup', 'term_ignored', 'phase_elapsed_ms', 'readiness_deadline_ms', 'cleanup_reserve_ms', 'cleanup_elapsed_ms', 'deadline_ms')) -or $Record.o03.status -cne 'PASS' -or -not (Test-ExactBoolean $Record.o03.term_ignored) -or $Record.o03.term_ignored -ne $true -or -not (Test-Identity $Record.o03.identity) -or -not (Test-ExactInteger $Record.o03.phase_elapsed_ms) -or $Record.o03.phase_elapsed_ms -gt 1500 -or $Record.o03.readiness_deadline_ms -ne 500 -or $Record.o03.cleanup_reserve_ms -ne 1000 -or -not (Test-ExactInteger $Record.o03.cleanup_elapsed_ms) -or $Record.o03.cleanup_elapsed_ms -gt 1000 -or $Record.o03.deadline_ms -ne 1500) {
            $Reason.Value = 'O03 identity/readiness result is invalid'
            return $false
        }
        if (-not (Test-ObjectShape $Record.o03.cleanup @('identity', 'wait_confirmed', 'returncode', 'signals')) -or -not (Test-IdentityEqual $Record.o03.cleanup.identity $Record.o03.identity)) {
            $Reason.Value = 'O03 cleanup shape mismatch'
            return $false
        }
        if ($Record.o03.cleanup.wait_confirmed -ne $true -or -not (Test-ExactBoolean $Record.o03.cleanup.wait_confirmed) -or -not (Test-ExactInteger $Record.o03.cleanup.returncode) -or $Record.o03.cleanup.returncode -ne -9 -or $Record.o03.cleanup.signals -isnot [System.Array] -or $Record.o03.cleanup.signals.Count -ne 2 -or $Record.o03.cleanup.signals[0] -cne 'TERM' -or $Record.o03.cleanup.signals[1] -cne 'KILL') {
            $Reason.Value = 'O03 direct wait or exact signal proof mismatch'
            return $false
        }
    } else {
        if (-not (Test-ObjectShape $Record.o03 @('status', 'worker_spawned')) -or $Record.o03.status -cne 'NOT_APPLICABLE' -or -not (Test-ExactBoolean $Record.o03.worker_spawned) -or $Record.o03.worker_spawned -ne $false) {
            $Reason.Value = 'candidate phase has unexpected O03 execution'
            return $false
        }
    }
    $Reason.Value = ''
    return $true
}

function Test-FailedTerminalRecord {
    param(
        [object]$Record,
        [string]$ExpectedPhase,
        [string]$ExpectedNonce,
        [string]$ExpectedManifest,
        [System.Collections.IDictionary]$ExpectedSources,
        [string]$ExpectedTicket,
        [System.Collections.IDictionary]$ExpectedInstalled,
        [object]$ExpectedSupervisor,
        [long]$MaximumPhaseMs,
        [object]$DriverExitCode,
        [object]$DriverExitConfirmed,
        [ref]$Reason
    )
    $Reason.Value = 'failed terminal envelope mismatch'
    $fields = @('kind', 'phase', 'nonce', 'manifest_sha256', 'source_sha256', 'ticket_sha256', 'status', 'o03', 'worker', 'worker_ack', 'supervisor', 'ready_supervisor_elapsed_ms', 'supervisor_elapsed_ms', 'phase_elapsed_ms', 'installed_source_sha256', 'post_hashes', 'preservation_failure')
    if (-not (Test-ObjectShape $Record $fields) -or $Record.kind -cne 'TERMINAL' -or $Record.phase -cne $ExpectedPhase -or $Record.nonce -cne $ExpectedNonce -or $Record.status -cne 'FAIL') { return $false }
    if ($Record.manifest_sha256 -cne $ExpectedManifest -or $Record.ticket_sha256 -cne $ExpectedTicket -or -not (Test-HashObject $Record.source_sha256 $ExpectedSources) -or -not (Test-IdentityEqual $Record.supervisor $ExpectedSupervisor)) { $Reason.Value = 'failed terminal phase, source, or supervisor binding mismatch'; return $false }
    if (-not (Test-ExactBoolean $DriverExitConfirmed) -or $DriverExitConfirmed -ne $true -or -not (Test-ExactInteger $DriverExitCode) -or $DriverExitCode -ne 1) { $Reason.Value = 'failed worker does not have a confirmed nonzero WSL driver exit'; return $false }
    if (-not (Test-ExactInteger $Record.ready_supervisor_elapsed_ms) -or $Record.ready_supervisor_elapsed_ms -lt 0 -or -not (Test-ExactInteger $Record.supervisor_elapsed_ms) -or $Record.supervisor_elapsed_ms -lt $Record.ready_supervisor_elapsed_ms -or $Record.supervisor_elapsed_ms -gt $MaximumPhaseMs -or -not (Test-ExactInteger $Record.phase_elapsed_ms) -or $Record.phase_elapsed_ms -lt 0 -or $Record.phase_elapsed_ms -gt $Record.supervisor_elapsed_ms) { $Reason.Value = 'failed terminal clock values are invalid'; return $false }
    if ($null -ne $Record.preservation_failure -or -not (Test-HashObject $Record.installed_source_sha256 $ExpectedInstalled) -or -not (Test-ObjectShape $Record.post_hashes @('source_sha256', 'ticket_sha256', 'manifest_sha256', 'installed_source_sha256', 'interpreter_sha256')) -or -not (Test-HashObject $Record.post_hashes.source_sha256 $ExpectedSources) -or $Record.post_hashes.ticket_sha256 -cne $ExpectedTicket -or $Record.post_hashes.manifest_sha256 -cne $ExpectedManifest -or -not (Test-HashObject $Record.post_hashes.installed_source_sha256 $ExpectedInstalled) -or $Record.post_hashes.interpreter_sha256 -cne '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900') { $Reason.Value = 'failed terminal source preservation proof is invalid'; return $false }
    $worker = $Record.worker
    $ackFields = @('pid', 'start_ticks', 'executable', 'executable_sha256', 'wait_confirmed', 'returncode')
    $workerIsStandard = Test-ObjectShape $worker @('status', 'identity', 'wait_confirmed', 'returncode', 'outcome', 'stderr', 'stdout')
    $workerIsSupervisorFailure = Test-ObjectShape $worker @('status', 'identity', 'cleanup', 'wait_confirmed', 'returncode', 'error', 'outcome', 'stdout', 'stderr')
    if (-not $workerIsStandard -and -not $workerIsSupervisorFailure) { $Reason.Value = 'worker failure has an unexpected ownership record shape'; return $false }
    if ($worker.status -cne 'FAIL' -or -not (Test-Identity $worker.identity) -or -not (Test-ExactBoolean $worker.wait_confirmed) -or $worker.wait_confirmed -ne $true -or -not (Test-ExactInteger $worker.returncode) -or $worker.stderr -isnot [string] -or $worker.stdout -isnot [string]) { $Reason.Value = 'worker failure has no direct-child wait proof'; return $false }
    if (-not (Test-ObjectShape $Record.worker_ack $ackFields) -or -not (Test-ExactBoolean $Record.worker_ack.wait_confirmed) -or $Record.worker_ack.wait_confirmed -ne $true -or -not (Test-ExactInteger $Record.worker_ack.returncode) -or $Record.worker_ack.returncode -ne $worker.returncode -or -not (Test-IdentityEqual $worker.identity $Record.worker_ack)) { $Reason.Value = 'worker acknowledgement differs from direct Popen.wait observation'; return $false }
    if ($workerIsSupervisorFailure) {
        if ($worker.error -isnot [string] -or $worker.error.Length -eq 0) { $Reason.Value = 'supervisor-owned worker failure lacks its exact error record'; return $false }
        if ($null -ne $worker.cleanup) {
            $cleanup = $worker.cleanup
            $cleanupFields = @('identity', 'wait_confirmed', 'returncode', 'signals')
            $cleanupFieldsWithError = @('identity', 'wait_confirmed', 'returncode', 'signals', 'error')
            if (-not (Test-ObjectShape $cleanup $cleanupFields) -and -not (Test-ObjectShape $cleanup $cleanupFieldsWithError)) { $Reason.Value = 'supervisor cleanup proof has an unexpected shape'; return $false }
            if (-not (Test-IdentityEqual $worker.identity $cleanup.identity) -or -not (Test-ExactBoolean $cleanup.wait_confirmed) -or $cleanup.wait_confirmed -ne $true -or -not (Test-ExactInteger $cleanup.returncode) -or $cleanup.returncode -ne $worker.returncode -or $cleanup.signals -isnot [System.Array]) { $Reason.Value = 'supervisor cleanup proof differs from confirmed worker exit'; return $false }
        }
    }
    if ($null -ne $worker.outcome) {
        if ($workerIsStandard -and $worker.returncode -ne 1) { $Reason.Value = 'qualification worker result has an invalid failure returncode'; return $false }
        $outcome = $worker.outcome
        if (-not (Test-ObjectShape $outcome @('kind', 'phase', 'status', 'failure_case', 'error_type', 'error', 'traceback', 'observed')) -or $outcome.kind -cne 'RESULT' -or $outcome.phase -cne $ExpectedPhase -or $outcome.status -cne 'FAIL' -or $outcome.failure_case -isnot [string] -or $outcome.error_type -isnot [string] -or $outcome.error -isnot [string] -or $outcome.traceback -isnot [string]) { $Reason.Value = 'worker failure result is malformed or not phase-bound'; return $false }
    } else {
        if (-not $workerIsSupervisorFailure -or $worker.error -isnot [string] -or $worker.error.Length -eq 0) { $Reason.Value = 'supervisor-owned worker failure record is malformed'; return $false }
    }
    if ($ExpectedPhase -eq 'baseline') {
        if (-not (Test-ObjectShape $Record.o03 @('status', 'identity', 'cleanup', 'term_ignored', 'phase_elapsed_ms', 'readiness_deadline_ms', 'cleanup_reserve_ms', 'cleanup_elapsed_ms', 'deadline_ms')) -or $Record.o03.status -cne 'PASS' -or -not (Test-Identity $Record.o03.identity) -or -not (Test-ObjectShape $Record.o03.cleanup @('identity', 'wait_confirmed', 'returncode', 'signals')) -or -not (Test-IdentityEqual $Record.o03.identity $Record.o03.cleanup.identity) -or -not (Test-ExactBoolean $Record.o03.cleanup.wait_confirmed) -or $Record.o03.cleanup.wait_confirmed -ne $true -or -not (Test-ExactInteger $Record.o03.cleanup.returncode) -or $Record.o03.cleanup.returncode -ne -9 -or $Record.o03.cleanup.signals -isnot [System.Array] -or $Record.o03.cleanup.signals.Count -ne 2 -or $Record.o03.cleanup.signals[0] -cne 'TERM' -or $Record.o03.cleanup.signals[1] -cne 'KILL') { $Reason.Value = 'failed baseline terminal lacks completed O03 direct-child cleanup'; return $false }
    } elseif (-not (Test-ObjectShape $Record.o03 @('status', 'worker_spawned')) -or $Record.o03.status -cne 'NOT_APPLICABLE' -or -not (Test-ExactBoolean $Record.o03.worker_spawned) -or $Record.o03.worker_spawned -ne $false) { $Reason.Value = 'failed candidate terminal unexpectedly includes O03'; return $false }
    $Reason.Value = ''
    return $true
}

function Get-FailedTerminalCategory {
    param([object]$Record, [bool]$Validated)
    if ($null -ne $Record -and $null -ne $Record.preservation_failure) { return 'SOURCE_PRESERVATION_FAILURE' }
    if ($null -ne $Record -and $Record.phase -ceq 'baseline' -and $null -ne $Record.o03 -and $Record.o03.status -cne 'PASS') { return 'CLEANUP_FAILURE' }
    if ($null -eq $Record -or $null -eq $Record.worker_ack -or -not (Test-ExactBoolean $Record.worker_ack.wait_confirmed) -or $Record.worker_ack.wait_confirmed -ne $true -or -not (Test-ExactInteger $Record.worker_ack.returncode)) { return 'CLEANUP_FAILURE_UNRESOLVED_OWNERSHIP' }
    if (-not $Validated -or $null -eq $Record.worker -or $Record.worker.status -cne 'FAIL') { return 'OBSERVER_FAILURE_INVALID_FAILURE_RECORD' }
    if ($null -ne $Record.worker.outcome -and $Record.worker.outcome.error_type -ceq 'TimeoutError') { return 'DEADLINE_FAILURE' }
    if ((Get-PropertyNames $Record.worker) -ccontains 'error' -and $Record.worker.error -match '^TimeoutExpired:') { return 'DEADLINE_FAILURE' }
    if ($null -eq $Record.worker.outcome) { return 'OBSERVER_FAILURE_INVALID_FAILURE_RECORD' }
    return Get-WorkerFailureCategory $Record.worker.outcome
}

function Write-NewUtf8File {
    param([string]$Path, [string]$Text)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $bytes = $encoding.GetBytes($Text)
    $stream = New-Object System.IO.FileStream(
        $Path,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        $stream.Dispose()
    }
}

function Write-JsonCreateNew {
    param([string]$Path, [object]$Value)
    $text = ConvertTo-Json -InputObject $Value -Depth 100
    Write-NewUtf8File $Path $text
}

function Write-ProtocolJsonLine {
    param([System.Diagnostics.Process]$Process, [object]$Value)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $bytes = $encoding.GetBytes((ConvertTo-Json -InputObject $Value -Depth 20 -Compress) + "`n")
    $stream = $Process.StandardInput.BaseStream
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
}

function Close-ProtocolInput {
    param([System.Diagnostics.Process]$Process)
    if (-not $script:DriverStarted -or $null -eq $Process) { return }
    try { $Process.StandardInput.Dispose() } catch { }
}

function Get-PinnedArchiveHash {
    param([string]$Path, [object]$FreezeObject)
    $normalized = [System.IO.Path]::GetFullPath($Path).Replace('\', '/')
    $matches = @($FreezeObject.protected_files_sha256.PSObject.Properties | Where-Object { $_.Name.Replace('\', '/') -ieq $normalized })
    if ($matches.Count -ne 1 -or -not (Test-Sha256 $matches[0].Value) -or -not [System.IO.File]::Exists($Path)) { throw ('historical fixture input is not uniquely pinned: ' + $normalized) }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $matches[0].Value) { throw ('historical fixture input differs from the current parent pin: ' + $normalized) }
    return $actual
}

function Get-RetainedSetupContext {
    $oldRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\controller-service-lease-prototype-20261019'))
    $evidencePath = Join-Path $oldRoot 'evidence\service-q-baseline.json'
    $freezePath = Join-Path $oldRoot 'service-q-freeze.json'
    $readyPath = Join-Path $oldRoot 'evidence\service-q-ready.json'
    $claimPath = Join-Path $oldRoot 'evidence\service-q-baseline.claim'
    $frozenTicketPath = Join-Path $oldRoot 'evidence\frozen-ticket.html'
    $evidenceDigest = Get-PinnedArchiveHash $evidencePath $script:Freeze
    $freezeDigest = Get-PinnedArchiveHash $freezePath $script:Freeze
    [void](Get-PinnedArchiveHash $readyPath $script:Freeze)
    [void](Get-PinnedArchiveHash $claimPath $script:Freeze)
    [void](Get-PinnedArchiveHash $frozenTicketPath $script:Freeze)
    $oldFreeze = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($freezePath, (New-Object System.Text.UTF8Encoding($false)))) -ErrorAction Stop
    $oldReady = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($readyPath, (New-Object System.Text.UTF8Encoding($false)))) -ErrorAction Stop
    $oldClaim = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($claimPath, (New-Object System.Text.UTF8Encoding($false)))) -ErrorAction Stop
    $oldEvidence = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($evidencePath, (New-Object System.Text.UTF8Encoding($false)))) -ErrorAction Stop
    $freezeFields = @('schema', 'ticket', 'class', 'approval', 'approval_commit', 'status', 'runtime_ready', 'runtime_attempts_authorized', 'installation_authorized', 'interpreter', 'mcp_package_present_file_observation', 'baseline_sha256', 'protected_files_sha256', 'source_owner', 'allowed_input_files', 'phases', 'source_preparation_gate_execution_authorized', 'execution_freeze', 'capacity_delta_bytes', 'candidate_source_commit', 'candidate_source_sha256', 'qualifier_source_contract', 'qualifier_source_commit')
    if (-not (Test-ObjectShape $oldFreeze $freezeFields) -or $oldFreeze.schema -cne 'ladybug.feat010.service-lease.freeze.v1' -or $oldFreeze.ticket -cne 'FEAT-010' -or $oldFreeze.status -cne 'APPROVED_QUALIFIER_SOURCE_READY' -or -not (Test-ExactBoolean $oldFreeze.source_preparation_gate_execution_authorized) -or $oldFreeze.source_preparation_gate_execution_authorized -ne $true) { throw 'protected historical freeze has an unexpected source contract' }
    if (-not (Test-ExactBoolean $oldFreeze.runtime_ready) -or $oldFreeze.runtime_ready -ne $false -or -not (Test-ExactInteger $oldFreeze.runtime_attempts_authorized) -or $oldFreeze.runtime_attempts_authorized -ne 0 -or -not (Test-ExactBoolean $oldFreeze.installation_authorized) -or $oldFreeze.installation_authorized -ne $false) { throw 'historical freeze includes runtime or installation authorization' }
    if (-not (Test-ObjectShape $oldFreeze.interpreter @('path', 'resolved', 'sha256')) -or $oldFreeze.interpreter.path -cne '/home/rastamafugg/.local/share/uv/tools/gdb-mcp/bin/python' -or $oldFreeze.interpreter.resolved -cne '/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12' -or $oldFreeze.interpreter.sha256 -cne '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900') { throw 'historical freeze interpreter pin changed' }
    if (-not (Test-ObjectShape $oldFreeze.execution_freeze @('authorized', 'source_sha256', 'ticket_sha256')) -or -not (Test-ExactBoolean $oldFreeze.execution_freeze.authorized) -or $oldFreeze.execution_freeze.authorized -ne $true -or -not (Test-Sha256 $oldFreeze.execution_freeze.ticket_sha256)) { throw 'historical execution freeze has an unexpected shape' }
    $oldSourcePaths = @('baseline/gdb.py.txt', 'baseline/server.py.txt', 'candidate/gdb.py', 'candidate/server.py', 'service-q.py', 'run-service-q.ps1')
    if (-not (Test-ObjectShape $oldFreeze.execution_freeze.source_sha256 $oldSourcePaths)) { throw 'historical freeze source map is incomplete' }
    if (-not (Test-ObjectShape $oldReady @('schema', 'qualifier_commit', 'candidate_commit', 'source_review', 'seven_input_sha256', 'ticket_sha256', 'manifest_environment_variable', 'manifest_sha256', 'baseline_ready', 'baseline_attempts', 'candidate_ready', 'candidate_attempts', 'phase_max_ms', 'protected_count', 'runtime_ready', 'runtime_attempts_authorized', 'installation_authorized', 'dispatch'))) { throw 'protected historical READY record has an unexpected shape' }
    if ($oldReady.schema -cne 'ladybug.feat010.service-lease.ready.v1' -or $oldReady.manifest_sha256 -cne $freezeDigest -or $oldReady.ticket_sha256 -cne $oldFreeze.execution_freeze.ticket_sha256 -or $oldReady.manifest_environment_variable -cne 'LADYBUG_FEAT010_SERVICE_Q_MANIFEST_SHA256' -or -not (Test-ExactBoolean $oldReady.baseline_ready) -or $oldReady.baseline_ready -ne $true -or $oldReady.baseline_attempts -ne 1 -or $oldReady.candidate_attempts -ne 1 -or $oldReady.phase_max_ms -ne 60000 -or $oldReady.protected_count -ne 139 -or $oldReady.runtime_ready -ne $false -or $oldReady.runtime_attempts_authorized -ne 0 -or $oldReady.installation_authorized -ne $false) { throw 'protected historical READY metadata differs from the original one-shot offline phase' }
    $sevenInputs = [ordered]@{}
    $oldSources = [ordered]@{}
    foreach ($path in $oldSourcePaths) {
        $digest = [string]$oldFreeze.execution_freeze.source_sha256.PSObject.Properties[$path].Value
        if (-not (Test-Sha256 $digest)) { throw ('historical source hash is malformed: ' + $path) }
        $oldSources[$path] = $digest
        $sevenInputs[$path] = $digest
    }
    $sevenInputs['service-q-freeze.json'] = $freezeDigest
    if (-not (Test-HashObject $oldReady.seven_input_sha256 ([pscustomobject]$sevenInputs))) { throw 'historical READY does not bind all seven original inputs' }
    if (-not (Test-ObjectShape $oldClaim @('phase', 'nonce', 'started_utc', 'purpose')) -or $oldClaim.phase -cne 'baseline' -or $oldClaim.nonce -cnotmatch '^[0-9a-f]{32}$' -or $oldClaim.purpose -cne 'single fixed FEAT-010 service-lease qualifier phase' -or $oldClaim.started_utc -isnot [string]) { throw 'protected historical baseline claim has an unexpected shape' }
    $ticketDigest = (Get-FileHash -LiteralPath $frozenTicketPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ticketDigest -cne $oldFreeze.execution_freeze.ticket_sha256) { throw 'historical frozen ticket differs from its source contract' }
    if (@(Get-PropertyNames $oldFreeze.protected_files_sha256).Count -ne 139) { throw 'historical source freeze did not pin the original 139 protected inputs' }
    if (-not (Test-ObjectShape $oldEvidence.ready @('installed_source_sha256', 'kind', 'manifest_sha256', 'nonce', 'phase', 'source_sha256', 'supervisor', 'supervisor_elapsed_ms', 'ticket_sha256')) -or $oldEvidence.ready.kind -cne 'READY' -or $oldEvidence.ready.phase -cne 'baseline' -or $oldEvidence.ready.nonce -cne $oldClaim.nonce -or $oldEvidence.ready.manifest_sha256 -cne $freezeDigest -or $oldEvidence.ready.ticket_sha256 -cne $oldFreeze.execution_freeze.ticket_sha256 -or -not (Test-Identity $oldEvidence.ready.supervisor) -or -not (Test-HashObject $oldEvidence.ready.source_sha256 ([pscustomobject]$oldSources)) -or -not (Test-ExactInteger $oldEvidence.ready.supervisor_elapsed_ms) -or $oldEvidence.ready.supervisor_elapsed_ms -le 0 -or $oldEvidence.ready.supervisor_elapsed_ms -ge 60000) { throw 'protected historical run READY is not independently bound to the original claim and sources' }
    if ($oldEvidence.protocol_records -isnot [System.Array] -or $oldEvidence.protocol_records.Count -ne 2 -or -not (Test-IdentityEqual $oldEvidence.protocol_records[0].supervisor $oldEvidence.ready.supervisor) -or $oldEvidence.protocol_records[0].kind -cne 'READY' -or $oldEvidence.protocol_records[0].phase -cne 'baseline' -or $oldEvidence.protocol_records[0].nonce -cne $oldClaim.nonce -or $oldEvidence.protocol_records[0].manifest_sha256 -cne $freezeDigest -or $oldEvidence.protocol_records[0].ticket_sha256 -cne $oldFreeze.execution_freeze.ticket_sha256 -or -not (Test-HashObject $oldEvidence.protocol_records[0].source_sha256 ([pscustomobject]$oldSources))) { throw 'protected historical protocol READY differs from the immutable run READY record' }
    return [pscustomobject]@{
        evidence_path = $evidencePath
        evidence_sha256 = $evidenceDigest
        manifest_sha256 = $freezeDigest
        source_sha256 = $oldSources
        ticket_sha256 = [string]$oldFreeze.execution_freeze.ticket_sha256
        nonce = [string]$oldClaim.nonce
        ready = $oldEvidence.ready
        supervisor = $oldEvidence.ready.supervisor
        freeze = $oldFreeze
        sentinel_path = (Join-Path $oldRoot ('evidence\o02-control-baseline-' + $oldClaim.nonce + '.tmp'))
    }
}

function Get-WorkerFailureCategory {
    param([object]$Outcome)
    if ($null -eq $Outcome -or $Outcome -is [string] -or $Outcome -is [System.Array]) { return 'OBSERVER_FAILURE_INVALID_FAILURE_RECORD' }
    if ($Outcome.failure_case -ceq 'SETUP') { return 'SETUP_OR_OBSERVER_FAILURE' }
    if ($Outcome.failure_case -ceq 'O04') { return 'CONTAINMENT_FAILURE' }
    if ($Outcome.error_type -ceq 'TimeoutError') { return 'DEADLINE_FAILURE' }
    if ($Outcome.failure_case -cmatch '^[BC][0-9]{2}$') { return 'PRODUCT_ASSERTION_FAILURE' }
    if ($Outcome.failure_case -ceq 'PHASE' -and $Outcome.error_type -ceq 'QualificationFailure' -and $Outcome.error -ceq 'worker exceeded supervisor relative deadline') { return 'DEADLINE_FAILURE' }
    if ($Outcome.failure_case -ceq 'PHASE' -and $Outcome.error_type -ceq 'QualificationFailure' -and $Outcome.error -ceq 'required fixed card set is incomplete or reordered') { return 'MISSING_COVERAGE' }
    if ($Outcome.failure_case -ceq 'PHASE' -and $Outcome.error_type -ceq 'QualificationFailure' -and $Outcome.error -ceq 'service factory total differs from the exact frozen card spawn count') { return 'CONTAINMENT_FAILURE' }
    if ($Outcome.failure_case -match '(?i)cleanup|reap|ownership') { return 'CLEANUP_FAILURE' }
    return 'OBSERVER_FAILURE_INVALID_FAILURE_RECORD'
}

function Test-RetainedSetupFailureRecord {
    param([object]$Evidence, [object]$Context, [ref]$Reason)
    $Reason.Value = 'historical failure evidence shape mismatch'
    if ($null -eq $Evidence -or $null -eq $Evidence.terminal) { return $false }
    $installed = [ordered]@{ 'gdb.py' = [string]$Context.freeze.baseline_sha256.'baseline/gdb.py.txt'; 'server.py' = [string]$Context.freeze.baseline_sha256.'baseline/server.py.txt' }
    $sharedReason = ''
    if (-not (Test-FailedTerminalRecord $Evidence.terminal 'baseline' $Context.nonce $Context.manifest_sha256 $Context.source_sha256 $Context.ticket_sha256 $installed $Context.supervisor 60000 $Evidence.driver_exit_code $Evidence.driver_exit_confirmed ([ref]$sharedReason))) { $Reason.Value = 'shared live FAIL-envelope validator rejected retained worker evidence: ' + $sharedReason; return $false }
    $outerFields = @('phase', 'nonce', 'manifest_sha256', 'source_sha256', 'ticket_sha256', 'status', 'admitted', 'baseline_precondition', 'baseline_cases', 'candidate_cases', 'o01', 'o02', 'o03', 'ready', 'terminal', 'worker_ack', 'worker_cleanup_status', 'driver_exit_code', 'driver_exit_confirmed', 'driver_is_wsl_only', 'protocol_lines', 'protocol_records', 'stderr', 'failure_category', 'failure_message', 'failure_detail', 'elapsed_ms', 'deadline_ms', 'go_budget_ms', 'attempt', 'baseline_evidence_sha256', 'preservation', 'evidence_write_started_elapsed_ms', 'evidence_written_utc')
    if (-not (Test-ObjectShape $Evidence $outerFields)) { return $false }
    if ($Evidence.phase -cne 'baseline' -or $Evidence.nonce -cne $Context.nonce -or $Evidence.manifest_sha256 -cne $Context.manifest_sha256 -or $Evidence.ticket_sha256 -cne $Context.ticket_sha256 -or -not (Test-HashObject $Evidence.source_sha256 $Context.source_sha256)) { $Reason.Value = 'historical failure phase, claim nonce, or original source binding mismatch'; return $false }
    if ($Evidence.status -cne 'FAIL' -or -not (Test-ExactBoolean $Evidence.admitted) -or $Evidence.admitted -ne $false -or $Evidence.baseline_precondition -cne 'NOT_REQUIRED' -or $Evidence.failure_category -cne 'PRODUCT_ASSERTION_OR_OBSERVER_FAILURE' -or $Evidence.failure_message -cne 'Terminal record rejected: admission envelope mismatch') { $Reason.Value = 'historical record is not the retained original failed admission'; return $false }
    if ($Evidence.worker_cleanup_status -cne 'CONFIRMED' -or -not (Test-ExactBoolean $Evidence.driver_is_wsl_only) -or $Evidence.driver_is_wsl_only -ne $true -or -not (Test-ExactBoolean $Evidence.driver_exit_confirmed) -or $Evidence.driver_exit_confirmed -ne $true -or -not (Test-ExactInteger $Evidence.driver_exit_code) -or $Evidence.driver_exit_code -ne 1) { $Reason.Value = 'historical WSL worker ownership or driver exit proof is absent'; return $false }
    if (-not (Test-ExactInteger $Evidence.deadline_ms) -or $Evidence.deadline_ms -ne 60000 -or -not (Test-ExactInteger $Evidence.attempt) -or $Evidence.attempt -ne 1 -or -not (Test-ExactInteger $Evidence.elapsed_ms) -or $Evidence.elapsed_ms -le 0 -or $Evidence.elapsed_ms -ge 60000 -or -not (Test-ExactInteger $Evidence.go_budget_ms) -or $Evidence.go_budget_ms -le 0 -or $Evidence.go_budget_ms -gt 53000 -or $null -ne $Evidence.baseline_evidence_sha256 -or -not (Test-ExactInteger $Evidence.evidence_write_started_elapsed_ms) -or $Evidence.evidence_write_started_elapsed_ms -le 0 -or $Evidence.evidence_write_started_elapsed_ms -gt $Evidence.elapsed_ms -or $Evidence.evidence_written_utc -isnot [string]) { $Reason.Value = 'historical phase deadline or one-shot evidence fields are invalid'; return $false }
    if (-not (Test-ObjectShape $Evidence.ready @('installed_source_sha256', 'kind', 'manifest_sha256', 'nonce', 'phase', 'source_sha256', 'supervisor', 'supervisor_elapsed_ms', 'ticket_sha256')) -or $Evidence.ready.kind -cne 'READY' -or $Evidence.ready.phase -cne 'baseline' -or $Evidence.ready.nonce -cne $Context.nonce -or $Evidence.ready.manifest_sha256 -cne $Context.manifest_sha256 -or $Evidence.ready.ticket_sha256 -cne $Context.ticket_sha256 -or -not (Test-HashObject $Evidence.ready.source_sha256 $Context.source_sha256) -or -not (Test-Identity $Evidence.ready.supervisor) -or -not (Test-ExactInteger $Evidence.ready.supervisor_elapsed_ms) -or $Evidence.ready.supervisor_elapsed_ms -le 0 -or $Evidence.ready.supervisor_elapsed_ms -ge 60000) { $Reason.Value = 'historical READY record does not bind the protected claim and sources'; return $false }
    if (-not (Test-HashObject $Evidence.ready.installed_source_sha256 ([pscustomobject]$installed))) { $Reason.Value = 'historical READY installed-source hashes differ from archived inputs'; return $false }
    $terminalFields = @('installed_source_sha256', 'kind', 'manifest_sha256', 'nonce', 'o03', 'phase', 'phase_elapsed_ms', 'post_hashes', 'preservation_failure', 'ready_supervisor_elapsed_ms', 'source_sha256', 'status', 'supervisor', 'supervisor_elapsed_ms', 'ticket_sha256', 'worker', 'worker_ack')
    if (-not (Test-ObjectShape $Evidence.terminal $terminalFields) -or $Evidence.terminal.kind -cne 'TERMINAL' -or $Evidence.terminal.phase -cne 'baseline' -or $Evidence.terminal.nonce -cne $Context.nonce -or $Evidence.terminal.manifest_sha256 -cne $Context.manifest_sha256 -or $Evidence.terminal.ticket_sha256 -cne $Context.ticket_sha256 -or -not (Test-HashObject $Evidence.terminal.source_sha256 $Context.source_sha256) -or $Evidence.terminal.status -cne 'FAIL' -or $null -ne $Evidence.terminal.preservation_failure) { $Reason.Value = 'historical TERMINAL record is not the bound failed worker record'; return $false }
    if (-not (Test-IdentityEqual $Evidence.ready.supervisor $Evidence.terminal.supervisor) -or -not (Test-ExactInteger $Evidence.terminal.ready_supervisor_elapsed_ms) -or $Evidence.terminal.ready_supervisor_elapsed_ms -ne $Evidence.ready.supervisor_elapsed_ms -or -not (Test-ExactInteger $Evidence.terminal.supervisor_elapsed_ms) -or $Evidence.terminal.supervisor_elapsed_ms -lt $Evidence.terminal.ready_supervisor_elapsed_ms -or $Evidence.terminal.supervisor_elapsed_ms -ge 60000 -or -not (Test-ExactInteger $Evidence.terminal.phase_elapsed_ms) -or $Evidence.terminal.phase_elapsed_ms -le 0 -or $Evidence.terminal.phase_elapsed_ms -gt $Evidence.terminal.supervisor_elapsed_ms) { $Reason.Value = 'historical TERMINAL supervisor identity or clock binding is invalid'; return $false }
    if (-not (Test-HashObject $Evidence.terminal.installed_source_sha256 ([pscustomobject]$installed)) -or -not (Test-ObjectShape $Evidence.terminal.post_hashes @('source_sha256', 'ticket_sha256', 'manifest_sha256', 'installed_source_sha256', 'interpreter_sha256')) -or -not (Test-HashObject $Evidence.terminal.post_hashes.source_sha256 $Context.source_sha256) -or $Evidence.terminal.post_hashes.ticket_sha256 -cne $Context.ticket_sha256 -or $Evidence.terminal.post_hashes.manifest_sha256 -cne $Context.manifest_sha256 -or -not (Test-HashObject $Evidence.terminal.post_hashes.installed_source_sha256 ([pscustomobject]$installed)) -or $Evidence.terminal.post_hashes.interpreter_sha256 -cne '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900') { $Reason.Value = 'historical post-run source preservation hashes mismatch'; return $false }
    $workerFields = @('status', 'identity', 'wait_confirmed', 'returncode', 'outcome', 'stderr', 'stdout')
    $ackFields = @('pid', 'start_ticks', 'executable', 'executable_sha256', 'wait_confirmed', 'returncode')
    if (-not (Test-ObjectShape $Evidence.terminal.worker $workerFields) -or $Evidence.terminal.worker.status -cne 'FAIL' -or -not (Test-Identity $Evidence.terminal.worker.identity) -or -not (Test-ExactBoolean $Evidence.terminal.worker.wait_confirmed) -or $Evidence.terminal.worker.wait_confirmed -ne $true -or -not (Test-ExactInteger $Evidence.terminal.worker.returncode) -or $Evidence.terminal.worker.returncode -ne 1 -or $Evidence.terminal.worker.stderr -isnot [string] -or $Evidence.terminal.worker.stdout -isnot [string]) { $Reason.Value = 'historical worker record lacks exact direct-child completion evidence'; return $false }
    if (-not (Test-ObjectShape $Evidence.terminal.worker_ack $ackFields) -or -not (Test-ExactBoolean $Evidence.terminal.worker_ack.wait_confirmed) -or $Evidence.terminal.worker_ack.wait_confirmed -ne $true -or -not (Test-ExactInteger $Evidence.terminal.worker_ack.returncode) -or $Evidence.terminal.worker_ack.returncode -ne 1 -or -not (Test-IdentityEqual $Evidence.terminal.worker.identity $Evidence.terminal.worker_ack) -or -not (Test-IdentityEqual $Evidence.terminal.worker_ack $Evidence.worker_ack) -or -not (Test-ExactBoolean $Evidence.worker_ack.wait_confirmed) -or $Evidence.worker_ack.wait_confirmed -ne $true -or -not (Test-ExactInteger $Evidence.worker_ack.returncode) -or $Evidence.worker_ack.returncode -ne 1) { $Reason.Value = 'historical worker identity, Popen.wait returncode, or duplicated acknowledgement mismatch'; return $false }
    $outcomeFields = @('kind', 'phase', 'status', 'failure_case', 'error_type', 'error', 'traceback', 'observed')
    $outcome = $Evidence.terminal.worker.outcome
    if (-not (Test-ObjectShape $outcome $outcomeFields) -or $outcome.kind -cne 'RESULT' -or $outcome.phase -cne 'baseline' -or $outcome.status -cne 'FAIL' -or $outcome.failure_case -cne 'SETUP' -or $outcome.error_type -cne 'TypeError' -or $outcome.error -cne "'function' object is not subscriptable" -or $outcome.traceback -isnot [string] -or $outcome.traceback -notmatch 'mcp\.server\.fastmcp' -or $outcome.traceback -notmatch 'TypeError: ''function'' object is not subscriptable' -or $null -ne $outcome.observed) { $Reason.Value = 'historical worker result is not the independently expected FastMCP import SETUP failure'; return $false }
    if ((Get-WorkerFailureCategory $outcome) -cne 'SETUP_OR_OBSERVER_FAILURE') { $Reason.Value = 'historical SETUP failure classifier differs from the independent expected category'; return $false }
    if ($Evidence.protocol_records -isnot [System.Array] -or $Evidence.protocol_records.Count -ne 2 -or $Evidence.protocol_records[0].kind -cne 'READY' -or $Evidence.protocol_records[1].kind -cne 'TERMINAL' -or $Evidence.protocol_records[0].phase -cne 'baseline' -or $Evidence.protocol_records[1].phase -cne 'baseline' -or $Evidence.protocol_records[0].nonce -cne $Context.nonce -or $Evidence.protocol_records[1].nonce -cne $Context.nonce -or $Evidence.protocol_records[1].status -cne 'FAIL') { $Reason.Value = 'historical READY/TERMINAL protocol ordering or binding is invalid'; return $false }
    if (-not (Test-ObjectShape $Evidence.o01 @('status', 'valid_accepted', 'invalid_cases_rejected')) -or $Evidence.o01.status -cne 'PASS' -or -not (Test-ExactBoolean $Evidence.o01.valid_accepted) -or $Evidence.o01.valid_accepted -ne $true -or $Evidence.o01.invalid_cases_rejected -isnot [System.Array] -or $Evidence.o01.invalid_cases_rejected.Count -ne 12) { $Reason.Value = 'historical O01 observer controls are incomplete'; return $false }
    $expectedO01 = @('missing_nonce', 'false_wait', 'string_true_wait', 'wrong_typed_returncode', 'wrong_phase', 'wrong_source_hash', 'stale_worker_ack', 'wrong_typed_counter', 'missing_case', 'string_true_case_boolean', 'nonzero_driver_exit', 'string_true_driver_confirmation')
    foreach ($name in $expectedO01) { if ($Evidence.o01.invalid_cases_rejected -notcontains $name) { $Reason.Value = 'historical O01 omitted a fixed rejection control'; return $false } }
    if (-not (Test-ObjectShape $Evidence.o02 @('status', 'collision_rejected', 'original_preserved', 'retained_path', 'retained_sha256')) -or $Evidence.o02.status -cne 'PASS' -or -not (Test-ExactBoolean $Evidence.o02.collision_rejected) -or $Evidence.o02.collision_rejected -ne $true -or -not (Test-ExactBoolean $Evidence.o02.original_preserved) -or $Evidence.o02.original_preserved -ne $true -or -not (Test-Sha256 $Evidence.o02.retained_sha256) -or ([System.IO.Path]::GetFullPath($Evidence.o02.retained_path).Replace('\', '/') -ine [System.IO.Path]::GetFullPath($Context.sentinel_path).Replace('\', '/')) -or $Evidence.o02.retained_sha256 -cne (Get-PinnedArchiveHash $Context.sentinel_path $script:Freeze)) { $Reason.Value = 'historical O02 retained collision evidence is invalid'; return $false }
    if (-not (Test-ObjectShape $Evidence.o03 @('status', 'identity', 'cleanup', 'term_ignored', 'phase_elapsed_ms', 'readiness_deadline_ms', 'cleanup_reserve_ms', 'cleanup_elapsed_ms', 'deadline_ms')) -or $Evidence.o03.status -cne 'PASS' -or -not (Test-Identity $Evidence.o03.identity) -or -not (Test-ExactBoolean $Evidence.o03.term_ignored) -or $Evidence.o03.term_ignored -ne $true -or -not (Test-ObjectShape $Evidence.o03.cleanup @('identity', 'wait_confirmed', 'returncode', 'signals')) -or -not (Test-IdentityEqual $Evidence.o03.identity $Evidence.o03.cleanup.identity) -or -not (Test-ExactBoolean $Evidence.o03.cleanup.wait_confirmed) -or $Evidence.o03.cleanup.wait_confirmed -ne $true -or -not (Test-ExactInteger $Evidence.o03.cleanup.returncode) -or $Evidence.o03.cleanup.returncode -ne -9 -or $Evidence.o03.cleanup.signals -isnot [System.Array] -or $Evidence.o03.cleanup.signals.Count -ne 2 -or $Evidence.o03.cleanup.signals[0] -cne 'TERM' -or $Evidence.o03.cleanup.signals[1] -cne 'KILL') { $Reason.Value = 'historical O03 child cleanup and direct wait proof is invalid'; return $false }
    if ($Evidence.terminal.o03.status -cne $Evidence.o03.status -or -not (Test-IdentityEqual $Evidence.terminal.o03.cleanup.identity $Evidence.o03.cleanup.identity) -or $Evidence.terminal.o03.cleanup.returncode -ne $Evidence.o03.cleanup.returncode) { $Reason.Value = 'historical O03 duplicated fields differ from TERMINAL'; return $false }
    if (-not (Test-ObjectShape $Evidence.preservation @('before', 'after', 'baseline_evidence_sha256', 'error')) -or $null -ne $Evidence.preservation.error -or $null -ne $Evidence.preservation.baseline_evidence_sha256 -or -not (Test-PreservationEqual $Evidence.preservation.before $Evidence.preservation.after) -or $Evidence.preservation.before.manifest_sha256 -cne $Context.manifest_sha256 -or $Evidence.preservation.before.ticket_sha256 -cne $Context.ticket_sha256 -or -not (Test-HashObject $Evidence.preservation.before.sources $Context.source_sha256)) { $Reason.Value = 'historical failure did not retain stable source and ticket preservation evidence'; return $false }
    $Reason.Value = ''
    return $true
}

function Test-RetainedSetupFailureControls {
    $context = Get-RetainedSetupContext
    $fixture = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($context.evidence_path, (New-Object System.Text.UTF8Encoding($false)))) -ErrorAction Stop
    $reason = ''
    if (-not (Test-RetainedSetupFailureRecord $fixture $context ([ref]$reason))) { throw ('retained historical SETUP failure rejected: ' + $reason) }
    $expectedCategory = 'SETUP_OR_OBSERVER_FAILURE'
    $observedCategory = Get-WorkerFailureCategory $fixture.terminal.worker.outcome
    if ($observedCategory -cne $expectedCategory) { throw 'retained worker SETUP diagnosis differs from independent expected classification' }
    $installed = [ordered]@{ 'gdb.py' = [string]$context.freeze.baseline_sha256.'baseline/gdb.py.txt'; 'server.py' = [string]$context.freeze.baseline_sha256.'baseline/server.py.txt' }
    $sharedControls = @('missing_worker_ack', 'false_wait', 'string_true_wait', 'wrong_returncode', 'stale_worker_identity', 'driver_unconfirmed', 'wrong_phase', 'wrong_nonce', 'wrong_source_hash', 'terminal_pass', 'missing_error_field', 'wrong_typed_error_field')
    $sharedRejected = New-Object System.Collections.ArrayList
    foreach ($name in $sharedControls) {
        $copy = ConvertFrom-Json (ConvertTo-Json -InputObject $fixture -Depth 30)
        switch ($name) {
            'missing_worker_ack' { $copy.terminal.worker_ack = $null }
            'false_wait' { $copy.terminal.worker_ack.wait_confirmed = $false }
            'string_true_wait' { $copy.terminal.worker_ack.wait_confirmed = 'true' }
            'wrong_returncode' { $copy.terminal.worker_ack.returncode = $true }
            'stale_worker_identity' { $copy.terminal.worker_ack.start_ticks = [long]($copy.terminal.worker_ack.start_ticks + 1) }
            'driver_unconfirmed' { $copy.driver_exit_confirmed = $false }
            'wrong_phase' { $copy.terminal.phase = 'candidate' }
            'wrong_nonce' { $copy.terminal.nonce = 'ffffffffffffffffffffffffffffffff' }
            'wrong_source_hash' { $copy.terminal.source_sha256.'candidate/gdb.py' = '0' * 64 }
            'terminal_pass' { $copy.terminal.status = 'PASS' }
            'missing_error_field' { [void]$copy.terminal.worker.outcome.PSObject.Properties.Remove('error') }
            'wrong_typed_error_field' { $copy.terminal.worker.outcome.error = [long]1 }
        }
        $negativeReason = ''
        $driverExitCode = $copy.driver_exit_code
        $driverExitConfirmed = $copy.driver_exit_confirmed
        $sharedAccepted = Test-FailedTerminalRecord $copy.terminal 'baseline' $context.nonce $context.manifest_sha256 $context.source_sha256 $context.ticket_sha256 $installed $context.supervisor 60000 $driverExitCode $driverExitConfirmed ([ref]$negativeReason)
        if ($sharedAccepted) { throw ('shared live FAIL-envelope validator accepted malformed terminal control: ' + $name) }
        [void]$sharedRejected.Add($name)
    }
    $diagnosisControls = @('wrong_failure_case', 'wrong_error_type', 'wrong_error_text')
    $diagnosisRejected = New-Object System.Collections.ArrayList
    foreach ($name in $diagnosisControls) {
        $copy = ConvertFrom-Json (ConvertTo-Json -InputObject $fixture -Depth 30)
        switch ($name) {
            'wrong_failure_case' { $copy.terminal.worker.outcome.failure_case = 'C01' }
            'wrong_error_type' { $copy.terminal.worker.outcome.error_type = 'ValueError' }
            'wrong_error_text' { $copy.terminal.worker.outcome.error = 'unrelated setup error' }
        }
        $negativeReason = ''
        if (Test-RetainedSetupFailureRecord $copy $context ([ref]$negativeReason)) { throw ('historical SETUP diagnosis control was accepted: ' + $name) }
        [void]$diagnosisRejected.Add($name)
    }
    $script:HistoricalFailureSha256 = $context.evidence_sha256
    $summary = [pscustomobject]@{
        status = 'PASS'
        classification = $expectedCategory
        failure_case = 'SETUP'
        error_type = 'TypeError'
        worker_wait_confirmed = $true
        worker_returncode = [long]1
        driver_exit_confirmed = $true
        driver_exit_code = [long]1
        fixture_sha256 = $context.evidence_sha256
        shared_validator_rejections = @($sharedRejected)
        diagnosis_mismatches_rejected = @($diagnosisRejected)
    }
    if (-not (Test-RetainedSetupControlSummary $summary)) { throw 'retained SETUP fixture summary failed independent output admission' }
    return $summary
}

function Test-RetainedSetupControlSummary {
    param([object]$Summary)
    if (-not (Test-ObjectShape $Summary @('status', 'classification', 'failure_case', 'error_type', 'worker_wait_confirmed', 'worker_returncode', 'driver_exit_confirmed', 'driver_exit_code', 'fixture_sha256', 'shared_validator_rejections', 'diagnosis_mismatches_rejected'))) { return $false }
    if ($Summary.status -cne 'PASS' -or $Summary.classification -cne 'SETUP_OR_OBSERVER_FAILURE' -or $Summary.failure_case -cne 'SETUP' -or $Summary.error_type -cne 'TypeError' -or -not (Test-ExactBoolean $Summary.worker_wait_confirmed) -or $Summary.worker_wait_confirmed -ne $true -or -not (Test-ExactInteger $Summary.worker_returncode) -or $Summary.worker_returncode -ne 1 -or -not (Test-ExactBoolean $Summary.driver_exit_confirmed) -or $Summary.driver_exit_confirmed -ne $true -or -not (Test-ExactInteger $Summary.driver_exit_code) -or $Summary.driver_exit_code -ne 1 -or -not (Test-Sha256 $Summary.fixture_sha256) -or $Summary.fixture_sha256 -cne $script:HistoricalFailureSha256 -or $Summary.shared_validator_rejections -isnot [System.Array] -or $Summary.diagnosis_mismatches_rejected -isnot [System.Array]) { return $false }
    $expectedShared = @('missing_worker_ack', 'false_wait', 'string_true_wait', 'wrong_returncode', 'stale_worker_identity', 'driver_unconfirmed', 'wrong_phase', 'wrong_nonce', 'wrong_source_hash', 'terminal_pass', 'missing_error_field', 'wrong_typed_error_field')
    if ($Summary.shared_validator_rejections.Count -ne $expectedShared.Count) { return $false }
    foreach ($name in $expectedShared) { if ($Summary.shared_validator_rejections -notcontains $name) { return $false } }
    $expectedDiagnosis = @('wrong_failure_case', 'wrong_error_type', 'wrong_error_text')
    if ($Summary.diagnosis_mismatches_rejected.Count -ne $expectedDiagnosis.Count) { return $false }
    foreach ($name in $expectedDiagnosis) { if ($Summary.diagnosis_mismatches_rejected -notcontains $name) { return $false } }
    return $true
}

function Test-O01Controls {
    param([System.Collections.IDictionary]$ExpectedSources, [System.Collections.IDictionary]$ExpectedInstalled, [string]$ExpectedTicket, [long]$MaximumPhaseMs)
    $controlNonce = '0123456789abcdef0123456789abcdef'
    $identity = [pscustomobject]@{
        pid = [long]11
        start_ticks = [long]22
        executable = '/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12'
        executable_sha256 = '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900'
    }
    $workerIdentity = [pscustomobject]@{
        pid = [long]31
        start_ticks = [long]42
        executable = $identity.executable
        executable_sha256 = $identity.executable_sha256
    }
    $ack = [pscustomobject]@{
        pid = [long]31
        start_ticks = [long]42
        executable = $identity.executable
        executable_sha256 = $identity.executable_sha256
        wait_confirmed = $true
        returncode = [long]0
    }
    $cases = New-Object System.Collections.ArrayList
    $sourceCaseList = if ($Phase -eq 'baseline') { @($script:BaselineCases) } else { @($script:CandidateCases | ForEach-Object { [pscustomobject]@{ case_id = $_; status = 'PASS' } }) }
    $factoryTotal = 0
    foreach ($sourceCase in $sourceCaseList) {
        $caseId = [string]$sourceCase.case_id
        $spawn = if ($caseId -eq 'C04') { 0 } else { 1 }
        if ($Phase -eq 'baseline') { $spawn = 1 }
        $waits = 1
        $term = 0
        $kill = 0
        if ($caseId -in @('B02', 'B04')) { $waits = 0 }
        if ($caseId -eq 'B03') { $waits = 2; $term = 1; $kill = 1 }
        if ($caseId -in @('C13', 'C14', 'C15', 'C16')) { $term = 1; $kill = 1 }
        $fakeProcesses = @()
        if ($spawn -eq 1) {
            $fakeReturncode = $null
            if ($caseId -eq 'B01') { $fakeReturncode = [long]0 }
            if ($caseId -eq 'C14') { $fakeReturncode = [long]-9 }
            $fakeProcesses = @([pscustomobject]@{
                returncode = $fakeReturncode
                wait_calls = [long]$waits
                terminate_calls = [long]$term
                kill_calls = [long]$kill
                drain_calls = [long]1
                writes = @('fixture-command')
                events = @('spawned', 'wait')
            })
            $factoryTotal += 1
        }
        $observation = [ordered]@{
            factory_call_count = [long]$spawn
            fake_processes = $fakeProcesses
            subject_calls = @([pscustomobject]@{ method = 'GdbManager.start_owned_session'; event = 'enter' })
        }
        switch ($caseId) {
            'B01' { $observation.stopped = $true; $observation.spawn_count = [long]1; $observation.wait_calls = [long]1 }
            'B02' { $observation.live_unregistered_process = $true; $observation.session_count = [long]0 }
            'B03' { $observation.exit_confirmed_by_close = $false; $observation.wait_calls_before_fixture_release = [long]2; $observation.kill_calls = [long]1 }
            'B04' { $observation.registry_count_after_failure = [long]0 }
            'C01' { $observation.invalid_spawn_delta = [long]0; $observation.lease_registered_before_factory_completion = $true; $observation.active = 'ACTIVE'; $observation.stopped = 'EXITED'; $observation.exit_confirmed = $true; $observation.returncode = [long]0; $observation.returncode_type = 'int' }
            'C02' { $observation.same_snapshot = $true; $observation.state = 'EXITED'; $observation.captured_launch = @('fixture.bin', @('captured-argument'), $null); $observation.mutated_caller_args = @('captured-argument', 'mutated-after-capture'); $observation.setup_writes = @('set args captured-argument') }
            'C03' { $observation.conflict_state = 'OWNER_CONFLICT'; $observation.spawn_delta = [long]0 }
            'C04' { $observation.stop_state = 'CANCELLED_BEFORE_START'; $observation.delayed_state = 'CANCELLED_BEFORE_START'; $observation.spawn_count = [long]0 }
            'C05' { $observation.caller_cancelled = $true; $observation.session_id_retained = $true; $observation.state = 'EXITED' }
            'C06' { $observation.startup_state = 'UNRESOLVED'; $observation.session_id_retained = $true; $observation.stop_state = 'EXITED' }
            'C07' { $observation.formatted_error_seen = $true; $observation.startup_state = 'UNRESOLVED'; $observation.stop_state = 'EXITED' }
            'C08' { $observation.caller_cancelled_while_factory_pending = $true; $observation.pending_state = 'UNRESOLVED'; $observation.late_handle_retained = $true; $observation.final_state = 'EXITED'; $observation.fixture_released = $true }
            'C09' { $observation.startup_state = 'UNRESOLVED'; $observation.response_collection_reached = $false; $observation.factory_delay_ms = [long]350; $observation.banner_stage_delay_ms = [long]350; $observation.setup_drain_delay_ms = [long]350; $observation.deadline_failure = [pscustomobject]@{ method = 'GdbSession._send_until'; event = 'raise'; exception_type = 'GdbError'; exception = 'Command deadline expired' } }
            'C10' { $observation.command_written = $false }
            'C11' { $observation.later_command_written = $false; $observation.tainted = $true; $observation.stop_state = 'EXITED' }
            'C12' { $observation.shared_budget_ms = [long]1000; $observation.lock_delay_ms = [long]350; $observation.drain_delay_ms = [long]400; $observation.collection_release_ms = [long]1100; $observation.collection_deadline_exceeded = $true; $observation.tainted = $true; $observation.observed_exception = 'TimeoutError: command deadline expired' }
            'C13' { $observation.registry_retained_before_fixture_release = $true; $observation.exit_confirmed_before_fixture_release = $false; $observation.returncode_before_fixture_release = $null; $observation.fixture_release_after_record = $true }
            'C14' { $observation.returncode = [long]-9; $observation.terminate_calls = [long]1; $observation.kill_calls = [long]1; $observation.wait_calls = [long]1; $observation.repeat_state = 'EXITED' }
            'C15' { $observation.first_state = 'UNRESOLVED'; $observation.second_state = 'UNRESOLVED'; $observation.same_cleanup_task = $true; $observation.kill_calls = [long]1; $observation.fixture_released = $true }
        }
        if ($caseId -eq 'C16') {
            $observation.normal_legacy_start_send_stop = $true
            $observation.fixture_release_after_record = $true
            $observation.normal_legacy_counts = [pscustomobject]@{ spawn_count = [long]1; wait_calls = [long]1; terminate_calls = [long]0; kill_calls = [long]0 }
        }
        [void]$cases.Add([pscustomobject]@{ case_id = $caseId; status = [string]$sourceCase.status; observations = [pscustomobject]$observation })
    }
    $record = [pscustomobject]@{
        kind = 'TERMINAL'
        phase = $Phase
        nonce = $controlNonce
        manifest_sha256 = 'a' * 64
        source_sha256 = [pscustomobject]$ExpectedSources
        ticket_sha256 = $ExpectedTicket
        status = 'PASS'
        o03 = if ($Phase -eq 'baseline') { [pscustomobject]@{ status = 'PASS'; identity = $identity; cleanup = [pscustomobject]@{ identity = $identity; wait_confirmed = $true; returncode = [long]-9; signals = @('TERM', 'KILL') }; term_ignored = $true; phase_elapsed_ms = [long]750; readiness_deadline_ms = [long]500; cleanup_reserve_ms = [long]1000; cleanup_elapsed_ms = [long]250; deadline_ms = [long]1500 } } else { [pscustomobject]@{ status = 'NOT_APPLICABLE'; worker_spawned = $false } }
        worker_ack = $ack
        worker = [pscustomobject]@{
            status = 'PASS'
            identity = $workerIdentity
            wait_confirmed = $true
            returncode = [long]0
            outcome = [pscustomobject]@{
                kind = 'RESULT'
                phase = $Phase
                nonce = $controlNonce
                manifest_sha256 = 'a' * 64
                source_sha256 = [pscustomobject]$ExpectedSources
                ticket_sha256 = $ExpectedTicket
                status = 'PASS'
                cases = $cases.ToArray()
                    o04 = [pscustomobject]@{
                    status = 'PASS'
                    denied_counts = [pscustomobject]@{
                        'asyncio.create_subprocess_shell' = [long]1
                        'os.system' = [long]1
                        'socket.bind' = [long]1
                        'socket.connect' = [long]1
                        'socket.getaddrinfo' = [long]1
                        'socket.listen' = [long]1
                        'socket.sendmsg' = [long]1
                        'socket.sendto' = [long]1
                        'subprocess.Popen' = [long]2
                        'subprocess.run' = [long]1
                    }
                    real_calls = [long]0
                    popen_denial_phases = @('before_import', 'after_import')
                    popen_denials = [long]2
                    annotation_controls = [pscustomobject]@{
                        safe_class_accepts_bytes = $true
                        installed_class_accepts_bytes = $true
                        broken_function_rejected = $true
                        broken_function_error_type = 'TypeError'
                        broken_function_error = "'function' object is not subscriptable"
                    }
                }
                factory_calls = [long]$factoryTotal
                denied_unexpected_factory = [long]0
                service_subprocess_calls = [long]$factoryTotal
            }
            stderr = ''
            stdout = '{}'
        }
        supervisor = $identity
        ready_supervisor_elapsed_ms = [long]10
        supervisor_elapsed_ms = [long]1000
        phase_elapsed_ms = [long]900
        installed_source_sha256 = [pscustomobject]$ExpectedInstalled
        post_hashes = [pscustomobject]@{
            source_sha256 = [pscustomobject]$ExpectedSources
            ticket_sha256 = $ExpectedTicket
            manifest_sha256 = 'a' * 64
            installed_source_sha256 = [pscustomobject]$ExpectedInstalled
            interpreter_sha256 = '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900'
        }
        preservation_failure = $null
    }
    $manifestControl = 'a' * 64
    $validReason = ''
    $valid = Test-TerminalRecord $record $Phase $controlNonce $manifestControl $ExpectedSources $ExpectedTicket $ExpectedInstalled $identity $MaximumPhaseMs 0 $true ([ref]$validReason)
    if (-not $valid) { throw ('O01 valid full terminal control was rejected: ' + $validReason) }
    $negativeCases = New-Object System.Collections.ArrayList
    [void]$negativeCases.Add([pscustomobject]@{ name = 'missing_nonce'; mutate = { param($x) $x.PSObject.Properties.Remove('nonce') } })
    [void]$negativeCases.Add([pscustomobject]@{ name = 'false_wait'; mutate = { param($x) $x.worker_ack.wait_confirmed = $false } })
    [void]$negativeCases.Add([pscustomobject]@{ name = 'string_true_wait'; mutate = { param($x) $x.worker_ack.wait_confirmed = 'true' } })
    [void]$negativeCases.Add([pscustomobject]@{ name = 'wrong_typed_returncode'; mutate = { param($x) $x.worker_ack.returncode = $true } })
    $oppositePhase = if ($Phase -eq 'baseline') { 'candidate' } else { 'baseline' }
    [void]$negativeCases.Add([pscustomobject]@{ name = 'wrong_phase'; mutate = { param($x) $x.phase = $oppositePhase } })
    [void]$negativeCases.Add([pscustomobject]@{ name = 'wrong_source_hash'; mutate = { param($x) $x.source_sha256.'candidate/gdb.py' = '0' * 64 } })
    [void]$negativeCases.Add([pscustomobject]@{ name = 'stale_worker_ack'; mutate = { param($x) $x.worker_ack.start_ticks = [long]43 } })
    [void]$negativeCases.Add([pscustomobject]@{ name = 'wrong_typed_counter'; mutate = { param($x) $x.worker.outcome.o04.denied_counts.PSObject.Properties['socket.bind'].Value = '1' } })
    [void]$negativeCases.Add([pscustomobject]@{ name = 'missing_case'; mutate = { param($x) $x.worker.outcome.cases = @() } })
    [void]$negativeCases.Add([pscustomobject]@{ name = 'string_true_case_boolean'; mutate = { param($x) if ($Phase -eq 'candidate') { $row = @($x.worker.outcome.cases | Where-Object { $_.case_id -eq 'C01' })[0]; $row.observations.lease_registered_before_factory_completion = 'true' } else { $row = @($x.worker.outcome.cases | Where-Object { $_.case_id -eq 'B01' })[0]; $row.observations.stopped = 'true' } } })
    $rejected = New-Object System.Collections.ArrayList
    foreach ($case in $negativeCases) {
        $copy = ConvertFrom-Json (ConvertTo-Json -InputObject $record -Depth 20)
        & $case.mutate $copy
        $reason = ''
        $accepted = Test-TerminalRecord $copy $Phase $controlNonce $manifestControl $ExpectedSources $ExpectedTicket $ExpectedInstalled $identity $MaximumPhaseMs 0 $true ([ref]$reason)
        if ($accepted) { throw ('O01 invalid admission control was accepted: ' + $case.name) }
        [void]$rejected.Add($case.name)
    }
    $driverReason = ''
    if (Test-TerminalRecord $record $Phase $controlNonce $manifestControl $ExpectedSources $ExpectedTicket $ExpectedInstalled $identity $MaximumPhaseMs 1 $true ([ref]$driverReason)) { throw 'O01 admitted a nonzero WSL driver exit' }
    $typedDriverReason = ''
    if (Test-TerminalRecord $record $Phase $controlNonce $manifestControl $ExpectedSources $ExpectedTicket $ExpectedInstalled $identity $MaximumPhaseMs 0 'true' ([ref]$typedDriverReason)) { throw 'O01 admitted string-true driver confirmation' }
    [void]$rejected.Add('nonzero_driver_exit')
    [void]$rejected.Add('string_true_driver_confirmation')
    $retainedSetupFailure = Test-RetainedSetupFailureControls
    return [pscustomobject]@{ status = 'PASS'; valid_accepted = $true; invalid_cases_rejected = @($rejected); retained_setup_failure = $retainedSetupFailure }
}

function Test-O02ExclusiveClaim {
    param([string]$Nonce)
    $path = Join-Path $script:EvidenceDirectory ('o02-control-' + $Phase + '-' + $Nonce + '.tmp')
    $sentinel = 'O02-COLLISION-ORIGINAL-' + $Nonce
    Write-NewUtf8File $path $sentinel
    $rejected = $false
    try {
        try {
            Write-NewUtf8File $path 'MUST-NOT-REPLACE'
        } catch [System.IO.IOException] {
            $rejected = $true
        }
        $preserved = [System.IO.File]::ReadAllText($path, (New-Object System.Text.UTF8Encoding($false)))
        if (-not $rejected -or $preserved -cne $sentinel) {
            throw 'O02 collision did not reject while preserving original bytes'
        }
        $digest = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        return [pscustomobject]@{ status = 'PASS'; collision_rejected = $true; original_preserved = $true; retained_path = $path; retained_sha256 = $digest }
    } finally {
        # The collision sentinel is evidence and remains in place.
    }
}

function Get-NextProtocolLine {
    param([System.Diagnostics.Process]$Process, [ref]$LineTask, [long]$StopAtMs)
    while (-not $LineTask.Value.IsCompleted) {
        if ($phaseClock.ElapsedMilliseconds -ge $StopAtMs) {
            return [pscustomobject]@{ timed_out = $true; line = $null }
        }
        Start-Sleep -Milliseconds 10
    }
    $line = $null
    try {
        $line = $LineTask.Value.GetAwaiter().GetResult()
    } catch {
        throw ('stdout read failed: ' + $_.Exception.ToString())
    }
    if ($null -ne $line) {
        [void]$script:WslStdout.Add($line)
        try { [void]$script:ProtocolLines.Add((ConvertFrom-Json -InputObject $line -ErrorAction Stop)) } catch { }
        $LineTask.Value = $Process.StandardOutput.ReadLineAsync()
    }
    return [pscustomobject]@{ timed_out = $false; line = $line }
}

function Read-JsonLine {
    param([string]$Line, [string]$Label)
    if ($null -eq $Line) { throw ($Label + ' ended before a protocol record arrived') }
    try {
        return ConvertFrom-Json -InputObject $Line -ErrorAction Stop
    } catch {
        throw ($Label + ' was not one complete JSON object: ' + $_.Exception.Message)
    }
}

function Assert-ReadyRecord {
    param([object]$Record, [object]$Hashes, [string]$ExpectedPhase = $Phase, [string]$ExpectedNonce = $script:PhaseNonce)
    if (-not (Test-ObjectShape $Record @('kind', 'phase', 'nonce', 'manifest_sha256', 'source_sha256', 'ticket_sha256', 'installed_source_sha256', 'supervisor', 'supervisor_elapsed_ms'))) { throw 'READY object shape mismatch' }
    if ($Record.kind -cne 'READY' -or $Record.phase -cne $ExpectedPhase -or $Record.nonce -cne $ExpectedNonce -or $Record.manifest_sha256 -cne $script:ManifestSha256 -or $Record.ticket_sha256 -cne $script:TicketSha256) { throw 'READY phase or nonce binding mismatch' }
    if (-not (Test-HashObject $Record.source_sha256 $Hashes) -or -not (Test-HashObject $Record.installed_source_sha256 $script:InstalledSourceSha256) -or -not (Test-Identity $Record.supervisor) -or -not (Test-ExactInteger $Record.supervisor_elapsed_ms) -or $Record.supervisor_elapsed_ms -lt 0 -or $Record.supervisor_elapsed_ms -gt $script:PhaseLimitMs) { throw 'READY source or supervisor identity mismatch' }
}

function Get-ExpectedCases {
    param([string]$ForPhase)
    if ($ForPhase -eq 'baseline') { return $script:BaselineCases }
    return @($script:CandidateCases | ForEach-Object { [pscustomobject]@{ case_id = $_; status = 'PASS' } })
}

try {
    if (-not [System.IO.Directory]::Exists($script:EvidenceDirectory)) {
        [void][System.IO.Directory]::CreateDirectory($script:EvidenceDirectory)
    }
    $claimObject = [pscustomobject]@{
        phase = $Phase
        nonce = $script:PhaseNonce
        started_utc = [DateTime]::UtcNow.ToString('o')
        purpose = 'single fixed FEAT-010 service-lease qualifier phase'
    }
    Write-JsonCreateNew $script:ClaimPath $claimObject
    $script:ClaimCreated = $true

    $repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
    $freezePath = Join-Path $PSScriptRoot 'service-q-freeze.json'
    $script:FreezePath = $freezePath
    $freezeRaw = [System.IO.File]::ReadAllText($freezePath, (New-Object System.Text.UTF8Encoding($false)))
    $freeze = ConvertFrom-Json -InputObject $freezeRaw -ErrorAction Stop
    $script:Freeze = $freeze
    if (-not (Test-ExactBoolean $freeze.source_preparation_gate_execution_authorized) -or $freeze.source_preparation_gate_execution_authorized -ne $true) { throw 'parent has not authorized gate execution in the freeze' }
    if (-not (Test-ExactBoolean $freeze.runtime_ready) -or $freeze.runtime_ready -ne $false) { throw 'offline qualifier freeze must keep runtime_ready false' }
    if (-not (Test-ExactInteger $freeze.runtime_attempts_authorized) -or $freeze.runtime_attempts_authorized -ne 0) { throw 'offline qualifier freeze must keep runtime_attempts_authorized at zero' }
    if (-not (Test-ExactBoolean $freeze.installation_authorized) -or $freeze.installation_authorized -ne $false) { throw 'freeze must explicitly keep installation unauthorized' }
    if (-not (Test-ObjectShape $freeze.phases.baseline @('source_cases', 'max_ms', 'attempts')) -or $freeze.phases.baseline.source_cases -ne 4 -or $freeze.phases.baseline.max_ms -ne 60000 -or $freeze.phases.baseline.attempts -ne 1) { throw 'baseline phase freeze changed' }
    if (-not (Test-ObjectShape $freeze.phases.candidate @('prerequisite', 'source_cases', 'max_ms', 'attempts')) -or $freeze.phases.candidate.source_cases -ne 16 -or $freeze.phases.candidate.max_ms -ne 60000 -or $freeze.phases.candidate.attempts -ne 1) { throw 'candidate phase freeze changed' }
    if ($freeze.status -cne 'APPROVED_RECOVERY_SOURCE_READY') { throw 'freeze status is not recovery execution-ready' }
    if (-not (Test-ObjectShape $freeze.interpreter @('path', 'resolved', 'sha256')) -or $freeze.interpreter.path -cne '/home/rastamafugg/.local/share/uv/tools/gdb-mcp/bin/python' -or $freeze.interpreter.resolved -cne '/home/rastamafugg/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12' -or $freeze.interpreter.sha256 -cne '339de109f072e52523066d97a2b3372e358a10cc00c6a9df62c28a6618061900') { throw 'freeze pinned interpreter identity changed' }
    $execution = $freeze.execution_freeze
    if (-not (Test-ObjectShape $execution @('authorized', 'source_sha256', 'ticket_sha256')) -or -not (Test-ExactBoolean $execution.authorized) -or $execution.authorized -ne $true) { throw 'parent execution_freeze has the wrong approved shape or authorization' }

    $manifestExpected = [System.Environment]::GetEnvironmentVariable('LADYBUG_FEAT010_SERVICE_Q_MANIFEST_SHA256', 'Process')
    if (-not (Test-Sha256 $manifestExpected)) { throw 'LADYBUG_FEAT010_SERVICE_Q_MANIFEST_SHA256 must contain the parent-published 64-character lowercase manifest SHA256' }
    $script:ManifestSha256 = (Get-FileHash -LiteralPath $freezePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($script:ManifestSha256 -cne $manifestExpected) { throw 'parent-published manifest digest does not match the freeze bytes' }
    $script:TicketSha256 = [string]$execution.ticket_sha256
    if (-not (Test-Sha256 $script:TicketSha256)) { throw 'ticket digest is missing or malformed in execution_freeze' }

    $frozenSourceObject = $execution.source_sha256
    $frozenSourceNames = @(Get-PropertyNames $frozenSourceObject)
    $expectedNames = @($script:ExpectedInputPaths | Sort-Object)
    if ($frozenSourceNames.Count -ne $expectedNames.Count) { throw 'execution_freeze must pin exactly the six non-manifest source files' }
    for ($index = 0; $index -lt $expectedNames.Count; $index++) {
        if ($frozenSourceNames[$index] -cne $expectedNames[$index]) { throw 'execution_freeze source path set differs from the seven-input freeze' }
    }
    foreach ($relativePath in $script:ExpectedInputPaths) {
        $path = Join-Path $PSScriptRoot ($relativePath -replace '/', '\')
        if (-not [System.IO.File]::Exists($path)) { throw ('required frozen source is missing: ' + $relativePath) }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = [string]$frozenSourceObject.PSObject.Properties[$relativePath].Value
        if (-not (Test-Sha256 $expected) -or $actual -cne $expected) { throw ('source hash differs from parent freeze: ' + $relativePath) }
        $script:SourceSha256[$relativePath] = $actual
    }
    $ticketPath = Join-Path $repoRoot 'wiki\internal\tickets\feat-010-attract-menu-free-start.html'
    $script:TicketPath = $ticketPath
    if (-not [System.IO.File]::Exists($ticketPath)) { throw 'canonical FEAT-010 ticket is missing' }
    $actualTicket = (Get-FileHash -LiteralPath $ticketPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualTicket -cne $script:TicketSha256) { throw 'canonical ticket hash differs from parent freeze' }
    if (-not (Test-ObjectShape $freeze.baseline_sha256 @('baseline/gdb.py.txt', 'baseline/server.py.txt'))) { throw 'immutable archived source hash map changed' }
    $script:InstalledSourceSha256['gdb.py'] = [string]$freeze.baseline_sha256.'baseline/gdb.py.txt'
    $script:InstalledSourceSha256['server.py'] = [string]$freeze.baseline_sha256.'baseline/server.py.txt'
    if (-not (Test-Sha256 $script:InstalledSourceSha256['gdb.py']) -or -not (Test-Sha256 $script:InstalledSourceSha256['server.py'])) { throw 'installed source hash pins are malformed' }
    $script:PreservationStart = Get-HostPreservationSnapshot $freeze
    $script:O01 = Test-O01Controls $script:SourceSha256 $script:InstalledSourceSha256 $script:TicketSha256 $script:PhaseLimitMs
    $script:O02 = Test-O02ExclusiveClaim $script:PhaseNonce

    if ($Phase -eq 'candidate') {
        $baselineOverrunMarker = Join-Path $script:EvidenceDirectory 'service-q-baseline-overrun.json'
        if ([System.IO.File]::Exists($baselineOverrunMarker)) { throw 'candidate dispatch is prohibited because baseline has a retained host-overrun failure marker' }
        $baselinePath = Join-Path $script:EvidenceDirectory 'service-q-baseline.json'
        if (-not [System.IO.File]::Exists($baselinePath)) { throw 'candidate phase requires the independently admitted baseline evidence file' }
        $baselineEvidence = ConvertFrom-Json -InputObject ([System.IO.File]::ReadAllText($baselinePath, (New-Object System.Text.UTF8Encoding($false)))) -ErrorAction Stop
        $script:BaselineEvidenceSha256 = (Get-FileHash -LiteralPath $baselinePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $evidenceFields = @('phase', 'nonce', 'manifest_sha256', 'source_sha256', 'ticket_sha256', 'status', 'admitted', 'baseline_precondition', 'baseline_cases', 'candidate_cases', 'o01', 'o02', 'o03', 'ready', 'terminal', 'worker_ack', 'worker_cleanup_status', 'driver_exit_code', 'driver_exit_confirmed', 'driver_is_wsl_only', 'protocol_lines', 'protocol_records', 'stderr', 'failure_category', 'failure_message', 'failure_detail', 'elapsed_ms', 'deadline_ms', 'go_budget_ms', 'attempt', 'baseline_evidence_sha256', 'preservation', 'evidence_write_started_elapsed_ms', 'evidence_written_utc')
        if (-not (Test-ObjectShape $baselineEvidence $evidenceFields)) { throw 'baseline evidence object shape mismatch' }
        if ($baselineEvidence.phase -cne 'baseline' -or $baselineEvidence.status -cne 'PASS' -or -not (Test-ExactBoolean $baselineEvidence.admitted) -or $baselineEvidence.admitted -ne $true -or $baselineEvidence.failure_category -ne $null -or $baselineEvidence.manifest_sha256 -cne $script:ManifestSha256 -or $baselineEvidence.ticket_sha256 -cne $script:TicketSha256 -or -not (Test-HashObject $baselineEvidence.source_sha256 $script:SourceSha256) -or -not (Test-ExactBoolean $baselineEvidence.driver_is_wsl_only) -or $baselineEvidence.driver_is_wsl_only -ne $true -or -not (Test-ExactBoolean $baselineEvidence.driver_exit_confirmed) -or $baselineEvidence.driver_exit_confirmed -ne $true -or -not (Test-ExactInteger $baselineEvidence.driver_exit_code) -or $baselineEvidence.driver_exit_code -ne 0 -or -not (Test-ExactInteger $baselineEvidence.deadline_ms) -or $baselineEvidence.deadline_ms -ne 60000 -or -not (Test-ExactInteger $baselineEvidence.attempt) -or $baselineEvidence.attempt -ne 1 -or -not (Test-ExactInteger $baselineEvidence.elapsed_ms) -or $baselineEvidence.elapsed_ms -gt $script:PhaseLimitMs -or $null -ne $baselineEvidence.baseline_evidence_sha256) { throw 'baseline evidence is not a matching complete PASS' }
        if ($baselineEvidence.baseline_precondition -cne 'NOT_REQUIRED' -or $baselineEvidence.worker_cleanup_status -cne 'CONFIRMED' -or -not (Test-ExactInteger $baselineEvidence.go_budget_ms) -or $baselineEvidence.go_budget_ms -le 0 -or $baselineEvidence.go_budget_ms -gt (60000 - $script:GoReserveMs) -or -not (Test-ExactInteger $baselineEvidence.evidence_write_started_elapsed_ms) -or $baselineEvidence.evidence_write_started_elapsed_ms -ge $script:TerminalStopAtMs) { throw 'baseline phase budget or worker cleanup evidence is invalid' }
        if (-not (Test-ObjectShape $baselineEvidence.o01 @('status', 'valid_accepted', 'invalid_cases_rejected', 'retained_setup_failure')) -or $baselineEvidence.o01.status -cne 'PASS' -or -not (Test-ExactBoolean $baselineEvidence.o01.valid_accepted) -or $baselineEvidence.o01.valid_accepted -ne $true -or $baselineEvidence.o01.invalid_cases_rejected -isnot [System.Array] -or -not (Test-RetainedSetupControlSummary $baselineEvidence.o01.retained_setup_failure)) { throw 'baseline O01 strict terminal and retained SETUP failure controls are absent' }
        if ($baselineEvidence.o01.invalid_cases_rejected.Count -ne 12) { throw 'baseline O01 invalid-control set has an unexpected count' }
        foreach ($controlName in @('missing_nonce', 'false_wait', 'string_true_wait', 'wrong_typed_returncode', 'wrong_phase', 'wrong_source_hash', 'stale_worker_ack', 'wrong_typed_counter', 'missing_case', 'string_true_case_boolean', 'nonzero_driver_exit', 'string_true_driver_confirmation')) {
            if ($baselineEvidence.o01.invalid_cases_rejected -notcontains $controlName) { throw ('baseline O01 omitted invalid control: ' + $controlName) }
        }
        if (-not (Test-ObjectShape $baselineEvidence.o02 @('status', 'collision_rejected', 'original_preserved', 'retained_path', 'retained_sha256')) -or $baselineEvidence.o02.status -cne 'PASS' -or -not (Test-ExactBoolean $baselineEvidence.o02.collision_rejected) -or $baselineEvidence.o02.collision_rejected -ne $true -or -not (Test-ExactBoolean $baselineEvidence.o02.original_preserved) -or $baselineEvidence.o02.original_preserved -ne $true -or -not (Test-Sha256 $baselineEvidence.o02.retained_sha256) -or -not [System.IO.File]::Exists($baselineEvidence.o02.retained_path)) { throw 'baseline O02 collision sentinel evidence is absent' }
        $baselineSentinelText = [System.IO.File]::ReadAllText($baselineEvidence.o02.retained_path, (New-Object System.Text.UTF8Encoding($false)))
        $expectedBaselineSentinel = Join-Path $script:EvidenceDirectory ('o02-control-baseline-' + $baselineEvidence.nonce + '.tmp')
        if ($baselineEvidence.o02.retained_path -cne $expectedBaselineSentinel -or $baselineSentinelText -cne ('O02-COLLISION-ORIGINAL-' + $baselineEvidence.nonce) -or (Get-FileHash -LiteralPath $baselineEvidence.o02.retained_path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $baselineEvidence.o02.retained_sha256) { throw 'baseline O02 retained collision sentinel changed' }
        if ($baselineEvidence.protocol_records -isnot [System.Array] -or $baselineEvidence.protocol_records.Count -ne 2 -or $baselineEvidence.protocol_records[0].kind -cne 'READY' -or $baselineEvidence.protocol_records[1].kind -cne 'TERMINAL' -or $baselineEvidence.protocol_records[0].phase -cne 'baseline' -or $baselineEvidence.protocol_records[1].phase -cne 'baseline') { throw 'baseline READY/TERMINAL protocol pair is incomplete' }
        if (-not (Test-IdentityEqual $baselineEvidence.terminal.worker_ack $baselineEvidence.worker_ack) -or -not (Test-ExactBoolean $baselineEvidence.worker_ack.wait_confirmed) -or $baselineEvidence.worker_ack.wait_confirmed -ne $baselineEvidence.terminal.worker_ack.wait_confirmed -or -not (Test-ExactInteger $baselineEvidence.worker_ack.returncode) -or $baselineEvidence.worker_ack.returncode -ne $baselineEvidence.terminal.worker_ack.returncode -or $baselineEvidence.o03.status -cne $baselineEvidence.terminal.o03.status -or $baselineEvidence.o03.phase_elapsed_ms -ne $baselineEvidence.terminal.o03.phase_elapsed_ms -or -not (Test-IdentityEqual $baselineEvidence.o03.cleanup.identity $baselineEvidence.terminal.o03.cleanup.identity) -or $baselineEvidence.o03.cleanup.returncode -ne $baselineEvidence.terminal.o03.cleanup.returncode) { throw 'baseline duplicated admission fields differ from raw TERMINAL' }
        if (-not (Test-ObjectShape $baselineEvidence.preservation @('before', 'after', 'baseline_evidence_sha256', 'error')) -or $null -ne $baselineEvidence.preservation.error -or $null -ne $baselineEvidence.preservation.baseline_evidence_sha256 -or -not (Test-PreservationEqual $baselineEvidence.preservation.before $baselineEvidence.preservation.after) -or -not (Test-PreservationEqual $baselineEvidence.preservation.after $script:PreservationStart) -or -not (Test-ExactInteger $baselineEvidence.evidence_write_started_elapsed_ms) -or $baselineEvidence.evidence_write_started_elapsed_ms -ge $script:PhaseLimitMs) { throw 'baseline preservation hashes do not match current pinned source, card, manifest, and protected files' }
        $baselineReason = ''
        Assert-ReadyRecord $baselineEvidence.ready $script:SourceSha256 'baseline' $baselineEvidence.nonce
        if (-not (Test-TerminalRecord $baselineEvidence.terminal 'baseline' $baselineEvidence.nonce $script:ManifestSha256 $script:SourceSha256 $script:TicketSha256 $script:InstalledSourceSha256 $baselineEvidence.ready.supervisor $script:PhaseLimitMs $baselineEvidence.driver_exit_code $baselineEvidence.driver_exit_confirmed ([ref]$baselineReason))) { throw ('baseline terminal evidence rejected: ' + $baselineReason) }
        $script:BaselinePrecondition = 'PASS_MATCHING_HASHES_AND_WORKER_REAP'
    }

    if ($phaseClock.ElapsedMilliseconds -ge ($script:PhaseLimitMs - $script:GoReserveMs)) { throw 'host preflight exhausted the relative GO budget' }
    $remainingMs = [int][Math]::Floor(($script:PhaseLimitMs - $script:GoReserveMs) - $phaseClock.ElapsedMilliseconds)
    if ($remainingMs -le 0) { throw 'no positive relative phase budget remains' }

    $wslScript = '/mnt/e/projects/ladybug/repro/feat010-menu-clock-repair-20261018/controller-service-lease-import-recovery-20261019/service-q.py'
    $wslPython = '/home/rastamafugg/.local/share/uv/tools/gdb-mcp/bin/python'
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = 'wsl.exe'
    $psi.Arguments = '--exec ' + $wslPython + ' -B ' + $wslScript + ' --supervisor'
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $script:Driver = New-Object System.Diagnostics.Process
    $script:Driver.StartInfo = $psi
    if (-not $script:Driver.Start()) { throw 'wsl.exe failed to start' }
    $script:DriverStarted = $true
    $script:PendingStdout = $script:Driver.StandardOutput.ReadLineAsync()
    $stderrTask = $script:Driver.StandardError.ReadToEndAsync()
    $init = [pscustomobject]@{
        kind = 'INIT'
        phase = $Phase
        nonce = $script:PhaseNonce
        manifest_sha256 = $script:ManifestSha256
        source_sha256 = [pscustomobject]$script:SourceSha256
        ticket_sha256 = $script:TicketSha256
    }
    Write-ProtocolJsonLine $script:Driver $init

    $readyStopAt = $script:PhaseLimitMs - $script:GoReserveMs
    $readyRead = Get-NextProtocolLine $script:Driver ([ref]$script:PendingStdout) $readyStopAt
    if ($readyRead.timed_out) {
        Close-ProtocolInput $script:Driver
        $script:FailureCategory = 'SETUP_OR_OBSERVER_FAILURE'
        throw 'Linux supervisor READY was not received before the host GO cutoff; no worker was authorized'
    }
    $script:Ready = Read-JsonLine $readyRead.line 'READY'
    Assert-ReadyRecord $script:Ready $script:SourceSha256
    $remainingMs = [int][Math]::Floor(($script:PhaseLimitMs - $script:GoReserveMs) - $phaseClock.ElapsedMilliseconds)
    if ($remainingMs -le 0) {
        Close-ProtocolInput $script:Driver
        $script:FailureCategory = 'SETUP_OR_OBSERVER_FAILURE'
        throw 'host GO budget expired after READY; worker was not authorized'
    }
    $go = [pscustomobject]@{
        kind = 'GO'
        phase = $Phase
        nonce = $script:PhaseNonce
        manifest_sha256 = $script:ManifestSha256
        remaining_ms = $remainingMs
    }
    Write-ProtocolJsonLine $script:Driver $go
    Close-ProtocolInput $script:Driver

    $terminalStopAt = $script:TerminalStopAtMs
    $terminalRead = Get-NextProtocolLine $script:Driver ([ref]$script:PendingStdout) $terminalStopAt
    if ($terminalRead.timed_out) {
        $script:FailureCategory = 'OBSERVER_FAILURE_UNRESOLVED_WORKER_OWNERSHIP'
        $script:WorkerCleanupStatus = 'UNCONFIRMED'
        throw 'Linux supervisor terminal worker wait acknowledgement exceeded the host phase deadline reserve'
    }
    $script:Terminal = Read-JsonLine $terminalRead.line 'TERMINAL'
    if ($script:Terminal.kind -ne 'TERMINAL') { throw 'supervisor final record was not TERMINAL' }
    $script:WorkerAck = $script:Terminal.worker_ack
    if ($null -eq $script:WorkerAck -or -not (Test-ExactBoolean $script:WorkerAck.wait_confirmed) -or $script:WorkerAck.wait_confirmed -ne $true -or -not (Test-ExactInteger $script:WorkerAck.returncode)) {
        $script:FailureCategory = Get-FailedTerminalCategory $script:Terminal $false
        $script:WorkerCleanupStatus = 'UNCONFIRMED'
        throw ('worker direct-child wait proof is absent or false (' + $script:FailureCategory + ')')
    }
    $script:WorkerCleanupStatus = 'CONFIRMED'
    $remainingWait = [int][Math]::Max(0, $terminalStopAt - $phaseClock.ElapsedMilliseconds)
    if (-not $script:Driver.WaitForExit($remainingWait)) {
        $script:FailureCategory = 'OBSERVER_FAILURE_UNRESOLVED_SUPERVISOR'
        throw 'WSL driver did not exit within the host phase deadline after terminal proof'
    }
    $script:DriverExitConfirmed = $true
    $script:DriverExitCode = $script:Driver.ExitCode
    if ($stderrTask.IsCompleted) {
        $script:WslStderr = $stderrTask.GetAwaiter().GetResult()
    }
    $terminalReason = ''
    if ($script:Terminal.status -ceq 'PASS') {
        if (-not (Test-TerminalRecord $script:Terminal $Phase $script:PhaseNonce $script:ManifestSha256 $script:SourceSha256 $script:TicketSha256 $script:InstalledSourceSha256 $script:Ready.supervisor $script:PhaseLimitMs $script:DriverExitCode $script:DriverExitConfirmed ([ref]$terminalReason))) {
            $script:FailureCategory = 'OBSERVER_FAILURE_INVALID_PASS_RECORD'
            throw ('PASS terminal record rejected: ' + $terminalReason)
        }
        $script:PreservationEnd = Get-HostPreservationSnapshot $freeze
        if (-not (Test-PreservationEqual $script:PreservationStart $script:PreservationEnd)) { $script:FailureCategory = 'SOURCE_PRESERVATION_FAILURE'; throw 'host source, ticket, manifest, or protected file hashes changed during the phase' }
        $script:FinalStatus = 'PASS'
        $script:WorkerCleanupStatus = 'CONFIRMED'
        $script:FailureCategory = $null
        $script:FailureMessage = $null
    } elseif ($script:Terminal.status -ceq 'FAIL') {
        $failedTerminalReason = ''
        $failedTerminalValid = Test-FailedTerminalRecord $script:Terminal $Phase $script:PhaseNonce $script:ManifestSha256 $script:SourceSha256 $script:TicketSha256 $script:InstalledSourceSha256 $script:Ready.supervisor $script:PhaseLimitMs $script:DriverExitCode $script:DriverExitConfirmed ([ref]$failedTerminalReason)
        $script:FailureCategory = Get-FailedTerminalCategory $script:Terminal $failedTerminalValid
        if ($failedTerminalValid) {
            $script:FailureMessage = $script:Terminal.worker.outcome.error
            throw ('qualification worker failed (' + $script:FailureCategory + '): ' + $script:FailureMessage)
        }
        throw ('failed terminal record rejected (' + $script:FailureCategory + '): ' + $failedTerminalReason)
    } else {
        $script:FailureCategory = 'OBSERVER_FAILURE_INVALID_TERMINAL_STATUS'
        throw ('terminal record status is neither PASS nor FAIL: ' + [string]$script:Terminal.status)
    }
} catch {
    if ($null -eq $script:FailureCategory) {
        $script:FailureCategory = 'SETUP_OR_OBSERVER_FAILURE'
    }
    $script:FailureMessage = $_.Exception.Message
    $script:FailureDetail = $_.Exception.ToString()
} finally {
    if ($script:DriverStarted -and $null -ne $script:Driver) {
        if (-not $script:Driver.HasExited -and $phaseClock.ElapsedMilliseconds -lt $script:TerminalStopAtMs) {
            Close-ProtocolInput $script:Driver
            $left = [int][Math]::Max(0, $script:TerminalStopAtMs - $phaseClock.ElapsedMilliseconds)
            if ($left -gt 0) { $script:DriverExitConfirmed = $script:Driver.WaitForExit($left) }
        }
        if ($script:Driver.HasExited) {
            $script:DriverExitConfirmed = $true
            $script:DriverExitCode = $script:Driver.ExitCode
            try {
                if ($null -ne $stderrTask -and $stderrTask.IsCompleted) { $script:WslStderr = $stderrTask.GetAwaiter().GetResult() }
            } catch { }
        }
    }
    if ($null -ne $script:PreservationStart -and $null -eq $script:PreservationEnd -and $null -ne $script:Freeze) {
        try {
            $script:PreservationEnd = Get-HostPreservationSnapshot $script:Freeze
            if (-not (Test-PreservationEqual $script:PreservationStart $script:PreservationEnd)) {
                throw 'source, ticket, manifest, or protected files changed during this failed phase'
            }
        } catch {
            $script:PreservationError = $_.Exception.ToString()
            $script:FinalStatus = 'FAIL'
            if ($null -eq $script:FailureCategory) { $script:FailureCategory = 'SOURCE_PRESERVATION_FAILURE' }
            if ($null -eq $script:FailureMessage) { $script:FailureMessage = $_.Exception.Message }
        }
    }
    if (-not $script:DriverExitConfirmed -and $null -ne $script:Driver -and $script:FinalStatus -eq 'PASS') {
        $script:FinalStatus = 'FAIL'
        $script:FailureCategory = 'OBSERVER_FAILURE_UNRESOLVED_SUPERVISOR'
        $script:FailureMessage = 'WSL driver direct-child exit was not confirmed before the host finalization reserve'
    }
    if ($phaseClock.ElapsedMilliseconds -ge $script:TerminalStopAtMs -and $script:FinalStatus -eq 'PASS') {
        $script:FinalStatus = 'FAIL'
        $script:FailureCategory = 'HOST_FINALIZATION_RESERVE_EXHAUSTED'
        $script:FailureMessage = 'host phase exhausted the fixed finalization reserve before evidence was written'
    }
    if ($script:FinalStatus -ne 'PASS') { $script:FinalStatus = 'FAIL' }
    $evidenceWriteStarted = [long]$phaseClock.ElapsedMilliseconds
    $evidence = [pscustomobject]@{
        phase = $Phase
        nonce = $script:PhaseNonce
        manifest_sha256 = $script:ManifestSha256
        source_sha256 = [pscustomobject]$script:SourceSha256
        ticket_sha256 = $script:TicketSha256
        status = $script:FinalStatus
        admitted = ($script:FinalStatus -eq 'PASS')
        baseline_precondition = $script:BaselinePrecondition
        baseline_cases = $script:BaselineCases
        candidate_cases = $script:CandidateCases
        o01 = $script:O01
        o02 = $script:O02
        o03 = if ($null -ne $script:Terminal) { $script:Terminal.o03 } else { $null }
        ready = $script:Ready
        terminal = $script:Terminal
        worker_ack = $script:WorkerAck
        worker_cleanup_status = $script:WorkerCleanupStatus
        driver_exit_code = $script:DriverExitCode
        driver_exit_confirmed = $script:DriverExitConfirmed
        driver_is_wsl_only = $true
        protocol_lines = @($script:WslStdout)
        protocol_records = @($script:ProtocolLines)
        stderr = $script:WslStderr
        failure_category = $script:FailureCategory
        failure_message = $script:FailureMessage
        failure_detail = $script:FailureDetail
        elapsed_ms = [long]$phaseClock.ElapsedMilliseconds
        deadline_ms = $script:PhaseLimitMs
        go_budget_ms = $remainingMs
        attempt = 1
        baseline_evidence_sha256 = $script:BaselineEvidenceSha256
        preservation = [pscustomobject]@{
            before = $script:PreservationStart
            after = $script:PreservationEnd
            baseline_evidence_sha256 = $script:BaselineEvidenceSha256
            error = $script:PreservationError
        }
        evidence_write_started_elapsed_ms = $evidenceWriteStarted
        evidence_written_utc = [DateTime]::UtcNow.ToString('o')
    }
    try {
        Write-JsonCreateNew $script:EvidencePath $evidence
        $evidenceWriteCompleted = [long]$phaseClock.ElapsedMilliseconds
        if ($evidenceWriteCompleted -gt $script:PhaseLimitMs) {
            $script:FinalStatus = 'FAIL'
            $script:FailureCategory = 'HOST_PHASE_OVERRUN'
            $script:FailureMessage = 'evidence write completed after the fixed 60000ms host deadline'
            $fallback = Join-Path $script:EvidenceDirectory ('service-q-' + $Phase + '-overrun.json')
            $overrun = [pscustomobject]@{
                phase = $Phase
                nonce = $script:PhaseNonce
                status = 'FAIL'
                admitted = $false
                failure_category = 'HOST_PHASE_OVERRUN'
                failure_message = $script:FailureMessage
                elapsed_ms = $evidenceWriteCompleted
                deadline_ms = $script:PhaseLimitMs
                terminal = $script:Terminal
                worker_ack = $script:WorkerAck
                driver_exit_code = $script:DriverExitCode
                driver_exit_confirmed = $script:DriverExitConfirmed
                protocol_lines = @($script:WslStdout)
                stderr = $script:WslStderr
            }
            Write-JsonCreateNew $fallback $overrun
        }
    } catch {
        $fallback = Join-Path $script:EvidenceDirectory ('service-q-failure-' + $Phase + '-' + $script:PhaseNonce + '.json')
        $writeFailure = [pscustomobject]@{
            phase = $Phase
            nonce = $script:PhaseNonce
            status = 'FAIL'
            admitted = $false
            failure_category = 'EVIDENCE_FINALIZATION_FAILURE'
            original_failure = $script:FailureDetail
            evidence_write_error = $_.Exception.ToString()
            worker_ack = $script:WorkerAck
            worker_cleanup_status = $script:WorkerCleanupStatus
            driver_exit_confirmed = $script:DriverExitConfirmed
            elapsed_ms = [long]$phaseClock.ElapsedMilliseconds
        }
        try { Write-JsonCreateNew $fallback $writeFailure } catch { }
        $script:FinalStatus = 'FAIL'
        $script:FailureCategory = 'EVIDENCE_FINALIZATION_FAILURE'
    }
    $phaseClock.Stop()
}

if ($script:FinalStatus -eq 'PASS') {
    Write-Output ('SERVICE_Q_PHASE_PASS ' + $Phase + ' ' + $script:ManifestSha256)
    exit 0
}
Write-Output ('SERVICE_Q_PHASE_FAIL ' + $Phase + ' ' + $script:FailureCategory + ' ' + $script:FailureMessage)
exit 1
