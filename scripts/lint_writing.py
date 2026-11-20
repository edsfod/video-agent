"""检查仓库里的文字是不是写成了过程记录（docs/writing.md）。

扫：docs/（不含 archive、user-notes、releases 和 release-log.md）、.claude/rules/、README.md、PRIVACY.md，以及代码里的注释
（src/、tests/、scripts/、packaging/、gui/src、gui/test、gui/scripts、.github/）。
找：归给用户的引语、「Claude 判断」这类过程标记、带钟点的过程记录。

用法：
    python scripts/lint_writing.py              # 全部查一遍，有问题时退出码 1
    python scripts/lint_writing.py 文件...       # 只查给定的文件（不在范围内的跳过）
    python scripts/lint_writing.py --staged     # 查这次要提交的文件（git pre-commit 钩子用）
    python scripts/lint_writing.py --message F  # 查提交信息（git commit-msg 钩子用：只查归给用户的引语）
    python scripts/lint_writing.py --hook       # Claude Code 钩子：从标准输入读工具调用，查刚写的文件；
                                                # Bash 调用后查工作区里改过的文件。有问题时退出码 2，说明写到标准错误
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOC_DIRS = [ROOT / 'docs', ROOT / '.claude' / 'rules']
DOC_FILES = [ROOT / 'README.md', ROOT / 'PRIVACY.md']
DOC_EXCLUDE = [ROOT / 'docs' / 'archive', ROOT / 'docs' / 'user-notes', ROOT / 'docs' / 'releases']
CODE_DIRS = [
  ROOT / 'src',
  ROOT / 'tests',
  ROOT / 'scripts',
  ROOT / 'packaging',
  ROOT / 'gui' / 'src',
  ROOT / 'gui' / 'test',
  ROOT / 'gui' / 'scripts',
  ROOT / '.github',
]
CODE_SUFFIXES = {'.py', '.js', '.ts', '.sh', '.ps1', '.yml', '.nsh', '.html', '.css'}
SKIP_PARTS = {'.venv', '__pycache__', 'node_modules'}
# 规定这条规则本身的地方
ALLOW = {ROOT / 'docs' / 'writing.md', Path(__file__).resolve()}
# 只追加的记录：发布检查记录
ALLOW |= {ROOT / 'docs' / 'release-log.md'}

QUOTE = r'["“「]'
RULES_ANY = [
  ('归给用户的引语', re.compile(r'用户[^。；\n]{0,24}[：:]\s*' + QUOTE + r'|\buser\b[^.;\n]{0,40}[：:]\s*' + QUOTE, re.I)),
  ('过程标记', re.compile(r'Claude judgment|Claude 判断|Claude\'s proposal|等用户定')),
]
RULES_DOC = [
  ('带钟点的过程记录', re.compile(r'20\d\d-\d\d-\d\d \d{1,2}:\d{2}(?!:)')),
]
COMMENT = re.compile(r'(#|//|/\*|^\s*\*|<!--|"""|\'\'\')')


def _skipped(path: Path) -> bool:
  return bool(SKIP_PARTS & set(path.parts))


def doc_files() -> list[Path]:
  out = [p for p in DOC_FILES if p.exists()]
  for d in DOC_DIRS:
    out += [p for p in d.rglob('*.md') if not any(ex in p.parents for ex in DOC_EXCLUDE)]
  return out


def code_files() -> list[Path]:
  out: list[Path] = []
  for d in CODE_DIRS:
    out += [p for p in d.rglob('*') if p.suffix in CODE_SUFFIXES and not _skipped(p)]
  return out


def check(path: Path, is_doc: bool) -> list[str]:
  problems = []
  rules = RULES_ANY + (RULES_DOC if is_doc else [])
  for no, line in enumerate(path.read_text(encoding='utf-8', errors='replace').splitlines(), 1):
    if not is_doc and not COMMENT.search(line):
      continue  # 代码只看带注释或文档字符串的行
    for name, pattern in rules:
      if pattern.search(line):
        problems.append(f'{path.relative_to(ROOT).as_posix()}:{no}: {name}: {line.strip()[:100]}')
  return problems


def in_scope(path: Path) -> bool | None:
  """在检查范围内：文档返回 True，代码返回 False；不在范围内返回 None。"""
  path = path.resolve()
  if path in ALLOW or _skipped(path):
    return None
  if (
    path.suffix == '.md'
    and (path in DOC_FILES or any(d in path.parents for d in DOC_DIRS))
    and not any(ex in path.parents for ex in DOC_EXCLUDE)
  ):
    return True
  if path.suffix in CODE_SUFFIXES and any(d in path.parents for d in CODE_DIRS):
    return False
  return None


def git_paths(*args: str) -> list[Path]:
  out = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8').stdout
  return [ROOT / line.strip() for line in out.splitlines() if line.strip()]


def changed_paths() -> list[Path]:
  """工作区里改过和新加的文件（含暂存的）。"""
  return git_paths('diff', '--name-only', '--diff-filter=ACMR', 'HEAD') + git_paths(
    'ls-files', '--others', '--exclude-standard'
  )


def lint(paths: list[Path]) -> list[str]:
  problems: list[str] = []
  for path in dict.fromkeys(paths):
    kind = in_scope(path) if path.exists() else None
    if kind is not None:
      problems += check(path, kind)
  return problems


def check_message(text: str) -> list[str]:
  name, pattern = RULES_ANY[0]
  return [
    f'提交信息第 {no} 行: {name}: {line.strip()[:100]}'
    for no, line in enumerate(text.splitlines(), 1)
    if not line.startswith('#') and pattern.search(line)
  ]


def hook() -> int:
  try:
    event = json.load(sys.stdin)
  except ValueError:
    return 0
  tool = event.get('tool_name', '')
  tool_input = event.get('tool_input') or {}
  if tool in ('Write', 'Edit', 'MultiEdit') and tool_input.get('file_path'):
    raw = re.sub(r'^/([a-zA-Z])/', r'\1:/', tool_input['file_path'])  # Git Bash 风格的 /c/... 也认
    problems = lint([Path(raw)])
  elif tool == 'Bash':
    problems = lint(changed_paths())
  else:
    return 0
  if not problems:
    return 0
  print('写法检查（docs/writing.md）没通过：写规整后的说法，不抄用户原话、不记讨论经过。改掉下面这些：', file=sys.stderr)
  for msg in problems:
    print(msg, file=sys.stderr)
  return 2


def main(argv: list[str]) -> int:
  if argv[:1] == ['--hook']:
    return hook()
  quiet = argv[:1] in (['--message'], ['--staged'])
  if argv[:1] == ['--message']:
    problems = check_message(Path(argv[1]).read_text(encoding='utf-8', errors='replace'))
  elif argv[:1] == ['--staged']:
    problems = lint(git_paths('diff', '--cached', '--name-only', '--diff-filter=ACMR'))
  elif argv:
    problems = lint([Path(a) for a in argv])
  else:
    problems = lint(doc_files() + code_files())
  for msg in problems:
    print(msg, file=sys.stderr if quiet else sys.stdout)
  if quiet:
    if problems:
      print('写法检查没通过（docs/writing.md）：改掉上面这些再提交。', file=sys.stderr)
  else:
    print(f'共 {len(problems)} 处' if problems else '没有发现问题')
  return 1 if problems else 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
