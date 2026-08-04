param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^USB\\VID_06CB&PID_0082\\[^\\]+$')]
    [string]$InstanceId,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

if (Test-Path -LiteralPath $OutputPath) {
    throw "Refusing to overwrite $OutputPath"
}

$parent = Split-Path -Parent $OutputPath
if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
    throw "Output directory does not exist: $parent"
}

Add-Type -AssemblyName System.Security

$registryPath = 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\' +
    $InstanceId + '\Device Parameters\Device Data'
$protected = Get-ItemPropertyValue -LiteralPath $registryPath -Name CalibrationData
$plain = [System.Security.Cryptography.ProtectedData]::Unprotect(
    $protected,
    $null,
    [System.Security.Cryptography.DataProtectionScope]::LocalMachine
)

try {
    [System.IO.File]::WriteAllBytes($OutputPath, $plain)
}
finally {
    [Array]::Clear($plain, 0, $plain.Length)
}
