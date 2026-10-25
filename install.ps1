$ErrorActionPreference = 'Stop'
$d = if ($env:VC_DISTRO) { $env:VC_DISTRO } else { 'Ubuntu' }
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { wsl --install -d $d; Write-Host 'WSL installation started; reboot may be needed.'; exit 0 }
$p = $PSScriptRoot -replace '\\','/'
if ($p -match '^//wsl(\.localhost|\$)/[^/]+(/.*)$') { $path = $Matches[2] } else { $path = & wsl.exe -d $d wslpath -a -u $p }
wsl.exe -d $d -- bash "$path/install.sh"
if ($LASTEXITCODE -ne 0) { Write-Host 'install.sh failed; not starting.'; exit 1 }
Start-Process wsl.exe -ArgumentList '-d',$d,'--','bash','-lc',"'$path/start.sh'"
for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest http://localhost:8080 -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 } }
Start-Process 'http://localhost:8080'
