param([string]$Ip, [string]$Script, [int]$WaitMs = 90000)
# copy a bash script into the VM (home dir), run it in the foreground, print its output
$name = Split-Path $Script -Leaf
$o = @("-o","BatchMode=yes","-o","StrictHostKeyChecking=no","-o","ConnectTimeout=8")
$p = Start-Process scp -ArgumentList ($o + @("`"$Script`"", "rb@${Ip}:$name")) -NoNewWindow -PassThru; $p.WaitForExit(30000) | Out-Null
$out = "$env:TEMP\vmexec_$name.txt"
$p = Start-Process ssh -ArgumentList ($o + @("rb@$Ip", "sed -i 's/\r$//' $name; bash $name 2>&1")) -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError "$out.err"
if (-not $p.WaitForExit($WaitMs)) { $p.Kill(); "TIMEOUT" }
Get-Content $out -ErrorAction SilentlyContinue | ForEach-Object { if ($_.Length -gt 240) { $_.Substring(0,240) } else { $_ } }
