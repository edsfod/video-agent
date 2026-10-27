"""Freeze the CLI with PyInstaller into build/cli/video-agent/ (Python, yt-dlp and the LGPL FFmpeg included).

Run from the repository root: uv run --with pyinstaller --with pillow python packaging/build_cli.py
The desktop installer ships this folder as resources/cli. FFmpeg comes from build/ffmpeg/, built by
packaging/ffmpeg/build.sh (CI artifact `ffmpeg-lgpl`); imageio-ffmpeg and its GPL ffmpeg.exe are left out.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build' / 'cli'
FFMPEG = ROOT / 'build' / 'ffmpeg'
if not (FFMPEG / 'bin' / 'ffmpeg.exe').is_file():
  sys.exit(
    'build/ffmpeg/ is missing. The installer ships the LGPL FFmpeg from packaging/ffmpeg/build.sh: download the '
    '`ffmpeg-lgpl` artifact of a CI run (gh run download <run id> -n ffmpeg-lgpl -D build/ffmpeg) or run the script '
    'in an MSYS2 UCRT64 shell.'
  )

subprocess.run(
  [
    sys.executable,
    '-m',
    'PyInstaller',
    str(ROOT / 'packaging' / 'entry.py'),
    '--name',
    'video-agent',
    '--onedir',
    '--console',
    '--noconfirm',
    '--clean',
    '--distpath',
    str(OUT),
    '--workpath',
    str(OUT / 'work'),
    '--specpath',
    str(OUT / 'work'),
    # From the source tree, not by import: in a fresh `uv run --with` environment the build interpreter cannot import
    # the editable project, so PyInstaller would leave out both the package and its data.
    '--paths',
    str(ROOT / 'src'),
    '--add-data',
    f'{ROOT / "src" / "video_agent" / "prompts"}{os.pathsep}video_agent/prompts',
    '--exclude-module',
    'imageio_ffmpeg',  # its ffmpeg.exe is a GPL build; media.tool finds the LGPL one under ffmpeg/
    '--add-binary',
    f'{FFMPEG / "bin" / "ffmpeg.exe"}{os.pathsep}ffmpeg',
    '--add-binary',
    f'{FFMPEG / "bin" / "ffprobe.exe"}{os.pathsep}ffmpeg',
    '--icon',
    str(ROOT / 'gui' / 'assets' / 'icon-256.png'),
  ],
  check=True,
)
EXE = OUT / 'video-agent' / 'video-agent.exe'
# Fail here, not in the installer: the frozen CLI must start, find its template and run the bundled yt-dlp ...
for args in (['template'], ['_yt-dlp', '--version']):
  subprocess.run([str(EXE), *args], check=True, capture_output=True)

# ... and process a video and pack it with nothing but its own FFmpeg, which exercises every filter it uses.
work = OUT / 'smoke'
shutil.rmtree(work, ignore_errors=True)
work.mkdir(parents=True)
clip = work / 'clip.mp4'
# Test picture and sound from filter sources: the LGPL build has no lavfi input device (--disable-devices).
subprocess.run(
  [
    str(FFMPEG / 'bin' / 'ffmpeg.exe'),
    *('-v', 'error', '-filter_complex', 'testsrc=size=320x180:rate=5:duration=12[v];sine=duration=12[a]'),
    *('-map', '[v]', '-map', '[a]', '-c:v', 'mpeg4', '-c:a', 'aac', str(clip)),
  ],
  check=True,
)
alone = {**os.environ, 'PATH': os.environ.get('SystemRoot', r'C:\Windows') + r'\System32'}
for args in (
  ['process', str(clip), '-o', str(work / 'out')],
  ['pack', str(clip), '-o', str(work / 'out'), '--zip', str(work / 'm.zip')],
):
  result = subprocess.run(
    [str(EXE), *args], check=False, env=alone, capture_output=True, text=True, encoding='utf-8', errors='replace'
  )
  if result.returncode not in (0, 1):  # 1: the clip has no subtitles, which process reports
    sys.exit(f'frozen CLI failed: {args[0]}\n{result.stdout}\n{result.stderr}')
manifest = next((work / 'out').glob('*/manifest.json'))
if '"screen_pages"' not in manifest.read_text(encoding='utf-8'):
  sys.exit('frozen CLI wrote no screen pages')
shutil.rmtree(work)

sys.path.insert(0, str(ROOT / 'packaging'))
from notices import write

print(write(OUT / 'video-agent' / 'THIRD-PARTY-NOTICES.txt', FFMPEG))
print(EXE)
