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
"""

import difflib
import json
import re
from pathlib import Path
from urllib.parse import unquote

from . import files, picture_review, transcript
from .evidence import clock

HEADING = '复查'
SECTION = re.compile(rf'^##\s*{HEADING}\s*\n(.*?)(?=^##\s|\Z)', re.MULTILINE | re.DOTALL)
CLOCK = r'(?:\d{1,2}:)?\d{1,2}:\d{2}'
ENTRY = re.compile(r'^\s*[-*]?\s*(补上|改正|删掉的节|不写的时间段|画面)\s*[:：]\s*(.+)$')
SPAN = re.compile(rf'`?({CLOCK})`?\s*[-–—~～至到]+\s*`?({CLOCK})`?')
# A part of the detailed notes with its time range in its heading, as the templates write it: ### 标题 `00:12:30`–`00:25:10`
RANGE = re.compile(rf'^#{{2,4}}\s.*?`({CLOCK})`\s*[-–—~～至到]+\s*`({CLOCK})`', re.MULTILINE)
TIME = re.compile(rf'`({CLOCK})`')
LINK = re.compile(r'[ \t]?\[[^\]\n]*\]\(<?(frames/[^)>\n]+)>?\)')
NOTHING = re.compile(r'^(?:无|没有)?(?=$|[\s（(，,。:：；;—-])')  # 「无」, alone or with a note on why
TEMPLATE_HEADING = re.compile(r'^##\s+(.+?)\s*$', re.MULTILINE)
NAME = 'summary-review.json'


def seconds(value):
  return sum(int(part) * 60**place for place, part in enumerate(reversed(value.split(':'))))


def take(text):
  """(summary without the 复查 section, what it lists) — None for an answer without one, a first draft. The lists:
  `added` and `fixed` as written, `dropped` (sections left out on purpose, as written), `skipped` ([start, end]
  spans left out on purpose) and `pictures` ({path: what it shows beyond the transcript, '' for nothing})."""
  found = SECTION.search(text)
  if not found:
    return text, None
  review = {'added': [], 'fixed': [], 'dropped': [], 'skipped': [], 'pictures': {}}
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
  if review is not None:
    linked = {unquote(match[1]) for match in LINK.finditer(text)}
    silent = sorted(linked - set(review.get('pictures', {})))
    if silent:
      problems.append(
        f'这些链接的图没有在「{HEADING}」里写图上有、字幕里没有的是什么：' + '、'.join(silent) + '。每张写一行'
        '「画面：<路径> <图上有、字幕里没有的内容>」；写不出来就写「无」，程序会去掉这个链接。'
      )
  return problems


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


def record(asset, draft, review, problems, status=lambda message: None, before=None):
  """Saves what the next round needs and says it; returns whether there is one, pictures aside: after a first draft,
  after a 复查 that added or corrected something in a draft that differs from the one `before`, and while a check
  finds something."""
  text = Path(draft).read_text(encoding='utf-8')
  lines = changed(before, text) if before is not None else None
  if review is not None:
    said = f'{HEADING}：补上 {len(review["added"])} 处，改正 {len(review["fixed"])} 处'
    if lines == 0:
      said += '，但稿子和上一稿一样'
    elif lines is not None:
      said += f'，稿子和上一稿相比改了 {lines} 行'
    status(said)
  for problem in problems:
    status(f'检查：{problem}')
  again = review is None or bool(problems) or (bool(review['added'] or review['fixed']) and lines != 0)
  state = {'draft': Path(draft).name, 'first': review is None, 'problems': problems, 'review': review, 'again': again}
  files.write_text(Path(asset) / NAME, json.dumps(state, ensure_ascii=False, indent=2) + '\n')
  return again
