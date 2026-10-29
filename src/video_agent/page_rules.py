"""Which screen pages to keep: comparing small grey copies of them (THUMB, one byte per pixel) for the same page with
small changes, a page built up step by step, scrolled text, a return to an earlier page and a passing state, and
tuning how long a page must stay towards a number of pages an hour. Pure functions on bytes, without FFmpeg, so they
can be tested on made-up pictures; media.merge_similar runs them on a video's pages.
"""

import math

# Pages whose small grey copies differ in fewer than this share of pixels show the same content: a pointer, a typed
# character, a pop-up, a highlighted line. Two slides in one template can differ in as little as 4 %.
SAME_PAGE = 0.025
THUMB = (128, 72)
SCROLL_NEW = 1 / 3  # a scroll that brings in less than this share of new lines leaves the same page
# A page shown for less than LONG_S counts only when most of it is new (another window, another slide); short pages
# with smaller changes are passing states, such as a terminal printing in bursts or a page being typed or scrolled.
LONG_S = 6.0
NEW_SCREEN = 0.5
RECENT = 8  # a page like one of the last RECENT kept pages is a return to it (switching windows), not a new page


def differ(a, b, width, height, shift=0, columns=None):
  """The share of pixels that differ by more than 20 grey levels where `b`, moved up by `shift` rows, overlaps `a`;
  within `columns` (a range) when given."""
  x0, x1 = (columns.start, columns.stop) if columns else (0, width)
  rows = range(max(0, -shift), min(height, height - shift))
  changed = 0
  for y in rows:
    top, other = y * width, (y + shift) * width
    changed += sum(abs(x - z) > 20 for x, z in zip(a[top + x0 : top + x1], b[other + x0 : other + x1]))
  return changed / max(1, len(rows) * (x1 - x0))


# A page built up step by step (a list, a diagram, a chat that grows) keeps everything already shown: when `b` changed
# fewer than this share of the pixels that carry content in `a`, `b` is `a` with more added. Background is the most
# common grey level of `a`; a page with content in less than BLANK of its pixels (a title alone, an empty window) counts
# as built up by whatever follows (user report, 2026-10-28: steps of one slide were kept as pages of their own).
KEPT_INK = 0.03
BLANK = 0.01


def added(a, b):
  """Whether `b` shows everything `a` shows, with more added."""
  counts = [0] * 256
  for value in a:
    counts[value] += 1
  background = max(range(256), key=counts.__getitem__)
  ink = [index for index, value in enumerate(a) if abs(value - background) > 20]
  if len(ink) < BLANK * len(a):
    return True
  changed = sum(abs(a[index] - b[index]) > 20 for index in ink)
  return changed < KEPT_INK * len(ink)


def _scroll(a, b, width, height, columns):
  """How many rows `b` is scrolled against `a` within `columns`, matched on the rows' mean brightness."""
  limit = int(height * SCROLL_NEW)
  first = [sum(a[y * width + columns.start : y * width + columns.stop]) for y in range(height)]
  second = [sum(b[y * width + columns.start : y * width + columns.stop]) for y in range(height)]

  def cost(shift):
    rows = range(max(0, -shift), min(height, height - shift))
    return sum(abs(first[y] - second[y + shift]) for y in rows) / max(1, len(rows))

  return min(range(-limit, limit + 1), key=lambda shift: (cost(shift), abs(shift)))


def scrolled(a, b, width, height):
  """Whether `b` is `a` with its text scrolled, as a whole or in its left and right halves separately (an editor
  beside a terminal), by less than SCROLL_NEW of the height."""
  halves = (range(width), range(width // 2), range(width // 2, width))
  for panes in ((halves[0],), halves[1:]):
    if all(
      differ(a, b, width, height, 0, pane) < SAME_PAGE
      or differ(a, b, width, height, _scroll(a, b, width, height, pane), pane) < SAME_PAGE
      for pane in panes
    ):
      return True
  return False


# How many pages an hour of video should give; outside this band LONG_S is tuned, as Opencast's video segmenter tunes its
# threshold towards a segment count. Wide on purpose: slides alone give 20-60 an hour, live coding more.
PAGES_PER_HOUR = (15, 75)
MIN_ALLOWED = 30  # a short video may always keep this many
LONG_STEPS = (2.0, 4.0, 6.0, 10.0, 15.0, 25.0, 40.0)  # values LONG_S is tuned through; LONG_S is the starting point


def tune_long(count_for, hours):
  """The LONG_S to use: raised step by step while count_for(LONG_S) gives more pages than the band allows for `hours`,
  lowered while it gives fewer, never beyond LONG_STEPS. Only short pages that are not mostly new respond to it, so a
  slide that replaces the screen survives any value."""
  low, high = PAGES_PER_HOUR[0] * hours, max(MIN_ALLOWED, PAGES_PER_HOUR[1] * hours)
  index = LONG_STEPS.index(LONG_S)
  count = count_for(LONG_STEPS[index])
  step = 1 if count > high else -1 if count < low else 0
  while step and 0 <= index + step < len(LONG_STEPS) and (count > high if step > 0 else count < low):
    index += step
    count = count_for(LONG_STEPS[index])
  return LONG_STEPS[index]


# Subtitles burnt into the picture change every few seconds and end each still period, so a chart shown for ten
# seconds comes as several short periods of the same page (user report, 2026-10-29). Periods this close together that
# show the same page count as one stay.
JOINED_GAP_S = 3.0


def stayed(pages, thumbs, index):
  """How long the page at `index` stayed: its own still period, run on through the following periods of the same page
  that start within JOINED_GAP_S of the previous one's end."""
  width, height = THUMB
  page = pages[index]
  end = page['time_s'] + page.get('stayed_s', math.inf)
  for other, thumb in zip(pages[index + 1 :], thumbs[index + 1 :]):
    if other['time_s'] - end > JOINED_GAP_S or differ(thumbs[index], thumb, width, height) >= SAME_PAGE:
      break
    end = other['time_s'] + other.get('stayed_s', math.inf)
  return end - page['time_s']


def merge(pages, thumbs, long_s):
  """The pages kept (see media.merge_similar), given each page's grey copy and the LONG_S to use."""
  width, height = THUMB
  merged, firsts = [], []  # kept pages, and the grey copy each group started with
  for index, (page, thumb) in enumerate(zip(pages, thumbs)):
    if firsts:
      first = firsts[-1]
      if differ(first, thumb, width, height) < SAME_PAGE or added(first, thumb):
        merged[-1]['path'] = page['path']
        continue
      if scrolled(first, thumb, width, height):
        continue
      if any(differ(earlier, thumb, width, height) < SAME_PAGE for earlier in firsts[-RECENT - 1 : -1]):
        continue
      if stayed(pages, thumbs, index) < long_s and differ(first, thumb, width, height) < NEW_SCREEN:
        continue
    merged.append(dict(page))
    firsts.append(thumb)
  return merged


def merge_steps(pages, thumbs):
  """The pages with the steps of one page as one: a page within SAME_PAGE of its group's first page, or showing all of
  it with more added, joins the group, which keeps its first time and its last, fullest picture. For pages found by
  another tool (AutoSlides Extractor keeps each step), where the rest of `merge` is that tool's own business."""
  width, height = THUMB
  merged, first = [], None
  for page, thumb in zip(pages, thumbs):
    if first is not None and (differ(first, thumb, width, height) < SAME_PAGE or added(first, thumb)):
      merged[-1]['path'] = page['path']
      continue
    merged.append(dict(page))
    first = thumb
  return merged
