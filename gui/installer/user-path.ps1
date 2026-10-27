# Add or remove one folder in the current user's PATH (HKCU\Environment). Called by the installer and uninstaller.
# Reads the raw registry value so entries such as %USERPROFILE%\bin stay unexpanded, and keeps the value's type;
# [Environment]::GetEnvironmentVariable would hand back the expanded text and writing it back would lose them.
param(
  [Parameter(Mandatory)] [ValidateSet('add', 'remove')] [string] $Action,
  [Parameter(Mandatory)] [string] $Folder
)
$ErrorActionPreference = 'Stop'

$key = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
try {
  $exists = $key.GetValueNames() -contains 'Path'
  $old = if ($exists) { [string]$key.GetValue('Path', '', 'DoNotExpandEnvironmentNames') } else { '' }
  $kind = if ($exists) { $key.GetValueKind('Path') } else { [Microsoft.Win32.RegistryValueKind]::ExpandString }
  $target = $Folder.TrimEnd('\')
  # -ne compares case-insensitively, like Windows paths.
  $parts = @($old -split ';' | Where-Object { $_ -and $_.TrimEnd('\') -ne $target })
  if ($Action -eq 'add') { $parts += $target }
  $new = $parts -join ';'
  if ($new -eq $old) { exit 0 }
  if ($new) { $key.SetValue('Path', $new, $kind) } elseif ($exists) { $key.DeleteValue('Path') }
} finally {
  $key.Close()
}
