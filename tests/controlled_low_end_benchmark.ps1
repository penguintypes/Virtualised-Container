param(
    [string]$Distro = "Ubuntu",
    [int]$MemoryGB = 1,
    [int]$Processors = 1,
    [int]$SwapMB = 256,
    [int]$Samples = 5,
    [int]$ContainerCount = 5
)

$ErrorActionPreference = "Stop"
$project = Split-Path $PSScriptRoot -Parent
$config = Join-Path $env:USERPROFILE ".wslconfig"
$backup = Join-Path $project ".wslconfig.benchmark-backup"
$hadConfig = Test-Path -LiteralPath $config
$originalRunning = @()

function ApiRequest {
    param([string]$Path, [string]$Method = "GET")
    Invoke-RestMethod -Uri "http://127.0.0.1:8010$Path" -Method $Method -TimeoutSec 30
}

function Wait-Api {
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        try {
            ApiRequest "/health" | Out-Null
            return
        } catch { Start-Sleep -Milliseconds 200 }
    }
    throw "Vcontainer API did not start"
}

function Start-WslApi {
    & wsl.exe -d $Distro -u root --exec systemctl restart vcontainer-api.service
    if ($LASTEXITCODE -ne 0) { throw "Could not start vcontainer-api.service" }
    Wait-Api
}

function Wait-Status {
    param([string]$Name, [string]$Expected)
    for ($attempt = 0; $attempt -lt 200; $attempt++) {
        try {
            $item = ApiRequest "/containers/$Name"
            if ($item.status -eq $Expected) { return $item }
            if ($Expected -eq "running" -and $item.status -eq "stopped" -and $item.exit_code -ne $null) {
                throw "$Name exited with code $($item.exit_code)"
            }
        } catch {
            if ($_.Exception.Message -like "*exited with code*") { throw }
        }
        Start-Sleep -Milliseconds 200
    }
    throw "$Name did not reach $Expected"
}

function Start-SavedContainers {
    param([string[]]$Names, [bool]$Strict)
    $started = [System.Collections.Generic.List[string]]::new()
    foreach ($name in $Names) {
        try {
            ApiRequest "/containers/$name/start" "POST" | Out-Null
            Wait-Status $name "running" | Out-Null
            $started.Add($name)
        } catch {
            if ($Strict) { throw }
            Write-Warning "Could not restart ${name}: $($_.Exception.Message)"
        }
    }
    return @($started)
}

try {
    try {
        $originalRunning = @((ApiRequest "/containers").containers |
            Where-Object status -eq "running" | ForEach-Object name)
    } catch {}

    if ($hadConfig) {
        Copy-Item -LiteralPath $config -Destination $backup -Force
    }

    @"
[wsl2]
memory=${MemoryGB}GB
processors=$Processors
swap=${SwapMB}MB
"@ | Set-Content -LiteralPath $config -Encoding ascii

    & wsl.exe --shutdown
    if ($LASTEXITCODE -ne 0) { throw "Could not shut down WSL" }
    Start-Sleep -Seconds 2
    Start-WslApi

    & (Join-Path $PSScriptRoot "lightweight_benchmark.ps1") `
        -Distro $Distro -Samples $Samples -ContainerCount $ContainerCount `
        -Output "performance_low_end_report.md"
    if ($LASTEXITCODE -ne 0) { throw "Low-end benchmark failed" }

    $ordered = @(
        "blogdrop-db", "blogdrop-backend",
        "blogdrop-frontend", "blogdrop-nginx"
    ) | Where-Object { $originalRunning -contains $_ }
    $ordered += @($originalRunning | Where-Object { $ordered -notcontains $_ })

    $stackStarted = Start-SavedContainers $ordered $true
    $stackHttp = "not tested"
    if ($stackStarted -contains "blogdrop-nginx") {
        for ($attempt = 0; $attempt -lt 100; $attempt++) {
            try {
                $watch = [Diagnostics.Stopwatch]::StartNew()
                $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 http://127.0.0.1:8080/
                $watch.Stop()
                if ($response.StatusCode -eq 200) {
                    $stackHttp = "$([Math]::Round($watch.Elapsed.TotalMilliseconds, 2)) ms"
                    break
                }
            } catch {}
            Start-Sleep -Milliseconds 500
        }
    }

    $limit = (& wsl.exe -d $Distro -u root --exec grep MemTotal /proc/meminfo).Trim()
    $cpuCount = (& wsl.exe -d $Distro -u root --exec nproc).Trim()
    Add-Content -LiteralPath (Join-Path $project "performance_low_end_report.md") -Value @"

## Controlled low-end stack test

- Configured WSL memory: ${MemoryGB} GiB
- Linux memory available under WSL limit: $limit
- Processors visible inside WSL: $cpuCount
- Configured swap: ${SwapMB} MiB
- Previously running containers restarted under constraint: $($stackStarted.Count)
- BlogDrop HTTP response time under constraint: $stackHttp
"@
}
finally {
    if ($hadConfig) {
        Move-Item -LiteralPath $backup -Destination $config -Force
    } else {
        Remove-Item -LiteralPath $config -Force -ErrorAction SilentlyContinue
    }

    & wsl.exe --shutdown
    Start-Sleep -Seconds 2
    try {
        Start-WslApi
        $restoreOrder = @(
            "blogdrop-db", "blogdrop-backend",
            "blogdrop-frontend", "blogdrop-nginx"
        ) | Where-Object { $originalRunning -contains $_ }
        $restoreOrder += @($originalRunning | Where-Object { $restoreOrder -notcontains $_ })
        Start-SavedContainers $restoreOrder $false | Out-Null
    } catch {
        Write-Warning "WSL configuration was restored, but workloads need manual restart: $($_.Exception.Message)"
    }
}
