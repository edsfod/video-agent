"""Rounds of a chat AI's summary until it holds everything the video says (user request, 2026-10-30: answers that did
not follow the template ended the rounds after one or two, errors and all, and were thin). Every answer imported from a
chat AI is checked for what a program can see: the template's sections, the 画面调整 section, the stretches of speech the
detailed part leaves out, times past the end. A first draft always goes to one round of 复查, in which the chat AI
goes through the transcript again against its draft and says in a 复查 section what it added and corrected; the rounds
go on while a 复查 adds or corrects anything, a check finds something or pictures are wanted (`pack --follow-up`).
How detailed a summary is depends on whether every point, reason, example, number, definition, condition and conclusion
said is in it, not on its length (user decision): only the chat AI, reading the transcript, can judge that, so its
复查 says what it found. The state between rounds is in summary-review.json in the video's folder.
"""

import json
import re
from pathlib import Path

from . import files, transcript
from .evidence import clock

HEADING = '复查'
SECTION = re.compile(rf'^##\s*{HEADING}\s*\n(.*?)(?=^##\s|\Z)', re.MULTILINE | re.DOTALL)
CLOCK = r'(?:\d{1,2}:)?\d{1,2}:\d{2}'
ENTRY = re.compile(r'^\s*[-*]?\s*(补上|改正|删掉的节|不写的时间段)\s*[:：]\s*(.+)$')
SPAN = re.compile(rf'`?({CLOCK})`?\s*[-–—~～至到]+\s*`?({CLOCK})`?')
# A part of the detailed notes with its time range in its heading, as the templates write it: ### 标题 `00:12:30`–`00:25:10`
RANGE = re.compile(rf'^#{{2,4}}\s.*?`({CLOCK})`\s*[-–—~～至到]+\s*`({CLOCK})`', re.MULTILINE)
TIME = re.compile(rf'`({CLOCK})`')
TEMPLATE_HEADING = re.compile(r'^##\s+(.+?)\s*$', re.MULTILINE)
NAME = 'summary-review.json'


def seconds(value):
  return sum(int(part) * 60**place for place, part in enumerate(reversed(value.split(':'))))


def take(text):
  """(summary without the 复查 section, what it lists) — None for an answer without one, a first draft. The lists:
  `added` and `fixed` as written, `dropped` (sections left out on purpose, as written) and `skipped` ([start, end]
  spans left out on purpose)."""
  found = SECTION.search(text)
  if not found:
    return text, None
  review = {'added': [], 'fixed': [], 'dropped': [], 'skipped': []}
  for line in found[1].splitlines():
    if not (match := ENTRY.match(line)) or match[2].strip().strip('`。') in ('无', '没有'):
      continue
    kind, what = match[1], match[2].strip()
    if kind == '补上':
      review['added'].append(what)
    elif kind == '改正':
      review['fixed'].append(what)
    elif kind == '删掉的节':
      review['dropped'].append(what)
    elif span := SPAN.search(what):
      review['skipped'].append([seconds(span[1]), seconds(span[2])])
  return (text[: found.start()] + text[found.end() :]).rstrip() + '\n', review


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


def check(text, asset, template_text, length, *, pictures, review):
  """What a program can see missing in a chat AI's summary, as lines to send back to it."""
  problems = []
  present = set(TEMPLATE_HEADING.findall(text))
  dropped = ' '.join(review['dropped']) if review else ''
  missing = [name for name in sections(template_text) if name not in present and name not in dropped]
  if missing:
    listed = '、'.join(f'「{name}」' for name in missing)
    problems.append(
      f'模板里的{listed}没有写：有内容就补上；确实没有内容，在「{HEADING}」里写「删掉的节：<节名>（为什么没有）」。'
    )
  if not pictures:
    problems.append('没有「画面调整」一节：没有要调整的画面也要写这一节，内容写「无」。')
  late = sorted({value for value in TIME.findall(text) if length and seconds(value) > length + 1}, key=seconds)
  if late:
    problems.append(f'这些时间点超过了视频的长度 {clock(length)}，核对后改正：' + '、'.join(late) + '。')
  ranges = [(seconds(start), seconds(end)) for start, end in RANGE.findall(text)]
  if ranges:
    skipped = [tuple(span) for span in review['skipped']] if review else []
    gaps = _uncovered(_speech(asset), ranges + skipped)
    if gaps:
      listed = '、'.join(f'{clock(start)}–{clock(end)}' for start, end in gaps)
      problems.append(
        f'字幕里这些时间段有讲话，详细内容的各段都没有覆盖：{listed}。补上这些时间讲的内容；确实不用写的（课间、闲聊、和'
        f'主题无关），在「{HEADING}」里写「不写的时间段：<开始>–<结束>（为什么）」。'
      )
  return problems


def load(asset):
  try:
    return json.loads((Path(asset) / NAME).read_text(encoding='utf-8'))
  except (OSError, ValueError):
    return {}


def record(asset, draft, review, problems, status=lambda message: None):
  """Saves what the next round needs and says it; returns whether there is one, pictures aside: after a first draft,
  after a 复查 that added or corrected something, and while a check finds something."""
  if review is not None:
    status(f'{HEADING}：补上 {len(review["added"])} 处，改正 {len(review["fixed"])} 处')
  for problem in problems:
    status(f'检查：{problem}')
  again = review is None or bool(review['added'] or review['fixed'] or problems)
  state = {'draft': Path(draft).name, 'first': review is None, 'problems': problems, 'review': review, 'again': again}
  files.write_text(Path(asset) / NAME, json.dumps(state, ensure_ascii=False, indent=2) + '\n')
  return again
