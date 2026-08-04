[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^\\\\\.\\USBPcap\d+$')]
    [string]$Interface,

    [Parameter(Mandatory)]
    [ValidateRange(0, 127)]
    [int]$DeviceAddress,

    [Parameter(Mandatory)]
    [ValidatePattern('^[a-z0-9][a-z0-9-]+$')]
    [string]$Name,

    [ValidateRange(1, 600)]
    [int]$DurationSeconds = 15,

    [string]$Action = 'unspecified',

    [string]$ExpectedOutcome = 'unspecified',

    [switch]$LockWorkstation,

    [string]$OutputDirectory = 'C:\fingerprint-lab\raw'
)

$ErrorActionPreference = 'Stop'
$usbPcap = 'C:\Program Files\USBPcap\USBPcapCMD.exe'
$capinfos = 'C:\Program Files\Wireshark\capinfos.exe'

foreach ($tool in @($usbPcap, $capinfos)) {
    if (-not (Test-Path -LiteralPath $tool)) {
        throw "Required tool is missing: $tool"
    }
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$capture = Join-Path $OutputDirectory "$Name.pcap"
$metadataPath = Join-Path $OutputDirectory "$Name.json"

foreach ($path in @($capture, $metadataPath)) {
    if (Test-Path -LiteralPath $path) {
        throw "Refusing to overwrite existing artifact: $path"
    }
}

$startedAt = (Get-Date).ToUniversalTime()
$arguments = @(
    '-d', $Interface,
    '-o', $capture,
    '--devices', $DeviceAddress,
    '--inject-descriptors'
)

$process = Start-Process -FilePath $usbPcap -ArgumentList $arguments -PassThru -WindowStyle Hidden

try {
    if ($LockWorkstation) {
        if ($DurationSeconds -le 3) {
            throw 'Lock-workstation captures must be longer than 3 seconds.'
        }
        Start-Sleep -Seconds 3
        Start-Process -FilePath 'rundll32.exe' -ArgumentList 'user32.dll,LockWorkStation'
        Start-Sleep -Seconds ($DurationSeconds - 3)
    } else {
        Start-Sleep -Seconds $DurationSeconds
    }
} finally {
    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id
    }
    $process.WaitForExit()
}

$endedAt = (Get-Date).ToUniversalTime()
if (-not (Test-Path -LiteralPath $capture)) {
    throw "USBPcap did not create $capture"
}

$captureFile = Get-Item -LiteralPath $capture
if ($captureFile.Length -lt 24) {
    throw "Capture is too short to contain a PCAP header: $capture"
}

$capinfosOutput = & $capinfos $capture 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "capinfos rejected the capture: $capinfosOutput"
}

$metadata = [ordered]@{
    schema = 1
    name = $Name
    started_at = $startedAt.ToString('o')
    ended_at = $endedAt.ToString('o')
    duration_seconds = $DurationSeconds
    interface = $Interface
    device_address = $DeviceAddress
    action = $Action
    expected_outcome = $ExpectedOutcome
    locked_workstation = [bool]$LockWorkstation
    capture = [ordered]@{
        path = $capture
        size = $captureFile.Length
        sha256 = (Get-FileHash -LiteralPath $capture -Algorithm SHA256).Hash
    }
    capinfos = @($capinfosOutput)
}

$metadata | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath $metadataPath -Encoding utf8NoBOM

$metadata | ConvertTo-Json -Depth 5
