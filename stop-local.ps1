$ErrorActionPreference='Stop'
$state=Join-Path $PSScriptRoot '.cache/local-runtime.json'
if(Test-Path -LiteralPath $state) {
    $roots=Get-Content -LiteralPath $state -Raw | ConvertFrom-Json
    $processes=Get-CimInstance Win32_Process
    function Get-OwnedTree([int]$RootId) {
        foreach($child in @($processes | Where-Object ParentProcessId -eq $RootId)) { Get-OwnedTree $child.ProcessId }
        $RootId
    }
    foreach($record in $roots) {
        $process=Get-Process -Id $record.pid -ErrorAction SilentlyContinue
        # PID может быть переиспользован: время старта защищает чужие процессы.
        if($process -and $process.StartTime.ToUniversalTime().Ticks -eq $record.start_ticks) {
            foreach($ownedId in @(Get-OwnedTree $process.Id)) { Stop-Process -Id $ownedId -Force -ErrorAction SilentlyContinue }
        }
    }
    Remove-Item -LiteralPath $state
}
Push-Location $PSScriptRoot
try {
    if(!$env:JWT_SECRET) { $env:JWT_SECRET='unused-stop-command' }
    & docker compose stop qdrant
    if($LASTEXITCODE -ne 0) { Write-Warning 'Could not stop Qdrant. Check Docker Desktop.' }
} finally { Pop-Location }
Write-Output 'Project frontend/backend processes stopped; data volumes preserved.'
