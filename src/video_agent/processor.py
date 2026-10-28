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

from . import corrections, files, layout, media, slide_extractor, transcript


def slug(value):
  """The video's name as a folder name: letters of any script, digits and `._-()` kept, the rest one `-`."""
  cleaned = re.sub(r'[^\w.()-]+', '-', value).strip('-. ')
  return cleaned[:64].rstrip('-. ') or 'video'


def _ascii_slug(value):
  """The name up to 0.8.3, which dropped every letter outside ASCII, so a Chinese title left little of itself."""
  cleaned = re.sub(r'[^A-Za-z0-9._-]+', '-', value).strip('-.')
  return cleaned[:64] or 'video'


def asset_folder(workspace, video):
  """The video's processing folder in the workspace. One made under the old name is renamed the first time it is
  asked for (user request, 2026-10-28), and the collection files that link into it follow; if the rename fails, as
  while another program has the folder open, the old name is used this time."""
  identity = hashlib.sha256(str(video).casefold().encode('utf-8')).hexdigest()[:10]
  workspace = Path(workspace)
  target = workspace / f'{slug(video.stem)}-{identity}'
  old = workspace / f'{_ascii_slug(video.stem)}-{identity}'
  if old != target and old.is_dir() and not target.exists():
    try:
      old.rename(target)
    except OSError:
      return old
    _relink_collections(workspace, old.name, target.name)
  return target


def _relink_collections(workspace, old, new):
  """Points the links of collection files (合集总结, 学习提纲 and their versions) at a renamed video folder."""
  for path in (workspace / '合集').glob('*/*.md'):
    text = path.read_text(encoding='utf-8')
    if f'/{old}/' in text:
      files.write_text(path, text.replace(f'/{old}/', f'/{new}/'))


def _write_json(path, value):
  files.write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + '\n')


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


# Runaway limits, not targets (AGENTS.md): the frames follow the video, and reaching a limit is reported.
MAX_FRAMES = 500
MAX_PAGES = 500

LAYOUT_TEXT = {
  'screen': 'the whole frame is a screen recording',
  'split': 'a screen region beside a camera picture',
  'inset': 'a camera picture inside the screen (blacked out when looking for pages)',
  'camera': 'a camera picture only; no screen pages are looked for',
}


def _context(manifest, rows):
  """summary-context.md from the manifest and the transcript rows in use."""

  def link(path):
    return quote(path, safe='/-._~')

  told = manifest['transcript']
  lines = [
    '# Video summary context',
    '',
    (
      'This is source evidence, not a generated summary. Write the summary from the transcript, the screen pages and '
      'the frames, following the rules and template printed by `video-agent template`.'
    ),
    '',
    f'- Source: `{manifest["source_video"]}`',
    f'- Duration: {manifest["duration_s"]:.1f} seconds',
    f'- Transcript source: {told["source"]}',
  ]
  if told.get('clean'):
    lines.append(
      f'- Transcript: cleaned with {told["corrections"]} corrections (`{told["clean"]}`); the original is `transcript.srt`'
    )
  kind = (manifest.get('layout') or {}).get('kind')
  if kind:
    lines.append(f'- Layout: {LAYOUT_TEXT[kind]}')
  if told.get('error'):
    lines.extend(['', f'- Transcript status: {told["error"]}'])
  lines.extend(['', '## Transcript', ''])
  # Each run of lines starts with the screen page then on screen (or, without pages, the frame), so whoever writes the
  # summary links the picture of the point it describes without matching times itself (user, 2026-10-28; yanhe-agent's
  # `query` did the same).
  kind, pictures = shown_pictures(manifest)
  if pictures:
    lines.append(f'{GROUPED} {kind} on screen while they were said; link that picture for their points.')
    lines.append('')
  marks = sorted(pictures, key=lambda item: item['time_s'])

  def mark(item):
    lines.extend(
      [''] * (lines[-1] != '') + [f'▶ {kind} from {transcript.format_clock(item["time_s"])}: {link(item["path"])}', '']
    )

  if rows:
    shown = 0
    for start, _, text in rows:
      while shown < len(marks) and marks[shown]['time_s'] <= start + 0.5:
        mark(marks[shown])
        shown += 1
      lines.append(f'[{transcript.format_clock(start)}] {" ".join(text.split())}')
    for item in marks[shown:]:  # shown after the last words
      mark(item)
  else:
    lines.append('(No speech transcript was available.)')
  lines.extend(['', '## Representative frames', ''])
  frames = manifest.get('representative_frames') or []
  lines.extend(f'- {item["time_s"]:.1f}s: ![frame]({link(item["path"])})' for item in frames)
  if not frames:
    lines.append('(No representative frames were extracted.)')
  pages = manifest.get('screen_pages') or []
  if pages:
    lines.extend(
      [
        '',
        '## Screen pages',
        '',
        (
          'Each distinct page shown in the screen region (slides, code, documents), at the source resolution, '
          'with the time it first appeared; the transcript above marks where each comes on screen.'
        ),
        '',
      ]
    )
    lines.extend(f'- {item["time_s"]:.1f}s: ![page]({link(item["path"])})' for item in pages)
  slides = (manifest.get('slide_extraction') or {}).get('slides') or []
  if slides:
    lines.extend(['', '## Extracted slides', ''])
    for item in slides:
      time_text = f'{item["time_s"]:.1f}s' if item['time_s'] is not None else 'time unavailable'
      lines.append(f'- {time_text}: ![slide]({link(item["path"])})')
  lines.append('')
  return '\n'.join(lines)


SLIDE_MATCH = 0.3  # a slide without a time takes the time of the screen page it differs from in less than this share


def _place_slides(slides, pages, work_dir):
  """Gives slides without a time (a folder without AutoSlides' timeline) the time of the screen page they look like."""
  untimed = [slide for slide in slides if slide['time_s'] is None]
  if not untimed or not pages:
    return slides
  page_thumbs = media._thumbnails(pages, Path(work_dir))
  slide_thumbs = media._thumbnails(untimed, Path(work_dir))
  if page_thumbs is None or slide_thumbs is None:
    return slides
  width, height = media.THUMB
  for slide, thumb in zip(untimed, slide_thumbs):
    share, page = min((media._differ(thumb, other, width, height), page) for other, page in zip(page_thumbs, pages))
    if share < SLIDE_MATCH:
      slide['time_s'] = page['time_s']
  return slides


def shown_pictures(manifest):
  """What was on screen, by time: slides with a time when there are any (AutoSlides' are filtered and cropped), else
  the screen pages, else the representative frames. Returns their kind and [{time_s, path}]."""
  slides = [item for item in (manifest.get('slide_extraction') or {}).get('slides') or [] if item['time_s'] is not None]
  if slides:
    return 'slide', sorted(slides, key=lambda item: item['time_s'])
  if manifest.get('screen_pages'):
    return 'screen page', manifest['screen_pages']
  return 'frame', manifest.get('representative_frames') or []


def refresh_transcript(asset):
  """After corrections changed: rebuilds the cleaned transcript, records it in the manifest and rewrites the context.
  Returns the changed lines. The caller holds the video's lock."""
  from . import corrections

  asset = Path(asset)
  changes = corrections.rebuild(asset)
  manifest_path = asset / 'manifest.json'
  manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
  told = manifest['transcript']
  manifest['transcript'] = transcript_entry(asset, told['source'], told['segments'], told.get('error'))
  _write_json(manifest_path, manifest)
  write_context(asset)
  return changes


GROUPED = 'Lines are grouped by the'


def update_context(asset):
  """Rewrites a summary-context.md written before its transcript marked the picture on screen (0.8.3 and earlier),
  so videos processed then get the new form without processing again. Takes the video's lock."""
  asset = Path(asset)
  context = asset / 'summary-context.md'
  if (asset / 'manifest.json').is_file() and context.is_file() and GROUPED not in context.read_text(encoding='utf-8'):
    with files.video_lock(asset, 'context'):
      write_context(asset)


def write_context(asset):
  """Writes summary-context.md from the manifest and the transcript in use (the cleaned one when there is one), so a
  cleaned transcript reaches every summary route without processing the video again."""
  asset = Path(asset)
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  files.write_text(asset / 'summary-context.md', _context(manifest, corrections.rows_in_use(asset) or []))


def transcript_entry(asset, source, segments, error):
  """The manifest's transcript entry, with the cleaned transcript if there is one."""
  asset = Path(asset)
  clean = asset / f'{corrections.CLEAN}.srt'
  return {
    'source': source,
    'segments': segments,
    'error': error or None,
    'srt': 'transcript.srt' if (asset / 'transcript.srt').is_file() else None,
    'clean': clean.name if clean.is_file() else None,
    'corrections': len(corrections.all_pairs(asset)),
  }


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
  max_frames=None,
  screen_region=None,
  extract_slides=False,
  slide_extractor_path=None,
  asr='none',
  allow_remote_asr=False,
  overwrite=False,
  subtitles=None,
  slides_folder=None,
  status=print,
):
  video, info = media.probe(video)
  asset = asset_folder(workspace, video)
  with files.video_lock(asset, 'process'):
    return _process_locked(
      video,
      info,
      asset,
      interval=interval,
      scene_threshold=scene_threshold,
      max_frames=max_frames,
      screen_region=screen_region,
      extract_slides=extract_slides,
      slide_extractor_path=slide_extractor_path,
      asr=asr,
      allow_remote_asr=allow_remote_asr,
      overwrite=overwrite or bool(subtitles),
      subtitles=subtitles,
      slides_folder=slides_folder,
      status=status,
    )


def _process_locked(
  video,
  info,
  asset,
  *,
  interval,
  scene_threshold,
  max_frames,
  screen_region,
  extract_slides,
  slide_extractor_path,
  asr,
  allow_remote_asr,
  overwrite,
  subtitles,
  slides_folder,
  status,
):
  status(f'{video.name}: {media.duration(info):.1f}s, {len(info.get("streams") or [])} streams')

  frame_run = datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
  frames_dir = asset / 'frames' / frame_run
  width, height = media.frame_size(info)
  length = media.duration(info)
  # The layout is read during the sampling pass; a region given by hand, or a video too short to tell, skips that.
  measure = None
  if screen_region is None and width and height and length >= 10:
    measure = layout.Measure(*layout.grid_size(width, height))
  status(f'{video.name}: sampling frames every {interval:g}s and at scene changes, and reading the layout')
  slide_result, slide_error = None, ''
  with tempfile.TemporaryDirectory(prefix='video-agent-') as temporary:
    temporary = Path(temporary)
    periodic, scenes = media.sample_frames(
      video, temporary / 'samples', interval, scene_threshold, measure, sample_gap=max(10.0, length / 120)
    )
    frame_candidates = _unique(periodic + scenes)
    frame_limit = max_frames or MAX_FRAMES
    if len(frame_candidates) > frame_limit:
      status(
        f'{video.name}: {len(frame_candidates)} representative frames; keeping {frame_limit} spread over the video'
      )
    frames = _copy_candidates(_bounded(frame_candidates, frame_limit), frames_dir, 'frame')

    if screen_region:
      found = layout.from_region(screen_region, width, height)
    elif measure:
      found = layout.to_source(layout.analyse(measure), width, height)
    else:
      found = layout.Layout('screen', width, height, [0, 0, width, height])
    region = found.page_filter()
    where = f' {found.screen[2]}x{found.screen[3]} at {found.screen[0]},{found.screen[1]}' if region else ''
    status(f'{video.name}: layout: {LAYOUT_TEXT[found.kind]}{where}')
    picture = frames_dir / 'layout.jpg'
    try:
      media.layout_picture(video, length / 2, found, picture)
    except media.MediaError:
      picture = None

    pages, pages_found, shown_s = [], 0, None
    if region:
      status(f'{video.name}: looking for screen pages')
      page_candidates, shown_s = media.screen_pages(video, temporary / 'pages', region, duration_s=length)
      pages_found = len(page_candidates)
      if pages_found > MAX_PAGES:
        status(f'{video.name}: {pages_found} screen pages; keeping {MAX_PAGES} spread over the video')
      pages = _copy_candidates(_bounded(page_candidates, MAX_PAGES), frames_dir / 'screen', 'page')
      status(f'{video.name}: {len(pages)} screen pages')

    if extract_slides:
      try:
        source = video
        if found.kind in ('split', 'inset'):
          # AutoSlides Extractor compares whole frames; give it the screen region alone.
          status(f'{video.name}: cropping the screen region for AutoSlides Extractor')
          source = media.crop_video(video, temporary / 'screen.mp4', region)
        slide_result = slide_extractor.extract(
          source,
          asset / 'slide-extraction',
          executable=slide_extractor_path,
          status=lambda message: status(f'{video.name}: {message}'),
        )
      except (slide_extractor.SlideExtractorError, media.MediaError) as error:
        slide_error = str(error)
        status(f'{video.name}: slide extraction failed: {slide_error}')

    # Slides made already: a folder the user chose, or the one AutoSlides keeps beside a screen recording it downloaded.
    imported = None if slide_result else slides_folder or slide_extractor.autoslides_folder(video)
    if imported:
      try:
        slide_result = slide_extractor.import_folder(imported, asset / 'slides')
        status(f'{video.name}: {len(slide_result["slides"])} slides from {Path(imported).name}')
        slide_result['slides'] = _place_slides(slide_result['slides'], pages, temporary)
      except slide_extractor.SlideExtractorError as error:
        slide_error = str(error)
        status(f'{video.name}: slides not taken: {slide_error}')

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
        subtitles=subtitles,
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
  # A transcript taken again (--overwrite-transcript) gets its corrections again.
  corrections.rebuild(asset)
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
    'transcript': transcript_entry(asset, transcript_source, len(rows), transcript_error),
    'representative_frame_run': str(frames_dir.relative_to(asset)),
    'layout': {
      **found.as_manifest(),
      'picture': picture.relative_to(asset).as_posix() if picture else None,
      'given': bool(screen_region),
    },
    'screen_pages': [{'time_s': item['time_s'], 'path': item['path'].relative_to(asset).as_posix()} for item in pages],
    'limits': {
      'frames': frame_limit,
      'frames_found': len(frame_candidates),
      'pages': MAX_PAGES,
      'pages_found': pages_found,
      'page_shown_at_least_s': shown_s,  # tuned towards media.PAGES_PER_HOUR
    },
    'representative_frames': [
      {'time_s': item['time_s'], 'path': item['path'].relative_to(asset).as_posix()} for item in frames
    ],
    'slide_extraction': {
      'enabled': bool(extract_slides),
      'imported': str(imported) if imported else None,
      'output': str(slide_result['output_root'].relative_to(asset)) if slide_result else None,
      'timeline': str(slide_result['timeline'].relative_to(asset)) if slide_result else None,
      'error': slide_error or None,
      'slides': [{'time_s': item['time_s'], 'path': item['path'].relative_to(asset).as_posix()} for item in slides],
    },
    'summary_context': 'summary-context.md',
    'summary_generated': False,
  }
  _write_json(asset / 'manifest.json', manifest)
  write_context(asset)
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
