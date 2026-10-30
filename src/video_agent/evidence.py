"""A processed video's evidence as the summary routes use it: its folder and manifest, the 视频 line, and which pictures
go to a model or a chat AI within a number of images. Every screen page and frame goes, one per image or several on
a contact sheet when there are too many.
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
# (screen pages, frames) per row on contact sheets, tried in turn: 1 sends each alone; pages, which carry text, stay
# larger than frames.
LAYOUTS = ((1, 1), (1, 2), (2, 2), (2, 3), (3, 3))

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


def _thin(items, count):
  """`count` of the items, spread evenly."""
  return items if len(items) <= count else [items[int(index * len(items) / count)] for index in range(count)]


def plan(asset, manifest, budget, work_dir, source=None):
  """What goes into `budget` images: every screen page and every frame, each alone or on contact sheets, with the
  first of LAYOUTS that fits (user decision, 2026-10-30: frames thinned to fit the room left after the pages left 66 of
  a video's 115 pictures never sent, so never judged). Only when even 3x3 sheets do not fit are pictures left out,
  evenly: frames down to one sheet, then pages. Returns ('page' | 'sheet' | 'frame' | 'frame-sheet', file, [(second,
  relative)]) per image, (pages, frames) per row, and the number of pictures left out. `source(relative)` gives the
  file to use for a picture (default: the picture itself), such as a copy with a label printed on it."""
  source = source or (lambda relative: asset / relative)
  shown = pages(manifest)
  found = frames(asset, manifest, 10**6)
  every = len(shown) + len(found)

  def images(page_side, frame_side):
    return math.ceil(len(shown) / page_side**2) + math.ceil(len(found) / frame_side**2)

  sides = next((layout for layout in LAYOUTS if images(*layout) <= budget), LAYOUTS[-1])
  if images(*sides) > budget:
    per = sides[0] ** 2
    shown = _thin(shown, max(1, budget - min(len(found), 1)) * per)
    found = _thin(found, max(0, budget - math.ceil(len(shown) / per)) * sides[1] ** 2)
  chosen = []
  for kind, items, side in (('page', shown, sides[0]), ('frame', found, sides[1])):
    if side == 1:
      chosen += [(kind, source(relative), [(second, relative)]) for second, relative in items]
    elif items:
      per = side * side
      made = media.sheets([source(relative) for _, relative in items], side, Path(work_dir) / f'{kind}-sheets')
      chosen += [
        ('sheet' if kind == 'page' else 'frame-sheet', sheet, items[index * per : (index + 1) * per])
        for index, sheet in enumerate(made)
      ]
  return chosen, sides, every - len(shown) - len(found)


def evidence_images(asset, manifest, budget, work_dir):
  """(label, file) pairs within `budget` images, as `plan` chooses them, and the number of pictures left out."""
  chosen, sides, dropped = plan(asset, manifest, budget, work_dir)
  images = []
  first = {'sheet': 1, 'frame-sheet': 1}
  for kind, path, shown in chosen:
    if kind in first:
      listing = '; '.join(f'{clock(second)} {relative}' for second, relative in shown)
      last = first[kind] + len(shown) - 1
      what, side = ('Screen pages', sides[0]) if kind == 'sheet' else ('Frames', sides[1])
      label = f'{what} {first[kind]}-{last} on one sheet, {side} per row, left to right then top to bottom: {listing}'
      first[kind] = last + 1
    else:
      ((second, relative),) = shown
      label = f'{"Screen page" if kind == "page" else "Frame"} at {clock(second)}, file {relative}:'
    images.append((label, path))
  return images, dropped
