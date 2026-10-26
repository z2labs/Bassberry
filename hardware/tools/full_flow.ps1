# Whole board flow, unattended: schematic -> placement -> pre-route twin gates -> srouter -> post-route -> DRC -> twin.
#   powershell -ExecutionPolicy Bypass -File hardware\tools\full_flow.ps1
$ErrorActionPreference = "Continue"
$root = Resolve-Path "$PSScriptRoot\..\.."
$py   = "C:\Program Files\KiCad\10.0\bin\python.exe"
$log  = "$root\hardware\bassberry\route\full_flow.log"
New-Item -ItemType Directory -Force "$root\hardware\bassberry\route" | Out-Null
Set-Location $root
"== $(Get-Date -Format HH:mm:ss) schematic" | Out-File -Encoding utf8 $log
& powershell -ExecutionPolicy Bypass -File "$root\hardware\tools\regen_sch.ps1" 2>&1 | Out-File -Append -Encoding utf8 $log
"== $(Get-Date -Format HH:mm:ss) placement" | Out-File -Append -Encoding utf8 $log
& $py hardware\tools\pcb_build.py 2>&1 | Select-String -NotMatch "duplicate image" | Out-File -Append -Encoding utf8 $log
if ($LASTEXITCODE -ne 0) { "== placement FAILED" | Out-File -Append -Encoding utf8 $log; exit 1 }
$gate = 0
foreach ($t in 'twin_check', 'twin_plug', 'twin_mech') {
  "== $(Get-Date -Format HH:mm:ss) pre-route $t" | Out-File -Append -Encoding utf8 $log
  & $py "hardware\twin\$t.py" hardware\bassberry\bassberry_placed.kicad_pcb --selftest -q 2>&1 | Select-String -NotMatch "duplicate image" | Out-File -Append -Encoding utf8 $log
  if ($LASTEXITCODE -ne 0) { $gate = 1 }
}
if ($gate) { "== pre-route twin FAILED: not routing" | Out-File -Append -Encoding utf8 $log; exit 1 }
"== $(Get-Date -Format HH:mm:ss) route" | Out-File -Append -Encoding utf8 $log
& $py hardware\tools\route.py 2>&1 | Select-String -NotMatch "duplicate image|^>>" | Out-File -Append -Encoding utf8 $log
if ($LASTEXITCODE -ne 0) { "== route FAILED (escape gate or srouter)" | Out-File -Append -Encoding utf8 $log; exit 1 }
Copy-Item hardware\bassberry\bassberry.kicad_pcb hardware\bassberry\route\bassberry_routed_raw.kicad_pcb
"== $(Get-Date -Format HH:mm:ss) post-route" | Out-File -Append -Encoding utf8 $log
& powershell -ExecutionPolicy Bypass -File "$root\hardware\tools\postroute.ps1" 2>&1 | Out-Null
Get-Content "$root\hardware\bassberry\route\postroute.log" | Out-File -Append -Encoding utf8 $log
"== $(Get-Date -Format HH:mm:ss) done" | Out-File -Append -Encoding utf8 $log
