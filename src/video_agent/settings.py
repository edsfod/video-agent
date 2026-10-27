"""Summary provider settings in %APPDATA%\\video-agent and API keys in Windows Credential Manager."""

import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

PROVIDERS = {
  'anthropic': {'base_url': 'https://api.anthropic.com', 'model': 'claude-sonnet-5-5', 'env': 'ANTHROPIC_API_KEY'},
  'openai': {'base_url': 'https://api.openai.com/v1', 'model': None, 'env': 'OPENAI_API_KEY'},
}
GENERIC, PERSIST_LOCAL_MACHINE, NOT_FOUND = 1, 2, 1168


class SettingsError(RuntimeError):
  pass


def settings_path():
  return Path(os.environ.get('APPDATA') or Path.home()) / 'video-agent' / 'settings.json'


def load():
  path = settings_path()
  if not path.is_file():
    return {'provider': 'anthropic', 'providers': {}}
  try:
    data = json.loads(path.read_text(encoding='utf-8'))
  except (OSError, json.JSONDecodeError) as error:
    raise SettingsError(f'Could not read {path}: {error}') from error
  data.setdefault('provider', 'anthropic')
  data.setdefault('providers', {})
  return data


def save(data):
  path = settings_path()
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = path.with_suffix('.json.part')
  temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
  temporary.replace(path)


def resolve(provider=None, model=None, base_url=None):
  """The provider, model and base URL to use: command-line values, then saved settings, then defaults."""
  data = load()
  name = provider or data['provider']
  if name not in PROVIDERS:
    raise SettingsError(f'Unknown provider {name!r}; choose one of: {", ".join(PROVIDERS)}')
  saved = data['providers'].get(name, {})
  chosen = {
    'provider': name,
    'model': model or saved.get('model') or PROVIDERS[name]['model'],
    'base_url': (base_url or saved.get('base_url') or PROVIDERS[name]['base_url']).rstrip('/'),
  }
  if not chosen['model']:
    raise SettingsError(
      f'No model set for {name}; pass --model or run: video-agent config --provider {name} --model NAME'
    )
  return chosen


class _Credential(ctypes.Structure):
  _fields_ = [
    ('Flags', wintypes.DWORD),
    ('Type', wintypes.DWORD),
    ('TargetName', wintypes.LPWSTR),
    ('Comment', wintypes.LPWSTR),
    ('LastWritten', wintypes.FILETIME),
    ('CredentialBlobSize', wintypes.DWORD),
    ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)),
    ('Persist', wintypes.DWORD),
    ('AttributeCount', wintypes.DWORD),
    ('Attributes', ctypes.c_void_p),
    ('TargetAlias', wintypes.LPWSTR),
    ('UserName', wintypes.LPWSTR),
  ]


def _advapi():
  if os.name != 'nt':
    raise SettingsError('Windows Credential Manager is only available on Windows')
  return ctypes.WinDLL('advapi32', use_last_error=True)


def _target(provider):
  return f'video-agent:{provider}'


def set_key(provider, key):
  blob = key.encode('utf-8')
  buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
  credential = _Credential(
    Type=GENERIC,
    TargetName=_target(provider),
    CredentialBlobSize=len(blob),
    CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
    Persist=PERSIST_LOCAL_MACHINE,
    UserName='api-key',
  )
  if not _advapi().CredWriteW(ctypes.byref(credential), 0):
    raise SettingsError(f'Could not save the key in Credential Manager (error {ctypes.get_last_error()})')


def get_key(provider):
  """The saved key, else the provider's environment variable, else None."""
  if os.name == 'nt':
    advapi = _advapi()
    pointer = ctypes.POINTER(_Credential)()
    if advapi.CredReadW(_target(provider), GENERIC, 0, ctypes.byref(pointer)):
      try:
        found = pointer.contents
        return bytes(found.CredentialBlob[: found.CredentialBlobSize]).decode('utf-8')
      finally:
        advapi.CredFree(pointer)
    if ctypes.get_last_error() != NOT_FOUND:
      raise SettingsError(f'Could not read the key from Credential Manager (error {ctypes.get_last_error()})')
  return os.environ.get(PROVIDERS[provider]['env']) or None


def key_source(provider):
  """Where get_key would find a key: 'Credential Manager', the environment variable's name, or None."""
  if os.name == 'nt':
    advapi = _advapi()
    pointer = ctypes.POINTER(_Credential)()
    if advapi.CredReadW(_target(provider), GENERIC, 0, ctypes.byref(pointer)):
      advapi.CredFree(pointer)
      return 'Credential Manager'
  variable = PROVIDERS[provider]['env']
  return f'environment variable {variable}' if os.environ.get(variable) else None


def delete_key(provider):
  if _advapi().CredDeleteW(_target(provider), GENERIC, 0):
    return True
  if ctypes.get_last_error() == NOT_FOUND:
    return False
  raise SettingsError(f'Could not delete the key from Credential Manager (error {ctypes.get_last_error()})')
