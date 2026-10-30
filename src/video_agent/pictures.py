"""Which of a video's pictures a summary is given, as a tree of sets (user decision, 2026-10-30). The root is every
picture processing took (representative frames, screen pages or slides) and those captured later outside a chat AI's
rounds; each node is a set derived from its parent by dropping and adding pictures, made when a chat AI's round drops
pictures it does not need or links ones it chose, or when the user drops or restores one by hand. The pictures stay
files in the video's folder, once each: a node only names paths, which carry their times.

One node is current: every summary route and pack is given its set, and a chat AI's round grows a node from it, so a
cheap AI may sort the pictures first and a better one write from what is left; choosing an earlier node starts again
from there. A picture linked in the latest draft of a round is always in its set (a round once dropped a page the
last draft linked). Each summary version records the node it was written with (versions.py). Processing again starts a
new tree, as the pictures are new. The tree is in pictures.json in the video's folder.
"""

import json
from datetime import datetime
from pathlib import Path

from . import contract, files

NAME = 'pictures.json'
ROOT = '0'


def _manifest(asset):
  return json.loads((Path(asset) / 'manifest.json').read_text(encoding='utf-8'))


def _processed(manifest):
  """The pictures processing took, in the manifest's order."""
  paths = [item['path'] for key in ('screen_pages', 'representative_frames') for item in manifest.get(key) or []]
  paths += [slide['path'] for slide in (manifest.get('slide_extraction') or {}).get('slides') or []]
  return list(dict.fromkeys(paths))


def _extras(asset):
  return sorted(path.relative_to(asset).as_posix() for path in (Path(asset) / 'frames' / 'extra').glob('frame-*.jpg'))


def _node(number, parent, source, note, drop, add):
  created = datetime.now().isoformat(timespec='seconds')
  return {'id': number, 'parent': parent, 'created': created, 'source': source, 'note': note, 'drop': drop, 'add': add}


def load(asset):
  """The tree for the video's current processing run, started afresh when there is none or it is for another run."""
  asset = Path(asset)
  manifest = _manifest(asset)
  try:
    tree = json.loads((asset / NAME).read_text(encoding='utf-8'))
  except (OSError, ValueError):
    tree = None
  if not tree or tree.get('run') != manifest.get('representative_frame_run'):
    tree = {'run': manifest.get('representative_frame_run'), 'current': ROOT, 'nodes': []}
  return tree


def _save(asset, tree):
  files.write_text(Path(asset) / NAME, json.dumps(tree, ensure_ascii=False, indent=2) + '\n')


def _find(tree, node):
  for item in tree['nodes']:
    if item['id'] == node:
      return item
  raise ValueError(f'no picture set {node!r}; see `video-agent pictures VIDEO`')


def _path(tree, node):
  """The nodes from the root's first child down to `node`."""
  chain = []
  while node != ROOT:
    item = _find(tree, node)
    chain.append(item)
    node = item['parent']
  return chain[::-1]


def _universe(asset, tree):
  """(every picture there is, the root's set): the root holds the extra pictures no node added and that are not a
  chat AI's candidates, such as an Agent's."""
  manifest = _manifest(asset)
  extras = _extras(asset)
  added = {path for item in tree['nodes'] for path in item['add']} | set(tree.get('candidates') or [])
  root = _processed(manifest) + [path for path in extras if path not in added]
  return _processed(manifest) + extras, root


def members(asset, node=None, tree=None):
  """The paths in a node's set (the current node by default), in the manifest's order, extra pictures last."""
  tree = tree or load(asset)
  every, root = _universe(asset, tree)
  chosen = set(root)
  for item in _path(tree, node or tree['current']):
    chosen = (chosen - set(item['drop'])) | set(item['add'])
  return [path for path in every if path in chosen]


def current(asset):
  return load(asset)['current']


def branch(asset, drop, add, *, source='', note='', base=None):
  """Makes the set of `base` (the current node by default) less `drop` and with `add` a new node, and the current one;
  returns its id, or the base's when nothing changes. Paths that are not pictures of the video are left out."""
  asset = Path(asset)
  tree = load(asset)
  base = base or tree['current']
  every, _ = _universe(asset, tree)
  have = set(members(asset, base, tree))
  wanted = set(add) & set(every)
  add = sorted(wanted - have)
  drop = sorted(set(drop) & have - wanted)
  if not add and not drop:
    tree['current'] = base
    _save(asset, tree)
    return base
  number = str(max((int(item['id']) for item in tree['nodes']), default=0) + 1)
  tree['nodes'].append(_node(number, base, source, note, drop, add))
  tree['current'] = number
  _save(asset, tree)
  return number


def candidates(asset, paths):
  """Records pictures taken as candidates for a chat AI to choose from: in no set until a draft links one."""
  tree = load(asset)
  tree['candidates'] = sorted(set(tree.get('candidates') or []) | set(paths))
  _save(asset, tree)


def use(asset, node):
  """Makes a node the current one."""
  tree = load(asset)
  if node != ROOT:
    _find(tree, node)
  tree['current'] = node
  _save(asset, tree)


def filtered(asset, manifest, node=None):
  """The manifest with only the pictures in a node's set (the current node by default), and those of the extra pictures
  under `extra_frames`."""
  keep = set(members(asset, node))
  manifest = dict(manifest)
  for key in ('representative_frames', 'screen_pages'):
    manifest[key] = [item for item in manifest.get(key) or [] if item['path'] in keep]
  if manifest.get('slide_extraction'):
    slides = manifest['slide_extraction'].get('slides') or []
    manifest['slide_extraction'] = {**manifest['slide_extraction'], 'slides': [i for i in slides if i['path'] in keep]}
  manifest['extra_frames'] = [path for path in _extras(asset) if path in keep]
  return manifest


def listing(asset) -> contract.Pictures:
  """Every node with its set and the pictures it leaves out, the root first."""
  asset = Path(asset)
  tree = load(asset)
  every, _ = _universe(asset, tree)
  heads = [(ROOT, None, _manifest(asset).get('updated_utc') or '', '处理', '')] + [
    (item['id'], item['parent'], item['created'], item['source'], item['note']) for item in tree['nodes']
  ]
  nodes: list[contract.PictureNode] = []
  for number, parent, created, source, note in heads:
    chosen = members(asset, number, tree)
    dropped = [path for path in every if path not in set(chosen)]
    nodes.append(
      {
        'id': number,
        'parent': parent,
        'created': created,
        'source': source,
        'note': note,
        'members': chosen,
        'dropped': dropped,
      }
    )
  return {'current': tree['current'], 'nodes': nodes}
