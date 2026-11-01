# ald one-line installer for Windows. Safe to re-run.
#
#   $env:INVITE = "<INVITE>"; iwr -useb https://<coordinator>/install.ps1 | iex
#   or: & ([scriptblock]::Create((iwr -useb https://<coordinator>/install.ps1))) -Invite <INVITE>
#
# The coordinator substitutes __COORDINATOR_URL__ when serving this file.
param(
    [string]$Invite = $env:INVITE,
    [string]$Name = $env:COMPUTERNAME,
    [string]$Coordinator = $(if ($env:ALD_COORDINATOR) { $env:ALD_COORDINATOR } else { "__COORDINATOR_URL__" }),
    [switch]$NoService,
    [switch]$NoWork
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

function Say($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "!!  $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "xx  $m" -ForegroundColor Red; exit 1 }

# (Do not compare against the placeholder literally: the coordinator replaces every occurrence.)
if (-not ($Coordinator -match '^https?://')) { Die "coordinator URL unknown: set `$env:ALD_COORDINATOR" }
$Coordinator = $Coordinator.TrimEnd("/")

function Add-UserPath($dir) {
    if ((Test-Path $dir) -and -not (($env:Path -split ";") -contains $dir)) { $env:Path = "$dir;$env:Path" }
}
Add-UserPath "$env:USERPROFILE\.local\bin"

# 1. uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Say "Installing uv (official Astral installer, user-local)"
    powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    Add-UserPath "$env:USERPROFILE\.local\bin"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Die "uv installation failed" }

# 2. ald
try { $ping = Invoke-RestMethod -Uri "$Coordinator/v1/ping" -UseBasicParsing } catch { Die "coordinator not reachable at $Coordinator" }
if (-not $ping.wheel_url) { Die "/v1/ping did not return wheel_url" }
$current = ""
if (Get-Command ald -ErrorAction SilentlyContinue) { $current = (& ald version 2>$null) }
if ($current -and $current.Trim() -eq "$($ping.latest_client_version)") {
    Say "ald $current already installed"
} else {
    Say "Installing ald $($ping.latest_client_version) with uv (Python 3.12)"
    & uv tool install --force --python 3.12 $ping.wheel_url
    if ($LASTEXITCODE -ne 0) { Die "uv tool install failed" }
    & uv tool update-shell 2>$null | Out-Null
}
Add-UserPath "$env:USERPROFILE\.local\bin"
if (-not (Get-Command ald -ErrorAction SilentlyContinue)) { Die "ald not on PATH; open a new terminal and re-run" }

# 3. Ollama
function Test-Ollama { try { Invoke-RestMethod -Uri "http://localhost:11434/api/version" -TimeoutSec 2 | Out-Null; $true } catch { $false } }
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue) -and -not (Test-Path $ollamaExe) -and -not (Test-Ollama)) {
    $installed = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Say "Installing Ollama with winget"
        & winget install --silent --accept-package-agreements --accept-source-agreements -e --id Ollama.Ollama
        $installed = ($LASTEXITCODE -eq 0)
    }
    if (-not $installed) {
        Say "Installing Ollama with the official OllamaSetup.exe"
        $setup = Join-Path $env:TEMP "OllamaSetup.exe"
        Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $setup -UseBasicParsing
        Start-Process -FilePath $setup -ArgumentList "/SILENT" -Wait
    }
}
Add-UserPath "$env:LOCALAPPDATA\Programs\Ollama"
if (-not (Test-Ollama)) {
    Say "Starting Ollama"
    $app = "$env:LOCALAPPDATA\Programs\Ollama\ollama app.exe"
    if (Test-Path $app) { Start-Process -FilePath $app } else { Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden }
    $i = 0; while (-not (Test-Ollama) -and $i -lt 30) { Start-Sleep 1; $i++ }
    if (-not (Test-Ollama)) { Die "Ollama did not start; start it and re-run" }
}

# 4. join, models, benchmark
if ($Invite) {
    Say "Joining $Coordinator as $Name"
    & ald join $Coordinator $Invite --name $Name
    if ($LASTEXITCODE -ne 0) { Die "join failed" }
} else { Warn "no INVITE given; skipping join (fine if this machine already joined)" }
Say "Pulling and verifying the pinned models for this machine's tier"
& ald setup --yes
if ($LASTEXITCODE -ne 0) { Warn "setup reported problems (see above)" }
Say "Benchmarking (~60 s)"
& ald doctor --bench
if ($LASTEXITCODE -ne 0) { Warn "benchmark failed; work will auto-tune from scratch" }

# 5. service + work
if (-not $NoService) {
    Say "Installing a Scheduled Task that runs 'ald work' at logon"
    & ald service install
}
Say "Summary"
& ald work --dry-run
& ald status --local
if (-not $NoService) {
    Say "ald work is running (Scheduled Task 'ald-worker'). Status: 'ald service status'; remove: 'ald service uninstall'."
} elseif (-not $NoWork) {
    Say "Starting ald work (Ctrl-C uploads partial results and releases leases)"
    & ald work --keep-awake
}
