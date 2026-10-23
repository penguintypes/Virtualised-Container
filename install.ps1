$ErrorActionPreference = 'Stop'
if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { wsl --install -d Ubuntu; Write-Host 'WSL installation started; reboot may be needed.'; exit 0 }
$path = & wsl.exe wslpath -a -u $PSScriptRoot
wsl.exe -d Ubuntu -- bash "$path/install.sh"
Start-Process wsl.exe -ArgumentList '-d','Ubuntu','--','bash','-lc','~/vcontainer/start.sh'
Start-Sleep -Seconds 12
Start-Process 'http://localhost:8080'
