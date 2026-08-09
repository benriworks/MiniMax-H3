function ConvertTo-MetricNumber {
    param([AllowNull()] $Value)

    if ($null -eq $Value) {
        return $null
    }

    $text = ([string] $Value).Trim()
    if (-not $text -or $text -eq '[N/A]' -or $text -eq 'N/A') {
        return $null
    }

    $number = 0.0
    $parsed = [double]::TryParse(
        $text,
        [System.Globalization.NumberStyles]::Float,
        [System.Globalization.CultureInfo]::InvariantCulture,
        [ref] $number
    )
    if ($parsed) {
        return $number
    }
    return $null
}

function ConvertFrom-NvidiaSmiCsvRow {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Line,

        [switch] $IncludesPower
    )

    $expectedFields = if ($IncludesPower) { 6 } else { 5 }
    $fields = [regex]::Split($Line.Trim(), '\s*,\s*', $expectedFields)
    if ($fields.Count -ne $expectedFields) {
        return $null
    }

    [pscustomobject]@{
        Name = $fields[0]
        UtilizationPercent = ConvertTo-MetricNumber $fields[1]
        TemperatureCelsius = ConvertTo-MetricNumber $fields[2]
        MemoryUsedMiB = ConvertTo-MetricNumber $fields[3]
        MemoryTotalMiB = ConvertTo-MetricNumber $fields[4]
        PowerWatts = if ($IncludesPower) { ConvertTo-MetricNumber $fields[5] } else { $null }
    }
}

function ConvertFrom-AcpiTenthsKelvin {
    param([AllowNull()] $Value)

    $tenthsKelvin = ConvertTo-MetricNumber $Value
    if ($null -eq $tenthsKelvin) {
        return $null
    }

    $celsius = ($tenthsKelvin / 10.0) - 273.15
    if ($celsius -lt -20.0 -or $celsius -gt 150.0) {
        return $null
    }
    return $celsius
}

function Get-CpuTemperatureMetric {
    $sensorProviders = @(
        @{ Namespace = 'root\LibreHardwareMonitor'; Source = 'LibreHardwareMonitor WMI' },
        @{ Namespace = 'root\OpenHardwareMonitor'; Source = 'OpenHardwareMonitor WMI' }
    )

    foreach ($provider in $sensorProviders) {
        try {
            $sensors = @(Get-CimInstance -Namespace $provider.Namespace -ClassName Sensor -ErrorAction Stop)
            $cpuSensors = @(
                $sensors | Where-Object {
                    $_.SensorType -eq 'Temperature' -and
                    (([string] $_.Identifier) -match '/(intelcpu|amdcpu)/' -or
                     ([string] $_.Name) -match 'CPU|Core')
                }
            )
            if ($cpuSensors.Count -gt 0) {
                $preferred = @($cpuSensors | Where-Object { ([string] $_.Name) -match 'Package' } | Select-Object -First 1)
                if ($preferred.Count -eq 0) {
                    $preferred = @($cpuSensors | Where-Object { ([string] $_.Name) -match 'Average' } | Select-Object -First 1)
                }
                if ($preferred.Count -eq 0) {
                    $preferred = @($cpuSensors | Sort-Object -Property Value -Descending | Select-Object -First 1)
                }

                $value = ConvertTo-MetricNumber $preferred[0].Value
                if ($null -ne $value) {
                    return [pscustomobject]@{
                        Available = $true
                        Celsius = $value
                        Label = ([string] $preferred[0].Name)
                        Source = $provider.Source
                    }
                }
            }
        }
        catch {
            # Optional sensor provider is not installed or not exposing WMI.
        }
    }

    try {
        $thermalZones = @(
            Get-CimInstance -Namespace 'root\wmi' -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop
        )
        $validZones = @(
            $thermalZones | ForEach-Object {
                $value = ConvertFrom-AcpiTenthsKelvin $_.CurrentTemperature
                if ($null -ne $value) {
                    [pscustomobject]@{ Celsius = $value; Name = ([string] $_.InstanceName) }
                }
            }
        )
        if ($validZones.Count -gt 0) {
            $hottest = $validZones | Sort-Object -Property Celsius -Descending | Select-Object -First 1
            return [pscustomobject]@{
                Available = $true
                Celsius = $hottest.Celsius
                Label = 'ACPI thermal zone (not CPU package)'
                Source = 'Windows firmware thermal zone'
            }
        }
    }
    catch {
        # Many desktop firmware implementations expose no ACPI thermal zone to Windows.
    }

    return [pscustomobject]@{
        Available = $false
        Celsius = $null
        Label = 'CPU temperature'
        Source = 'No CPU sensor exposed to Windows; optional hardware-monitor WMI is not running'
    }
}

function Get-NvidiaGpuMetrics {
    $nvidiaSmi = Get-Command 'nvidia-smi.exe' -ErrorAction SilentlyContinue
    if ($null -eq $nvidiaSmi) {
        $nvidiaSmi = Get-Command 'nvidia-smi' -ErrorAction SilentlyContinue
    }
    if ($null -eq $nvidiaSmi) {
        return @()
    }

    $queryWithPower = 'name,utilization.gpu,temperature.gpu,memory.used,memory.total,power.draw'
    $rows = @(& $nvidiaSmi.Source "--query-gpu=$queryWithPower" '--format=csv,noheader,nounits' 2>$null)
    $exitCode = $LASTEXITCODE
    $includesPower = $true

    if ($exitCode -ne 0) {
        $queryWithoutPower = 'name,utilization.gpu,temperature.gpu,memory.used,memory.total'
        $rows = @(& $nvidiaSmi.Source "--query-gpu=$queryWithoutPower" '--format=csv,noheader,nounits' 2>$null)
        $exitCode = $LASTEXITCODE
        $includesPower = $false
    }
    if ($exitCode -ne 0) {
        return @()
    }

    return @(
        $rows | ForEach-Object {
            if ([string] $_) {
                ConvertFrom-NvidiaSmiCsvRow -Line ([string] $_) -IncludesPower:$includesPower
            }
        } | Where-Object { $null -ne $_ }
    )
}

function Get-SystemMetricsSnapshot {
    $cpuLoad = $null
    try {
        $processors = @(Get-CimInstance -ClassName Win32_Processor -ErrorAction Stop)
        if ($processors.Count -gt 0) {
            $average = $processors | Measure-Object -Property LoadPercentage -Average
            $cpuLoad = ConvertTo-MetricNumber $average.Average
        }
    }
    catch {
        $cpuLoad = $null
    }

    $memoryUsedGiB = $null
    $memoryTotalGiB = $null
    $memoryPercent = $null
    try {
        $operatingSystem = Get-CimInstance -ClassName Win32_OperatingSystem -ErrorAction Stop
        $totalKiB = ConvertTo-MetricNumber $operatingSystem.TotalVisibleMemorySize
        $freeKiB = ConvertTo-MetricNumber $operatingSystem.FreePhysicalMemory
        if ($null -ne $totalKiB -and $null -ne $freeKiB -and $totalKiB -gt 0) {
            $memoryTotalGiB = $totalKiB / 1MB
            $memoryUsedGiB = ($totalKiB - $freeKiB) / 1MB
            $memoryPercent = (($totalKiB - $freeKiB) / $totalKiB) * 100.0
        }
    }
    catch {
        # Keep memory fields unavailable; telemetry must never block application launch.
    }

    [pscustomobject]@{
        Timestamp = Get-Date
        CpuLoadPercent = $cpuLoad
        CpuTemperature = Get-CpuTemperatureMetric
        MemoryUsedGiB = $memoryUsedGiB
        MemoryTotalGiB = $memoryTotalGiB
        MemoryUsedPercent = $memoryPercent
        Gpus = @(Get-NvidiaGpuMetrics)
    }
}

function Show-SystemMetrics {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('START', 'END')]
        [string] $Phase,

        [AllowNull()]
        [datetime] $StartedAt
    )

    try {
        $snapshot = Get-SystemMetricsSnapshot
        Write-Host ''
        Write-Host "=== System metrics: $Phase ==="
        Write-Host ("Time: {0}" -f $snapshot.Timestamp.ToString('yyyy-MM-dd HH:mm:ss zzz'))
        if ($Phase -eq 'END' -and $null -ne $StartedAt) {
            $elapsed = $snapshot.Timestamp - $StartedAt
            Write-Host ("Elapsed: {0:hh\:mm\:ss}" -f $elapsed)
        }

        $cpuUsageText = if ($null -ne $snapshot.CpuLoadPercent) {
            '{0:N0}%' -f $snapshot.CpuLoadPercent
        }
        else {
            'unavailable'
        }
        if ($snapshot.CpuTemperature.Available) {
            Write-Host ("CPU: usage {0} | {1} {2:N1} C ({3})" -f
                $cpuUsageText,
                $snapshot.CpuTemperature.Label,
                $snapshot.CpuTemperature.Celsius,
                $snapshot.CpuTemperature.Source)
        }
        else {
            Write-Host ("CPU: usage {0} | temperature unavailable ({1})" -f
                $cpuUsageText,
                $snapshot.CpuTemperature.Source)
        }

        if ($null -ne $snapshot.MemoryTotalGiB) {
            Write-Host ("RAM: {0:N1}/{1:N1} GiB used ({2:N0}%)" -f
                $snapshot.MemoryUsedGiB,
                $snapshot.MemoryTotalGiB,
                $snapshot.MemoryUsedPercent)
        }
        else {
            Write-Host 'RAM: unavailable'
        }

        if ($snapshot.Gpus.Count -eq 0) {
            Write-Host 'GPU: NVIDIA metrics unavailable'
        }
        else {
            for ($index = 0; $index -lt $snapshot.Gpus.Count; $index++) {
                $gpu = $snapshot.Gpus[$index]
                $gpuUsage = if ($null -ne $gpu.UtilizationPercent) { '{0:N0}%' -f $gpu.UtilizationPercent } else { 'unavailable' }
                $gpuTemperature = if ($null -ne $gpu.TemperatureCelsius) { '{0:N0} C' -f $gpu.TemperatureCelsius } else { 'unavailable' }
                $gpuMemory = if ($null -ne $gpu.MemoryUsedMiB -and $null -ne $gpu.MemoryTotalMiB) {
                    '{0:N0}/{1:N0} MiB' -f $gpu.MemoryUsedMiB, $gpu.MemoryTotalMiB
                }
                else {
                    'unavailable'
                }
                $gpuPower = if ($null -ne $gpu.PowerWatts) { ' | power {0:N1} W' -f $gpu.PowerWatts } else { '' }
                Write-Host ("GPU {0} ({1}): usage {2} | temperature {3} | VRAM {4}{5}" -f
                    $index, $gpu.Name, $gpuUsage, $gpuTemperature, $gpuMemory, $gpuPower)
            }
        }
        Write-Host '============================='
    }
    catch {
        Write-Warning "System metrics could not be collected: $($_.Exception.Message)"
    }
}
