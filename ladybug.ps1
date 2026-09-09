<#
Run from the project root:
  .\ladybug.ps1 Game             # Normal production game ROM
  .\ladybug.ps1 Checkpoint       # FEAT-007 automated checks; no game window
  .\ladybug.ps1 Game -Check      # Check launcher prerequisites only
#>
[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet('Game', 'Checkpoint')]
    [string]$Mode = 'Game',
    [switch]$Check
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$linuxRoot = (& wsl.exe --exec wslpath -a -u $projectRoot).Trim()
if ($LASTEXITCODE -ne 0 -or -not $linuxRoot) { throw 'WSL could not resolve the project directory.' }
$emulator = "$linuxRoot/docs/reference/xroar/src/xroar"
if ($Mode -eq 'Game') { $emulator = '/usr/local/bin/xroar' }
& wsl.exe --exec test -x $emulator
if ($LASTEXITCODE -ne 0) { throw "XRoar is unavailable: $emulator" }
if ($Mode -eq 'Game') {
    $rom = Join-Path $projectRoot 'build/ladybug.rom'
    if (-not (Test-Path -LiteralPath $rom) -or (Get-Item -LiteralPath $rom).Length -ne 65536) {
        throw 'Expected the existing 65536-byte GMC image at build/ladybug.rom.'
    }
    Write-Host 'Production game ROM: build/ladybug.rom.'
    if ($Check) { Write-Host 'Launcher prerequisites pass; this is not a gameplay verification.'; exit 0 }
    & wsl.exe --cd $linuxRoot --exec $emulator -ao pulse -machine coco3 -machine-cpu 6809 -ram 512 -ram-init random -cart-type gmc -cart-rom "$linuxRoot/build/ladybug.rom" -cart-autorun -tv-input rgb
    exit $LASTEXITCODE
}
Write-Host 'FEAT-007 production verification: cold boot, input, HUD, ranking and instructions.'
foreach ($file in @('ladybug.rom', 'ladybug-presentation.json', 'ladybug_shared_text.inc')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "build/$file"))) {
        throw "Missing production artifact: $file. Run scripts/build.sh build first."
    }
}
if ($Check) { Write-Host 'Production verification prerequisites pass.'; exit 0 }
& wsl.exe --cd $linuxRoot --exec python3 "$linuxRoot/scripts/verify_feat007_text.py" --phase runtime --refresh
exit $LASTEXITCODE
