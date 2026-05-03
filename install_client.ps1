# install_client.ps1 — Set up Atomic Chat on Windows
#
# Path 1 — Full Local Stack: llama-server + Python backend + React frontend,
#           offline capable; writes .env and start_local.bat
# Path 2 — Cloud Client Only: lightweight agent that connects to
#           agent.eric-merritt.com; writes .env.client and agent.bat
#
# Requirements: Python >= 3.12

$ErrorActionPreference = 'Stop'

function Info($msg)  { Write-Host "[+] $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Step($msg)  { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Fail($msg)  { Write-Host "[x] $msg" -ForegroundColor Red; exit 1 }

Write-Host 'Atomic Chat Installer' -ForegroundColor White
Write-Host '====================='
Write-Host ''

$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }

# ── Python check ──────────────────────────────────────────────────────────────
Step 'Checking Python...'

$python   = $null
$pyCheck  = 'import sys; print(str(sys.version_info.major) + "." + str(sys.version_info.minor))'

foreach ($cmd in @('python3', 'python', 'py')) {
    try {
        $ver = & $cmd -c $pyCheck 2>$null
        if ($ver) {
            $parts = $ver.Split('.')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) { $python = $cmd; break }
        }
    } catch {}
}

if (-not $python) {
    $searchDirs = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        'C:\Python', 'C:\Program Files\Python',
        (Join-Path $env:USERPROFILE 'AppData\Local\Programs\Python')
    )
    foreach ($baseDir in $searchDirs) {
        if (-not (Test-Path $baseDir)) { continue }
        $candidates = Get-ChildItem -Path $baseDir -Filter 'python.exe' -Recurse -ErrorAction SilentlyContinue |
                      Where-Object { $_.FullName -notmatch 'Scripts' }
        foreach ($exe in $candidates) {
            try {
                $ver = & $exe.FullName -c $pyCheck 2>$null
                if ($ver) {
                    $parts = $ver.Split('.')
                    if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) { $python = $exe.FullName; break }
                }
            } catch {}
        }
        if ($python) { break }
    }
}

if (-not $python) {
    Warn 'Python >= 3.12 not found.'
    $answer = Read-Host 'Install Python 3.12? (Y/N)'
    if ($answer -match '^[Yy]') {
        $installerUrl  = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe'
        $installerPath = Join-Path $env:TEMP 'python-3.12-installer.exe'
        Info 'Downloading Python 3.12...'
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
        Start-Process -FilePath $installerPath `
            -ArgumentList @('/passive', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1') -Wait
        Remove-Item $installerPath -ErrorAction SilentlyContinue
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
                    [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
        foreach ($cmd in @('python', 'py')) {
            try {
                $ver = & $cmd -c $pyCheck 2>$null
                if ($ver) {
                    $parts = $ver.Split('.')
                    if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 12) { $python = $cmd; break }
                }
            } catch {}
        }
        if (-not $python) {
            $default = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
            if (Test-Path $default) { $python = $default }
        }
        if (-not $python) { Fail 'Python not found after install. Reopen PowerShell and re-run.' }
        Info 'Python installed!'
    } else {
        Fail 'Python >= 3.12 required. Install from https://www.python.org/downloads/'
    }
}

Info "Using $python ($(& $python --version 2>&1))"

# ── Shared helpers ────────────────────────────────────────────────────────────

function Find-FreePort([int]$Start, [int]$End) {
    for ($p = $Start; $p -le $End; $p++) {
        try {
            $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $p)
            $l.Start(); $l.Stop(); return $p
        } catch [System.Net.Sockets.SocketException] { continue }
    }
    return $null
}

function Find-Models {
    $dirs = @(
        (Join-Path $env:USERPROFILE 'models'),
        (Join-Path $env:USERPROFILE '.cache\llama.cpp'),
        (Join-Path $env:USERPROFILE '.cache\huggingface\hub'),
        (Join-Path $env:LOCALAPPDATA 'llama.cpp'),
        (Join-Path $env:LOCALAPPDATA 'lm-studio\models'),
        'C:\models', 'C:\AI\models'
    )
    $found = @()
    foreach ($dir in $dirs) {
        if (Test-Path $dir) {
            $found += Get-ChildItem -Path $dir -Filter '*.gguf' -Recurse -ErrorAction SilentlyContinue |
                      Select-Object -ExpandProperty FullName
        }
    }
    return $found | Sort-Object
}

function Detect-GpuBackend {
    # Returns: cuda (NVIDIA+CUDA), vulkan (AMD/Radeon/Intel Arc), cpu (fallback)
    # ROCm is Linux-only; AMD on Windows uses the Vulkan build
    $gpus = Get-WmiObject Win32_VideoController -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Name
    foreach ($gpu in $gpus) {
        if ($gpu -match 'NVIDIA') {
            $cudaRt = Get-ChildItem 'C:\Windows\System32' -Filter 'nvcuda.dll' -ErrorAction SilentlyContinue
            return if ($cudaRt) { 'cuda' } else { 'vulkan' }
        }
        if ($gpu -match 'AMD|Radeon|Intel Arc|Intel Xe') { return 'vulkan' }
    }
    return 'cpu'
}

# Downloads a GGUF from HuggingFace; returns the local path on success
function Invoke-HFDownload([string]$Repo) {
    $pyScript = @'
import urllib.request, json, sys, os
from pathlib import Path

repo = sys.argv[1]
out_dir = Path.home() / "models" / repo.split("/")[-1]
out_dir.mkdir(parents=True, exist_ok=True)

hdrs = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"} if os.environ.get("HF_TOKEN") else {}

print(f"Fetching file list from HuggingFace: {repo}")
req = urllib.request.Request(
    f"https://huggingface.co/api/models/{repo}?expand[]=siblings", headers=hdrs)
with urllib.request.urlopen(req) as r:
    data = json.load(r)

gguf_files = [s["rfilename"] for s in data.get("siblings", []) if s["rfilename"].endswith(".gguf")]
if not gguf_files:
    print("No .gguf files found in this repo.", file=sys.stderr); sys.exit(1)

print("Available GGUF files:")
for i, f in enumerate(gguf_files, 1):
    print(f"  [{i}] {f}")

choice = input(f"Select [1-{len(gguf_files)}]: ").strip()
try:
    idx = int(choice) - 1
    if not 0 <= idx < len(gguf_files): raise ValueError
except ValueError:
    print("Invalid selection.", file=sys.stderr); sys.exit(1)

filename  = gguf_files[idx]
url  = f"https://huggingface.co/{repo}/resolve/main/{filename}"
dest = out_dir / filename

if dest.exists():
    print(f"Already downloaded: {dest}")
    print(str(dest)); sys.exit(0)

print(f"Downloading {filename} to {dest}...")
req = urllib.request.Request(url, headers=hdrs)
with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
    total = int(r.headers.get("Content-Length", 0))
    done  = 0
    while True:
        buf = r.read(1 << 20)
        if not buf: break
        f.write(buf); done += len(buf)
        if total:
            print(f"\r  {done*100//total}% ({done>>20}/{total>>20} MB)", end="", flush=True)

print(f"\nDone: {dest}")
print(str(dest))
'@
    $tmp = Join-Path $env:TEMP 'hf_download_tmp.py'
    Set-Content -Path $tmp -Value $pyScript -Encoding UTF8
    $lines = & $python $tmp $Repo
    Remove-Item $tmp -ErrorAction SilentlyContinue
    # last line is the path
    return ($lines | Select-Object -Last 1)
}

# ── Mode selection ────────────────────────────────────────────────────────────
Write-Host ''
Write-Host 'Choose install mode:' -ForegroundColor White
Write-Host '  [1] Full Local Stack  - your own LLM + backend + frontend (offline capable)'
Write-Host '  [2] Cloud Client Only - agent connects to agent.eric-merritt.com'
Write-Host ''
$mode = Read-Host 'Mode [1/2]'

# ══════════════════════════════════════════════════════════════════════════════
# PATH 1 — FULL LOCAL STACK
# ══════════════════════════════════════════════════════════════════════════════
if ($mode -eq '1') {

    # ── 1a. llama-server ──────────────────────────────────────────────────────
    Step 'Locating llama-server...'

    $llamaBin = $null
    foreach ($c in @('llama-server',
                      (Join-Path $env:LOCALAPPDATA 'llama.cpp\llama-server.exe'),
                      'C:\llama.cpp\build\bin\Release\llama-server.exe',
                      (Join-Path $env:USERPROFILE 'llama.cpp\build\bin\Release\llama-server.exe'))) {
        try {
            $r = (Get-Command $c -ErrorAction SilentlyContinue)?.Source
            if ($r -and (Test-Path $r)) { $llamaBin = $r; break }
        } catch {}
        if ($c -ne 'llama-server' -and (Test-Path $c)) { $llamaBin = $c; break }
    }

    if (-not $llamaBin) {
        Warn 'llama-server not found.'
        Write-Host '  [a] winget (Windows Package Manager)'
        Write-Host '  [b] Download pre-built release from GitHub'
        Write-Host '  [c] Skip — install manually later'
        $installChoice = Read-Host 'Choice [a/b/c]'

        switch ($installChoice.ToLower()) {
            'a' {
                Info 'Installing via winget...'
                try {
                    winget install -e --id ggerganov.llama.cpp --accept-package-agreements --accept-source-agreements
                    $llamaBin = (Get-Command 'llama-server' -ErrorAction SilentlyContinue)?.Source
                } catch {
                    Warn 'winget failed — falling back to GitHub download'
                    $installChoice = 'b'
                }
            }
        }

        if ($installChoice.ToLower() -eq 'b') {
            $gpu = Detect-GpuBackend
            Info "Detected GPU backend: $gpu"
            $releaseApi = 'https://api.github.com/repos/ggerganov/llama.cpp/releases/latest'
            $release    = Invoke-RestMethod -Uri $releaseApi -UseBasicParsing
            # rocm is Linux-only; AMD on Windows uses the vulkan build
            $pattern    = switch ($gpu) {
                'cuda'   { 'win-cuda-cu\d+\.\d+-x64\.zip$' }
                'vulkan' { 'win-vulkan-x64\.zip$' }
                'rocm'   { 'win-vulkan-x64\.zip$' }
                default  { 'win-avx2-x64\.zip$' }
            }
            $asset = $release.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
            if (-not $asset) { $asset = $release.assets | Where-Object { $_.name -match 'win-avx2-x64\.zip$' } | Select-Object -First 1 }
            if (-not $asset) { Fail 'No Windows release found. Download manually from https://github.com/ggerganov/llama.cpp/releases' }

            $zip       = Join-Path $env:TEMP 'llama-cpp.zip'
            $extractTo = Join-Path $scriptDir '.llama-cpp'
            Info "Downloading $($asset.name)..."
            Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip -UseBasicParsing
            Expand-Archive -Path $zip -DestinationPath $extractTo -Force
            Remove-Item $zip -ErrorAction SilentlyContinue
            $llamaBin = Get-ChildItem -Path $extractTo -Filter 'llama-server.exe' -Recurse |
                        Select-Object -First 1 -ExpandProperty FullName
            if (-not $llamaBin) { Fail 'llama-server.exe not found in downloaded archive.' }
            Info "Extracted: $llamaBin"
        }

        if ($installChoice.ToLower() -eq 'c') {
            Warn 'Skipping. Set LLAMA_SERVER_BIN in .env before running.'
            $llamaBin = 'llama-server'
        }
    } else {
        Info "Found: $llamaBin"
    }

    # ── 1b. Model selection ───────────────────────────────────────────────────
    Step 'Model setup...'

    $defaultRepo = 'sci4ai/Qwen3.5-9B-Abliterated-Q8_0-GGUF'
    $modelPath   = ''

    $scanAns = Read-Host 'Scan common folders for existing GGUF models? [y/N]'
    $models  = @()
    if ($scanAns -match '^[Yy]') {
        $models = Find-Models
    }

    if ($models.Count -gt 0) {
        Write-Host ''
        Write-Host 'Found models:'
        for ($i = 0; $i -lt $models.Count; $i++) {
            Write-Host ("  [{0}] {1}" -f ($i + 1), $models[$i])
        }
        Write-Host "  [0] Download from HuggingFace"
        Write-Host "  [m] Enter path manually"
        Write-Host ''
        $sel = Read-Host "Select [0-$($models.Count)/m]"
        if ($sel -match '^\d+$') {
            $idx = [int]$sel
            if ($idx -ge 1 -and $idx -le $models.Count) {
                $modelPath = $models[$idx - 1]
            } elseif ($idx -eq 0) {
                $sel = 'h'
            } else {
                Fail 'Invalid selection.'
            }
        } else {
            $sel = $sel.ToLower()
        }
        if ($sel -eq 'm') {
            $modelPath = Read-Host 'Enter full path to GGUF file'
        }
    } else {
        Write-Host ''
        Write-Host '  [1] Download from HuggingFace'
        Write-Host '  [2] Enter local path'
        Write-Host ''
        $sel = Read-Host 'Choice [1/2]'
        if ($sel -eq '1') { $sel = 'h' }
        if ($sel -eq '2') { $modelPath = Read-Host 'Enter full path to GGUF file' }
    }

    if ($sel -eq 'h' -or ($models.Count -eq 0 -and $sel -eq '1')) {
        Write-Host ''
        $repoInput = Read-Host "HuggingFace repo (org/name) or Enter for default [$defaultRepo]"
        $repo      = if ($repoInput.Trim()) { $repoInput.Trim() } else { $defaultRepo }
        if (Test-Path $repo) {
            $modelPath = $repo
        } elseif ($repo -match '^[^/]+/[^/]+$') {
            $modelPath = Invoke-HFDownload $repo
        } else {
            Fail "Could not interpret input as a local path or HuggingFace repo ID: $repo"
        }
    }

    if (-not $modelPath) { Fail 'No model selected.' }
    Info "Model: $modelPath"

    # ── 1c. GPU layers ────────────────────────────────────────────────────────
    Step 'GPU offload layers...'
    $detectedGpu = Detect-GpuBackend
    $defaultNgl  = if ($detectedGpu -ne 'cpu') { '99' } else { '0' }
    Info "Detected GPU: $detectedGpu"
    $nglInput = Read-Host "GPU layers to offload (0=CPU only, 99=all) [default: $defaultNgl]"
    $modelNgl = if ($nglInput.Trim()) { $nglInput.Trim() } else { $defaultNgl }

    # ── 1d. uv ────────────────────────────────────────────────────────────────
    Step 'Checking uv...'
    $uv = (Get-Command uv -ErrorAction SilentlyContinue)?.Source
    if (-not $uv) {
        Info 'Installing uv...'
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path', 'User') + ';' +
                    [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
        $uv = (Get-Command uv -ErrorAction SilentlyContinue)?.Source
    }
    if ($uv) {
        Info "uv found: $uv"
        Set-Location $scriptDir
        & uv sync
    } else {
        Warn 'uv not found. Falling back to pip...'
        & $python -m pip install --quiet flask flask-cors websockets python-dotenv qwen-agent requests rich alembic
    }

    # ── 1e. npm ───────────────────────────────────────────────────────────────
    Step 'Installing frontend dependencies...'
    $npm = (Get-Command npm -ErrorAction SilentlyContinue)?.Source
    if (-not $npm) {
        Warn 'npm not found. Install Node.js from https://nodejs.org/ and re-run, or run:'
        Write-Host "  npm --prefix `"$scriptDir\frontend`" install"
    } else {
        & npm --prefix "$scriptDir\frontend" install
        Info 'Frontend dependencies installed.'
    }

    # ── 1f. Storage ───────────────────────────────────────────────────────────
    Step 'Conversation storage...'
    Write-Host '  [1] SQLite  - local database (search, tasks, folders)'
    Write-Host '  [2] JSONL   - flat files per conversation (portable)'
    Write-Host '  [3] None    - no history stored'
    Write-Host ''
    $convStorage = $null
    while (-not $convStorage) {
        switch (Read-Host 'Storage [1/2/3]') {
            '1' { $convStorage = 'sqlite' }
            '2' { $convStorage = 'jsonl' }
            '3' { $convStorage = 'none'; Warn 'No conversation history will be stored.' }
            default { Write-Host 'Enter 1, 2, or 3' }
        }
    }

    # ── 1g. Ports ─────────────────────────────────────────────────────────────
    Step 'Finding available ports...'
    $llamaPort    = Find-FreePort 8080 8180
    $toolsPort    = Find-FreePort 5100 5200
    $backendPort  = Find-FreePort 5000 5099
    $frontendPort = Find-FreePort 5173 5273
    if (-not ($llamaPort -and $toolsPort -and $backendPort -and $frontendPort)) {
        Fail 'Could not allocate all required ports. Free up ports in ranges 8080-8180, 5000-5200, 5173-5273.'
    }
    Info "llama-server: $llamaPort | tools: $toolsPort | backend: $backendPort | frontend: $frontendPort"

    # ── 1h. Data dir + secret key ─────────────────────────────────────────────
    $dataDir    = Join-Path $env:USERPROFILE '.atomic_chat'
    $jsonlDir   = Join-Path $dataDir 'conversations'
    $dbPath     = Join-Path $dataDir 'atomic_chat.db'
    New-Item -ItemType Directory -Force -Path $dataDir  | Out-Null
    New-Item -ItemType Directory -Force -Path $jsonlDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $scriptDir 'logs') | Out-Null

    $secretKey   = [System.Convert]::ToBase64String(
        [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    $modelAlias  = [System.IO.Path]::GetFileNameWithoutExtension($modelPath) -replace '\s+', '-'
    $databaseUrl = "sqlite:///$($dbPath -replace '\\', '/')"

    # ── 1i. Write .env ────────────────────────────────────────────────────────
    $envPath    = Join-Path $scriptDir '.env'
    $envContent = @"
MODEL=$modelPath
MODEL_ALIAS=$modelAlias
MODEL_NGL=$modelNgl
MODEL_CTX=4096
LLAMA_SERVER_BIN=$llamaBin
LLAMA_PORT=$llamaPort
TOOLS_PORT=$toolsPort
BACKEND_PORT=$backendPort
FRONTEND_PORT=$frontendPort
SECRET_KEY=$secretKey
DATABASE_URL=$databaseUrl
CONVERSATION_STORAGE=$convStorage
JSONL_PATH=$jsonlDir
"@
    Set-Content -Path $envPath -Value $envContent -Encoding UTF8
    Info 'Saved configuration to .env'

    # ── 1j. DB init ───────────────────────────────────────────────────────────
    Step 'Initialising database...'
    try {
        if ($uv) {
            & uv run alembic upgrade head
        } else {
            & $python -m alembic upgrade head
        }
        Info 'Database ready.'
    } catch {
        Warn "DB init failed: $_. Run 'alembic upgrade head' manually."
    }

    # ── 1k. start_local.bat ───────────────────────────────────────────────────
    $startBat = Join-Path $scriptDir 'start_local.bat'
    $batContent = @'
@echo off
setlocal enabledelayedexpansion
set "DIR=%~dp0"
cd /d "%DIR%"
if not exist "%DIR%logs" mkdir "%DIR%logs"

for /f "usebackq tokens=1,* delims==" %%A in ("%DIR%.env") do (
    set "_k=%%A"
    if not "!_k!"=="" if not "!_k:~0,1!"=="#" set "%%A=%%B"
)

echo Starting Atomic Chat (local mode)...

start "llama-server" /MIN cmd /k "%LLAMA_SERVER_BIN%" --model "%MODEL%" --host 0.0.0.0 --port %LLAMA_PORT% -ngl %MODEL_NGL% --alias "%MODEL_ALIAS%"
timeout /t 3 /nobreak > nul

start "tools-server" /MIN cmd /k uv run python "%DIR%tools_server.py"
start "backend" /MIN cmd /k uv run python "%DIR%main.py" --serve
start "frontend" /MIN cmd /k npm --prefix "%DIR%frontend" run dev

echo.
echo Services started. Open: http://localhost:%FRONTEND_PORT%
echo Logs: %DIR%logs\
'@
    Set-Content -Path $startBat -Value $batContent -Encoding ASCII
    Info 'Created start_local.bat'

# ══════════════════════════════════════════════════════════════════════════════
# PATH 2 — CLOUD CLIENT ONLY
# ══════════════════════════════════════════════════════════════════════════════
} elseif ($mode -eq '2') {

    Step 'Cloud Client — setting up agent...'

    # ── 2a. Create venv ───────────────────────────────────────────────────────
    $venvDir = Join-Path $scriptDir '.client-venv'
    $venvPy  = Join-Path $venvDir 'Scripts\python.exe'

    if (Test-Path $venvDir) { Warn 'Reusing existing .client-venv' }
    else {
        Info 'Creating virtual environment...'
        & $python -m venv $venvDir
    }
    Info 'Installing dependencies...'
    & $venvPy -m pip install --quiet --upgrade pip
    & $venvPy -m pip install --quiet websockets rich requests python-dotenv cryptography

    # ── 2b. Write .env.client ─────────────────────────────────────────────────
    $envFile = Join-Path $scriptDir '.env.client'
    $envContent = @"
ATOMIC_HOST=https://agent.eric-merritt.com
AGENT_SERVER=wss://agent.eric-merritt.com/api/bridge/connect
ALLOWED_PATHS=$env:USERPROFILE
"@
    Set-Content -Path $envFile -Value $envContent -Encoding UTF8
    Info 'Saved configuration to .env.client'

    # ── 2c. agent.bat ─────────────────────────────────────────────────────────
    $agentBat = Join-Path $scriptDir 'agent.bat'
    $batContent = @'
@echo off
set "DIR=%~dp0"
"%DIR%.client-venv\Scripts\python.exe" "%DIR%atomic_client\agent.py" %*
'@
    Set-Content -Path $agentBat -Value $batContent -Encoding ASCII
    Info 'Created agent.bat'

} else {
    Fail 'Invalid choice. Run the script again and enter 1 or 2.'
}

# ── .gitignore ────────────────────────────────────────────────────────────────
$gitignore = Join-Path $scriptDir '.gitignore'
foreach ($pattern in @('.client-venv', '.env.client', '.llama-cpp', 'logs/')) {
    $found = (Test-Path $gitignore) -and ((Get-Content $gitignore -ErrorAction SilentlyContinue) -contains $pattern)
    if (-not $found) { Add-Content -Path $gitignore -Value $pattern }
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '==============================' -ForegroundColor Green
Write-Host '  Installation complete!'      -ForegroundColor Green
Write-Host '==============================' -ForegroundColor Green
Write-Host ''

if ($mode -eq '1') {
    Write-Host 'Start all services:'
    Write-Host '  .\start_local.bat'
    Write-Host ''
    Write-Host "Configuration: .env"
} else {
    Write-Host 'Start the agent bridge:'
    Write-Host '  .\agent.bat'
    Write-Host ''
    Write-Host 'The agent will open your browser for authentication on first run.'
    Write-Host "Configuration: .env.client"
    Write-Host "  Edit ALLOWED_PATHS to control which folders the agent can access."
}
Write-Host ''
