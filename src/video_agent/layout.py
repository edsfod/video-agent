"""Where the screen is in a video: full screen, beside a camera picture, or with a camera picture inside it.

Lecture uploads often put the camera picture beside or inside the screen recording. Page changes have to be looked for
in the screen region only, or the speaker's movement drowns them out: AutoSlides Extractor compares whole frames and
keeps few slides from such videos, and its auto-crop runs only after that. The layout is read from a small grey copy
of the video (GRID_WIDTH pixels wide), during the same FFmpeg pass that samples the representative frames:

- Borders between two pictures are straight lines that stay put for the whole video. Text and slide templates also
  make lasting edges, so a line only counts when it spans the frame (a split) or closes a box in a corner (a camera
  inset), and away from the frame's own edge.
- A camera picture changes nearly every second (people move); a screen stands still most of the time and changes when
  a page turns or someone types. On a 97-minute lecture with much live coding the camera side changed in 99 % of the
  seconds and the screen side in 21 % (2026-10-27). FFmpeg reports, per second, the share of each CELL x CELL block of
  the grey copy that changed by more than MOTION_LEVEL.

Without a convincing border the whole frame is one region: a screen when it is mostly still, otherwise a camera.
"""

from dataclasses import dataclass

GRID_WIDTH = 256
CELL = 4  # the per-second change report has one value per CELL x CELL block of the grey copy
MOTION_LEVEL = 12  # grey levels between frames one second apart; compression noise in a still area stays below
EDGE_LEVEL = 12  # grey levels across a border
LASTING = 0.85  # share of sampled frames in which an edge must be present to count as a border
SPAN = 0.9  # a split line runs across this share of the frame
INSET_SIDE = 0.15  # a camera inset's sides run along at least this share of the frame
MARGIN = 0.08  # borders this close to the frame's edge are frames of the picture, not splits
ACTIVE = 0.002  # a region is active in a second when this share of it changed
CAMERA = 0.5  # a camera picture is active in at least this share of the seconds; a screen in less


@dataclass
class Layout:
  kind: str  # 'screen' (the whole frame), 'split', 'inset' (camera picture inside the screen), 'camera'
  width: int
  height: int
  screen: tuple | None = None  # (x, y, w, h) in source pixels: where to look for page changes
  camera: tuple | None = None  # (x, y, w, h): the camera picture; blacked out for 'inset'
  activity: tuple = ()  # share of active seconds: (screen, camera)

  def page_filter(self):
    """The FFmpeg filters that leave only the screen region, or None for a camera-only video."""
    if self.kind == 'camera':
      return None
    parts = []
    if self.kind == 'inset':
      x, y, w, h = self.camera
      parts.append(f'drawbox=x={x}:y={y}:w={w}:h={h}:color=black:t=fill')
    x, y, w, h = self.screen
    if (w, h) != (self.width, self.height):
      parts.append(f'crop={w}:{h}:{x}:{y}')
    return ','.join(parts) or 'null'

  def as_manifest(self):
    return {
      'kind': self.kind,
      'size': [self.width, self.height],
      'screen': self.screen,
      'camera': self.camera,
      'activity': [round(value, 3) for value in self.activity],
    }


def grid_size(width, height):
  """The grey copy's size: GRID_WIDTH wide, height in proportion and a multiple of CELL (so also even)."""
  return GRID_WIDTH, max(CELL, round(height * GRID_WIDTH / max(1, width) / CELL) * CELL)


class Measure:
  """Collects what FFmpeg streams: per second, the changed share of each cell (one byte, 255 = all of it), and a
  sparse set of plain grey frames for the borders."""

  def __init__(self, width, height):
    self.width, self.height = width, height
    self.size = width * height
    self.columns, self.rows = width // CELL, height // CELL
    self.cell_size = self.columns * self.rows
    self.seconds = []
    self.samples = []

  def feed(self, cells):
    self.seconds.append(cells)

  def sample(self, frame):
    self.samples.append(frame)

  def lasting_edges(self):
    """Per pixel, the share of samples with a jump to its left neighbour (vertical edges) and to the one above."""
    w, h, n = self.width, self.height, max(1, len(self.samples))
    vertical = [0] * self.size
    horizontal = [0] * self.size
    for frame in self.samples:
      for y in range(h):
        row = y * w
        for x in range(1, w):
          if abs(frame[row + x] - frame[row + x - 1]) > EDGE_LEVEL:
            vertical[row + x] += 1
        if y:
          for x in range(w):
            if abs(frame[row + x] - frame[row - w + x]) > EDGE_LEVEL:
              horizontal[row + x] += 1
    return [v / n for v in vertical], [v / n for v in horizontal]

  def activity(self, box):
    """The share of seconds in which the cells inside `box` (grey-copy pixels) changed by more than ACTIVE."""
    x, y, w, h = box
    x0, y0 = -(-x // CELL), -(-y // CELL)
    x1, y1 = (x + w) // CELL, (y + h) // CELL
    if x1 <= x0 or y1 <= y0 or not self.seconds:
      return 0.0
    limit = ACTIVE * (x1 - x0) * (y1 - y0) * 255
    active = 0
    for cells in self.seconds:
      changed = sum(sum(cells[row * self.columns + x0 : row * self.columns + x1]) for row in range(y0, y1))
      active += changed > limit
    return active / len(self.seconds)


def _split_lines(vertical, horizontal, w, h):
  """Lasting lines across the whole frame, away from its edges: [('x', position) | ('y', position)]."""
  lines = []
  for x in range(round(MARGIN * w), round((1 - MARGIN) * w)):
    if sum(vertical[y * w + x] >= LASTING for y in range(h)) >= SPAN * h:
      lines.append(('x', x))
  for y in range(round(MARGIN * h), round((1 - MARGIN) * h)):
    if sum(horizontal[y * w + x] >= LASTING for x in range(w)) >= SPAN * w:
      lines.append(('y', y))
  return _merge(lines)


def _merge(lines):
  """Neighbouring positions of one blurred border become one line, the middle one."""
  merged = []
  for axis, position in lines:
    if merged and merged[-1][0] == axis and position - merged[-1][2] <= 2:
      merged[-1][2] = position
    else:
      merged.append([axis, position, position])
  return [(axis, (first + last) // 2) for axis, first, last in merged]


def _insets(vertical, horizontal, w, h):
  """Boxes in a corner closed by a lasting vertical and horizontal line: camera picture-in-picture candidates."""
  boxes = []

  def run_v(x, y0, y1):
    return sum(vertical[y * w + x] >= LASTING for y in range(y0, y1)) >= 0.9 * (y1 - y0)

  def run_h(y, x0, x1):
    return sum(horizontal[y * w + x] >= LASTING for x in range(x0, x1)) >= 0.9 * (x1 - x0)

  side_w, side_h = max(2, round(INSET_SIDE * w)), max(2, round(INSET_SIDE * h))
  for x in range(round(MARGIN * w), round((1 - MARGIN) * w)):
    for y in range(round(MARGIN * h), round((1 - MARGIN) * h)):
      for left, top in ((False, False), (False, True), (True, False), (True, True)):
        # The camera box spans from the corner to (x, y); its inner sides are the lines at x and y.
        y0, y1 = (0, y) if top else (y, h)
        x0, x1 = (0, x) if left else (x, w)
        if y1 - y0 < side_h or x1 - x0 < side_w or (x1 - x0) * (y1 - y0) > 0.5 * w * h:
          continue
        if run_v(x, y0, y1) and run_h(y, x0, x1):
          boxes.append((x0, y0, x1 - x0, y1 - y0))
  # The largest box per corner; nested candidates come from blurred lines.
  best = {}
  for box in boxes:
    corner = (box[0] == 0, box[1] == 0)
    if corner not in best or box[2] * box[3] > best[corner][2] * best[corner][3]:
      best[corner] = box
  return list(best.values())


def _trim_dark(measure, box):
  """Shrinks a region by rows and columns that are dark in every sample (letterbox bars)."""
  x, y, w, h = box
  width = measure.width

  def dark(cells):
    return all(max(frame[i] for i in cells) < 24 for frame in measure.samples[:: max(1, len(measure.samples) // 40)])

  while w > 4 and dark([row * width + x for row in range(y, y + h)]):
    x, w = x + 1, w - 1
  while w > 4 and dark([row * width + x + w - 1 for row in range(y, y + h)]):
    w -= 1
  while h > 4 and dark([y * width + col for col in range(x, x + w)]):
    y, h = y + 1, h - 1
  while h > 4 and dark([(y + h - 1) * width + col for col in range(x, x + w)]):
    h -= 1
  return x, y, w, h


def analyse(measure):
  """The layout in grey-copy pixels; `to_source` scales it to the video."""
  w, h = measure.width, measure.height
  whole = (0, 0, w, h)
  if not measure.samples or not measure.seconds:
    return Layout('screen', w, h, whole)
  vertical, horizontal = measure.lasting_edges()

  splits = []  # (screen box, camera box, kind)
  for axis, position in _split_lines(vertical, horizontal, w, h):
    if axis == 'x':
      first, second = (0, 0, position, h), (position, 0, w - position, h)
    else:
      first, second = (0, 0, w, position), (0, position, w, h - position)
    splits += [(first, second, 'split'), (second, first, 'split')]

  def choose(candidates):
    best = None
    for screen, camera, kind in candidates:
      # Measured a cell away from the border, where the two pictures blur into each other.
      screen_active = measure.activity(_inner(screen, camera, kind))
      camera_active = measure.activity(_pad(camera, -CELL))
      if camera_active >= CAMERA and screen_active < CAMERA and screen_active <= camera_active / 2:
        margin = camera_active - screen_active
        if best is None or margin > best.activity[1] - best.activity[0]:
          best = Layout(kind, w, h, screen, camera, (screen_active, camera_active))
    return best

  # A line across the whole frame is the stronger evidence: a corner box is only looked at without a split. (Board
  # edges inside a camera picture can close a box with the split line.)
  best = choose(splits) or choose([(whole, box, 'inset') for box in _insets(vertical, horizontal, w, h)])
  if best:
    if best.kind == 'split':
      best.screen = _trim_dark(measure, _shrink(best.screen, best.camera))
    return best
  active = measure.activity(whole)
  if active < CAMERA:
    return Layout('screen', w, h, _trim_dark(measure, whole), None, (active,))
  return Layout('camera', w, h, whole, None, (active,))


def _pad(box, amount):
  x, y, w, h = box
  return x - amount, y - amount, w + 2 * amount, h + 2 * amount


def _inner(screen, camera, kind):
  """Where to measure the screen: for a split, its region less a cell at the border; for an inset, the band beside
  the camera box."""
  if kind != 'inset':
    return _shrink(screen, camera, CELL)
  x, _, w, _ = camera
  full_w, full_h = screen[2], screen[3]
  return (x + w + CELL, 0, full_w - x - w - CELL, full_h) if x == 0 else (0, 0, x - CELL, full_h)


def _shrink(screen, camera, amount=1):
  """Moves the screen's side at the border `amount` grid pixels away from it, where the two pictures blur together."""
  x, y, w, h = screen
  if camera[0] + camera[2] <= x:  # camera on the left
    return x + amount, y, w - amount, h
  if camera[0] >= x + w:
    return x, y, w - amount, h
  if camera[1] + camera[3] <= y:
    return x, y + amount, w, h - amount
  return x, y, w, h - amount


def to_source(layout, width, height):
  """The same layout in the video's pixels, with even sizes and positions as YUV 4:2:0 crops need."""
  sx, sy = width / layout.width, height / layout.height

  def scale(box):
    if box is None:
      return None
    x, y, w, h = box
    x0, y0 = int(x * sx) // 2 * 2, int(y * sy) // 2 * 2
    x1, y1 = min(width, round((x + w) * sx)), min(height, round((y + h) * sy))
    return [x0, y0, (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2]

  return Layout(layout.kind, width, height, scale(layout.screen), scale(layout.camera), layout.activity)


def from_region(text, width, height):
  """A screen region given by hand as 'x,y,w,h' in the video's pixels."""
  try:
    x, y, w, h = (int(part) for part in text.split(','))
  except ValueError:
    raise ValueError(f'expected x,y,w,h in pixels, got {text!r}') from None
  if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
    raise ValueError(f'the region {text} does not fit in the {width}x{height} video')
  x, y = x // 2 * 2, y // 2 * 2
  return Layout('screen' if (w, h) == (width, height) else 'split', width, height, [x, y, w // 2 * 2, h // 2 * 2])
