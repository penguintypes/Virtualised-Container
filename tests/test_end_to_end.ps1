$ErrorActionPreference = 'Stop'
$project = Resolve-Path (Join-Path $PSScriptRoot '..')
wsl.exe -d Ubuntu -u root --exec bash "$(wsl.exe wslpath -a -u $project)\tests\rest_cases.sh"
