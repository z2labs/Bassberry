# JLCPCB fabrication outputs from a routed KiCad board (KiCad 10 kicad-cli).
#   powershell -ExecutionPolicy Bypass -File jlc_fab.ps1 [-Board path\to\board.kicad_pcb]
# -> <board dir>/jlc/gerber/*  Gerber + Excellon with JLC's KiCad settings, zipped as <name>_gerber.zip
#    <board dir>/jlc/<name>_pos_kicad.csv  raw placement, both sides (jlc_bom_cpl.py / jlc_rotfix.py turn it into the CPL)
param([string]$Board = "$PSScriptRoot\..\bassberry\bassberry.kicad_pcb")
$cli  = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
$b    = (Resolve-Path $Board).Path
$name = [IO.Path]::GetFileNameWithoutExtension($b)
$o    = Join-Path (Split-Path $b) "jlc"
$g    = "$o\gerber"
Remove-Item -Recurse -Force $g -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $g | Out-Null
# JLC KiCad guide: Protel extensions, silkscreen clipped by the mask openings, no X2 / netlist attributes; inner layers as many as the board has
$inner = (Select-String -Path $b -Pattern '^\s*\(\d+ "(In\d+\.Cu)"' | ForEach-Object { $_.Matches[0].Groups[1].Value }) -join ","
$layers = (@("F.Cu") + $(if ($inner) { $inner } else { @() }) + @("B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts")) -join ","
& $cli pcb export gerbers -o "$g\" -l $layers --subtract-soldermask --no-x2 --no-netlist $b
# Excellon, mm, PTH and NPTH in separate files, absolute origin (same as the Gerbers), plus the drill map
& $cli pcb export drill -o "$g\" --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 `
      --drill-origin absolute $b
Compress-Archive -Force -Path "$g\*" -DestinationPath "$o\${name}_gerber.zip"
& $cli pcb export pos -o "$o\${name}_pos_kicad.csv" --format csv --units mm --side both $b
Get-ChildItem $g, $o -File | Select-Object Name, Length
