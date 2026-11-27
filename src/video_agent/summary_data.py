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


def view(data):
  """The two outlines over the units (ADR-0013), for the Markdown and for the app to draw.

  points: each mainline under its topic, its units in time order; a unit's own sides under it, a side between two units
  or for a whole mainline in its place in time; a unit whose head is a conclusion marked. The conclusions the summarizer
  drew are not here: the speaker did not say them. argument: the units as a forest along 支撑 and 铺垫, each under what
  it supports or sets up; a unit in neither stands alone; a unit reached twice is expanded once. units: each unit's
  items in the order each outline opens them, and the items one level down that each outline brings forward."""
  units = {u['id']: u for u in data['units']}
  start = lambda uid: units[uid]['start'] if uid in units else 0
  return {
    'points': _points(data, units, start),
    'argument': _argument(data, units, start),
    'about': about(data),
    'units': {
      uid: {
        'points': [{'item': item['id'], 'depth': depth} for depth, item in tree(unit, 'points')],
        'argument': [{'item': item['id'], 'depth': depth} for depth, item in tree(unit, 'argument')],
        'points_more': [i['id'] for i in unit['items'] if i['parent'] == 'S0' and i['edge'] in FIRST['points']],
        'argument_more': [i['id'] for i in unit['items'] if i['parent'] == 'S0' and i['edge'] in FIRST['argument']],
      }
      for uid, unit in units.items()
    },
  }


UNCHECKED = '（AI 未核对）'


def about(data):
  """What the summary says of itself: the model that wrote it, how many places are unsure, how many pieces read off
  pictures are not checked."""
  texts = [part for u in data['units'] for item in u['items'] for part in (item['text'], item['details'])]
  return {
    'model': data.get('model', ''),
    'unsure': len(data['unsure']),
    'unchecked': sum(text.count(UNCHECKED) for text in texts),
  }


def about_line(found):
  parts = [f'模型：{found["model"]}'] if found['model'] else []
  return '；'.join([*parts, f'需确认 {found["unsure"]} 处', f'AI 未核对 {found["unchecked"]} 处']) + '。'


def _points(data, units, start):
  hosted, placed = {}, {}  # sides under a unit; sides in their place in time, by the mainline they go with
  member = {uid: (u['attach'] or {}).get('line') for uid, u in units.items()}
  for uid, u in units.items():
    side = (u['attach'] or {}).get('side') or {}
    if 'unit' in side:
      hosted.setdefault(side['unit'], []).append(uid)
    elif 'between' in side:
      placed.setdefault(('unit', side['between'][0]), []).append((uid, 'between'))
    elif 'line' in side:
      placed.setdefault(('line', side['line']), []).append((uid, 'line'))
  concluded = {c['unit'] for line in data['lines'] for c in line['conclusions'] if 'unit' in c}
  shown, groups = set(), []

  def rows(entries, depth=0):
    out = []
    for uid, side in sorted(entries, key=lambda e: start(e[0])):
      if uid in shown or uid not in units:
        continue
      shown.add(uid)
      out.append({'unit': uid, 'depth': depth, 'side': side, 'conclusion': uid in concluded})
      out += rows([(s, 'unit') for s in hosted.get(uid, [])], depth + 1)
    return out

  def line_of(uid, seen=()):  # the mainline a side goes with: that of what it hangs on
    if member.get(uid):
      return member[uid]
    side = (units[uid]['attach'] or {}).get('side') or {} if uid in units else {}
    host = side.get('unit') or (side.get('between') or [None])[0]
    return line_of(host, (*seen, uid)) if host and host not in seen else side.get('line')

  first = lambda line: min([start(u) for u in units if member.get(u) == line['id']] or [float('inf')])
  for line in sorted(data['lines'], key=first):
    entries = [(uid, None) for uid in units if member.get(uid) == line['id']]
    entries += placed.get(('line', line['id']), [])
    entries += [
      e for (kind, host), found in placed.items() if kind == 'unit' and line_of(host) == line['id'] for e in found
    ]
    groups.append({'line': line['id'], 'topic': line['topic'], 'rows': rows(entries)})
  if left := [(uid, None) for uid in units if uid not in shown]:
    groups.append({'line': None, 'topic': '归属有问题的单元', 'rows': rows(left)})
  return groups


def _argument(data, units, start):
  conclusions = {c['id']: c['text'] for line in data['lines'] for c in line['conclusions'] if 'id' in c}
  edges = [e for e in data['edges'] if e['kind'] in ('支撑', '铺垫') and e['from'] in units]
  edges = [e for e in edges if e['to'] in units or e['to'] in conclusions]
  into, gives = {}, set()
  for edge in edges:
    into.setdefault(edge['to'], []).append(edge)
    gives.add(edge['from'])
  out, shown = [], set()
  row = lambda **kw: (
    {'unit': None, 'text': '', 'depth': 0, 'kind': None, 'contribution': '', 'source': None, 'repeat': False} | kw
  )

  def grow(target, depth):
    for edge in sorted(into.get(target, []), key=lambda e: start(e['from'])):
      uid = edge['from']
      if uid in shown:
        out.append(row(unit=uid, depth=depth, kind=edge['kind'], repeat=True))
        continue
      shown.add(uid)
      out.append(
        row(unit=uid, depth=depth, kind=edge['kind'], contribution=edge['contribution'], source=edge['source'])
      )
      grow(uid, depth + 1)

  roots = [uid for uid in units if uid not in gives] + [k for k in conclusions if k in into]
  order = lambda r: start(r) if r in units else min(start(e['from']) for e in into[r])
  for root in sorted(roots, key=order):
    if root in units:
      shown.add(root)
      out.append(row(unit=root))
    else:
      out.append(row(text=conclusions[root]))
    grow(root, 1)
  for uid in units:  # units that only support each other in a ring
    if uid not in shown:
      shown.add(uid)
      out.append(row(unit=uid))
      grow(uid, 1)
  return out


def markdown(data):
  """The summary as Markdown (ADR-0013): the front; the points outline and the argument outline from `view`, each unit
  a link; then every unit, folded, for the links to open; then what is unsure."""
  units = {u['id']: u for u in data['units']}
  shape = view(data)

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
    out += ['', '### 须知', '', *listed(data['notices'])]
  out += [
    '',
    '## 概要',
    '',
    refs(data['abstract']),
    '',
    '## 关于这份总结',
    '',
    about_line(shape['about']),
    '',
    '## 要点提纲',
    '',
  ]
  sides = {'unit': '旁支', 'between': '旁支，插在两个单元之间', 'line': '旁支，给整条主线做背景'}
  for group in shape['points']:
    out += [f'### {refs(group["topic"]) or group["line"]}', '']
    for r in group['rows']:
      unit = units[r['unit']]
      marks = ''.join(
        f'【{m}】' for m in ([sides[r['side']]] if r['side'] else []) + (['主结论'] if r['conclusion'] else [])
      )
      out.append(f'{"  " * r["depth"]}- `{clock(unit["start"])}` {link(r["unit"])}{marks}：{refs(head(unit))}')
    out.append('')
  out += ['## 论证提纲', '']
  for r in shape['argument']:
    pad = '  ' * r['depth']
    if r['unit'] is None:
      out.append(f'{pad}- 总结者归纳：{refs(r["text"])}')
    elif r['repeat']:
      out.append(f'{pad}- {r["kind"]}：{link(r["unit"])}（在别处展开）')
    elif r['kind'] is None:
      out.append(f'{pad}- {link(r["unit"])}：{refs(head(units[r["unit"]]))}')
    else:
      source = r['source'] or {}
      said = (
        f'（讲者 `{clock(source["time"])}`：{refs(source["said"])}）'
        if source.get('by') == '讲者'
        else '（总结者归纳）'
        if source
        else ''
      )
      out.append(f'{pad}- {r["kind"]}：{link(r["unit"])}：{refs(r["contribution"] or head(units[r["unit"]]))}{said}')
  out += ['', '## 单元', '']
  for unit in data['units']:
    shown = re.sub(r'`([^`]+)`', r'<code>\1</code>', html.escape(refs(head(unit)), quote=False))
    summary = (
      f'<details id="{unit["id"]}"><summary><strong>{html.escape(unit["title"])}</strong> '
      f'<code>{clock(unit["start"])}–{clock(unit["end"])}</code>：{shown}</summary>'
    )
    out += [
      summary,
      '',
      *unit_markdown(unit, data, name, refs),
      '',
      '</details>',
      '',
    ]
  out += ['## 需确认', '', *listed(data['unsure'])]
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


FIRST = {'points': ('展开',), 'argument': ('支撑', '反驳', '步骤')}  # the edges each outline brings forward


def tree(unit, outline='points'):
  """[(depth, item)] of a unit as it shows opened: the head first, each item under its parent. Under one parent the
  items with the edges the outline is about come first (要点提纲: 展开, the aspects of a point; 论证提纲: 支撑, 反驳, 步骤,
  the reasons and steps), then the others; each in time order, one without a time where it was written."""
  items = unit['items']
  ids = {item['id'] for item in items}
  shown_time, last = {}, -1
  for item in items:
    last = item['time'] if item['time'] is not None else last
    shown_time[item['id']] = last
  children = {}
  for index, item in enumerate(items):
    parent = item['parent'] if item['parent'] in ids and item['id'] != 'S0' else None
    rank = 0 if item['edge'] in FIRST[outline] else 1
    children.setdefault(parent, []).append((rank, shown_time[item['id']], index, item))
  out, done = [], set()

  def put(item, depth):
    if item['id'] in done:
      return
    done.add(item['id'])
    out.append((depth, item))
    for *_, child in sorted(children.get(item['id'], []), key=lambda c: c[:3]):
      put(child, depth + 1)

  for *_, root in sorted(children.get(None, []), key=lambda c: (c[3]['id'] != 'S0', c[1], c[2])):
    put(root, 0)
  for item in items:  # parents in a ring: shown at the top rather than lost
    put(item, 0)
  return out


def item_line(item, depth, refs=lambda text: text):
  tags = ''.join(f'`{label}` ' for label in item['labels'])
  stamp = f'`{clock(item["time"])}` ' if item['time'] is not None else ''
  edge = f'{item["edge"]} · ' if item['edge'] and depth else ''
  return f'{"  " * depth}- **{item["id"]}** {edge}{tags}{stamp}{refs(item["text"])}'.rstrip()


def unit_markdown(unit, data, name, refs, outline='points'):
  """The whole unit, as it shows opened: its kind and attachment, then its tree."""
  out = [f'{unit["kind"]} · {where(unit, data, name)}', '']
  seen = set()  # a picture used for several items shows under the first of them
  for depth, item in tree(unit, outline):
    pad = '  ' * depth
    out.append(item_line(item, depth, refs))
    for line in item['details'].splitlines():
      out.append(f'{pad}  {refs(line)}' if line.strip() else '')
    for picture in item['pictures']:
      if picture['path'] not in seen:
        seen.add(picture['path'])
        out.append(f'{pad}  - [{picture["caption"] or "画面"}](<{picture["path"]}>)')
  return out
