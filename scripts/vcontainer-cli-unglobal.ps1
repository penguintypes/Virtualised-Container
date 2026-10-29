$ErrorActionPreference = "Stop"
$installDirectory = Split-Path -Parent $PSScriptRoot
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$comparison = [StringComparer]::OrdinalIgnoreCase
$entries = @(
    $userPath -split ";" |
        Where-Object { $_ } |
        ForEach-Object { $_.TrimEnd("\") }
)
$updated = @(
    $entries | Where-Object {
        -not $comparison.Equals($_, $installDirectory)
    }
)

if ($updated.Count -eq $entries.Count) {
    Write-Host "Vcontainer is not in the user PATH."
    exit 0
}

[Environment]::SetEnvironmentVariable(
    "Path",
    ($updated -join ";"),
    "User"
)

Write-Host "Removed Vcontainer from the user PATH."
Write-Host "Open a new terminal to apply the change."
