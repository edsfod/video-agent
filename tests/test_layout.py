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
  subprocess.run([*command, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(target)], check=True)
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


def test_near_identical_pages_merge_into_the_latest_picture(tmp_path):
  # One page whose pointer moves, then a small label appears; then a real second page.
  graph = (
    'color=c=white:s=320x180:r=5:d=20,'
    "drawbox=x=20:y=20:w=200:h=80:color=0x303030:t=fill:enable='lt(t,12)',"
    "drawbox=x='40+t*3':y=140:w=6:h=8:color=black:t=fill:enable='lt(t,12)',"
    "drawbox=x=230:y=20:w=20:h=12:color=red:t=fill:enable='between(t,6,12)',"
    "drawbox=x=60:y=60:w=220:h=100:color=0x6060c0:t=fill:enable='gte(t,12)'[out]"
  )
  video = _video(tmp_path, 'merge', graph)
  pages = media.screen_pages(video, tmp_path / 'pages', 'null', stable=1.0)
  assert [round(page['time_s']) for page in pages] == [0, 12]
  assert pages[0]['path'].name != 'page-00001.jpg', 'the later, more complete picture of the first page is kept'
