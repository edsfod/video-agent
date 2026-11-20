"""主线与单元, built from 详细内容 (user decision, 2026-11-20; docs/design/summary.md).

The model makes each judgment once, in 详细内容: what each proposition says (its line is the claim in one sentence, the
particulars in lines under it), how propositions relate (`← P1, P2` support, `反驳 P4`, `步骤 P39` a step of an event),
and which items the main conclusion takes from the units, with where each link comes from (a line `接上：` under it).
The program lays out the logic view from that: every group of related items is a tree, a unit, under the heading of the
part of 详细内容 its root is in; the main line is the item with `接上：` and what links to it. Each item is expanded
once, items related to nothing stay out, and each number links to its entry in 详细内容.
"""

import re

HEADING = '主线与单元'
MARK = 'video-agent: 这一节由程序根据详细内容生成'  # in a template's section, the program writes the section
CLOCK = r'(?:\d{1,2}:)?\d{1,2}:\d{2}'
PART = re.compile(rf'^###\s+(.+?)(?:\s*`{CLOCK}`\s*[-–—~～至到]+\s*`{CLOCK}`.*)?\s*$')
ITEM = re.compile(r'^(\s*)[-*]\s*\*\*P(\d+)\*\*(.*)$')
TOKEN = re.compile(r'\s*(`[^`\n]*`|（[^）\n]*）|\([^)\n]*\)|(←|反驳|步骤)\s*((?:P\d+[\s,，、和]*)+))')
TIME = re.compile(rf'^`{CLOCK}`$')
JOIN = re.compile(r'^\s+[-*]\s*接上\s*[:：]\s*(.+)$')
PICTURE = re.compile(r'\s*\[[^\]\n]*\]\(<?(?:frames|slide-extraction|slides)/[^)\n]*\)')
UP = {'support': 0, 'attack': 1, 'step': 1}  # which end of a relation is above: 0 the item written first, 1 the other
OWN = re.compile(r'^###\s+`?拓展`?\s.*?(?=^#{2,3}\s|\Z)', re.MULTILINE | re.DOTALL)  # a unit of the writer's own


def _section(text, name):
  found = re.search(rf'^##\s*{re.escape(name)}\s*\n(.*?)(?=^##\s|\Z)', text, re.MULTILINE | re.DOTALL)
  return found[1] if found else ''


def wanted(template_text):
  """Whether a template leaves 主线与单元 to the program."""
  return MARK in _section(template_text, HEADING)


class Item:
  def __init__(self, number, part):
    self.number, self.part, self.tag, self.claim = number, part, '', ''
    self.joins = []  # (number, where the link comes from), on a main conclusion


def parse(text):
  """(items by number in the order written, relations as (upper, lower, kind)) from 详细内容."""
  items, relations, part, current = {}, [], None, None
  for line in _section(text, '详细内容').splitlines():
    heading = PART.match(line)
    if heading:
      part, current = heading[1].strip(), None
      continue
    found = ITEM.match(line)
    if found and found[2] not in items:
      current = Item(found[2], part)
      items[current.number] = current
      rest = found[3]
      while token := TOKEN.match(rest):
        if token[2]:
          kind = {'←': 'support', '反驳': 'attack', '步骤': 'step'}[token[2]]
          for other in re.findall(r'P(\d+)', token[3]):
            pair = (current.number, other)
            relations.append((pair[UP[kind]], pair[1 - UP[kind]], kind))
        elif not current.tag and not TIME.match(token[1]) and token[1].startswith('`'):
          current.tag = token[1]
        elif current.tag and token[1].startswith(('（', '(')):
          current.tag += token[1]  # 引用（出处；讲者的态度）
        rest = rest[token.end() :]
      current.claim = PICTURE.sub('', rest).strip()
      continue
    join = JOIN.match(line)
    if join and current:
      for entry in re.split(r'[；;]', join[1]):
        number = re.search(r'P(\d+)', entry)
        if number:
          current.joins.append((number[1], entry[number.end() :].strip(' ：:，,')))
  return items, relations


def build(text):
  """(the 主线与单元 section, problems to tell the writer); the section is '' when no items are related."""
  items, relations = parse(text)
  problems = []
  unknown = sorted({n for a, b, _ in relations for n in (a, b) if n not in items}, key=int)
  if unknown:
    problems.append('这些编号在关系里用到了，详细内容里却没有这个命题：' + '、'.join(f'P{n}' for n in unknown) + '。')
  mains = [item for item in items.values() if item.joins]
  for main in mains:
    for number, _ in main.joins:
      if number not in items:
        problems.append(f'P{main.number} 的「接上」里有 P{number}，详细内容里却没有这个命题。')
      elif not any({a, b} == {main.number, number} for a, b, _ in relations):
        relations.append((main.number, number, 'support'))
  relations = [(a, b, kind) for a, b, kind in dict.fromkeys(relations) if a in items and b in items and a != b]
  main_numbers = {main.number for main in mains}

  # Groups of related items, the main conclusions left out: each is a unit, or belongs to the main line.
  inner = [(a, b, kind) for a, b, kind in relations if a not in main_numbers and b not in main_numbers]
  group = {n: n for n in items}

  def find(n):
    while group[n] != n:
      group[n] = group[group[n]]
      n = group[n]
    return n

  for a, b, _ in inner:
    group[find(a)] = find(b)
  members = {}
  for n in items:
    members.setdefault(find(n), []).append(n)
  joined = {number for main in mains for number, _ in main.joins}
  next_to_main = {b if a in main_numbers else a for a, b, _ in relations if (a in main_numbers) != (b in main_numbers)}
  # A group next to the main conclusion with nothing in 接上 belongs to the main line when what links it is a quotation
  # or a filled-in premise (prompts/summary.md); a group of one is in no unit.
  plain = {n for n in next_to_main if items[n].tag.startswith(('`引用`', '`补全`'))}
  owned = {
    key
    for key, names in members.items()
    if len(names) == 1 or set(names) & next_to_main and not set(names) & joined and set(names) & next_to_main <= plain
  }

  order = {n: i for i, n in enumerate(items)}
  shown_edges = set()
  lines = []

  def line(number, depth, prefix='', suffix='', note=''):
    item = items[number]
    tag = f' {item.tag}' if item.tag else ''
    lines.append(f'{"  " * depth}- {prefix}[**P{number}**](#P{number}){tag}{suffix} {item.claim}{note}'.rstrip())

  def expand(number, depth, allowed, seen):
    """Lines for the items under `number` that are in `allowed`, each expanded once (in `seen`): the items next to it
    are taken here before any is expanded, so an item is expanded at the highest place it has."""
    edges = sorted(
      (edge for edge in relations if number in edge[:2] and edge[0] in allowed and edge[1] in allowed),
      key=lambda edge: (edge[0] != number, order[edge[1] if edge[0] == number else edge[0]]),
    )
    taken = []
    for edge in edges:
      if edge in shown_edges:
        continue
      shown_edges.add(edge)
      other = edge[1] if edge[0] == number else edge[0]
      taken.append((edge, other, other not in seen))
      seen.add(other)
    for (upper, lower, kind), other, fresh in taken:
      if upper == number:  # the other item is below this one
        prefix, suffix = {'support': '← ', 'attack': '反驳 ', 'step': ''}[kind], ''
      elif kind == 'support':  # the other item stands on this one: written as in 详细内容
        prefix, suffix = '', f' ← P{number}'
      else:
        prefix, suffix = '', f'（P{number} {"反驳它" if kind == "attack" else "是它的一步"}）'
      line(other, depth, prefix, suffix, '' if fresh else '（在别处展开）')
      if fresh:
        expand(other, depth + 1, allowed, seen)

  def root_of(names):
    """The item a unit starts from: one nothing stands above, an event with steps before others (an event and what it
    shows, as the template has it), then the one reaching the most items, then the first written."""
    names = set(names)
    lower = {b for a, b, _ in inner if a in names}
    tops = [n for n in names if n not in lower] or list(names)

    def reach(n, seen=None):
      seen = seen or {n}
      for a, b, _ in inner:
        if a == n and b not in seen:
          seen.add(b)
          reach(b, seen)
      return seen

    events = {a for a, _, kind in inner if kind == 'step'}
    return min(tops, key=lambda n: (n not in events, -len(reach(n)), order[n]))

  unit_root = {key: root_of(names) for key, names in members.items() if key not in owned}
  seen = set()
  for main in mains:
    lines.append('### 主线\n')
    line(main.number, 0)
    seen.add(main.number)
    sources = dict(main.joins)
    for upper, lower, kind in sorted(
      (edge for edge in relations if main.number in edge[:2]),
      key=lambda edge: order[edge[1] if edge[0] == main.number else edge[0]],
    ):
      other = lower if upper == main.number else upper
      key = find(other)
      shown_edges.add((upper, lower, kind))
      prefix = {'support': '← ', 'attack': '反驳 ', 'step': ''}[kind] if upper == main.number else ''
      if key in unit_root:
        said = sources.get(other)
        if said is None:
          problems.append(
            f'P{other} 接到了主结论 P{main.number}，「接上」里却没写这层关系的出处：讲者把它接到主结论的原话（时间和原话），'
            '或「总结者归纳」。'
          )
        note = f'（来自单元：P{unit_root[key]}；{said or "出处没写"}）'
        line(other, 1, prefix, '', note)
      else:
        note = f'（{sources[other]}）' if sources.get(other) else ''
        seen.add(other)
        line(other, 1, prefix, '', note)
        expand(other, 2, set(members[key]), seen)
    lines.append('')

  by_part = {}
  for key, root in sorted(unit_root.items(), key=lambda pair: order[pair[1]]):
    by_part.setdefault(items[root].part, []).append(root)
  for part, roots in by_part.items():
    lines.append(f'### {part or "（没有分段）"}\n')
    for root in roots:
      seen.add(root)
      line(root, 0)
      expand(root, 1, set(members[find(root)]), seen)
      lines.append('')
  if not lines:
    return '', problems
  return f'## {HEADING}\n\n' + '\n'.join(lines).rstrip() + '\n', problems


def place(text, template_text):
  """The summary with 主线与单元 written by the program where the template has it, and what was found wrong; the text
  unchanged when the template leaves the section to the writer."""
  if not wanted(template_text):
    return text, []
  section, problems = build(text)
  own = [block.rstrip() + '\n' for block in OWN.findall(_section(text, HEADING))]
  if own:
    section = (section or f'## {HEADING}\n') + '\n' + '\n'.join(own)
  found = re.search(rf'^##\s*{HEADING}\s*\n.*?(?=^##\s|\Z)', text, re.MULTILINE | re.DOTALL)
  if found:
    return text[: found.start()] + (section + '\n' if section else '') + text[found.end() :], problems
  if not section:
    return text, problems
  order = re.findall(r'^##\s+(.+?)\s*$', template_text.split(f'## {HEADING}', 1)[-1], re.MULTILINE)
  for name in order:
    later = re.search(rf'^##\s*{re.escape(name)}\s*$', text, re.MULTILINE)
    if later:
      return text[: later.start()] + section + '\n' + text[later.start() :], problems
  return text.rstrip() + '\n\n' + section, problems
