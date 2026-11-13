param([int]$FrontendPort=3000, [int]$BackendPort=8000, [string]$DataDir='')
$ErrorActionPreference='Stop'
$repoRoot=$PSScriptRoot
$cache=Join-Path $repoRoot '.cache'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
foreach($port in @($FrontendPort,$BackendPort)) {
    if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port is busy. Stop the previous frontend/backend first." }
}
$python=Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'
if(!(Test-Path -LiteralPath $python)) { $python=Join-Path (Split-Path $repoRoot -Parent) 'backend/.venv/Scripts/python.exe' }
if(!(Test-Path -LiteralPath $python)) { throw 'Create backend/.venv and install backend/requirements.lock.txt first.' }
$next=Join-Path $repoRoot 'frontend/node_modules/next/dist/bin/next'
if(!(Test-Path -LiteralPath $next)) { throw 'Run npm ci in frontend first.' }
$envFile=Join-Path $repoRoot '.env'
if(!(Test-Path -LiteralPath $envFile)) {
    $bytes=New-Object byte[] 32
    $rng=[System.Security.Cryptography.RandomNumberGenerator]::Create();$rng.GetBytes($bytes);$rng.Dispose()
    $secret=[BitConverter]::ToString($bytes).Replace('-','').ToLower()
    [IO.File]::WriteAllText($envFile,"JWT_SECRET=$secret`nOLLAMA_CHAT_MODEL=qwen3:4b`nOLLAMA_EMBED_MODEL=nomic-embed-text`n")
}
$allowed=@('JWT_SECRET','OLLAMA_BASE_URL','OLLAMA_CHAT_MODEL','OLLAMA_EMBED_MODEL','RAG_QUERY_EXPANSION','LLM_BASE_URL','LLM_API_KEY','LLM_MODEL')
foreach($line in Get-Content -LiteralPath $envFile) {
    if($line -match '^([A-Z_]+)=(.*)$' -and $allowed -contains $Matches[1]) {
        [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2].Trim().Trim('"').Trim("'"),'Process')
    }
}
if(!$env:JWT_SECRET) { throw 'Set JWT_SECRET in .env.' }
if(!$DataDir) { $DataDir=Join-Path $repoRoot 'backend/data' }
$env:DATA_DIR=[IO.Path]::GetFullPath($DataDir)
$env:QDRANT_URL='http://127.0.0.1:6335'
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:$BackendPort"
$env:CORS_ORIGINS="http://127.0.0.1:$FrontendPort,http://localhost:$FrontendPort"
Push-Location $repoRoot
try {
    & docker compose up -d qdrant
    if($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop, then run this script again.' }
} finally { Pop-Location }
$backend=Start-Process -FilePath $python -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort" -WorkingDirectory (Join-Path $repoRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $cache 'backend.log') -RedirectStandardError (Join-Path $cache 'backend-error.log') -PassThru
try {
    $frontend=Start-Process -FilePath (Get-Command node).Source -ArgumentList "`"$next`" dev --hostname 127.0.0.1 --port $FrontendPort" -WorkingDirectory (Join-Path $repoRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $cache 'frontend.log') -RedirectStandardError (Join-Path $cache 'frontend-error.log') -PassThru
} catch { Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue; throw }
@($backend,$frontend) | ForEach-Object { @{pid=$_.Id;start_ticks=$_.StartTime.ToUniversalTime().Ticks} } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $cache 'local-runtime.json')
Write-Output "PSB Docs: http://127.0.0.1:$FrontendPort/knowledge"
Write-Output 'Stop: .\stop-local.ps1 (frontend, backend and project Qdrant).'
