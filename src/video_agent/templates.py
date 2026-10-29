"""Summary templates: the rules and template a summary follows. Several exist side by side and each summary can use
another (user request, 2026-10-29); the chosen one is the `template` setting.

The built-in ones ship with the program. The user's are Markdown files in %APPDATA%\\video-agent\\templates: one with a
built-in's name is the user's edited copy of it, whose first line records which version of the built-in it was copied
from, so an update that changes the built-in can say so; any other name is a template of the user's own. Updates never
touch the user's files.
"""

import hashlib
import re
from importlib import resources

from . import files, settings

STANDARD = '标准'
BUILT_IN = {STANDARD: 'summary.md', '命题分析': 'propositions.md'}
BASE_MARK = re.compile(r'<!-- video-agent default: (\w+) -->\r?\n?')
BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class TemplateError(RuntimeError):
  pass


def folder():
  return settings.settings_path().parent / 'templates'


def _path(name):
  return folder() / f'{name}.md'


def _compare_path(name):
  return folder() / '.defaults' / f'{name}.md'


def built_in(name):
  return resources.files('video_agent').joinpath(f'prompts/{BUILT_IN[name]}').read_text(encoding='utf-8')


def _fingerprint(text):
  return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


def _body(path):
  return BASE_MARK.sub('', path.read_text(encoding='utf-8-sig'), count=1)


def _migrate():
  """Before several templates, the user's one copy was summary.md beside the settings, copied from the standard one.
  A copy that is word for word a built-in template goes, and that template is chosen; any other becomes the user's
  copy of the standard one."""
  old = settings.settings_path().parent / 'summary.md'
  old.with_name('summary.default.md').unlink(missing_ok=True)
  if not old.is_file():
    return
  body = _body(old).replace('\r\n', '\n').strip()
  same = next((name for name in BUILT_IN if built_in(name).strip() == body), None)
  if same:
    old.unlink()
    if same != STANDARD:
      _choose(same)
  elif not _path(STANDARD).exists():
    folder().mkdir(parents=True, exist_ok=True)
    old.replace(_path(STANDARD))


def names():
  _migrate()
  own = sorted(path.stem for path in folder().glob('*.md') if path.stem not in BUILT_IN) if folder().is_dir() else []
  return [*BUILT_IN, *own]


def _choose(name):
  data = settings.load()
  data['template'] = name
  settings.save(data)


def current():
  known = names()  # first: moving an old copy may choose a template
  chosen = settings.load().get('template')
  return chosen if chosen in known else STANDARD


def _known(name):
  name = name or current()
  if name not in names():
    raise TemplateError(f'No summary template named {name!r}; video-agent template --list lists them')
  return name


def text(name=None):
  """The rules and template to follow: the named one, or the chosen one; the user's copy of a built-in when there is
  one."""
  name = _known(name)
  path = _path(name)
  return _body(path) if path.is_file() else built_in(name)


def info(name=None):
  """Where a template is, whether it is built in, whether the user changed it, and whether the built-in one changed
  since it was copied. For an outdated copy, the current built-in is written to `default` for comparing."""
  name = _known(name)
  path = _path(name)
  entry = {'name': name, 'path': str(path), 'builtin': name in BUILT_IN, 'customized': False, 'outdated': False}
  entry |= {'default': None, 'current': name == current()}
  if name in BUILT_IN and path.is_file():
    found = BASE_MARK.match(path.read_text(encoding='utf-8-sig'))
    entry['customized'] = True
    entry['outdated'] = not found or found.group(1) != _fingerprint(built_in(name))
    files.write_text(_compare_path(name), built_in(name))
    entry['default'] = str(_compare_path(name))
  return entry


def listing():
  return [info(name) for name in names()]


def use(name):
  _choose(_known(name))
  return info(name)


def edit(name=None):
  """The file to edit: for a built-in template, the user's copy, made from it the first time."""
  name = _known(name)
  path = _path(name)
  if name in BUILT_IN and not path.is_file():
    files.write_text(path, f'<!-- video-agent default: {_fingerprint(built_in(name))} -->\n{built_in(name)}')
  return info(name)


def copy(name, new):
  """A new template of the user's own, starting from another one's text."""
  new = (new or '').strip()
  if not new or BAD_NAME.search(new) or new.startswith('.') or new.endswith('.') or len(new) > 60:
    raise TemplateError(f'{new!r} cannot be a template name: use up to 60 characters, none of < > : " / \\ | ? *')
  if new in names():
    raise TemplateError(f'There is already a template named {new!r}')
  files.write_text(_path(new), text(name))
  return info(new)


def accept(name=None):
  """Marks the user's copy of a built-in template as up to date with it (after merging its changes by hand)."""
  name = _known(name)
  path = _path(name)
  if name in BUILT_IN and path.is_file():
    files.write_text(path, f'<!-- video-agent default: {_fingerprint(built_in(name))} -->\n{_body(path)}')
  return info(name)


def reset(name=None):
  """Removes the user's file: a built-in template goes back to as it ships, one of the user's own is deleted (and the
  standard one chosen, if it was the chosen one)."""
  name = _known(name)
  chosen = current()
  _path(name).unlink(missing_ok=True)
  _compare_path(name).unlink(missing_ok=True)
  if name in BUILT_IN:
    return info(name)
  if chosen == name:
    _choose(STANDARD)
  return {'name': name, 'deleted': True}
