"""Invoke the installed AutoSlides Extractor CLI for optional slide output."""

import json
import os
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path


class SlideExtractorError(RuntimeError):
  pass


def find_extractor(explicit=None):
  candidates = []
  if explicit:
    candidates.append(Path(explicit).expanduser())
  if configured := os.environ.get('AUTOSLIDES_EXTRACTOR'):
    candidates.append(Path(configured).expanduser())
  for command in ('SlidesExtractor', 'AutoSlidesExtractor'):
    if found := shutil.which(command):
      candidates.append(Path(found))
  if os.name == 'nt':
    for variable in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
      if root := os.environ.get(variable):
        base = Path(root)
        candidates.append(base / 'AutoSlides Extractor' / 'AutoSlidesExtractor.exe')
        candidates.append(base / 'Programs' / 'AutoSlides Extractor' / 'AutoSlidesExtractor.exe')
  for candidate in candidates:
    if candidate.is_file():
      return candidate.resolve()
  raise SlideExtractorError(
    'AutoSlides Extractor was not found. Install it or pass --slide-extractor PATH; the slide option is off by default.'
  )


def _timeline(slide_folder):
  path = slide_folder / 'timeline.json'
  if not path.is_file():
    return []
  try:
    data = json.loads(path.read_text(encoding='utf-8'))
  except (OSError, json.JSONDecodeError):
    return []
  resolutions = data.get('resolutions') or {}
  result, seen = [], set()
  for event in sorted(data.get('events') or [], key=lambda row: row.get('changeAt', 0)):
    resolution = resolutions.get(str(event.get('id'))) or resolutions.get(event.get('id')) or {}
    state = resolution.get('state')
    name = (
      resolution.get('file')
      if state == 'canonical'
      else resolution.get('duplicateOf')
      if state == 'duplicate'
      else None
    )
    if not name:
      continue
    image = slide_folder / name
    if image.is_file() and image.name not in seen:
      seen.add(image.name)
      result.append({'time_s': float(event.get('changeAt', 0)), 'path': image})
  return result


def extract(video, output_parent, *, executable=None, status=print):
  program = find_extractor(executable)
  run_id = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
  output_root = Path(output_parent) / run_id
  output_root.mkdir(parents=True, exist_ok=False)
  command = [
    str(program),
    '--video',
    str(video),
    '--output',
    str(output_root),
    '--json',
    '--write-timeline',
    '--ssim-threshold',
    '0.9985',
    '--enable-downsampling',
    'true',
    '--downsample-width',
    '480',
    '--downsample-height',
    '270',
    '--chunk-size',
    '100',
    '--jpeg-quality',
    '95',
    '--phash-redundant',
    '--hamming-threshold',
    '10',
    '--ml-classify',
    '--ml-execution-provider',
    'Auto',
    '--ml-not-slide-high',
    '0.90',
    '--ml-not-slide-low',
    '0.75',
    '--ml-maybe-slide-high',
    '0.90',
    '--ml-maybe-slide-low',
    '0.75',
    '--ml-slide-max',
    '0.25',
    '--ml-delete-maybe-slides',
    'false',
  ]
  status(f'AutoSlides Extractor: starting on {Path(video).name}')
  try:
    process = subprocess.Popen(
      command,
      cwd=output_root,
      stdin=subprocess.DEVNULL,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      encoding='utf-8',
      errors='replace',
    )
    assert process.stdout is not None
    for line in process.stdout:
      line = line.strip()
      if not line:
        continue
      try:
        event = json.loads(line)
      except json.JSONDecodeError:
        status(f'AutoSlides Extractor: {line}')
        continue
      kind = event.get('event') or event.get('type') or 'progress'
      details = event.get('message') or event.get('stage') or event.get('progress')
      status(f'AutoSlides Extractor: {kind}' + (f' {details}' if details is not None else ''))
    code = process.wait()
  except OSError as error:
    raise SlideExtractorError(f'Could not start AutoSlides Extractor: {error}') from error
  if code != 0:
    raise SlideExtractorError(f'AutoSlides Extractor exited with code {code}; its output is in {output_root}')
  folders = sorted(path for path in output_root.glob('slides_*') if path.is_dir())
  if not folders:
    raise SlideExtractorError(f'AutoSlides Extractor completed without a slides_* folder; inspect {output_root}')
  folder = folders[0]
  slides = _timeline(folder)
  if not slides:
    images = sorted([*folder.glob('*.jpg'), *folder.glob('*.jpeg'), *folder.glob('*.png')])
    slides = [{'time_s': None, 'path': image} for image in images]
  return {'output_root': output_root, 'folder': folder, 'timeline': folder / 'timeline.json', 'slides': slides}
