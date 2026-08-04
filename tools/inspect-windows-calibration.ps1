param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^USB\\VID_06CB&PID_0082\\[^\\]+$')]
    [string]$InstanceId,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [string]$CaptureDirectory = 'C:\fingerprint-lab\raw',
    [string]$Tshark = 'C:\Program Files\Wireshark\tshark.exe'
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
Add-Type -TypeDefinition @'
using System;

public static class Syna0082ByteSearch
{
    public static int IndexOf(byte[] haystack, byte[] needle)
    {
        if (haystack == null || needle == null || needle.Length == 0)
            return -1;
        int limit = haystack.Length - needle.Length;
        for (int i = 0; i <= limit; i++)
        {
            int j = 0;
            while (j < needle.Length && haystack[i + j] == needle[j])
                j++;
            if (j == needle.Length)
                return i;
        }
        return -1;
    }
}
'@

function Get-Sha256Hex {
    param([byte[]]$Bytes)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-', '')
    }
    finally {
        $algorithm.Dispose()
    }
}

function Convert-HexToBytes {
    param([string]$Hex)
    if (($Hex.Length % 2) -ne 0 -or $Hex -notmatch '^[0-9a-fA-F]*$') {
        throw 'Invalid hexadecimal USB payload'
    }
    $bytes = New-Object byte[] ($Hex.Length / 2)
    for ($index = 0; $index -lt $bytes.Length; $index++) {
        $bytes[$index] = [Convert]::ToByte($Hex.Substring($index * 2, 2), 16)
    }
    return $bytes
}

function Get-Entropy {
    param([byte[]]$Bytes)
    $counts = New-Object long[] 256
    foreach ($value in $Bytes) {
        $counts[$value]++
    }
    $entropy = 0.0
    foreach ($count in $counts) {
        if ($count -eq 0) {
            continue
        }
        $probability = $count / [double]$Bytes.Length
        $entropy -= $probability * [Math]::Log($probability, 2)
    }
    return $entropy
}

function Get-PayloadRelations {
    param([byte[]]$Plaintext)

    if (-not (Test-Path -LiteralPath $Tshark -PathType Leaf)) {
        return @()
    }

    $seen = @{}
    $relations = @()
    $captures = Get-ChildItem -LiteralPath $CaptureDirectory -Filter '*.pcap' -File
    foreach ($capture in $captures) {
        $tsharkArguments = @(
            '-n', '-r', $capture.FullName,
            '-Y', 'usb.endpoint_address == 0x01 && usb.capdata',
            '-T', 'fields',
            '-E', 'quote=n',
            '-E', 'occurrence=f',
            '-e', 'usb.capdata'
        )
        $payloadLines = & $Tshark @tsharkArguments 2>$null
        foreach ($line in $payloadLines) {
            if ([string]::IsNullOrWhiteSpace($line)) {
                continue
            }
            $payload = Convert-HexToBytes $line.Trim()
            if ($payload.Length -lt 100) {
                continue
            }
            $hash = Get-Sha256Hex $payload
            if ($seen.ContainsKey($hash)) {
                continue
            }
            $seen[$hash] = $true

            $exactOffset = [Syna0082ByteSearch]::IndexOf($Plaintext, $payload)
            $sampled = 0
            $matched = 0
            for ($offset = 0; $offset + 64 -le $payload.Length; $offset += 256) {
                $chunk = New-Object byte[] 64
                [Array]::Copy($payload, $offset, $chunk, 0, 64)
                $sampled++
                if ([Syna0082ByteSearch]::IndexOf($Plaintext, $chunk) -ge 0) {
                    $matched++
                }
            }

            $relations += [ordered]@{
                capture = $capture.Name
                payload_length = $payload.Length
                payload_sha256 = $hash
                exact_offset_in_plaintext = $exactOffset
                sampled_64_byte_chunks = $sampled
                matched_64_byte_chunks = $matched
            }
        }
    }
    return $relations
}

$registryPath = 'Registry::HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Enum\' +
    $InstanceId + '\Device Parameters\Device Data'
$protected = Get-ItemPropertyValue -LiteralPath $registryPath -Name CalibrationData

$result = [ordered]@{
    schema = 1
    collected_at = (Get-Date).ToUniversalTime().ToString('o')
    account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    usb_id = '06cb:0082'
    protected_length = $protected.Length
    protected_sha256 = Get-Sha256Hex $protected
    attempts = @()
}

foreach ($scope in @(
    [System.Security.Cryptography.DataProtectionScope]::CurrentUser,
    [System.Security.Cryptography.DataProtectionScope]::LocalMachine
)) {
    try {
        $plain = [System.Security.Cryptography.ProtectedData]::Unprotect(
            $protected,
            $null,
            $scope
        )
        $result.attempts += [ordered]@{
            scope = $scope.ToString()
            success = $true
            plaintext_length = $plain.Length
            plaintext_sha256 = Get-Sha256Hex $plain
            entropy_bits_per_byte = Get-Entropy $plain
            payload_relations = @(Get-PayloadRelations $plain)
        }
        [Array]::Clear($plain, 0, $plain.Length)
    }
    catch {
        $result.attempts += [ordered]@{
            scope = $scope.ToString()
            success = $false
            error_type = $_.Exception.GetType().FullName
        }
    }
}

$result | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $OutputPath -Encoding UTF8
