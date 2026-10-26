# Post-routing pipeline, mandatory order from srouter docs/USAGE.md, then KiCad DRC and the digital twin.
#   powershell -ExecutionPolicy Bypass -File hardware\tools\postroute.ps1
$ErrorActionPreference = "Continue"
$root  = Resolve-Path "$PSScriptRoot\..\.."
$py    = "C:\Program Files\KiCad\10.0\bin\python.exe"
$cli   = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
$tools = if ($env:SROUTER_TOOLS) { $env:SROUTER_TOOLS } else { "C:\Users\RF\Documents\GitHub\srouter-b3\tools" }
$board = "$root\hardware\bassberry\bassberry.kicad_pcb"
$log   = "$root\hardware\bassberry\route\postroute.log"
function step($name, [scriptblock]$b) {
  "== $name  $(Get-Date -Format HH:mm:ss)" | Out-File -Append -Encoding utf8 $log
  & $b 2>&1 | Select-String -NotMatch "duplicate image handler" | ForEach-Object { $_.Line } | Out-File -Append -Encoding utf8 $log
  "   exit $LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
}
"" | Out-File -Encoding utf8 $log
step "1 track_tidy"   { & $py "$tools\track_tidy.py" $board }
step "1b power_pour" { & $py "$root\hardware\tools\power_pour.py" $board }
step "2 zone fill"    { & $py -c "import pcbnew;b=pcbnew.LoadBoard(r'$board');pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard(r'$board',b);print('filled')" }
step "3 gnd_stitch"   { & $py "$tools\gnd_stitch.py" $board }
step "4 via_rescue"   { & $py "$tools\via_rescue.py" $board --net GND }
step "5 stitch_audit" { & $py "$tools\stitch_audit.py" $board }
step "6 silk_dfm fix" { & $py "$tools\silk_dfm.py" $board --fix }
step "6 silk_dfm"     { & $py "$tools\silk_dfm.py" $board }
step "7 DRC"          { & $cli pcb drc --schematic-parity --severity-all --format json -o "$root\hardware\bassberry\route\drc.json" $board;
                        & $py -c "import json,collections;d=json.load(open(r'$root\hardware\bassberry\route\drc.json'));v=d['violations'];u=d.get('unconnected_items',[]);p=d.get('schematic_parity',[]);c=collections.Counter((x['severity'],x['type']) for x in v);print('violations',len(v),'unconnected',len(u),'parity',len(p));[print(' ',k,n) for k,n in c.most_common()]" }
foreach ($t in 'twin_check','twin_plug','twin_analog','twin_mech') {
  step "twin $t" { & $py "$root\hardware\twin\$t.py" $board --selftest -q }
}
