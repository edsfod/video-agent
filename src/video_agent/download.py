"""Optional yt-dlp command-line adapter for downloading URLs to local files."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


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
  if importlib.util.find_spec('yt_dlp'):
    return [sys.executable, '-m', 'yt_dlp']
  raise DownloadError(
    'yt-dlp is not installed or not on PATH. Install its executable, set YT_DLP_EXECUTABLE, '
    'or pass --yt-dlp PATH. See https://github.com/yt-dlp/yt-dlp.'
  )


def _base_command(program, config):
  command = [*program, '--ignore-config']
  if config:
    command.extend(['--config-locations', str(config)])
  return command


def _is_playlist(program, url, config):
  command = [
    *_base_command(program, config),
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
  return isinstance(info, dict) and info.get('_type') in ('playlist', 'multi_video')


def download_urls(
  urls, output, *, format_selector='bv*+ba/b', playlist=False, executable_path=None, config_path=None, status=print
):
  program = executable(executable_path)
  output = Path(output).expanduser().resolve()
  output.mkdir(parents=True, exist_ok=True)
  config = Path(config_path).expanduser().resolve() if config_path else None
  if config is not None and not config.is_file():
    raise DownloadError(f'yt-dlp config file does not exist: {config}')
  template = output / '%(title)s [%(id)s].%(ext)s'
  downloaded, failed = [], 0

  for url in urls:
    if not playlist:
      try:
        if _is_playlist(program, url, config):
          status('yt-dlp: URL resolves to a playlist; pass --playlist to download its entries')
          failed += 1
          continue
      except DownloadError as error:
        status(f'yt-dlp: URL check failed: {error}')
        failed += 1
        continue
    command = [
      *_base_command(program, config),
      '--yes-playlist' if playlist else '--no-playlist',
      '--format',
      format_selector,
      '--output',
      str(template),
      '--print',
      'after_move:filepath',
      '--no-simulate',
      url,
    ]
    status('yt-dlp: starting download')
    process = None
    try:
      process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding='utf-8',
        errors='replace',
      )
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
      code = process.wait()
    except KeyboardInterrupt:
      if process is not None and process.poll() is None:
        process.terminate()
        process.wait()
      raise
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
