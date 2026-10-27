# Add or remove one folder in the current user's PATH (HKCU\Environment). Called by the installer and uninstaller.
# Reads the raw registry value so entries such as %USERPROFILE%\bin stay unexpanded, and keeps the value's type;
# [Environment]::GetEnvironmentVariable would hand back the expanded text and writing it back would lose them.
# Only this folder's entry changes; other entries, empty ones and a trailing ';' stay, so add then remove gives back
# the same text. -Key points at another HKCU subkey for tests.
param(
  [Parameter(Mandatory)] [ValidateSet('add', 'remove')] [string] $Action,
  [Parameter(Mandatory)] [string] $Folder,
  [string] $Key = 'Environment'
)
$ErrorActionPreference = 'Stop'

$registry = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($Key)
try {
  $exists = $registry.GetValueNames() -contains 'Path'
  $old = if ($exists) { [string]$registry.GetValue('Path', '', 'DoNotExpandEnvironmentNames') } else { '' }
  $kind = if ($exists) { $registry.GetValueKind('Path') } else { [Microsoft.Win32.RegistryValueKind]::ExpandString }
  $target = $Folder.TrimEnd('\')
  # -eq compares case-insensitively, like Windows paths.
  $ours = { param($entry) $entry -and $entry.TrimEnd('\') -eq $target }
  $parts = @($old -split ';')
  if ($Action -eq 'add') {
    if (@($parts | Where-Object { & $ours $_ }).Count) { exit 0 }
    $new = if (-not $old) { $target } elseif ($old.EndsWith(';')) { "$old$target;" } else { "$old;$target" }
  } else {
    $new = @($parts | Where-Object { -not (& $ours $_) }) -join ';'
  }
  if ($new -ceq $old) { exit 0 }
  if ($new) { $registry.SetValue('Path', $new, $kind) } elseif ($exists) { $registry.DeleteValue('Path') }
} finally {
  $registry.Close()
}
