$ErrorActionPreference = "Stop"
$installDirectory = Split-Path -Parent $PSScriptRoot
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$entries = @(
    $userPath -split ";" |
        Where-Object { $_ } |
        ForEach-Object { $_.TrimEnd("\") }
)
$comparison = [StringComparer]::OrdinalIgnoreCase

if (-not (Test-Path (Join-Path $installDirectory "vcontainer.exe"))) {
    throw "vcontainer.exe was not found in $installDirectory"
}

$alreadyInstalled = $entries | Where-Object {
    $comparison.Equals($_, $installDirectory)
}

if (-not $alreadyInstalled) {
    [Environment]::SetEnvironmentVariable(
        "Path",
        ((@($entries) + $installDirectory) -join ";"),
        "User"
    )
    Write-Host "Added Vcontainer to the user PATH."
} else {
    Write-Host "Vcontainer is already in the user PATH."
}

Write-Host "Open a new terminal, then run: vcontainer ps"
