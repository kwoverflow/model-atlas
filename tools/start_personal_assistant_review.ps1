param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [int]$BackendPort = 18000,
    [int]$FrontendPort = 3000,
    [string]$DraftStrategy = $env:PERSONAL_ASSISTANT_DRAFT_STRATEGY,
    [string]$FrontendDistDir = '.next',
    [switch]$BackendOnly
)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($DraftStrategy)) { $DraftStrategy = 'assistant-release-v1' }
$repo = Split-Path -Parent $PSScriptRoot
$base = (Resolve-Path -LiteralPath $Workspace).Path
if (!(Test-Path -LiteralPath $base -PathType Container)) {
    throw 'Initialize a dedicated review workspace first.'
}
$ports = @($BackendPort)
if (!$BackendOnly) { $ports += $FrontendPort }
foreach ($port in $ports) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is in use. Specify another port; existing processes will not be stopped."
    }
}
$python = Join-Path $repo '.venv/Scripts/python.exe'
$logs = Join-Path $base 'server-logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$env:PERSONAL_ASSISTANT_WORKSPACE = $base
$env:PERSONAL_ASSISTANT_RUNTIME_URL = 'http://127.0.0.1:11435'
$env:PERSONAL_ASSISTANT_DRAFT_STRATEGY = $DraftStrategy
$env:NEXT_DIST_DIR = $FrontendDistDir
$env:BACKEND_CORS_ORIGINS = "http://localhost:$FrontendPort"
$env:NEXT_PUBLIC_API_URL = "http://localhost:$BackendPort/api/v1"
$env:SERVER_API_URL = $env:NEXT_PUBLIC_API_URL
$backend = Start-Process -FilePath $python -ArgumentList @(
    '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
    '--host', '127.0.0.1', '--port', "$BackendPort"
) -WorkingDirectory $repo -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs 'backend.out.log') `
    -RedirectStandardError (Join-Path $logs 'backend.err.log')
$frontend = $null
if (!$BackendOnly) {
$node = (Get-Command node.exe).Source
$frontend = Start-Process -FilePath $node -ArgumentList @(
    'node_modules/next/dist/bin/next', 'dev', '--hostname', '127.0.0.1', '--port', "$FrontendPort"
) -WorkingDirectory (Join-Path $repo 'frontend') -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logs 'frontend.out.log') `
    -RedirectStandardError (Join-Path $logs 'frontend.err.log')
}
$readyUrls = @("http://127.0.0.1:$BackendPort/api/v1/personal-assistant/workspace")
if (!$BackendOnly) { $readyUrls += "http://127.0.0.1:$FrontendPort/personal-assistant" }
foreach ($url in $readyUrls) {
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $url -TimeoutSec 2
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch { Start-Sleep -Seconds 1 }
    }
    if (!$ready) { throw "Server did not become ready: $url. Inspect logs in $logs." }
}
@{
    backend_pid = $backend.Id
    frontend_pid = $frontend.Id
    url = "http://localhost:$FrontendPort/personal-assistant"
    logs = $logs
    draft_strategy = $DraftStrategy
    frontend_dist_dir = $FrontendDistDir
} | ConvertTo-Json
