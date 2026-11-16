"""Deleting videos from the workspace (user request, 2026-11-16: one click, several at once): each video's processing
folder with its transcript, pictures and every summary version, and its place in collections; the video file itself,
with the subtitle and info files yt-dlp saved beside it, only when this program downloaded it (into the workspace's
下载 folder or a followed collection's download folder). A video the user added from their own disk stays where it is
(docs/product-rules.md).
"""

import json
import shutil
from pathlib import Path

from . import collection, contract, files, processor

DOWNLOADS = '下载'
# What yt-dlp saves beside a video under the same name (`<name>.ai-zh.srt`, `<name>.info.json`).
BESIDE = {'.srt', '.vtt', '.ass', '.ssa', '.lrc', '.json'}


def _key(path):
  return str(Path(path)).casefold()


def download_folders(workspace):
  """The folders this program downloads into: the workspace's 下载 and each followed collection's own."""
  workspace = Path(workspace)
  found = [workspace / DOWNLOADS]
  for name in collection.names(workspace):
    source = collection.load(workspace, name).get('source') or {}
    if source.get('folder'):
      found.append(Path(source['folder']))
  return [folder.expanduser().resolve() for folder in found]


def downloaded(workspace, video):
  """Whether this program downloaded the video: it lies in one of the folders downloads go to."""
  video = Path(video).expanduser().resolve()
  return any(video.is_relative_to(folder) for folder in download_folders(workspace))


def asset_folders(workspace, video):
  """Every processing folder of the video: the one its path names, and any other whose manifest names the video, such
  as one made under an older folder name."""
  workspace = Path(workspace)
  video = Path(video).expanduser().resolve()
  found = []
  own = processor.asset_folder(workspace, video)
  if own.is_dir():
    found.append(own)
  for manifest in workspace.glob('*/manifest.json'):
    folder = manifest.parent
    if folder in found or folder.name in (DOWNLOADS, collection.FOLDER):
      continue
    try:
      source = json.loads(manifest.read_text(encoding='utf-8')).get('source_video')
    except (OSError, ValueError):
      continue
    if source and _key(Path(source).expanduser().resolve()) == _key(video):
      found.append(folder)
  return found


def _free(folder):
  """Fails when a job is writing in the folder (it holds the folder's lock)."""
  with files.video_lock(folder, 'delete the video'):
    pass


def delete(workspace, video) -> contract.Deleted:
  """Deletes one video from the workspace as the module says; returns what went and what stayed."""
  workspace = Path(workspace)
  video = Path(video).expanduser().resolve()
  folders = asset_folders(workspace, video)
  for folder in folders:
    _free(folder)
  taken_out = []
  for name in collection.names(workspace):
    members = collection.load(workspace, name)['videos']
    if any(_key(Path(member).expanduser().resolve()) == _key(video) for member in members):
      collection.remove(workspace, name, [str(video)])
      taken_out.append(name)
  for folder in folders:
    shutil.rmtree(folder)
  removed = []
  mine = downloaded(workspace, video)
  if mine and video.parent.is_dir():
    beside = [
      path
      for path in video.parent.iterdir()
      if path.is_file() and path.name.startswith(f'{video.stem}.') and path.suffix.lower() in BESIDE
    ]
    for path in [video, *beside]:
      if path.is_file():
        path.unlink()
        removed.append(str(path))
  return {
    'video': str(video),
    'folders': [str(folder) for folder in folders],
    'collections': taken_out,
    'files': removed,
    'video_kept': not mine,
  }
