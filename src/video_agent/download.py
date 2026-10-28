"""Optional yt-dlp command-line adapter for downloading URLs to local files."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import media


class DownloadError(RuntimeError):
  pass


def executable(explicit=None):
  if explicit:
    candidate = Path(explicit).expanduser()
    if candidate.is_file():
      return [str(candidate.resolve())]
    if found := shutil.which(str(explicit)):
      return [found]
    raise DownloadError(f'yt-dlp executable not found: {explicit}')
  if configured := os.environ.get('YT_DLP_EXECUTABLE'):
    candidate = Path(configured).expanduser()
    if candidate.is_file():
      return [str(candidate.resolve())]
    if found := shutil.which(configured):
      return [found]
    raise DownloadError(f'YT_DLP_EXECUTABLE does not point to an executable: {configured}')
  for name in ('yt-dlp', 'yt-dlp.exe'):
    if found := shutil.which(name):
      return [found]
  if os.name == 'nt':
    for variable in ('APPDATA', 'LOCALAPPDATA'):
      if root := os.environ.get(variable):
        managed = Path(root) / 'media-downloader' / 'bin' / 'yt-dlp.exe'
        if managed.is_file():
          return [str(managed.resolve())]
  # The yt-dlp installed with this package. A frozen build has no `python -m`, so it runs through `video-agent _yt-dlp`.
  if importlib.util.find_spec('yt_dlp'):
    return [sys.executable, '_yt-dlp'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'yt_dlp']
  raise DownloadError(
    'yt-dlp is not installed or not on PATH. Install its executable, set YT_DLP_EXECUTABLE, '
    'or pass --yt-dlp PATH. See https://github.com/yt-dlp/yt-dlp.'
  )


# Subtitle tracks saved beside the video, where `process` finds them. Danmaku (Bilibili comments) and live chat are
# not subtitles. Bilibili lists its subtitles, including the AI ones, only to a logged-in account (pass --cookies).
SUBTITLE_LANGS = 'all,-danmaku,-live_chat'

# Windows file names cannot hold / or \. yt-dlp puts look-alike maths symbols there (⧸ ⧹), which read oddly; the
# user chose a plain _ instead (2026-10-28), not the fullwidth forms.
TITLE_FIXES = ['--replace-in-metadata', 'title', r'[/\\]', '_']

# Entry titles reported for a list found without --playlist, so a front end can show what it would download.
LIST_TITLES = 5


def _base_command(program, config, cookies):
  # yt-dlp looks for ffmpeg only on PATH; point it at ours so separate video and audio streams get merged.
  command = [*program, '--ignore-config', '--ffmpeg-location', media.tool('ffmpeg')]
  if config:
    command.extend(['--config-locations', str(config)])
  if cookies:
    command.extend(['--cookies', str(cookies)])
  return command


def _list_info(program, url, config, cookies):
  """The list a URL stands for even without --playlist (a series, a season, a channel), or None for one video."""
  command = [
    *_base_command(program, config, cookies),
    '--no-playlist',
    '--flat-playlist',
    '--dump-single-json',
    '--skip-download',
    url,
  ]
  result = subprocess.run(
    command,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=None,
    text=True,
    encoding='utf-8',
    errors='replace',
    check=False,
  )
  if result.returncode:
    raise DownloadError(f'yt-dlp could not inspect a URL (exit status {result.returncode})')
  try:
    info = json.loads(result.stdout)
  except json.JSONDecodeError as error:
    raise DownloadError('yt-dlp returned invalid JSON while checking whether the URL is a playlist') from error
  if not isinstance(info, dict) or info.get('_type') not in ('playlist', 'multi_video'):
    return None
  entries = [entry for entry in info.get('entries') or [] if isinstance(entry, dict)]
  return {
    'url': url,
    'title': info.get('title') or '',
    'count': info.get('playlist_count') or len(entries),
    'titles': [entry['title'] for entry in entries if entry.get('title')][:LIST_TITLES],  # Bilibili lists give none
  }


def _run(command, output):
  """Runs one yt-dlp download; returns its exit code and the saved video paths it printed."""
  process = subprocess.Popen(
    command,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=None,
    text=True,
    encoding='utf-8',
    errors='replace',
  )
  try:
    assert process.stdout is not None
    paths = []
    for line in process.stdout:
      value = line.strip()
      if not value:
        continue
      candidate = Path(value)
      if not candidate.is_absolute():
        candidate = output / candidate
      if candidate.is_file():
        paths.append(candidate.resolve())
    return process.wait(), paths
  except KeyboardInterrupt:
    if process.poll() is None:
      process.terminate()
      process.wait()
    raise


def download_urls(
  urls,
  output,
  *,
  format_selector='bv*+ba/b',
  playlist=False,
  subtitles=True,
  executable_path=None,
  config_path=None,
  cookies_path=None,
  status=print,
  found_list=None,
):
  """Downloads each URL; a URL that stands for a list without `playlist` is skipped and passed to `found_list`."""
  program = executable(executable_path)
  output = Path(output).expanduser().resolve()
  output.mkdir(parents=True, exist_ok=True)
  config = Path(config_path).expanduser().resolve() if config_path else None
  if config is not None and not config.is_file():
    raise DownloadError(f'yt-dlp config file does not exist: {config}')
  cookies = Path(cookies_path).expanduser().resolve() if cookies_path else None
  if cookies is not None and not cookies.is_file():
    raise DownloadError(f'cookies file does not exist: {cookies}')
  template = output / '%(title)s [%(id)s].%(ext)s'
  downloaded, failed = [], 0

  for url in urls:
    if not playlist:
      try:
        found = _list_info(program, url, config, cookies)
        if found:
          status(f'yt-dlp: URL is a list of {found["count"]} videos; pass --playlist to download its entries')
          if found_list:
            found_list(found)
          failed += 1
          continue
      except DownloadError as error:
        status(f'yt-dlp: URL check failed: {error}')
        failed += 1
        continue
    command = [
      *_base_command(program, config, cookies),
      '--yes-playlist' if playlist else '--no-playlist',
      '--format',
      format_selector,
      *TITLE_FIXES,
      '--output',
      str(template),
      '--print',
      'after_move:filepath',
      '--no-simulate',
      url,
    ]
    subtitle_options = ['--write-subs', '--sub-langs', SUBTITLE_LANGS] if subtitles else []
    status('yt-dlp: starting download' + (' with subtitles' if subtitles else ''))
    try:
      code, paths = _run([*command[:-1], *subtitle_options, url], output)
      # yt-dlp gives up the whole video when a subtitle request fails, so try once more without subtitles.
      if code != 0 and not paths and subtitles:
        status('yt-dlp: download failed; retrying without subtitles')
        code, paths = _run(command, output)
    except OSError as error:
      status(f'yt-dlp: could not run ({type(error).__name__})')
      failed += 1
      continue

    downloaded.extend(paths)
    if code != 0:
      status(f'yt-dlp: download failed with exit status {code}')
      failed += 1
    elif not paths:
      status('yt-dlp: finished without reporting a saved video path')
      failed += 1
    else:
      for path in paths:
        status(f'Downloaded: {path}')
  return downloaded, failed
