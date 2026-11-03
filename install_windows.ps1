# Installer for the accountability monitor (Windows, Task Scheduler).
#
# Sets up a Python virtual environment, installs dependencies, and registers
# a Scheduled Task that starts the monitor at logon and restarts it if it
# stops. Run from the repo root in PowerShell:
#
#     powershell -ExecutionPolicy Bypass -File .\install_windows.ps1
#
$ErrorActionPreference = "Stop"

$InstallDir = Join-Path $env:LOCALAPPDATA "AccountabilityMonitor"
$Venv       = Join-Path $InstallDir "venv"
$Config     = Join-Path $InstallDir "config.json"
$SrcDir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName   = "AccountabilityMonitor"

Write-Host "==> Installing to: $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

Write-Host "==> Copying source"
$dst = Join-Path $InstallDir "accountability_monitor"
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Copy-Item -Recurse (Join-Path $SrcDir "accountability_monitor") $dst

Write-Host "==> Setting up config"
if (-not (Test-Path $Config)) {
    Copy-Item (Join-Path $SrcDir "config.example.json") $Config
    Write-Host "    Created $Config -- EDIT IT before email will send."
} else {
    Write-Host "    Keeping existing $Config"
}

Write-Host "==> Creating virtual environment"
python -m venv $Venv
& (Join-Path $Venv "Scripts\pip.exe") install --quiet --upgrade pip
& (Join-Path $Venv "Scripts\pip.exe") install --quiet -r (Join-Path $SrcDir "requirements.txt")

Write-Host "==> Registering scheduled task"
$pyw = Join-Path $Venv "Scripts\pythonw.exe"   # pythonw = no console window
$action  = New-ScheduledTaskAction -Execute $pyw `
    -Argument "-m accountability_monitor.monitor --config `"$Config`"" `
    -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host ""
Write-Host "Done."
Write-Host "  * Edit config:        notepad `"$Config`""
Write-Host "    (partner_email, sender_email, smtp_password)"
Write-Host "  * Restart after edit: Stop-ScheduledTask -TaskName $TaskName; Start-ScheduledTask -TaskName $TaskName"
Write-Host "  * (Recommended) set healthcheck_url in the config to a"
Write-Host "    healthchecks.io ping URL so your partner is warned if"
Write-Host "    monitoring goes quiet."
