"""The 画面调整 section a chat AI writes at the end of a summary, since it cannot look at the video itself: pictures it
does not need (stock footage, the speaker, a blank screen), which are not offered to anyone again, and spans in which
it misses a picture, in which the import takes a few different candidates for the next round (`pack --follow-up`) to
choose from. The state between rounds is in picture-review.json in the video's folder.
"""

import json
import re
from pathlib import Path
from urllib.parse import unquote

from . import files, media, page_rules

HEADING = '画面调整'
SECTION = re.compile(rf'^##\s*{HEADING}\s*\n(.*?)(?=^##\s|\Z)', re.MULTILINE | re.DOTALL)
CLOCK = r'(?:\d{1,2}:)?\d{1,2}:\d{2}'
UNUSED = re.compile(r'^\s*[-*]?\s*不用\s*[:：]\s*(.+)$')
WANTED = re.compile(
  rf'^\s*[-*]?\s*补截\s*[:：]\s*`?({CLOCK})`?(?:\s*[-–—~～至到]+\s*`?({CLOCK})`?)?\s*[:：，,]?\s*(.*)$'
)
PATH = re.compile(r'frames/[^\s`()（）<>，,；;]+?\.(?:jpe?g|png)', re.IGNORECASE)
NAME = 'picture-review.json'
CANDIDATES = 4  # different pictures taken for one span
SPAN_S = 10.0  # a request for one moment looks at what is shown from then on for this long


def _clock(second):
  return media.clock_name(second).replace('-', ':')


def seconds(clock):
  return sum(int(part) * 60**place for place, part in enumerate(reversed(clock.split(':'))))


def take(text):
  """(summary without the 画面调整 section, [paths not to use], [(start, end, what is wanted)])."""
  found = SECTION.search(text)
  if not found:
    return text, [], []
  unused, wanted = [], []
  for line in found[1].splitlines():
    if match := UNUSED.match(line):
      unused += PATH.findall(unquote(match[1]))
    elif match := WANTED.match(line):
      start = seconds(match[1])
      end = seconds(match[2]) if match[2] else start + SPAN_S
      wanted.append((start, max(start, end), match[3].strip()))
  return (text[: found.start()] + text[found.end() :]).rstrip() + '\n', unused, wanted


def load(asset):
  try:
    return json.loads((Path(asset) / NAME).read_text(encoding='utf-8'))
  except (OSError, ValueError):
    return {'unused': [], 'requests': [], 'draft': None}


def unused(asset):
  return set(load(asset).get('unused') or [])


def without_unused(asset, manifest):
  """The manifest without the pictures a chat AI said it does not need."""
  skip = unused(asset)
  if not skip:
    return manifest
  manifest = dict(manifest)
  for key in ('representative_frames', 'screen_pages'):
    manifest[key] = [item for item in manifest.get(key) or [] if item['path'] not in skip]
  if manifest.get('slide_extraction'):
    slides = manifest['slide_extraction'].get('slides') or []
    manifest['slide_extraction'] = {
      **manifest['slide_extraction'],
      'slides': [i for i in slides if i['path'] not in skip],
    }
  return manifest


def candidates(video, asset, start, end, length):
  """Up to CANDIDATES pictures from start to end that differ from each other, taken into frames/extra; [] when the
  span is outside the video. Seconds showing the same picture form a run, and the longest runs come first: a chart
  held on screen stays the same while stock footage changes every second (on the user's COVID video, choosing only by
  difference gave three shots of a corridor and the chart last), and only runs held two seconds or more count when
  there are any. Each run gives its last second, the most complete."""
  end = min(end, length - 0.5) if length else end
  if start < 0 or start > end:
    return []
  thumbs = media.grey_frames(video, start, end - start + 1)
  width, height = page_rules.THUMB
  runs = []  # [first index, last index]
  for index, thumb in enumerate(thumbs):
    if runs and page_rules.differ(thumbs[runs[-1][0]], thumb, width, height) < page_rules.SAME_PAGE:
      runs[-1][1] = index
    else:
      runs.append([index, index])
  # Pictures held for two seconds or more, when there are any; otherwise moving footage is all the span shows.
  held = [run for run in runs if run[1] > run[0]] or runs
  chosen = []
  for first, last in sorted(held, key=lambda run: (run[0] - run[1], run[0])):
    if len(chosen) == CANDIDATES:
      break
    if all(page_rules.differ(thumbs[other], thumbs[last], width, height) >= page_rules.SAME_PAGE for other in chosen):
      chosen.append(last)
  taken = []
  for index in sorted(chosen) or [0]:
    taken.append(media.save_frame(video, asset, start + index, length).relative_to(asset).as_posix())
  return taken


def apply(video, asset, draft, unused_paths, wanted, length, status=lambda message: None):
  """Records what the section asked for and takes the candidates; `draft` is the file the summary was saved as. The
  caller holds the video's lock. Returns the new state."""
  asset = Path(asset)
  state = load(asset)
  known = [path for path in unused_paths if (asset / path).is_file()]
  state['unused'] = sorted(set(state.get('unused') or []) | set(known))
  requests = []
  for start, end, what in wanted:
    try:
      taken = candidates(video, asset, start, end, length)
    except media.MediaError as error:
      status(f'补截 {_clock(start)}: {error}')
      taken = []
    status(f'补截 {_clock(start)}–{_clock(end)} {what}: {len(taken)} 张候选')
    requests.append({'start_s': start, 'end_s': end, 'what': what, 'candidates': taken})
  state['requests'] = requests
  state['draft'] = Path(draft).name
  if known:
    status(f'不再使用 {len(known)} 张画面')
  files.write_text(asset / NAME, json.dumps(state, ensure_ascii=False, indent=2) + '\n')
  return state
