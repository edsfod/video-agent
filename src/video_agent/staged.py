"""`summarize --staged`: a video's summary written in stages (docs/design/staged.md). One main conversation that never
sees pictures marks the transcript and cuts it into units (M1), weighs the writers' objections to the cut (M2) and
writes the parts about the whole (M3); one conversation per unit writes that unit from its transcript and pictures and
is told in later turns what the program's checks found. The program checks, merges and assembles; the model only fixes
what it is told. State is the files in <video folder>/staged/<run>/, so a run cut short goes on where it stopped."""

import json
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from . import evidence, files, importer, media, staged_agy, templates
from . import staged_prompts as prompts

FOLDER = 'staged'
STEP_S = 5  # one sample of the screen region every STEP_S seconds
GRAY = (64, 36)  # samples shrunk to this, in gray, for telling whether the screen changed
CHANGED = 0.03  # share of gray pixels that differ by more than 16 above which a sample is a new picture
MARGIN_S = 60  # transcript shown around a unit, and how far outside it a proposition's time may be
GAP_S = 30  # a stretch of transcript this long with no proposition time near it is reported
MAX_FIXES = 2
DUPLICATE = 0.5  # share of shared 4-character pieces above which two propositions of different units count as one
SCALE = 2  # single pictures are given at this many times their size: the screen region of a lecture can be 726×410
OVERLAP = 0.08  # share of the picture a zoomed region reaches past its edges
REGIONS = {
  '全图': (0, 0, 1, 1),
  '上半': (0, 0, 1, 0.5),
  '下半': (0, 0.5, 1, 1),
  '左半': (0, 0, 0.5, 1),
  '右半': (0.5, 0, 1, 1),
  '左上': (0, 0, 0.5, 0.5),
  '右上': (0.5, 0, 1, 0.5),
  '左下': (0, 0.5, 0.5, 1),
  '右下': (0.5, 0.5, 1, 1),
}
# A proposition line that only says what was shown; 「讲者展示了……」 followed by what it shows is content, so only a
# short line is reported.
POINTER = re.compile(r'(讲者|视频|老师)?(展示了|介绍了|讲解了|演示了|讲了|谈到|提到了|说明了一个)')
LEAD = re.compile(r'^(?:讲者|视频|老师)?(?:演示|展示|介绍|讲解|阐明|阐述|细化|归纳|探讨|梳理|说明|分析)(?!了)')
POINTER_LEN = 40
# A formula read off a picture and not checked on an enlarged crop is marked for the reader: the writer does not
# see which small characters it misread. Paths, commands and messages are mostly read right.
UNCHECKED = '（AI 未核对）'
UNCHECKED_LEN = 20
FORMULA = re.compile(r'^=|[A-Z]{2,}\(|\$[A-Z]{1,3}\$?\d|[A-Z]{1,3}\$\d')
COMMAND = re.compile(
  r'^(\$\s|>\s|(ls|cd|cat|git|fd|find|eza|sudo|for|echo|lsusb|xdg-open|vi|vim|nvim|make|python3?|pip|curl|head|tail|'
  r'grep|sleep|dmesg)\b)'
)
CLOCK = r'(\d{1,2}:\d{2}:\d{2})'
SPAN = re.compile(rf'`?{CLOCK}`?\s*[-–—~至]+\s*`?{CLOCK}`?\s*(.*)')
LABEL = re.compile(r'^- (?:#\d+(?:\s*[–\-~]\s*#?\d+)?\s*[、,，]?\s*)+')
LOCK = threading.Lock()


class StagedError(RuntimeError):
  pass


# ---- text ------------------------------------------------------------------------------------------------------------


def seconds(text):
  return sum(int(part) * 60**place for place, part in enumerate(reversed(text.split(':'))))


def clock(second):
  second = round(second)
  return f'{second // 3600:02d}:{second // 60 % 60:02d}:{second % 60:02d}'


def section(text, name):
  found = re.search(rf'^##\s*{re.escape(name)}\s*\n(.*?)(?=^##\s|\Z)', text or '', re.MULTILINE | re.DOTALL)
  return found[1].strip() if found else None


def replace_section(text, name, body):
  return re.sub(
    rf'(^##\s*{re.escape(name)}\s*\n).*?(?=^##\s|\Z)',
    lambda m: m[1] + body + '\n\n',
    text,
    count=1,
    flags=re.MULTILINE | re.DOTALL,
  )


def items(body):
  """The bullet lines of a section, without 「无」."""
  lines = [line.strip()[2:].strip() for line in (body or '').splitlines() if line.strip().startswith(('- ', '* '))]
  return [line for line in lines if line.strip('。 ') not in ('无', '没有')]


def read(path):
  return Path(path).read_text(encoding='utf-8') if Path(path).is_file() else None


def write(path, text):
  Path(path).parent.mkdir(parents=True, exist_ok=True)
  files.write_text(Path(path), text)


def posix(path):
  return Path(path).as_posix()


def blocks(body):
  """{'S<n>': the proposition line and its sub-lines} of a 正文 section, in order."""
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


def numbers(line):
  """The picture numbers a 「## 画面」 line starts with: #3, #3–#5, #3、#7."""
  found = set()
  for match in re.finditer(r'#(\d+)(?:\s*[–\-~]\s*#?(\d+))?', (LABEL.match(line) or [''])[0]):
    found |= set(range(int(match[1]), int(match[2] or match[1]) + 1))
  return found


def pieces(text):
  plain = re.sub(r'`[^`]*`|\[[^\]]*\]\([^)]*\)|\*\*S\d+\*\*|[\s，。、；：:（）()「」"“”]', '', text)
  return {plain[i : i + 4] for i in range(len(plain) - 3)}


def unreadable(reply):
  """A fix reply whose 正文 has content but no proposition the merge can read."""
  body = (section(reply, '正文') or '').strip()
  return bool(body) and body != '无' and not blocks(body)


def parse_regular(text):
  """{'fixes': [(wrong, right)], 'anchors': [...], 'empty': [...]} from M1's marks."""
  fixes = []
  for line in items(section(text, '改正')):
    if (found := re.match(r'(.+?)\s*(?:→|->|=>)\s*(.+)', line)) and found[1].strip() != found[2].strip():
      fixes.append((found[1].strip().strip('`「」'), found[2].strip().strip('`「」')))
  anchors, empty = [], []
  for line in items(section(text, '锚点')):
    if found := SPAN.search(line):
      kind = '必看' if '必看' in found[3][:6] else '细节'
      what = re.sub(r'^(必看|细节)\s*[:：]?\s*', '', found[3]).strip()
      anchors.append({'start': seconds(found[1]), 'end': seconds(found[2]), 'kind': kind, 'what': what})
  for line in items(section(text, '无内容')):
    if found := SPAN.search(line):
      empty.append({'start': seconds(found[1]), 'end': seconds(found[2]), 'why': found[3].strip()})
  anchors.sort(key=lambda a: a['start'])
  for number, anchor in enumerate(anchors, 1):
    anchor['id'] = f'A{number}'
  return {'fixes': fixes, 'anchors': anchors, 'empty': empty}


def parse_units(text, length):
  """The unit table: each unit runs from its start to the next one's. A unit's id is its start (U004027), so a unit
  whose start stays keeps its folder and turns when the table changes around it."""
  found = []
  for line in items(section(text, '单元')):
    if not (match := re.match(rf'`?{CLOCK}`?\s*(.*)', line)):
      continue
    parts = [part.strip() for part in match[2].split('|')] + ['', '']
    found.append({'start': seconds(match[1]), 'title': parts[0], 'kind': parts[1] or '论证', 'line': parts[2]})
  found.sort(key=lambda u: u['start'])
  for number, unit in enumerate(found):
    unit['id'] = 'U' + clock(unit['start']).replace(':', '')
    unit['end'] = found[number + 1]['start'] if number + 1 < len(found) else length
    unit['skip'] = '略过' in unit['kind']
  return found


def unit_problems(units, length):
  if not units:
    return ['单元表是空的，或格式不对']
  problems = []
  if units[0]['start'] > 60:
    problems.append('第一个单元没有从视频开头开始')
  if any(not 0 <= u['start'] < length for u in units):
    problems.append('有单元的起点不在视频里')
  return problems


def merge(text, patch):
  """A unit's draft with a fix reply merged in: (text, propositions changed). A proposition replaces the one of its
  number; one given without its sub-lines replaces only the proposition line. A picture line replaces the numbers it
  names, and an old line that covered more (#5–#6) keeps the rest (#6). A section the reply writes again replaces the
  old one."""
  old, new = blocks(section(text, '正文')), blocks(section(patch, '正文'))
  for key, block in new.items():
    if key in old and '\n' not in block.strip() and '\n' in old[key]:
      new[key] = block.strip() + '\n' + old[key].split('\n', 1)[1]
  merged = {**old, **new}
  shown = [(numbers(line), line) for line in (section(text, '画面') or '').splitlines() if line.strip()]
  for line in (section(patch, '画面') or '').splitlines():
    line = re.sub(r'^\s*(?=#\d)', '- ', line)
    if mine := numbers(line):
      kept = []
      for theirs, old_line in shown:
        if theirs & mine:
          if left := sorted(theirs - mine):
            kept.append((set(left), LABEL.sub('- ' + '、'.join(f'#{n}' for n in left) + ' ', old_line, count=1)))
        else:
          kept.append((theirs, old_line))
      shown = kept + [(mine, line)]
  shown.sort(key=lambda item: min(item[0]) if item[0] else 0)
  text = replace_section(text, '正文', '\n'.join(merged[k] for k in sorted(merged, key=lambda k: int(k[1:]))))
  if shown:
    text = replace_section(text, '画面', '\n'.join(line for _, line in shown))
  for name in ('事项', '预设', '需确认', '要点候选', '边界', '补截'):
    if (replaced := section(patch, name)) is not None and section(text, name) is not None:
      text = replace_section(text, name, replaced)
  return text, len(new)


def pointer(head):
  """A proposition line that only names what the video did there."""
  plain = re.sub(r'\[[^\]]*\]\([^)]*\)', '', head)
  plain = re.sub(r'^-\s*\*\*S\d+\*\*\s*|`[^`]*`\s*|←.*$', '', plain).strip()
  return bool(POINTER.search(plain) or LEAD.match(plain)) and len(plain) <= POINTER_LEN


def mark_unchecked(text, checked=()):
  """(text, how many marked): in 「## 正文」, each formula of UNCHECKED_LEN characters or more that is not in `checked`
  (read again on an enlarged crop) and not marked already gets UNCHECKED after it."""
  marked = 0

  def mark(match):
    nonlocal marked
    code = match[1]
    if len(code) < UNCHECKED_LEN or code in checked or not FORMULA.search(code) or COMMAND.match(code):
      return match[0]
    after = match.string[match.end() : match.end() + 12].lstrip()
    if after.startswith(('（AI 未核对', '(AI 未核对', 'AI 未核对', '（看不清', '看不清')):
      return match[0]
    marked += 1
    return match[0] + UNCHECKED

  head, heading, tail = text.partition('## 正文')
  if not heading:
    return text, 0
  rest = re.split(r'(?m)^(?=## )', tail, maxsplit=1)
  rest[0] = re.sub(r'`([^`\n]+)`', mark, rest[0])
  return head + heading + ''.join(rest), marked


def unlink_dropped(text, paths, own):
  """(text, how many): links in 「## 正文」 to a picture the unit itself marks 无用 go to the picture it repeats
  (「重复 #m」), or away. `paths` is {number: path}, `own` {path: why}."""
  fixed = 0

  def unlink(match):
    nonlocal fixed
    if match[3] not in own:
      return match[0]
    fixed += 1
    same = re.search(r'重复\s*#(\d+)', own[match[3]])
    if same and int(same[1]) in paths and paths[int(same[1])] not in own:
      return f'{match[1]}{match[2]}{paths[int(same[1])]}{match[4]}'
    return ''

  head, heading, tail = text.partition('## 正文')
  if not heading:
    return text, 0
  rest = re.split(r'(?m)^(?=## )', tail, maxsplit=1)
  rest[0] = re.sub(r'( ?)(\[[^\]]*\]\(<?)([^)>]+?\.(?:jpe?g|png))(>?\))', unlink, rest[0])
  return head + heading + ''.join(rest), fixed


def objections(texts):
  """{unit id: its writer's 「## 边界」} for the units whose writer objected to the table; `texts` is {id: draft}."""
  found = {}
  for uid, text in texts.items():
    said = (section(text or '', '边界') or '').strip()
    if said and not re.match(r'^[-\s]*无\s*[。.]?$', said):
      found[uid] = said
  return found


def duplicates(drafts):
  """Proposition pairs of different units that say the same thing: {later unit id: [what to tell it]}. `drafts` is
  [(unit id, draft)] in order."""
  found, seen = {}, []
  for uid, text in drafts:
    for key, block in blocks(section(text or '', '正文')).items():
      head = block.splitlines()[0]
      mine = pieces(head)
      for other, other_key, other_head, theirs in seen:
        if other != uid and mine and theirs and len(mine & theirs) / len(mine | theirs) > DUPLICATE:
          found.setdefault(uid, []).append(
            f'{key} 和 {other} 的 {other_key} 说的是同一件事：{other_head[:80]}——删掉，或只留本单元特有的部分'
          )
      seen.append((uid, key, head, mine))
  return found


def numbered(units, drafts):
  """(详细内容, {P: (second, line)}, [(unit, {S: P})], next number): the units' propositions numbered P1, P2… through
  the whole, with their relations. `drafts` is {unit id: draft}."""
  parts, props, maps, number = [], {}, [], 0
  for unit in units:
    if unit['skip']:
      continue
    body = section(drafts.get(unit['id']) or '', '正文') or ''
    mapping = {}
    for match in re.finditer(r'^- \*\*S(\d+)\*\*', body, re.MULTILINE):
      if match[1] not in mapping:
        number += 1
        mapping[match[1]] = number

    def relation(match, mapping=mapping):
      return match[1] + ' ' + re.sub(r'S(\d+)', lambda m: f'P{mapping.get(m[1], m[1])}', match[2])

    text = re.sub(r'\*\*S(\d+)\*\*', lambda m, mapping=mapping: f'**P{mapping.get(m[1], m[1])}**', body)
    text = re.sub(r'(←|反驳|步骤)\s*((?:S\d+\s*[,，、]?\s*)+)', relation, text)
    for match in re.finditer(r'^- \*\*P(\d+)\*\*(.*)$', text, re.MULTILINE):
      stamp = re.search(rf'`{CLOCK}`', match[2])
      props[int(match[1])] = (seconds(stamp[1]) if stamp else unit['start'], match[0])
    parts.append(f'### {unit["title"]} `{clock(unit["start"])}`–`{clock(unit["end"])}`\n\n{text.strip()}\n')
    maps.append((unit, mapping))
  return '\n'.join(parts), props, maps, number + 1


def assemble(units, drafts, whole, head):
  """The summary in the template's form: the units' 详细内容, and 元信息, 概要, 要点 and the rest from M3's reply
  `whole`. 要点 are written by the program from the propositions M3 names; `head` is the title and the 视频 line."""
  body, props, _, next_number = numbered(units, drafts)
  joined = '；'.join(item.rstrip('。') for item in items(section(whole, '接上')))
  main = (items(section(whole, '主结论')) or [''])[0]
  summarizer = ''
  if main and '总结者归纳' in main:
    premises = ', '.join(f'P{n}' for n in re.findall(r'P(\d+)', main))
    claim = re.sub(r'`?总结者归纳`?|[（(]?\s*←\s*(P\d+\s*[,，、]?\s*)+[）)]?|[，,。；;]+$', '', main).strip(' ，,：:')
    summarizer = f'\n### 总结者归纳\n\n- **P{next_number}** `总结者归纳` ← {premises} {claim}\n'
    summarizer += f'  - 接上：{joined}\n' if joined else ''
  elif main and (found := re.search(r'P(\d+)', main)) and joined:
    lines = body.split('\n')
    start = next((i for i, line in enumerate(lines) if line.startswith(f'- **P{found[1]}**')), None)
    if start is not None:
      end = start + 1
      while end < len(lines) and lines[end].startswith('  '):
        end += 1
      lines.insert(end, f'  - 接上：{joined}')
      body = '\n'.join(lines)
  steps = {}
  for n, (_, line) in props.items():
    for match in re.finditer(r'步骤\s*P(\d+)', line):
      steps.setdefault(int(match[1]), []).append(n)
  tags = r'`(?:\d{1,2}:\d{2}:\d{2}|引用|观点|推断|事实|总结者归纳)`'  # only times and tags; other code spans stay
  relation = r'(?:←\s*(?:P\d+\s*[,，、]?\s*)+|反驳\s*P\d+\s*|步骤\s*P\d+\s*)'
  points = []
  for item in items(section(whole, '要点')):
    named = [int(n) for n in re.findall(r'P(\d+)', item) if int(n) in props]
    if not named:
      continue
    near = set(named)  # the time span of a point covers its premises and steps
    for n in named:
      if arrow := re.search(r'←\s*((?:P\d+\s*[,，、]?\s*)+)', props[n][1]):
        near |= {int(p) for p in re.findall(r'P(\d+)', arrow[1]) if int(p) in props}
      near |= set(steps.get(n, []))
    times = sorted(props[n][0] for n in near)
    text = re.sub(r'^- \*\*P\d+\*\*\s*', '', props[named[0]][1])
    text = re.sub(tags + rf'|`{relation}`|{relation}[。；;]?|\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\s{2,}', ' ', text).strip(' ：:')
    span = f'`{clock(times[0])}`' + (f'–`{clock(times[-1])}`' if times[-1] > times[0] else '')
    points.append(f'- {span} {text}（' + '、'.join(f'**P{n}**' for n in dict.fromkeys(named)) + '）')
  marker = '<!-- video-agent: 这一节由程序根据详细内容生成，你只写拓展单元 -->'
  return (
    f'{head}\n\n## 元信息\n\n{section(whole, "元信息") or ""}\n\n### 需留意\n\n{section(whole, "需留意") or ""}\n\n'
    f'## 概要\n\n{section(whole, "概要") or ""}\n\n## 要点\n\n'
    + '\n'.join(points)
    + f'\n\n## 主线与单元\n\n{marker}\n\n'
    f'## 详细内容\n\n{body.strip()}\n{summarizer}\n## 需确认\n\n{section(whole, "需确认") or "无"}\n'
  )


def rules(template_text):
  """(rules for a unit, rules for the whole): the template's sections each step needs."""
  chunks = re.split(r'^(?=## )', template_text, flags=re.MULTILINE)
  named = {chunk[3]: chunk for chunk in chunks if re.match(r'## [一二三四五六七]、', chunk)}
  note = '这是总结规则的一部分，只留下这一步用得到的节；各节怎么拼成整篇由程序做。\n\n'
  return note + ''.join(named.get(key, '') for key in '一二四五七'), note + ''.join(
    named.get(key, '') for key in '一二三'
  )


def usage_text(used):
  return (
    f'{used["calls"]} 次调用；读入（未命中缓存）{used["input"]:,}；缓存命中 {used["cache_read"]:,}；'
    f'输出 {used["output"]:,}（思考 {used["thinking"]:,}）'
  )


# ---- a run -----------------------------------------------------------------------------------------------------------


class Run:
  """One staged summary of a video. Everything it has done is in its folder; `go` reads what is there and does what is
  left."""

  def __init__(self, video, workspace, *, model=None, fix_model=None, restart=False, status=print, channel=staged_agy):
    self.video, info, self.asset, self.manifest = evidence.processed(video, workspace)
    self.workspace = Path(workspace)
    self.length = self.manifest.get('duration_s') or media.duration(info)
    self.channel, self.status = channel, status
    root = self.asset / FOLDER
    runs = sorted(p for p in root.glob('2*') if p.is_dir()) if root.is_dir() else []
    open_runs = [p for p in runs if not (p / 'imported').is_file()]
    self.dir = open_runs[-1] if open_runs and not restart else root / datetime.now().strftime('%Y%m%d-%H%M%S')
    self.dir.mkdir(parents=True, exist_ok=True)
    self.samples = root / 'samples'  # shared by the video's runs
    self.record = json.loads(read(self.dir / 'run.json') or '{}')
    self.record.setdefault('turns', {})
    self.record.setdefault('model', model or channel.MODEL)
    self.record.setdefault('fix_model', fix_model or channel.FIX_MODEL)
    self.save()
    self.unit_rules, self.whole_rules = rules(templates.built_in(templates.STANDARD))

  def say(self, text):
    line = f'[{time.strftime("%H:%M:%S")}] {text}'
    self.status(line)
    with LOCK, open(self.dir / 'progress.log', 'a', encoding='utf-8', newline='\n') as out:
      out.write(line + '\n')

  def save(self):
    with LOCK:
      write(self.dir / 'run.json', json.dumps(self.record, ensure_ascii=False, indent=1) + '\n')

  # ---- one turn ------------------------------------------------------------------------------------------------------

  def turn(self, key, prompt, conversation=None):
    self.say(f'开始 {key}' + ('（接着原对话）' if conversation else ''))
    model = self.record['fix_model'] if re.match(r'W-.*-(fix|dup)', key) else self.record['model']
    try:
      found = self.channel.turn(
        prompt, self.asset, self.dir / 'log' / f'{key}.log', conversation=conversation, model=model
      )
    except staged_agy.ChannelError as error:
      self.say(f'{key} 失败：{error}')
      return None
    with LOCK:
      self.record['turns'][key] = {
        k: found[k] for k in ('conversation', 'calls', 'failed', 'tools', 'tool_names', 'denied', 'usage', 'seconds')
      } | {'model': model}
    self.save()
    self.say(f'{key} 完成，{found["seconds"]:.0f} 秒，' + usage_text(found['usage'] | {'calls': found['calls']}))
    return found

  def total(self):
    total = {'calls': 0, 'input': 0, 'cache_read': 0, 'output': 0, 'thinking': 0}
    for found in self.record['turns'].values():
      total['calls'] += found['calls'] + found.get('failed', 0)
      for field in ('input', 'cache_read', 'output', 'thinking'):
        total[field] += found['usage'][field]
    return total

  # ---- material ------------------------------------------------------------------------------------------------------

  def raw_lines(self):
    path = self.asset / 'transcript.clean.txt'
    if not path.is_file():
      path = self.asset / 'transcript.txt'
    return [line for line in (read(path) or '').splitlines() if re.match(rf'\[{CLOCK}\]', line)]

  def regular(self):
    text = read(self.dir / 'regular.md')
    return parse_regular(text) if text is not None else None

  def units(self):
    text = read(self.dir / 'units.md')
    return parse_units(text, self.length) if text is not None else None

  def transcript(self):
    """The transcript with M1's corrections and its marks (anchors, stretches with no content) between the lines."""
    found = self.regular() or {'fixes': [], 'anchors': [], 'empty': []}
    marks = [
      (a['start'], f'⟨锚点 {a["id"]} {a["kind"]} {clock(a["start"])}–{clock(a["end"])}：{a["what"]}⟩')
      for a in found['anchors']
    ]
    marks += [(e['start'], f'⟨无内容 {clock(e["start"])}–{clock(e["end"])}：{e["why"]}⟩') for e in found['empty']]
    marks.sort(key=lambda m: m[0])
    out, index = [], 0
    for line in self.raw_lines():
      second = seconds(re.match(rf'\[{CLOCK}\]', line)[1])
      while index < len(marks) and marks[index][0] <= second:
        out.append(marks[index][1])
        index += 1
      for wrong, right in found['fixes']:
        line = line.replace(wrong, right)
      out.append(line)
    out += [mark for _, mark in marks[index:]]
    write(self.dir / 'transcript.md', '\n'.join(out) + '\n')
    return out

  def screen(self):
    """The screen region (x, y, w, h), or the whole picture."""
    layout = self.manifest.get('layout') or {}
    if layout.get('screen'):
      return layout['screen']
    width, height = layout.get('size') or media.frame_size(media.probe(self.video)[1])
    return [0, 0, width, height]

  def take_samples(self):
    """The screen region every STEP_S seconds in original pixels, and each sample shrunk to gray for telling whether
    the screen changed."""
    if (self.samples / 'gray.raw').is_file():
      return
    x, y, w, h = self.screen()
    self.samples.mkdir(parents=True, exist_ok=True)
    self.say(f'取样：每 {STEP_S} 秒一帧屏幕区域')
    graph = f'[0:v]fps=1/{STEP_S},crop={w}:{h}:{x}:{y},split=2[a][b];[b]scale={GRAY[0]}:{GRAY[1]},format=gray[g]'
    command = [media.tool('ffmpeg'), '-v', 'error', '-y', '-i', str(self.video), '-filter_complex', graph]
    command += ['-map', '[a]', '-q:v', '3', str(self.samples / 's-%05d.jpg')]
    command += ['-map', '[g]', '-f', 'rawvideo', str(self.samples / 'gray.part')]
    subprocess.run(command, check=True, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (self.samples / 'gray.part').replace(self.samples / 'gray.raw')

  def grays(self):
    data = (self.samples / 'gray.raw').read_bytes()
    size = GRAY[0] * GRAY[1]
    return [data[i : i + size] for i in range(0, len(data) - size + 1, size)]

  def dropped(self):
    """{picture path in the video folder: why}, from every unit's 「## 画面」 lines marked 无用."""
    return json.loads(read(self.dir / 'dropped.json') or '{}')

  def pictures_in(self, start, end):
    """Screen pages in [start, end) and the samples that differ from the picture kept before them: [(second, kind,
    path)]."""
    grays = self.grays()
    near = lambda second: min(len(grays) - 1, max(0, round((second + 2) / STEP_S)))
    pages = {near(p['time_s']): p for p in self.manifest.get('screen_pages') or [] if start <= p['time_s'] < end}
    dropped = self.dropped()
    chosen, last = [], None
    for index in range(max(0, int(start // STEP_S)), min(len(grays), int(-(-end // STEP_S)))):
      sample = self.samples / f's-{index + 1:05d}.jpg'
      path = self.asset / pages[index]['path'] if index in pages else sample
      if posix(path.relative_to(self.asset)) in dropped:
        continue
      if index in pages:
        chosen.append((pages[index]['time_s'], '屏幕页', path))
        last = grays[index]
      elif last is None or sum(1 for p, q in zip(last, grays[index]) if abs(p - q) > 16) / len(last) > CHANGED:
        chosen.append((index * STEP_S, '补帧', sample))
        last = grays[index]
    return chosen

  def label_picture(self, source, target, text):
    """The single picture a writer opens: the original at SCALE times its size, labelled."""
    width, height = media.frame_size(media.probe(source)[1])
    bigger = Path(target).with_suffix('.x2.png')
    bigger.parent.mkdir(parents=True, exist_ok=True)
    graph = f'scale={width * SCALE // 2 * 2}:{height * SCALE // 2 * 2}:flags=lanczos'
    subprocess.run(
      [media.tool('ffmpeg'), '-y', '-v', 'error', '-i', str(source), '-vf', graph, str(bigger)],
      check=True,
      capture_output=True,
      creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    media.label_picture(bigger, target, text)
    bigger.unlink()

  def prepare(self, unit, lines):
    """A unit's folder: its transcript with a margin, its picture list, the labelled pictures and the sheets of four."""
    folder = self.dir / 'units' / unit['id']
    if (folder / 'frames.md').is_file():
      return folder
    folder.mkdir(parents=True, exist_ok=True)
    start, end = unit['start'], unit['end']
    excerpt, began, ended = [], False, False
    for line in lines:
      stamp = re.match(rf'\[{CLOCK}\]', line) or re.search(rf'⟨\S+ (?:A\d+ \S+ )?{CLOCK}', line)
      second = seconds(stamp[1]) if stamp else None
      if second is None or second < start - MARGIN_S or second > end + MARGIN_S:
        continue
      if not began and second >= start:
        excerpt.append(f'—— 本单元从这里开始（`{clock(start)}`）——')
        began = True
      if not ended and second >= end:
        excerpt.append(f'—— 本单元到这里结束（`{clock(end)}`）——')
        ended = True
      excerpt.append(line)
    write(folder / 'excerpt.md', '\n'.join(excerpt) + '\n')
    shown = self.pictures_in(start, end)
    listing, labelled = [], []
    for number, (second, kind, path) in enumerate(shown, 1):
      target = folder / 'labelled' / f'{number:03d}.jpg'
      self.label_picture(path, target, f'#{number} {clock(second)}')
      labelled.append(target)
      listing.append(f'- #{number} `{clock(second)}` {kind} {posix(path.relative_to(self.asset))}')
    sheets = media.sheets(labelled, 2, folder / 'sheets') if labelled else []
    write(folder / 'sheets.txt', '\n'.join(posix(sheet) for sheet in sheets) + '\n')
    write(folder / 'frames.md', '\n'.join(listing or ['（这个单元没有画面）']) + '\n')
    self.say(f'{unit["id"]}：{len(shown)} 张图，{len(sheets)} 张总图')
    return folder

  def paths(self, folder):
    """{number: picture path in the video folder} of a unit's list."""
    found = {}
    for line in (read(folder / 'frames.md') or '').splitlines():
      if match := re.match(r'- #(\d+) `[^`]+` \S+ (\S+)', line):
        found[int(match[1])] = match[2]
    return found

  # ---- the main conversation -----------------------------------------------------------------------------------------

  def main_conversation(self):
    return (self.record['turns'].get('M1') or {}).get('conversation')

  def m1(self):
    """Marks (regular.md) and the units with the draft of the whole (units.md), in one turn on the transcript."""
    prompt = prompts.M1.format(start=clock(0), end=clock(self.length), transcript='\n'.join(self.raw_lines()))
    if found := self.turn('M1', prompt):
      text = found['response']
      pick = lambda names: '\n\n'.join(f'## {n}\n{section(text, n) or "无"}' for n in names) + '\n'
      write(self.dir / 'regular.md', pick(('改正', '锚点', '无内容')))
      write(self.dir / 'units.md', pick(('单元', '事项', '元信息', '主结论', '连接处')))

  def m1_fix(self, problems):
    prompt = prompts.M1FIX.format(problems='\n'.join(f'- {p}' for p in problems))
    if (found := self.turn('M1-fix', prompt, self.main_conversation())) and (
      table := section(found['response'], '单元')
    ):
      write(self.dir / 'units.md', replace_section(read(self.dir / 'units.md'), '单元', table))

  def bounds(self, units, notes):
    """The writers' objections go to the main conversation, which may move unit starts next to them. Only the units
    in `notes` and their neighbours may change (the others are being fixed meanwhile); a table that changes others is
    not taken. A unit whose start or end moved is written again; its old folder and turns are kept as v1."""
    if 'M2-bounds' in self.record['turns'] or not notes:
      return units
    order = [u['id'] for u in units]
    touchable = {
      order[i + d] for i, uid in enumerate(order) if uid in notes for d in (-1, 0, 1) if 0 <= i + d < len(order)
    }
    text = '\n\n'.join(
      f'### {u["title"]}（`{clock(u["start"])}`–`{clock(u["end"])}`）\n{notes[u["id"]]}'
      for u in units
      if u['id'] in notes
    )
    found = self.turn('M2-bounds', prompts.BOUNDS.format(notes=text), self.main_conversation())
    table = section(found['response'], '单元') if found else None
    if not table or not re.search(rf'^\s*-\s*`?{CLOCK}', table, re.MULTILINE):  # 「无」: nothing to change
      return units
    before = read(self.dir / 'units.md')
    write(self.dir / 'units.v1.md', before)
    write(self.dir / 'units.md', replace_section(before, '单元', table))
    new = self.units()
    ranges = {(u['start'], u['end']) for u in new}
    moved = [u for u in units if (u['start'], u['end']) not in ranges]
    problems = unit_problems(new, self.length) + [
      f'{u["title"]} 没有意见却被改了范围' for u in moved if u['id'] not in touchable
    ]
    if problems:
      write(self.dir / 'units.md', before)
      self.say('改过的单元表不用，照旧：' + '；'.join(problems))
      return units
    with LOCK:
      for unit in moved:
        if (self.dir / 'units' / unit['id']).is_dir():
          (self.dir / 'units-v1').mkdir(exist_ok=True)
          (self.dir / 'units' / unit['id']).rename(self.dir / 'units-v1' / unit['id'])
        for key in [k for k in self.record['turns'] if k == f'W-{unit["id"]}' or k.startswith(f'W-{unit["id"]}-')]:
          self.record['turns'][f'v1-{key}'] = self.record['turns'].pop(key)
      kept = {(u['start'], u['end']) for u in units}
      again = [u['id'] for u in new if not u['skip'] and (u['start'], u['end']) not in kept]
      self.record['bounds'] = {'moved': [u['id'] for u in moved], 'written_again': again}
    self.save()
    self.say(f'单元表改了：{len(moved)} 个单元的范围变了，重写 {len(again)} 个')
    return new

  def m3(self, units):
    drafts = self.drafts(units)
    body, _, maps, _ = numbered(units, drafts)
    write(self.dir / 'body.md', body)
    ledger = [re.sub(r'\[[^\]]*\]\([^)]*\)', '', line) for line in body.splitlines() if line.startswith('- **P')]
    reports = []
    for unit, mapping in maps:
      text = drafts[unit['id']]
      found = '\n'.join(f'### {name}\n{section(text, name) or "无"}' for name in ('事项', '预设', '需确认', '要点候选'))
      reports.append(
        f'## {unit["id"]} {unit["title"]}\n'
        + re.sub(r'\bS(\d+)\b', lambda m, mapping=mapping: f'P{mapping.get(m[1], m[1])}', found)
      )
    prompt = prompts.M3.format(ledger='\n'.join(ledger), reports='\n'.join(reports))
    if found := self.turn('M3', prompt, self.main_conversation()):
      write(self.dir / 'global.md', found['response'])

  # ---- a unit --------------------------------------------------------------------------------------------------------

  def drafts(self, units):
    return {u['id']: read(self.dir / 'units' / u['id'] / 'body.md') or '' for u in units}

  def unit_prompt(self, unit, folder):
    listing = []
    for line in read(folder / 'frames.md').splitlines():
      if match := re.match(r'- #(\d+) (`[^`]+`) (\S+) (\S+)', line):
        single = folder / 'labelled' / f'{int(match[1]):03d}.jpg'
        listing.append(f'- #{match[1]} {match[2]} {match[3]} 链接写：{match[4]} 单张图：{posix(single)}')
    return prompts.W.format(
      title=unit['title'],
      start=clock(unit['start']),
      end=clock(unit['end']),
      kind=unit['kind'],
      line=unit['line'],
      gap=GAP_S,
      sheets='、'.join((read(folder / 'sheets.txt') or '').split()) or '（没有）',
      rules=self.unit_rules,
      units=section(read(self.dir / 'units.md'), '单元'),
      frames='\n'.join(listing) or '（这个单元没有画面）',
      excerpt=read(folder / 'excerpt.md'),
    )

  def first(self, unit):
    """The unit's first draft (body.md), unless it is there already."""
    folder = self.dir / 'units' / unit['id']
    if (last := read(folder / 'body.md')) is None and (
      found := self.turn(f'W-{unit["id"]}', self.unit_prompt(unit, folder))
    ):
      last = found['response']
      write(folder / 'body.md', last)
    return last

  def candidates(self, unit, folder):
    """What the program finds but the writer judges: transcript with no proposition time near it, anchors no
    proposition meets, propositions that only name what was shown."""
    body = section(read(folder / 'body.md') or '', '正文') or ''
    times = [seconds(t) for t in re.findall(rf'`{CLOCK}`', body)]
    found = self.regular() or {'anchors': [], 'empty': []}
    empty = [(e['start'], e['end']) for e in found['empty']]
    problems, run = [], []

    def close(run):
      if run and run[-1][0] - run[0][0] >= GAP_S:
        first = run[0][1].split(']', 1)[1].strip()[:40]
        problems.append(
          f'`{clock(run[0][0])}`–`{clock(run[-1][0])}` 这段字幕附近没有命题（开头是「{first}」），看是否漏写'
        )

    for line in self.raw_lines():
      second = seconds(re.match(rf'\[{CLOCK}\]', line)[1])
      if not unit['start'] <= second < unit['end'] or any(a <= second <= b for a, b in empty):
        continue
      if any(t - 10 <= second <= t + GAP_S for t in times):
        close(run)
        run = []
      else:
        run.append((second, line))
    close(run)
    for anchor in found['anchors']:
      if unit['start'] <= anchor['start'] < unit['end'] and not any(
        anchor['start'] - 15 <= t <= anchor['end'] + 15 for t in times
      ):
        problems.append(
          f'锚点 {anchor["id"]} `{clock(anchor["start"])}`–`{clock(anchor["end"])}` {anchor["kind"]}：{anchor["what"]}——没有命题对上'
        )
    for key, block in blocks(body).items():
      if pointer(block.splitlines()[0]):
        problems.append(f'{key} 可能是路标句（只说讲了什么）：{block.splitlines()[0][:80]}')
    return problems

  def body_problems(self, unit, folder, new=()):
    """Errors in the draft the writer fixes: no propositions, times outside the unit, picture numbers with no line in
    「## 画面」 (but `new` ones, just captured, the writer has not seen yet), links to missing files."""
    text = read(folder / 'body.md')
    if not text or not section(text, '正文') or '**S1**' not in text:
      return ['没有「## 正文」或没有 **S1**']
    problems = []
    for match in re.finditer(rf'^- \*\*S(\d+)\*\*[^\n]*?`{CLOCK}`', section(text, '正文'), re.MULTILINE):
      if not unit['start'] - MARGIN_S <= seconds(match[2]) <= unit['end'] + MARGIN_S:
        problems.append(f'S{match[1]} 的时间 {match[2]} 不在本单元 {clock(unit["start"])}–{clock(unit["end"])} 里')
    count = len(re.findall(r'^- #\d+', read(folder / 'frames.md'), re.MULTILINE))
    covered = set()
    for match in re.finditer(r'#(\d+)(?:\s*[–\-~]\s*#?(\d+))?', section(text, '画面') or ''):
      covered |= set(range(int(match[1]), int(match[2] or match[1]) + 1))
    if missing := sorted(set(range(1, count + 1)) - covered - set(new)):
      problems.append('「## 画面」缺这些编号：' + '、'.join(f'#{n}' for n in missing))
    for link in re.findall(r'\]\(<?([^)>]+?\.(?:jpe?g|png))>?\)', text):
      if not (self.asset / link).is_file():
        problems.append(f'链接的图不存在：{link}')
    return problems

  def own_dropped(self, folder):
    """{path: why} of the pictures the unit's own 「## 画面」 marks 无用."""
    paths, found = self.paths(folder), {}
    for line in (section(read(folder / 'body.md') or '', '画面') or '').splitlines():
      if (match := LABEL.match(line)) and (why := re.match(r'无用\s*[:：]?\s*(.*)', line[match.end() :])):
        for number in numbers(line):
          if number in paths:
            found[paths[number]] = why[1].strip()[:80] or '无用'
    return found

  def tidy(self, unit, folder):
    """What the program puts right itself: a link whose file is missing but whose file name is in the unit's list, a
    link to a picture the unit marks 无用; and the pictures marked 无用 noted for later lists."""
    listed = {}
    for number, path in self.paths(folder).items():
      listed[Path(path).name] = path
      listed[f'{number:03d}.jpg'] = path
    text = read(folder / 'body.md') or ''

    def repair(match):
      link = match[2]
      if (self.asset / link).is_file():
        return match[0]
      path = Path(link)
      if path.is_absolute() and path.is_file() and self.asset in path.parents and 'labelled' not in path.parts:
        right = posix(path.relative_to(self.asset))
      else:
        right = listed.get(path.name)
      return f'{match[1]}{right}{match[3]}' if right else match[0]

    fixed = re.sub(r'(\]\(<?)([^)>]+?\.(?:jpe?g|png))(>?\))', repair, text)
    own = self.own_dropped(folder)
    fixed, _ = unlink_dropped(fixed, self.paths(folder), own)
    if fixed != text:
      write(folder / 'body.md', fixed)
    if own:
      with LOCK:
        write(self.dir / 'dropped.json', json.dumps(self.dropped() | own, ensure_ascii=False, indent=1) + '\n')

  def requests(self, unit, folder, text):
    """[(second, what)] to capture: the writer's 「## 补截」, and anchors with no picture near them."""
    done = {round(s) for s in self.record.setdefault('captured', {}).get(unit['id'], [])}
    wanted = []
    for line in items(section(text or '', '补截')):
      if (match := re.match(rf'`?{CLOCK}`?\s*(.*)', line)) and unit['start'] - MARGIN_S <= seconds(match[1]) <= unit[
        'end'
      ] + MARGIN_S:
        wanted.append((seconds(match[1]), match[2].strip(' ：:')))
    times = [seconds(t) for t in re.findall(rf'`{CLOCK}`', read(folder / 'frames.md') or '')]
    for anchor in (self.regular() or {'anchors': []})['anchors']:
      if unit['start'] <= anchor['start'] < unit['end'] and not any(
        anchor['start'] - 5 <= t <= anchor['end'] + 5 for t in times
      ):
        wanted.append(((anchor['start'] + anchor['end']) // 2, f'锚点 {anchor["id"]}：{anchor["what"]}'))
    return [(s, w) for s, w in dict(wanted).items() if s not in done]

  def capture(self, unit, folder, wanted):
    """Captures the screen region at each second, numbers and labels the pictures after the unit's list and puts them
    on sheets; returns the text that tells the writer."""
    x, y, w, h = self.screen()
    lines = (read(folder / 'frames.md') or '').splitlines()
    lines = [line for line in lines if line.startswith('- #')]
    number, labelled, told = len(lines), [], []
    for second, what in sorted(wanted):
      number += 1
      raw = folder / 'captured' / f'c-{clock(second).replace(":", "-")}.jpg'
      media.frame_at(self.video, second, raw, video_filter=f'crop={w}:{h}:{x}:{y}')
      target = folder / 'labelled' / f'{number:03d}.jpg'
      self.label_picture(raw, target, f'#{number} {clock(second)}')
      labelled.append(target)
      lines.append(f'- #{number} `{clock(second)}` 补截 {posix(raw.relative_to(self.asset))}')
      told.append(
        f'- #{number} `{clock(second)}` 补截 链接写：{posix(raw.relative_to(self.asset))} 单张图：{posix(target)}（要看：{what}）'
      )
    write(folder / 'frames.md', '\n'.join(lines) + '\n')
    count = len(list((folder / 'sheets').glob('extra-*')))
    sheets = media.sheets(labelled, 2, folder / 'sheets' / f'extra-{count + 1}')
    with LOCK:
      self.record['captured'].setdefault(unit['id'], []).extend(s for s, _ in wanted)
    self.save()
    self.say(f'{unit["id"]}：补截 {len(wanted)} 张')
    return (
      f'\n\n按你的要求和锚点补截了 {len(wanted)} 张图，拼成了总图：{"、".join(posix(s) for s in sheets)}。'
      '先用 view_file 在同一步里把总图打开；看不清的格子再打开单张图：\n' + '\n'.join(told)
    )

  def zooms(self, unit, text):
    """([(number, region, what)] to enlarge, [numbers asked again]): the writer's 「#n 放大 区域」 requests. Nothing is
    enlarged unasked, and a picture once: the crop is the original pixels, so a second one shows
    nothing more."""
    done = {int(key.split(':')[0]) for key in self.record.setdefault('zoomed', {}).get(unit['id'], [])}
    wanted = []
    for line in items(section(text or '', '补截')):
      if (match := re.match(r'#(\d+)\s*放大\s*(\S{2})\S*\s*[:：]?\s*(.*)', line)) and match[2] in REGIONS:
        wanted.append((int(match[1]), match[2], match[3].strip()))
    return [z for z in wanted if z[0] not in done], sorted({n for n, _, _ in wanted if n in done})

  def zoom(self, unit, folder, wanted):
    """Crops each region from the picture's original file and enlarges it; returns the text that tells the writer."""
    paths, told, size = self.paths(folder), [], ''
    for number, region, what in wanted:
      if number not in paths:
        continue
      source = self.asset / paths[number]
      width, height = media.frame_size(media.probe(source)[1])
      left, top, right, bottom = REGIONS[region]
      # widened a little past the halves, so a line of text cut by the middle shows whole in one of the two pieces
      left, top = max(0, left - OVERLAP), max(0, top - OVERLAP)
      right, bottom = min(1, right + OVERLAP), min(1, bottom + OVERLAP)
      w, h = int(width * (right - left)) // 2 * 2, int(height * (bottom - top)) // 2 * 2
      scale = min(4, 1400 / w)
      target = folder / 'zoomed' / f'{number:03d}-{region}.png'
      target.parent.mkdir(parents=True, exist_ok=True)
      graph = f'crop={w}:{h}:{int(width * left)}:{int(height * top)},scale={int(w * scale) // 2 * 2}:-2:flags=lanczos'
      subprocess.run(
        [media.tool('ffmpeg'), '-y', '-v', 'error', '-i', str(source), '-vf', graph, str(target)],
        check=True,
        capture_output=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
      )
      told.append(f'- #{number} {region}放大：{posix(target)}（要读：{what}）')
      size = f'{width}×{height}'
    with LOCK:
      self.record['zoomed'].setdefault(unit['id'], []).extend(f'{n}:{r}' for n, r, _ in wanted)
    self.save()
    if not told:
      return ''
    self.say(f'{unit["id"]}：放大 {len(told)} 块')
    return (
      f'\n\n放大了 {len(told)} 块区域：从原图（{size} 像素）按原始像素截出再放大，不拼总图；放大不会多出原图没有的细节，'
      '每张图只放大这一次。先用 view_file 在同一步里把它们全部打开，对照核对你转写过的代码、公式、表格：\n'
      + '\n'.join(told)
    )

  def fix(self, unit, folder, key, problems, pictures=''):
    """One fix turn in the unit's conversation: the problems and new pictures go in, the reply is merged."""
    number = len(list(folder.glob('body.v*.md'))) + 1
    shutil.copy(folder / 'body.md', folder / f'body.v{number}.md')
    told = ''
    if problems:
      told = '\n\n查出下面这些地方。逐条看：确实有问题的改；查错了的（例如那段字幕确实没有内容）不改，在「## 不改」里说明。\n'
      told += '\n'.join(f'- {p}' for p in problems)
    conversation = self.record['turns'][f'W-{unit["id"]}']['conversation']
    found = self.turn(key, prompts.FIX.format(pictures=pictures, problems=told), conversation)
    if found is None or not re.search(r'^##\s', found['response'], re.MULTILINE):  # stopped or empty: ask once more
      again = self.turn(f'{key}-again', prompts.AGAIN, conversation)
      found = again if again and re.search(r'^##\s', again['response'], re.MULTILINE) else None
    if found and unreadable(found['response']):
      self.say(f'{key} 的正文格式读不进来，要它照格式重写')
      if (again := self.turn(f'{key}-format', prompts.REFORMAT, conversation)) and not unreadable(again['response']):
        found = again
    if found:
      write(folder / f'fix-{number}.md', found['response'])
      text, changed = merge(read(folder / 'body.md'), found['response'])
      write(folder / 'body.md', text)
      with LOCK:
        self.record.setdefault('fixes', {})[key] = {
          'problems': len(problems),
          'pictures': pictures.count('\n- #'),
          'changed': changed,
        }
      self.save()
    return found

  def write_unit(self, unit):
    """The first draft and up to MAX_FIXES fix turns, each for what the checks find and the pictures asked for."""
    folder = self.dir / 'units' / unit['id']
    key = f'W-{unit["id"]}'
    if (last := self.first(unit)) is None:
      return
    for round_ in range(1, MAX_FIXES + 1):
      name = f'{key}-fix{round_}'
      if name in self.record['turns']:
        last = read(folder / f'fix-{round_}.md') or last
        continue
      self.tidy(unit, folder)
      wanted = self.requests(unit, folder, last)
      enlarge, again = self.zooms(unit, last)
      before = len(self.paths(folder))
      pictures = self.capture(unit, folder, wanted) if wanted else ''
      pictures += self.zoom(unit, folder, enlarge) if enlarge else ''
      new = set(range(before + 1, before + len(wanted) + 1))
      raised = self.record.setdefault('raised', {}).setdefault(unit['id'], [])
      fresh = [
        c for c in self.candidates(unit, folder) if c not in raised
      ]  # one answered in 「## 不改」 is not raised again
      raised += fresh
      problems = self.body_problems(unit, folder, new) + fresh
      problems += [
        f'#{n} 已经按原始像素放大过一次，不再放大（原片分辨率是上限）：不能逐字确认的字符删掉，只写结构和大意，标「看不清（原片分辨率不够）」'
        for n in again
      ]
      with LOCK:
        self.record.setdefault('checks', {})[f'{key}-{round_}'] = {
          'problems': problems,
          'captures': len(wanted),
          'zooms': len(enlarge),
        }
      self.save()
      if not problems and not pictures:
        break
      if not (found := self.fix(unit, folder, name, problems, pictures)):
        break
      last = found['response']
    self.tidy(unit, folder)
    if left := self.body_problems(unit, folder) + self.candidates(unit, folder):
      self.say(f'{unit["id"]} 剩下 {len(left)} 处：' + '；'.join(left)[:400])

  def mark(self, unit):
    """Marks the formulas read off pictures and not checked on an enlarged crop."""
    folder = self.dir / 'units' / unit['id']
    text = read(folder / 'body.md') or ''
    zoomed = {int(z.split(':')[0]) for z in self.record.get('zoomed', {}).get(unit['id'], [])}
    checked = set()
    for line in (section(text, '画面') or '').splitlines():
      if numbers(line) & zoomed:
        checked |= set(re.findall(r'`([^`]+)`', line))
    text, marked = mark_unchecked(text, checked)
    if marked:
      write(folder / 'body.md', text)

  # ---- the loop ------------------------------------------------------------------------------------------------------

  def go(self, parallel=0, overwrite=False):
    """Does what is left and saves the summary. Returns the path written."""
    if not self.raw_lines():
      raise StagedError('这个视频没有字幕，写不了总结')
    self.take_samples()
    if self.regular() is None or self.units() is None:
      self.m1()
    if self.regular() is None or self.units() is None:
      raise StagedError('主对话第一轮没有交出标记和单元表')
    lines = self.transcript()
    if (problems := unit_problems(self.units(), self.length)) and 'M1-fix' not in self.record['turns']:
      self.m1_fix(problems)
    units = self.units()
    if problems := unit_problems(units, self.length):
      raise StagedError('单元表不对：' + '；'.join(problems))
    writing = [u for u in units if not u['skip']]
    self.say(f'{len(units)} 个单元，要写 {len(writing)} 个')
    for unit in writing:
      self.prepare(unit, lines)
    with ThreadPoolExecutor(
      max_workers=parallel or 2 * len(writing) or 1
    ) as pool:  # units are independent: all at once
      list(pool.map(self.first, writing))
      # The units no objection can touch go on to their fix rounds while the main conversation weighs the objections;
      # the others wait for its table, so a unit written again has not been fixed for nothing.
      notes = objections({u['id']: read(self.dir / 'units' / u['id'] / 'body.md') for u in writing})
      order = [u['id'] for u in units]
      waiting = {
        order[i + d] for i, uid in enumerate(order) if uid in notes for d in (-1, 0, 1) if 0 <= i + d < len(order)
      }
      if 'M2-bounds' in self.record['turns']:
        waiting = set()
      going = [pool.submit(self.write_unit, u) for u in writing if u['id'] not in waiting]
      units = self.bounds(units, notes)
      writing = [u for u in units if not u['skip']]
      for unit in (fresh := [u for u in writing if u['id'] in waiting or u['id'] not in order]):
        self.prepare(unit, lines)
      going += [pool.submit(self.write_unit, u) for u in fresh]
      for future in going:
        future.result()
      drafts = self.drafts(writing)
      repeated = {
        u: p
        for u, p in duplicates([(u['id'], drafts[u['id']]) for u in writing]).items()
        if f'W-{u}-dup' not in self.record['turns']
      }
      by_id = {u['id']: u for u in writing}
      list(
        pool.map(
          lambda item: self.fix(by_id[item[0]], self.dir / 'units' / item[0], f'W-{item[0]}-dup', item[1]),
          repeated.items(),
        )
      )
    missing = [u['id'] for u in writing if not (self.dir / 'units' / u['id'] / 'body.md').is_file()]
    if missing:
      raise StagedError(f'{len(missing)} 个单元没有写成（{"、".join(missing)}）；再运行同一条命令接着写')
    for unit in writing:
      self.mark(unit)
    if not (self.dir / 'global.md').is_file():
      self.m3(units)
    if not (self.dir / 'global.md').is_file():
      raise StagedError('主对话最后一轮没有交出全局部分；再运行同一条命令接着写')
    head = f'# {evidence.video_name(self.video)}\n\n{evidence.video_line(self.video, self.length)}'
    text = assemble(units, self.drafts(units), read(self.dir / 'global.md'), head)
    write(self.dir / 'summary.md', text)
    total = self.total()
    model = self.record['model'] + (
      f'，修改轮 {self.record["fix_model"]}' if self.record['fix_model'] != self.record['model'] else ''
    )
    target, _ = importer.import_summary(
      self.video,
      self.workspace,
      text,
      overwrite=overwrite,
      source=f'{self.channel.NAME} 分阶段',
      note=f'{model}；{usage_text(total)}',
      template=templates.STANDARD,
      usage=total,
      status=self.say,
    )
    write(self.dir / 'imported', datetime.now().isoformat(timespec='seconds') + '\n')
    self.say(f'完成：{target}；{usage_text(total)}')
    return target


def summarize(video, workspace, *, model=None, fix_model=None, restart=False, overwrite=False, status=print):
  """`summarize --staged`: goes on with the video's unfinished staged run, or starts one; returns the path written."""
  staged_agy.prepare(evidence.processed(video, workspace)[2])
  return Run(video, workspace, model=model, fix_model=fix_model, restart=restart, status=status).go(overwrite=overwrite)
