"""Build a per-video evidence workspace without modifying the source media."""

import hashlib
import json
import re
import shutil
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from . import media, slide_extractor, transcript


def slug(value):
  cleaned = re.sub(r'[^A-Za-z0-9._-]+', '-', value).strip('-.')
  return cleaned[:64] or 'video'


def asset_folder(workspace, video):
  identity = hashlib.sha256(str(video).casefold().encode('utf-8')).hexdigest()[:10]
  return Path(workspace) / f'{slug(video.stem)}-{identity}'


def _write_json(path, value):
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = path.with_suffix(path.suffix + '.part')
  temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
  temporary.replace(path)


def _stamp(value):
  total = max(0, round(value))
  hours, total = divmod(total, 3600)
  minutes, seconds = divmod(total, 60)
  return f'{hours:02}-{minutes:02}-{seconds:02}'


MIN_GAP_S = 1.0  # a scene change and a regular sample this close show the same picture


def _unique(candidates):
  found, seen = [], set()
  for item in sorted(candidates, key=lambda candidate: candidate['time_s']):
    digest = hashlib.sha256(item['path'].read_bytes()).digest()
    if digest in seen or (found and item['time_s'] - found[-1]['time_s'] < MIN_GAP_S):
      continue
    seen.add(digest)
    found.append(item)
  return found


def _bounded(candidates, limit):
  if len(candidates) <= limit:
    return candidates
  if limit == 1:
    return [candidates[len(candidates) // 2]]
  indexes = {round(index * (len(candidates) - 1) / (limit - 1)) for index in range(limit)}
  return [candidates[index] for index in sorted(indexes)]


def _copy_candidates(candidates, target, prefix):
  target = Path(target)
  target.mkdir(parents=True, exist_ok=True)
  result = []
  for number, item in enumerate(candidates, 1):
    name = f'{prefix}-{number:03d}-{_stamp(item["time_s"])}.jpg'
    path = target / name
    shutil.copyfile(item['path'], path)
    result.append({'time_s': round(item['time_s'], 3), 'path': path})
  return result


def _context(asset, video, info, rows, transcript_source, transcript_error, frames, slides):
  seconds = media.duration(info)
  lines = [
    '# Video summary context',
    '',
    'This is source evidence, not a generated summary. Write a concise, timestamped summary from the transcript and frames.',
    '',
    f'- Source: `{video}`',
    f'- Duration: {seconds:.1f} seconds',
    f'- Transcript source: {transcript_source}',
  ]
  if transcript_error:
    lines.extend(['', f'- Transcript status: {transcript_error}'])
  lines.extend(['', '## Transcript', ''])
  if rows:
    lines.extend(f'[{transcript.format_clock(start)}] {" ".join(text.split())}' for start, _, text in rows)
  else:
    lines.append('(No speech transcript was available.)')
  lines.extend(['', '## Representative frames', ''])
  if frames:
    for item in frames:
      relative = quote(item['path'].relative_to(asset).as_posix(), safe='/-._~')
      lines.append(f'- {item["time_s"]:.1f}s: ![frame]({relative})')
  else:
    lines.append('(No representative frames were extracted.)')
  if slides:
    lines.extend(['', '## Extracted slides', ''])
    for item in slides:
      relative = quote(item['path'].relative_to(asset).as_posix(), safe='/-._~')
      time_text = f'{item["time_s"]:.1f}s' if item['time_s'] is not None else 'time unavailable'
      lines.append(f'- {time_text}: ![slide]({relative})')
  lines.append('')
  return '\n'.join(lines)


def _previous_source(asset):
  """Where a kept transcript first came from, read from the last manifest; older manifests may not say."""
  try:
    source = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))['transcript']['source']
  except (OSError, ValueError, KeyError, TypeError):
    return 'existing-output'
  return source if source and source != 'unavailable' else 'existing-output'


def process_video(
  video,
  workspace,
  *,
  interval=60.0,
  scene_threshold=0.35,
  max_frames=36,
  extract_slides=False,
  slide_extractor_path=None,
  asr='none',
  allow_remote_asr=False,
  overwrite=False,
  status=print,
):
  video, info = media.probe(video)
  asset = asset_folder(workspace, video)
  asset.mkdir(parents=True, exist_ok=True)
  status(f'{video.name}: {media.duration(info):.1f}s, {len(info.get("streams") or [])} streams')

  frame_run = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
  frames_dir = asset / 'frames' / frame_run
  status(f'{video.name}: sampling frames every {interval:g}s and at scene changes')
  with tempfile.TemporaryDirectory(prefix='video-agent-') as temporary:
    temporary = Path(temporary)
    periodic = media.periodic_frames(video, temporary / 'periodic', interval)
    try:
      scenes = media.scene_frames(video, temporary / 'scenes', scene_threshold)
    except media.MediaError as error:
      status(f'{video.name}: scene detection unavailable; keeping periodic samples ({error})')
      scenes = []
    frame_candidates = _bounded(_unique(periodic + scenes), max_frames)
    frames = _copy_candidates(frame_candidates, frames_dir, 'frame')

  slide_result, slide_error = None, ''
  if extract_slides:
    try:
      slide_result = slide_extractor.extract(
        video,
        asset / 'slide-extraction',
        executable=slide_extractor_path,
        status=lambda message: status(f'{video.name}: {message}'),
      )
    except slide_extractor.SlideExtractorError as error:
      slide_error = str(error)
      status(f'{video.name}: slide extraction failed: {slide_error}')

  status(f'{video.name}: obtaining timed subtitles')
  transcript_path = asset / 'transcript.srt'
  transcript_error = ''
  existing_rows = (
    transcript.parse(transcript_path.read_text(encoding='utf-8-sig', errors='replace'))
    if transcript_path.is_file()
    else None
  )
  transcript_source = _previous_source(asset)
  if existing_rows is not None and not overwrite:
    rows = existing_rows
  else:
    try:
      rows, transcript_source = transcript.acquire(
        video,
        info.get('streams') or [],
        asset,
        asr=asr,
        allow_remote_asr=allow_remote_asr,
        status=lambda message: status(f'{video.name}: {message}'),
      )
      transcript.write(rows, asset)
    except media.MediaError as error:
      if existing_rows is not None:
        rows, transcript_source = existing_rows, _previous_source(asset)
        transcript_error = f'Refresh failed; kept the existing transcript. {error}'
      else:
        rows, transcript_source, transcript_error = [], 'unavailable', str(error)

  slides = slide_result['slides'] if slide_result else []
  text = _context(asset, video, info, rows, transcript_source, transcript_error, frames, slides)
  context_path = asset / 'summary-context.md'
  context_path.write_text(text, encoding='utf-8')
  manifest = {
    'schema_version': 1,
    'source_video': str(video),
    'updated_utc': datetime.now(UTC).isoformat(),
    'duration_s': media.duration(info),
    'streams': [
      {
        'index': stream.get('index'),
        'type': stream.get('codec_type'),
        'codec': stream.get('codec_name'),
        'language': (stream.get('tags') or {}).get('language'),
      }
      for stream in info.get('streams') or []
    ],
    'transcript': {
      'source': transcript_source,
      'segments': len(rows),
      'error': transcript_error or None,
      'srt': 'transcript.srt' if transcript_path.is_file() else None,
    },
    'representative_frame_run': str(frames_dir.relative_to(asset)),
    'representative_frames': [
      {'time_s': item['time_s'], 'path': item['path'].relative_to(asset).as_posix()} for item in frames
    ],
    'slide_extraction': {
      'enabled': bool(extract_slides),
      'output': str(slide_result['output_root'].relative_to(asset)) if slide_result else None,
      'timeline': str(slide_result['timeline'].relative_to(asset)) if slide_result else None,
      'error': slide_error or None,
      'slides': [{'time_s': item['time_s'], 'path': item['path'].relative_to(asset).as_posix()} for item in slides],
    },
    'summary_context': 'summary-context.md',
    'summary_generated': False,
  }
  _write_json(asset / 'manifest.json', manifest)
  status(f'{video.name}: evidence saved to {asset}')
  if transcript_error:
    status(f'{video.name}: transcript missing; frames and summary context were still saved')
  return {
    'asset': asset,
    'rows': len(rows),
    'frames': len(frames),
    'slides': len(slides),
    'transcript_error': transcript_error,
    'slide_error': slide_error,
    'source': transcript_source,
  }
