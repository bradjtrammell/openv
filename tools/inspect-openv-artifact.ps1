# OpenV experimental Windows artifact inspection (does not execute game binaries)
# Usage: pwsh -NoProfile -File .\tools\inspect-openv-artifact.ps1 -Directory 'C:\OpenV-Test'
param([Parameter(Mandatory=$true)][string]$Directory,[string]$Manifest)
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath $Directory).Path
$files=@(Get-ChildItem -LiteralPath $root -Recurse -File)
$executables=@($files | Where-Object { $_.Extension -ieq '.exe' })
$summary=[ordered]@{
 path=$root
 file_count=$files.Count
 total_bytes=($files|Measure-Object -Property Length -Sum).Sum
 executables=@($executables|ForEach-Object {$_.FullName.Substring($root.Length).TrimStart('\','/')})
}
$summary | ConvertTo-Json -Depth 6
if($Manifest){
 $m=Get-Content -LiteralPath $Manifest -Raw|ConvertFrom-Json
 $bad=@()
 foreach($entry in $m.files){
   $relative=[string]$entry.path
   if([IO.Path]::IsPathRooted($relative) -or ($relative -split '[\\/]' | Where-Object {$_ -eq '..'})){
     $bad+="Unsafe manifest path: $relative";continue
   }
   $p=Join-Path $root $relative
   if(-not(Test-Path -LiteralPath $p -PathType Leaf)){ $bad+="Missing: $relative";continue }
   $actual=(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash
   if($actual -ine $entry.sha256){$bad+="SHA256 mismatch: $relative"}
 }
 if($bad.Count){$bad|ForEach-Object {Write-Error $_};exit 1}
 Write-Host "All $(@($m.files).Count) manifest entries verified." -ForegroundColor Green
}
Write-Host 'Inspection only. The source-derived experimental artifact has not been confirmed installable or playable.'
