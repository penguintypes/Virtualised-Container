# Forward all CLI arguments to the Linux runtime in WSL 2.
# Override the defaults with VCONTAINER_WSL_DISTRO and VCONTAINER_WSL_USER.
$ErrorActionPreference = 'Stop'
$distribution = if ($env:VCONTAINER_WSL_DISTRO) { $env:VCONTAINER_WSL_DISTRO } else { 'Ubuntu' }
$linuxUser = if ($env:VCONTAINER_WSL_USER) { $env:VCONTAINER_WSL_USER } else { 'vcdev' }
$cliArguments = @($args)
$scriptPath = Join-Path $PSScriptRoot 'run_container.sh'

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw 'WSL is required. Install Ubuntu on WSL 2 before using this launcher.'
}

$linuxScriptPath = & wsl.exe -d $distribution -u $linuxUser --exec wslpath -a -u $scriptPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& wsl.exe -d $distribution -u $linuxUser --exec bash "$linuxScriptPath" @cliArguments
exit $LASTEXITCODE
