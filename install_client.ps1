# install_client.ps1 — Set up the client agent for agent.eric-merritt.com (Windows)
#
# Usage:
#   git clone <repo-url> && cd <repo>
#   .\install_client.ps1
#
# After install, run:
#   .\agent.bat                              # interactive chat
#   .\agent.bat -m "list files in ~/code"    # one-shot
#   .\agent.bat --allow-writes -m "fix it"   # enable write tools

$ErrorActionPreference = 'Stop'

function Info($msg)  { Write-Host "[+] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Fail($msg)  { Write-Host "[x] $msg" -ForegroundColor Red; exit 1 }

Write-Host 'Agent Client Installer' -ForegroundColor White
Write-Host '======================================'
Write-Host ''

# ── 1. Check Python ──────────────────────────────────────────────────────────
Info 'Checking Python...'

$python = $null
$pyCheck = 'import sys; print(str(sys.version_info.major) + "." + str(sys.version_info.minor))'
foreach ($cmd in @('python3', 'python', 'py')) {
    try {
        $ver = & $cmd -c $pyCheck 2>$null
        if ($ver) {
            $parts = $ver.Split('.')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) {
                $python = $cmd
                break
            }
        }
    } catch {}
}

if (-not $python) {
    Warn 'Python >= 3.12 not found.'
    $answer = Read-Host 'Do you want to install Python 3.12? (Y/N)'
    if ($answer -match '^[Yy]') {
        Info 'Downloading Python 3.12 installer...'
        $installerUrl = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
        $installerPath = Join-Path $env:TEMP 'python-3.12-installer.exe'
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing

        Info 'Running Python installer...'
        Warn 'The installer will run — Python will be added to PATH automatically.'
        $argList = @('/passive', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1')
        Start-Process -FilePath $installerPath -ArgumentList $argList -Wait

        Remove-Item $installerPath -ErrorAction SilentlyContinue

        # Refresh PATH so we can find the new install
        $userPath = [System.Environment]::GetEnvironmentVariable('Path', [System.EnvironmentVariableTarget]::User)
        $machPath = [System.Environment]::GetEnvironmentVariable('Path', [System.EnvironmentVariableTarget]::Machine)
        $env:Path = $userPath + ';' + $machPath

        # Re-check for Python
        foreach ($cmd in @('python3', 'python', 'py')) {
            try {
                $ver = & $cmd -c $pyCheck 2>$null
                if ($ver) {
                    $parts = $ver.Split('.')
                    if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) {
                        $python = $cmd
                        break
                    }
                }
            } catch {}
        }

        if (-not $python) {
            Fail 'Python still not found after install. Please close and reopen PowerShell, then run this script again.'
        }

        Info 'Python installed successfully!'
    } else {
        Fail 'Python >= 3.12 is required. Install from https://www.python.org/downloads/'
    }
}

$pyVersion = & $python --version 2>&1
Info "Using $python ($pyVersion)"

# ── 2. Create venv ───────────────────────────────────────────────────────────
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
$venvDir = Join-Path $scriptDir '.client-venv'

if (Test-Path $venvDir) {
    Warn 'Virtual environment already exists at .client-venv'
} else {
    Info 'Creating virtual environment...'
    & $python -m venv $venvDir
}

$pythonExe = Join-Path $venvDir 'Scripts\python.exe'

Info 'Installing dependencies...'
& $pythonExe -m pip install --quiet --upgrade pip
& $pythonExe -m pip install --quiet websockets

# ── 3. API key ───────────────────────────────────────────────────────────────
$envFile = Join-Path $scriptDir '.env.client'

if (Test-Path $envFile) {
    Warn 'Config file .env.client already exists - skipping key setup'
    Warn 'Edit .env.client to change your key'
} else {
    Write-Host ''
    Write-Host 'API Key Setup' -ForegroundColor White
    Write-Host 'You need an external API key for agent.eric-merritt.com.'
    Write-Host 'Contact the server admin to get one.'
    Write-Host ''
    $apiKey = Read-Host 'Paste your API key (or press Enter to skip for now)'

    if ($apiKey) {
        $envContent = 'AGENT_API_KEY=' + $apiKey + "`n" + 'AGENT_SERVER=wss://agent.eric-merritt.com/api/chat/ws'
        Set-Content -Path $envFile -Value $envContent -Encoding UTF8
        Info 'Saved to .env.client'
    } else {
        $envContent = 'AGENT_API_KEY=YOUR_KEY_HERE' + "`n" + 'AGENT_SERVER=wss://agent.eric-merritt.com/api/chat/ws'
        Set-Content -Path $envFile -Value $envContent -Encoding UTF8
        Warn 'Placeholder saved to .env.client - edit it before running'
    }
}

# ── 4. Create wrapper batch file ─────────────────────────────────────────────
$wrapper = Join-Path $scriptDir 'agent.bat'

$batContent = @'
@echo off
REM Convenience wrapper for client_agent.py
setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
if exist "%SCRIPT_DIR%.env.client" (
    for /f "usebackq tokens=1,* delims==" %%A in ("%SCRIPT_DIR%.env.client") do set "%%A=%%B"
)
"%SCRIPT_DIR%.client-venv\Scripts\python.exe" "%SCRIPT_DIR%client_agent.py" %*
'@

Set-Content -Path $wrapper -Value $batContent -Encoding ASCII
Info 'Created agent.bat wrapper'

# ── 5. Add to .gitignore ────────────────────────────────────────────────────
$gitignore = Join-Path $scriptDir '.gitignore'
$patterns = @('.client-venv', '.env.client')

foreach ($pattern in $patterns) {
    $found = $false
    if (Test-Path $gitignore) {
        $found = (Get-Content $gitignore -ErrorAction SilentlyContinue) -contains $pattern
    }
    if (-not $found) {
        Add-Content -Path $gitignore -Value $pattern
    }
}

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '=====================================' -ForegroundColor Green
Write-Host '  Installation complete!' -ForegroundColor Green
Write-Host '=====================================' -ForegroundColor Green
Write-Host ''
Write-Host 'Quick start:'
Write-Host '  .\agent.bat                                  # interactive chat'
Write-Host '  .\agent.bat -m "list files in ~/projects"    # one-shot'
Write-Host '  .\agent.bat --allow-writes -m "fix main.py"  # enable writes'
Write-Host ''
Write-Host 'Configuration:  .env.client'
Write-Host '  AGENT_API_KEY  - your API key'
Write-Host '  AGENT_SERVER   - server URL (default: wss://agent.eric-merritt.com/api/chat/ws)'
Write-Host ''

if (Test-Path $envFile) {
    $content = Get-Content $envFile -Raw
    if ($content -match 'YOUR_KEY_HERE') {
        Warn 'Do not forget to set your API key in .env.client!'
    }
}
