# Plot top/bottom views of the board to SVG (for review images)
$cli = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
$b = "$PSScriptRoot\..\bassberry\bassberry.kicad_pcb"
$o = "$PSScriptRoot\..\bassberry\plots"
New-Item -ItemType Directory -Force $o | Out-Null
& $cli pcb export svg --mode-single --fit-page-to-board --exclude-drawing-sheet -l "F.Cu,F.SilkS,F.Fab,F.CrtYd,Edge.Cuts" -o "$o\top.svg" $b | Out-Null
& $cli pcb export svg --mode-single --fit-page-to-board --exclude-drawing-sheet --mirror -l "B.Cu,B.SilkS,B.Fab,B.CrtYd,Edge.Cuts" -o "$o\bottom.svg" $b | Out-Null
& $cli pcb export svg --mode-single --fit-page-to-board --exclude-drawing-sheet -l "In1.Cu,Edge.Cuts" -o "$o\in1.svg" $b | Out-Null
Get-ChildItem $o | Select Name,Length
