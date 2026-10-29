# machine index on the G7: ONE iteration, ONE thread, bench input (same as _z_post.sh / _vm_mindex.sh elsewhere)
$r = "C:\Users\RF\Documents\GitHub\bassberry\hardware\bassberry\route\bench"
$sr = "C:\Users\RF\Documents\GitHub\srouter-gpu\target\release\srouter.exe"   # feat/cuda-wavefront built without the cuda feature = CPU-only
$dirs = @("-dir","F.Cu:H:2.5","-dir","In1.Cu:V:2.5","-dir","In2.Cu:H:2.5","-dir","B.Cu:V:2.5")
foreach ($k in 1..3) {
  $t0 = Get-Date
  & $sr -de "$r\bassberry_bench.dsn" -do "$env:TEMP\idx.ses" -rules "$r\bench_rules.json" -it 1 -mt 1 @dirs > "$env:TEMP\idx.log" 2>&1
  $dt = ((Get-Date) - $t0).TotalSeconds
  (Select-String "$env:TEMP\idx.log" -Pattern "iter  1").Line + ("  real {0:N1} s" -f $dt)
}
(Get-CimInstance Win32_Processor).Name; (Get-CimInstance Win32_Processor).NumberOfLogicalProcessors
Get-CimInstance Win32_Process -Filter "Name='srouter.exe'" | Select -Expand ProcessId | % { "other srouter running: $_" }
