[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('response', 'lifecycle')]
    [string]$Phase
)

$ErrorActionPreference = 'Stop'
$AuditRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$CaseRoot = [IO.Path]::GetFullPath((Split-Path -Parent $AuditRoot))
$ResultsRoot = Join-Path $AuditRoot 'v2-results'
$PhaseClaimPath = Join-Path $ResultsRoot "$Phase.phase-claim.json"
$CardPath = Join-Path $AuditRoot 'controller-v2-card.json'
$ManifestPath = Join-Path $AuditRoot 'review-source-freeze.json'
$NodePath = 'C:\Program Files\nodejs\node.exe'
$OwnedNames = @(
    'analysis-v2.py.txt',
    'controller-v2.js.txt',
    'lifecycle-regression-v2.cjs',
    'response-fixtures-v2.json',
    'response-regression-v2.cjs',
    'run-controller-v2-offline.ps1'
)
$PhaseClock = [Diagnostics.Stopwatch]::StartNew()
$AttemptDir = $null
$AttemptId = $null
$CardSha256 = $null
$SourceStateBefore = $null
$PreservationBefore = $null
$Preflight = $null
$ChildResult = $null
$PreservationAfter = $null
$FinalSourceState = $null
$Status = 'FAIL'
$Failure = $null
$ChildrenRemaining = if ($Phase -eq 'response') { 2 } else { 1 }

function Get-Sha256([string]$LiteralPath) {
    return (Get-FileHash -LiteralPath $LiteralPath -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-ExclusiveUtf8([string]$LiteralPath, [string]$Text) {
    $full = [IO.Path]::GetFullPath($LiteralPath)
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Text)
    $stream = [IO.File]::Open($full, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}

function Write-ExclusiveJson([string]$LiteralPath, $Value) {
    $json = ConvertTo-Json -InputObject $Value -Depth 40 -Compress
    Write-ExclusiveUtf8 $LiteralPath ($json + "`n")
}

function Add-FailureText([string]$Message) {
    if ([string]::IsNullOrWhiteSpace($Message)) { return }
    if ([string]::IsNullOrWhiteSpace($script:Failure)) { $script:Failure = $Message }
    else { $script:Failure = $script:Failure + '; ' + $Message }
}

function Test-WithinRoot([string]$Root, [string]$Candidate) {
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $candidateFull = [IO.Path]::GetFullPath($Candidate)
    $prefix = $rootFull + [IO.Path]::DirectorySeparatorChar
    return $candidateFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function New-PhaseClaim {
    if (-not (Test-Path -LiteralPath $ResultsRoot -PathType Container)) { [void][IO.Directory]::CreateDirectory($ResultsRoot) }
    Write-ExclusiveJson $PhaseClaimPath ([pscustomobject]@{
        ticket = 'FEAT-010'
        phase = $Phase
        createdUtc = [DateTime]::UtcNow.ToString('o')
        processId = $PID
        rule = 'exclusive single phase claim; no reruns'
    })
}

function Get-SourceState($Card) {
    $freeze = $Card.execution_freeze
    $expected = $freeze.files_sha256
    if ($null -eq $expected) { throw 'Parent execution_freeze.files_sha256 is absent.' }
    $expectedNames = @($expected.PSObject.Properties.Name | Sort-Object)
    $ownedSorted = @($OwnedNames | Sort-Object)
    if (($expectedNames -join '|') -cne ($ownedSorted -join '|')) { throw 'execution_freeze.files_sha256 must name exactly the six owned source files.' }
    $actual = [ordered]@{}
    $errors = [Collections.Generic.List[string]]::new()
    foreach ($name in $OwnedNames) {
        $expectedHash = [string]$expected.$name
        if ($expectedHash -notmatch '^[a-fA-F0-9]{64}$') { $errors.Add("freeze hash is invalid for $name"); continue }
        $sourcePath = Join-Path $AuditRoot $name
        try {
            $actual[$name] = Get-Sha256 $sourcePath
            if ($actual[$name] -cne $expectedHash.ToLowerInvariant()) { $errors.Add("frozen source mismatch: $name") }
        }
        catch { $errors.Add("cannot hash frozen source ${name}: $($_.Exception.Message)") }
    }
    if ($errors.Count -gt 0) { throw ($errors -join '; ') }
    return [pscustomobject]@{ expected = $expected; actual = $actual }
}

function Get-PreservationState($Card) {
    $failures = [Collections.Generic.List[string]]::new()
    $auditMap = $Card.protected_audit_sha256
    $auditNames = @($auditMap.PSObject.Properties.Name)
    if ($auditNames.Count -ne 32) { $failures.Add("protected audit map count is $($auditNames.Count), expected 32") }
    foreach ($name in ($auditNames | Sort-Object)) {
        $target = [IO.Path]::GetFullPath((Join-Path $AuditRoot $name))
        if (-not (Test-WithinRoot $AuditRoot $target)) { $failures.Add("protected audit path escapes audit root: $name"); continue }
        try {
            $actualHash = Get-Sha256 $target
            if ($actualHash -cne ([string]$auditMap.$name).ToLowerInvariant()) { $failures.Add("protected audit hash changed: $name") }
        }
        catch { $failures.Add("protected audit file missing/unreadable: $name") }
    }
    if ([string]$Card.protected_case_manifest -cne 'review-source-freeze.json retained_sha256 (18 entries), relative to parent case directory') {
        $failures.Add('protected_case_manifest pointer differs from the reviewed retained manifest')
    }
    try {
        $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
        $retained = $manifest.retained_sha256
        $retainedNames = @($retained.PSObject.Properties.Name)
        if ($retainedNames.Count -ne 18) { $failures.Add("retained case manifest count is $($retainedNames.Count), expected 18") }
        foreach ($name in ($retainedNames | Sort-Object)) {
            $target = [IO.Path]::GetFullPath((Join-Path $CaseRoot $name))
            if (-not (Test-WithinRoot $CaseRoot $target)) { $failures.Add("retained case path escapes parent case root: $name"); continue }
            try {
                $actualHash = Get-Sha256 $target
                if ($actualHash -cne ([string]$retained.$name).ToLowerInvariant()) { $failures.Add("retained case hash changed: $name") }
            }
            catch { $failures.Add("retained case file missing/unreadable: $name") }
        }
    }
    catch { $failures.Add("retained case manifest could not be verified: $($_.Exception.Message)") }
    return [pscustomobject]@{
        valid = ($failures.Count -eq 0)
        auditExpected = 32
        caseExpected = 18
        failures = @($failures.ToArray())
    }
}

function New-AttemptDirectory {
    if (Test-Path -LiteralPath $ResultsRoot) {
        $existing = @(Get-ChildItem -LiteralPath $ResultsRoot -Directory -ErrorAction SilentlyContinue | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'response.attempt.json') })
        if ($existing.Count -gt 0) { throw 'A response attempt marker already exists; reruns are prohibited.' }
    }
    $script:AttemptId = ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N'))
    $script:AttemptDir = Join-Path $ResultsRoot $script:AttemptId
    if (Test-Path -LiteralPath $script:AttemptDir) { throw 'Generated v2-results attempt directory already exists.' }
    [void][IO.Directory]::CreateDirectory($script:AttemptDir)
    Write-ExclusiveJson (Join-Path $script:AttemptDir 'response.attempt.json') ([pscustomobject]@{
        ticket = 'FEAT-010'
        phase = 'response'
        attemptId = $script:AttemptId
        createdUtc = [DateTime]::UtcNow.ToString('o')
        cardSha256 = $null
        sourceHashes = $null
    })
}

function Find-ResponseAttempt($Card, $SourceState) {
    if (-not (Test-Path -LiteralPath $ResultsRoot -PathType Container)) { throw 'No response attempt exists for the lifecycle prerequisite.' }
    $runs = @(Get-ChildItem -LiteralPath $ResultsRoot -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'response.run.json') })
    if ($runs.Count -ne 1) { throw "Expected exactly one response run, found $($runs.Count)." }
    $directory = $runs[0].FullName
    if (-not (Test-WithinRoot $ResultsRoot $directory)) { throw 'Response attempt directory escapes v2-results.' }
    $run = Get-Content -LiteralPath (Join-Path $directory 'response.run.json') -Raw | ConvertFrom-Json
    if ($run.phase -cne 'response' -or $run.status -cne 'PASS') { throw 'The matching frozen response phase did not pass.' }
    if ($run.cardSha256 -cne $script:CardSha256) { throw 'Response result card hash differs from current card.' }
    foreach ($name in $OwnedNames) {
        if ([string]$run.sourceHashes.$name -cne [string]$SourceState.expected.$name) { throw "Response result source freeze differs for $name." }
    }
    if ($run.preservation.after -ne $true) { throw 'Response phase did not preserve protected inputs after execution.' }
    if (Test-Path -LiteralPath (Join-Path $directory 'lifecycle.attempt.json')) { throw 'Lifecycle attempt marker already exists; reruns are prohibited.' }
    $script:AttemptDir = $directory
    $script:AttemptId = Split-Path -Leaf $directory
    return $run
}

function Invoke-BoundedNode([string[]]$Arguments) {
    if ($script:ChildrenRemaining -lt 1) { throw 'No child invocation remains in the fixed phase plan.' }
    $phaseElapsedAtEntry = [int]$PhaseClock.ElapsedMilliseconds
    $childrenAfterCurrent = $script:ChildrenRemaining - 1
    $futureChildReserve = 6500 * $childrenAfterCurrent
    $remainingAtEntry = 60000 - $phaseElapsedAtEntry
    $availableForThisChild = $remainingAtEntry - 10000 - $futureChildReserve - 6500
    $timeout = [Math]::Min(50000, [Math]::Floor($availableForThisChild / $script:ChildrenRemaining))
    if ($timeout -le 0) { throw 'No bounded child budget remains after reserving phase finalization, kill, output, and later child time.' }
    $script:ChildrenRemaining -= 1
    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $NodePath
    $startInfo.WorkingDirectory = $AuditRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    foreach ($argument in $Arguments) { $startInfo.ArgumentList.Add([string]$argument) }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $childClock = [Diagnostics.Stopwatch]::StartNew()
    try {
        if (-not $process.Start()) { throw 'Node child process did not start.' }
    }
    catch {
        $childClock.Stop()
        $process.Dispose()
        throw
    }
    $childPid = $process.Id
    $childExecutable = $process.StartInfo.FileName
    $childStartedUtc = $null
    $identityCaptureFailure = $null
    try { $childStartedUtc = $process.StartTime.ToUniversalTime().ToString('o') }
    catch { $identityCaptureFailure = $_.Exception.Message }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $startupElapsed = [int]$PhaseClock.ElapsedMilliseconds - $phaseElapsedAtEntry
    $timeout = [Math]::Max(0, [Math]::Floor($timeout - $startupElapsed))
    $naturalCompletion = $false
    if ($timeout -gt 0) { $naturalCompletion = $process.WaitForExit([int]$timeout) }
    $exitConfirmed = $naturalCompletion
    $killFailure = $null
    if (-not $naturalCompletion) {
        try { $process.Kill($true) }
        catch { $killFailure = $_.Exception.Message }
        try { $exitConfirmed = $process.WaitForExit(4000) }
        catch {
            $exitConfirmed = $false
            if ($killFailure) { $killFailure = $killFailure + '; ' + $_.Exception.Message }
            else { $killFailure = $_.Exception.Message }
        }
    }
    $stdoutReady = $stdoutTask.Wait(1250)
    $stderrReady = $stderrTask.Wait(1250)
    $captureFailures = [Collections.Generic.List[string]]::new()
    $stdout = '[stdout capture incomplete after bounded wait]'
    $stderr = '[stderr capture incomplete after bounded wait]'
    if ($stdoutReady) {
        try { $stdout = $stdoutTask.GetAwaiter().GetResult() }
        catch { $captureFailures.Add("stdout capture failed: $($_.Exception.Message)") }
    }
    else { $captureFailures.Add('stdout capture did not finish within the bounded wait') }
    if ($stderrReady) {
        try { $stderr = $stderrTask.GetAwaiter().GetResult() }
        catch { $captureFailures.Add("stderr capture failed: $($_.Exception.Message)") }
    }
    else { $captureFailures.Add('stderr capture did not finish within the bounded wait') }
    $exitCode = if ($exitConfirmed) { $process.ExitCode } else { -1 }
    $childClock.Stop()
    $process.Dispose()
    $cleanupMessages = [Collections.Generic.List[string]]::new()
    if (-not $exitConfirmed) { $cleanupMessages.Add('Node child did not exit after the bounded kill grace') }
    if ($killFailure) { $cleanupMessages.Add("Node child termination failed: $killFailure") }
    foreach ($captureFailure in $captureFailures) { $cleanupMessages.Add($captureFailure) }
    $cleanupFailure = if ($cleanupMessages.Count -gt 0) { $cleanupMessages -join '; ' } else { $null }
    return [pscustomobject]@{
        timedOut = ($timeout -le 0 -or -not $naturalCompletion -or -not $exitConfirmed)
        processExitConfirmed = $exitConfirmed
        cleanupFailure = $cleanupFailure
        processIdentity = [pscustomobject]@{ pid = $childPid; executable = $childExecutable; startedUtc = $childStartedUtc; captureFailure = $identityCaptureFailure }
        exitCode = $exitCode
        elapsedMs = [int]$childClock.ElapsedMilliseconds
        stdout = $stdout
        stderr = $stderr
    }
}

function Get-SyntaxPreflightScript {
    return @'
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Module = require('node:module');
const root = process.argv[1];
if (typeof root !== 'string' || root.length === 0) throw new Error('audit path argument missing');
const syntaxFiles = ['response-regression-v2.cjs', 'lifecycle-regression-v2.cjs'];
for (const file of syntaxFiles) new vm.Script(fs.readFileSync(path.join(root, file), 'utf8'), { filename: file });
const modulePath = path.join(root, 'controller-v2.js.txt');
const compiled = new Module(modulePath, module);
compiled.filename = modulePath;
compiled.paths = Module._nodeModulePaths(root);
compiled._compile(fs.readFileSync(modulePath, 'utf8'), modulePath);
process.stdout.write(JSON.stringify({ status: 'PASS', syntaxFiles, inertControllerCompiled: true, runFixedControllerInvoked: false }) + '\n');
'@
}

function Get-TestExpectedCases([string]$SelectedPhase) {
    $card = Get-Content -LiteralPath $CardPath -Raw | ConvertFrom-Json
    if ($SelectedPhase -eq 'response') { return @($card.response_card.required_cases) }
    return @($card.lifecycle_card.required_cases)
}

try {
    New-PhaseClaim
    if ($Phase -eq 'response') { New-AttemptDirectory }
    $cardBytes = [IO.File]::ReadAllBytes($CardPath)
    $script:CardSha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($cardBytes)).ToLowerInvariant()
    $card = [Text.Encoding]::UTF8.GetString($cardBytes) | ConvertFrom-Json
    $script:SourceStateBefore = Get-SourceState $card
    $script:PreservationBefore = Get-PreservationState $card
    if ($Phase -eq 'lifecycle') {
        [void](Find-ResponseAttempt $card $script:SourceStateBefore)
        Write-ExclusiveJson (Join-Path $script:AttemptDir 'lifecycle.attempt.json') ([pscustomobject]@{
            ticket = 'FEAT-010'
            phase = 'lifecycle'
            attemptId = $script:AttemptId
            createdUtc = [DateTime]::UtcNow.ToString('o')
            cardSha256 = $script:CardSha256
            sourceHashes = $script:SourceStateBefore.actual
        })
    }
    Write-ExclusiveJson (Join-Path $script:AttemptDir "$Phase.preflight.json") ([pscustomobject]@{
        phase = $Phase
        attemptId = $script:AttemptId
        cardSha256 = $script:CardSha256
        sourceHashes = $script:SourceStateBefore.actual
        preservationBefore = $script:PreservationBefore
    })

    if (-not (Test-Path -LiteralPath $NodePath -PathType Leaf)) { throw 'The reviewed Node.js executable is unavailable.' }
    if (-not $script:PreservationBefore.valid) { throw ('Protected input precheck failed: ' + ($script:PreservationBefore.failures -join '; ')) }

    if ($Phase -eq 'response') {
        $preflight = Invoke-BoundedNode @('-e', (Get-SyntaxPreflightScript), $AuditRoot)
        $script:Preflight = $preflight
        $script:ChildResult = $preflight
        if ($preflight.cleanupFailure) { throw "Response phase syntax/module preflight child cleanup failed: $($preflight.cleanupFailure)" }
        if ($preflight.timedOut -or $preflight.exitCode -ne 0 -or $preflight.stderr.Length -ne 0) { throw 'Response phase syntax/module preflight failed or exceeded its child deadline.' }
        $preflightRecord = $preflight.stdout.Trim() | ConvertFrom-Json
        if ($preflightRecord.status -cne 'PASS' -or $preflightRecord.inertControllerCompiled -ne $true -or $preflightRecord.runFixedControllerInvoked -ne $false) { throw 'Syntax/module preflight result is invalid.' }
    }

    $harnessName = if ($Phase -eq 'response') { 'response-regression-v2.cjs' } else { 'lifecycle-regression-v2.cjs' }
    $harnessPath = Join-Path $AuditRoot $harnessName
    $arguments = @($harnessPath)
    if ($Phase -eq 'lifecycle') { $arguments += $script:AttemptDir }
    $script:ChildResult = Invoke-BoundedNode $arguments
    if ($script:ChildResult.cleanupFailure) { throw "Offline harness child cleanup failed: $($script:ChildResult.cleanupFailure)" }
    if ($script:ChildResult.timedOut) { throw 'Offline harness child exceeded its bounded deadline.' }
    if ($script:ChildResult.exitCode -ne 0) { throw "Offline harness stopped at its first failure (exit $($script:ChildResult.exitCode))." }
    if ($script:ChildResult.stderr.Length -ne 0) { throw 'Offline harness wrote nonempty stderr.' }
    $harnessResult = $script:ChildResult.stdout.Trim() | ConvertFrom-Json
    if ($harnessResult.status -cne 'PASS') { throw 'Offline harness did not emit a PASS JSON result.' }
    $expectedCases = @(Get-TestExpectedCases $Phase)
    $actualCases = if ($Phase -eq 'response') { @($harnessResult.passedCases) } else { @($harnessResult.cases | ForEach-Object { $_.id }) }
    if (($expectedCases -join '|') -cne ($actualCases -join '|')) { throw 'Harness case results differ from the exact card list.' }
    if ($Phase -eq 'response' -and $harnessResult.schema -cne 'ladybug.feat010.controller-v2.response.v1') { throw 'Response JSON schema identifier mismatch.' }
    if ($Phase -eq 'lifecycle' -and $harnessResult.schema -cne 'ladybug.feat010.controller-v2.lifecycle.v1') { throw 'Lifecycle JSON schema identifier mismatch.' }
    if ($PhaseClock.ElapsedMilliseconds -ge 60000) { throw 'Entire phase reached or exceeded the 60-second deadline.' }
    $script:Status = 'PASS'
}
catch {
    $script:Failure = $_.Exception.Message
    $script:Status = 'FAIL'
}
finally {
    try {
        if (Test-Path -LiteralPath $CardPath) {
            $afterCard = Get-Content -LiteralPath $CardPath -Raw | ConvertFrom-Json
            $script:PreservationAfter = Get-PreservationState $afterCard
            $script:FinalSourceState = Get-SourceState $afterCard
            if ($script:PreservationAfter.valid -ne $true) {
                $script:Status = 'FAIL'
                Add-FailureText ('Protected input postcheck failed: ' + ($script:PreservationAfter.failures -join '; '))
            }
            if ($script:SourceStateBefore) {
                foreach ($name in $OwnedNames) {
                    if ($script:SourceStateBefore.actual[$name] -cne $script:FinalSourceState.actual[$name]) {
                        $script:Status = 'FAIL'
                        Add-FailureText "Owned source hash changed during the phase: $name"
                    }
                }
            }
            if ($script:CardSha256 -and (Get-Sha256 $CardPath) -cne $script:CardSha256) {
                $script:Status = 'FAIL'
                Add-FailureText 'Card hash changed during the phase'
            }
        }
    }
    catch {
        $script:Status = 'FAIL'
        Add-FailureText ('Post-phase preservation check failed: ' + $_.Exception.Message)
    }
    if ($script:AttemptDir) {
        try {
            if ($PhaseClock.ElapsedMilliseconds -ge 55000) {
                $script:Status = 'FAIL'
                Add-FailureText 'Phase reached the 55-second finalization reserve boundary'
            }
            $stdoutName = "$Phase.stdout.json"
            $stderrName = "$Phase.stderr.txt"
            $stdoutText = if ($script:ChildResult) { $script:ChildResult.stdout } else { '' }
            $stderrText = if ($script:ChildResult) { $script:ChildResult.stderr } else { '' }
            Write-ExclusiveUtf8 (Join-Path $script:AttemptDir $stdoutName) $stdoutText
            Write-ExclusiveUtf8 (Join-Path $script:AttemptDir $stderrName) $stderrText
            if ($PhaseClock.ElapsedMilliseconds -ge 60000) {
                $script:Status = 'FAIL'
                Add-FailureText 'Entire phase reached or exceeded the 60-second deadline before run result'
            }
            $runRecord = [pscustomobject]@{
                ticket = 'FEAT-010'
                phase = $Phase
                status = $script:Status
                attemptId = $script:AttemptId
                cardSha256 = $script:CardSha256
                sourceHashes = if ($script:SourceStateBefore) { $script:SourceStateBefore.actual } else { $null }
                preservation = [pscustomobject]@{ before = ($script:PreservationBefore.valid -eq $true); after = ($script:PreservationAfter.valid -eq $true); beforeDetails = $script:PreservationBefore; afterDetails = $script:PreservationAfter }
                preflight = $script:Preflight
                child = if ($script:ChildResult) { [pscustomobject]@{ identity = $script:ChildResult.processIdentity; timedOut = $script:ChildResult.timedOut; processExitConfirmed = $script:ChildResult.processExitConfirmed; cleanupFailure = $script:ChildResult.cleanupFailure; exitCode = $script:ChildResult.exitCode; elapsedMs = $script:ChildResult.elapsedMs } } else { $null }
                elapsedMs = [int]$PhaseClock.ElapsedMilliseconds
                failure = $script:Failure
                scope = 'OFFLINE_MOCK_ONLY; runtime identity/service cancellation/live behavior not proved'
            }
            Write-ExclusiveJson (Join-Path $script:AttemptDir "$Phase.run.json") $runRecord
        }
        catch {
            $script:Status = 'FAIL'
            Add-FailureText ('Exclusive evidence write failed: ' + $_.Exception.Message)
        }
    }
}

if ($PhaseClock.ElapsedMilliseconds -ge 60000) {
    $script:Status = 'FAIL'
    Add-FailureText 'Entire phase reached or exceeded the 60-second deadline after evidence writes'
}

$final = [pscustomobject]@{
    schema = 'ladybug.feat010.controller-v2.wrapper.v1'
    phase = $Phase
    status = $script:Status
    attemptId = $script:AttemptId
    elapsedMs = [int]$PhaseClock.ElapsedMilliseconds
    failure = $script:Failure
    preservationBefore = $script:PreservationBefore
    preservationAfter = $script:PreservationAfter
}
Write-Output (ConvertTo-Json -InputObject $final -Depth 16 -Compress)
if ($script:Status -ne 'PASS') { exit 1 }
