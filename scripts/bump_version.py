"""Set the version everywhere it is written: `uv run scripts/bump_version.py 0.8.3`.

The CLI, the plugin manifests, the window's package files, uv.lock and the wheel links in README.md and the skill carry
the version; tests/test_cli.py::test_versions_match checks they agree. Each file must hold the old version where
expected, or nothing is written. The release notes, docs/releases/v<version>.md, are written by hand; the script says
when they are missing.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r'\d+\.\d+\.\d+')


def current(root=ROOT):
  text = (root / 'src/video_agent/__init__.py').read_text(encoding='utf-8')
  return re.search(r"__version__ = '([^']+)'", text).group(1)


def _json(text, old, new, paths):
  """The JSON text with the version at each key path changed; the rest of the file as npm writes it."""
  data = json.loads(text)
  for keys in paths:
    holder = data
    for key in keys[:-1]:
      holder = holder[key]
    if holder[keys[-1]] != old:
      raise ValueError(f'{"/".join(keys)} is {holder[keys[-1]]}, not {old}')
    holder[keys[-1]] = new
  return json.dumps(data, indent=2, ensure_ascii=False) + '\n'


def _replace(pattern, count):
  """A change that replaces `pattern` (formatted with the old version) exactly `count` times."""

  def change(text, old, new):
    found = text.count(pattern.format(old))
    if found != count:
      raise ValueError(f'{pattern.format(old)!r} found {found} times, expected {count}')
    return text.replace(pattern.format(old), pattern.format(new))

  return change


def _uv_lock(text, old, new):
  own = f'[[package]]\nname = "video-agent"\nversion = "{old}"\n'
  if own not in text:
    raise ValueError(f'no video-agent {old} package entry')
  return text.replace(own, own.replace(old, new))


WHEEL = 'releases/download/v{0}/video_agent-{0}-py3-none-any.whl'
CHANGES = {
  'src/video_agent/__init__.py': _replace("__version__ = '{}'", 1),
  'pyproject.toml': _replace('\nversion = "{}"\n', 1),
  'plugin.json': lambda text, old, new: _json(text, old, new, [('version',)]),
  '.claude-plugin/plugin.json': lambda text, old, new: _json(text, old, new, [('version',)]),
  'gui/package.json': lambda text, old, new: _json(text, old, new, [('version',)]),
  'gui/package-lock.json': lambda text, old, new: _json(text, old, new, [('version',), ('packages', '', 'version')]),
  'uv.lock': _uv_lock,
  'README.md': _replace(WHEEL, 1),
  'skills/video-agent/SKILL.md': _replace(WHEEL, 2),
}


def bump(new, root=ROOT):
  """Changes every file from the current version to `new`; returns the old version and the files changed."""
  if not VERSION.fullmatch(new):
    raise ValueError(f'{new} is not a version like 0.8.3')
  old = current(root)
  if new == old:
    raise ValueError(f'the version is already {old}')
  texts = {name: (root / name).read_text(encoding='utf-8') for name in CHANGES}
  changed = {}
  for name, change in CHANGES.items():
    try:
      changed[name] = change(texts[name], old, new)
    except (ValueError, KeyError) as error:
      raise ValueError(f'{name}: {error}') from None
  for name, text in changed.items():  # only once every file has its old version where expected
    (root / name).write_bytes(text.encode('utf-8'))
  return old, list(changed)


def main(argv):
  if len(argv) != 1:
    print(__doc__.strip().splitlines()[0], file=sys.stderr)
    return 2
  try:
    old, names = bump(argv[0])
  except ValueError as error:
    print(f'nothing changed: {error}', file=sys.stderr)
    return 1
  print(f'{old} -> {argv[0]}: ' + ', '.join(names))
  notes = ROOT / 'docs' / 'releases' / f'v{argv[0]}.md'
  if not notes.is_file():
    print(f'write the release notes: {notes.relative_to(ROOT).as_posix()}')
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
