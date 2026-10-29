param([string]$Ip, [string]$FileList, [string]$Dest = "bench")
$Files = $FileList -split ';'
$o = "-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8"
$p = Start-Process ssh -ArgumentList "$o rb@$Ip `"mkdir -p $Dest`"" -NoNewWindow -PassThru; $p.WaitForExit(20000) | Out-Null
foreach ($f in $Files) {
  $p = Start-Process scp -ArgumentList "$o `"$f`" rb@${Ip}:$Dest/" -NoNewWindow -PassThru
  if (-not $p.WaitForExit(120000)) { $p.Kill(); "TIMEOUT $f" } else { "put $f rc=$($p.ExitCode)" }
}
