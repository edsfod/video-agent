"""Write 总结.md from a processed video's evidence with a model API; the Agent skill is the other route.

The model sees the transcript and the representative frames. Where the provider supports tool calling it can ask for
more frames: the `frame` tool saves one into `frames/extra/` and sends the image back, up to a limit.
"""

import base64
import json
import re
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


def _video_link(video):
  name = video.name.replace('[', '\\[').replace(']', '\\]')
  return f'[{name}](<{video.as_posix()}>)'


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
  max_images=40,
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

  frames = _evidence_frames(asset, manifest, max_images)
  images = [(f'Frame at {_clock(second)}, file {relative}:', asset / relative) for second, relative in frames]
  tools = _Tools(video, asset, media.duration(info), max_extra_frames, status) if use_tools else None
  intro = '\n\n'.join(
    part
    for part in (
      f'Write {SUMMARY_NAME} for this video. Return only the Markdown of the file, with no preamble.',
      (
        f'{SUMMARY_NAME} lives in the folder that holds the frames, so link frames by the relative paths given with '
        f'each image. Link the source video exactly as {_video_link(video)}'
      ),
      _TOOL_HINT if tools else '',
      f'The user asked: {request}' if request else '',
      'The evidence prepared by Video Agent follows: summary-context.md, then the frames.',
      context_path.read_text(encoding='utf-8'),
    )
    if part
  )

  status(
    f'{video.name}: asking {config["provider"]} model {config["model"]} with {len(images)} frames'
    + ('' if use_tools else ' (no tool calling)')
  )
  call = _anthropic if config['provider'] == 'anthropic' else _openai
  text = _clean(call(_session(), config, key, template(), intro, images, tools))
  if len(text.strip()) < 40:
    raise SummaryError('The model returned no usable summary')
  files.write_text(target, text)
  return target
