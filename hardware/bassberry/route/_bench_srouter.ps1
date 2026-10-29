$r = "C:\Users\RF\Documents\GitHub\bassberry\hardware\bassberry\route\bench"
$sr = "C:\Users\RF\Documents\GitHub\srouter-cong\target\release\srouter.exe"
$dirs = @("-dir","F.Cu:H:2.5","-dir","In1.Cu:V:2.5","-dir","In2.Cu:H:2.5","-dir","B.Cu:V:2.5")
$t0 = Get-Date
& $sr -de "$r\bassberry_bench.dsn" -do "$r\srouter2.ses" -rules "$r\bench_rules.json" -report "$r\srouter2_report.json" -congmap "$r\srouter2_cong.json" -it 60 -stall 10 @dirs > "$r\srouter2.log" 2>&1
"srouter single pass, all nets: {0:N0} s" -f ((Get-Date) - $t0).TotalSeconds
Select-String "$r\srouter2.log" -Pattern "global:|stall:|^\s*!|routed .* nets|total\]" | ForEach-Object { $_.Line } | Select-Object -Last 25

