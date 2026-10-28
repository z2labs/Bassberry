# Post-routing pipeline, mandatory order from srouter docs/USAGE.md, then KiCad DRC and the digital twin.
#   powershell -ExecutionPolicy Bypass -File hardware\tools\postroute.ps1
$ErrorActionPreference = "Continue"
$root  = Resolve-Path "$PSScriptRoot\..\.."
$py    = "C:\Program Files\KiCad\10.0\bin\python.exe"
$cli   = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
$tools = if ($env:SROUTER_TOOLS) { $env:SROUTER_TOOLS } else { "C:\Users\RF\Documents\GitHub\srouter-jlc\tools" }   # feat/jlc-fab: silk_dfm also clears via holes
$board = "$root\hardware\bassberry\bassberry.kicad_pcb"
$log   = "$root\hardware\bassberry\route\postroute.log"
function step($name, [scriptblock]$b) {
  "== $name  $(Get-Date -Format HH:mm:ss)" | Out-File -Append -Encoding utf8 $log
  & $b 2>&1 | Select-String -NotMatch "duplicate image handler" | ForEach-Object { $_.Line } | Out-File -Append -Encoding utf8 $log
  "   exit $LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
}
"" | Out-File -Encoding utf8 $log
Copy-Item $board "$root\hardware\bassberry\route\pre_tidy.kicad_pcb"
step "1 track_tidy"   { & $py "$tools\track_tidy.py" $board }
step "1a tidy_guard"  { & $py "$root\hardware\tools\tidy_guard.py" "$root\hardware\bassberry\route\pre_tidy.kicad_pcb" $board }
step "1c via_off_pad" { & $py "$root\hardware\tools\via_off_pad.py" $board }
step "1b power_pour" { & $py "$root\hardware\tools\power_pour.py" $board }
step "2 zone fill"    { & $py -c "import pcbnew;b=pcbnew.LoadBoard(r'$board');pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard(r'$board',b);print('filled')" }
# walled-in GND pads first (gnd_pad_rescue moves the signal tracks and strips stitching, so it goes before gnd_stitch)
$env:SROUTER = if ($env:SROUTER) { $env:SROUTER } else { "C:\Users\RF\Documents\GitHub\srouter-feat\target\release\srouter.exe" }
$orph = & $py "$tools\via_rescue.py" $board --net GND --dry 2>&1 | Select-String "remaining orphan: (\S+)" | ForEach-Object { $_.Matches[0].Groups[1].Value.TrimEnd(',') } | Sort-Object -Unique
"== 2b walled-in GND pads: $($orph -join ' ')" | Out-File -Append -Encoding utf8 $log
# (gnd_pad_rescue is not used: it re-routes the ripped nets at srouter's single width, which would undo the power copper;
#  GND pads get their own dog-bone vias before routing instead - pcb_build.py gnd_dogbones)
step "4 via_rescue"   { & $py "$tools\via_rescue.py" $board --net GND }
step "4b via_off_pad" { & $py "$root\hardware\tools\via_off_pad.py" $board }
step "4c z2_stitch"   { & $py "$root\hardware\tools\z2_stitch.py" $board }   # Z2 Stitch 0.3.0, last copper step: nothing is routed after it
step "5 stitch_audit" { & $py "$tools\stitch_audit.py" $board }
step "6 silk_dfm fix" { & $py "$tools\silk_dfm.py" $board --fix }
step "6a dfm silk fix" { & $py "$root\hardware\twin\twin_dfm.py" $board --fix-silk }
step "6 silk_dfm"     { & $py "$tools\silk_dfm.py" $board }
step "6b zone refill" { & $py -c "import pcbnew;b=pcbnew.LoadBoard(r'$board');pcbnew.ZONE_FILLER(b).Fill(b.Zones());pcbnew.SaveBoard(r'$board',b);print('refilled after stitching')" }
step "6c zero-length tracks" { & $py -c "import pcbnew;b=pcbnew.LoadBoard(r'$board');z=[t for t in b.GetTracks() if t.GetClass()!='PCB_VIA' and t.GetStart()==t.GetEnd()];[b.Remove(t) for t in z];pcbnew.SaveBoard(r'$board',b);print('zero-length tracks removed:',len(z))" }
step "7 DRC"          { & $cli pcb drc --schematic-parity --severity-all --format json -o "$root\hardware\bassberry\route\drc.json" $board;
                        & $py -c "import json,collections;d=json.load(open(r'$root\hardware\bassberry\route\drc.json'));v=d['violations'];u=d.get('unconnected_items',[]);p=d.get('schematic_parity',[]);c=collections.Counter((x['severity'],x['type']) for x in v);print('violations',len(v),'unconnected',len(u),'parity',len(p));[print(' ',k,n) for k,n in c.most_common()]" }
foreach ($t in 'twin_check','twin_plug','twin_analog','twin_mech','twin_dfm') {
  step "twin $t" { & $py "$root\hardware\twin\$t.py" $board --selftest -q }
}
