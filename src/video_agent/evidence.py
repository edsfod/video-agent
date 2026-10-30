"""A processed video's evidence as the summary routes use it: its folder and manifest, the 视频 line, and which pictures
go to a model or a chat AI within a number of images. Every screen page goes, one per image or several on a contact
sheet when there are too many; the representative and extra frames fill the room left.
"""

import json
import math
import re
from pathlib import Path

from . import media, pictures, processor
from .model_api import SummaryError
from .processor import asset_folder

SUMMARY_NAME = '总结.md'
EXTRA_NAME = re.compile(r'frame-(\d{2})-(\d{2})-(\d{2})\.jpg$')
SHEET_SIDES = (1, 2, 3)  # pages per row on a contact sheet; 1 sends each page alone
MIN_FRAMES = 8  # representative frames kept beside the pages, for the speaker and the room

# yt-dlp puts look-alike characters into file names for those Windows forbids; these two read as odd in a title.
FILENAME_LOOKALIKES = str.maketrans({'⧸': '/', '⧹': '\\'})


def video_name(video):
  """The title shown for a video: its file name without the extension, with `⧸` and `⧹` turned back into slashes."""
  return Path(video).stem.translate(FILENAME_LOOKALIKES)


def length_text(seconds):
  total = round(seconds)
  hours, rest = divmod(total, 3600)
  return f'{hours}:{rest // 60:02}:{rest % 60:02}' if hours else f'{rest // 60}:{rest % 60:02}'


def video_line(video, seconds):
  """The start of the summary's 视频 line; the name is plain text, so its brackets need no escaping."""
  return f'视频：{video_name(video)} · [打开视频](<{Path(video).as_posix()}>) · 时长：{length_text(seconds)}'


def clock(second):
  return media.clock_name(second).replace('-', ':')


def processed(video, workspace):
  """(video, probe info, folder, manifest) of a processed video, with its summary-context.md brought up to date."""
  video, info = media.probe(video)
  asset = asset_folder(workspace, video)
  manifest_path, context_path = asset / 'manifest.json', asset / 'summary-context.md'
  if not manifest_path.is_file() or not context_path.is_file():
    raise SummaryError(f'{video.name} has not been processed in {workspace}; run process with the same --output first')
  processor.update_context(asset)
  return video, info, asset, pictures.filtered(asset, json.loads(manifest_path.read_text(encoding='utf-8')))


def frames(asset, manifest, limit):
  frames = [(item['time_s'], item['path']) for item in manifest.get('representative_frames') or []]
  # The extra frames in the current set of pictures (pictures.filtered), or all of them for a manifest without it.
  extras = manifest.get('extra_frames')
  if extras is None:
    extras = [
      path.relative_to(asset).as_posix() for path in sorted((Path(asset) / 'frames' / 'extra').glob('frame-*.jpg'))
    ]
  for relative in extras:
    match = EXTRA_NAME.search(relative)
    if match:
      hours, minutes, seconds = (int(part) for part in match.groups())
      frames.append((hours * 3600 + minutes * 60 + seconds, relative))
  frames.sort()
  if len(frames) > limit:
    step = len(frames) / limit
    frames = [frames[int(index * step)] for index in range(limit)]
  return frames


def pages(manifest):
  """(time, path) of what was on screen: slides with a time when there are any, else the screen pages."""
  kind, items = processor.shown_pictures(manifest)
  return [] if kind == 'frame' else [(item['time_s'], item['path']) for item in items]


def plan(asset, manifest, budget, work_dir, source=None):
  """What goes into `budget` images: every screen page, alone or on 2x2 or 3x3 contact sheets when there are too
  many, then representative and extra frames in the room left (at least MIN_FRAMES where there are). Pages are
  dropped, evenly, only when even 3x3 sheets do not fit. Returns ('page' | 'sheet' | 'frame', file, [(second,
  relative)]) per image, pages per row, and the number of pages left out. `source(relative)` gives the file to use for
  a picture (default: the picture itself), such as a copy with a label printed on it."""
  source = source or (lambda relative: asset / relative)
  shown = pages(manifest)
  found = frames(asset, manifest, 10**6)
  room = max(1, budget - min(len(found), MIN_FRAMES))
  side = next((value for value in SHEET_SIDES if math.ceil(len(shown) / value**2) <= room), SHEET_SIDES[-1])
  per = side * side
  dropped = 0
  if math.ceil(len(shown) / per) > room:
    dropped = len(shown) - room * per
    step = len(shown) / (room * per)
    shown = [shown[int(index * step)] for index in range(room * per)]
  chosen = []
  if side == 1:
    chosen = [('page', source(relative), [(second, relative)]) for second, relative in shown]
  elif shown:
    for index, sheet in enumerate(media.sheets([source(relative) for _, relative in shown], side, work_dir)):
      chosen.append(('sheet', sheet, shown[index * per : (index + 1) * per]))
  left = max(0, budget - len(chosen))
  if len(found) > left:
    found = [found[int(index * len(found) / left)] for index in range(left)] if left else []
  chosen += [('frame', source(relative), [(second, relative)]) for second, relative in found]
  return chosen, side, dropped


def evidence_images(asset, manifest, budget, work_dir):
  """(label, file) pairs within `budget` images, as `plan` chooses them, and the number of pages left out."""
  chosen, side, dropped = plan(asset, manifest, budget, work_dir)
  images = []
  first = 1
  for kind, path, shown in chosen:
    if kind == 'sheet':
      listing = '; '.join(f'{clock(second)} {relative}' for second, relative in shown)
      last = first + len(shown) - 1
      label = f'Screen pages {first}-{last} on one sheet, {side} per row, left to right then top to bottom: {listing}'
      first = last + 1
    else:
      ((second, relative),) = shown
      label = f'{"Screen page" if kind == "page" else "Frame"} at {clock(second)}, file {relative}:'
    images.append((label, path))
  return images, dropped
