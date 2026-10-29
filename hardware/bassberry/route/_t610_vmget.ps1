param([string]$Ip, [string]$FileList, [string]$Dest = "D:\vm\xfer\out")
# copy files from a VM's ~/bench to the T610 host (then the G7 pulls them with scp)
New-Item -ItemType Directory -Force $Dest | Out-Null
$o = "-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8"
foreach ($f in ($FileList -split ';')) {
  $p = Start-Process scp -ArgumentList "$o rb@${Ip}:bench/$f `"$Dest\$f`"" -NoNewWindow -PassThru
  if (-not $p.WaitForExit(120000)) { $p.Kill(); "TIMEOUT $f" } else { "got $f rc=$($p.ExitCode) $((Get-Item "$Dest\$f" -ErrorAction SilentlyContinue).Length) bytes" }
}
