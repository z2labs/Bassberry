# JLCPCB fabrication + assembly outputs from the routed board (KiCad 10 kicad-cli).
#   powershell -ExecutionPolicy Bypass -File hardware\tools\jlc_fab.ps1
# -> hardware/bassberry/jlc/gerber/*  (Gerber + Excellon, JLC naming conventions, zipped as bassberry_gerber.zip)
#    hardware/bassberry/jlc/bassberry_pos_kicad.csv (raw placement; jlc_bom_cpl.py turns it into the JLC CPL + BOM)
$cli  = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
$root = Resolve-Path "$PSScriptRoot\..\.."
$b    = "$root\hardware\bassberry\bassberry.kicad_pcb"
$o    = "$root\hardware\bassberry\jlc"
$g    = "$o\gerber"
Remove-Item -Recurse -Force $g -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $g | Out-Null
# JLC KiCad guide: Protel extensions, silkscreen clipped by the mask openings, no X2 / netlist attributes
& $cli pcb export gerbers -o "$g\" -l "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts" `
      --subtract-soldermask --no-x2 --no-netlist --use-drill-file-origin $b
# Excellon, mm, PTH and NPTH in separate files, plus the drill map
& $cli pcb export drill -o "$g\" --format excellon --excellon-units mm --excellon-separate-th --generate-map --map-format gerberx2 `
      --drill-origin absolute $b
Compress-Archive -Force -Path "$g\*" -DestinationPath "$o\bassberry_gerber.zip"
# placement of every footprint, both sides (DNP and board-only items are filtered by jlc_bom_cpl.py)
& $cli pcb export pos -o "$o\bassberry_pos_kicad.csv" --format csv --units mm --side both $b
Get-ChildItem $g, $o -File | Select-Object Name, Length
