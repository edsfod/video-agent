"""检查文档和代码里引用的编号、文件都存在（docs/doc-rules.md「检查」）。

查：
- 需求编号（SRC、FRM、SUM、MGT、APP、INS、PRV）：由 docs/requirements.md 的 `### <编号> ` 标题定义；
- 总结提示词的要求（PRM-）：由 docs/summary-requirements.md 表格第一列定义；
- ADR 编号：由 docs/adr/<NNNN>-*.md 的文件名定义；
- 不变量（`A1`、`C1` 这类）：由 ARCHITECTURE.md「不变量」表格第一列定义，查「不变量 `X`」这样的引用；
- Markdown 的相对链接，和文字里写出的 `docs/….md`、`ARCHITECTURE.md` 路径，指向的文件都要存在。

废弃的编号列在所属文件的「## 已废弃编号」里，只能出现在那个文件里。
不扫：docs/releases/ 和 docs/release-log.md（发布时的记录，不跟着改）、docs/user-notes/、notes/、总结模板
src/video_agent/prompts/（里面的链接是给模型的例子）。

用法：
    python scripts/verify_doc_references.py     # 有问题时退出码 1
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ_FILE = ROOT / 'docs' / 'requirements.md'
PRM_FILE = ROOT / 'docs' / 'summary-requirements.md'
ADR_DIR = ROOT / 'docs' / 'adr'
ARCH_FILE = ROOT / 'ARCHITECTURE.md'
RETIRED = '## 已废弃编号'

DOC_FILES = [ROOT / 'README.md', ROOT / 'ARCHITECTURE.md', ROOT / 'PRIVACY.md']
DOC_DIRS = [ROOT / 'docs', ROOT / '.claude' / 'rules', ROOT / 'skills']
DOC_EXCLUDE = [ROOT / 'docs' / 'releases', ROOT / 'docs' / 'user-notes', ROOT / 'docs' / 'release-log.md']
CODE_DIRS = [
  ROOT / 'src',
  ROOT / 'tests',
  ROOT / 'scripts',
  ROOT / 'packaging',
  ROOT / 'gui' / 'src',
  ROOT / 'gui' / 'test',
  ROOT / 'gui' / 'scripts',
  ROOT / 'gui' / 'installer',
  ROOT / '.github',
]
CODE_EXCLUDE = [ROOT / 'src' / 'video_agent' / 'prompts']
CODE_SUFFIXES = {'.py', '.js', '.ts', '.sh', '.ps1', '.yml', '.nsh', '.html', '.css'}
SKIP_PARTS = {'.venv', '__pycache__', 'node_modules'}

REQ_DEF = re.compile(r'^### ((?:SRC|FRM|SUM|MGT|APP|INS|PRV)-\d{2}) ', re.MULTILINE)
REQ_REF = re.compile(r'\b(?:SRC|FRM|SUM|MGT|APP|INS|PRV)-\d{2}\b')
PRM_DEF = re.compile(r'^\| (PRM-[A-Z]\d+a?) \|', re.MULTILINE)
PRM_REF = re.compile(r'\bPRM-[A-Z]\d+a?\b')
RETIRED_ITEM = re.compile(r'^- `([A-Z]{3}-[A-Z]?\d+a?)`', re.MULTILINE)
ADR_REF = re.compile(r'\bADR-(\d{4})\b')
INV_DEF = re.compile(r'^\| `([AC]\d+)` \|', re.MULTILINE)
INV_REF = re.compile(r'不变量\s*((?:`[AC]\d+`[、，和\s]*)+)')
INV_ID = re.compile(r'`([AC]\d+)`')
LINK = re.compile(r'\]\(([^)\s]+)\)')
ROOT_PATH = re.compile(r'(?<![\w/.-])((?:docs/[\w./-]+\.md)|ARCHITECTURE\.md)\b')
FENCE = re.compile(r'^```.*?^```', re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r'`[^`\n]+`')


def _script(path: Path) -> bool:
  """没有扩展名、第一行是 #! 的脚本（如 scripts/githooks/ 下的钩子）。"""
  if path.suffix or not path.is_file():
    return False
  with path.open('rb') as f:
    return f.read(2) == b'#!'


def _excluded(path: Path, excluded: list[Path]) -> bool:
  return bool(SKIP_PARTS & set(path.parts)) or any(path == ex or ex in path.parents for ex in excluded)


def doc_files() -> list[Path]:
  out = [p for p in DOC_FILES if p.exists()]
  for d in DOC_DIRS:
    out += [p for p in d.rglob('*.md') if not _excluded(p, DOC_EXCLUDE)]
  return sorted(set(out))


def code_files() -> list[Path]:
  out: list[Path] = []
  for d in CODE_DIRS:
    out += [p for p in d.rglob('*') if (p.suffix in CODE_SUFFIXES or _script(p)) and not _excluded(p, CODE_EXCLUDE)]
  return sorted(set(out))


def defined(path: Path, pattern: re.Pattern[str], errors: list[str]) -> tuple[set[str], set[str]]:
  """一个文件定义的编号和废弃的编号；同一编号定义两次、或既在用又废弃，记为问题。"""
  text = path.read_text(encoding='utf-8')
  head, _, retired_part = text.partition(RETIRED)
  found = pattern.findall(head)
  active = set(found)
  name = path.relative_to(ROOT).as_posix()
  for item in sorted({x for x in found if found.count(x) > 1}):
    errors.append(f'{name}: {item} 定义了两次')
  retired = set(RETIRED_ITEM.findall(retired_part))
  for item in sorted(active & retired):
    errors.append(f'{name}: {item} 既在用又列在「已废弃编号」里')
  return active, retired


def check_ids(rel: str, path: Path, text: str, ids: dict, errors: list[str]) -> None:
  for pattern, (active, retired, home) in ids.items():
    for item in sorted(set(pattern.findall(text))):
      if item in active:
        continue
      if item in retired:
        if path != home:
          errors.append(f'{rel}: 引用了已废弃的 {item}')
        continue
      errors.append(f'{rel}: {item} 不存在')


def main() -> int:
  errors: list[str] = []
  reqs, reqs_retired = defined(REQ_FILE, REQ_DEF, errors)
  prms, prms_retired = defined(PRM_FILE, PRM_DEF, errors)
  invariants = set(INV_DEF.findall(ARCH_FILE.read_text(encoding='utf-8')))
  adrs = {p.name[:4] for p in ADR_DIR.glob('[0-9][0-9][0-9][0-9]-*.md')}
  ids = {REQ_REF: (reqs, reqs_retired, REQ_FILE), PRM_REF: (prms, prms_retired, PRM_FILE)}

  docs = doc_files()
  links = 0
  for path in docs + code_files():
    rel = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding='utf-8', errors='replace')
    check_ids(rel, path, text, ids, errors)
    for number in sorted(set(ADR_REF.findall(text))):
      if number not in adrs:
        errors.append(f'{rel}: ADR-{number} 不存在')
    for group in INV_REF.findall(text):
      for item in INV_ID.findall(group):
        if item not in invariants:
          errors.append(f'{rel}: 不变量 {item} 不存在')
    for target in sorted(set(ROOT_PATH.findall(text))):
      if not (ROOT / target).is_file():
        errors.append(f'{rel}: {target} 不存在')
    if path in docs:
      prose = INLINE_CODE.sub('', FENCE.sub('', text))
      for target in LINK.findall(prose):
        if re.match(r'[a-z][a-z0-9+.-]*:', target) or target.startswith('#') or '<' in target:
          continue
        links += 1
        if not (path.parent / target.split('#')[0]).exists():
          errors.append(f'{rel}: 链接 {target} 指向的文件不存在')

  for msg in errors:
    print(msg)
  if errors:
    print(f'共 {len(errors)} 处')
  else:
    counts = f'需求 {len(reqs)} 条、PRM {len(prms)} 条、ADR {len(adrs)} 份、不变量 {len(invariants)} 条'
    print(f'引用都存在：{counts}，链接 {links} 个')
  return 1 if errors else 0


if __name__ == '__main__':
  sys.exit(main())
