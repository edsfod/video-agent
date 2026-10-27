"""Freeze the CLI with PyInstaller into build/cli/video-agent/ (Python, ffmpeg and yt-dlp included).

Run from the repository root: uv run --with pyinstaller --with pillow python packaging/build_cli.py
The desktop installer ships this folder as resources/cli.
"""

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
    '--collect-data',
    'video_agent',  # prompts/summary.md
    '--collect-binaries',
    'imageio_ffmpeg',  # the bundled ffmpeg.exe
    '--collect-data',
    'imageio_ffmpeg',
    '--icon',
    str(ROOT / 'gui' / 'assets' / 'icon-256.png'),
  ],
  check=True,
)
print(OUT / 'video-agent' / 'video-agent.exe')
