"""Timed subtitle parsing, selection, and output."""

import re
import subprocess
from pathlib import Path

from . import files
from .media import MediaError, extract_audio, tool

ARROW = re.compile(
  r'(?P<start>(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{1,3})\s+-->\s+'
  r'(?P<end>(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{1,3})'
)


def parse_time(value):
  parts = value.replace(',', '.').split(':')
  seconds = float(parts[-1])
  minutes = int(parts[-2])
  hours = int(parts[-3]) if len(parts) == 3 else 0
  return hours * 3600 + minutes * 60 + seconds


def parse(text):
  text = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
  rows = []
  for block in re.split(r'\n[ \t]*\n', text.strip()):
    lines = block.splitlines()
    if not lines or lines[0].strip().upper() == 'WEBVTT' or lines[0].lstrip().startswith('NOTE'):
      continue
    for number, line in enumerate(lines[:2]):
      match = ARROW.search(line)
      if match:
        words = '\n'.join(lines[number + 1 :]).strip()
        if words:
          rows.append((parse_time(match['start']), parse_time(match['end']), words))
        break
  return sorted(rows, key=lambda row: (row[0], row[1]))


def _stamp(value, separator=','):
  millis = max(0, round(value * 1000))
  hours, millis = divmod(millis, 3_600_000)
  minutes, millis = divmod(millis, 60_000)
  seconds, millis = divmod(millis, 1000)
  return f'{hours:02}:{minutes:02}:{seconds:02}{separator}{millis:03}'


def format_clock(value):
  return _stamp(value, '')[:8]


def format_srt(rows):
  return ''.join(
    f'{number}\n{_stamp(start)} --> {_stamp(end)}\n{text.strip()}\n\n'
    for number, (start, end, text) in enumerate(rows, 1)
  )


def format_text(rows):
  lines = []
  for start, _, text in rows:
    lines.append(f'[{format_clock(start)}] {" ".join(text.split())}\n')
  return ''.join(lines)


# The language part of `clip.<language>.srt`, as yt-dlp names subtitle files: `zh-CN`, `en`, `ai-zh`, `zh-Hans`.
# Only language-like parts count, so `clip.part2.srt`, which belongs to `clip.part2.mp4`, is not taken for `clip.mp4`.
LANGUAGE_TAG = re.compile(r'(ai-)?[a-z]{2,3}([-_][a-z0-9]{2,8})*', re.IGNORECASE)


def _sidecar_language(video, path):
  """'' for `clip.srt`, the language for `clip.<language>.srt`, None for files that are not this video's."""
  name, prefix = path.name.casefold(), video.stem.casefold()
  if path.suffix.lower() not in ('.srt', '.vtt') or not name.startswith(prefix + '.'):
    return None
  language = path.name[len(prefix) + 1 : -len(path.suffix)]
  return language if language == '' or LANGUAGE_TAG.fullmatch(language) else None


def sidecar(video):
  """A subtitle file beside the video: `clip.srt` first, then Chinese, other human tracks, then AI ones (`ai-*`)."""
  video = Path(video)
  # Compared by name, not globbed: names such as `title [BV1xx].mp4` hold glob brackets.
  found = []
  for path in video.parent.iterdir():
    language = _sidecar_language(video, path)
    if language is not None and path.is_file():
      bare = language.casefold().removeprefix('ai-')
      found.append(((language != '', language.casefold().startswith('ai-'), not bare.startswith('zh'), language), path))
  for _, candidate in sorted(found):
    rows = parse(candidate.read_text(encoding='utf-8-sig'))
    if rows:
      return rows, f'sidecar:{candidate.name}'
  return None


def embedded(video, streams, output_dir):
  subtitle_streams = [stream for stream in streams if stream.get('codec_type') == 'subtitle']
  for stream in subtitle_streams:
    path = Path(output_dir) / '.embedded-subtitle.srt'
    command = [
      tool('ffmpeg'),
      '-y',
      '-hide_banner',
      '-loglevel',
      'error',
      '-i',
      str(video),
      '-map',
      f'0:{stream["index"]}',
      '-c:s',
      'srt',
      str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', check=False)
    if result.returncode == 0 and path.is_file():
      rows = parse(path.read_text(encoding='utf-8-sig', errors='replace'))
      path.unlink(missing_ok=True)
      if rows:
        language = (stream.get('tags') or {}).get('language', 'und')
        return rows, f'embedded:{language}'
    else:
      path.unlink(missing_ok=True)
  return None


def acquire(video, streams, output_dir, *, asr='none', allow_remote_asr=False, status=print):
  found = sidecar(video) or embedded(video, streams, output_dir)
  if found:
    return found
  if not any(stream.get('codec_type') == 'audio' for stream in streams):
    return [], 'no-audio-or-subtitles'
  if asr == 'none':
    raise MediaError(
      f'No sidecar or embedded subtitles found for {Path(video).name}. To transcribe with BCut, choose the remote '
      'provider and explicitly allow its upload: --asr bcut --allow-remote-asr. The extracted audio will be sent to Bilibili.'
    )
  if asr != 'bcut':
    raise MediaError(f'Unsupported ASR provider: {asr}')
  if not allow_remote_asr:
    raise MediaError('BCut sends extracted audio to Bilibili; add --allow-remote-asr only if you agree to that upload')
  from .providers import bcut

  audio = Path(output_dir) / '.audio-for-bcut.m4a'
  try:
    extract_audio(video, audio)
    try:
      rows = bcut.transcribe(audio, status)
    except bcut.BcutError as error:
      raise MediaError(f'BCut transcription failed: {error}') from error
    except Exception as error:
      raise MediaError(f'BCut transcription failed ({type(error).__name__})') from error
  finally:
    audio.unlink(missing_ok=True)
  return rows, 'bcut-remote'


def write(rows, output_dir, stem='transcript'):
  output_dir = Path(output_dir)
  output_dir.mkdir(parents=True, exist_ok=True)
  srt = output_dir / f'{stem}.srt'
  text = output_dir / f'{stem}.txt'
  files.write_text(srt, format_srt(rows))
  files.write_text(text, format_text(rows))
  return srt, text
