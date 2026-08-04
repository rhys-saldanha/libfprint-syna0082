[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$targetPattern = 'VID_06CB&PID_0082'
$operatingSystem = Get-CimInstance Win32_OperatingSystem

$pnpDevices = Get-PnpDevice -PresentOnly |
    Where-Object InstanceId -Like "*$targetPattern*"

$signedDrivers = Get-CimInstance Win32_PnPSignedDriver |
    Where-Object DeviceId -Like "*$targetPattern*" |
    Select-Object DeviceName, Manufacturer, DriverProviderName, DriverVersion,
        DriverDate, InfName, IsSigned, Signer

$usbPcap = Get-Command USBPcapCMD.exe -ErrorAction SilentlyContinue
$tshark = Get-Command tshark.exe -ErrorAction SilentlyContinue
$usbPcapPath = if ($usbPcap) {
    $usbPcap.Source
} elseif (Test-Path 'C:\Program Files\USBPcap\USBPcapCMD.exe') {
    'C:\Program Files\USBPcap\USBPcapCMD.exe'
} else {
    $null
}
$tsharkPath = if ($tshark) {
    $tshark.Source
} elseif (Test-Path 'C:\Program Files\Wireshark\tshark.exe') {
    'C:\Program Files\Wireshark\tshark.exe'
} else {
    $null
}

[ordered]@{
    collected_at = (Get-Date).ToUniversalTime().ToString('o')
    computer = $env:COMPUTERNAME
    windows = [ordered]@{
        product = $operatingSystem.Caption
        version = $operatingSystem.Version
        architecture = $operatingSystem.OSArchitecture
    }
    devices = @($pnpDevices | Select-Object Status, Class, FriendlyName,
        InstanceId)
    drivers = @($signedDrivers)
    tools = [ordered]@{
        usbpcap = $usbPcapPath
        tshark = $tsharkPath
    }
} | ConvertTo-Json -Depth 6
