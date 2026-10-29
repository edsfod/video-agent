"""Set the version everywhere it is written: `uv run scripts/bump_version.py 0.8.3` (or `0.9.2-beta`, `0.9.2-beta.2`).

The CLI, the plugin manifests, the window's package files, uv.lock and the wheel links in README.md and the skill carry
the version; tests/test_cli.py::test_versions_match checks they agree. Each file must hold the old version where
expected, or nothing is written. The release notes, docs/releases/v<version>.md, are written by hand; the script says
when they are missing.

A pre-release (user request, 2026-10-29: 0.9.2-beta before 0.9.2) is written the semantic-versioning way everywhere
but in Python's packaging, which spells it its own way (PEP 440: 0.9.2b0), so pyproject.toml, uv.lock and the wheel's
file name carry that; the tag and the release folder keep the first. README.md keeps the links of the last full
release during a pre-release, so people reading it install that one.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r'\d+\.\d+\.\d+(-(alpha|beta|rc)(\.\d+)?)?')
PEP440 = {'alpha': 'a', 'beta': 'b', 'rc': 'rc'}


def python(version):
  """The version as Python's packaging writes it: 0.9.2-beta -> 0.9.2b0, 0.9.2-rc.1 -> 0.9.2rc1, 0.9.2 -> 0.9.2."""
  core, _, pre = version.partition('-')
  if not pre:
    return core
  kind, _, number = pre.partition('.')
  return f'{core}{PEP440[kind]}{number or 0}'


def prerelease(version):
  return '-' in version


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
  own = f'[[package]]\nname = "video-agent"\nversion = "{python(old)}"\n'
  if own not in text:
    raise ValueError(f'no video-agent {python(old)} package entry')
  return text.replace(own, own.replace(python(old), python(new)))


def wheel(version):
  return f'releases/download/v{version}/video_agent-{python(version)}-py3-none-any.whl'


def _wheels(count):
  def change(text, old, new):
    found = text.count(wheel(old))
    if found != count:
      raise ValueError(f'{wheel(old)!r} found {found} times, expected {count}')
    return text.replace(wheel(old), wheel(new))

  return change


def _readme(text, old, new):
  """The one wheel link, of the last full release: left during a pre-release, and replaced by the next full one."""
  links = re.findall(r'releases/download/v[^/\s]+/video_agent-[^-\s]+-py3-none-any\.whl', text)
  if len(links) != 1 or prerelease(links[0].split('/')[2][1:]):
    raise ValueError(f'expected one wheel link of a full release, found {links}')
  if not prerelease(old) and links[0] != wheel(old):
    raise ValueError(f'{wheel(old)!r} not found')
  return text if prerelease(new) else text.replace(links[0], wheel(new))


CHANGES = {
  'src/video_agent/__init__.py': _replace("__version__ = '{}'", 1),
  'pyproject.toml': lambda text, old, new: _replace('\nversion = "{}"\n', 1)(text, python(old), python(new)),
  'plugin.json': lambda text, old, new: _json(text, old, new, [('version',)]),
  '.claude-plugin/plugin.json': lambda text, old, new: _json(text, old, new, [('version',)]),
  'gui/package.json': lambda text, old, new: _json(text, old, new, [('version',)]),
  'gui/package-lock.json': lambda text, old, new: _json(text, old, new, [('version',), ('packages', '', 'version')]),
  'uv.lock': _uv_lock,
  'README.md': _readme,
  'skills/video-agent/SKILL.md': _wheels(2),
}


def bump(new, root=ROOT):
  """Changes every file from the current version to `new`; returns the old version and the files changed."""
  if not VERSION.fullmatch(new):
    raise ValueError(f'{new} is not a version like 0.8.3 or 0.9.2-beta')
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
