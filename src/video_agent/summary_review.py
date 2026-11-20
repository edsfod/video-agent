"""Rounds of a chat AI's summary until it holds everything the video says (user request, 2026-10-30: answers that did
not follow the template ended the rounds after one or two, errors and all, and were thin). Every answer imported from a
chat AI is checked for what a program can see: the template's sections, the 画面调整 section, the stretches of speech the
detailed part leaves out, times past the end. A first draft always goes to one round of 复查, in which the chat AI
goes through the transcript again against its draft and says in a 复查 section what it added and corrected; the rounds
go on while a 复查 adds or corrects anything, a check finds something or pictures are wanted (`pack --follow-up`).
How detailed a summary is depends on whether every point, reason, example, number, definition, condition and conclusion
said is in it, not on its length (user decision): only the chat AI, reading the transcript, can judge that, so its
复查 says what it found. Likewise for pictures (user decision, 2026-10-30: title cards repeating what was said, the
speaker and stock footage linked although the rules said not to): the 复查 says for each linked picture what it shows
that the transcript does not; a link for which it says nothing is taken out, and a picture linked without a word on it
is named in the next round. Whether a round changed anything is read from the drafts themselves, not from its 复查
(user report, 2026-10-30: six rounds did not end; the fourth 复查 was the third's word for word, and the sixth listed
two corrections in a draft equal to the fifth). The state between rounds is in summary-review.json in the video's
folder.

What is worth writing is the summary's judgement, not every minute (user decision, 2026-11-16: requiring every stretch
made summaries long-winded): a stretch of speech no part covers is named only when it is long (GAP_S), and only once;
left out again, it stays out. What the checks do insist on is that 要点 leaves nothing important out: a part of the
detailed notes with no line in 要点 is named, unless the 复查 says why it has none; and a proposition whose time lies
outside its part's range is named (the first NJU lecture put 01:21:20 in a part of 01:24:19–01:39:59).
"""

import difflib
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

from . import files, forest, picture_review, transcript
from .evidence import clock

HEADING = '复查'
SECTION = re.compile(rf'^##\s*{HEADING}\s*\n(.*?)(?=^##\s|\Z)', re.MULTILINE | re.DOTALL)
CLOCK = r'(?:\d{1,2}:)?\d{1,2}:\d{2}'
ENTRY = re.compile(r'^\s*[-*]?\s*(补上|改正|删去|删掉的节|不写的时间段|要点不收|画面)\s*[:：]\s*(.+)$')
SPAN = re.compile(rf'`?({CLOCK})`?\s*[-–—~～至到]+\s*`?({CLOCK})`?')
# A part of the detailed notes with its time range in its heading, as the templates write it: ### 标题 `00:12:30`–`00:25:10`
RANGE = re.compile(rf'^#{{2,4}}\s.*?`({CLOCK})`\s*[-–—~～至到]+\s*`({CLOCK})`', re.MULTILINE)
TIME = re.compile(rf'`({CLOCK})`')
PART = re.compile(rf'^(#{{2,4}})\s+(.*?)`({CLOCK})`\s*[-–—~～至到]+\s*`({CLOCK})`.*$', re.MULTILINE)
NUMBER = re.compile(r'\*\*P(\d+)\*\*|(?<![A-Za-z0-9])P(\d+)(?![0-9])')
PROPOSITION = re.compile(rf'^\s*[-*]\s*\*\*P\d+\*\*[^`\n]*(?:`[^`\n]*`[^`\n]*)*?`({CLOCK})`', re.MULTILINE)
# A stretch of speech in no part is named when at least this long (Claude judgment: about a slide's worth of talk);
# shorter ones are the summary's to leave out.
GAP_S = 120
# A proposition this far outside its part's range is in the wrong part (times are written to the second, and a point
# may be said a little before the part it belongs to begins).
OUTSIDE_S = 60
LINK = re.compile(r'[ \t]?\[[^\]\n]*\]\(<?(' + picture_review.FOLDERS + r'[^)>\n]+)>?\)')
NOTHING = re.compile(r'^(?:无|没有)?(?=$|[\s（(，,。:：；;—-])')  # 「无」, alone or with a note on why
TEMPLATE_HEADING = re.compile(r'^##\s+(.+?)\s*$', re.MULTILINE)
NAME = 'summary-review.json'


def seconds(value):
  return sum(int(part) * 60**place for place, part in enumerate(reversed(value.split(':'))))


def take(text):
  """(summary without the 复查 section, what it lists) — None for an answer without one, a first draft. The lists:
  `added`, `fixed` and `removed` as written, `dropped` (sections left out on purpose, as written), `skipped` ([start,
  end] spans left out on purpose), `unlisted` (parts with nothing for 要点, as written) and `pictures` ({path: what it
  shows beyond the transcript, '' for nothing})."""
  found = SECTION.search(text)
  if not found:
    return text, None
  review = {'added': [], 'fixed': [], 'removed': [], 'dropped': [], 'skipped': [], 'unlisted': [], 'pictures': {}}
  for line in found[1].splitlines():
    if not (match := ENTRY.match(line)) or match[2].strip().strip('`。') in ('无', '没有'):
      continue
    kind, what = match[1], match[2].strip()
    if kind == '画面':
      for path in picture_review.PATH.findall(unquote(what)):
        beyond = picture_review.PATH.sub('', unquote(what)).strip(' \t`。，,：:—-（）()「」')
        review['pictures'][path] = '' if NOTHING.match(beyond) else beyond
    elif kind == '补上':
      review['added'].append(what)
    elif kind == '改正':
      review['fixed'].append(what)
    elif kind == '删去':
      review['removed'].append(what)
    elif kind == '要点不收':
      review['unlisted'].append(what)
    elif kind == '删掉的节':
      review['dropped'].append(what)
    elif span := SPAN.search(what):
      review['skipped'].append([seconds(span[1]), seconds(span[2])])
  return (text[: found.start()] + text[found.end() :]).rstrip() + '\n', review


def drop_links(text, review):
  """(text without the links to pictures the 复查 says show nothing beyond the transcript, their paths)."""
  empty = {path for path, beyond in (review or {}).get('pictures', {}).items() if not beyond}
  if not empty:
    return text, []
  dropped = sorted({unquote(match[1]) for match in LINK.finditer(text) if unquote(match[1]) in empty})
  return LINK.sub(lambda match: '' if unquote(match[1]) in empty else match[0], text), dropped


def sections(template_text):
  """The `##` sections of a template's video summary (the first ```markdown block after its 视频总结 heading), without
  those that name a placeholder such as `## <主题>`."""
  start = template_text.find('视频总结')
  block = re.search(r'^```markdown\n(.*?)^```', template_text[max(start, 0) :], re.MULTILINE | re.DOTALL)
  if not block:
    return []
  return [name for name in TEMPLATE_HEADING.findall(block[1]) if '<' not in name]


def _speech(asset):
  for name in ('transcript.clean.srt', 'transcript.srt'):
    path = Path(asset) / name
    if path.is_file():
      return transcript.parse(path.read_text(encoding='utf-8'))
  return []


def _uncovered(cues, covered):
  """Spans of consecutive subtitle lines whose middle is in no covered range (a second of slack either side, as the
  ranges are written to the second)."""
  spans, open_span = [], False
  for start, end, _ in cues:
    middle = (start + end) / 2
    if any(low - 1 <= middle <= high + 1 for low, high in covered):
      open_span = False
    elif open_span:
      spans[-1][1] = end
    else:
      spans.append([start, end])
      open_span = True
  return spans


def _section(text, name):
  """The body of the `## <name>` section, '' when there is none."""
  found = re.search(rf'^##\s*{re.escape(name)}\s*\n(.*?)(?=^##\s|\Z)', text, re.MULTILINE | re.DOTALL)
  return found[1] if found else ''


def _parts(text):
  """The parts of 详细内容 with a time range in their heading: (title, start, end, body)."""
  body = _section(text, '详细内容')
  found = list(PART.finditer(body))
  return [
    (
      match[2].strip(),
      seconds(match[3]),
      seconds(match[4]),
      body[match.end() : found[i + 1].start() if i + 1 < len(found) else len(body)],
    )
    for i, match in enumerate(found)
  ]


def unlisted_parts(text, unlisted=()):
  """Titles of the parts of 详细内容 that nothing in 要点 points to (by a time within the part or one of its
  proposition numbers), leaving out those the 复查 names as having nothing for 要点."""
  points = _section(text, '要点')
  if not points.strip():
    return []
  times = [seconds(value) for value in TIME.findall(points)]
  numbers = {first or second for first, second in NUMBER.findall(points)}
  excused = ' '.join(unlisted)
  missing = []
  for title, start, end, body in _parts(text):
    own = {first or second for first, second in NUMBER.findall(body)}
    if any(start - 1 <= value <= end + 1 for value in times) or own & numbers or (title and title in excused):
      continue
    missing.append(title or f'{clock(start)}–{clock(end)}')
  return missing


def misplaced(text):
  """Propositions whose time lies well outside the range of the part they are written in, as `P<n> <time>（<part>）`."""
  found = []
  for title, start, end, body in _parts(text):
    for match in PROPOSITION.finditer(body):
      value = seconds(match[1])
      if value < start - OUTSIDE_S or value > end + OUTSIDE_S:
        number = NUMBER.search(match[0])
        found.append(f'P{number[1] or number[2]} `{match[1]}`（{title or clock(start)}，{clock(start)}–{clock(end)}）')
  return found


def check(text, asset, template_text, length, *, pictures, review, asked=(), agent=False):
  """What a program can see missing in a chat AI's summary, as lines to send back to it. `asked`: the stretches of
  speech named in rounds before, not named again. With `agent`, worded for an Agent, which writes no 复查."""
  problems = []
  excuse = '确实没有就不用管' if agent else None
  present = set(TEMPLATE_HEADING.findall(text))
  dropped = ' '.join(review['dropped']) if review else ''
  generated = {forest.HEADING} if forest.wanted(template_text) else set()  # written by the program, gone when empty
  missing = [name for name in sections(template_text) if name not in present | generated and name not in dropped]
  if missing:
    listed = '、'.join(f'「{name}」' for name in missing)
    problems.append(
      f'模板里的{listed}没有写：有内容就补上；'
      + (f'{excuse}。' if agent else f'确实没有内容，在「{HEADING}」里写「删掉的节：<节名>（为什么没有）」。')
    )
  if not pictures:
    problems.append('没有「画面调整」一节：没有要调整的画面也要写这一节，内容写「无」。')
  late = sorted({value for value in TIME.findall(text) if length and seconds(value) > length + 1}, key=seconds)
  if late:
    problems.append(f'这些时间点超过了视频的长度 {clock(length)}，核对后改正：' + '、'.join(late) + '。')
  ranges = [(seconds(start), seconds(end)) for start, end in RANGE.findall(text)]
  if ranges:
    skipped = [tuple(span) for span in review['skipped']] if review else []
    gaps = [span for span in gaps_in(text, asset, skipped) if not any(_overlaps(span, other) for other in asked)]
    if gaps:
      listed = '、'.join(f'{clock(start)}–{clock(end)}' for start, end in gaps)
      problems.append(
        f'字幕里这些较长的时间段有讲话，详细内容的各段都没有覆盖：{listed}。看一下有没有值得记的内容，有就补上；没有就'
        f'不用写，也不用说明（这些时间段只提醒这一次）。'
      )
  if '要点' in sections(template_text):
    missing = unlisted_parts(text, review['unlisted'] if review else ())
    if missing:
      listed = '、'.join(f'「{title}」' for title in missing)
      problems.append(
        f'详细内容里这些段落在「要点」里一条都没有：{listed}。有读者不能漏掉的内容（结论和视频展开的想法、讲者花了'
        f'时间的演示或例子、讲者强调的内容）就按时间顺序补进要点；'
        + (f'{excuse}。' if agent else f'确实没有，在「{HEADING}」里写「要点不收：<段落标题>（为什么）」。')
      )
  if forest.wanted(template_text):
    problems += forest.build(text)[1]
  wrong = misplaced(text)
  if wrong:
    problems.append(
      '这些命题的时间点不在所在段落的时间范围里，放到对应的段落，或者改正时间点：' + '、'.join(wrong) + '。'
    )
  if review is not None:
    linked = {unquote(match[1]) for match in LINK.finditer(text)}
    silent = sorted(linked - set(review.get('pictures', {})))
    if silent:
      problems.append(
        f'这些链接的图没有在「{HEADING}」里写图上有、字幕里没有的是什么：' + '、'.join(silent) + '。每张写一行'
        '「画面：<路径> <图上有、字幕里没有的内容>」；写不出来就写「无」，程序会去掉这个链接。'
      )
  return problems


def gaps_in(text, asset, skipped=()):
  """Stretches of speech of at least GAP_S that no part of 详细内容 covers, as [start, end]."""
  ranges = [(seconds(start), seconds(end)) for start, end in RANGE.findall(text)]
  if not ranges:
    return []
  return [span for span in _uncovered(_speech(asset), ranges + list(skipped)) if span[1] - span[0] >= GAP_S]


def _overlaps(one, other):
  return one[0] < other[1] and other[0] < one[1]


def load(asset):
  try:
    return json.loads((Path(asset) / NAME).read_text(encoding='utf-8'))
  except (OSError, ValueError):
    return {}


def changed(before, after):
  """How many lines of a summary differ from the draft before, blank lines and spaces aside."""
  lines = [[re.sub(r'\s+', '', line) for line in text.splitlines() if line.strip()] for text in (before, after)]
  blocks = difflib.SequenceMatcher(None, *lines, autojunk=False).get_opcodes()
  return sum(max(end - start, last - first) for kind, start, end, first, last in blocks if kind != 'equal')


def record(asset, draft, review, problems, status=lambda message: None, before=None, asked=()):
  """Saves what the next round needs and says it; returns whether there is one, pictures aside: after a first draft,
  after a 复查 that added or corrected something in a draft that differs from the one `before`, and while a check
  finds something."""
  text = Path(draft).read_text(encoding='utf-8')
  lines = changed(before, text) if before is not None else None
  if review is not None:
    said = f'{HEADING}：补上 {len(review["added"])} 处，改正 {len(review["fixed"])} 处'
    if review['removed']:
      said += f'，删去 {len(review["removed"])} 处'
    if lines == 0:
      said += '，但稿子和上一稿一样'
    elif lines is not None:
      said += f'，稿子和上一稿相比改了 {lines} 行'
    status(said)
  for problem in problems:
    status(f'检查：{problem}')
  again = (
    review is None or bool(problems) or (bool(review['added'] or review['fixed'] or review['removed']) and lines != 0)
  )
  state = {'draft': Path(draft).name, 'first': review is None, 'problems': problems, 'review': review, 'again': again}
  state['asked'] = [list(span) for span in asked] + [span for span in gaps_in(text, asset) if list(span) not in asked]
  files.write_text(Path(asset) / NAME, json.dumps(state, ensure_ascii=False, indent=2) + '\n')
  return again


def digest(text):
  return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def save_state(asset, state):
  files.write_text(Path(asset) / NAME, json.dumps(state, ensure_ascii=False, indent=2) + '\n')


def update(asset, **keys):
  """Adds to the state between rounds what the import knows besides the checks (the round, the template, the draft's
  digest, whether another round is due)."""
  state = load(asset)
  if state:
    files.write_text(Path(asset) / NAME, json.dumps(state | keys, ensure_ascii=False, indent=2) + '\n')


def renamed(asset, names):
  """Follows the draft to its new file name after `versions --use` swapped the current text and a version."""
  state = load(asset)
  if state.get('draft') in names:
    update(asset, draft=names[state['draft']])


def own_draft(asset, state, template):
  """The draft a later round may write over: the one the rounds wrote last, still as they wrote it (not edited by hand
  since) and written to the same template. None otherwise."""
  name = state.get('draft')
  draft = Path(asset) / name if name else None
  if not draft or not draft.is_file():
    return None
  if state.get('digest') and state['digest'] != digest(draft.read_text(encoding='utf-8')):
    return None
  if state.get('template') and template and state['template'] != template:
    return None
  return draft


def unfinished(asset, template):
  """The round an unfinished run of rounds stopped at (lost network, rate limit, stopped by hand), for a new run to go
  on from in a new conversation; None when there is none to go on with: the last run converged, its draft was changed
  or removed, or it was written to another template."""
  state = load(asset)
  if not state.get('more') or not state.get('round') or own_draft(asset, state, template) is None:
    return None
  return state['round']
