param([string]$Ip, [string]$Script, [string]$Log)
# copy a script into the VM and run it detached (nohup), log in the VM's home
$name = Split-Path $Script -Leaf
$o = "-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=8"
$p = Start-Process scp -ArgumentList "$o `"$Script`" rb@${Ip}:$name" -NoNewWindow -PassThru; $p.WaitForExit(30000) | Out-Null
$p = Start-Process ssh -ArgumentList "$o rb@$Ip `"sed -i 's/\r$//' $name; nohup bash $name > $Log 2>&1 < /dev/null & echo started`"" -NoNewWindow -PassThru -RedirectStandardOutput "$env:TEMP\vmrun.txt"
if (-not $p.WaitForExit(30000)) { $p.Kill(); "TIMEOUT" }
Get-Content "$env:TEMP\vmrun.txt"
