# get-agent.ps1 — Download and install the Atomic Chat client agent (Windows)
#
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/eric-merritt/agentic_w_langchain_ollama/main/get-agent.ps1 | iex
#
# Or with a custom directory:
#   $env:AGENT_DIR="C:\my-agent"; irm https://raw.githubusercontent.com/eric-merritt/agentic_w_langchain_ollama/main/get-agent.ps1 | iex

$ErrorActionPreference = "Stop"

$BaseUrl = "https://raw.githubusercontent.com/eric-merritt/agentic_w_langchain_ollama/main"
$Files = @("client_agent.py", "install_client.ps1")

$InstallDir = if ($env:AGENT_DIR) { $env:AGENT_DIR } else { Join-Path (Get-Location) "agent-client" }

function Info($msg) { Write-Host "[+] $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "[x] $msg" -ForegroundColor Red; exit 1 }

Write-Host "Atomic Chat - Client Agent Installer" -ForegroundColor White
Write-Host "======================================"
Write-Host ""

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

foreach ($file in $Files) {
    Info "Downloading $file..."
    $url = "$BaseUrl/$file"
    $dest = Join-Path $InstallDir $file
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    } catch {
        Fail "Failed to download $file from $url"
    }
}

Info "Running installer..."
Write-Host ""
Set-Location $InstallDir
& powershell -ExecutionPolicy Bypass -File ".\install_client.ps1"
