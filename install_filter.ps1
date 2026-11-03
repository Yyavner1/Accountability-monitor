# Apply the website filter to the system hosts file (Windows).
# Run in an ELEVATED PowerShell (Run as Administrator):
#
#     powershell -ExecutionPolicy Bypass -File .\install_filter.ps1 [blocklist.txt] [URL]
#
param(
    [string]$Blocklist = "$PSScriptRoot\blocklist.txt",
    [string]$Url = ""
)
$ErrorActionPreference = "Stop"

# Require elevation (editing the hosts file needs admin).
$admin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) {
    Write-Error "Please run this in an elevated PowerShell (Run as Administrator)."
    exit 1
}

$tmp = [System.IO.Path]::GetTempFileName()
Get-Content $Blocklist | Set-Content $tmp
if ($Url -ne "") {
    Write-Host "==> Downloading blocklist from $Url"
    Invoke-WebRequest -Uri $Url -OutFile "$tmp.dl"
    Get-Content "$tmp.dl" | Add-Content $tmp
    Remove-Item "$tmp.dl"
}

Write-Host "==> Applying filter"
$env:PYTHONPATH = $PSScriptRoot
python -m accountability_monitor.blocker apply $tmp
Remove-Item $tmp

ipconfig /flushdns | Out-Null
Write-Host "Done. Status:  python -m accountability_monitor.blocker status"
Write-Host "Remove (elevated):  python -m accountability_monitor.blocker remove"
