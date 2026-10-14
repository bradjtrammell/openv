# OpenV gaming PC readiness check (non-destructive)
# Run: pwsh -NoProfile -File .\tools\openv-gaming-pc-preflight.ps1
$ErrorActionPreference = 'Stop'
Write-Host 'OpenV Gaming PC Preflight' -ForegroundColor Cyan
$checks = @()
function Record($Name,$Pass,$Details) {
  $script:checks += [pscustomobject]@{Check=$Name;Pass=$Pass;Details=$Details}
  Write-Host ("{0} {1}: {2}" -f $(if($Pass){'[OK]'}else{'[CHECK]'}),$Name,$Details)
}
$os = Get-CimInstance Win32_OperatingSystem
Record 'Windows 64-bit' ($env:PROCESSOR_ARCHITECTURE -eq 'AMD64') "$($os.Caption) $($os.Version)"
$gameCandidates = @(
  "${env:ProgramFiles}\Rockstar Games\Grand Theft Auto V\GTA5.exe",
  "${env:ProgramFiles(x86)}\Steam\steamapps\common\Grand Theft Auto V\GTA5.exe",
  "${env:ProgramFiles}\Epic Games\GTAV\GTA5.exe"
)
$existing = $gameCandidates | Where-Object {Test-Path $_} | Select-Object -First 1
Record 'GTA V executable in standard paths' ([bool]$existing) $(if($existing){$existing}else{'Not found automatically; custom install locations need manual check'})
$gpu=Get-CimInstance Win32_VideoController | Select-Object -First 2 -ExpandProperty Name
Record 'Display adapter detected' ([bool]$gpu) ($gpu -join ', ')
Record 'Git available' ([bool](Get-Command git -ErrorAction SilentlyContinue)) 'Needed only if building locally'
Record 'PowerShell 7 available' ($PSVersionTable.PSVersion.Major -ge 7) "$($PSVersionTable.PSVersion)"
$checks | ConvertTo-Json | Set-Content -Encoding utf8 '.\openv-preflight.json'
Write-Host 'Saved openv-preflight.json'
if (-not $existing) { Write-Host 'No game found in standard locations. This is not a failed ownership check.' -ForegroundColor Yellow }
