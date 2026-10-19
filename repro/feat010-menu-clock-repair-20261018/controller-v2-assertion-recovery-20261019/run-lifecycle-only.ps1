$ErrorActionPreference = 'Stop'
$prefix = Join-Path $PSScriptRoot 'lifecycle-characterization'
foreach ($suffix in @('.stdout.json','.stderr.txt','.run.json')) {
    if (Test-Path -LiteralPath ($prefix + $suffix)) { throw 'One-shot lifecycle output already exists' }
}
$freeze = Get-Content (Join-Path $PSScriptRoot 'offline-parent-freeze.json') -Raw | ConvertFrom-Json
foreach ($name in @('lifecycle-regression.cjs','executed-controller.js.txt')) {
    $expected = ($freeze | Where-Object name -eq $name).sha256
    if ((Get-FileHash (Join-Path $PSScriptRoot $name)).Hash.ToLowerInvariant() -ne $expected) { throw 'Frozen input changed' }
}
$startInfo = [Diagnostics.ProcessStartInfo]::new('C:/Program Files/nodejs/node.exe')
$startInfo.ArgumentList.Add((Join-Path $PSScriptRoot 'lifecycle-regression.cjs'))
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
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($prefix + '.stdout.json', $stdout, $utf8)
[IO.File]::WriteAllText($prefix + '.stderr.txt', $stderr, $utf8)
$record = @{ phase = 'lifecycle'; purpose = 'Independent offline phase; response phase not retried'; exit_code = $child.ExitCode; completed = $completed; elapsed_seconds = $timer.Elapsed.TotalSeconds; deadline_seconds = 60; emulator_calls = 0; real_gdb_calls = 0; runtime_readiness = 'NOT_ESTABLISHED' }
[IO.File]::WriteAllText($prefix + '.run.json', ($record | ConvertTo-Json), $utf8)
$record | ConvertTo-Json -Compress
if (-not $completed -or $child.ExitCode -ne 0) { throw 'Lifecycle phase failed; retained output; no retry' }
