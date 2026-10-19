$ErrorActionPreference = 'Stop'
$auditDir = $PSScriptRoot
$utf8 = [System.Text.UTF8Encoding]::new($false)
$names = @('response-regression.cjs','response-fixtures.json','lifecycle-regression.cjs','response-review.json','lifecycle-review.json','admission-review.json','executed-controller.js.txt','executed-preflight.js.txt','ready-inline-analysis.py.txt')
$freeze = foreach ($name in $names) {
    $file = Join-Path $auditDir $name
    @{ name = $name; sha256 = (Get-FileHash -LiteralPath $file).Hash.ToLowerInvariant() }
}
$freezePath = Join-Path $auditDir 'offline-parent-freeze.json'
$stream = [IO.File]::Open($freezePath, [IO.FileMode]::CreateNew)
try { $bytes = $utf8.GetBytes(($freeze | ConvertTo-Json -Depth 8)); $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
foreach ($phase in @('response','lifecycle')) {
    $prefix = Join-Path $auditDir ($phase + '-characterization')
    foreach ($suffix in @('.stdout.json','.stderr.txt','.run.json')) {
        if (Test-Path -LiteralPath ($prefix + $suffix)) { throw 'One-shot offline result already exists' }
    }
    $startInfo = [Diagnostics.ProcessStartInfo]::new('C:/Program Files/nodejs/node.exe')
    $startInfo.ArgumentList.Add((Join-Path $auditDir ($phase + '-regression.cjs')))
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $child = [Diagnostics.Process]::Start($startInfo)
    $stdoutTask = $child.StandardOutput.ReadToEndAsync()
    $stderrTask = $child.StandardError.ReadToEndAsync()
    $completed = $child.WaitForExit(55000)
    if (-not $completed) { $child.Kill(); $child.WaitForExit(2000) | Out-Null }
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $timer.Stop()
    [IO.File]::WriteAllText($prefix + '.stdout.json', $stdout, $utf8)
    [IO.File]::WriteAllText($prefix + '.stderr.txt', $stderr, $utf8)
    $record = @{ phase = $phase; purpose = 'Non-gating offline historical characterization'; exit_code = $child.ExitCode; completed = $completed; elapsed_seconds = $timer.Elapsed.TotalSeconds; deadline_seconds = 60; emulator_calls = 0; real_gdb_calls = 0; runtime_readiness = 'NOT_ESTABLISHED' }
    [IO.File]::WriteAllText($prefix + '.run.json', ($record | ConvertTo-Json), $utf8)
    $record | ConvertTo-Json -Compress
    if (-not $completed -or $child.ExitCode -ne 0) { throw 'Offline phase failed; retained output; no retry' }
}
