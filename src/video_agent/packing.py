"""Material for chat AIs on the web, which cannot run commands: the prompt (rules, template, evidence), on its own for
the clipboard, in a zip with the pictures, or in a folder of numbered pictures for a chat AI that takes a limited
number of files. The answer comes back through importer.py.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

from . import files, media, templates
from .evidence import SUMMARY_NAME, clock, frames, pages, plan, processed, video_line, video_name
from .importer import CAPTURE, CORRECTIONS_HEADING
from .model_api import SummaryError

PROMPT_NAME = '提示词.md'
SHEET_FOLDER = '总图'
PICTURE_KINDS = {'page': '屏幕页', 'sheet': '屏幕页总图', 'frame': '画面'}

# A chat AI is asked to put the whole file in one code block (OUTPUT_FENCE), so its copy button gives the Markdown as
# written; four backticks, so the ``` blocks inside stay inside. Any fence of three or more is taken off on import.
OUTPUT_FENCE = (
  '把整篇内容放在一个 Markdown 代码块里输出：第一行写 ````markdown（四个反引号），最后一行写 ````，'
  '代码块外面不要加任何说明。用四个反引号，正文里的 ``` 代码块就不会把它截断。'
)

# Shown after the template as a section of it, with its form, so a chat AI writes it as it writes the others.
CORRECTIONS_SECTION = f"""## 字幕改正（网页 AI 写在总结最后）

你不能运行命令，所以规则里用 `video-agent fix` 整理字幕的那一步改成在总结最后写这一节：每次出现都识别错的名字、术语，\
每行一条。导入时程序会照它整理字幕（原字幕保留），再把这一节从总结里去掉。只错一次的、错的写法本身也是正常词语的，只在\
总结正文里改，不列进来；没有要改的就不写这一节。

```markdown
## {CORRECTIONS_HEADING}

- 错的写法 → 正确写法
```"""


# After the long evidence, a chat AI has the rules far behind it; DeepSeek's web chat wrote a retelling with mixed-up
# times and pictures from other points, though the rules said otherwise (user, 2026-10-28). The points it missed, once
# more at the end; the rules themselves stay in the template.
REMINDER = f"""写之前，再对一遍上面规则里的这几条：

- 详细内容写成能快速扫读的笔记，不要按讲话顺序逐段复述（「作者说……他还说……」）；每一部分自己判断用几句话、列表、表格还是步骤。
- 各节按视频的先后排，时间范围不交错；每个要点标的时间点就是视频讲到它的时候。
- 画面链接用讲到这一点时屏幕上的那一张：字幕里每段开头的 ▶ 行写着当时的画面。
- 视频以外你补充的内容，每条以「补充：」开头；讲者的说法保留原来的分寸，「不建议」不写成「禁止」。
- 照模板的各节写，需要时最后加「{CORRECTIONS_HEADING}」一节；整篇放进一个 ````markdown 代码块。"""

CAPTURE_NOTE = (
  f'材料里没有你要的画面时（比如讲者说「大家看这张图」，附上的屏幕页和画面里却没有），照常写画面链接，路径写成 '
  f'`{CAPTURE}:时:分:秒`，例如 `[画面]({CAPTURE}:00:12:34)`：导入时程序会在那个时间截图，并把链接换成截下的图。'
)


def numbered_pictures(asset, manifest, budget, work_dir):
  """At most `budget` pictures with numbered names, for a chat AI that takes a limited number of files, and the note
  that says which frames each one shows and which paths to link."""
  chosen, side, dropped = plan(asset, manifest, budget, work_dir)
  entries, lines = [], []
  for number, (kind, path, shown) in enumerate(chosen, 1):
    name = f'{number:03d}-{PICTURE_KINDS[kind]}-{clock(shown[0][0]).replace(":", "-")}.jpg'
    entries.append((name, path))
    lines.append(f'- {name}：' + '、'.join(f'{clock(second)} {relative}' for second, relative in shown))
  page_count = sum(len(shown) for kind, _, shown in chosen if kind != 'frame')
  frame_count = sum(kind == 'frame' for kind, _, _ in chosen)
  sheets = ''
  if side > 1:
    count = sum(kind == 'sheet' for kind, _, _ in chosen)
    sheets = f'，拼在 {count} 张总图里（每张 {side}×{side} 页，从左到右、从上到下）'
  note = (
    f'我附上了 {len(entries)} 张图片：这个视频的 {page_count} 张屏幕页（幻灯片、代码、文档）{sheets}，'
    f'和 {frame_count} 张整幅画面。'
    '上传后的文件名不是总结里要用的路径：下表左边是图片的文件名，右边是它显示的画面的时间和路径（总图按顺序列出'
    '每一页）。写总结时链接右边的路径，链接到画面所在的那一页；没有出现在表里的画面不要链接。'
  )
  if dropped:
    note += f'屏幕页太多，有 {dropped} 页没有附上，材料里提到它们时你看不到。'
  return entries, note + '\n\n' + '\n'.join(lines)


def material(video, workspace, *, request='', max_images=40, work_dir=None, max_files=None, template=None):
  """The prompt for a chat AI: rules, template and the evidence. With `work_dir`, also the files that go along as
  (path in the zip, file): every screen page and up to `max_images` other frames, at their paths in the video's folder
  (so links written from the evidence still work once the summary is imported there), and 2x2 contact sheets of the
  pages in SHEET_FOLDER for chat AIs that take few images. With `max_files` as well, at most that many files with the
  prompt: numbered pictures in one folder, as `numbered_pictures` chooses them."""
  video, info, asset, manifest = processed(video, workspace)
  shown = pages(manifest)
  found = frames(asset, manifest, max_images)
  entries, notes = [], []
  if work_dir is not None:
    notes.append(CAPTURE_NOTE)
  if work_dir is None:
    notes.append('这次没有附上画面，材料里列出的屏幕页和画面你看不到：不要描述画面内容，也不要链接画面。')
  elif max_files:
    entries, note = numbered_pictures(asset, manifest, max_files - 1, Path(work_dir))
    notes.append(note)
  else:
    entries = [(relative, asset / relative) for _, relative in shown + found]
    notes.append(
      f'我附上了这个视频的 {len(shown)} 张屏幕页（幻灯片、代码、文档，每页一张）和 {len(found)} 张整幅画面，'
      '文件名里带时间点。下面材料引用它们时写的是 frames/… 的相对路径：看图时按文件名对应，写总结时照材料里的相对'
      '路径链接，不要只写文件名。没有附上的画面不要链接。'
    )
    if shown:
      sheets = media.sheets([asset / relative for _, relative in shown], 2, Path(work_dir))
      lines = []
      for index, sheet in enumerate(sheets, 1):
        name = f'{SHEET_FOLDER}/{SHEET_FOLDER}-{index:03d}.jpg'
        entries.append((name, sheet))
        group = shown[(index - 1) * 4 : index * 4]
        lines.append(f'- {name}：' + '、'.join(f'{clock(second)} {relative}' for second, relative in group))
      notes.append(
        f'如果一次收不了这么多图片，就看 {SHEET_FOLDER}/ 里的 {len(sheets)} 张总图：每张拼了 4 页屏幕页，从左到右、'
        '从上到下，对应下表。链接时仍写原来的屏幕页路径。\n\n' + '\n'.join(lines)
      )
  text = '\n\n'.join(
    part
    for part in (
      f'请按下面的规则和模板，为这个视频写 {SUMMARY_NAME}（Markdown）。{OUTPUT_FENCE}',
      f'我的要求：{request}' if request else '',
      *notes,
      f'「视频」那一行的开头照抄：{video_line(video, media.duration(info))}',
      templates.text(template),
      CORRECTIONS_SECTION,
      '---',
      (asset / 'summary-context.md').read_text(encoding='utf-8'),
      '---',
      REMINDER,
    )
    if part
  )
  return text, entries


def pack(video, workspace, target, *, request='', max_images=40, template=None):
  """Writes a zip with 提示词.md, the screen pages, frames and contact sheets, for chat AIs that take files. Returns
  the zip and the number of pictures in it."""
  target = Path(target)
  target.parent.mkdir(parents=True, exist_ok=True)
  temporary = files.temporary_beside(target)
  try:
    with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
      text, entries = material(
        video, workspace, request=request, max_images=max_images, work_dir=work_dir, template=template
      )
      with zipfile.ZipFile(temporary, 'w') as archive:
        archive.writestr(PROMPT_NAME, text, compress_type=zipfile.ZIP_DEFLATED)
        for name, path in entries:
          archive.write(path, name)  # JPEG does not compress further
    files.replace(temporary, target)
  finally:
    temporary.unlink(missing_ok=True)
  return target, len(entries)


def pack_folder(video, workspace, parent, *, request='', max_files=50, template=None):
  """Writes a new folder in `parent` with 提示词.md and numbered pictures, `max_files` files in all, for chat AIs that
  take files one by one up to a limit and no zip. Returns the folder and the number of pictures in it."""
  if max_files < 2:
    raise SummaryError('a folder for a chat AI needs room for the prompt and at least one picture')
  parent = Path(parent)
  name = f'{video_name(Path(video))}-材料'
  target = parent / name
  number = 2
  while target.exists():
    target = parent / f'{name} ({number})'
    number += 1
  with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
    text, entries = material(
      video, workspace, request=request, work_dir=work_dir, max_files=max_files, template=template
    )
    temporary = files.temporary_beside(target)
    try:
      temporary.mkdir(parents=True)
      files.write_text(temporary / PROMPT_NAME, text)
      for picture, path in entries:
        shutil.copyfile(path, temporary / picture)
      temporary.rename(target)
    finally:
      shutil.rmtree(temporary, ignore_errors=True)
  return target, len(entries)
