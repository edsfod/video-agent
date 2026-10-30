"""Write 总结.md from a processed video's evidence with a model API; the Agent skill and chat AIs (packing.py,
importer.py) are the other routes.

The model sees the transcript, every screen page and the representative frames, within an image budget (evidence.py).
Where the provider supports tool calling it can ask for more frames: the `frame` tool saves one into `frames/extra/`
and sends the image back, up to a limit.
"""

import json
import tempfile
from pathlib import Path

from . import files, media, model_api, pictures, processor, templates, versions
from .evidence import SUMMARY_NAME, clock, evidence_images, video_line
from .importer import clean
from .model_api import SummaryError
from .processor import asset_folder


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
    self.status(f'model asked for a frame at {clock(second)}')
    return path, f'Saved {relative} at {clock(second)}; link it as ({relative}).'


_TOOL_HINT = (
  'Before writing, find the moments where the speaker points at the screen ("我们看看", "如图", "this chart") or '
  'the transcript is unclear, and call the frame tool for each one that no frame below already shows. Read what '
  'the new frames show and use it.'
)


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
  template=None,
):
  video, info = media.probe(video)
  asset = asset_folder(workspace, video)
  manifest_path, context_path = asset / 'manifest.json', asset / 'summary-context.md'
  if not manifest_path.is_file() or not context_path.is_file():
    raise SummaryError(f'{video.name} has not been processed in {workspace}; run process with the same --output first')
  model_api.provider(config, key)  # a missing key is said before anything else
  rules = templates.text(template)
  processor.update_context(asset)
  with files.video_lock(asset, 'summarize'):
    return _summarize_locked(
      video, info, asset, config, key, request, max_images, max_extra_frames, use_tools, overwrite, status, rules
    )


def _summarize_locked(
  video, info, asset, config, key, request, max_images, max_extra_frames, use_tools, overwrite, status, rules
):
  manifest_path, context_path = asset / 'manifest.json', asset / 'summary-context.md'
  target = asset / SUMMARY_NAME
  manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

  with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
    images, dropped = evidence_images(asset, manifest, max_images, Path(work_dir))
    if dropped:
      status(f'{video.name}: {dropped} pictures do not fit in {max_images} images even on sheets; pass --max-images')
    text = _ask(
      video, info, asset, config, key, request, images, max_extra_frames, use_tools, context_path, target, status, rules
    )
  # An existing summary stays current unless the new one is asked to replace it; either way neither is lost.
  source = f'模型 API · {config["model"]}'
  path, _ = versions.save(
    target, text, source=source, note=request, make_current=overwrite, pictures=pictures.current(asset)
  )
  return path


def _ask(
  video, info, asset, config, key, request, images, max_extra_frames, use_tools, context_path, target, status, rules
):
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
  text = clean(model_api.ask(config, key, rules, intro, images, tools))
  if len(text.strip()) < 40:
    raise SummaryError('The model returned no usable summary')
  return text
