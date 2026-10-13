param(
    [Parameter(Mandatory = $true)][string]$ApplicationRoot,
    [string]$ShortcutPath
)
$ErrorActionPreference = 'Stop'
$taskRoot = (Resolve-Path -LiteralPath $ApplicationRoot).Path
$taskLauncher = Join-Path $taskRoot 'ORSI.cmd'
$taskPython = Join-Path $taskRoot 'runtime\python\pythonw.exe'
$taskIcon = Join-Path $taskRoot 'app\ui\assets\orsi-app.ico'
if (-not (Test-Path -LiteralPath $taskLauncher -PathType Leaf) -or -not (Test-Path -LiteralPath $taskPython -PathType Leaf) -or -not (Test-Path -LiteralPath $taskIcon -PathType Leaf)) {
    throw 'O.R.S.I launch files or icon are missing.'
}
function Test-OrsiShortcut($Link) {
    return ($Link.TargetPath -ieq $taskLauncher -or
        ($Link.TargetPath -ieq $taskPython -and $Link.Arguments -match '^\s*-m\s+app\.(main|launcher)(\s|$)'))
}

# Matching shortcut/process identities let Windows associate a pinned shortcut
# with the app window instead of the shared Python runtime.
if (-not ('OrsiShortcutProperties' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class OrsiShortcutProperties {
    [StructLayout(LayoutKind.Sequential)] struct PropertyKey {
        public Guid fmtid; public uint pid;
    }
    [StructLayout(LayoutKind.Explicit, Size=24)] struct PropVariant {
        [FieldOffset(0)] public ushort vt;
        [FieldOffset(8)] public IntPtr value;
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }
    [DllImport("shell32.dll", CharSet=CharSet.Unicode, PreserveSig=false)]
    static extern void SHGetPropertyStoreFromParsingName(string path, IntPtr context,
        uint flags, ref Guid iid, [MarshalAs(UnmanagedType.Interface)] out IPropertyStore store);
    [DllImport("ole32.dll")] static extern int PropVariantClear(ref PropVariant value);
    public static void SetAppId(string path, string appId) {
        var iid = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99");
        IPropertyStore store;
        SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iid, out store);
        var key = new PropertyKey { fmtid=new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid=5 };
        var value = new PropVariant();
        try {
            value.vt = 31; // VT_LPWSTR, released with PropVariantClear.
            value.value = Marshal.StringToCoTaskMemUni(appId);
            store.SetValue(ref key, ref value);
            store.Commit();
        } finally {
            PropVariantClear(ref value);
            Marshal.FinalReleaseComObject(store);
        }
    }
}
'@
}
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcut = $null
$taskTemporary = $null
try {
    if (-not $ShortcutPath) {
        $taskDesktop = [Environment]::GetFolderPath('DesktopDirectory')
        $taskNumber = 1
        do {
            $taskName = if ($taskNumber -eq 1) { 'O.R.S.I.lnk' } else { "O.R.S.I ($taskNumber).lnk" }
            $ShortcutPath = Join-Path $taskDesktop $taskName
            if (-not (Test-Path -LiteralPath $ShortcutPath)) { break }
            $taskExisting = $taskShell.CreateShortcut($ShortcutPath)
            $taskSame = Test-OrsiShortcut $taskExisting
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskExisting)
            if ($taskSame) { break }
            $taskNumber++
        } while ($true)
    }
    $ShortcutPath = [IO.Path]::GetFullPath($ShortcutPath)
    if ([IO.Path]::GetExtension($ShortcutPath) -ine '.lnk' -or -not (Test-Path -LiteralPath (Split-Path -Parent $ShortcutPath) -PathType Container)) {
        throw 'Choose a shortcut filename ending in .lnk inside an existing folder.'
    }
    $taskTemporary = Join-Path (Split-Path -Parent $ShortcutPath) ('.orsi-shortcut-' + [Guid]::NewGuid().ToString('N') + '.lnk')
    $taskNew = -not (Test-Path -LiteralPath $ShortcutPath)
    if (-not $taskNew) { Copy-Item -LiteralPath $ShortcutPath -Destination $taskTemporary }
    $taskShortcut = $taskShell.CreateShortcut($taskTemporary)
    if (-not $taskNew -and -not (Test-OrsiShortcut $taskShortcut)) {
        throw 'The existing shortcut opens another application. It was preserved.'
    }
    if ($taskNew) {
        $taskShortcut.TargetPath = $taskPython
        $taskShortcut.Arguments = '-m app.launcher'
        $taskShortcut.WorkingDirectory = $taskRoot
        $taskShortcut.Description = 'Open O.R.S.I'
        $taskShortcut.WindowStyle = 1
    }
    $taskShortcut.IconLocation = "$taskIcon,0"
    $taskShortcut.Save()
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskShortcut)
    $taskShortcut = $null
    [OrsiShortcutProperties]::SetAppId($taskTemporary, 'ORSI.Desktop')
    Move-Item -LiteralPath $taskTemporary -Destination $ShortcutPath -Force
    $taskTemporary = $null
    Write-Output "O.R.S.I shortcut ready: $ShortcutPath"
} finally {
    if ($null -ne $taskShortcut) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskShortcut) }
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($taskShell)
    if ($taskTemporary -and (Test-Path -LiteralPath $taskTemporary)) { Remove-Item -LiteralPath $taskTemporary }
}
