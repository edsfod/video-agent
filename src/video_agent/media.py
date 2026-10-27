"""FFmpeg and ffprobe operations for local video files."""

import json
import re
import shutil
import subprocess
from pathlib import Path


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
  """ffmpeg or ffprobe from PATH; ffmpeg falls back to the copy bundled with imageio-ffmpeg. ffprobe may be None."""
  found = shutil.which(name)
  if found or name == 'ffprobe':
    return found
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


def _extract_filter(video, output_dir, prefix, video_filter, *, allow_empty=False):
  output_dir = Path(output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  pattern = output_dir / f'{prefix}-%05d.jpg'
  command = [
    tool('ffmpeg'),
    '-y',
    '-hide_banner',
    '-loglevel',
    'info',
    '-i',
    str(video),
    '-map',
    '0:v:0',
    '-vf',
    video_filter,
    '-fps_mode',
    'vfr',
    '-q:v',
    '4',
    str(pattern),
  ]
  result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
  paths = sorted(output_dir.glob(f'{prefix}-*.jpg'))
  times = [float(value) for value in PTS_TIME.findall(result.stderr)]
  if result.returncode and not paths:
    # Nothing selected: older FFmpeg says the output has no stream; 7.x and 9.x fail to open the encoder after
    # "No filtered frames for output stream".
    stderr = result.stderr.lower()
    empty_selection = 'does not contain any stream' in stderr or 'no filtered frames for output stream' in stderr
    if allow_empty and empty_selection:
      return []
    raise MediaError(
      f'FFmpeg frame extraction failed for {Path(video).name}: {result.stderr.strip() or result.returncode}'
    )
  if not paths:
    return []
  if len(paths) != len(times):
    raise MediaError(f'FFmpeg returned {len(paths)} frames but {len(times)} timestamps for {Path(video).name}')
  return [{'time_s': second, 'path': path} for second, path in zip(times, paths)]


def frame_at(video, second, output):
  output = Path(output)
  output.parent.mkdir(parents=True, exist_ok=True)
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
    'scale=1280:-2',
    '-q:v',
    '3',
    str(output),
  ]
  result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
  if result.returncode or not output.is_file():
    raise MediaError(
      f'Could not save a frame at {second:g}s from {Path(video).name}: {result.stderr.strip() or result.returncode}'
    )
  return output


def periodic_frames(video, output_dir, interval):
  if interval <= 0:
    raise ValueError('Frame interval must be greater than zero')
  # select, not fps=1/N: FFmpeg 9's MJPEG encoder fails to open with fps=1/N when the video is shorter than about
  # 2N seconds, and fps also drops the last partial interval.
  value = f'{interval:g}'
  expression = f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{value})',showinfo,scale=960:-2"
  return _extract_filter(video, output_dir, 'periodic', expression)


def scene_frames(video, output_dir, threshold):
  if not 0 < threshold <= 1:
    raise ValueError('Scene threshold must be greater than 0 and at most 1')
  expression = f"select='gt(scene,{threshold})',showinfo,scale=960:-2"
  return _extract_filter(video, output_dir, 'scene', expression, allow_empty=True)
