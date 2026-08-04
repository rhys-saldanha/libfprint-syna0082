param(
    [string]$AdapterPath = (
        'C:\Windows\System32\DriverStore\FileRepository\' +
        'synawudfbiousbpqidongleprod.inf_amd64_da5880249e9b8d68\' +
        'synaBscAdapter52.dll'
    )
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class Syna0082SensorNative
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern IntPtr LoadLibrary(string path);

    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, SetLastError = true)]
    public static extern IntPtr GetProcAddress(IntPtr module, string name);

    [DllImport("kernel32.dll")]
    public static extern bool FreeLibrary(IntPtr module);

    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    public delegate int QuerySensorInterface(out IntPtr sensorInterface);
}
'@

# WINBIO_SENSOR_INTERFACE_VERSION_3, in declaration order from winbio_adapter.h.
$functionNames = @(
    'Attach', 'Detach', 'ClearContext', 'QueryStatus', 'Reset', 'SetMode',
    'SetIndicatorStatus', 'GetIndicatorStatus', 'StartCapture', 'FinishCapture',
    'ExportSensorData', 'Cancel', 'PushDataToEngine', 'ControlUnit',
    'ControlUnitPrivileged', 'NotifyPowerChange', 'PipelineInit',
    'PipelineCleanup', 'Activate', 'Deactivate', 'QueryExtendedInfo',
    'QueryCalibrationFormats', 'SetCalibrationFormat', 'AcceptCalibrationData',
    'AsyncImportRawBuffer', 'AsyncImportSecureBuffer', 'QueryPrivateSensorType',
    'ConnectSecure', 'StartCaptureEx', 'StartNotifyWake', 'FinishNotifyWake'
)

$module = [Syna0082SensorNative]::LoadLibrary($AdapterPath)
if ($module -eq [IntPtr]::Zero) {
    throw "LoadLibrary failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
}

try {
    $address = [Syna0082SensorNative]::GetProcAddress($module, 'WbioQuerySensorInterface')
    if ($address -eq [IntPtr]::Zero) {
        throw 'WbioQuerySensorInterface export was not found'
    }
    $query = [Runtime.InteropServices.Marshal]::GetDelegateForFunctionPointer(
        $address,
        [type][Syna0082SensorNative+QuerySensorInterface]
    )
    $interface = [IntPtr]::Zero
    $result = $query.Invoke([ref]$interface)
    if ($result -ne 0 -or $interface -eq [IntPtr]::Zero) {
        throw ('WbioQuerySensorInterface failed with HRESULT 0x{0:X8}' -f $result)
    }

    $guidBytes = New-Object byte[] 16
    [Runtime.InteropServices.Marshal]::Copy([IntPtr]::Add($interface, 16), $guidBytes, 0, 16)
    $size = [Runtime.InteropServices.Marshal]::ReadInt64($interface, 8)
    $functions = [ordered]@{}
    for ($index = 0; $index -lt $functionNames.Count; $index++) {
        $offset = 32 + 8 * $index
        if ($offset + 8 -gt $size) {
            break
        }
        $pointer = [Runtime.InteropServices.Marshal]::ReadInt64($interface, $offset)
        $functions[$functionNames[$index]] = if ($pointer -eq 0) {
            $null
        }
        else {
            '0x{0:X}' -f ($pointer - $module.ToInt64())
        }
    }

    [ordered]@{
        hresult = ('0x{0:X8}' -f $result)
        version_major = [Runtime.InteropServices.Marshal]::ReadInt16($interface, 0)
        version_minor = [Runtime.InteropServices.Marshal]::ReadInt16($interface, 2)
        adapter_type = [Runtime.InteropServices.Marshal]::ReadInt32($interface, 4)
        interface_size = $size
        adapter_id = ([Guid]::new($guidBytes)).ToString()
        functions = $functions
    } | ConvertTo-Json -Depth 4
}
finally {
    [void][Syna0082SensorNative]::FreeLibrary($module)
}
