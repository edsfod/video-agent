"""Versions of a written file (a video's 总结.md, a collection's overview or study guide): a new text never replaces the
current one unless asked, and nothing is lost when it does (user request, 2026-10-28).

The current text stays at its usual name, which every link and route reads. Each other version is a file beside it,
`总结 (2026-10-28 15-30-12).md`, in the same folder so its relative links to frames still work. `<name>.versions.json`
records when each text was written, by what route and with what note, for the current one and the others.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from . import files


class VersionError(RuntimeError):
  pass


def _index_path(target):
  return target.with_name(f'{target.stem}.versions.json')


def _load(target):
  path = _index_path(target)
  data = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
  data.setdefault('current', None)
  data.setdefault('versions', [])
  # A current text written before versions existed, or by hand, is still a version worth keeping.
  if target.is_file() and data['current'] is None:
    stamp = datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec='seconds')
    data['current'] = {'created': stamp, 'source': '', 'note': ''}
  return data


def _save(target, data):
  files.write_text(_index_path(target), json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def _version_name(target, created):
  stamp = created.replace('T', ' ').replace(':', '-')
  name = target.with_name(f'{target.stem} ({stamp}){target.suffix}')
  number = 2
  while name.exists():
    name = target.with_name(f'{target.stem} ({stamp}) {number}{target.suffix}')
    number += 1
  return name


def _meta(source, note):
  return {'created': datetime.now().isoformat(timespec='seconds'), 'source': source or '', 'note': note or ''}


def _keep_current(target, data):
  """Moves the current text into a version file of its own."""
  meta = data['current'] or _meta('', '')
  kept = _version_name(target, meta['created'])
  shutil.copy2(target, kept)
  data['versions'].append({'file': kept.name, **meta})
  return kept


def save(target, text, *, source='', note='', make_current=False):
  """Writes a new text. The first one, or one asked to be current, becomes the current text (the one it replaces is
  kept as a version); otherwise it is kept as a version beside the current one. Returns (path written, is current)."""
  target = Path(target)
  data = _load(target)
  meta = _meta(source, note)
  if target.is_file() and not make_current:
    path = _version_name(target, meta['created'])
    files.write_text(path, text)
    data['versions'].append({'file': path.name, **meta})
    _save(target, data)
    return path, False
  if target.is_file():
    _keep_current(target, data)
  files.write_text(target, text)
  data['current'] = meta
  _save(target, data)
  return target, True


def keep(target, *, source=''):
  """Keeps a copy of the current text as a version unless an identical one is kept already; for routes that write
  the file themselves, such as an Agent. Returns the version's path or None."""
  target = Path(target)
  if not target.is_file():
    return None
  data = _load(target)
  text = target.read_bytes()
  for version in data['versions']:
    path = target.with_name(version['file'])
    if path.is_file() and path.read_bytes() == text:
      return None
  kept = _keep_current(target, data)
  data['current'] = _meta(source, '')
  _save(target, data)
  return kept


def _find(target, data, name):
  for version in data['versions']:
    if version['file'] == name:
      return version
  raise VersionError(f'no version {name!r} of {target.name}')


def use(target, name):
  """Makes a version the current text; the current one becomes a version."""
  target = Path(target)
  data = _load(target)
  chosen = _find(target, data, name)
  text = target.with_name(name).read_text(encoding='utf-8')
  if target.is_file():
    _keep_current(target, data)
  files.write_text(target, text)
  target.with_name(name).unlink()
  data['versions'].remove(chosen)
  data['current'] = {key: chosen[key] for key in ('created', 'source', 'note')}
  _save(target, data)


def delete(target, name):
  """Deletes a version; the current text is never deleted this way."""
  target = Path(target)
  data = _load(target)
  chosen = _find(target, data, name)
  target.with_name(name).unlink(missing_ok=True)
  data['versions'].remove(chosen)
  _save(target, data)


def set_note(target, name, note):
  """Changes the note of a version, or of the current text when `name` is the target's own name."""
  target = Path(target)
  data = _load(target)
  if name == target.name:
    if data['current'] is None:
      raise VersionError(f'{target.name} does not exist')
    data['current']['note'] = note
  else:
    _find(target, data, name)['note'] = note
  _save(target, data)


def listing(target):
  """The current text and the other versions, newest first, each with its file, time, source and note."""
  target = Path(target)
  data = _load(target)
  current = {'file': target.name, **data['current']} if target.is_file() and data['current'] else None
  versions = [
    {**version, 'path': str(target.with_name(version['file']))}
    for version in data['versions']
    if target.with_name(version['file']).is_file()
  ]
  versions.sort(key=lambda version: version['created'], reverse=True)
  return {'current': current and {**current, 'path': str(target)}, 'versions': versions}
