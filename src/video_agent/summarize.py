"""Write 总结.md from a processed video's evidence with a model API; the Agent skill is the other route.

The model sees the transcript, every screen page and the representative frames, within an image budget: pages go one
per image, or several on a contact sheet when there are too many. Where the provider supports tool calling it can ask
for more frames: the `frame` tool saves one into `frames/extra/` and sends the image back, up to a limit.
"""

import base64
import hashlib
import json
import math
import re
import shutil
import tempfile
import zipfile
from importlib import resources
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from . import files, media, processor, settings, versions
from .processor import asset_folder

SUMMARY_NAME = '总结.md'
FRAME_TOOL = {
  'name': 'frame',
  'description': (
    'Save the video frame at a given time and look at it. Use it where the speaker points at the screen or the '
    'transcript is unclear and no frame you have is near. Returns the image and its relative path for linking.'
  ),
  'schema': {
    'type': 'object',
    'properties': {'time': {'type': 'string', 'description': 'Time in the video as HH:MM:SS, MM:SS or seconds'}},
    'required': ['time'],
  },
}
EXTRA_NAME = re.compile(r'frame-(\d{2})-(\d{2})-(\d{2})\.jpg$')


class SummaryError(RuntimeError):
  pass


def default_template():
  return resources.files('video_agent').joinpath('prompts/summary.md').read_text(encoding='utf-8')


# The user's own copy of the rules and template, used by every route instead of the default. Its first line records
# which default it was copied from, so an update that changes the default can say so; updates never touch the copy.
BASE_MARK = re.compile(r'<!-- video-agent default: (\w+) -->\n?')


def template_path():
  return settings.settings_path().parent / 'summary.md'


def _fingerprint(text):
  return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


def template():
  """The rules and template every route follows: the user's copy when there is one, otherwise the default."""
  path = template_path()
  if path.is_file():
    return BASE_MARK.sub('', path.read_text(encoding='utf-8-sig'), count=1)
  return default_template()


def template_info():
  """Where the user's copy is, whether there is one, and whether the default changed since it was copied. With a copy,
  the current default is written beside it (summary.default.md) for comparing."""
  path = template_path()
  info = {'path': str(path), 'customized': path.is_file(), 'outdated': False, 'default': None}
  if info['customized']:
    found = BASE_MARK.match(path.read_text(encoding='utf-8-sig'))
    info['outdated'] = not found or found.group(1) != _fingerprint(default_template())
    default = path.with_name('summary.default.md')
    files.write_text(default, default_template())
    info['default'] = str(default)
  return info


def edit_template():
  """Creates the user's copy from the default when there is none; returns template_info()."""
  path = template_path()
  if not path.is_file():
    default = default_template()
    files.write_text(path, f'<!-- video-agent default: {_fingerprint(default)} -->\n{default}')
  return template_info()


def accept_template():
  """Marks the user's copy as up to date with the current default (after merging its changes by hand)."""
  path = template_path()
  if path.is_file():
    body = BASE_MARK.sub('', path.read_text(encoding='utf-8-sig'), count=1)
    files.write_text(path, f'<!-- video-agent default: {_fingerprint(default_template())} -->\n{body}')
  return template_info()


def reset_template():
  """Removes the user's copy, so every route follows the default again."""
  template_path().unlink(missing_ok=True)
  template_path().with_name('summary.default.md').unlink(missing_ok=True)
  return template_info()


def _session():
  http = requests.Session()
  retry = Retry(
    4, backoff_factor=3, status_forcelist=[429, 500, 502, 503, 504, 529], allowed_methods=None, raise_on_status=False
  )
  for scheme in ('https://', 'http://'):
    http.mount(scheme, HTTPAdapter(max_retries=retry))
  return http


def _post(http, url, headers, body):
  try:
    reply = http.post(url, headers=headers, json=body, timeout=600)
  except requests.RequestException as error:
    raise SummaryError(f'{url}: request failed ({type(error).__name__})') from error
  if reply.status_code >= 400:
    raise SummaryError(f'{url}: HTTP {reply.status_code}: {reply.text[:500]}')
  try:
    return reply.json()
  except ValueError as error:
    raise SummaryError(f'{url}: response was not valid JSON') from error


def _encode(path):
  return base64.b64encode(Path(path).read_bytes()).decode('ascii')


def _clock(second):
  return media.clock_name(second).replace('-', ':')


def _evidence_frames(asset, manifest, limit):
  frames = [(item['time_s'], item['path']) for item in manifest.get('representative_frames') or []]
  for path in sorted((asset / 'frames' / 'extra').glob('frame-*.jpg')):
    match = EXTRA_NAME.search(path.name)
    if match:
      hours, minutes, seconds = (int(part) for part in match.groups())
      frames.append((hours * 3600 + minutes * 60 + seconds, path.relative_to(asset).as_posix()))
  frames.sort()
  if len(frames) > limit:
    step = len(frames) / limit
    frames = [frames[int(index * step)] for index in range(limit)]
  return frames


SHEET_SIDES = (1, 2, 3)  # pages per row on a contact sheet; 1 sends each page alone
MIN_FRAMES = 8  # representative frames kept beside the pages, for the speaker and the room


def _evidence_plan(asset, manifest, budget, work_dir):
  """What goes into `budget` images: every screen page, alone or on 2x2 or 3x3 contact sheets when there are too
  many, then representative and extra frames in the room left (at least MIN_FRAMES where there are). Pages are
  dropped, evenly, only when even 3x3 sheets do not fit. Returns ('page' | 'sheet' | 'frame', file, [(second,
  relative)]) per image, pages per row, and the number of pages left out."""
  pages = [(item['time_s'], item['path']) for item in manifest.get('screen_pages') or []]
  frames = _evidence_frames(asset, manifest, 10**6)
  room = max(1, budget - min(len(frames), MIN_FRAMES))
  side = next((value for value in SHEET_SIDES if math.ceil(len(pages) / value**2) <= room), SHEET_SIDES[-1])
  per = side * side
  dropped = 0
  if math.ceil(len(pages) / per) > room:
    dropped = len(pages) - room * per
    step = len(pages) / (room * per)
    pages = [pages[int(index * step)] for index in range(room * per)]
  plan = []
  if side == 1:
    plan = [('page', asset / relative, [(second, relative)]) for second, relative in pages]
  elif pages:
    for index, sheet in enumerate(media.sheets([asset / relative for _, relative in pages], side, work_dir)):
      plan.append(('sheet', sheet, pages[index * per : (index + 1) * per]))
  left = max(0, budget - len(plan))
  if len(frames) > left:
    frames = [frames[int(index * len(frames) / left)] for index in range(left)] if left else []
  plan += [('frame', asset / relative, [(second, relative)]) for second, relative in frames]
  return plan, side, dropped


def evidence_images(asset, manifest, budget, work_dir):
  """(label, file) pairs within `budget` images, as `_evidence_plan` chooses them, and the number of pages left out."""
  plan, side, dropped = _evidence_plan(asset, manifest, budget, work_dir)
  images = []
  first = 1
  for kind, path, shown in plan:
    if kind == 'sheet':
      listing = '; '.join(f'{_clock(second)} {relative}' for second, relative in shown)
      last = first + len(shown) - 1
      label = f'Screen pages {first}-{last} on one sheet, {side} per row, left to right then top to bottom: {listing}'
      first = last + 1
    else:
      ((second, relative),) = shown
      label = f'{"Screen page" if kind == "page" else "Frame"} at {_clock(second)}, file {relative}:'
    images.append((label, path))
  return images, dropped


class _Tools:
  """Runs the frame tool for the model and enforces the limit."""

  def __init__(self, video, asset, length, limit, status):
    self.video, self.asset, self.length, self.left, self.status = video, asset, length, limit, status

  def frame(self, arguments):
    if self.left <= 0:
      return None, 'Frame limit reached; finish the summary with the frames you have.'
    try:
      second = media.parse_clock((arguments or {}).get('time', ''))
      path = media.save_frame(self.video, self.asset, second, self.length)
    except (ValueError, media.MediaError) as error:
      return None, f'Error: {error}'
    self.left -= 1
    relative = path.relative_to(self.asset).as_posix()
    self.status(f'model asked for a frame at {_clock(second)}')
    return path, f'Saved {relative} at {_clock(second)}; link it as ({relative}).'


def _anthropic(http, config, key, system, intro, images, tools):
  url = f'{config["base_url"]}/v1/messages'
  headers = {'x-api-key': key, 'anthropic-version': '2023-06-01'}
  content = [{'type': 'text', 'text': intro}]
  for label, path in images:
    content += [
      {'type': 'text', 'text': label},
      {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': _encode(path)}},
    ]
  messages = [{'role': 'user', 'content': content}]
  body = {'model': config['model'], 'max_tokens': 16000, 'system': system, 'messages': messages}
  if tools:
    body['tools'] = [
      {'name': FRAME_TOOL['name'], 'description': FRAME_TOOL['description'], 'input_schema': FRAME_TOOL['schema']}
    ]
  while True:
    answer = _post(http, url, headers, body)
    blocks = answer.get('content') or []
    calls = [block for block in blocks if block.get('type') == 'tool_use']
    if answer.get('stop_reason') != 'tool_use' or not calls:
      return ''.join(block.get('text', '') for block in blocks if block.get('type') == 'text')
    messages.append({'role': 'assistant', 'content': blocks})
    results = []
    for call in calls:
      path, note = tools.frame(call.get('input'))
      result = [{'type': 'text', 'text': note}]
      if path:
        result.append(
          {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': _encode(path)}}
        )
      results.append({'type': 'tool_result', 'tool_use_id': call['id'], 'content': result, 'is_error': path is None})
    messages.append({'role': 'user', 'content': results})


def _openai(http, config, key, system, intro, images, tools):
  url = f'{config["base_url"]}/chat/completions'
  headers = {'Authorization': f'Bearer {key}'} if key else {}
  content = [{'type': 'text', 'text': intro}]
  for label, path in images:
    content += [
      {'type': 'text', 'text': label},
      {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{_encode(path)}'}},
    ]
  messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}]
  body = {'model': config['model'], 'messages': messages}
  if tools:
    body['tools'] = [
      {
        'type': 'function',
        'function': {
          'name': FRAME_TOOL['name'],
          'description': FRAME_TOOL['description'],
          'parameters': FRAME_TOOL['schema'],
        },
      }
    ]
  while True:
    answer = _post(http, url, headers, body)
    try:
      message = answer['choices'][0]['message']
    except (KeyError, IndexError, TypeError) as error:
      raise SummaryError(f'{url}: unexpected response shape') from error
    calls = message.get('tool_calls') or []
    if not calls:
      return message.get('content') or ''
    messages.append({'role': 'assistant', 'content': message.get('content'), 'tool_calls': calls})
    # Tool messages carry text only here, so the images follow in one user message.
    shown = []
    for call in calls:
      try:
        arguments = json.loads(call['function'].get('arguments') or '{}')
      except json.JSONDecodeError:
        arguments = {}
      path, note = tools.frame(arguments)
      messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': note})
      if path:
        shown += [
          {'type': 'text', 'text': note},
          {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{_encode(path)}'}},
        ]
    if shown:
      messages.append({'role': 'user', 'content': shown})


_TOOL_HINT = (
  'Before writing, find the moments where the speaker points at the screen ("我们看看", "如图", "this chart") or '
  'the transcript is unclear, and call the frame tool for each one that no frame below already shows. Read what '
  'the new frames show and use it.'
)


# yt-dlp puts look-alike characters into file names for those Windows forbids; these two read as odd in a title.
FILENAME_LOOKALIKES = str.maketrans({'⧸': '/', '⧹': '\\'})


def video_name(video):
  """The title shown for a video: its file name without the extension, with `⧸` and `⧹` turned back into slashes."""
  return Path(video).stem.translate(FILENAME_LOOKALIKES)


def length_text(seconds):
  total = round(seconds)
  hours, rest = divmod(total, 3600)
  return f'{hours}:{rest // 60:02}:{rest % 60:02}' if hours else f'{rest // 60}:{rest % 60:02}'


def video_line(video, seconds):
  """The start of the summary's 视频 line; the name is plain text, so its brackets need no escaping."""
  return f'视频：{video_name(video)} · [打开视频](<{Path(video).as_posix()}>) · 时长：{length_text(seconds)}'


def _clean(text):
  text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
  fenced = re.fullmatch(r'```(?:markdown|md)?\s*\n(.*)\n```', text, re.DOTALL)
  return (fenced.group(1) if fenced else text).strip() + '\n'


def summarize_video(
  video,
  workspace,
  config,
  key,
  *,
  request='',
  max_images=60,
  max_extra_frames=8,
  use_tools=True,
  overwrite=False,
  status=print,
):
  video, info = media.probe(video)
  asset = asset_folder(workspace, video)
  manifest_path, context_path = asset / 'manifest.json', asset / 'summary-context.md'
  if not manifest_path.is_file() or not context_path.is_file():
    raise SummaryError(f'{video.name} has not been processed in {workspace}; run process with the same --output first')
  if config['provider'] == 'anthropic' and not key:
    raise SummaryError('No API key for anthropic; run: video-agent config --provider anthropic --set-key')
  with files.video_lock(asset, 'summarize'):
    return _summarize_locked(
      video, info, asset, config, key, request, max_images, max_extra_frames, use_tools, overwrite, status
    )


def _summarize_locked(
  video, info, asset, config, key, request, max_images, max_extra_frames, use_tools, overwrite, status
):
  manifest_path, context_path = asset / 'manifest.json', asset / 'summary-context.md'
  target = asset / SUMMARY_NAME
  manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

  with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
    images, dropped = evidence_images(asset, manifest, max_images, Path(work_dir))
    if dropped:
      status(
        f'{video.name}: {dropped} screen pages do not fit in {max_images} images even on sheets; pass --max-images'
      )
    text = _ask(
      video, info, asset, config, key, request, images, max_extra_frames, use_tools, context_path, target, status
    )
  # An existing summary stays current unless the new one is asked to replace it; either way neither is lost.
  path, _ = versions.save(target, text, source=f'模型 API · {config["model"]}', note=request, make_current=overwrite)
  return path


def _ask(video, info, asset, config, key, request, images, max_extra_frames, use_tools, context_path, target, status):
  tools = _Tools(video, asset, media.duration(info), max_extra_frames, status) if use_tools else None
  intro = '\n\n'.join(
    part
    for part in (
      f'Write {SUMMARY_NAME} for this video. Return only the Markdown of the file, with no preamble.',
      (
        f'{SUMMARY_NAME} lives in the folder that holds the frames, so link frames by the relative paths given with '
        f'each image. Start the 视频 line exactly with: {video_line(video, media.duration(info))}'
      ),
      _TOOL_HINT if tools else '',
      f'The user asked: {request}' if request else '',
      'The evidence prepared by Video Agent follows: summary-context.md, then the screen pages and the frames.',
      context_path.read_text(encoding='utf-8'),
    )
    if part
  )

  status(
    f'{video.name}: asking {config["provider"]} model {config["model"]} with {len(images)} images'
    + ('' if use_tools else ' (no tool calling)')
  )
  call = _anthropic if config['provider'] == 'anthropic' else _openai
  text = _clean(call(_session(), config, key, template(), intro, images, tools))
  if len(text.strip()) < 40:
    raise SummaryError('The model returned no usable summary')
  return text


def _processed(video, workspace):
  video, info = media.probe(video)
  asset = asset_folder(workspace, video)
  manifest_path, context_path = asset / 'manifest.json', asset / 'summary-context.md'
  if not manifest_path.is_file() or not context_path.is_file():
    raise SummaryError(f'{video.name} has not been processed in {workspace}; run process with the same --output first')
  return video, info, asset, json.loads(manifest_path.read_text(encoding='utf-8'))


# Chat AIs rewrite links they cannot resolve: Gemini wraps a relative path in a search
# (https://www.google.com/search?q=frames/…), ChatGPT puts it under its sandbox (sandbox:/mnt/data/<zip>/frames/…).
LINK = re.compile(r'(\]\(<?)([^()<>\s]+)(>?\))')
LOCAL_ROOTS = ('frames/', 'transcript', 'summary-context.md', '../')


def _local_target(target, base):
  """The relative path a rewritten link stands for, when that file is in `base`; None for a link to leave alone."""
  candidates = []
  parsed = urlparse(target)
  if parsed.scheme in ('http', 'https'):
    for values in parse_qs(parsed.query).values():
      candidates += values
  if parsed.scheme in ('http', 'https', 'sandbox', 'file') or target.startswith('/'):
    path = unquote(parsed.path if parsed.scheme else target)
    for root in LOCAL_ROOTS:
      if root in path:
        candidates.append(path[path.index(root) :])
  for candidate in candidates:
    candidate = unquote(candidate).strip()
    if candidate.startswith(LOCAL_ROOTS) and (Path(base) / candidate).exists():
      return candidate
  return None


def repair_links(text, base):
  """Puts back the relative links a chat AI turned into search or sandbox links (user report, 2026-10-28)."""
  return LINK.sub(lambda m: m[1] + (_local_target(m[2], base) or m[2]) + m[3], text)


# A chat AI cannot run `video-agent fix`; the prompt asks it to list recurring mishearings in this section instead.
CORRECTIONS_HEADING = '字幕改正'
CORRECTIONS = re.compile(rf'^##\s*{CORRECTIONS_HEADING}\s*\n(.*?)(?=^##\s|\Z)', re.MULTILINE | re.DOTALL)
PAIR = re.compile(r'^\s*(?:[-*]\s*)?`?(.+?)`?\s*(?:→|->|=>)\s*`?(.+?)`?\s*$')


# Shown after the template as a section of it, with its form, so a chat AI writes it as it writes the others.
CORRECTIONS_SECTION = f"""## 字幕改正（网页 AI 写在总结最后）

你不能运行命令，所以规则里用 `video-agent fix` 整理字幕的那一步改成在总结最后写这一节：每次出现都识别错的名字、术语，\
每行一条。导入时程序会照它整理字幕（原字幕保留），再把这一节从总结里去掉。只错一次的、错的写法本身也是正常词语的，只在\
总结正文里改，不列进来；没有要改的就不写这一节。

```markdown
## {CORRECTIONS_HEADING}

- 错的写法 → 正确写法
```"""


def take_corrections(text):
  """(summary without the 字幕改正 section, [(wrong, right)] it listed)."""
  found = CORRECTIONS.search(text)
  if not found:
    return text, []
  pairs = [(m[1], m[2]) for line in found[1].splitlines() if (m := PAIR.match(line)) and m[1] != m[2]]
  return (text[: found.start()] + text[found.end() :]).rstrip() + '\n', pairs


def import_summary(video, workspace, text, *, overwrite=False, source='', note=''):
  """Saves a summary written elsewhere, such as by a chat AI from `pack`, as 总结.md: a ```markdown fence is removed,
  rewritten links point at the video's files again, the 视频 line is the one this program writes, and a 字幕改正
  section goes into the cleaned transcript. With a summary there already, the new one is kept as a version unless
  `overwrite` makes it current (versions.py). Returns (path written, corrections applied)."""
  video, info, asset, manifest = _processed(video, workspace)
  text, pairs = take_corrections(_clean(text))
  if len(text.strip()) < 40:
    raise SummaryError('The summary to import is empty or too short')
  text = repair_links(text, asset)
  line = video_line(video, manifest.get('duration_s') or media.duration(info))
  text = re.sub(r'^视频：.*?时长：[0-9:]+', lambda _: line, text, count=1, flags=re.MULTILINE)
  with files.video_lock(asset, 'import the summary'):
    target, _ = versions.save(asset / SUMMARY_NAME, text, source=source or '导入', note=note, make_current=overwrite)
    if pairs:
      from . import corrections

      known = [pair for pair in corrections.load(asset) if pair[0] not in {wrong for wrong, _ in pairs}]
      corrections.save(asset, known + pairs)
      processor.refresh_transcript(asset)
  return target, pairs


PROMPT_NAME = '提示词.md'


SHEET_FOLDER = '总图'


PICTURE_KINDS = {'page': '屏幕页', 'sheet': '屏幕页总图', 'frame': '画面'}


def _numbered_pictures(asset, manifest, budget, work_dir):
  """At most `budget` pictures with numbered names, for a chat AI that takes a limited number of files, and the note
  that says which frames each one shows and which paths to link."""
  plan, side, dropped = _evidence_plan(asset, manifest, budget, work_dir)
  entries, lines = [], []
  for number, (kind, path, shown) in enumerate(plan, 1):
    name = f'{number:03d}-{PICTURE_KINDS[kind]}-{_clock(shown[0][0]).replace(":", "-")}.jpg'
    entries.append((name, path))
    lines.append(f'- {name}：' + '、'.join(f'{_clock(second)} {relative}' for second, relative in shown))
  pages = sum(len(shown) for kind, _, shown in plan if kind != 'frame')
  frames = sum(kind == 'frame' for kind, _, _ in plan)
  sheets = ''
  if side > 1:
    count = sum(kind == 'sheet' for kind, _, _ in plan)
    sheets = f'，拼在 {count} 张总图里（每张 {side}×{side} 页，从左到右、从上到下）'
  note = (
    f'我附上了 {len(entries)} 张图片：这个视频的 {pages} 张屏幕页（幻灯片、代码、文档）{sheets}，和 {frames} 张整幅画面。'
    '上传后的文件名不是总结里要用的路径：下表左边是图片的文件名，右边是它显示的画面的时间和路径（总图按顺序列出'
    '每一页）。写总结时链接右边的路径，链接到画面所在的那一页；没有出现在表里的画面不要链接。'
  )
  if dropped:
    note += f'屏幕页太多，有 {dropped} 页没有附上，材料里提到它们时你看不到。'
  return entries, note + '\n\n' + '\n'.join(lines)


def material(video, workspace, *, request='', max_images=40, work_dir=None, max_files=None):
  """The prompt for a chat AI: rules, template and the evidence. With `work_dir`, also the files that go along as
  (path in the zip, file): every screen page and up to `max_images` other frames, at their paths in the video's folder
  (so links written from the evidence still work once the summary is imported there), and 2x2 contact sheets of the
  pages in SHEET_FOLDER for chat AIs that take few images. With `max_files` as well, at most that many files with the
  prompt: numbered pictures in one folder, as `_numbered_pictures` chooses them."""
  video, info, asset, manifest = _processed(video, workspace)
  pages = [(item['time_s'], item['path']) for item in manifest.get('screen_pages') or []]
  frames = _evidence_frames(asset, manifest, max_images)
  entries, notes = [], []
  if work_dir is None:
    notes.append('这次没有附上画面，材料里列出的屏幕页和画面你看不到：不要描述画面内容，也不要链接画面。')
  elif max_files:
    entries, note = _numbered_pictures(asset, manifest, max_files - 1, Path(work_dir))
    notes.append(note)
  else:
    entries = [(relative, asset / relative) for _, relative in pages + frames]
    notes.append(
      f'我附上了这个视频的 {len(pages)} 张屏幕页（幻灯片、代码、文档，每页一张）和 {len(frames)} 张整幅画面，'
      '文件名里带时间点。下面材料引用它们时写的是 frames/… 的相对路径：看图时按文件名对应，写总结时照材料里的相对'
      '路径链接，不要只写文件名。没有附上的画面不要链接。'
    )
    if pages:
      sheets = media.sheets([asset / relative for _, relative in pages], 2, Path(work_dir))
      lines = []
      for index, sheet in enumerate(sheets, 1):
        name = f'{SHEET_FOLDER}/{SHEET_FOLDER}-{index:03d}.jpg'
        entries.append((name, sheet))
        group = pages[(index - 1) * 4 : index * 4]
        lines.append(f'- {name}：' + '、'.join(f'{_clock(second)} {relative}' for second, relative in group))
      notes.append(
        f'如果一次收不了这么多图片，就看 {SHEET_FOLDER}/ 里的 {len(sheets)} 张总图：每张拼了 4 页屏幕页，从左到右、'
        '从上到下，对应下表。链接时仍写原来的屏幕页路径。\n\n' + '\n'.join(lines)
      )
  text = '\n\n'.join(
    part
    for part in (
      f'请按下面的规则和模板，为这个视频写 {SUMMARY_NAME}（Markdown）。只输出文件内容，前后不要加说明。',
      f'我的要求：{request}' if request else '',
      *notes,
      f'「视频」那一行的开头照抄：{video_line(video, media.duration(info))}',
      template(),
      CORRECTIONS_SECTION,
      '---',
      (asset / 'summary-context.md').read_text(encoding='utf-8'),
    )
    if part
  )
  return text, entries


def pack(video, workspace, target, *, request='', max_images=40):
  """Writes a zip with 提示词.md, the screen pages, frames and contact sheets, for chat AIs that take files. Returns
  the zip and the number of pictures in it."""
  target = Path(target)
  target.parent.mkdir(parents=True, exist_ok=True)
  temporary = files.temporary_beside(target)
  try:
    with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
      text, entries = material(video, workspace, request=request, max_images=max_images, work_dir=work_dir)
      with zipfile.ZipFile(temporary, 'w') as archive:
        archive.writestr(PROMPT_NAME, text, compress_type=zipfile.ZIP_DEFLATED)
        for name, path in entries:
          archive.write(path, name)  # JPEG does not compress further
    files.replace(temporary, target)
  finally:
    temporary.unlink(missing_ok=True)
  return target, len(entries)


def pack_folder(video, workspace, parent, *, request='', max_files=50):
  """Writes a new folder in `parent` with 提示词.md and numbered pictures, `max_files` files in all, for chat AIs that
  take files one by one up to a limit and no zip. Returns the folder and the number of pictures in it."""
  if max_files < 2:
    raise SummaryError('a folder for a chat AI needs room for the prompt and at least one picture')
  parent = Path(parent)
  name = f'{video_name(Path(video))}-材料'
  target = parent / name
  number = 2
  while target.exists():
    target = parent / f'{name} ({number})'
    number += 1
  with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
    text, entries = material(video, workspace, request=request, work_dir=work_dir, max_files=max_files)
    temporary = files.temporary_beside(target)
    try:
      temporary.mkdir(parents=True)
      files.write_text(temporary / PROMPT_NAME, text)
      for picture, path in entries:
        shutil.copyfile(path, temporary / picture)
      temporary.rename(target)
    finally:
      shutil.rmtree(temporary, ignore_errors=True)
  return target, len(entries)


def _collection_evidence(workspace, name):
  """Each video's summary in order, the skipped ones and the shared terms, as Markdown, and the videos that still lack
  a summary. The summaries already link their pictures, so a collection file is written from text."""
  from . import collection

  info = collection.status(workspace, name)
  parts, missing = [], []
  for member in info['videos']:
    folder = Path(member['folder']).name
    length = length_text(member['duration_s']) if member['duration_s'] else 'not processed'
    head = f'### {member["index"]}. {video_name(member["video"])} ({length}); its folder: ../../{folder}/'
    if member['skipped']:
      parts += [head, f'Skipped: {member["skipped"]}', '']
    elif member['summary']:
      parts += [head, Path(member['summary']).read_text(encoding='utf-8').strip(), '']
    else:
      missing.append(member['video'])
      parts += [head, '(No summary yet.)', '']
  if info['terms']:
    parts += [
      '### Shared terms of the cleaned transcripts',
      *(f'- {wrong} -> {right}' for wrong, right in info['terms']),
    ]
  return info, '\n'.join(parts), missing


def _collection_target(workspace, name, guide):
  from . import collection

  return collection.folder(workspace, name) / (collection.GUIDE if guide else collection.OVERVIEW)


def collection_material(workspace, name, *, guide=False, request=''):
  """The prompt for a chat AI to write the collection overview or study guide."""
  target = _collection_target(workspace, name, guide)
  _, evidence, missing = _collection_evidence(workspace, name)
  notes = (
    [f'还没有总结的视频：{"、".join(video_name(video) for video in missing)}。这几集只能按标题提一句。']
    if missing
    else []
  )
  return '\n\n'.join(
    part
    for part in (
      f'请按下面的规则和模板，为合集「{name}」写 {target.name}（Markdown）。只输出文件内容，前后不要加说明。',
      f'我的要求：{request}' if request else '',
      *notes,
      template(),
      '---',
      f'合集「{name}」各集的总结，按顺序：',
      evidence,
    )
    if part
  )


def summarize_collection(workspace, name, config, key, *, guide=False, request='', overwrite=False, status=print):
  """Writes 合集总结.md or 学习提纲.md with a model API from the members' summaries."""
  from . import collection

  if config['provider'] == 'anthropic' and not key:
    raise SummaryError('No API key for anthropic; run: video-agent config --provider anthropic --set-key')
  target = _collection_target(workspace, name, guide)
  with collection.lock(workspace, name, 'summarize the collection'):
    _, evidence, missing = _collection_evidence(workspace, name)
    if missing:
      raise SummaryError(
        'These videos have no summary yet; summarize or skip them first: '
        + ', '.join(video_name(video) for video in missing)
      )
    intro = '\n\n'.join(
      part
      for part in (
        (
          f'Write {target.name} for the collection "{name}", in the folder {target.parent.name}/ of the workspace. '
          "Return only the Markdown of the file, with no preamble. Link each video's summary by the relative path "
          'given with it (../../<folder>/总结.md).'
        ),
        f'The user asked: {request}' if request else '',
        'The summaries of the videos follow, in order.',
        evidence,
      )
      if part
    )
    status(f'{name}: asking {config["provider"]} model {config["model"]} for {target.name}')
    call = _anthropic if config['provider'] == 'anthropic' else _openai
    text = _clean(call(_session(), config, key, template(), intro, [], None))
    if len(text.strip()) < 40:
      raise SummaryError('The model returned no usable text')
    path, _ = versions.save(target, text, source=f'模型 API · {config["model"]}', note=request, make_current=overwrite)
  return path


def import_collection(workspace, name, text, *, guide=False, overwrite=False, source='', note=''):
  """Saves a collection overview or study guide written elsewhere, as import_summary does for one video."""
  from . import collection

  collection.load(workspace, name)
  target = _collection_target(workspace, name, guide)
  text = repair_links(_clean(text), target.parent)
  if len(text.strip()) < 40:
    raise SummaryError('The text to import is empty or too short')
  with collection.lock(workspace, name, 'import into the collection'):
    path, _ = versions.save(target, text, source=source or '导入', note=note, make_current=overwrite)
  return path
