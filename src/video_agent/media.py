"""FFmpeg and ffprobe operations for local video files."""

import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import files


class MediaError(RuntimeError):
  pass


PTS_TIME = re.compile(r'pts_time:([0-9]+(?:\.[0-9]+)?)')


def parse_clock(value):
  """Seconds from `70`, `1:10` or `00:01:10`; ValueError otherwise."""
  try:
    parts = [float(part) for part in str(value).strip().split(':')]
  except ValueError:
    raise ValueError(f'not a time: {value!r}; use seconds, MM:SS or HH:MM:SS') from None
  if not 1 <= len(parts) <= 3 or any(part < 0 for part in parts):
    raise ValueError(f'not a time: {value!r}; use seconds, MM:SS or HH:MM:SS')
  seconds = 0.0
  for part in parts:
    seconds = seconds * 60 + part
  return seconds


def clock_name(second):
  total = round(second)
  return f'{total // 3600:02}-{total % 3600 // 60:02}-{total % 60:02}'


def save_frame(video, asset, second, length):
  """Save one frame into `<asset>/frames/extra/`, refusing times outside the video."""
  if second < 0 or (length and second >= length):
    raise MediaError(f'{second:g}s is outside the video (0-{length:.1f}s)')
  return frame_at(video, second, Path(asset) / 'frames' / 'extra' / f'frame-{clock_name(second)}.jpg')


def tool(name):
  """ffmpeg or ffprobe: from PATH first, then the LGPL build frozen into the desktop installer's CLI, then (ffmpeg
  only) the copy that comes with imageio-ffmpeg in a pip or uv install. ffprobe may be None."""
  found = shutil.which(name)
  if found:
    return found
  bundled = Path(getattr(sys, '_MEIPASS', '')) / 'ffmpeg' / f'{name}.exe'
  if getattr(sys, 'frozen', False) and bundled.is_file():
    return str(bundled)
  if name == 'ffprobe':
    return None
  try:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()
  except (ImportError, RuntimeError) as error:
    raise MediaError(f'ffmpeg was not found on PATH and the bundled copy is unavailable ({error})') from error


STREAM = re.compile(
  r'^\s*Stream #0:(?P<index>\d+)(?:\[0x[0-9a-f]+\])?(?:\((?P<language>[^)]+)\))?: '
  r'(?P<type>Video|Audio|Subtitle|Data|Attachment): (?P<codec>[^\s,]+)',
  re.MULTILINE,
)
SIZE = re.compile(r', (?P<w>\d{2,5})x(?P<h>\d{2,5})[ ,]')
DURATION = re.compile(r'Duration: (?P<h>\d+):(?P<m>\d\d):(?P<s>\d\d(?:\.\d+)?)')


def _probe_with_ffmpeg(video):
  """The parts of ffprobe's JSON this package uses, read from ffmpeg's banner when ffprobe is missing."""
  result = subprocess.run(
    [tool('ffmpeg'), '-hide_banner', '-i', str(video)],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',
    check=False,
  )
  text = result.stderr
  if 'Input #0' not in text:
    raise MediaError(f'ffmpeg could not read {video.name}: {text.strip()[-500:]}')
  streams = []
  for match in STREAM.finditer(text):
    stream = {'index': int(match['index']), 'codec_type': match['type'].lower(), 'codec_name': match['codec']}
    if match['language']:
      stream['tags'] = {'language': match['language']}
    if stream['codec_type'] == 'video' and (size := SIZE.search(text, match.end(), text.find('\n', match.end()))):
      stream['width'], stream['height'] = int(size['w']), int(size['h'])
    streams.append(stream)
  info = {'streams': streams, 'format': {}}
  if found := DURATION.search(text):
    info['format']['duration'] = str(int(found['h']) * 3600 + int(found['m']) * 60 + float(found['s']))
  return info


def probe(video):
  video = Path(video).expanduser().resolve()
  if not video.is_file():
    raise MediaError(f'Video file does not exist: {video}')
  ffprobe = tool('ffprobe')
  if ffprobe is None:
    info = _probe_with_ffmpeg(video)
  else:
    result = subprocess.run(
      [ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(video)],
      capture_output=True,
      text=True,
      encoding='utf-8',
      errors='replace',
      check=False,
    )
    if result.returncode:
      raise MediaError(f'ffprobe could not read {video.name}: {result.stderr.strip() or result.returncode}')
    try:
      info = json.loads(result.stdout)
    except json.JSONDecodeError as error:
      raise MediaError(f'ffprobe returned invalid JSON for {video.name}') from error
  streams = info.get('streams') or []
  if not any(stream.get('codec_type') == 'video' for stream in streams):
    raise MediaError(f'No video stream found in {video.name}')
  return video, info


def frame_size(info):
  """Width and height of the first video stream, or (0, 0) when unknown."""
  stream = next((item for item in info.get('streams') or [] if item.get('codec_type') == 'video'), {})
  return int(stream.get('width') or 0), int(stream.get('height') or 0)


def duration(info):
  value = (info.get('format') or {}).get('duration')
  try:
    return max(0.0, float(value))
  except (TypeError, ValueError):
    return 0.0


def extract_audio(video, output):
  output = Path(output)
  output.parent.mkdir(parents=True, exist_ok=True)
  command = [
    tool('ffmpeg'),
    '-y',
    '-hide_banner',
    '-loglevel',
    'error',
    '-i',
    str(video),
    '-map',
    '0:a:0',
    '-vn',
    '-ac',
    '1',
    '-ar',
    '16000',
    '-c:a',
    'aac',
    '-b:a',
    '48k',
    str(output),
  ]
  result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
  if result.returncode or not output.is_file():
    raise MediaError(f'Could not extract audio from {Path(video).name}: {result.stderr.strip() or result.returncode}')
  return output


def frame_at(video, second, output, video_filter=None):
  """Saves through a unique temporary file, so two runs asking for the same second do not write one file at once."""
  output = Path(output)
  output.parent.mkdir(parents=True, exist_ok=True)
  final, output = output, files.temporary_beside(output)
  command = [
    tool('ffmpeg'),
    '-y',
    '-hide_banner',
    '-loglevel',
    'error',
    '-ss',
    f'{second:.3f}',
    '-i',
    str(video),
    '-map',
    '0:v:0',
    '-frames:v',
    '1',
    '-vf',
    video_filter or 'scale=1280:-2',
    '-q:v',
    '3',
    str(output),
  ]
  try:
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    if result.returncode or not output.is_file():
      raise MediaError(
        f'Could not save a frame at {second:g}s from {Path(video).name}: {result.stderr.strip() or result.returncode}'
      )
    files.replace(output, final)
  finally:
    output.unlink(missing_ok=True)
  return final


# metadata=mode=print writes only frames that carry metadata, which plain frames do not; this gives each one an entry.
STAMP = 'metadata=mode=add:key=video_agent:value=1,'


def _times(path):
  return [float(value) for value in PTS_TIME.findall(path.read_text(encoding='utf-8'))] if path.is_file() else []


def _run_ffmpeg(command, cwd, stdout_reader=None):
  """Runs FFmpeg with stderr in a file (it can be long) and, when given, a reader for its stdout."""
  log = Path(cwd) / 'ffmpeg.log'
  with log.open('wb') as errors:
    process = subprocess.Popen(
      command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if stdout_reader else None, stderr=errors
    )
    try:
      if stdout_reader:
        stdout_reader(process.stdout)
      code = process.wait()
    except BaseException:
      process.kill()
      process.wait()
      raise
  return code, log.read_text(encoding='utf-8', errors='replace').strip()


def sample_frames(video, output_dir, interval, scene_threshold, measure=None, sample_gap=30.0):
  """One decoding pass for the representative frames: one every `interval` seconds and the scene-change candidates,
  at 960 pixels wide. With `measure` (a layout.Measure), the same pass streams the grey copy the layout is read from:
  per second the changed share of each cell, and a plain frame every `sample_gap` seconds."""
  if interval <= 0:
    raise ValueError('Frame interval must be greater than zero')
  if not 0 < scene_threshold <= 1:
    raise ValueError('Scene threshold must be greater than 0 and at most 1')
  from . import layout

  output_dir = Path(output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  # select, not fps=1/N: FFmpeg 9's MJPEG encoder fails to open with fps=1/N when the video is shorter than about
  # 2N seconds, and fps also drops the last partial interval. Frame 0 joins the scene candidates so that output is
  # never empty (FFmpeg 7 and 9 fail on an output without frames); it is the same image as the first regular sample
  # and is merged away.
  branches = [
    (
      f"[p]select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{interval:g})',"
      f'{STAMP}metadata=mode=print:file=periodic.txt,scale=960:-2[periodic]'
    ),
    f"[s]select='gt(scene\\,{scene_threshold:g})+eq(n\\,0)',{STAMP}metadata=mode=print:file=scene.txt,scale=960:-2[scene]",
  ]
  outputs = [
    *('-map', '[periodic]', '-fps_mode', 'vfr', '-q:v', '4', 'periodic-%05d.jpg'),
    *('-map', '[scene]', '-fps_mode', 'vfr', '-q:v', '4', 'scene-%05d.jpg'),
  ]
  if measure:
    grey = f'scale={measure.width}:{measure.height}:flags=area,format=gray'
    branches += [
      (
        f"[m]fps=1,{grey},tblend=all_mode=difference,lut=y='if(gte(val\\,{layout.MOTION_LEVEL})\\,255\\,0)',"
        f'scale={measure.columns}:{measure.rows}:flags=area[motion]'
      ),
      f'[a]fps=1/{sample_gap:g},{grey}[samples]',
    ]
    outputs += [
      *('-map', '[motion]', '-f', 'rawvideo', 'pipe:1'),
      *('-map', '[samples]', '-f', 'rawvideo', 'samples.raw'),
    ]
  graph = f'[0:v:0]split={len(branches)}' + ''.join(f'[{branch[1]}]' for branch in branches) + ';' + ';'.join(branches)
  command = [tool('ffmpeg'), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(video), '-filter_complex', graph]

  def read(stream):
    while len(cells := stream.read(measure.cell_size)) == measure.cell_size:
      measure.feed(cells)

  code, errors = _run_ffmpeg([*command, *outputs], output_dir, read if measure else None)
  if code:
    raise MediaError(f'FFmpeg frame extraction failed for {Path(video).name}: {errors or code}')
  if measure and (samples := output_dir / 'samples.raw').is_file():
    data = samples.read_bytes()
    for start in range(0, len(data) - measure.size + 1, measure.size):
      measure.sample(data[start : start + measure.size])
  found = []
  for prefix in ('periodic', 'scene'):
    paths = sorted(output_dir.glob(f'{prefix}-*.jpg'))
    times = _times(output_dir / f'{prefix}.txt')
    if len(paths) != len(times):
      raise MediaError(f'FFmpeg returned {len(paths)} frames but {len(times)} timestamps for {Path(video).name}')
    found.append([{'time_s': second, 'path': path} for second, path in zip(times, paths)])
  return found[0], found[1]


# A screen page counts once the region stayed this long without a change: animations, scrolling and the transition
# between two slides settle first.
PAGE_STABLE_S = 2.0
# freezedetect's tolerance: the mean difference from the page's first frame over all colour planes, as a share of the
# largest possible. Measured with freezedetect itself (2026-10-28): a dark label covering 0.8 % of a white slide changes
# it by 0.003-0.004; on the first 400 s of a 97-minute lecture 0.004 found 10 stable periods, 0.003 12, 0.0025 14 and
# 0.002 17, where the quality jump at keyframes starts to count. Small extra candidates are merged or dropped later.
STILL = 0.0025
FREEZE_EVENT = re.compile(r'lavfi\.freezedetect\.freeze_(start|end)=([0-9.]+)')


def screen_pages(video, output_dir, region_filter, stable=PAGE_STABLE_S):
  """Pages of the screen region at the source resolution, from one frame per second. FFmpeg's freezedetect compares
  each frame with the first frame of the current page and marks the frame at which the region has stayed within STILL
  of it for `stable` seconds; only marked frames are kept, with the time the page first appeared. (mpdecimate, which
  did this before, is GPL-only and not in the LGPL FFmpeg the installer ships.)"""
  output_dir = Path(output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  # The first print logs every start and end (only those frames carry metadata), for how long each page stayed.
  graph = (
    f'{region_filter},fps=1,freezedetect=n={STILL}:d={stable:g},metadata=mode=print:file=events.txt,'
    'metadata=mode=select:key=lavfi.freezedetect.freeze_start,metadata=mode=print:file=pages.txt'
  )
  command = [tool('ffmpeg'), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(video), '-map', '0:v:0']
  command += ['-vf', graph, '-fps_mode', 'vfr', '-q:v', '2', 'page-%05d.jpg']
  code, errors = _run_ffmpeg(command, output_dir)
  paths = sorted(output_dir.glob('page-*.jpg'))
  log = output_dir / 'events.txt'
  events = (
    [(kind, float(value)) for kind, value in FREEZE_EVENT.findall(log.read_text(encoding='utf-8'))]
    if log.is_file()
    else []
  )
  starts = [value for kind, value in events if kind == 'start']
  if code or len(paths) != len(starts):
    raise MediaError(f'FFmpeg could not find screen pages in {Path(video).name}: {errors or code}')
  # A page lasts until the next end event; the last one may run to the end of the video.
  ends = iter([value for kind, value in events if kind == 'end'] + [math.inf] * len(starts))
  pages = [{'time_s': start, 'path': path, 'stayed_s': next(ends) - start} for start, path in zip(starts, paths)]
  return merge_similar(pages, output_dir)


# Pages whose small grey copies differ in fewer than this share of pixels show the same content: a pointer, a typed
# character, a pop-up, a highlighted line. Two slides in one template can differ in as little as 4 %.
SAME_PAGE = 0.025
THUMB = (128, 72)
SCROLL_NEW = 1 / 3  # a scroll that brings in less than this share of new lines leaves the same page
# A page shown for less than LONG_S counts only when most of it is new (another window, another slide); short pages
# with smaller changes are passing states, such as a terminal printing in bursts or a page being typed or scrolled.
LONG_S = 6.0
NEW_SCREEN = 0.5
RECENT = 8  # a page like one of the last RECENT kept pages is a return to it (switching windows), not a new page


def _differ(a, b, width, height, shift=0, columns=None):
  """The share of pixels that differ by more than 20 grey levels where `b`, moved up by `shift` rows, overlaps `a`;
  within `columns` (a range) when given."""
  x0, x1 = (columns.start, columns.stop) if columns else (0, width)
  rows = range(max(0, -shift), min(height, height - shift))
  changed = 0
  for y in rows:
    top, other = y * width, (y + shift) * width
    changed += sum(abs(x - z) > 20 for x, z in zip(a[top + x0 : top + x1], b[other + x0 : other + x1]))
  return changed / max(1, len(rows) * (x1 - x0))


def _scroll(a, b, width, height, columns):
  """How many rows `b` is scrolled against `a` within `columns`, matched on the rows' mean brightness."""
  limit = int(height * SCROLL_NEW)
  first = [sum(a[y * width + columns.start : y * width + columns.stop]) for y in range(height)]
  second = [sum(b[y * width + columns.start : y * width + columns.stop]) for y in range(height)]

  def cost(shift):
    rows = range(max(0, -shift), min(height, height - shift))
    return sum(abs(first[y] - second[y + shift]) for y in rows) / max(1, len(rows))

  return min(range(-limit, limit + 1), key=lambda shift: (cost(shift), abs(shift)))


def _scrolled(a, b, width, height):
  """Whether `b` is `a` with its text scrolled, as a whole or in its left and right halves separately (an editor
  beside a terminal), by less than SCROLL_NEW of the height."""
  halves = (range(width), range(width // 2), range(width // 2, width))
  for panes in ((halves[0],), halves[1:]):
    if all(
      _differ(a, b, width, height, 0, pane) < SAME_PAGE
      or _differ(a, b, width, height, _scroll(a, b, width, height, pane), pane) < SAME_PAGE
      for pane in panes
    ):
      return True
  return False


def merge_similar(pages, work_dir):
  """Drops pages that add little to the ones kept, comparing small grey copies:
  - the same page with small changes (bullets that appear one by one, a finished line of typing, a pop-up): the group
    keeps its first time and its last picture, which is the most complete;
  - the same text scrolled by less than SCROLL_NEW of the page, as a whole or in its left and right halves: the
    group keeps its picture;
  - a return to one of the last RECENT pages, as when switching between slides and a terminal: dropped;
  - a page shown for less than LONG_S that is not mostly new: dropped as a passing state.
  Comparing with the group's first page, not its latest, keeps slow typing and scrolling from drifting along."""
  if len(pages) < 2:
    return pages
  work_dir = Path(work_dir)
  listing = work_dir / 'thumbs.txt'
  listing.write_text(''.join(f"file '{page['path'].as_posix()}'\n" for page in pages), encoding='utf-8')
  width, height = THUMB
  command = [tool('ffmpeg'), '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing)]
  command += ['-vf', f'scale={width}:{height}:flags=area,format=gray', '-f', 'rawvideo', 'pipe:1']
  result = subprocess.run(command, capture_output=True, check=False)
  size = width * height
  if result.returncode or len(result.stdout) != size * len(pages):
    return pages  # keep them all rather than lose any
  thumbs = [result.stdout[index * size : (index + 1) * size] for index in range(len(pages))]

  merged, firsts = [], []  # kept pages, and the grey copy each group started with
  for page, thumb in zip(pages, thumbs):
    if firsts:
      first = firsts[-1]
      if _differ(first, thumb, width, height) < SAME_PAGE:
        merged[-1]['path'] = page['path']
        continue
      if _scrolled(first, thumb, width, height):
        continue
      if any(_differ(earlier, thumb, width, height) < SAME_PAGE for earlier in firsts[-RECENT - 1 : -1]):
        continue
      if page.get('stayed_s', math.inf) < LONG_S and _differ(first, thumb, width, height) < NEW_SCREEN:
        continue
    merged.append(dict(page))
    firsts.append(thumb)
  return merged


# Contact sheets of screen pages for models and chat AIs that take a limited number of images. Anthropic scales larger
# images down to about this width, so the tiles stay near the size of a typical screen region.
SHEET_WIDTH = 1568


def sheets(paths, side, output_dir, width=SHEET_WIDTH):
  """Pictures with `side` x `side` pages each, left to right then top to bottom; the last may have blank cells."""
  output_dir = Path(output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  listing = output_dir / 'sheets.txt'
  listing.write_text(''.join(f"file '{Path(path).as_posix()}'\n" for path in paths), encoding='utf-8')
  tile = (width - 6 * (side + 1)) // side // 2 * 2
  graph = f'scale={tile}:-2,tile={side}x{side}:padding=6:margin=6:color=white'
  command = [tool('ffmpeg'), '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', str(listing)]
  result = subprocess.run(
    [*command, '-vf', graph, '-q:v', '3', str(output_dir / 'sheet-%03d.jpg')],
    capture_output=True,
    text=True,
    encoding='utf-8',
    errors='replace',
    check=False,
  )
  found = sorted(output_dir.glob('sheet-*.jpg'))
  if result.returncode or len(found) != -(-len(paths) // (side * side)):
    raise MediaError(f'FFmpeg could not make contact sheets: {result.stderr.strip() or result.returncode}')
  return found


def layout_picture(video, second, layout, output):
  """A frame with the screen region outlined in green and the camera picture in red, to check the layout."""
  boxes = [(layout.screen, 'green'), (layout.camera, 'red')]
  drawn = ','.join(
    f'drawbox=x={x}:y={y}:w={w}:h={h}:color={colour}:t=4' for box, colour in boxes if box for x, y, w, h in [box]
  )
  return frame_at(video, second, output, video_filter=drawn or None)


def crop_video(video, output, region_filter):
  """The screen region as its own video, for AutoSlides Extractor, which looks at whole frames."""
  output = Path(output)
  command = [tool('ffmpeg'), '-y', '-hide_banner', '-loglevel', 'error', '-i', str(video), '-map', '0:v:0']
  # FFmpeg's own MPEG-4 encoder at high quality: the installer's LGPL FFmpeg has no x264.
  command += ['-vf', region_filter, '-c:v', 'mpeg4', '-q:v', '2', '-an', str(output)]
  result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
  if result.returncode or not output.is_file():
    raise MediaError(
      f'Could not crop the screen region of {Path(video).name}: {result.stderr.strip() or result.returncode}'
    )
  return output
