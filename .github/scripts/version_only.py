"""Prints yes when the commits since BASE change nothing but the version where scripts/bump_version.py writes it, and
release notes; else no. Used by changed-jobs.sh: python3 .github/scripts/version_only.py BASE.

Every changed line outside docs/releases/ must name the old or the new version, in either spelling (semantic, or
Python's), or be README.md's wheel link (which keeps the last full release's during a pre-release), and every changed
file must be one bump_version.py writes or a release note.
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import bump_version  # noqa: E402


def git(*args):
  return subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', check=True).stdout


def version(ref):
  return re.search(r"__version__ = '([^']+)'", git('show', f'{ref}:src/video_agent/__init__.py')).group(1)


def version_only(base):
  old, new = version(base), version('HEAD')
  files = [name for name in git('diff', '--name-only', base, 'HEAD').splitlines() if name]
  if old == new or not all(name in bump_version.CHANGES or name.startswith('docs/releases/') for name in files):
    return False
  spelled = {old, new, bump_version.python(old), bump_version.python(new)}
  code = [name for name in files if not name.startswith('docs/releases/')]
  lines = [
    line
    for line in git('diff', '-U0', base, 'HEAD', '--', *code).splitlines()
    if line.startswith(('+', '-')) and not line.startswith(('+++', '---'))
  ]
  wheel = re.compile(r'releases/download/v[^/\s]+/video_agent-[^-\s]+-py3-none-any\.whl')
  return all(any(spelling in line for spelling in spelled) or wheel.search(line) for line in lines)


if __name__ == '__main__':
  print('yes' if version_only(sys.argv[1]) else 'no')
