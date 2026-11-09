param(
    [ValidateSet('Tool019Q1','Tool019ManualDown','ActorAB01Runtime')][string]$Operation,
    [string]$EvidenceRoot,
    [switch]$ReadinessConfirmed
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-Tool019HostState {
    param([bool]$NeedsReadiness=$false,[bool]$ReadyConfirmed=$false,[bool]$RootExists=$false)
    return @{ ready=$false; go_sent=$false; owned_work_started=$false; wsl_started=$false;
        children_exited=$false; receipt=$false; exit_code=$null; result_class=$null;
        reason=$null; complete=$false; actions=@(); go_ms=$null; last_ms=0;
        needs_readiness=$NeedsReadiness; readiness_confirmed=$ReadyConfirmed; root_exists=$RootExists;
        unrelated_processes_touched=$false; original_files_unchanged=$true; retry_count=0;
        deadline_extended=$false; receipt_required=$true; owned_children_alive=$false }
}

function Update-Tool019Host {
    param([hashtable]$State,[object]$Event)
    $now=[double]$Event.ms; $kind=[string]$Event.event
    if($now -lt $State.last_ms){throw 'Non-monotonic host event'}
    $State.last_ms=$now; $State.actions=@()
    if($State.complete){return}
    switch($kind){
        'admission' {
            if($State.root_exists){$State.result_class='harness_failure';$State.reason='evidence_root_exists';$State.complete=$true}
            elseif($State.needs_readiness -and -not $State.readiness_confirmed){$State.result_class='incomplete';$State.reason='readiness_not_confirmed';$State.complete=$true}
        }
        'dispatch' {$State.wsl_started=$true}
        'ready' {
            if($now -ge 10000 -or $null -ne $State.result_class){$State.result_class='timeout';$State.reason='startup_admission_deadline';$State.actions=@('cancel')}
            else {$State.ready=$true;$State.actions=@('go')}
        }
        'go' {
            if(-not $State.ready -or $now -ge 10000 -or $null -ne $State.result_class){$State.result_class='timeout';$State.actions=@('cancel')}
            else {$State.go_sent=$true;$State.go_ms=$now}
        }
        'native_work_start' {
            if(-not $State.go_sent){$State.result_class='harness_failure';$State.reason='work_before_go';$State.actions=@('cancel')}
            else {$State.owned_work_started=$true;$State.owned_children_alive=$true}
        }
        'native_work_exit' {
            $State.exit_code=[int]$Event.code
            if($State.exit_code -ne 0 -and $null -eq $State.result_class){$State.result_class='command_failed'}
        }
        'owned_children_exited' {$State.children_exited=$true;$State.owned_children_alive=$false}
        'native_receipt' {$State.receipt=$true}
        'startup_admission_deadline' {
            if(-not $State.go_sent){$State.result_class='timeout';$State.reason='startup_admission_deadline';$State.actions=@('cancel')}
        }
        'native_work_deadline' {
            if(-not $State.children_exited){$State.result_class='timeout';$State.reason='native_work_deadline';$State.actions=@('cancel')}
        }
        'control_eof' {if($null -eq $State.result_class){$State.result_class='cancelled'};$State.actions=@('cancel')}
        'owned_bridge_exited' {
            if(-not $State.owned_work_started){
                if($null -eq $State.result_class){$State.result_class='harness_failure';$State.reason='bridge_exit_before_ready'}
                $State.complete=$true
            }
        }
        'receipt_missing' {
            if(-not $State.receipt){$State.result_class='incomplete';$State.reason='missing_native_receipt';$State.complete=$true;$State.actions=@('cancel')}
        }
        'host_finalization' {
            $State.actions=@('cancel')
            if($State.children_exited -and -not $State.receipt){$State.result_class='incomplete';$State.reason='missing_native_receipt';$State.complete=$true}
        }
        'owned_exit_unconfirmed' {$State.result_class='cleanup_failure';$State.complete=$true;$State.actions=@('cancel')}
        'host_deadline' {
            $State.actions=@('cancel')
            if($State.owned_work_started -and -not $State.children_exited){$State.result_class='cleanup_failure'}
            elseif(-not $State.receipt -and $State.owned_work_started){$State.result_class='incomplete';$State.reason='missing_native_receipt'}
            elseif($null -eq $State.result_class){$State.result_class='timeout'}
            $State.complete=$true
        }
    }
    if($State.receipt -and $State.children_exited -and ($null -ne $State.exit_code -or $null -ne $State.result_class)){
        if($null -eq $State.result_class){$State.result_class='passed'}
        $State.complete=$true
    }
}

function Invoke-Tool019HostFixtures {
    param([string]$FixturePath)
    $definitions=Get-Content -LiteralPath $FixturePath -Raw -Encoding UTF8 | ConvertFrom-Json
    $rows=@()
    foreach($case in $definitions.host_cases){
        $need=($case.PSObject.Properties.Name -contains 'operation' -and $case.operation -eq 'Tool019ManualDown')
        $confirmed= -not ($case.PSObject.Properties.Name -contains 'readiness_confirmed' -and -not $case.readiness_confirmed)
        $exists=($case.PSObject.Properties.Name -contains 'evidence_root_exists' -and $case.evidence_root_exists)
        $state=New-Tool019HostState $need $confirmed $exists
        # Same event transition function as real dispatch; clock/process events are fake.
        Update-Tool019Host $state ([pscustomobject]@{ms=0;event='admission'})
        foreach($event in $case.events){Update-Tool019Host $state $event}
        $rows+=@{id=$case.id;actual=$state}
    }
    return ($rows | ConvertTo-Json -Depth 12 -Compress)
}

function Write-Tool019JsonNew {
    param([string]$Path,[object]$Value)
    $text=($Value | ConvertTo-Json -Depth 30 -Compress)+"`n"
    $bytes=(New-Object System.Text.UTF8Encoding($false)).GetBytes($text)
    $stream=[System.IO.File]::Open($Path,[System.IO.FileMode]::CreateNew,[System.IO.FileAccess]::Write,[System.IO.FileShare]::Read)
    try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}finally{$stream.Dispose()}
}

function Invoke-Tool019Host {
    param([string]$Operation,[string]$EvidenceRoot,[bool]$ReadinessConfirmed)
    $clock=[System.Diagnostics.Stopwatch]::StartNew()
    $project=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
    $root=[System.IO.Path]::GetFullPath($EvidenceRoot).TrimEnd([char]92)
    $admittedPrefix=(Join-Path $project 'repro')+[char]92
    if(-not $root.StartsWith($admittedPrefix,[System.StringComparison]::OrdinalIgnoreCase) -or $root.Contains('"') -or $root.Contains("`n") -or $root.Contains("`r")){throw 'Evidence root must be a new directory under E project repro'}
    $state=New-Tool019HostState ($Operation -eq 'Tool019ManualDown') $ReadinessConfirmed (Test-Path -LiteralPath $root)
    Update-Tool019Host $state ([pscustomobject]@{ms=$clock.Elapsed.TotalMilliseconds;event='admission'})
    if($state.complete){return $state}
    $null=[System.IO.Directory]::CreateDirectory($root)
    $relative=$root.Substring($project.Length+1).Replace([char]92,[char]47)
    $linuxRoot='/mnt/e/projects/ladybug/'+$relative
    $bridgeArguments=@('-e','python3','-B','/mnt/e/projects/ladybug/scripts/engineering/dispatch_wsl.py','--operation',$Operation,'--evidence',$linuxRoot)
    $info=New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName='wsl.exe';$info.Arguments=($bridgeArguments | ForEach-Object {if($_ -match '\s'){'"'+$_+'"'}else{$_}}) -join ' '
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $process=New-Object System.Diagnostics.Process;$process.StartInfo=$info
    $events=New-Object System.Collections.ArrayList
    $closed=$false;$startupExpired=$false;$workExpired=$false;$finalizing=$false
    $errorTask=$null;$lineTask=$null
    try{
        Write-Tool019JsonNew (Join-Path $root 'host-request.json') @{operation=$Operation;arguments=$bridgeArguments;readiness_confirmed=$ReadinessConfirmed;maximum_seconds=60}
        if(-not $process.Start()){throw 'WSL process did not start'}
        Update-Tool019Host $state ([pscustomobject]@{ms=$clock.Elapsed.TotalMilliseconds;event='dispatch'})
        $lineTask=$process.StandardOutput.ReadLineAsync();$errorTask=$process.StandardError.ReadToEndAsync()
        while(-not $state.complete){
            $now=$clock.Elapsed.TotalMilliseconds
            $incoming=@()
            if($lineTask -and $lineTask.IsCompleted){
                $line=$lineTask.GetAwaiter().GetResult()
                if($null -ne $line){
                    $record=$line | ConvertFrom-Json
                    $event=@{ms=$now;event=[string]$record.event}
                    if($record.PSObject.Properties.Name -contains 'code'){$event.code=[int]$record.code}
                    $incoming+= [pscustomobject]$event
                    $lineTask=$process.StandardOutput.ReadLineAsync()
                }else{$lineTask=$null;$incoming+=[pscustomobject]@{ms=$now;event='owned_bridge_exited'}}
            }
            if(-not $state.go_sent -and $now -ge 10000 -and -not $startupExpired){$startupExpired=$true;$incoming+=[pscustomobject]@{ms=$now;event='startup_admission_deadline'}}
            if($state.go_sent -and $now -ge $state.go_ms+40000 -and -not $state.children_exited -and -not $workExpired){$workExpired=$true;$incoming+=[pscustomobject]@{ms=$now;event='native_work_deadline'}}
            $nativeFinish=55000
            if($null -ne $state.go_ms){$nativeFinish=[Math]::Min(55000,$state.go_ms+45000)}
            if($now -ge $nativeFinish -and -not $finalizing){$finalizing=$true;$incoming+=[pscustomobject]@{ms=$now;event='host_finalization'}}
            if($now -ge 59800){$incoming+=[pscustomobject]@{ms=$now;event='host_deadline'}}
            foreach($event in $incoming){
                $null=$events.Add($event);Update-Tool019Host $state $event
                if($state.actions -contains 'go'){
                    $process.StandardInput.WriteLine('GO');$process.StandardInput.Flush()
                    $go=[pscustomobject]@{ms=$clock.Elapsed.TotalMilliseconds;event='go'}
                    $null=$events.Add($go);Update-Tool019Host $state $go
                }
                if($state.actions -contains 'cancel' -and -not $closed){$process.StandardInput.Close();$closed=$true}
            }
            if($finalizing -and -not $process.HasExited){$process.Kill()}
            if(-not $state.complete){Start-Sleep -Milliseconds 5}
        }
    }catch{
        $state.result_class='harness_failure';$state.reason=$_.Exception.Message
    }finally{
        if(-not $closed){try{$process.StandardInput.Close()}catch{}}
        try{
            if(-not $process.HasExited){
                $wait=[Math]::Max(0,[Math]::Min(300,59900-$clock.Elapsed.TotalMilliseconds))
                if(-not $process.WaitForExit([int]$wait)){$process.Kill()}
            }
        }catch{}
        $state.elapsed_seconds=[Math]::Round($clock.Elapsed.TotalSeconds,4)
        $state.events=@($events.ToArray())
        $state.operation=$Operation
        if($errorTask -and $errorTask.IsCompleted){$state.stderr=$errorTask.GetAwaiter().GetResult()}
        $state.native_receipt_path=Join-Path $root 'native-receipt.json'
        if(Test-Path -LiteralPath $state.native_receipt_path){$state.native_result=Get-Content -LiteralPath $state.native_receipt_path -Raw -Encoding UTF8 | ConvertFrom-Json}
        if($state.elapsed_seconds -gt 60 -and $state.result_class -eq 'passed'){$state.result_class='timeout';$state.reason='host_deadline'}
        Write-Tool019JsonNew (Join-Path $root 'host-receipt.json') $state
        $process.Dispose()
    }
    return $state
}

# Dot sourcing exposes the same transition engine to offline Q1 without dispatch.
if($MyInvocation.InvocationName -eq '.'){return}
if(-not $Operation -or -not $EvidenceRoot){throw 'Specify fixed Operation and new EvidenceRoot'}
$result=Invoke-Tool019Host $Operation $EvidenceRoot ([bool]$ReadinessConfirmed)
$result | ConvertTo-Json -Depth 30
if($result.result_class -ne 'passed'){exit 1}
