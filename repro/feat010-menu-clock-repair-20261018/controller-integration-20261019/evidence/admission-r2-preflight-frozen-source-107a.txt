$ErrorActionPreference = 'Stop'
$clock = [System.Diagnostics.Stopwatch]::StartNew()
$root = $PSScriptRoot
$maximumMs = 30000
$maximumFileBytes = 16777216
$maximumFileUnits = 16777216
$fileChunkBytes = 4096
$requiredDescriptorPath = 'evidence/sro-qualification-case-contract.json'
$requiredDescriptorSha256 = '493ffe9524977bb07376f55ef521a4d5e691539be5b7624f6194bab2d36043c0'
$resultPath = Join-Path $root 'evidence/admission-r2-preflight-result.json'
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
$powershellReaderControls = New-Object System.Collections.Generic.List[object]
$pythonReaderControls = @()
$powershellDocumentReads = @()
$pythonDocumentReads = @()
$preflightScalarPinsPassed = $false
$preflightScalarPinControls = New-Object System.Collections.Generic.List[object]
$script:preflightPinRowAdded = $false
$failure = $null
function Test-ScalarString {
    param([AllowNull()][object]$Value)
    return ($Value -is [string])
}
function Get-DirectJsonPropertyValue {
    param([AllowNull()][object]$Object, [string]$Name)
    if ($null -eq $Object) { return ,$null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return ,$null }
    return ,$property.Value
}
function Test-ExactJsonKeys {
    param([AllowNull()][object]$Object, [string[]]$ExpectedKeys)
    if ($null -eq $Object -or $Object -is [System.Array] -or $Object -is [string]) { return $false }
    $actualKeys = @($Object.PSObject.Properties | ForEach-Object { $_.Name })
    if ($actualKeys.Count -ne $ExpectedKeys.Count) { return $false }
    foreach ($key in $ExpectedKeys) {
        if ($actualKeys -cnotcontains $key) { return $false }
    }
    return $true
}
function Test-ReaderEnvelope {
    param([AllowNull()][object]$Envelope)
    if (-not (Test-ExactJsonKeys $Envelope @('documents', 'vectors'))) { return $false }
    return ($Envelope.documents -is [System.Array] -and $Envelope.vectors -is [System.Array])
}
function Test-ReaderDocumentShape {
    param([AllowNull()][object]$Control)
    if (-not (Test-ExactJsonKeys $Control @('id', 'accepted', 'rejection', 'position', 'actual_position', 'retained_bytes', 'text_units', 'whole_document_decode_attempted', 'sha256', 'prefix_b64'))) { return $false }
    $isInteger = { param($Value) (($Value -is [byte]) -or ($Value -is [int16]) -or ($Value -is [int32]) -or ($Value -is [int64])) }
    if ($Control.id -isnot [string] -or $Control.accepted -isnot [bool] -or $Control.whole_document_decode_attempted -isnot [bool]) { return $false }
    if ($Control.rejection -is [System.Array] -or ($null -ne $Control.rejection -and $Control.rejection -isnot [string])) { return $false }
    foreach ($name in @('position', 'actual_position', 'retained_bytes')) {
        $value = Get-DirectJsonPropertyValue $Control $name
        if (-not (& $isInteger $value) -or $value -lt 0) { return $false }
    }
    if ($Control.retained_bytes -gt $maximumFileBytes -or $Control.position -gt ($maximumFileBytes + 1) -or $Control.actual_position -gt ($maximumFileBytes + 1)) { return $false }
    if ($null -ne $Control.text_units -and (-not (& $isInteger $Control.text_units) -or $Control.text_units -lt 0)) { return $false }
    if ($Control.sha256 -isnot [string] -or $Control.sha256 -cnotmatch '^[0-9a-f]{64}$') { return $false }
    if ($Control.prefix_b64 -isnot [string] -or $Control.prefix_b64.Length -gt 44) { return $false }
    return $true
}
function Test-ReaderVectorShape {
    param([AllowNull()][object]$Control)
    if (-not (Test-ExactJsonKeys $Control @('id', 'accepted', 'rejection', 'position', 'actual_position', 'retained_bytes', 'text_units', 'whole_document_decode_attempted', 'sha256', 'prefix_b64', 'passed'))) { return $false }
    if ($Control.id -isnot [string] -or $Control.accepted -isnot [bool] -or $Control.whole_document_decode_attempted -isnot [bool] -or $Control.passed -isnot [bool]) { return $false }
    if ($Control.rejection -is [System.Array] -or ($null -ne $Control.rejection -and $Control.rejection -isnot [string])) { return $false }
    if ($Control.rejection -ceq 'VECTOR_EXCEPTION') {
        return (-not $Control.accepted -and -not $Control.passed -and -not $Control.whole_document_decode_attempted -and $null -eq $Control.position -and $null -eq $Control.actual_position -and $null -eq $Control.retained_bytes -and $null -eq $Control.text_units -and $null -eq $Control.sha256 -and $null -eq $Control.prefix_b64)
    }
    $isInteger = { param($Value) (($Value -is [byte]) -or ($Value -is [int16]) -or ($Value -is [int32]) -or ($Value -is [int64])) }
    foreach ($name in @('position', 'actual_position', 'retained_bytes')) {
        $value = Get-DirectJsonPropertyValue $Control $name
        if (-not (& $isInteger $value) -or $value -lt 0) { return $false }
    }
    if ($Control.retained_bytes -gt $maximumFileBytes -or $Control.position -gt ($maximumFileBytes + 1) -or $Control.actual_position -gt ($maximumFileBytes + 1)) { return $false }
    if ($null -ne $Control.text_units -and (-not (& $isInteger $Control.text_units) -or $Control.text_units -lt 0)) { return $false }
    if ($Control.sha256 -isnot [string] -or $Control.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $Control.prefix_b64 -isnot [string] -or $Control.prefix_b64.Length -gt 44) { return $false }
    return $true
}
function Read-BoundedUtf8Stream {
    param([System.IO.Stream]$Stream)
    $retained = [System.IO.MemoryStream]::new([int]$maximumFileBytes)
    $chunk = New-Object byte[] $fileChunkBytes
    $position = 0
    $overLimit = $false
    $readFailure = $null
    try {
        while ($true) {
            if ($clock.ElapsedMilliseconds -ge ($maximumMs - 1000)) { $readFailure = 'READ_DEADLINE'; break }
            $request = [int][Math]::Min([long]$fileChunkBytes, ([long]$maximumFileBytes - $position + 1))
            try { $count = $Stream.Read($chunk, 0, $request) } catch { $readFailure = 'READ_ERROR'; break }
            if ($count -eq 0) { break }
            $keep = [int][Math]::Min([long]$count, ([long]$maximumFileBytes - $position))
            if ($keep -gt 0) {
                $retained.Write($chunk, 0, $keep)
                $position += $keep
            }
            if ($count -gt $keep) {
                $position += 1
                $overLimit = $true
                break
            }
        }
        $retainedBytes = [int]$retained.Length
        $raw = $retained.GetBuffer()
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            $digest = $hasher.ComputeHash($raw, 0, $retainedBytes)
            $sha256 = ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
        } finally { $hasher.Dispose() }
        $sampleCount = [int][Math]::Min(32, $retainedBytes)
        $prefixB64 = [Convert]::ToBase64String($raw, 0, $sampleCount)
        if ($null -ne $readFailure) {
            return [pscustomobject]@{
                accepted = $false; rejection = $readFailure; position = $position
                retained_bytes = $retainedBytes; text = $null; text_units = $null
                whole_document_decode_attempted = $false; sha256 = $sha256; prefix_b64 = $prefixB64
            }
        }
        if ($overLimit) {
            return [pscustomobject]@{
                accepted = $false; rejection = 'BYTE_LIMIT_BEFORE_DECODE'; position = $position
                retained_bytes = $retainedBytes; text = $null; text_units = $null
                whole_document_decode_attempted = $false; sha256 = $sha256; prefix_b64 = $prefixB64
            }
        }
        $offset = 0
        if ($retainedBytes -ge 3 -and $raw[0] -eq 239 -and $raw[1] -eq 187 -and $raw[2] -eq 191) { $offset = 3 }
        $text = $null
        try {
            $text = (New-Object System.Text.UTF8Encoding($false, $true)).GetString($raw, $offset, ($retainedBytes - $offset))
        } catch [System.Text.DecoderFallbackException] {
            return [pscustomobject]@{
                accepted = $false; rejection = 'STRICT_UTF8'; position = $position
                retained_bytes = $retainedBytes; text = $null; text_units = $null
                whole_document_decode_attempted = $true; sha256 = $sha256; prefix_b64 = $prefixB64
            }
        }
        $units = $text.Length
        if ($units -gt $maximumFileUnits) {
            return [pscustomobject]@{
                accepted = $false; rejection = 'UTF16_UNIT_LIMIT'; position = $position
                retained_bytes = $retainedBytes; text = $null; text_units = $units
                whole_document_decode_attempted = $true; sha256 = $sha256; prefix_b64 = $prefixB64
            }
        }
        if ($units -eq 0) {
            return [pscustomobject]@{
                accepted = $false; rejection = 'EMPTY_JSON_OBJECT'; position = $position
                retained_bytes = $retainedBytes; text = ''; text_units = 0
                whole_document_decode_attempted = $true; sha256 = $sha256; prefix_b64 = $prefixB64
            }
        }
        return [pscustomobject]@{
            accepted = $true; rejection = $null; position = $position
            retained_bytes = $retainedBytes; text = $text; text_units = $units
            whole_document_decode_attempted = $true; sha256 = $sha256; prefix_b64 = $prefixB64
        }
    } finally { $retained.Dispose() }
}
function Read-BoundedUtf8File {
    param([string]$Path)
    try { $stream = [System.IO.File]::OpenRead($Path) }
    catch {
        return ,[pscustomobject]@{
            accepted = $false; rejection = 'OPEN_ERROR'; position = [long]0; actual_position = [long]0
            retained_bytes = [long]0; text = $null; text_units = $null
            whole_document_decode_attempted = $false; sha256 = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'; prefix_b64 = ''
        }
    }
    try {
        $result = Read-BoundedUtf8Stream $stream
        try { $actualPosition = [long]$stream.Position } catch { $actualPosition = [long]$result.position }
        $result | Add-Member -NotePropertyName actual_position -NotePropertyValue $actualPosition
        return ,$result
    }
    finally { $stream.Dispose() }
}
function Get-ReaderSummary {
    param([string]$Id, [object]$Observation)
    return [pscustomobject]@{
        id = $Id; accepted = [bool]$Observation.accepted; rejection = $Observation.rejection
        position = [long]$Observation.position; actual_position = [long]$Observation.actual_position
        retained_bytes = [long]$Observation.retained_bytes; text_units = if ($null -eq $Observation.text_units) { $null } else { [long]$Observation.text_units }
        whole_document_decode_attempted = [bool]$Observation.whole_document_decode_attempted
        sha256 = $Observation.sha256; prefix_b64 = $Observation.prefix_b64
    }
}
function New-AsciiRepeatStream {
    param([int]$Count, [byte]$Value)
    $text = [System.String]::new([char]$Value, $Count)
    $bytes = [System.Text.Encoding]::ASCII.GetBytes($text)
    return [System.IO.MemoryStream]::new($bytes, $false)
}
function New-ReaderVectorStream {
    param([object]$Vector)
    switch ($Vector.input_kind) {
        'repeat_byte' { return New-AsciiRepeatStream ([int]$Vector.input_count) ([byte]$Vector.input_byte) }
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
        default { throw ('Unsupported file-reader vector input kind: ' + $Vector.input_kind) }
    }
}
function Test-ReaderVector {
    param([object]$Vector)
    $stream = New-ReaderVectorStream $Vector
    try {
        $observation = Read-BoundedUtf8Stream $stream
        $actualPosition = [long]$stream.Position
    }
    finally { $stream.Dispose() }
    $expectedAccepted = ($Vector.expected -ceq 'ACCEPT')
    $passed = ($observation.accepted -eq $expectedAccepted -and $observation.position -eq $Vector.expected_position -and $actualPosition -eq $Vector.expected_position)
    if ($expectedAccepted) {
        $passed = $passed -and $observation.retained_bytes -eq $Vector.expected_retained_bytes -and $observation.text_units -eq $Vector.expected_text_units
        if ($Vector.expected_text -ceq 'ASCII_A_REPEAT') {
            $passed = $passed -and $observation.text.Length -eq $Vector.expected_text_units -and $observation.text.Trim([char[]]@('A')).Length -eq 0
        } elseif ($Vector.expected_text -ceq 'ASCII_A_4092_THEN_U00E9_Z') {
            $passed = $passed -and $observation.text.Length -eq $Vector.expected_text_units -and $observation.text.Substring(0, [int]$Vector.repeat_count).Trim([char[]]@('A')).Length -eq 0 -and [int][char]$observation.text[[int]$Vector.repeat_count] -eq 233 -and $observation.text.Substring($observation.text.Length - 1) -ceq 'Z'
        } else { $passed = $false }
        $passed = $passed -and $observation.whole_document_decode_attempted
    } else {
        $passed = $passed -and $observation.rejection -ceq $Vector.rejection
        if ($null -ne $Vector.maximum_retained_bytes) { $passed = $passed -and $observation.retained_bytes -le $Vector.maximum_retained_bytes }
        if ($null -ne $Vector.whole_document_decode_allowed) { $passed = $passed -and $observation.whole_document_decode_attempted -eq $Vector.whole_document_decode_allowed }
        if ($null -ne $Vector.expected_text_units) { $passed = $passed -and $observation.text_units -eq $Vector.expected_text_units }
        if ($Vector.id -ceq 'FILE_EMPTY_JSON_REJECT') { $passed = $passed -and $observation.whole_document_decode_attempted }
    }
    return [pscustomobject]@{
        id = [string]$Vector.id; accepted = [bool]$observation.accepted; rejection = $observation.rejection
        position = [long]$observation.position; actual_position = $actualPosition; retained_bytes = [long]$observation.retained_bytes
        text_units = if ($null -eq $observation.text_units) { $null } else { [long]$observation.text_units }
        whole_document_decode_attempted = [bool]$observation.whole_document_decode_attempted
        sha256 = $observation.sha256; prefix_b64 = $observation.prefix_b64
        passed = [bool]$passed
    }
}
function Test-ReaderControl {
    param([object]$Control, [object]$Vector)
    if (-not (Test-ReaderVectorShape $Control)) { return $false }
    $id = Get-DirectJsonPropertyValue $Control 'id'
    $passed = Get-DirectJsonPropertyValue $Control 'passed'
    $accepted = Get-DirectJsonPropertyValue $Control 'accepted'
    $position = Get-DirectJsonPropertyValue $Control 'position'
    $actualPosition = Get-DirectJsonPropertyValue $Control 'actual_position'
    $retainedBytes = Get-DirectJsonPropertyValue $Control 'retained_bytes'
    $textUnits = Get-DirectJsonPropertyValue $Control 'text_units'
    $decodeAttempted = Get-DirectJsonPropertyValue $Control 'whole_document_decode_attempted'
    $rejection = Get-DirectJsonPropertyValue $Control 'rejection'
    $sha = Get-DirectJsonPropertyValue $Control 'sha256'
    $prefix = Get-DirectJsonPropertyValue $Control 'prefix_b64'
    $isInteger = { param($Value) (($Value -is [byte]) -or ($Value -is [int16]) -or ($Value -is [int32]) -or ($Value -is [int64])) }
    if ($id -isnot [string] -or $id -cne $Vector.id -or $passed -isnot [bool] -or -not $passed) { return $false }
    if ($accepted -isnot [bool] -or $accepted -ne ($Vector.expected -ceq 'ACCEPT')) { return $false }
    if (-not (& $isInteger $position) -or $position -lt 0 -or $position -ne $Vector.expected_position) { return $false }
    if (-not (& $isInteger $actualPosition) -or $actualPosition -lt 0 -or $actualPosition -ne $Vector.expected_position) { return $false }
    if (-not (& $isInteger $retainedBytes) -or $retainedBytes -lt 0 -or $decodeAttempted -isnot [bool]) { return $false }
    if ($sha -isnot [string] -or $sha -cnotmatch '^[0-9a-f]{64}$' -or $prefix -isnot [string] -or $prefix.Length -gt 44) { return $false }
    if ($Control.accepted) {
        if (-not $decodeAttempted -or $retainedBytes -ne $Vector.expected_retained_bytes -or -not (& $isInteger $textUnits) -or $textUnits -lt 0 -or $textUnits -ne $Vector.expected_text_units -or $rejection -is [System.Array] -or $null -ne $rejection) { return $false }
    } else {
        if ($rejection -isnot [string] -or $rejection -cne $Vector.rejection) { return $false }
        if ($null -ne $Vector.maximum_retained_bytes -and $retainedBytes -gt $Vector.maximum_retained_bytes) { return $false }
        if ($null -ne $Vector.whole_document_decode_allowed -and $decodeAttempted -ne $Vector.whole_document_decode_allowed) { return $false }
        if ($null -ne $Vector.expected_text_units -and (-not (& $isInteger $textUnits) -or $textUnits -lt 0 -or $textUnits -ne $Vector.expected_text_units)) { return $false }
        if ($Vector.id -ceq 'FILE_EMPTY_JSON_REJECT' -and (-not $decodeAttempted -or -not (& $isInteger $textUnits) -or $textUnits -ne 0)) { return $false }
        if ($Vector.id -cne 'FILE_EMPTY_JSON_REJECT' -and ($textUnits -is [System.Array] -or $null -ne $textUnits)) { return $false }
    }
    return $true
}
function Test-ReaderControlSet {
    param([object[]]$Controls, [object[]]$Vectors)
    if ($Controls.Count -ne $Vectors.Count) { return $false }
    for ($index = 0; $index -lt $Vectors.Count; $index++) {
        if (-not (Test-ReaderControl $Controls[$index] $Vectors[$index])) { return $false }
    }
    return $true
}
function Test-ReaderDocumentSets {
    param([object]$PowerShellEnvelope, [object]$PythonEnvelope)
    if (-not (Test-ReaderEnvelope $PowerShellEnvelope) -or -not (Test-ReaderEnvelope $PythonEnvelope)) { return $false }
    $PowerShellDocuments = $PowerShellEnvelope.documents
    $PythonDocuments = $PythonEnvelope.documents
    $ids = @('integration-freeze.json', 'evidence/sro-qualification-case-contract.json')
    if ($PowerShellDocuments.Count -ne 2 -or $PythonDocuments.Count -ne 2) { return $false }
    $isInteger = { param($Value) (($Value -is [byte]) -or ($Value -is [int16]) -or ($Value -is [int32]) -or ($Value -is [int64])) }
    for ($index = 0; $index -lt 2; $index++) {
        $left = $PowerShellDocuments[$index]
        $right = $PythonDocuments[$index]
        foreach ($control in @($left, $right)) {
            if (-not (Test-ReaderDocumentShape $control)) { return $false }
            $id = Get-DirectJsonPropertyValue $control 'id'
            $accepted = Get-DirectJsonPropertyValue $control 'accepted'
            $rejection = Get-DirectJsonPropertyValue $control 'rejection'
            $decoded = Get-DirectJsonPropertyValue $control 'whole_document_decode_attempted'
            $sha = Get-DirectJsonPropertyValue $control 'sha256'
            $prefix = Get-DirectJsonPropertyValue $control 'prefix_b64'
            if ($id -isnot [string] -or $id -cne $ids[$index] -or $accepted -isnot [bool] -or -not $accepted -or $rejection -is [System.Array] -or $null -ne $rejection) { return $false }
            if ($decoded -isnot [bool] -or -not $decoded) { return $false }
            foreach ($name in @('position', 'actual_position', 'retained_bytes', 'text_units')) {
                $value = Get-DirectJsonPropertyValue $control $name
                if (-not (& $isInteger $value) -or $value -lt 0 -or $value -gt $maximumFileBytes) { return $false }
            }
            if ($control.position -ne $control.actual_position -or $control.position -ne $control.retained_bytes) { return $false }
            if ($sha -isnot [string] -or $sha -cnotmatch '^[0-9a-f]{64}$') { return $false }
            if ($prefix -isnot [string] -or $prefix.Length -gt 44) { return $false }
        }
        if ($left.position -ne $right.position -or $left.retained_bytes -ne $right.retained_bytes -or $left.text_units -ne $right.text_units -or $left.sha256 -cne $right.sha256 -or $left.prefix_b64 -cne $right.prefix_b64) { return $false }
    }
    return ($PowerShellDocuments[1].sha256 -ceq $requiredDescriptorSha256)
}
function Get-PreflightStringPinValues {
    param([object]$Freeze)
    $preflight = Get-DirectJsonPropertyValue $Freeze 'recovery_preflight'
    $sourceFiles = Get-DirectJsonPropertyValue $preflight 'source_files'
    $python = Get-DirectJsonPropertyValue $Freeze 'python'
    $values = [ordered]@{}
    $values.Add('recovery_preflight.status', (Get-DirectJsonPropertyValue $preflight 'status'))
    $values.Add('recovery_preflight.path', (Get-DirectJsonPropertyValue $preflight 'path'))
    $values.Add('recovery_preflight.source_sha256', (Get-DirectJsonPropertyValue $preflight 'source_sha256'))
    $values.Add('recovery_preflight.host_path', (Get-DirectJsonPropertyValue $preflight 'host_path'))
    $values.Add('recovery_preflight.host_sha256', (Get-DirectJsonPropertyValue $preflight 'host_sha256'))
    $values.Add('recovery_preflight.ps_version', (Get-DirectJsonPropertyValue $preflight 'ps_version'))
    $values.Add('recovery_preflight.wsl_path', (Get-DirectJsonPropertyValue $preflight 'wsl_path'))
    $values.Add('recovery_preflight.wsl_sha256', (Get-DirectJsonPropertyValue $preflight 'wsl_sha256'))
    $values.Add('python.path', (Get-DirectJsonPropertyValue $python 'path'))
    $values.Add('python.resolved', (Get-DirectJsonPropertyValue $python 'resolved'))
    $values.Add('python.sha256', (Get-DirectJsonPropertyValue $python 'sha256'))
    $values.Add('recovery_preflight.source_files.service/gdb.py', (Get-DirectJsonPropertyValue $sourceFiles 'service/gdb.py'))
    $values.Add('recovery_preflight.source_files.service/server.py', (Get-DirectJsonPropertyValue $sourceFiles 'service/server.py'))
    $values.Add('recovery_preflight.source_files.stop-q.py', (Get-DirectJsonPropertyValue $sourceFiles 'stop-q.py'))
    $values.Add('recovery_preflight.source_files.run-integration-q.ps1', (Get-DirectJsonPropertyValue $sourceFiles 'run-integration-q.ps1'))
    $values.Add('recovery_preflight.source_files.evidence/sro-q-first-failure-20261020/executed-host.ps1.txt', (Get-DirectJsonPropertyValue $sourceFiles 'evidence/sro-q-first-failure-20261020/executed-host.ps1.txt'))
    return $values
}
function Test-PreflightTimestamp {
    param($Record, [string]$Expected)
    return ($Record.started_utc -is [string] -and $Record.started_utc -ceq $Expected)
}
function Require-Preflight {
    param([string]$Id, [bool]$Condition, [string]$FailureMessage)
    if ($Id -ceq 'FSA_PREFLIGHT_STRING_PINS') {
        $rows.Add([pscustomobject]@{ id = $Id; passed = $Condition; pin_controls = @($preflightScalarPinControls.ToArray()) })
        $script:preflightPinRowAdded = $true
    } else {
        $rows.Add([pscustomobject]@{ id = $Id; passed = $Condition })
    }
    if (-not $Condition) {
        if (-not [string]::IsNullOrEmpty($FailureMessage)) { throw $FailureMessage }
        throw ('Preflight failed: ' + $Id)
    }
    if ($clock.ElapsedMilliseconds -ge ($maximumMs - 1000)) { throw 'Preflight work deadline reached' }
}
try {
    $claimPath = Join-Path $root 'evidence/admission-r2-preflight.claim'
    $claimStream = New-Object System.IO.FileStream($claimPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    $claimCreated = $true
    try {
        $claimBytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes('SRO-P admission-r2 one invocation; retained on failure')
        $claimStream.Write($claimBytes, 0, $claimBytes.Length)
        $claimStream.Flush($true)
    } finally { $claimStream.Dispose() }
    $freezeRead = Read-BoundedUtf8File (Join-Path $root 'integration-freeze.json')
    $powershellDocumentReads += Get-ReaderSummary 'integration-freeze.json' $freezeRead
    if (-not $freezeRead.accepted) { throw ('Bounded manifest read rejected: ' + $freezeRead.rejection) }
    $freeze = ConvertFrom-Json -InputObject $freezeRead.text
    $admission = Get-DirectJsonPropertyValue $freeze 'file_scalar_admission_r2'
    $descriptorPathValue = Get-DirectJsonPropertyValue $admission 'descriptor_path'
    $descriptorHashValue = Get-DirectJsonPropertyValue $admission 'descriptor_sha256'
    if (-not (Test-ScalarString $descriptorPathValue) -or -not (Test-ScalarString $descriptorHashValue) -or $descriptorPathValue -cne $requiredDescriptorPath -or $descriptorHashValue -cne $requiredDescriptorSha256) {
        throw 'Frozen file-scalar descriptor identity is not the approved scalar pin'
    }
    $descriptorRead = Read-BoundedUtf8File (Join-Path $root $descriptorPathValue)
    $powershellDocumentReads += Get-ReaderSummary $descriptorPathValue $descriptorRead
    if (-not $descriptorRead.accepted) { throw ('Bounded descriptor read rejected: ' + $descriptorRead.rejection) }
    if ($descriptorRead.sha256 -cne $descriptorHashValue) { throw 'Frozen file-scalar descriptor hash mismatch' }
    $descriptorRoot = ConvertFrom-Json -InputObject $descriptorRead.text
    $descriptorRootSchema = Get-DirectJsonPropertyValue $descriptorRoot 'schema'
    $descriptorRuntimeAuthorized = Get-DirectJsonPropertyValue $descriptorRoot 'runtime_authorized'
    $descriptorNativeEvidence = Get-DirectJsonPropertyValue $descriptorRoot 'native_evidence'
    if (-not (Test-ScalarString $descriptorRootSchema) -or $descriptorRootSchema -cne 'ladybug.feat010.sro.case-contract.v1' -or $descriptorRuntimeAuthorized -isnot [bool] -or $descriptorRuntimeAuthorized -or $descriptorNativeEvidence -isnot [bool] -or $descriptorNativeEvidence) {
        throw 'Frozen SRO case-contract root identity or authority mismatch'
    }
    $descriptor = Get-DirectJsonPropertyValue $descriptorRoot 'file_scalar_admission_r2'
    $expectedDescriptorSchema = 'ladybug.feat010.file-scalar-admission-r2.expectations.v1'
    $expectedPreflightStringPaths = @(
        'recovery_preflight.status', 'recovery_preflight.path', 'recovery_preflight.source_sha256',
        'recovery_preflight.host_path', 'recovery_preflight.host_sha256', 'recovery_preflight.ps_version',
        'recovery_preflight.wsl_path', 'recovery_preflight.wsl_sha256', 'python.path', 'python.resolved',
        'python.sha256', 'recovery_preflight.source_files.service/gdb.py',
        'recovery_preflight.source_files.service/server.py', 'recovery_preflight.source_files.stop-q.py',
        'recovery_preflight.source_files.run-integration-q.ps1',
        'recovery_preflight.source_files.evidence/sro-q-first-failure-20261020/executed-host.ps1.txt'
    )
    $expectedFsaRows = @('FSA_FILE_EXACT_CAP', 'FSA_FILE_OVER_CAP_STOP', 'FSA_FILE_UTF8_SPLIT_BOM', 'FSA_FILE_UTF8_INVALID', 'FSA_FILE_EMPTY_JSON_REJECT', 'FSA_PREFLIGHT_STRING_PINS')
    $expectedVectorIds = @('FILE_EXACT_CAP', 'FILE_OVER_CAP_STOP', 'FILE_UTF8_SPLIT_BOM', 'FILE_UTF8_INVALID', 'FILE_EMPTY_JSON_REJECT')
    $readerVectors = @($descriptor.file_vectors)
    $descriptorPaths = @($descriptor.preflight_string_paths)
    $descriptorRows = @($descriptor.preflight_rows)
    $descriptorVectorIds = @($readerVectors | ForEach-Object { $_.id })
    $descriptorShapePassed = (
        (Test-ScalarString $descriptor.schema) -and $descriptor.schema -ceq $expectedDescriptorSchema -and
        $descriptor.maximum_bytes -eq $maximumFileBytes -and $descriptor.maximum_utf16_units -eq $maximumFileUnits -and $descriptor.chunk_maximum_bytes -eq $fileChunkBytes -and
        $readerVectors.Count -eq 5 -and ($descriptorVectorIds -join '|') -ceq ($expectedVectorIds -join '|') -and
        ($descriptorPaths -join '|') -ceq ($expectedPreflightStringPaths -join '|') -and
        ($descriptorRows -join '|') -ceq ($expectedFsaRows -join '|')
    )
    if (-not $descriptorShapePassed) { throw 'Frozen file-scalar descriptor shape mismatch' }
    $pinValues = Get-PreflightStringPinValues $freeze
    if ($pinValues.Count -ne 16 -or $descriptorPaths.Count -ne 16) { Require-Preflight 'FSA_PREFLIGHT_STRING_PINS' $false }
    foreach ($pinPath in $descriptorPaths) {
        $hasPinValue = $pinValues.Contains($pinPath)
        $pinValue = if ($hasPinValue) { $pinValues[$pinPath] } else { $null }
        $baselineIsString = ($hasPinValue -and (Test-ScalarString $pinValue))
        $pinControl = [pscustomobject]@{
            path = [string]$pinPath; baseline_is_string = [bool]$baselineIsString
            matching_array_attempted = $false; matching_array_is_string = $null
            matching_array_rejected = $null; passed = $false
        }
        [void]$preflightScalarPinControls.Add($pinControl)
        if (-not $baselineIsString) {
            Require-Preflight 'FSA_PREFLIGHT_STRING_PINS' $false ('Preflight scalar pin is not a direct string: ' + $pinPath)
        }
    }
    $expected = Get-DirectJsonPropertyValue $freeze 'recovery_preflight'
    $dispatchAuthorized = Get-DirectJsonPropertyValue $expected 'dispatch_authorized'
    $qualificationDispatchAuthorized = Get-DirectJsonPropertyValue $freeze 'qualification_dispatch_authorized'
    $runtimeReady = Get-DirectJsonPropertyValue $freeze 'runtime_ready'
    $runtimeAttemptsAuthorized = Get-DirectJsonPropertyValue $freeze 'runtime_attempts_authorized'
    $installationAuthorized = Get-DirectJsonPropertyValue $freeze 'installation_authorized'
    Require-Preflight 'approved-freeze-present' ((Test-ScalarString $expected.status) -and $expected.status -ceq 'SOURCE_REVIEWED_READY' -and $dispatchAuthorized -is [bool] -and $dispatchAuthorized -and $qualificationDispatchAuthorized -is [bool] -and -not $qualificationDispatchAuthorized -and $runtimeReady -is [bool] -and -not $runtimeReady -and ($runtimeAttemptsAuthorized -is [int] -or $runtimeAttemptsAuthorized -is [long]) -and $runtimeAttemptsAuthorized -eq 0 -and $installationAuthorized -is [bool] -and -not $installationAuthorized)
    Require-Preflight 'invocation-path' ([System.IO.Path]::GetFullPath($PSCommandPath) -ieq [System.IO.Path]::GetFullPath((Join-Path $root $expected.path)))
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
    $preflightScalarPinsPassed = $true
    foreach ($pinControl in $preflightScalarPinControls) {
        $pinValue = $pinValues[$pinControl.path]
        $oneElementArray = New-Object object[] 1
        $oneElementArray[0] = $pinValue
        $arrayIsString = Test-ScalarString $oneElementArray
        $pinControl.matching_array_attempted = $true
        $pinControl.matching_array_is_string = [bool]$arrayIsString
        $pinControl.matching_array_rejected = -not $arrayIsString
        $pinControl.passed = ($pinControl.baseline_is_string -and $pinControl.matching_array_rejected)
        if (-not $pinControl.passed) {
            $preflightScalarPinsPassed = $false
            Require-Preflight 'FSA_PREFLIGHT_STRING_PINS' $false ('Matching array was not rejected for preflight scalar pin: ' + $pinControl.path)
        }
    }
    foreach ($vector in $readerVectors) {
        try {
            $control = Test-ReaderVector $vector
        } catch {
            $vectorId = [string]$vector.id
            $control = [pscustomobject]@{
                id = $vectorId; accepted = $false; rejection = 'VECTOR_EXCEPTION'
                position = $null; actual_position = $null; retained_bytes = $null; text_units = $null
                whole_document_decode_attempted = $false; sha256 = $null; prefix_b64 = $null; passed = $false
            }
            [void]$powershellReaderControls.Add($control)
            $rows.Add([pscustomobject]@{ id = ('FSA_' + $vectorId); passed = $false })
            throw ('PowerShell reader vector threw for ' + $vectorId + ': ' + $_.Exception.Message)
        }
        [void]$powershellReaderControls.Add($control)
        if (-not $control.passed) {
            $rows.Add([pscustomobject]@{ id = ('FSA_' + $vector.id); passed = $false })
            throw ('PowerShell reader vector failed: ' + $vector.id)
        }
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
import base64, hashlib, io, json, pathlib, sys, time
MAX_FILE_BYTES = 16777216
MAX_FILE_UNITS = 16777216
CHUNK_MAX_BYTES = 4096
PYTHON_WORK_BUDGET_MS = 0
DESCRIPTOR_PATH = 'evidence/sro-qualification-case-contract.json'
DESCRIPTOR_SHA256 = '493ffe9524977bb07376f55ef521a4d5e691539be5b7624f6194bab2d36043c0'
root = pathlib.Path('/mnt/e/projects/ladybug/repro/feat010-menu-clock-repair-20261018/controller-integration-20261019')
rows = []
file_reader_controls = {'documents': [], 'vectors': []}

class RepeatByteReader:
    def __init__(self, count, value):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError('invalid repeated-byte input count')
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError('invalid repeated-byte input value')
        self.remaining = count
        self.position = 0
        self.value = bytes((value,))

    def read(self, count):
        amount = min(count, self.remaining)
        self.remaining -= amount
        self.position += amount
        return self.value * amount

    def tell(self):
        return self.position

def bounded_utf8_read(stream):
    retained = bytearray()
    position = 0
    read_failure = None
    while True:
        if time.monotonic() >= work_deadline:
            read_failure = 'READ_DEADLINE'
            break
        request = min(CHUNK_MAX_BYTES, MAX_FILE_BYTES - position + 1)
        try:
            chunk = stream.read(request)
        except BaseException:
            read_failure = 'READ_ERROR'
            break
        if not isinstance(chunk, (bytes, bytearray)):
            read_failure = 'READ_ERROR'
            break
        if not chunk:
            break
        keep = min(len(chunk), MAX_FILE_BYTES - position)
        if keep:
            retained.extend(chunk[:keep])
            position += keep
        if len(chunk) > keep:
            position += 1
            digest = hashlib.sha256(retained).hexdigest()
            prefix_b64 = base64.b64encode(retained[:32]).decode('ascii')
            return {'accepted': False, 'rejection': 'BYTE_LIMIT_BEFORE_DECODE', 'position': position,
                    'retained_bytes': len(retained), 'text': None, 'text_units': None,
                    'whole_document_decode_attempted': False, 'sha256': digest, 'prefix_b64': prefix_b64}
    digest = hashlib.sha256(retained).hexdigest()
    prefix_b64 = base64.b64encode(retained[:32]).decode('ascii')
    if read_failure is not None:
        return {'accepted': False, 'rejection': read_failure, 'position': position,
                'retained_bytes': len(retained), 'text': None, 'text_units': None,
                'whole_document_decode_attempted': False, 'sha256': digest, 'prefix_b64': prefix_b64}
    try:
        text = retained.decode('utf-8-sig', errors='strict')
    except UnicodeDecodeError:
        return {'accepted': False, 'rejection': 'STRICT_UTF8', 'position': position,
                'retained_bytes': len(retained), 'text': None, 'text_units': None,
                'whole_document_decode_attempted': True, 'sha256': digest, 'prefix_b64': prefix_b64}
    text_units = sum(2 if ord(character) > 0xffff else 1 for character in text)
    if text_units > MAX_FILE_UNITS:
        return {'accepted': False, 'rejection': 'UTF16_UNIT_LIMIT', 'position': position,
                'retained_bytes': len(retained), 'text': None, 'text_units': text_units,
                'whole_document_decode_attempted': True, 'sha256': digest, 'prefix_b64': prefix_b64}
    if not text:
        return {'accepted': False, 'rejection': 'EMPTY_JSON_OBJECT', 'position': position,
                'retained_bytes': len(retained), 'text': '', 'text_units': 0,
                'whole_document_decode_attempted': True, 'sha256': digest, 'prefix_b64': prefix_b64}
    return {'accepted': True, 'rejection': None, 'position': position,
            'retained_bytes': len(retained), 'text': text, 'text_units': text_units,
            'whole_document_decode_attempted': True, 'sha256': digest, 'prefix_b64': prefix_b64}

def bounded_file(path, reader_id):
    try:
        with path.open('rb') as stream:
            result = bounded_utf8_read(stream)
            try:
                actual_position = stream.tell()
            except BaseException:
                actual_position = result['position']
    except OSError:
        result = {'accepted': False, 'rejection': 'OPEN_ERROR', 'position': 0,
                  'retained_bytes': 0, 'text': None, 'text_units': None,
                  'whole_document_decode_attempted': False,
                  'sha256': hashlib.sha256(b'').hexdigest(), 'prefix_b64': ''}
        actual_position = 0
    file_reader_controls['documents'].append({
        'id': reader_id, 'accepted': result['accepted'], 'rejection': result['rejection'],
        'position': result['position'], 'actual_position': actual_position,
        'retained_bytes': result['retained_bytes'], 'text_units': result['text_units'],
        'whole_document_decode_attempted': result['whole_document_decode_attempted'],
        'sha256': result['sha256'], 'prefix_b64': result['prefix_b64']})
    if not result['accepted']:
        raise ValueError('bounded JSON file rejected: ' + str(result['rejection']))
    return result

def scalar_string(owner, key, label):
    if not isinstance(owner, dict):
        raise ValueError(label + ' owner is not an object')
    value = owner.get(key)
    if not isinstance(value, str):
        raise ValueError(label + ' is not a scalar string')
    return value

def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label + ' is not an integer')
    return value

def reader_vector(vector):
    if not isinstance(vector, dict):
        raise ValueError('file-reader vector is not an object')
    kind = scalar_string(vector, 'input_kind', 'vector.input_kind')
    if kind == 'repeat_byte':
        stream = RepeatByteReader(integer(vector.get('input_count'), 'input_count'), integer(vector.get('input_byte'), 'input_byte'))
    elif kind == 'bom_repeat_suffix':
        prefix = bytes(integer(value, 'prefix byte') for value in vector.get('prefix_bytes', []))
        repeat_count = integer(vector.get('repeat_count'), 'repeat_count')
        repeat_byte = integer(vector.get('repeat_byte'), 'repeat_byte')
        suffix = bytes(integer(value, 'suffix byte') for value in vector.get('suffix_bytes', []))
        stream = io.BytesIO(prefix + bytes((repeat_byte,)) * repeat_count + suffix)
    elif kind == 'literal_bytes':
        stream = io.BytesIO(bytes(integer(value, 'literal byte') for value in vector.get('input_bytes', [])))
    else:
        raise ValueError('unsupported file-reader vector input kind')
    observed = bounded_utf8_read(stream)
    actual_position = stream.tell()
    expected = scalar_string(vector, 'expected', 'vector.expected')
    expected_position = integer(vector.get('expected_position'), 'expected_position')
    passed = observed['accepted'] == (expected == 'ACCEPT') and observed['position'] == expected_position and actual_position == expected_position
    if expected == 'ACCEPT':
        passed = passed and observed['retained_bytes'] == integer(vector.get('expected_retained_bytes'), 'expected_retained_bytes')
        passed = passed and observed['text_units'] == integer(vector.get('expected_text_units'), 'expected_text_units')
        text_kind = scalar_string(vector, 'expected_text', 'expected_text')
        if text_kind == 'ASCII_A_REPEAT':
            passed = passed and len(observed['text']) == observed['text_units'] and observed['text'].count('A') == len(observed['text'])
        elif text_kind == 'ASCII_A_4092_THEN_U00E9_Z':
            count = integer(vector.get('repeat_count'), 'repeat_count')
            passed = passed and observed['text'] == ('A' * count + '\u00e9Z')
        else:
            passed = False
        passed = passed and observed['whole_document_decode_attempted']
    else:
        rejection = scalar_string(vector, 'rejection', 'vector.rejection')
        passed = passed and observed['rejection'] == rejection
        if 'maximum_retained_bytes' in vector:
            passed = passed and observed['retained_bytes'] <= integer(vector['maximum_retained_bytes'], 'maximum_retained_bytes')
        if 'whole_document_decode_allowed' in vector:
            passed = passed and observed['whole_document_decode_attempted'] is vector['whole_document_decode_allowed']
        elif vector.get('id') == 'FILE_EMPTY_JSON_REJECT':
            passed = passed and observed['whole_document_decode_attempted'] is True and observed['text_units'] == 0
    return {'id': scalar_string(vector, 'id', 'vector.id'), 'accepted': observed['accepted'],
            'rejection': observed['rejection'], 'position': observed['position'], 'actual_position': actual_position,
            'retained_bytes': observed['retained_bytes'], 'text_units': observed['text_units'],
            'whole_document_decode_attempted': observed['whole_document_decode_attempted'],
            'sha256': observed['sha256'], 'prefix_b64': observed['prefix_b64'], 'passed': bool(passed)}

try:
    work_deadline = time.monotonic() + (PYTHON_WORK_BUDGET_MS / 1000.0)
    freeze_read = bounded_file(root / 'integration-freeze.json', 'integration-freeze.json')
    freeze = json.loads(freeze_read['text'])
    if not isinstance(freeze, dict):
        raise ValueError('freeze root is not an object')
    admission = freeze.get('file_scalar_admission_r2')
    descriptor_path = scalar_string(admission, 'descriptor_path', 'descriptor_path')
    descriptor_sha256 = scalar_string(admission, 'descriptor_sha256', 'descriptor_sha256')
    if descriptor_path != DESCRIPTOR_PATH or descriptor_sha256 != DESCRIPTOR_SHA256:
        raise ValueError('frozen descriptor identity mismatch')
    descriptor_read = bounded_file(root / descriptor_path, descriptor_path)
    if descriptor_read['sha256'] != descriptor_sha256:
        raise ValueError('descriptor hash mismatch')
    descriptor_root = json.loads(descriptor_read['text'])
    if not isinstance(descriptor_root, dict) or scalar_string(descriptor_root, 'schema', 'descriptor root schema') != 'ladybug.feat010.sro.case-contract.v1' or descriptor_root.get('runtime_authorized') is not False or descriptor_root.get('native_evidence') is not False:
        raise ValueError('frozen SRO case-contract root identity or authority mismatch')
    descriptor = descriptor_root.get('file_scalar_admission_r2')
    if not isinstance(descriptor, dict) or scalar_string(descriptor, 'schema', 'descriptor.schema') != 'ladybug.feat010.file-scalar-admission-r2.expectations.v1':
        raise ValueError('descriptor schema mismatch')
    if integer(descriptor.get('maximum_bytes'), 'maximum_bytes') != MAX_FILE_BYTES or integer(descriptor.get('maximum_utf16_units'), 'maximum_utf16_units') != MAX_FILE_UNITS or integer(descriptor.get('chunk_maximum_bytes'), 'chunk_maximum_bytes') != CHUNK_MAX_BYTES:
        raise ValueError('descriptor reader bounds mismatch')
    vectors = descriptor.get('file_vectors')
    if not isinstance(vectors, list) or [scalar_string(item, 'id', 'vector.id') for item in vectors] != ['FILE_EXACT_CAP', 'FILE_OVER_CAP_STOP', 'FILE_UTF8_SPLIT_BOM', 'FILE_UTF8_INVALID', 'FILE_EMPTY_JSON_REJECT']:
        raise ValueError('descriptor vector set mismatch')
    expected = freeze.get('recovery_preflight')
    if not isinstance(expected, dict) or scalar_string(expected, 'status', 'recovery_preflight.status') != 'SOURCE_REVIEWED_READY' or expected.get('dispatch_authorized') is not True:
        raise ValueError('preflight freeze is not execution-authorized')
    if freeze.get('qualification_dispatch_authorized') is not False or freeze.get('runtime_ready') is not False or freeze.get('runtime_attempts_authorized') != 0 or freeze.get('installation_authorized') is not False:
        raise ValueError('qualification, runtime, or installation authority is unexpectedly enabled')
    source_pins = expected.get('source_files')
    if not isinstance(source_pins, dict):
        raise ValueError('source_files is not an object')
    executable = pathlib.Path(sys.executable).resolve()
    python_pins = freeze.get('python')
    python_resolved = scalar_string(python_pins, 'resolved', 'python.resolved')
    python_hash = scalar_string(python_pins, 'sha256', 'python.sha256')
    if str(executable) != python_resolved or hashlib.sha256(executable.read_bytes()).hexdigest() != python_hash:
        raise ValueError('pinned compiler identity mismatch')
    sources = {}
    for relative in ('service/gdb.py', 'service/server.py', 'stop-q.py'):
        if (root / relative).stat().st_size > 262144:
            raise ValueError('compile input exceeds fixed cap: ' + relative)
        source = (root / relative).read_bytes()
        pinned_hash = scalar_string(source_pins, relative, 'source_files.' + relative)
        if len(source) > 262144 or hashlib.sha256(source).hexdigest() != pinned_hash:
            raise ValueError('compile input cap/hash mismatch: ' + relative)
        sources[relative] = source
    for vector in vectors:
        try:
            control = reader_vector(vector)
        except BaseException as exc:
            vector_id = vector.get('id') if isinstance(vector, dict) and isinstance(vector.get('id'), str) else 'VECTOR_EXCEPTION'
            control = {'id': vector_id, 'accepted': False, 'rejection': 'VECTOR_EXCEPTION',
                       'position': None, 'actual_position': None, 'retained_bytes': None, 'text_units': None,
                       'whole_document_decode_attempted': False, 'sha256': None, 'prefix_b64': None, 'passed': False}
            file_reader_controls['vectors'].append(control)
            raise ValueError('file-reader vector threw for ' + vector_id + ': ' + str(exc)[:512]) from exc
        file_reader_controls['vectors'].append(control)
        if not control['passed']:
            raise ValueError('file-reader vector failed: ' + control['id'] + ' (' + str(control['rejection']) + ')')
    for relative, source in sources.items():
        if time.monotonic() >= work_deadline:
            raise TimeoutError('compile-only work deadline reached')
        compile(source, relative, 'exec', dont_inherit=True)
        rows.append({'id': relative, 'compiled_only': True})
    try:
        compile('def broken(:\n', '<independent-malformed-negative>', 'exec')
    except SyntaxError:
        rows.append({'id': 'malformed-python-rejected', 'passed': True})
    else:
        raise ValueError('independent malformed Python was accepted')
    print(json.dumps({'kind': 'SRO_P_COMPILE_ONLY', 'rows': rows, 'file_reader_controls': file_reader_controls}, separators=(',', ':')))
except BaseException as exc:
    print(json.dumps({'kind': 'SRO_P_COMPILE_FAILURE', 'rows': rows, 'file_reader_controls': file_reader_controls, 'error_type': type(exc).__name__, 'error': str(exc)[:2048]}, separators=(',', ':')))
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
    $pythonWorkBudgetMs = [int]($maximumMs - 1000 - $clock.ElapsedMilliseconds)
    if ($pythonWorkBudgetMs -le 0) { throw 'Python work budget exhausted after compiler start' }
    $pythonBudgetSource = 'PYTHON_WORK_BUDGET_MS = 0'
    if ($pythonBody.IndexOf($pythonBudgetSource, [System.StringComparison]::Ordinal) -lt 0 -or $pythonBody.IndexOf($pythonBudgetSource, [System.StringComparison]::Ordinal) -ne $pythonBody.LastIndexOf($pythonBudgetSource, [System.StringComparison]::Ordinal)) {
        throw 'Embedded Python work-budget placeholder is missing or ambiguous'
    }
    $pythonBody = $pythonBody.Replace($pythonBudgetSource, ('PYTHON_WORK_BUDGET_MS = ' + $pythonWorkBudgetMs))
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
    $pythonControlsValue = Get-DirectJsonPropertyValue $compilerResult 'file_reader_controls'
    $pythonDocumentsValue = Get-DirectJsonPropertyValue $pythonControlsValue 'documents'
    $pythonVectorsValue = Get-DirectJsonPropertyValue $pythonControlsValue 'vectors'
    if ($pythonDocumentsValue -is [System.Array]) { $pythonDocumentReads = $pythonDocumentsValue }
    if ($pythonVectorsValue -is [System.Array]) { $pythonReaderControls = $pythonVectorsValue }
    $pythonEnvelopeShapePassed = Test-ReaderEnvelope $pythonControlsValue
    if ($compilerResult.kind -ceq 'SRO_P_COMPILE_FAILURE') {
        $failureRows = Get-DirectJsonPropertyValue $compilerResult 'rows'
        $failureType = Get-DirectJsonPropertyValue $compilerResult 'error_type'
        $failureText = Get-DirectJsonPropertyValue $compilerResult 'error'
        $failureControlsShapePassed = $pythonEnvelopeShapePassed
        if ($failureControlsShapePassed) {
            foreach ($documentControl in $pythonDocumentReads) {
                if (-not (Test-ReaderDocumentShape $documentControl)) { $failureControlsShapePassed = $false; break }
            }
        }
        if ($failureControlsShapePassed) {
            foreach ($vectorControl in $pythonReaderControls) {
                if (-not (Test-ReaderVectorShape $vectorControl)) { $failureControlsShapePassed = $false; break }
            }
        }
        $failureSchemaPassed = ($failureType -is [string] -and $failureText -is [string] -and $failureRows -is [System.Array] -and $failureRows.Count -le 3 -and $failureControlsShapePassed)
        $rows.Add([pscustomobject]@{ id = 'compiler-failure-schema'; passed = [bool]$failureSchemaPassed })
        $failureDescription = 'Embedded Python compiler failure (' + [string]$failureType + '): ' + ([string]$failureText).Substring(0, [Math]::Min(512, ([string]$failureText).Length))
        if (-not $failureSchemaPassed) { throw ($failureDescription + '; failure envelope schema invalid') }
        throw $failureDescription
    }
    Require-Preflight 'compiler-exit-zero' ($childExitCode -eq 0)
    $compilerRowsValue = Get-DirectJsonPropertyValue $compilerResult 'rows'
    Require-Preflight 'compiler-result-shape' ($compilerResult.kind -ceq 'SRO_P_COMPILE_ONLY' -and $compilerRowsValue -is [System.Array] -and $compilerRowsValue.Count -eq 4 -and $pythonEnvelopeShapePassed -and $pythonDocumentReads.Count -eq 2 -and $pythonReaderControls.Count -eq 5 -and $powershellReaderControls.Count -eq 5)
    for ($index = 0; $index -lt $expectedVectorIds.Count; $index++) {
        $powershellControl = $powershellReaderControls[$index]
        $pythonControl = if ($index -lt $pythonReaderControls.Count) { $pythonReaderControls[$index] } else { $null }
        $controlPasses = (Test-ReaderControl $powershellControl $readerVectors[$index]) -and (Test-ReaderControl $pythonControl $readerVectors[$index])
        Require-Preflight ('FSA_' + $expectedVectorIds[$index]) $controlPasses
    }
    $powershellReaderEnvelope = [pscustomobject]@{ documents = @($powershellDocumentReads); vectors = @($powershellReaderControls.ToArray()) }
    $documentControlsPassed = Test-ReaderDocumentSets $powershellReaderEnvelope $pythonControlsValue
    Require-Preflight 'FSA_PREFLIGHT_STRING_PINS' ($preflightScalarPinsPassed -and $documentControlsPassed)
    for ($index = 0; $index -lt 3; $index++) {
        Require-Preflight ('compiler-result-row-' + $index) ($compilerResult.rows[$index].id -ceq $requiredPaths[$index] -and $compilerResult.rows[$index].compiled_only -eq $true)
    }
    Require-Preflight 'compiler-negative-row' ($compilerResult.rows[3].id -ceq 'malformed-python-rejected' -and $compilerResult.rows[3].passed -eq $true)
} catch {
    $failure = $_.Exception.Message
    if ($claimCreated -and -not $script:preflightPinRowAdded) {
        $rows.Add([pscustomobject]@{ id = 'FSA_PREFLIGHT_STRING_PINS'; passed = $false; pin_controls = @($preflightScalarPinControls.ToArray()) })
        $script:preflightPinRowAdded = $true
    }
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
$powershellReaderEnvelope = [pscustomobject]@{ documents = @($powershellDocumentReads); vectors = @($powershellReaderControls.ToArray()) }
$embeddedPythonEnvelope = Get-DirectJsonPropertyValue $compilerResult 'file_reader_controls'
if ($null -eq $embeddedPythonEnvelope) { $embeddedPythonEnvelope = [pscustomobject]@{ documents = @(); vectors = @() } }
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
    file_reader_controls = [ordered]@{
        powershell = $powershellReaderEnvelope
        embedded_python = $embeddedPythonEnvelope
    }
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
