param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^USB\\VID_06CB&PID_0082\\[^\\]+$')]
    [string]$InstanceId,

    [string]$OutputDirectory = 'C:\fingerprint-lab\raw'
)

$ErrorActionPreference = 'Stop'

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$currentPrincipal = New-Object System.Security.Principal.WindowsPrincipal($identity)
if (-not $currentPrincipal.IsInRole(
    [System.Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    throw 'This launcher must run from an elevated PowerShell process'
}

$worker = Join-Path $PSScriptRoot 'inspect-windows-calibration.ps1'
if (-not (Test-Path -LiteralPath $worker -PathType Leaf)) {
    throw "Worker script does not exist: $worker"
}

$jobs = @(
    [ordered]@{
        TaskName = 'Syna0082CalibrationInspectSystem'
        UserId = 'SYSTEM'
        Output = Join-Path $OutputDirectory 'calibration-dpapi-system.json'
    },
    [ordered]@{
        TaskName = 'Syna0082CalibrationInspectLocalService'
        UserId = 'NT AUTHORITY\LOCAL SERVICE'
        Output = Join-Path $OutputDirectory 'calibration-dpapi-local-service.json'
    }
)

$decrypted = $false
foreach ($job in $jobs) {
    if (Get-ScheduledTask -TaskName $job.TaskName -ErrorAction SilentlyContinue) {
        throw "Refusing to replace existing task $($job.TaskName)"
    }
    if (Test-Path -LiteralPath $job.Output) {
        throw "Refusing to overwrite $($job.Output)"
    }
}

foreach ($job in $jobs) {
    $arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ' +
        '"' + $worker + '" -InstanceId "' + $InstanceId +
        '" -OutputPath "' + $job.Output + '"'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $job.UserId -LogonType ServiceAccount -RunLevel Highest

    try {
        Register-ScheduledTask -TaskName $job.TaskName -Action $action -Principal $taskPrincipal | Out-Null
        Start-ScheduledTask -TaskName $job.TaskName

        $deadline = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $deadline) {
            if (Test-Path -LiteralPath $job.Output) {
                break
            }
            Start-Sleep -Milliseconds 250
        }
        if (-not (Test-Path -LiteralPath $job.Output)) {
            $info = Get-ScheduledTaskInfo -TaskName $job.TaskName
            throw "Task did not produce output; last result $($info.LastTaskResult)"
        }
        $jobResult = Get-Content -LiteralPath $job.Output -Raw |
            ConvertFrom-Json
        $decrypted = @($jobResult.attempts |
            Where-Object { $_.success }).Count -gt 0
    }
    finally {
        if (Get-ScheduledTask -TaskName $job.TaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $job.TaskName -Confirm:$false
        }
    }
    if ($decrypted) {
        break
    }
}

$jobs | ForEach-Object {
    if (Test-Path -LiteralPath $_.Output) {
        Get-Content -LiteralPath $_.Output -Raw
    }
}
