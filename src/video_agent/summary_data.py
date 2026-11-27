"""A summary as data (ADR-0014): units of items in a tree, mainlines, and the edges between units that advance them.
The model's text is read into it once; what does not hold together is sent back to whoever wrote it; the Markdown that
readers of text get (a collection's overview, the version history, an export) is written from it."""

import html
import re

CLOCK = r'(\d{1,2}:\d{2}:\d{2})'
INSIDE = ('支撑', '反驳', '步骤', '展开')  # an item's edge to its parent in the unit
ADVANCE = ('支撑', '铺垫', '续')  # an edge between units that advances a mainline
UNIT = rf'(?:U\d{{6}}|`?{CLOCK[1:-1]}`?)'  # a unit by its id or by its start
FORMAT = 1


def seconds(text):
  return sum(int(part) * 60**place for place, part in enumerate(reversed(text.split(':'))))


def clock(second):
  second = round(second)
  return f'{second // 3600:02d}:{second // 60 % 60:02d}:{second % 60:02d}'


def unit_id(token):
  """U004027 for U004027, 00:40:27 or `00:40:27`."""
  token = token.strip('` ')
  return token if token.startswith('U') else 'U' + clock(seconds(token)).replace(':', '')


def blocks(body):
  """{'S<n>': the item line and the lines under it} of a 正文 section, in order."""
  found, key = {}, None
  for line in (body or '').splitlines():
    if match := re.match(r'^- \*\*S(\d+)\*\*', line):
      key = f'S{match[1]}'
      found[key] = [line]
    elif key and (line.startswith('  ') or not line.strip()):
      found[key].append(line)
    else:
      key = None
  return {k: '\n'.join(v).rstrip() for k, v in found.items()}


def bullets(body):
  """The bullet lines of a section, without 「无」."""
  lines = [line.strip()[2:].strip() for line in (body or '').splitlines() if line.strip().startswith(('- ', '* '))]
  return [line for line in lines if line.strip('。 ') not in ('无', '没有')]


# ---- one unit --------------------------------------------------------------------------------------------------------


def read_item(key, block):
  """An item from its block: what follows **S<n>** is the edge to its parent, the tags and the time, in any order, then
  the text; the indented lines under it are its details."""
  first, _, rest = block.partition('\n')
  line = re.sub(r'^- \*\*S\d+\*\*', '', first)
  item = {'id': key, 'parent': None, 'edge': None, 'time': None, 'labels': [], 'text': '', 'pictures': []}
  parents = []
  while True:
    line = line.lstrip()
    if match := re.match(r'(支撑|反驳|步骤|展开)\s*S(\d+)', line):
      parents.append((match[1], f'S{match[2]}'))
    elif match := re.match(rf'`{CLOCK}`', line):
      item['time'] = item['time'] if item['time'] is not None else seconds(match[1])
    elif match := re.match(r'`([^`\n]+)`', line):
      item['labels'].append(match[1])
    else:
      break
    line = line[match.end() :]
  if parents:
    item['edge'], item['parent'] = parents[0]
  item['text'] = line.strip()
  item['details'] = '\n'.join(l.removeprefix('  ') for l in rest.splitlines()).strip('\n')
  return item, parents


def read_items(body):
  """(items in written order, problems): the items of a unit's 正文, each hung on its parent; the problems are for the
  unit's writer."""
  items, problems = [], []
  for key, block in blocks(body).items():
    item, parents = read_item(key, block)
    first = block.split('\n', 1)[0]
    if '←' in first:
      problems.append(f'{key} 用了「←」：关系写在子节点上，每个条目写自己的父节点，例如「支撑 S0」')
    if key == 'S0' and parents:
      problems.append('S0 是单元的头，不写父节点')
    elif key != 'S0' and not parents and '←' not in first:
      problems.append(f'{key} 没有写父节点：在编号后面写「支撑／反驳／步骤／展开 S<n>」')
    if len(parents) > 1:
      problems.append(f'{key} 写了 {len(parents)} 个父节点，只能有一个')
    items.append(item)
  ids = {item['id'] for item in items}
  if 'S0' not in ids:
    problems.insert(0, '没有头 **S0**：单元让读者带走的那一句写成 S0')
  parent = {item['id']: item['parent'] for item in items}
  for item in items:
    if item['parent'] and item['parent'] not in ids:
      problems.append(f'{item["id"]} 的父节点 {item["parent"]} 不存在')
      continue
    seen, at = {item['id']}, item['parent']
    while parent.get(at):
      if at in seen:
        problems.append(f'{item["id"]} 往上的父节点连成了环')
        break
      seen.add(at)
      at = parent[at]
  if re.search(r'\]\([^)\s]*\.(?:jpe?g|png)>?\)', body or ''):
    problems.append('「## 正文」里有图片链接：正文不写链接，图在「## 画面」里写「#<编号> 用在 S<n>：……」挂到条目上')
  return items, problems


def read_pictures(shown, paths):
  """({'S<n>': [(path, caption)]}, problems) from a unit's 「## 画面」 lines 「#3 用在 S1、S2：caption. 读出（…）：…」;
  `paths` is {number: picture path}."""
  found, problems = {}, []
  for line in (shown or '').splitlines():
    match = re.match(r'\s*-\s*((?:#\d+(?:\s*[–\-~]\s*#?\d+)?\s*[、,，]?\s*)+)(.*)', line)
    if not match or not (use := re.match(r'用在\s*((?:S\d+\s*[、,，和]?\s*)+)[:：]?\s*(.*)', match[2].strip())):
      continue
    numbers = set()
    for span in re.finditer(r'#(\d+)(?:\s*[–\-~]\s*#?(\d+))?', match[1]):
      numbers |= set(range(int(span[1]), int(span[2] or span[1]) + 1))
    caption = re.split(r'[。.]?\s*读出', use[2], maxsplit=1)[0].strip(' 。.')
    for key in re.findall(r'S\d+', use[1]):
      for number in sorted(numbers):
        if number in paths:
          found.setdefault(key, []).append((paths[number], caption))
        else:
          problems.append(f'#{number} 不在本单元的画面清单里')
  return found, problems


def unit_data(unit, draft, paths, section):
  """(the unit as data, problems for its writer); `section` reads a section of the draft."""
  items, problems = read_items(section(draft, '正文'))
  pictures, more = read_pictures(section(draft, '画面'), paths)
  ids = {item['id'] for item in items}
  problems += more + [f'「## 画面」里的 {key} 不存在' for key in pictures if key not in ids]
  for item in items:
    item['pictures'] = [{'path': path, 'caption': caption} for path, caption in pictures.get(item['id'], [])]
  data = {k: unit[k] for k in ('id', 'start', 'end', 'title', 'kind')} | {'attach': None, 'items': items}
  return data, problems


# ---- the whole -------------------------------------------------------------------------------------------------------


def read_attach(text):
  """An attachment: {'line': 'L1'}, or a side {'side': {'unit': U}}, {'side': {'between': [U, U]}}, {'side': {'line':
  'L1'}}; None for text that is none of them."""
  text = (text or '').strip(' 。')
  if match := re.fullmatch(r'(?:主线\s*)?(L\d+)', text):
    return {'line': match[1]}
  if not (match := re.match(r'(?:旁支[，,]?\s*)?岔出(?:自)?\s*(.+)', text)):
    return None
  where = match[1].strip()
  if re.fullmatch(r'L\d+', where):
    return {'side': {'line': where}}
  found = [unit_id(token) for token in re.findall(UNIT, where)]
  if len(found) == 2:
    return {'side': {'between': found}}
  return {'side': {'unit': found[0]}} if len(found) == 1 else None


def read_lines(text):
  """The mainlines: [{'id': 'L1', 'topic': …, 'conclusions': [{'unit': U} | {'id': 'K1', 'text': …}]}]."""
  found = []
  for line in (text or '').splitlines():
    if match := re.match(r'-\s*(L\d+)\s*(?:话题)?\s*[:：]?\s*(.*)', line.strip()):
      found.append({'id': match[1], 'topic': re.sub(r'^话题\s*[:：]\s*', '', match[2]).strip(), 'conclusions': []})
    elif found and (match := re.match(r'-\s*主结论\s*(K\d+)?\s*[:：]\s*(.*)', line.strip())):
      if match[1]:
        text_ = re.sub(r'`?总结者归纳`?\s*', '', match[2]).strip()
        found[-1]['conclusions'].append({'id': match[1], 'text': text_})
      elif units := re.findall(UNIT, match[2]):
        found[-1]['conclusions'].append({'unit': unit_id(units[0])})
  return found


def read_edges(text):
  """The edges between units: [{'from': U, 'to': U or K, 'kind': 支撑／铺垫／续, 'source': …, 'contribution': …}]."""
  found = []
  for line in bullets(text):
    match = re.match(rf'({UNIT})\s*(支撑|铺垫|续)\s*(K\d+|{UNIT})\s*(.*)', line)
    if not match:
      continue
    edge = {
      'from': unit_id(match[1]),
      'kind': match[2],
      'to': match[3] if match[3].startswith('K') else unit_id(match[3]),
    }
    edge |= {'source': None, 'contribution': ''}
    for part in re.split(r'\s*[|｜]\s*', match[4].strip(' |｜')):
      if said := re.match(rf'讲者\s*`?{CLOCK}`?\s*[:：]?\s*(.*)', part):
        edge['source'] = {'by': '讲者', 'time': seconds(said[1]), 'said': said[2].strip()}
      elif part.startswith('总结者归纳'):
        edge['source'] = {'by': '总结者归纳'}
      elif gives := re.match(r'贡献\s*[:：]\s*(.*)', part):
        edge['contribution'] = gives[1].strip()
    found.append(edge)
  return found


def whole_problems(units, attach_text, lines, edges):
  """What does not hold together in the mainlines, the attachments and the edges (ADR-0012), for the main
  conversation; `units` are the unit ids in order. Returns (problems, {unit: attachment})."""
  problems, attach = [], {}
  known = set(units)
  for line in bullets(attach_text):
    if not (match := re.match(rf'({UNIT})\s*[:：]?\s*(.*)', line)):
      continue
    uid, where = unit_id(match[1]), read_attach(match[2])
    if uid not in known:
      problems.append(f'「## 归属」里的 {uid} 不是单元')
    elif where is None:
      problems.append(f'{uid} 的归属读不懂：{match[2][:40]}（写 L<n>，或「岔出 U…」「岔出 U…–U…」「岔出 L<n>」）')
    elif uid in attach:
      problems.append(f'{uid} 写了不止一个归属')
    else:
      attach[uid] = where
  problems += [f'{uid} 没有归属' for uid in units if uid not in attach]
  ids = {line['id'] for line in lines}
  ks = {c['id'] for line in lines for c in line['conclusions'] if 'id' in c}
  for line in lines:
    if not line['topic']:
      problems.append(f'{line["id"]} 没有话题')
    for c in line['conclusions']:
      if 'unit' in c and attach.get(c['unit']) != {'line': line['id']}:
        problems.append(f'{line["id"]} 的主结论在 {c["unit"]}，但 {c["unit"]} 不属于 {line["id"]}')
  for uid, where in attach.items():
    side = where.get('side', {})
    for ref in [where.get('line'), side.get('line')]:
      if ref and ref not in ids:
        problems.append(f'{uid} 的归属 {ref} 不是一条主线')
    for ref in ([side['unit']] if 'unit' in side else []) + side.get('between', []):
      if ref not in known:
        problems.append(f'{uid} 挂在 {ref} 上，{ref} 不是单元')
  for line in lines:
    if not line['conclusions'] and not any(where == {'line': line['id']} for where in attach.values()):
      problems.append(f'{line["id"]} 没有单元')
  for edge in edges:
    a, b = edge['from'], edge['to']
    if a not in known or (b not in known and b not in ks):
      problems.append(f'「{a} {edge["kind"]} {b}」里有不存在的单元或主结论')
      continue
    if edge['kind'] == '续':
      ends = attach.get(a, {}), attach.get(b, {})
      if not (('line' in ends[0] and ends[0] == ends[1]) or all('side' in end for end in ends)):
        problems.append(f'{a} 续 {b}：「续」的两端要在同一条主线里')
      continue
    if 'side' in attach.get(b, {}):
      problems.append(f'{b} 标成了旁支，但 {a} 对它有{edge["kind"]}关系：有单元依赖它，它不是旁支')
    if 'side' in attach.get(a, {}):
      problems.append(f'{a} 标成了旁支，但它{edge["kind"]} {b}：推进别的单元的不是旁支')
  for line in lines:
    ends = {c.get('unit') or c['id'] for c in line['conclusions']}
    if not ends:
      continue
    members = {uid for uid, where in attach.items() if where == {'line': line['id']}}
    reached, grew = set(ends), True
    while grew:
      grew = False
      for edge in edges:
        if edge['from'] in members and edge['to'] in reached and edge['from'] not in reached:
          reached.add(edge['from'])
          grew = True
    for uid in sorted(members - reached):
      problems.append(f'{uid} 属于 {line["id"]}，但沿推进边走不到它的主结论：漏了推进边，或归属写错了')
  return problems, attach


# ---- Markdown --------------------------------------------------------------------------------------------------------


def markdown(data):
  """The summary as Markdown (ADR-0013): the front, then two outlines over the same units. The time outline lists every
  unit in time order by its head, folded, and opens to the whole unit; the mainline outline lists each mainline's units
  by what they give it, each linking to its unit in the time outline. Opened all, either outline gives every unit."""
  units = {u['id']: u for u in data['units']}

  def name(uid):
    return f'「{units[uid]["title"]}」' if uid in units else uid

  def link(uid):
    return f'[「{units[uid]["title"]}」](#{uid})' if uid in units else uid

  def refs(text):  # the spaces a model puts around an id in Chinese go with it
    return re.sub(
      r' ?\bU(\d{6})(?:\.(S\d+))?\b ?',
      lambda m: name(f'U{m[1]}') + (m[2] or '') if f'U{m[1]}' in units else m[0],
      text or '',
    )

  def listed(lines):  # an item the model left empty (「预设：」) is left out
    return [f'- {refs(line)}' for line in lines if not re.fullmatch(r'[^：:]{1,12}[：:]\s*', line)] or ['无']

  out = [f'# {data["title"]}', '', data['video'], '', '## 元信息', '', *listed(data['meta'])]
  if data['notices']:
    out += ['', '### 需留意', '', *listed(data['notices'])]
  out += ['', '## 概要', '', refs(data['abstract']), '', '## 时间提纲', '']
  for unit in data['units']:
    side = ' · 旁支' if 'side' in (unit['attach'] or {}) else ''
    shown = re.sub(r'`([^`]+)`', r'<code>\1</code>', html.escape(refs(head(unit)), quote=False))
    summary = (
      f'<details id="{unit["id"]}"><summary><strong>{html.escape(unit["title"])}</strong> '
      f'<code>{clock(unit["start"])}–{clock(unit["end"])}</code>{side}：{shown}</summary>'
    )
    out += [
      summary,
      '',
      *unit_markdown(unit, data, name, refs),
      '',
      '</details>',
      '',
    ]
  out += ['## 主线提纲', '', *mainlines(data, link, refs), '## 需确认', '', *listed(data['unsure'])]
  return '\n'.join(out).rstrip() + '\n'


def head(unit):
  first = next((item for item in unit['items'] if item['id'] == 'S0'), None)
  return first['text'] if first else ''


def where(unit, data, name):
  attach = unit['attach'] or {}
  topics = {line['id']: line['topic'] for line in data['lines']}
  if 'line' in attach:
    return f'主线：{topics.get(attach["line"], attach["line"])}'
  side = attach.get('side') or {}
  if 'unit' in side:
    return f'旁支，从{name(side["unit"])}岔出'
  if 'between' in side:
    return f'旁支，插在{name(side["between"][0])}和{name(side["between"][1])}之间'
  if 'line' in side:
    return f'旁支，挂在主线「{topics.get(side["line"], side["line"])}」上'
  return '没有归属'


def tree(unit):
  """[(depth, item)] of a unit in reading order: the head first, each item under its parent, items under one parent
  in time order (one without a time where it was written)."""
  items = unit['items']
  ids = {item['id'] for item in items}
  shown_time, last = {}, -1
  for item in items:
    last = item['time'] if item['time'] is not None else last
    shown_time[item['id']] = last
  children = {}
  for index, item in enumerate(items):
    parent = item['parent'] if item['parent'] in ids and item['id'] != 'S0' else None
    children.setdefault(parent, []).append((shown_time[item['id']], index, item))
  out, done = [], set()

  def put(item, depth):
    if item['id'] in done:
      return
    done.add(item['id'])
    out.append((depth, item))
    for _, _, child in sorted(children.get(item['id'], []), key=lambda c: c[:2]):
      put(child, depth + 1)

  for _, _, root in sorted(children.get(None, []), key=lambda c: (c[2]['id'] != 'S0', *c[:2])):
    put(root, 0)
  for item in items:  # parents in a ring: shown at the top rather than lost
    put(item, 0)
  return out


def item_line(item, depth, refs=lambda text: text):
  tags = ''.join(f'`{label}` ' for label in item['labels'])
  stamp = f'`{clock(item["time"])}` ' if item['time'] is not None else ''
  edge = f'{item["edge"]} · ' if item['edge'] and depth else ''
  return f'{"  " * depth}- **{item["id"]}** {edge}{tags}{stamp}{refs(item["text"])}'.rstrip()


def unit_markdown(unit, data, name, refs):
  """The whole unit, as it shows opened: its kind and attachment, then its tree."""
  out = [f'{unit["kind"]} · {where(unit, data, name)}', '']
  seen = set()  # a picture used for several items shows under the first of them
  for depth, item in tree(unit):
    pad = '  ' * depth
    out.append(item_line(item, depth, refs))
    for line in item['details'].splitlines():
      out.append(f'{pad}  {refs(line)}' if line.strip() else '')
    for picture in item['pictures']:
      if picture['path'] not in seen:
        seen.add(picture['path'])
        out.append(f'{pad}  - [{picture["caption"] or "画面"}](<{picture["path"]}>)')
  return out


def mainlines(data, name, refs):
  """The mainline outline: each mainline under its topic; one with conclusions grows from them along the edges, one
  without lists its units in time order; sides under what they hang on. A unit is expanded once, where it is
  highest."""
  units = {u['id']: u for u in data['units']}
  start = lambda uid: units[uid]['start'] if uid in units else 0
  into = {}
  for edge in data['edges']:
    into.setdefault(edge['to'], []).append(edge)
  member = {u['id']: (u['attach'] or {}).get('line') for u in data['units']}
  hanging = {}
  for u in data['units']:
    side = (u['attach'] or {}).get('side') or {}
    key = (
      ('unit', side['unit'])
      if 'unit' in side
      else ('unit', side['between'][0])
      if 'between' in side
      else ('line', side.get('line'))
    )
    if side:
      hanging.setdefault(key, []).append(u['id'])
  out, shown = [], set()

  def sides(key, depth):
    for uid in sorted(hanging.get(key, []), key=start):
      if uid in shown:
        continue
      shown.add(uid)
      out.append(f'{"  " * depth}- 旁支 {name(uid)}：{refs(head(units[uid]))}')
      sides(('unit', uid), depth + 1)

  def grow(target, line, depth, level):
    for edge in sorted(into.get(target, []), key=lambda e: start(e['from'])):
      uid, pad = edge['from'], '  ' * depth
      if member.get(uid) != line['id']:
        out.append(f'{pad}- {edge["kind"]}：{name(uid)}（另一条主线）')
        continue
      if uid in shown or level.get(uid, depth) < depth:
        out.append(f'{pad}- {edge["kind"]}：{name(uid)}（在别处展开）')
        continue
      shown.add(uid)
      source = edge['source'] or {}
      said = (
        f'（讲者 `{clock(source["time"])}`：{source["said"]}）'
        if source.get('by') == '讲者'
        else '（总结者归纳）'
        if source
        else ''
      )
      out.append(f'{pad}- {edge["kind"]}：{name(uid)}：{refs(edge["contribution"] or head(units[uid]))}{said}')
      sides(('unit', uid), depth + 1)
      grow(uid, line, depth + 1, level)

  def levels(ends, line):
    level, frontier, depth = {}, list(ends), 1
    while frontier:
      nxt = []
      for target in frontier:
        for edge in into.get(target, []):
          if member.get(edge['from']) == line['id'] and edge['from'] not in level:
            level[edge['from']] = depth
            nxt.append(edge['from'])
      frontier, depth = nxt, depth + 1
    return level

  first = lambda line: min([start(uid) for uid, l in member.items() if l == line['id']] or [0])
  for line in sorted(data['lines'], key=first):
    out += [f'### {refs(line["topic"]) or line["id"]}', '']
    for c in line['conclusions']:
      if 'unit' in c and c['unit'] in units:
        end = c['unit']
        shown.add(end)
        out.append(f'- 主结论 {name(end)}：{refs(head(units[end]))}')
        sides(('unit', end), 1)
      elif 'id' in c:
        end = c['id']
        out.append(f'- 主结论（总结者归纳）：{refs(c["text"])}')
      else:
        continue
      grow(end, line, 1, levels([end], line))
    rest = [uid for uid, l in member.items() if l == line['id'] and uid not in shown]
    for uid in sorted(rest, key=start):
      shown.add(uid)
      note = '（没有接到主结论）' if line['conclusions'] else ''
      out.append(f'- {name(uid)}：{refs(head(units[uid]))}{note}')
      sides(('unit', uid), 1)
    sides(('line', line['id']), 0)
    out.append('')
  if left := [uid for uid in units if uid not in shown]:
    out += ['### 归属有问题的单元', ''] + [
      f'- {name(uid)}：{refs(head(units[uid]))}' for uid in sorted(left, key=start)
    ]
  return out
