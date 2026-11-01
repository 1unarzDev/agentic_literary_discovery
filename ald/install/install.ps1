# ald one-line installer for Windows (PowerShell 5.1+). Safe to re-run.
#
#   $env:INVITE = "<INVITE>"; iwr -useb https://<coordinator>/install.ps1 | iex
#   or: & ([scriptblock]::Create((iwr -useb https://<coordinator>/install.ps1))) -Invite <INVITE>
#
# Run it from an *Administrator* PowerShell to install the background task so it starts at boot and keeps
# running after you sign out; from a normal PowerShell the task runs while you are signed in.
# Optional env vars: ALD_NAME (display name), ALD_NO_SERVICE=1, ALD_NO_WORK=1, ALD_COORDINATOR.
# The coordinator substitutes __COORDINATOR_URL__ when serving this file.
param(
    [string]$Invite = $env:INVITE,
    [string]$Name = $(if ($env:ALD_NAME) { $env:ALD_NAME } else { $env:COMPUTERNAME }),
    [string]$Coordinator = $(if ($env:ALD_COORDINATOR) { $env:ALD_COORDINATOR } else { "__COORDINATOR_URL__" }),
    [switch]$NoService = $($env:ALD_NO_SERVICE -eq "1"),
    [switch]$NoWork = $($env:ALD_NO_WORK -eq "1")
)

# Everything runs inside a function so that, under `| iex`, nothing leaks into the caller's session and an
# error never closes the window (no `exit`). Native tools (uv, winget, ald) write progress to stderr; with
# PowerShell 5.1 that must not be treated as an error, so their exit codes are checked explicitly instead.
function Install-Ald {
    param([string]$Invite, [string]$Name, [string]$Coordinator, [bool]$NoService, [bool]$NoWork)
    $ErrorActionPreference = "Continue"
    $ProgressPreference = "SilentlyContinue"
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    # Model downloads take a while, and an upgrade stops the running worker (which normally keeps the PC
    # awake): keep the system from sleeping until this script ends (ES_CONTINUOUS | ES_SYSTEM_REQUIRED).
    try {
        if (-not ("Ald.AldPowerNative" -as [type])) {
            Add-Type -Namespace Ald -Name AldPowerNative -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);' -ErrorAction Stop
        }
        [Ald.AldPowerNative]::SetThreadExecutionState([uint32]"0x80000001") | Out-Null
    } catch { }

    function Say($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
    function Warn($m) { Write-Host "!!  $m" -ForegroundColor Yellow }
    function Native([string]$exe, [string[]]$argv) {
        # Run a native command, stream its output, return its exit code (stderr is not an error).
        & $exe @argv 2>&1 | ForEach-Object { if ($_ -is [System.Management.Automation.ErrorRecord]) { Write-Host $_.Exception.Message } else { Write-Host $_ } }
        return $LASTEXITCODE
    }
    function Add-SessionPath($dir) {
        if ((Test-Path $dir) -and -not (($env:Path -split ";") -contains $dir)) { $env:Path = "$dir;$env:Path" }
    }
    function Test-Ollama { try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 2 -UseBasicParsing | Out-Null; $true } catch { $false } }

    # (Do not compare against the placeholder literally: the coordinator replaces every occurrence.)
    if (-not ($Coordinator -match '^https?://')) { throw "coordinator URL unknown: set `$env:ALD_COORDINATOR" }
    $Coordinator = $Coordinator.TrimEnd("/")
    $bin = Join-Path $env:USERPROFILE ".local\bin"
    Add-SessionPath $bin

    # 1. uv (official Astral installer, user-local, no admin) ----------------------------------------
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Say "Installing uv (official Astral installer, user-local)"
        $rc = Native "powershell" @("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "ByPass", "-Command", "irm https://astral.sh/uv/install.ps1 | iex")
        Add-SessionPath $bin
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv installation failed (exit $rc)" }
    }
    $uv = (Get-Command uv).Source

    # 2. ald -------------------------------------------------------------------------------------------
    try { $ping = Invoke-RestMethod -Uri "$Coordinator/v1/ping" -UseBasicParsing -TimeoutSec 30 -ErrorAction Stop }
    catch { throw "coordinator not reachable at $Coordinator ($($_.Exception.Message))" }
    if (-not $ping.wheel_url) { throw "/v1/ping did not return wheel_url" }
    $current = ""
    if (Get-Command ald -ErrorAction SilentlyContinue) { $current = "$(& ald version 2>$null)".Trim() }
    if ($current -and $current -eq "$($ping.latest_client_version)") {
        Say "ald $current already installed"
    } else {
        Say "Installing ald $($ping.latest_client_version) with uv (Python 3.12)"
        # A running worker locks its own files; stop it before replacing the install.
        if ($current) { & schtasks /End /TN ald-worker 2>&1 | Out-Null; Start-Sleep 3 }
        $rc = Native $uv @("tool", "install", "--force", "--python", "3.12", $ping.wheel_url)
        if ($rc -ne 0) { throw "uv tool install failed (exit $rc)" }
        Native $uv @("tool", "update-shell") | Out-Null
    }
    Add-SessionPath $bin
    if (-not (Get-Command ald -ErrorAction SilentlyContinue)) { throw "ald not on PATH; open a new PowerShell and re-run" }

    # 3. Ollama (silent install; no admin needed: it installs per user) -------------------------------
    $ollamaDir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue) -and -not (Test-Path (Join-Path $ollamaDir "ollama.exe")) -and -not (Test-Ollama)) {
        $installed = $false
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Say "Installing Ollama with winget (silent)"
            $rc = Native "winget" @("install", "--id", "Ollama.Ollama", "-e", "--source", "winget", "--silent",
                                    "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity")
            $installed = ($rc -eq 0) -and (Test-Path (Join-Path $ollamaDir "ollama.exe"))
        }
        if (-not $installed) {
            Say "Installing Ollama with the official OllamaSetup.exe (silent)"
            $setup = Join-Path $env:TEMP "OllamaSetup.exe"
            Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $setup -UseBasicParsing -ErrorAction Stop
            Start-Process -FilePath $setup -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-" -Wait
        }
        if (-not (Test-Path (Join-Path $ollamaDir "ollama.exe"))) { throw "Ollama installation failed" }
    }
    Add-SessionPath $ollamaDir
    # `ald setup` (below) starts Ollama if needed, writes the tuned OLLAMA_* user variables and restarts it.

    # 4. join, models, benchmark ----------------------------------------------------------------------
    if ($Invite) {
        Say "Joining $Coordinator as $Name"
        $rc = Native "ald" @("join", $Coordinator, $Invite, "--name", $Name)
        if ($rc -ne 0) { throw "join failed (is the invite valid and unused?)" }
    } else { Warn "no INVITE given; skipping join (fine if this machine already joined)" }
    Say "Configuring Ollama, pulling and verifying the pinned models for this machine's tier"
    $rc = Native "ald" @("setup", "--yes")
    if ($rc -ne 0) { Warn "setup reported problems (see above)" }
    Say "Benchmarking (~2 min)"
    $rc = Native "ald" @("doctor", "--bench")
    if ($rc -ne 0) { Warn "benchmark failed; work will auto-tune from scratch" }

    # 5. background task + work -----------------------------------------------------------------------
    $ok = $true
    if (-not $NoService) {
        Say "Installing (or rewriting) the Scheduled Task 'ald-worker' and starting it"
        $rc = Native "ald" @("service", "install")
        if ($rc -ne 0) { Warn "service install failed (see above)"; $ok = $false }
        Say "Waiting for the worker to start and reach the coordinator (up to 3 min)"
        $rc = Native "ald" @("service", "verify", "--wait", "180")
        if ($rc -ne 0) { $ok = $false }
    }
    Native "ald" @("status") | Out-Null
    if (-not $NoService) {
        if ($ok) {
            Write-Host "==> SUCCESS: ald is installed and working in the background (Scheduled Task 'ald-worker')." -ForegroundColor Green
            Say "Check: 'ald status' (or 'ald status --watch'); settings: 'ald config'; stop/remove: 'ald service uninstall'."
            Say "Open a new PowerShell window to use the 'ald' command."
        } else {
            Write-Host "xx  FAILED: ald is installed but the background worker is not running. Re-run this command;" -ForegroundColor Red
            Write-Host "xx  if it fails again, send the output above to the project admin." -ForegroundColor Red
        }
    } elseif (-not $NoWork) {
        Say "Starting ald work (Ctrl-C uploads partial results and releases leases)"
        & ald work
    }
}

try {
    Install-Ald -Invite $Invite -Name $Name -Coordinator $Coordinator -NoService ([bool]$NoService) -NoWork ([bool]$NoWork)
} catch {
    Write-Host "xx  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "xx  ald installation did not finish; fix the problem above and re-run the same command." -ForegroundColor Red
} finally {
    try { [Ald.AldPowerNative]::SetThreadExecutionState([uint32]"0x80000000") | Out-Null } catch { }
}
