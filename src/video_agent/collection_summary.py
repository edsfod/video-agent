"""A collection's overview (合集总结.md) and study guide (学习提纲.md), written from its videos' summaries, which already
link their pictures, so no images are sent: with a model API, or as a prompt for a chat AI. Agents write them through
the skill and save them with importer.import_collection.
"""

from pathlib import Path

from . import collection, model_api, templates, versions
from .evidence import length_text, video_name
from .importer import clean
from .model_api import SummaryError
from .packing import OUTPUT_FENCE


def _evidence(workspace, name):
  """Each video's summary in order, the skipped ones and the shared terms, as Markdown, and the videos that still lack
  a summary. The summaries already link their pictures, so a collection file is written from text."""
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


def collection_material(workspace, name, *, guide=False, request='', template=None):
  """The prompt for a chat AI to write the collection overview or study guide."""
  target = collection.text_path(workspace, name, guide)
  _, evidence, missing = _evidence(workspace, name)
  notes = (
    [f'还没有总结的视频：{"、".join(video_name(video) for video in missing)}。这几集只能按标题提一句。']
    if missing
    else []
  )
  return '\n\n'.join(
    part
    for part in (
      f'请按下面的规则和模板，为合集「{name}」写 {target.name}（Markdown）。{OUTPUT_FENCE}',
      f'我的要求：{request}' if request else '',
      *notes,
      templates.text(template),
      '---',
      f'合集「{name}」各集的总结，按顺序：',
      evidence,
    )
    if part
  )


def summarize_collection(
  workspace, name, config, key, *, guide=False, request='', overwrite=False, status=print, template=None
):
  """Writes 合集总结.md or 学习提纲.md with a model API from the members' summaries."""
  model_api.provider(config, key)  # a missing key is said before anything else
  target = collection.text_path(workspace, name, guide)
  rules = templates.text(template)
  with collection.lock(workspace, name, 'summarize the collection'):
    _, evidence, missing = _evidence(workspace, name)
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
    text = clean(model_api.ask(config, key, rules, intro, [], None))
    if len(text.strip()) < 40:
      raise SummaryError('The model returned no usable text')
    path, _ = versions.save(target, text, source=f'模型 API · {config["model"]}', note=request, make_current=overwrite)
  return path
