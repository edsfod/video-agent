"""Which screen pages are kept, on made-up grey copies (page_rules.THUMB): the same page with a small change, a page
built up step by step, scrolled text, a return to an earlier page, and a passing state."""

from video_agent import page_rules
from video_agent.page_rules import THUMB, added, differ, merge, scrolled

WIDTH, HEIGHT = THUMB


def page(lines, background=255, ink=0, blocks=()):
  """A page of text lines: (row, length) bars two rows high from the left margin, and (x, y, w, h, value) blocks."""
  picture = bytearray([background] * WIDTH * HEIGHT)
  for row, length in lines:
    for y in (row, row + 1):
      picture[y * WIDTH + 8 : y * WIDTH + 8 + length] = bytes([ink]) * length
  for x, y, w, h, value in blocks:
    for line in range(y, y + h):
      picture[line * WIDTH + x : line * WIDTH + x + w] = bytes([value]) * w
  return bytes(picture)


TEXT = [(row, 20 + (index * 37) % 90) for index, row in enumerate(range(4, 66, 6))]
OTHER = [(row, 110 - (index * 23) % 80) for index, row in enumerate(range(7, 66, 5))]


def test_a_small_mark_is_the_same_page_and_another_text_is_not():
  a = page(TEXT)
  assert differ(a, a, WIDTH, HEIGHT) == 0
  assert differ(a, page(TEXT, blocks=[(100, 60, 8, 8, 0)]), WIDTH, HEIGHT) < page_rules.SAME_PAGE
  assert differ(a, page(OTHER), WIDTH, HEIGHT) > page_rules.SAME_PAGE
  assert differ(a, page(TEXT, background=0, ink=255), WIDTH, HEIGHT) > page_rules.NEW_SCREEN


def test_a_page_with_more_added_keeps_what_it_showed():
  first = page(TEXT[:5])
  assert added(first, page(TEXT))  # more lines below
  assert not added(page(TEXT), page(TEXT[:5]))  # lines taken away
  assert added(page(TEXT[:1]), page(OTHER))  # a title alone is built up by whatever follows


def test_scrolled_text_is_the_same_page():
  lines = page(TEXT)
  moved = page([(row - 6, length) for row, length in TEXT if row >= 6] + [(64, 50)])
  assert scrolled(lines, moved, WIDTH, HEIGHT)
  assert not scrolled(lines, page(OTHER), WIDTH, HEIGHT)


def test_merge_keeps_new_pages_and_drops_repeats_and_passing_states():
  a = page(TEXT)
  a_marked = page(TEXT, blocks=[(100, 60, 8, 8, 0)])
  b = page(OTHER)
  b_half = page(OTHER, blocks=[(0, 0, WIDTH // 2, 36, 255)])  # half of b wiped: a passing state
  inverted = page(TEXT, background=0, ink=255)
  shown = [
    ('a', 0, 30, a),
    ('a, marked', 30, 30, a_marked),  # the same page: joins a's group, which keeps the fuller last picture
    ('b', 60, 30, b),
    ('a again', 90, 30, a),  # a return to a recent page
    ('b, half wiped', 120, 2, b_half),  # short and not mostly new
    ('inverted', 122, 2, inverted),  # short but mostly new: kept
  ]
  pages = [{'time_s': time, 'path': name, 'stayed_s': stayed} for name, time, stayed, _ in shown]
  kept = merge(pages, [thumb for *_, thumb in shown], page_rules.LONG_S)
  assert [(item['time_s'], item['path']) for item in kept] == [(0, 'a, marked'), (60, 'b'), (122, 'inverted')]


def test_a_page_cut_into_short_stays_by_changing_subtitles_stays_as_long_as_they_add_up():
  b = page(OTHER)
  subtitled = [page(TEXT, blocks=[(30 + 10 * index, 66, 40, 4, 0)]) for index in range(3)]  # a new line every 2-3 s
  shown = [(0, 30, b), (30, 2, subtitled[0]), (32, 3, subtitled[1]), (35, 2, subtitled[2]), (60, 2, page(TEXT))]
  pages = [{'time_s': time, 'path': str(time), 'stayed_s': stayed} for time, stayed, _ in shown]
  thumbs = [thumb for *_, thumb in shown]
  assert page_rules.stayed(pages, thumbs, 1) == 7
  assert page_rules.stayed(pages, thumbs, 4) == 2, 'too long after the others'
  assert [item['time_s'] for item in merge(pages, thumbs, page_rules.LONG_S)] == [0, 30]
