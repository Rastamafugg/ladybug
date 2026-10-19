$ErrorActionPreference = 'Stop'
$utf8 = [Text.UTF8Encoding]::new($false)
$caseDir = Split-Path $PSScriptRoot -Parent
$freeze = Get-Content (Join-Path $PSScriptRoot 'review-source-freeze.json') -Raw | ConvertFrom-Json
$checked = @()
foreach ($property in $freeze.retained_sha256.PSObject.Properties) {
    $file = Join-Path $caseDir $property.Name
    $actual = (Get-FileHash -LiteralPath $file).Hash.ToLowerInvariant()
    if ($actual -ne $property.Value) { throw "Protected evidence changed: $($property.Name)" }
    $checked += $property.Name
}
foreach ($property in $freeze.audit_archive_sha256.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $property.Name)).Hash.ToLowerInvariant() -ne $property.Value) { throw 'Archived controller source changed' }
}
$record = @{ kind = 'Parent QA review'; date = '2026-10-19'; verdict = 'NOT_READY_RUNTIME_PAUSED'; protected_files_unchanged = $checked; original_inline_archives_unchanged = $true; production_changes = 0; emulator_attempts = 0; real_gdb_calls = 0; capacity_change_bytes = 0; response_phase = 'SETUP_FAILURE_BEFORE_19_CASES'; lifecycle_phase = '22_OF_23_MATCHED_ONE_HARNESS_MEASUREMENT_FAILURE'; retries = 0; current_proposal = 'Offline v2 controller repair only; external session deadline/ownership unresolved'; prior_sigint_only_retry = 'Held; insufficient after complete review' }
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'parent-qa.json'), ($record | ConvertTo-Json -Depth 8), $utf8)
$sections = @{}
$sections['wiki/internal/tickets/feat-010-attract-menu-free-start.html'] = @'
<section id="complete-controller-review-20261019"><h2>2026-10-19 — Complete controller review; runtime paused</h2>
<p><strong>High-risk review verdict: controller NOT READY.</strong> User explicitly pauses runtime and requests complete controller review. Luna Extra High response, admission and lifecycle reviews plus parent QA include the recovered exact inline controller/preflight, Ready-embedded Python analysis, parent qualification/reconciliation wrappers, three host files and pinned installed GDB-MCP source. <a href="../../../repro/feat010-menu-clock-repair-20261018/controller-review-20261019/controller-audit.html">Full severity findings, coverage and bounded replacement proposal</a>.</p>
<p>Parent review incorrectly promoted synthetic helper qualification to complete controller readiness. The dispatch-time inline SIGINT predicate was not frozen or exercised; GDB-MCP formatting omits signal-name. Real attach signal remains unknown. Broader risks include structured-error false admission, command-unbound register/session parsing, unbounded awaits and service-side unregistered process ownership, unchecked cleanup, fixed-path evidence overwrite, handoff acknowledgement and trace interpretation gaps. Prior Ready is withdrawn for runtime dispatch; the narrow attachment-only retry proposal is held and insufficient. No product assertion or stutter cause is established.</p>
<p>Original R-I remains one stop/zero guest reads/R-T not run; observed cleanup completed in4.011seconds. This review ran no emulator/GDB/build. New offline response characterization failed syntax before19cases (0.0737646/60seconds); separate lifecycle characterization matched22of23 historical expectations but failed one nested-JSON cleanup counter (0.1075977/60seconds). Both failures retained, neither retried or counted as readiness. All18protected evidence/artifact hashes and six original-source archive hashes remain unchanged. No production/capacity change.</p>
<p><strong>Proposed next scope, not approved/Ready:</strong> new case-local v2 harness/controller sources only; typed response/stop admission, ownership/deadline contract, exclusive per-attempt evidence and offline good/broken fixtures. One60second syntax/fixture phase then one60second mocked controller phase; first failure stops. No guard/window/service/ROM changes or runtime attempt. Service creation/cancellation dependency must be resolved or separately proposed before any live Ready claim. The full linked brief states targets, exact exclusions, order and stop conditions.</p></section>
'@
$sections['wiki/internal/tickets/index.html'] = @'
<section id="feat010-complete-controller-review-20261019"><h2>2026-10-19 — FEAT-010 controller unqualified; runtime paused</h2><p><a href="feat-010-attract-menu-free-start.html#complete-controller-review-20261019">Complete controller audit and replacement offline-only proposal</a>. Prior runtime Ready withdrawn; SIGINT-only retry held. Structured response admission, ownership/deadline, cleanup and evidence gaps exceed the attachment assertion. Two new offline observer failures retained without retry. No emulator/GDB/build/product change; helper qualification is not end-to-end readiness.</p></section>
'@
$sections['wiki/internal/log.html'] = @'
<section id="feat010-complete-controller-audit-20261019"><h2>2026-10-19 — FEAT-010 complete controller audit</h2><p>User pauses runtime. PM/debugger/QA parent review uses Luna Extra High response/admission/lifecycle assignments, recovers exact original inline main/preflight tool input, archives Ready analysis and visible-call parent wrappers, and inspects pinned GDB-MCP formatter/session implementation. Identifies parent qualification-boundary failure and broader admission, deadlines/ownership, cleanup, persistence and trace-order gaps. Response offline run stops at CommonJS syntax; independent lifecycle run has22matched expectations/one harness counter failure. No retry, emulator, live GDB, build or product change. All protected old evidence/source hashes preserved. <a href="tickets/feat-010-attract-menu-free-start.html#complete-controller-review-20261019">Canonical findings and proposed bounded offline v2 repair</a>. Scoped HTML links/IDs and staged whitespace checked; no global wiki lint claim.</p></section>
'@
foreach ($entry in $sections.GetEnumerator()) {
    $path = $entry.Key
    $section = $entry.Value
    $current = [IO.File]::ReadAllText((Join-Path (Get-Location) $path))
    $id = [regex]::Match($section, 'id="([^"]+)"').Groups[1].Value
    if ($current.Contains('id="' + $id + '"')) { throw 'Review section already exists' }
    $offset = $current.LastIndexOf('</body>')
    if ($offset -lt 0) { throw 'Missing HTML body terminator' }
    [IO.File]::WriteAllText((Join-Path (Get-Location) $path), $current.Insert($offset, $section + "`n"), $utf8)
    $info = [Diagnostics.ProcessStartInfo]::new('git')
    $info.ArgumentList.Add('show'); $info.ArgumentList.Add('HEAD:' + $path)
    $info.UseShellExecute = $false; $info.RedirectStandardOutput = $true
    $child = [Diagnostics.Process]::Start($info)
    $base = $child.StandardOutput.ReadToEnd(); $child.WaitForExit()
    if ($child.ExitCode -ne 0) { throw 'Cannot read HEAD wiki baseline' }
    $staged = $base.Insert($base.LastIndexOf('</body>'), $section + "`n")
    $temporary = Join-Path $PSScriptRoot ('staged-' + [IO.Path]::GetFileName($path) + '.txt')
    [IO.File]::WriteAllText($temporary, $staged, $utf8)
    $blob = (& git hash-object -w -- $temporary).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot create scoped wiki blob' }
    & git update-index --cacheinfo ('100644,' + $blob + ',' + $path)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot stage scoped wiki section' }
    Remove-Item -LiteralPath $temporary
}
$record | ConvertTo-Json -Compress -Depth 8
