"""Freeze the CLI with PyInstaller into build/cli/video-agent/ (Python, ffmpeg and yt-dlp included).

Run from the repository root: uv run --with pyinstaller --with pillow python packaging/build_cli.py
The desktop installer ships this folder as resources/cli.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build' / 'cli'

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
    '--collect-binaries',
    'imageio_ffmpeg',  # the bundled ffmpeg.exe
    '--collect-data',
    'imageio_ffmpeg',
    '--icon',
    str(ROOT / 'gui' / 'assets' / 'icon-256.png'),
  ],
  check=True,
)
EXE = OUT / 'video-agent' / 'video-agent.exe'
# Fail here, not in the installer: the frozen CLI must start, find its template and run the bundled yt-dlp.
for args in (['template'], ['_yt-dlp', '--version']):
  subprocess.run([str(EXE), *args], check=True, capture_output=True)
print(EXE)
