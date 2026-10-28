"""Re-encode a video in place to take less space without visible loss (user decision, 2026-10-28).

Measured on 5-minute clips of a Yanhekt lecture, at the source resolution, against the clip with VMAF: a 1080p screen
recording (H.264, 835 kbps) came to 20 % of its size at 10 frames a second with SVT-AV1 at CRF 40 (VMAF 96.8), and a
classroom camera recording (H.264, 1.75 Mbps) to 59 % at CRF 40 (VMAF 94.7); see ARCHITECTURE.md, "Compression". A
video already in AV1, HEVC or VP9, such as Bilibili's, is left alone: it gains little. The new file is written beside
the old one and replaces it only when its duration matches and it is smaller; the path stays the same, so the video's
processing folder and summaries still belong to it. A tag in the file marks it, so compressing again does nothing.
"""

import subprocess
from itertools import pairwise

from . import files, media

MARK = 'video-agent compressed'
CRF = 40
STILL_FPS = 10  # for a mostly still picture (a screen recording); moving pictures keep their frame rate
EFFICIENT = {'av1', 'hevc', 'vp9'}
AUDIO_KEEP_KBPS = 96  # AAC at or under this is copied; anything else becomes AAC at AUDIO_KBPS
AUDIO_KBPS = 64
DURATION_SLACK_S = 1.0
# Mostly still: in fewer than this share of the sampled seconds did more than ACTIVE of the picture change. The same
# measure layout.py uses to tell a screen from a camera picture.
STILL = 0.5
ACTIVE = 0.002
MOTION_LEVEL = 12
SAMPLE = (60, 600)  # seconds from the start, and how long, measured to tell


class CompressError(RuntimeError):
  pass


def _tags(info):
  return {key.lower(): value for key, value in ((info.get('format') or {}).get('tags') or {}).items()}


def skip_reason(info):
  """Why this video is not compressed, or None."""
  if MARK in _tags(info).get('comment', ''):
    return 'already compressed by Video Agent'
  video = next(stream for stream in info.get('streams') or [] if stream.get('codec_type') == 'video')  # probe checked
  if video.get('codec_name') in EFFICIENT:
    return f'already {video["codec_name"].upper()}, which gains little from compressing again'
  return None


def mostly_still(video, length):
  """Whether the picture hardly moves (a screen recording rather than a camera), from one grey frame a second."""
  start, span = SAMPLE if length > sum(SAMPLE) else (0, length)
  width, height = 64, 36
  command = [media.tool('ffmpeg'), '-v', 'error', '-ss', str(start), '-t', str(span), '-i', str(video), '-map', '0:v:0']
  command += ['-vf', f'fps=1,scale={width}:{height}:flags=area,format=gray', '-f', 'rawvideo', 'pipe:1']
  data = subprocess.run(command, capture_output=True, check=False).stdout
  size = width * height
  frames = [data[index : index + size] for index in range(0, len(data) - size + 1, size)]
  if len(frames) < 3:
    return False
  active = sum(
    sum(abs(a - b) > MOTION_LEVEL for a, b in zip(first, second)) > ACTIVE * size for first, second in pairwise(frames)
  )
  return active < STILL * (len(frames) - 1)


def _audio_options(info):
  audio = [stream for stream in info.get('streams') or [] if stream.get('codec_type') == 'audio']
  if not audio:
    return []
  rate = int(audio[0].get('bit_rate') or 0) // 1000
  if audio[0].get('codec_name') == 'aac' and 0 < rate <= AUDIO_KEEP_KBPS:
    return ['-c:a', 'copy']
  return ['-c:a', 'aac', '-b:a', f'{AUDIO_KBPS}k']


def compress(video, *, status=print):
  """Compresses the video in place. Returns {'video', 'skipped' (a reason or None), 'before', 'after', 'still'}."""
  video, info = media.probe(video)
  before = video.stat().st_size
  reason = skip_reason(info)
  if reason:
    status(f'{video.name}: not compressed: {reason}')
    return {'video': str(video), 'skipped': reason, 'before': before, 'after': before, 'still': None}
  length = media.duration(info)
  still = mostly_still(video, length)
  status(
    f'{video.name}: compressing ({"a still picture, " + str(STILL_FPS) + " frames a second" if still else "a moving picture"})'
  )
  setting = f'{MARK}: AV1 CRF {CRF}' + (f', {STILL_FPS} fps' if still else '')
  temporary = files.temporary_beside(video)  # keeps the extension, by which FFmpeg picks the container
  command = [media.tool('ffmpeg'), '-y', '-hide_banner', '-loglevel', 'error', '-stats', '-i', str(video)]
  command += ['-map', '0:v:0', '-map', '0:a?', '-map', '0:s?', '-map_metadata', '0']
  command += (['-vf', f'fps={STILL_FPS}'] if still else []) + ['-c:v', 'libsvtav1', '-preset', '8', '-crf', str(CRF)]
  command += _audio_options(info) + ['-c:s', 'copy', '-metadata', f'comment={setting}']
  if video.suffix.lower() in ('.mp4', '.m4v', '.mov'):
    command += ['-movflags', '+faststart']
  command.append(str(temporary))
  try:
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    if result.returncode or not temporary.is_file():
      tail = result.stderr.strip().splitlines()[-1:] or [str(result.returncode)]
      if 'libsvtav1' in result.stderr and 'Unknown encoder' in result.stderr:
        tail = ['this FFmpeg has no SVT-AV1 encoder (libsvtav1); the desktop installer ships one']
      raise CompressError(f'FFmpeg could not compress {video.name}: {tail[0]}')
    _, done = media.probe(temporary)
    after = temporary.stat().st_size
    if abs(media.duration(done) - length) > DURATION_SLACK_S:
      raise CompressError(f'the compressed copy of {video.name} lasts {media.duration(done):.1f}s, not {length:.1f}s')
    if after >= before:
      status(f'{video.name}: not replaced: the compressed copy is not smaller')
      return {'video': str(video), 'skipped': 'not smaller', 'before': before, 'after': before, 'still': still}
    files.replace(temporary, video)
  finally:
    temporary.unlink(missing_ok=True)
  status(f'{video.name}: {before / 1e6:.0f} MB -> {after / 1e6:.0f} MB ({after / before:.0%})')
  return {'video': str(video), 'skipped': None, 'before': before, 'after': after, 'still': still}
