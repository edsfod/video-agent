"""Writes THIRD-PARTY-NOTICES.txt for the desktop installer: each third-party component frozen into the CLI or shipped
beside it, with its version, licence and licence text (ARCHITECTURE.md, "Bundled FFmpeg"). build_cli.py calls it in
the build environment, whose installed packages are the ones PyInstaller freezes."""

import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASES = 'https://github.com/edsfod/video-agent/releases'
RULE = '=' * 100


def _canonical(name):
  return re.sub(r'[-_.]+', '-', name).lower()


def _runtime_distributions():
  """The project's runtime dependencies and theirs, without imageio-ffmpeg: its GPL ffmpeg.exe is left out of the
  installer, which carries the LGPL build instead."""
  found, todo = {}, ['video-agent']
  while todo:
    name = todo.pop()
    if _canonical(name) in found:
      continue
    try:
      dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
      continue  # an optional dependency that is not installed, so not frozen either
    found[_canonical(name)] = dist
    for requirement in dist.requires or []:
      if 'extra ==' not in requirement:
        todo.append(re.split(r'[\s;<>=!~\[(]', requirement, maxsplit=1)[0])
  for own in ('video-agent', 'imageio-ffmpeg'):
    found.pop(own, None)
  return sorted(found.values(), key=lambda dist: _canonical(dist.metadata['Name']))


def _licence_texts(dist):
  names = ('license', 'licence', 'copying', 'notice')
  files = [path for path in dist.files or [] if any(word in path.name.lower() for word in names)]
  return [(path.name, Path(dist.locate_file(path)).read_text(encoding='utf-8', errors='replace')) for path in files]


def _section(title, details, texts):
  parts = [RULE, title, RULE, *details, '']
  for name, text in texts:
    parts += [f'--- {name} ---', text.strip(), '']
  return '\n'.join(parts)


def write(target, ffmpeg_dir):
  ffmpeg_dir = Path(ffmpeg_dir)
  sections = [
    (
      'Video Agent is free software under the GNU AGPL 3.0 or later (LICENSE.txt). It ships the third-party software '
      'below; each section names a component, its version and licence, followed by the licence text.\n'
    )
  ]
  build = (ffmpeg_dir / 'BUILD.txt').read_text(encoding='utf-8').strip()
  sections.append(
    _section(
      'FFmpeg with dav1d and zlib: resources\\cli\\_internal\\ffmpeg\\ffmpeg.exe and ffprobe.exe',
      [
        build,
        '',
        'FFmpeg is licensed under the GNU Lesser General Public License 2.1 or later; this build has no GPL parts.',
        'dav1d is under the BSD 2-Clause licence, zlib under the zlib licence.',
        f'Complete corresponding source: each release at {RELEASES} carries the exact FFmpeg and dav1d source',
        'tarballs and FFmpeg-BUILD.txt; the build script is packaging/ffmpeg/build.sh in the source repository.',
      ],
      [
        (path.name, path.read_text(encoding='utf-8', errors='replace'))
        for path in sorted((ffmpeg_dir / 'licenses').iterdir())
      ],
    )
  )
  python_licence = Path(sys.base_prefix) / 'LICENSE.txt'
  sections.append(
    _section(
      f'Python {sys.version.split()[0]} (Python Software Foundation License, with the licences of the libraries it bundles)',
      [],
      [('LICENSE.txt', python_licence.read_text(encoding='utf-8', errors='replace'))],
    )
  )
  for dist in _runtime_distributions():
    licence = dist.metadata.get('License-Expression') or dist.metadata.get('License') or 'see the licence text'
    sections.append(
      _section(f'{dist.metadata["Name"]} {dist.version} ({licence.splitlines()[0]})', [], _licence_texts(dist))
    )
  pyinstaller = metadata.distribution('pyinstaller')
  sections.append(
    _section(
      f'PyInstaller {pyinstaller.version} bootloader (GPL 2.0 or later with the bootloader exception)',
      ['The exception allows distributing the frozen program under its own licence.'],
      _licence_texts(pyinstaller),
    )
  )
  sections.append(
    _section(
      'AutoSlides colour palette (Apache License 2.0, Copyright 2025 bit-admin)',
      [
        'The light and dark colour values of the window come from AutoSlides,',
        'https://github.com/bit-admin/Yanhekt-AutoSlides (src/renderer/shared/styles/theme.css).',
      ],
      [('LICENSE', (ROOT / 'packaging' / 'licenses' / 'AutoSlides-Apache-2.0.txt').read_text(encoding='utf-8'))],
    )
  )
  sections.append(
    _section(
      'Electron, Chromium and the JavaScript packages of the window',
      [
        'Electron and Chromium: LICENSE.electron.txt and LICENSES.chromium.html in the installation folder.',
        'Each JavaScript package carries its licence inside resources\\app.asar (node_modules\\<package>\\LICENSE).',
      ],
      [],
    )
  )
  Path(target).write_text('\n'.join(sections), encoding='utf-8', newline='\n')
  return target
