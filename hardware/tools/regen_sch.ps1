# Regenerate schematics, run ERC and export the netlist (Windows, KiCad 10).
#   powershell -ExecutionPolicy Bypass -File hardware\tools\regen_sch.ps1
$ErrorActionPreference = "Continue"
$root = Resolve-Path "$PSScriptRoot\..\.."
$py  = "C:\Program Files\KiCad\10.0\bin\python.exe"
$cli = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
Set-Location $root
& $py hardware\tools\bassberry_sch.py
Set-Location hardware\bassberry
& $cli sch erc --severity-all --format json -o erc.json bassberry.kicad_sch | Out-Null
& $cli sch export netlist --format kicadsexpr -o bassberry.net bassberry.kicad_sch | Out-Null
& $py -c "import json;d=json.load(open('erc.json'));v=[x for s in d['sheets'] for x in s['violations']];print('ERC violations:',len(v));[print(' ',x['severity'],x['type'],[i['description'][:50] for i in x['items']]) for x in v]"
Set-Location $root
