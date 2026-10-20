param(
    [ValidateSet('Outer', 'Child')]
    [string]$Context,
    [ValidateRange(512, 8192)]
    [int]$MaximumBytes = 8192
)

$ErrorActionPreference = 'Stop'

if (-not $PSBoundParameters.ContainsKey('Context')) { throw 'Context is required.' }
if ($Context -cne 'Outer' -and $Context -cne 'Child') { throw 'Context must be exactly Outer or Child.' }
$diagnosticSourcePath = [System.IO.Path]::GetFullPath($PSCommandPath)

$contextSchema = 'ladybug.feat010.fsa-e.context.v1'
$missingCommandName = 'LADYBUG_FSA_MISSING_COMMAND_20261020'
$stdoutMarker = 'FSA_E_CHILD_STDOUT_20261020'
$stderrMarker = 'FSA_E_CHILD_STDERR_20261020'
$errorTextMaximumCharacters = 512

function Get-OptionalPropertyValue {
    param([AllowNull()][object]$Object, [string]$Name)
    if ($null -eq $Object) { return ,$null }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return ,$null }
    return ,$property.Value
}

function Convert-MetadataValueToString {
    param([AllowNull()][object]$Value, [string]$Label)
    if ($null -eq $Value) { return ,$null }
    if ($Value -is [string]) { return ,$Value }
    if ($Value -is [System.Version] -or $Value.GetType().IsEnum) { return ,$Value.ToString() }
    throw ('Unexpected metadata type for ' + $Label + ': ' + $Value.GetType().FullName)
}

function Get-Sha256WithDotNet {
    param([string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $digest = $hasher.ComputeHash($stream)
        return ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
    } finally {
        $hasher.Dispose()
        $stream.Dispose()
    }
}

function New-CommandMetadata {
    param([string]$Name, [AllowNull()][object]$CommandInfo)
    if ($null -eq $CommandInfo) {
        return [pscustomobject][ordered]@{
            name = $Name
            command_type = $null
            source = $null
            module_name = $null
            module_version = $null
            module_path = $null
            script_file = $null
        }
    }

    $module = Get-OptionalPropertyValue $CommandInfo 'Module'
    $moduleVersion = Get-OptionalPropertyValue $CommandInfo 'Version'
    $modulePath = Get-OptionalPropertyValue $module 'Path'
    $scriptBlock = Get-OptionalPropertyValue $CommandInfo 'ScriptBlock'
    $scriptFile = Get-OptionalPropertyValue $scriptBlock 'File'
    if ($null -eq $scriptFile -and $CommandInfo.CommandType.ToString() -ceq 'ExternalScript') {
        $scriptFile = Get-OptionalPropertyValue $CommandInfo 'Path'
    }

    return [pscustomobject][ordered]@{
        name = $Name
        command_type = Convert-MetadataValueToString $CommandInfo.CommandType 'command_type'
        source = Convert-MetadataValueToString (Get-OptionalPropertyValue $CommandInfo 'Source') 'source'
        module_name = Convert-MetadataValueToString (Get-OptionalPropertyValue $CommandInfo 'ModuleName') 'module_name'
        module_version = Convert-MetadataValueToString $moduleVersion 'module_version'
        module_path = Convert-MetadataValueToString $modulePath 'module_path'
        script_file = Convert-MetadataValueToString $scriptFile 'script_file'
    }
}

function New-BoundedErrorObservation {
    param([AllowNull()][string]$Message)
    if ($null -eq $Message) { $Message = 'The command failed without an exception message.' }
    $truncated = ($Message.Length -gt $errorTextMaximumCharacters)
    if ($truncated) { $Message = $Message.Substring(0, $errorTextMaximumCharacters) }
    return [pscustomobject]@{ text = $Message; truncated = [bool]$truncated }
}

function New-HashCommandObservation {
    param([string]$ImagePath)
    $success = $false
    $sha256 = $null
    $errorMessage = $null

    try {
        $hashResults = @(Get-FileHash -LiteralPath $ImagePath -Algorithm SHA256 -ErrorAction Stop)
        if ($hashResults.Count -ne 1) {
            $errorMessage = 'Get-FileHash returned an unexpected result count.'
        } else {
            $observedHash = Get-OptionalPropertyValue $hashResults[0] 'Hash'
            if ($observedHash -is [string] -and $observedHash -cmatch '^[0-9a-fA-F]{64}$') {
                $sha256 = $observedHash.ToLowerInvariant()
                $success = $true
            } else {
                $errorMessage = 'Get-FileHash did not return a scalar 64-character SHA-256 value.'
            }
        }
    } catch {
        $errorMessage = $_.Exception.Message
    }

    $errorObservation = if ($null -eq $errorMessage) { $null } else { New-BoundedErrorObservation $errorMessage }
    return [pscustomobject][ordered]@{
        attempted = $true
        success = [bool]$success
        sha256 = $sha256
        error = if ($null -eq $errorObservation) { $null } else { $errorObservation.text }
        error_truncated = if ($null -eq $errorObservation) { $false } else { [bool]$errorObservation.truncated }
    }
}

function New-FsaContext {
    param([string]$ContextName, [string]$SourcePath, [bool]$MarkerWriteCallsCompleted)

    $process = [System.Diagnostics.Process]::GetCurrentProcess()
    try {
        $imagePath = [System.IO.Path]::GetFullPath($process.MainModule.FileName)
    } finally {
        $process.Dispose()
    }

    # Invoke the actual unqualified hash command before recording its imported provenance.
    $hashCommand = New-HashCommandObservation $imagePath
    $hashCandidates = @(Get-Command -Name 'Get-FileHash' -All -ListImported -ErrorAction SilentlyContinue)
    $commandMetadata = New-Object System.Collections.Generic.List[object]
    foreach ($hashCandidate in $hashCandidates) {
        [void]$commandMetadata.Add((New-CommandMetadata 'Get-FileHash' $hashCandidate))
    }
    $commands = @($commandMetadata.ToArray())

    $sourcePath = [System.IO.Path]::GetFullPath($SourcePath)
    $sourceSha256 = Get-Sha256WithDotNet $sourcePath
    $powerShellVersion = $PSVersionTable.PSVersion.ToString()

    $negativeCandidates = @(Get-Command -Name $missingCommandName -All -ListImported -ErrorAction SilentlyContinue)
    $negativeCommandAvailable = ($negativeCandidates.Count -gt 0)

    $autoloadVariable = $ExecutionContext.SessionState.PSVariable.Get('PSModuleAutoLoadingPreference')
    $autoloadIsSet = ($null -ne $autoloadVariable)
    $autoloadValue = $null
    if ($autoloadIsSet) {
        $autoloadValue = Convert-MetadataValueToString $autoloadVariable.Value 'PSModuleAutoLoadingPreference'
    }

    $modulePath = $env:PSModulePath
    if ($null -ne $modulePath -and $modulePath -isnot [string]) {
        throw 'PSModulePath has a non-string value that the approved schema cannot represent.'
    }

    $utilityModules = New-Object System.Collections.Generic.List[object]
    $availableUtilityModules = @(Get-Module -ListAvailable -Name 'Microsoft.PowerShell.Utility' -ErrorAction Stop)
    foreach ($moduleInfo in $availableUtilityModules) {
        [void]$utilityModules.Add([pscustomobject][ordered]@{
            name = Convert-MetadataValueToString (Get-OptionalPropertyValue $moduleInfo 'Name') 'utility.name'
            version = Convert-MetadataValueToString (Get-OptionalPropertyValue $moduleInfo 'Version') 'utility.version'
            path = Convert-MetadataValueToString (Get-OptionalPropertyValue $moduleInfo 'Path') 'utility.path'
            module_base = Convert-MetadataValueToString (Get-OptionalPropertyValue $moduleInfo 'ModuleBase') 'utility.module_base'
        })
    }

    return [pscustomobject][ordered]@{
        schema = $contextSchema
        context = $ContextName
        source_path = $sourcePath
        source_sha256 = $sourceSha256
        powershell_path = $imagePath
        powershell_version = $powerShellVersion
        ps_module_path = $modulePath
        autoload_preference = [pscustomobject][ordered]@{
            is_set = [bool]$autoloadIsSet
            value = $autoloadValue
        }
        hash_command = $hashCommand
        commands = $commands
        negative_command_available = [bool]$negativeCommandAvailable
        utility_modules = @($utilityModules.ToArray())
        marker_write_calls_completed = [bool]$MarkerWriteCallsCompleted
    }
}

$markerWriteCallsCompleted = $false
if ($Context -ceq 'Child') {
    [Console]::Out.WriteLine($stdoutMarker)
    [Console]::Out.Flush()
    [Console]::Error.WriteLine($stderrMarker)
    [Console]::Error.Flush()
    $markerWriteCallsCompleted = $true
}

$contextObject = New-FsaContext $Context $diagnosticSourcePath $markerWriteCallsCompleted
if ($Context -ceq 'Outer') { return $contextObject }

$json = ConvertTo-Json -InputObject $contextObject -Depth 8 -Compress
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
$bytes = $utf8.GetBytes($json + [Environment]::NewLine)
if ($bytes.Length -gt $MaximumBytes) {
    throw ('Diagnostic receipt exceeds the supplied byte budget: ' + $bytes.Length + ' > ' + $MaximumBytes)
}

$resultPath = Join-Path $PSScriptRoot 'fsa-command-environment-result.json'
$receipt = New-Object System.IO.FileStream($resultPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
try {
    $receipt.Write($bytes, 0, $bytes.Length)
    $receipt.Flush($true)
} finally {
    $receipt.Dispose()
}
