$ErrorActionPreference = 'Stop'
$clock = [System.Diagnostics.Stopwatch]::StartNew()
$root = $PSScriptRoot
$maximumMs = 30000
$resultPath = Join-Path $root 'evidence/recovery-r1-preflight-result.json'
if (Test-Path -LiteralPath $resultPath) { throw 'Preflight result already exists; no retry or overwrite' }
$rows = New-Object System.Collections.Generic.List[object]
$child = $null
$childStarted = $false
$claimCreated = $false
$exitConfirmed = $false
$childExitCode = $null
$compilerResult = $null
$compilerText = ''
$compilerPrefixB64 = ''
$failure = $null
function Test-PreflightTimestamp {
    param($Record, [string]$Expected)
    return ($Record.started_utc -is [string] -and $Record.started_utc -ceq $Expected)
}
function Require-Preflight {
    param([string]$Id, [bool]$Condition)
    $rows.Add([pscustomobject]@{ id = $Id; passed = $Condition })
    if (-not $Condition) { throw ('Preflight failed: ' + $Id) }
    if ($clock.ElapsedMilliseconds -ge ($maximumMs - 1000)) { throw 'Preflight work deadline reached' }
}
try {
    $freeze = Get-Content -LiteralPath (Join-Path $root 'integration-freeze.json') -Raw | ConvertFrom-Json
    $expected = $freeze.recovery_preflight
    Require-Preflight 'approved-freeze-present' ($null -ne $expected -and $expected.status -ceq 'SOURCE_REVIEWED_READY' -and $expected.dispatch_authorized -eq $true -and $freeze.qualification_dispatch_authorized -eq $false -and $freeze.runtime_ready -eq $false -and $freeze.runtime_attempts_authorized -eq 0 -and $freeze.installation_authorized -eq $false)
    Require-Preflight 'invocation-path' ([System.IO.Path]::GetFullPath($PSCommandPath) -ieq [System.IO.Path]::GetFullPath((Join-Path $root $expected.path)))
    $claimPath = Join-Path $root 'evidence/recovery-r1-preflight.claim'
    $claimStream = New-Object System.IO.FileStream($claimPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $claimCreated = $true
    try {
        $claimBytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes('SRO-P one invocation; retained on failure')
        $claimStream.Write($claimBytes, 0, $claimBytes.Length)
        $claimStream.Flush($true)
    } finally { $claimStream.Dispose() }
    $hostPath = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    Require-Preflight 'host-image' ($hostPath -ieq $expected.host_path -and (Get-FileHash -LiteralPath $hostPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $expected.host_sha256)
    Require-Preflight 'host-version' ($PSVersionTable.PSVersion.ToString() -ceq $expected.ps_version)
    Require-Preflight 'preflight-source' ((Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $expected.source_sha256)
    $requiredPaths = @('service/gdb.py', 'service/server.py', 'stop-q.py', 'run-integration-q.ps1', 'evidence/sro-q-first-failure-20261020/executed-host.ps1.txt')
    $actualPaths = @($expected.source_files.PSObject.Properties.Name | Sort-Object)
    Require-Preflight 'complete-source-key-set' (($actualPaths -join '|') -ceq (($requiredPaths | Sort-Object) -join '|'))
    foreach ($pin in $expected.source_files.PSObject.Properties) {
        Require-Preflight ('source-' + $pin.Name) ((Get-FileHash -LiteralPath (Join-Path $root $pin.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $pin.Value)
    }
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'run-integration-q.ps1'), [ref]$tokens, [ref]$parseErrors)
    Require-Preflight 'current-host-parses' (@($parseErrors).Count -eq 0)
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'evidence/sro-q-first-failure-20261020/executed-host.ps1.txt'), [ref]$tokens, [ref]$parseErrors)
    Require-Preflight 'retained-bad-host-rejected' (@($parseErrors).Count -gt 0)
    $stamp = '2026-10-20T12:34:56.1234567Z'
    $roundTrip = ConvertFrom-Json -InputObject (ConvertTo-Json -Compress -InputObject ([pscustomobject]@{ started_utc = $stamp }))
    Require-Preflight 'timestamp-roundtrip-string' (Test-PreflightTimestamp $roundTrip $stamp)
    Require-Preflight 'timestamp-date-negative' (-not (Test-PreflightTimestamp ([pscustomobject]@{started_utc = [datetime]$stamp}) $stamp))
    $pythonBody = @'
import hashlib, json, pathlib, sys
root = pathlib.Path('/mnt/e/projects/ladybug/repro/feat010-menu-clock-repair-20261018/controller-integration-20261019')
rows = []
try:
    freeze = json.loads((root / 'integration-freeze.json').read_text(encoding='utf-8'))
    expected = freeze['recovery_preflight']
    executable = pathlib.Path(sys.executable).resolve()
    if str(executable) != freeze['python']['resolved'] or hashlib.sha256(executable.read_bytes()).hexdigest() != freeze['python']['sha256']:
        raise ValueError('pinned compiler identity mismatch')
    for relative in ('service/gdb.py', 'service/server.py', 'stop-q.py'):
        if (root / relative).stat().st_size > 262144:
            raise ValueError('compile input exceeds fixed cap: ' + relative)
        source = (root / relative).read_bytes()
        if len(source) > 262144 or hashlib.sha256(source).hexdigest() != expected['source_files'][relative]:
            raise ValueError('compile input cap/hash mismatch: ' + relative)
        compile(source, relative, 'exec', dont_inherit=True)
        rows.append({'id': relative, 'compiled_only': True})
    try:
        compile('def broken(:\n', '<independent-malformed-negative>', 'exec')
    except SyntaxError:
        rows.append({'id': 'malformed-python-rejected', 'passed': True})
    else:
        raise ValueError('independent malformed Python was accepted')
    print(json.dumps({'kind': 'SRO_P_COMPILE_ONLY', 'rows': rows}, separators=(',', ':')))
except BaseException as exc:
    print(json.dumps({'kind': 'SRO_P_COMPILE_FAILURE', 'rows': rows, 'error_type': type(exc).__name__, 'error': str(exc)[:2048]}, separators=(',', ':')))
    sys.exit(1)
'@
    $processInfo = New-Object System.Diagnostics.ProcessStartInfo
    $processInfo.FileName = $expected.wsl_path
    Require-Preflight 'wsl-image' ((Get-FileHash -LiteralPath $processInfo.FileName -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $expected.wsl_sha256)
    $processInfo.Arguments = '--exec ' + $freeze.python.path + ' -B -'
    $processInfo.UseShellExecute = $false
    $processInfo.CreateNoWindow = $true
    $processInfo.RedirectStandardInput = $true
    $processInfo.RedirectStandardOutput = $true
    $processInfo.StandardInputEncoding = New-Object System.Text.UTF8Encoding($false)
    $child = New-Object System.Diagnostics.Process
    $child.StartInfo = $processInfo
    $childStarted = $child.Start()
    Require-Preflight 'compiler-started' $childStarted
    $child.StandardInput.WriteLine($pythonBody)
    $child.StandardInput.Close()
    $compilerBytes = New-Object System.IO.MemoryStream
    try {
        $chunk = New-Object byte[] 4096
        while ($true) {
            $remaining = [int]($maximumMs - 1000 - $clock.ElapsedMilliseconds)
            if ($remaining -le 0) { throw 'Compiler output deadline reached' }
            $readTask = $child.StandardOutput.BaseStream.ReadAsync($chunk, 0, $chunk.Length)
            if (-not $readTask.Wait($remaining)) { throw 'Compiler output wait timed out' }
            $count = $readTask.GetAwaiter().GetResult()
            if ($count -eq 0) { break }
            if ($compilerBytes.Length + $count -gt 8192) { throw 'Compiler output exceeded8192byte cap' }
            $compilerBytes.Write($chunk, 0, $count)
        }
        $compilerText = (New-Object System.Text.UTF8Encoding($false, $true)).GetString($compilerBytes.ToArray())
    } finally {
        $compilerPrefixB64 = [Convert]::ToBase64String($compilerBytes.ToArray())
        $compilerBytes.Dispose()
    }
    $remaining = [int]($maximumMs - 1000 - $clock.ElapsedMilliseconds)
    Require-Preflight 'compiler-wait-budget' ($remaining -gt 0)
    $exitConfirmed = $child.WaitForExit($remaining)
    Require-Preflight 'compiler-direct-exit' $exitConfirmed
    $childExitCode = $child.ExitCode
    $compilerResult = ConvertFrom-Json -InputObject $compilerText
    Require-Preflight 'compiler-envelope-kind' ($compilerResult.kind -is [string] -and $compilerResult.kind -cin @('SRO_P_COMPILE_ONLY', 'SRO_P_COMPILE_FAILURE'))
    if ($compilerResult.kind -ceq 'SRO_P_COMPILE_FAILURE') {
        Require-Preflight 'compiler-failure-schema' ($compilerResult.error_type -is [string] -and $compilerResult.error -is [string] -and @($compilerResult.rows).Count -le 3)
    }
    Require-Preflight 'compiler-exit-zero' ($childExitCode -eq 0)
    Require-Preflight 'compiler-result-shape' ($compilerResult.kind -ceq 'SRO_P_COMPILE_ONLY' -and @($compilerResult.rows).Count -eq 4)
    for ($index = 0; $index -lt 3; $index++) {
        Require-Preflight ('compiler-result-row-' + $index) ($compilerResult.rows[$index].id -ceq $requiredPaths[$index] -and $compilerResult.rows[$index].compiled_only -eq $true)
    }
    Require-Preflight 'compiler-negative-row' ($compilerResult.rows[3].id -ceq 'malformed-python-rejected' -and $compilerResult.rows[3].passed -eq $true)
} catch {
    $failure = $_.Exception.Message
} finally {
    if ($childStarted -and -not $exitConfirmed) {
        $cleanupRemaining = [int]($maximumMs - 1000 - $clock.ElapsedMilliseconds)
        if ($cleanupRemaining -gt 0) {
            try { $exitConfirmed = $child.WaitForExit($cleanupRemaining) } catch { }
        }
    }
    if ($childStarted -and $exitConfirmed) {
        try { $childExitCode = $child.ExitCode } catch { }
    }
}
$elapsedBeforeEvidence = $clock.ElapsedMilliseconds
if (-not $claimCreated) {
    [Console]::Error.WriteLine('SRO_P_FAIL_BEFORE_EXCLUSIVE_CLAIM ' + $failure)
    exit 1
}
if ($null -eq $failure -and $elapsedBeforeEvidence -ge ($maximumMs - 500)) { $failure = 'Preflight exceeded reserved evidence boundary' }
$result = [ordered]@{
    schema = 'ladybug.feat010.recovery-preflight.v1'
    status = if ($null -eq $failure) { 'CHECKS_COMPLETE_PENDING_PARENT_EXIT_AND_DEADLINE' } else { 'FAIL' }
    rows = @($rows.ToArray())
    failure = $failure
    direct_exit_confirmed = $exitConfirmed
    child_exit_code = $childExitCode
    child_started = $childStarted
    unresolved_child = ($childStarted -and -not $exitConfirmed)
    compiler_result = $compilerResult
    compiler_output = $compilerText
    compiler_output_prefix_b64 = $compilerPrefixB64
    elapsed_before_evidence_ms = $elapsedBeforeEvidence
    maximum_ms = $maximumMs
    runtime_attempts = 0
    external_admission_required = 'Parent must observe runner exit0, SRO_P_PASS, matching retained evidence and entire start-to-exit elapsed at most30000ms; this record never self-certifies final completion.'
}
$bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes((ConvertTo-Json -InputObject $result -Depth 20) + [Environment]::NewLine)
try {
    $stream = New-Object System.IO.FileStream($resultPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length); $stream.Flush($true) } finally { $stream.Dispose() }
} catch {
    [Console]::Error.WriteLine('Preflight evidence finalization failed: ' + $_.Exception.Message)
    exit 1
}
if ($null -ne $failure -or $clock.ElapsedMilliseconds -ge $maximumMs) {
    [Console]::Error.WriteLine('SRO_P_FAIL ' + $failure)
    exit 1
}
[Console]::WriteLine('SRO_P_PASS')
exit 0
