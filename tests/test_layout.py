"""Layout detection and screen pages on synthetic videos: a moving block stands in for the speaker, and white slides
with a different set of dark boxes every 6 seconds stand in for the screen."""

import json
import subprocess

import pytest

from video_agent import cli, layout, media
from video_agent.processor import asset_folder

PAGE_S, PAGES = 6, 6
LENGTH = PAGE_S * PAGES


def _slides(name, size='320x180'):
  """White pages, each with its own two boxes; the label lets several of them be stacked in one graph."""
  boxes = ''.join(
    f",drawbox=x={20 + 40 * page}:y={15 + 10 * (page % 3)}:w=150:h=60:color=0x303030:t=fill:enable='between(t,{page * PAGE_S},{page * PAGE_S + PAGE_S - 0.01})'"
    f",drawbox=x={140 - 15 * page}:y=110:w=120:h=40:color=0x6060c0:t=fill:enable='between(t,{page * PAGE_S},{page * PAGE_S + PAGE_S - 0.01})'"
    for page in range(PAGES)
  )
  return f'color=c=white:s={size}:r=5:d={LENGTH}{boxes}[{name}]'


def _camera(name, size='320x180', box='30x60'):
  """A grey room with a dark block walking across it."""
  width, height = (int(part) for part in size.split('x'))
  w, h = (int(part) for part in box.split('x'))
  return (
    f'color=c=0x707070:s={size}:r=5:d={LENGTH}[{name}room];color=c=0x202020:s={box}:r=5:d={LENGTH}[{name}person];'
    f"[{name}room][{name}person]overlay=x='mod(t*37,{width - w})':y={height - h - 4}[{name}]"
  )


def _video(tmp_path, name, graph):
  target = tmp_path / f'{name}.mp4'
  command = [media.tool('ffmpeg'), '-y', '-v', 'error', '-filter_complex', graph, '-map', '[out]']
  # mpeg4 rather than libx264, so the LGPL FFmpeg the installer ships can make it too.
  subprocess.run([*command, '-c:v', 'mpeg4', '-q:v', '3', '-pix_fmt', 'yuv420p', str(target)], check=True)
  return target


def _process(video, workspace, *extra):
  assert cli.main(['process', str(video), '-o', str(workspace), '--json', *extra]) in (0, 1)  # no subtitles: 1
  return json.loads((asset_folder(workspace, video.resolve()) / 'manifest.json').read_text(encoding='utf-8'))


def test_split_layout_finds_the_screen_and_its_pages(tmp_path):
  video = _video(tmp_path, 'split', f'{_camera("cam")};{_slides("screen")};[cam][screen]hstack[out]')
  manifest = _process(video, tmp_path / 'work')
  found = manifest['layout']
  assert found['kind'] == 'split'
  x, y, w, h = found['screen']
  assert 320 <= x <= 330 and y == 0 and x + w >= 630 and h == 180
  assert found['camera'][0] == 0 and found['camera'][2] <= 322
  assert len(manifest['screen_pages']) == PAGES
  times = [page['time_s'] for page in manifest['screen_pages']]
  assert all(abs(time - index * PAGE_S) <= 1.5 for index, time in enumerate(times)), times
  asset = asset_folder(tmp_path / 'work', video.resolve())
  assert (asset / manifest['layout']['picture']).is_file()
  context = (asset / 'summary-context.md').read_text(encoding='utf-8')
  assert '## Screen pages' in context and 'beside a camera picture' in context


def test_full_screen_and_camera_only(tmp_path):
  screen = _video(tmp_path, 'screen', _slides('out', '640x360'))
  manifest = _process(screen, tmp_path / 'work')
  assert manifest['layout']['kind'] == 'screen'
  assert manifest['layout']['screen'] == [0, 0, 640, 360]
  assert len(manifest['screen_pages']) == PAGES

  camera = _video(tmp_path, 'camera', _camera('out', '640x360', '60x120'))
  manifest = _process(camera, tmp_path / 'work')
  assert manifest['layout']['kind'] == 'camera'
  assert manifest['screen_pages'] == []


def test_camera_inset_is_blacked_out(tmp_path):
  graph = f'{_slides("screen", "640x360")};{_camera("cam", "160x90", "16x30")};[screen][cam]overlay=x=470:y=260[out]'
  manifest = _process(_video(tmp_path, 'inset', graph), tmp_path / 'work')
  found = manifest['layout']
  assert found['kind'] == 'inset', found
  x, y, w, h = found['camera']
  assert 462 <= x <= 474 and 252 <= y <= 264 and x + w == 640 and y + h == 360
  assert len(manifest['screen_pages']) == PAGES


def test_a_screen_region_given_by_hand(tmp_path):
  video = _video(tmp_path, 'split', f'{_camera("cam")};{_slides("screen")};[cam][screen]hstack[out]')
  manifest = _process(video, tmp_path / 'work', '--screen-region', '320,0,320,180')
  assert manifest['layout'] | {'picture': None} == {
    'kind': 'split',
    'size': [640, 180],
    'screen': [320, 0, 320, 180],
    'camera': None,
    'activity': [],
    'picture': None,
    'given': True,
  }
  assert len(manifest['screen_pages']) == PAGES
  with pytest.raises(ValueError):
    layout.from_region('600,0,320,180', 640, 180)


def _boxes(*boxes):
  """A white 320x180 picture with dark boxes (x, y, w, h, start, end) shown from `start` to `end` seconds."""
  drawn = ''.join(
    f",drawbox=x={x}:y={y}:w={w}:h={h}:color=0x303030:t=fill:enable='between(t,{start},{end - 0.01})'"
    for x, y, w, h, start, end in boxes
  )
  return f'color=c=white:s=320x180:r=5:d=30{drawn}[out]'


def test_an_addition_to_a_page_keeps_the_fuller_picture(tmp_path):
  # A page, then a label added to it (under 2.5 % of the picture), then another page.
  graph = _boxes((20, 20, 200, 80, 0, 20), (230, 20, 40, 12, 8, 20), (60, 110, 220, 60, 20, 30))
  pages, _ = media.screen_pages(_video(tmp_path, 'addition', graph), tmp_path / 'pages', 'null')
  assert [round(page['time_s']) for page in pages] == [0, 20]
  assert pages[0]['path'].name != 'page-00001.jpg', 'the later, more complete picture of the first page is kept'


def test_short_minor_changes_and_returns_are_not_new_pages(tmp_path):
  graph = _boxes(
    (20, 20, 200, 80, 0, 10),  # page A, 10 s
    (20, 20, 200, 80, 10, 13),
    (20, 110, 120, 20, 10, 13),  # A with a line more, only 3 s: a passing state
    (100, 30, 200, 130, 13, 21),  # page B, 8 s
    (20, 20, 200, 80, 21, 30),  # back to A: a return, not a new page
  )
  pages, _ = media.screen_pages(_video(tmp_path, 'passing', graph), tmp_path / 'pages', 'null')
  assert [round(page['time_s']) for page in pages] == [0, 13]


def test_the_shown_time_is_tuned_towards_a_page_count_per_hour():
  # Pretend each step up of LONG_S removes 40 pages from 300.
  counts = dict(zip(media.LONG_STEPS, (380, 340, 300, 260, 220, 180, 140)))
  assert media.tune_long(counts.get, 2) == 40.0  # 150 allowed in 2 h: raised to the last step, still above
  assert media.tune_long(counts.get, 4) == 6.0  # 300 allowed: the default stays
  assert media.tune_long(counts.get, 3.5) == 10.0  # 262 allowed: one step up is enough
  assert media.tune_long(dict.fromkeys(media.LONG_STEPS, 5).get, 1) == 2.0  # too few at any value: lowered to the end
  assert media.tune_long(dict.fromkeys(media.LONG_STEPS, 25).get, 0.2) == 6.0  # a short video may keep 30
