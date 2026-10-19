$ErrorActionPreference = 'Stop'
$utf8 = [Text.UTF8Encoding]::new($false, $true)
$paths = @{
 'wiki/internal/tickets/feat-010-attract-menu-free-start.html' = 'complete-controller-review-20261019'
 'wiki/internal/tickets/index.html' = 'feat010-complete-controller-review-20261019'
 'wiki/internal/log.html' = 'feat010-complete-controller-audit-20261019'
 'wiki/internal/tooling/testing.html' = 'controller-qualification-boundary-20261019'
}
foreach ($entry in $paths.GetEnumerator()) {
    $current = [IO.File]::ReadAllText((Join-Path (Get-Location) $entry.Key), $utf8)
    $section = [regex]::Match($current, '<section id="' + $entry.Value + '">[\s\S]*?</section>').Value
    if (-not $section) { throw 'Missing owned section' }
    $info = [Diagnostics.ProcessStartInfo]::new('git')
    $info.ArgumentList.Add('show'); $info.ArgumentList.Add('HEAD:' + $entry.Key)
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true
    $child = [Diagnostics.Process]::Start($info)
    $memory = [IO.MemoryStream]::new()
    $child.StandardOutput.BaseStream.CopyTo($memory)
    $child.WaitForExit()
    if ($child.ExitCode -ne 0) { throw 'HEAD read failed' }
    $base = $utf8.GetString($memory.ToArray())
    $staged = $base.Insert($base.LastIndexOf('</body>'), $section + "`n")
    $temporary = Join-Path $PSScriptRoot ('staged-' + [IO.Path]::GetFileName($entry.Key) + '.txt')
    [IO.File]::WriteAllText($temporary, $staged, $utf8)
    $blob = (& git hash-object -w --no-filters -- $temporary).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Blob write failed' }
    & git update-index --cacheinfo ('100644,' + $blob + ',' + $entry.Key)
    if ($LASTEXITCODE -ne 0) { throw 'Index update failed' }
    Remove-Item -LiteralPath $temporary
}
