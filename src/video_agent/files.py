"""Writes that readers never see half done, and one writer at a time per video folder.

Which runs may overlap (see ARCHITECTURE.md, "Concurrent jobs"): `process` and `summarize` change shared files in a
video's folder (`transcript.*`, `summary-context.md`, `manifest.json`, `总结.md`), so each holds the folder's lock while
it runs and a second one fails at once instead of waiting. `frame` writes only its own new file and takes no lock, so
an Agent may call it while a summary is being written. Readers (`show`, the GUI) take no lock; every shared file is
replaced in one step, so they see the old or the new version, never a part.
"""

import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

LOCK_NAME = '.lock'
LOCK_WAIT_S = 2.0


class BusyError(RuntimeError):
  pass


def temporary_beside(path, prefix='.'):
  """A unique name in the same folder (so the final rename stays on one drive), hidden from `frame-*.jpg` globs."""
  path = Path(path)
  return path.with_name(f'{prefix}{path.stem}.{uuid.uuid4().hex[:8]}.part{path.suffix}')


def replace(source, target, attempts=10):
  """`os.replace`, retried briefly: on Windows it fails while another process has the target open without sharing
  delete access, as a Python reader does for the moment it reads."""
  for attempt in range(attempts):
    try:
      return os.replace(source, target)
    except PermissionError:
      if attempt == attempts - 1:
        raise
      time.sleep(0.05 * (attempt + 1))


def write_text(path, text):
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = temporary_beside(path)
  try:
    # newline='\n': Windows would write every \n as \r\n, and a text that already had \r\n came out as \r\r\n, which
    # Markdown reads as two line breaks (a code block of an imported summary showed a blank line after every line).
    temporary.write_text(text, encoding='utf-8', newline='\n')
    replace(temporary, path)
  finally:
    temporary.unlink(missing_ok=True)


@contextmanager
def video_lock(asset, action):
  """Holds `<asset>/.lock` for one writer. The operating system releases it when the process ends, even when killed,
  so a stopped job never leaves the folder locked; Windows may take a moment for that, so a taken lock is tried again
  for up to LOCK_WAIT_S seconds before the run gives up."""
  asset = Path(asset)
  asset.mkdir(parents=True, exist_ok=True)
  handle = open(asset / LOCK_NAME, 'a+b')  # noqa: SIM115 - held for the whole block
  try:
    deadline = time.monotonic() + LOCK_WAIT_S
    while True:
      try:
        _lock(handle)
        break
      except OSError:
        if time.monotonic() < deadline:
          time.sleep(0.1)
          continue
        raise BusyError(
          f'Another Video Agent run is changing {asset.name} (process or summarize); wait for it to finish, then '
          f'{action} again'
        ) from None
    try:
      yield
    finally:
      _unlock(handle)
  finally:
    handle.close()


if os.name == 'nt':
  import msvcrt

  # Byte 0 is locked; Windows allows locking past the end of an empty file.
  def _lock(handle):
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

  def _unlock(handle):
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
  import fcntl

  def _lock(handle):
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

  def _unlock(handle):
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
