param(
    [string]$ApiUrl = "http://127.0.0.1:8010",
    [string]$Distro = "Ubuntu",
    [int]$Samples = 10,
    [int]$ContainerCount = 5,
    [string]$Output = "performance_report.md"
)

$ErrorActionPreference = "Stop"
$created = [System.Collections.Generic.List[string]]::new()

function ApiRequest {
    param([string]$Path, [string]$Method = "GET", $Body = $null)
    $parameters = @{Uri = "$ApiUrl$Path"; Method = $Method; TimeoutSec = 30}
    if ($null -ne $Body) {
        $parameters.ContentType = "application/json"
        $parameters.Body = $Body | ConvertTo-Json -Compress -Depth 8
    }
    try {
        Invoke-RestMethod @parameters
    } catch {
        $detail = $_.ErrorDetails.Message
        if (-not $detail) { $detail = $_.Exception.Message }
        throw "$Method $Path failed: $detail"
    }
}

function Remove-BenchmarkContainer {
    param([string]$Name)
    $lastError = $null
    try {
        $current = ApiRequest "/containers/$Name"
        if ($current.status -eq "running") {
            try { ApiRequest "/containers/$Name/stop" "POST" | Out-Null } catch {}
            Wait-ContainerStatus $Name "stopped" 20000 | Out-Null
        }
    } catch {
        if ($_.Exception.Message -notlike "*404*") { $lastError = $_ }
    }

    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            ApiRequest "/containers/$Name" "DELETE" | Out-Null
            return
        } catch {
            $lastError = $_
            Start-Sleep -Seconds 2
        }
    }
    throw "Could not remove benchmark container $Name after 5 attempts: $lastError"
}

function Wait-ContainerStatus {
    param([string]$Name, [string]$Status, [int]$TimeoutMilliseconds = 10000)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    while ($watch.ElapsedMilliseconds -lt $TimeoutMilliseconds) {
        try {
            $container = ApiRequest "/containers/$Name"
            if ($container.status -eq $Status) { return $container }
        } catch {}
        Start-Sleep -Milliseconds 50
    }
    throw "Container $Name did not reach $Status"
}

function WslValue {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $value = & wsl.exe -d $Distro -u root --exec @Arguments
    if ($LASTEXITCODE -ne 0) { throw "WSL command failed: $($Arguments -join ' ')" }
    ($value | Out-String).Trim()
}

function Percentile {
    param([double[]]$Values, [double]$Percent)
    $ordered = @($Values | Sort-Object)
    if (-not $ordered.Count) { return 0 }
    $index = [Math]::Ceiling($Percent * $ordered.Count) - 1
    [Math]::Round($ordered[[Math]::Max(0, $index)], 2)
}

function WslMemoryBytes {
    $process = Get-Process -Name "vmmemWSL" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $process) { return 0 }
    [int64]$process.WorkingSet64
}

try {
    ApiRequest "/health" | Out-Null
    $initialContainers = @(ApiRequest "/containers").containers
    $initialRunning = @($initialContainers | Where-Object status -eq "running").Count

    $apiMemory = [int64](WslValue systemctl show vcontainer-api.service --property=MemoryCurrent --value)
    $apiPeak = [int64](WslValue systemctl show vcontainer-api.service --property=MemoryPeak --value)
    $apiTasks = [int](WslValue systemctl show vcontainer-api.service --property=TasksCurrent --value)
    $wslBefore = WslMemoryBytes

    $apiTimes = [System.Collections.Generic.List[double]]::new()
    1..$Samples | ForEach-Object {
        $watch = [Diagnostics.Stopwatch]::StartNew()
        ApiRequest "/containers" | Out-Null
        $watch.Stop()
        $apiTimes.Add($watch.Elapsed.TotalMilliseconds)
    }

    $startupTimes = [System.Collections.Generic.List[double]]::new()
    1..$Samples | ForEach-Object {
        $name = "perf-start-$_-$PID"
        $watch = [Diagnostics.Stopwatch]::StartNew()
        ApiRequest "/containers" "POST" @{
            name = $name; image = "alpine"; command = @("/bin/sleep", "2")
        } | Out-Null
        $created.Add($name)
        Wait-ContainerStatus $name "running" | Out-Null
        $watch.Stop()
        $startupTimes.Add($watch.Elapsed.TotalMilliseconds)
        Wait-ContainerStatus $name "stopped" 20000 | Out-Null
        Remove-BenchmarkContainer $name
        $created.Remove($name) | Out-Null
    }

    $wslBeforeFive = WslMemoryBytes
    1..$ContainerCount | ForEach-Object {
        $name = "perf-idle-$_-$PID"
        ApiRequest "/containers" "POST" @{
            name = $name; image = "alpine"; command = @("/bin/sleep", "120")
        } | Out-Null
        $created.Add($name)
    }
    foreach ($name in $created) { Wait-ContainerStatus $name "running" | Out-Null }
    Start-Sleep -Seconds 2

    $containerMemory = 0L
    foreach ($name in $created) {
        $metric = ApiRequest "/containers/$name/metrics"
        $containerMemory += [int64]($metric.memory_used_bytes ?? 0)
    }
    $wslAfterFive = WslMemoryBytes

    $httpTimes = [System.Collections.Generic.List[double]]::new()
    try {
        1..$Samples | ForEach-Object {
            $watch = [Diagnostics.Stopwatch]::StartNew()
            Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 http://127.0.0.1:8080/ | Out-Null
            $watch.Stop()
            $httpTimes.Add($watch.Elapsed.TotalMilliseconds)
        }
    } catch {
        $httpTimes.Clear()
    }

    $sizes = @{}
    foreach ($entry in @{
        runtime = "/opt/vcontainer"
        api = "/home/vcdev/vcontainer-api"
        images = "/var/lib/vcontainer/images"
        containers = "/var/lib/vcontainer/containers"
    }.GetEnumerator()) {
        $sizes[$entry.Key] = [int64]((WslValue du -sb $entry.Value).Split()[0])
    }
    $binarySize = [int64](WslValue stat -c "%s" /opt/vcontainer/bin/vcontainer)

    $apiAverage = [Math]::Round(($apiTimes | Measure-Object -Average).Average, 2)
    $startupAverage = [Math]::Round(($startupTimes | Measure-Object -Average).Average, 2)
    $wslDelta = [Math]::Max(0, $wslAfterFive - $wslBeforeFive)
    $perContainerDelta = if ($ContainerCount) { [Math]::Round($wslDelta / $ContainerCount) } else { 0 }
    $httpAverage = if ($httpTimes.Count) { [Math]::Round(($httpTimes | Measure-Object -Average).Average, 2) } else { $null }

    $report = @"
# Vcontainer lightweight performance report

Generated: $(Get-Date -Format o)

## Test context

- WSL distribution: $Distro
- Logical processors exposed to WSL: $(WslValue nproc)
- Linux memory available under WSL limit: $(WslValue grep MemTotal /proc/meminfo)
- Containers already running before benchmark: $initialRunning
- Samples per latency test: $Samples

## Results

| Measurement | Result |
| --- | ---: |
| API service current memory | $([Math]::Round($apiMemory / 1MB, 2)) MiB |
| API service peak memory | $([Math]::Round($apiPeak / 1MB, 2)) MiB |
| API service tasks | $apiTasks |
| Total WSL working set before benchmark | $([Math]::Round($wslBefore / 1MB, 2)) MiB |
| Container-list API average | $apiAverage ms |
| Container-list API p95 | $(Percentile $apiTimes 0.95) ms |
| Warm Alpine startup average | $startupAverage ms |
| Warm Alpine startup p95 | $(Percentile $startupTimes 0.95) ms |
| Sum of cgroup memory for $ContainerCount idle Alpine containers | $([Math]::Round($containerMemory / 1MB, 2)) MiB |
| WSL working-set increase for $ContainerCount idle containers | $([Math]::Round($wslDelta / 1MB, 2)) MiB |
| Approximate WSL increase per idle container | $([Math]::Round($perContainerDelta / 1MB, 2)) MiB |
| BlogDrop HTTP average | $(if ($null -eq $httpAverage) { "not available" } else { "$httpAverage ms" }) |
| BlogDrop HTTP p95 | $(if ($httpTimes.Count) { "$(Percentile $httpTimes 0.95) ms" } else { "not available" }) |
| Runtime binary size | $([Math]::Round($binarySize / 1KB, 2)) KiB |
| Installed runtime directory | $([Math]::Round($sizes.runtime / 1MB, 2)) MiB |
| Python API environment | $([Math]::Round($sizes.api / 1MB, 2)) MiB |
| Downloaded images | $([Math]::Round($sizes.images / 1MB, 2)) MiB |
| Container writable state | $([Math]::Round($sizes.containers / 1MB, 2)) MiB |

## Interpretation

The API-service value isolates Vcontainer's always-running control-plane cost.
The total WSL value also includes the Linux kernel, filesystem cache, systemd,
the four-container demo stack, and other WSL processes, so it must not be
reported as Vcontainer-only memory. The five-container cgroup total is the most
useful measurement of incremental idle workload memory.
"@

    $outputPath = Join-Path (Split-Path $PSScriptRoot -Parent) $Output
    Set-Content -LiteralPath $outputPath -Value $report -Encoding utf8
    $report
    "Saved report: $outputPath"
}
finally {
    foreach ($name in @($created)) {
        try { Remove-BenchmarkContainer $name } catch {
            Write-Warning $_.Exception.Message
        }
    }
}
