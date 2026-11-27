"""Versions of a written file (a video's 总结.md, a collection's overview or study guide): a new text never replaces the
current one unless asked, and nothing is lost when it does (docs/summary-design.md).

The current text stays at its usual name, which every link and route reads. Each other version is a file beside it,
`总结 (2026-10-28 15-30-12).md`, in the same folder so its relative links to frames still work. `<name>.versions.json`
records when each text was written, by what route and with what note, for the current one and the others.

Each text also records where it came from: written afresh (`based_on` null), or written from an earlier version
(`based_on` that version's id), which an import finds by the share of lines the two have word for word (`closest`). The
ids stay with a text when it is renamed (made current, or current no longer), so the versions form a forest. Older
records without `based_on` show neither.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from . import contract, files


class VersionError(RuntimeError):
  pass


UNKNOWN = object()  # how a text came about is not known (texts saved before 2026-11-16)
# Two summaries of one video written apart share no line word for word; one written from another shares many (the first
# NJU lecture, 2026-11-16: 0% between four versions written apart, 41% for one an Agent wrote after reading another).
SHARED = 0.2
LINE = 20  # shorter lines (headings, labels) are left out of the comparison


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
  data['versions'] = [version for version in data['versions'] if target.with_name(version['file']).is_file()]
  files.write_text(_index_path(target), json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def _version_name(target, created):
  stamp = created.replace('T', ' ').replace(':', '-')
  name = target.with_name(f'{target.stem} ({stamp}){target.suffix}')
  number = 2
  while name.exists():
    name = target.with_name(f'{target.stem} ({stamp}) {number}{target.suffix}')
    number += 1
  return name


def _meta(source, note, pictures=None, based_on=UNKNOWN, usage=None):
  meta = {'created': datetime.now().isoformat(timespec='seconds'), 'source': source or '', 'note': note or ''}
  if usage:
    meta['usage'] = usage  # the model's tokens and calls that wrote it, when the program ran the model itself
  if pictures is not None:
    meta['pictures'] = pictures  # the set of pictures it was written with (pictures.py)
  if based_on is not UNKNOWN:
    meta['based_on'] = based_on
  return meta


def _id(meta):
  """A text's id: given when it was written; for texts written before ids, the time it was written."""
  return meta.get('id') or meta['created']


def _give_id(data, meta):
  taken = {_id(other) for other in [data['current'], *data['versions']] if other}
  meta['id'], number = meta['created'], 2
  while meta['id'] in taken:
    meta['id'] = f'{meta["created"]} {number}'
    number += 1


def _keep_current(target, data):
  """Moves the current text into a version file of its own."""
  meta = data['current'] or _meta('', '')
  kept = _version_name(target, meta['created'])
  shutil.copy2(target, kept)
  data['versions'].append({'file': kept.name, **meta})
  return kept


def save(
  target, text, *, source='', note='', make_current=False, pictures=None, based_on=UNKNOWN, usage=None, _same=None
):
  """Writes a new text. The first one, or one asked to be current, becomes the current text (the one it replaces is
  kept as a version); otherwise it is kept as a version beside the current one. `pictures` names the set of pictures
  it was written with, `based_on` the id of the version it was written from (None: written afresh), `usage` the tokens
  and calls that wrote it. Returns (path written, is current)."""
  target = Path(target)
  data = _load(target)
  meta = _meta(source, note, pictures, based_on, usage)
  _give_id(data, meta)
  meta |= _same or {}
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


def overwrite(
  target, name, text, *, source='', note='', make_current=False, pictures=None, based_on=UNKNOWN, usage=None
):
  """Writes a new text over an earlier one, the current text (`name` the target's own name) or a version, keeping
  neither: a chat AI's later round over the round before, whether or not it became current. A version written over
  takes the new time in its name; with `make_current` it becomes the current text. It stays the same text in the
  record: its id, and where it came from unless a source is found now. Returns (path written, is current)."""
  target = Path(target)
  data = _load(target)
  old = data['current'] if name == target.name else _find(target, data, name)
  same = {'id': _id(old)}
  if based_on in (None, UNKNOWN) and 'based_on' in old:
    same['based_on'] = old['based_on']
  if name == target.name:
    files.write_text(target, text)
    data['current'] = _meta(source, note, pictures, based_on, usage) | same
    _save(target, data)
    return target, True
  data['versions'].remove(old)
  target.with_name(name).unlink(missing_ok=True)
  _save(target, data)
  return save(
    target,
    text,
    source=source,
    note=note,
    make_current=make_current,
    pictures=pictures,
    based_on=based_on,
    usage=usage,
    _same=same,
  )


def closest(target, text, *, ignore=(), skip=None):
  """The version a text was most likely written from: the one with which it shares the largest part of its lines word
  for word, if that part is at least SHARED, as (id, file, share); else None. `ignore`: lines every text has (the
  template's), `skip`: the file the text is about to write over."""
  target = Path(target)
  data = _load(target)
  common = {line.strip() for line in ignore}

  def lines(value):
    return {line.strip() for line in value.splitlines() if len(line.strip()) >= LINE and line.strip() not in common}

  mine = lines(text)
  if not mine:
    return None
  found = None
  texts = [(target.name, data['current'])] if target.is_file() and data['current'] else []
  for file, meta in texts + [(version['file'], version) for version in data['versions']]:
    path = target.with_name(file)
    if file == skip or not path.is_file():
      continue
    share = len(mine & lines(path.read_text(encoding='utf-8'))) / len(mine)
    if share >= SHARED and (found is None or share > found[2]):
      found = (_id(meta), file, share)
  return found


def keep(target, *, source=''):
  """Keeps a copy of the current text as a version unless an identical one is kept already; for routes that may
  write the file themselves, such as an Agent. The current text keeps its record: it is still the same text. The copy
  is marked as kept for `source` until `settle` sees what the route did. Returns the version's path or None."""
  target = Path(target)
  if not target.is_file():
    return None
  data = _load(target)
  _settle(target, data)
  text = target.read_bytes()
  for version in data['versions']:
    path = target.with_name(version['file'])
    if path.is_file() and path.read_bytes() == text:
      _save(target, data)
      return None
  meta = data['current'] or _meta('', '')
  kept = _version_name(target, meta['created'])
  shutil.copy2(target, kept)
  data['versions'].append({'file': kept.name, **meta, 'kept_for': source})
  _save(target, data)
  return kept


def settle(target):
  """After the route a copy was kept for has finished: the copy goes when another file has the same text (the route
  left the current text alone, or saved its own through the CLI, which keeps the old one itself); when the route
  wrote over the current text itself, that text is recorded as the route's. Until 2026-11-16 `keep` recorded the
  current text as the route's at once, so an Agent that saved through `summarize --import` left the old text labelled
  as its own beside a duplicate of it."""
  target = Path(target)
  data = _load(target)
  if _settle(target, data):
    _save(target, data)


def _settle(target, data):
  changed = False
  for version in list(data['versions']):
    if 'kept_for' not in version:
      continue
    source = version.pop('kept_for')
    changed = True
    path = target.with_name(version['file'])
    if not path.is_file():
      continue
    text = path.read_bytes()
    others = [target] + [target.with_name(other['file']) for other in data['versions'] if other is not version]
    if any(other.is_file() and other.read_bytes() == text for other in others):
      data['versions'].remove(version)
      path.unlink()
    elif target.is_file() and data['current'] == {key: value for key, value in version.items() if key != 'file'}:
      stamp = datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec='seconds')
      data['current'] = {'created': stamp, 'source': source, 'note': ''}
  return changed


def _find(target, data, name):
  for version in data['versions']:
    if version['file'] == name:
      return version
  raise VersionError(f'no version {name!r} of {target.name}')


def use(target, name):
  """Makes a version the current text; the current one becomes a version, whose file name is returned (None when
  there was no current text)."""
  target = Path(target)
  data = _load(target)
  chosen = _find(target, data, name)
  text = target.with_name(name).read_text(encoding='utf-8')
  kept = _keep_current(target, data) if target.is_file() else None
  files.write_text(target, text)
  target.with_name(name).unlink()
  data['versions'].remove(chosen)
  data['current'] = {key: value for key, value in chosen.items() if key != 'file'}
  _save(target, data)
  return kept.name if kept else None


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


def listing(target) -> contract.Versions:
  """The current text and the other versions, newest first, each with its file, time, source and note."""
  target = Path(target)
  data = _load(target)

  def entry(file, meta) -> contract.Version:
    path = target.with_name(file)
    return {
      'file': file,
      'created': meta['created'],
      'source': meta['source'],
      'note': meta['note'],
      'path': str(path),
      'pictures': meta.get('pictures'),
      'id': _id(meta),
      'based_on': meta.get('based_on'),
      'origin': 'revised' if meta.get('based_on') else 'fresh' if 'based_on' in meta else 'unknown',
      'usage': meta.get('usage'),
    }

  current = entry(target.name, data['current']) if target.is_file() and data['current'] else None
  versions = [
    entry(version['file'], version) for version in data['versions'] if target.with_name(version['file']).is_file()
  ]
  versions.sort(key=lambda version: version['created'], reverse=True)
  return {'current': current, 'versions': versions}
