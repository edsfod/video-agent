"""Write 总结.md from a processed video's evidence with a model API; the Agent skill is the other route.

The model sees the transcript, every screen page and the representative frames, within an image budget: pages go one
per image, or several on a contact sheet when there are too many. Where the provider supports tool calling it can ask
for more frames: the `frame` tool saves one into `frames/extra/` and sends the image back, up to a limit.
"""

import base64
import json
import math
import re
import tempfile
import zipfile
from importlib import resources
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from . import files, media
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


def template():
  return resources.files('video_agent').joinpath('prompts/summary.md').read_text(encoding='utf-8')


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


def evidence_images(asset, manifest, budget, work_dir):
  """(label, file) pairs within `budget` images: every screen page, alone or on 2x2 or 3x3 contact sheets when
  there are too many, then representative and extra frames in the room left (at least MIN_FRAMES where there are).
  Pages are dropped, evenly, only when even 3x3 sheets do not fit. Returns the pairs and the number of pages left out."""
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
  images = []
  if side == 1:
    images = [(f'Screen page at {_clock(second)}, file {relative}:', asset / relative) for second, relative in pages]
  elif pages:
    for index, sheet in enumerate(media.sheets([asset / relative for _, relative in pages], side, work_dir)):
      group = pages[index * per : (index + 1) * per]
      listing = '; '.join(f'{_clock(second)} {relative}' for second, relative in group)
      first, last = index * per + 1, index * per + len(group)
      label = f'Screen pages {first}-{last} on one sheet, {side} per row, left to right then top to bottom: {listing}'
      images.append((label, sheet))
  left = max(0, budget - len(images))
  if len(frames) > left:
    frames = [frames[int(index * len(frames) / left)] for index in range(left)] if left else []
  images += [(f'Frame at {_clock(second)}, file {relative}:', asset / relative) for second, relative in frames]
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
  text = text.strip()
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
  if target.exists() and not overwrite:
    raise SummaryError(f'{target} already exists; pass --overwrite to replace it')
  manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

  with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
    images, dropped = evidence_images(asset, manifest, max_images, Path(work_dir))
    if dropped:
      status(
        f'{video.name}: {dropped} screen pages do not fit in {max_images} images even on sheets; pass --max-images'
      )
    return _ask(
      video, info, asset, config, key, request, images, max_extra_frames, use_tools, context_path, target, status
    )


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
  files.write_text(target, text)
  return target


def _processed(video, workspace):
  video, info = media.probe(video)
  asset = asset_folder(workspace, video)
  manifest_path, context_path = asset / 'manifest.json', asset / 'summary-context.md'
  if not manifest_path.is_file() or not context_path.is_file():
    raise SummaryError(f'{video.name} has not been processed in {workspace}; run process with the same --output first')
  return video, info, asset, json.loads(manifest_path.read_text(encoding='utf-8'))


def import_summary(video, workspace, text, *, overwrite=False):
  """Saves a summary written elsewhere, such as by a chat AI from `pack`, as 总结.md; a ```markdown fence is removed."""
  video, _, asset, _ = _processed(video, workspace)
  text = _clean(text)
  if len(text.strip()) < 40:
    raise SummaryError('The summary to import is empty or too short')
  with files.video_lock(asset, 'import the summary'):
    target = asset / SUMMARY_NAME
    if target.exists() and not overwrite:
      raise SummaryError(f'{target} already exists; pass --overwrite to replace it')
    files.write_text(target, text)
  return target


PROMPT_NAME = '提示词.md'


SHEET_FOLDER = '总图'


def material(video, workspace, *, request='', max_images=40, work_dir=None):
  """The prompt for a chat AI: rules, template and the evidence. With `work_dir`, also the files that go along as
  (path in the zip, file): every screen page and up to `max_images` other frames, at their paths in the video's folder
  (so links written from the evidence still work once the summary is imported there), and 2x2 contact sheets of the
  pages in SHEET_FOLDER for chat AIs that take few images."""
  video, info, asset, manifest = _processed(video, workspace)
  pages = [(item['time_s'], item['path']) for item in manifest.get('screen_pages') or []]
  frames = _evidence_frames(asset, manifest, max_images)
  entries, notes = [], []
  if work_dir is None:
    notes.append('这次没有附上画面，材料里列出的屏幕页和画面你看不到：不要描述画面内容，也不要链接画面。')
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
