"""Material for chat AIs on the web, which cannot run commands: the prompt (rules, template, evidence), on its own for
the clipboard, in a zip with the pictures, or in a folder of numbered pictures for a chat AI that takes a limited
number of files. The answer comes back through importer.py; when it asks for pictures in a 画面调整 section, the next
round (`follow_up`) gives the candidates taken and the summary as saved, until it asks for no more.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path

from . import files, media, picture_review, templates
from .evidence import SUMMARY_NAME, clock, frames, pages, plan, processed, video_line, video_name
from .importer import CORRECTIONS_HEADING
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
- 画面是材料，不是配图：表格、图表、文件和政策截图、公式、代码里的内容要读出来写进总结，尤其是讲者没念出来的数字和\
条文。画面链接只放在它确实显示了这一点的地方，不按时间顺手配一张；链接文字写图上是什么，写成 `[<图表、截\
图……>：<图上是什么>](frames/…)`，说不出图上有和这一点相关的内容就不链接；素材画面、空镜、讲者特写不链接。
- 视频以外你补充的内容，每条以「补充：」开头；讲者的说法保留原来的分寸，「不建议」不写成「禁止」。
- 写完对一遍画面：附上的图里和内容无关的（素材、空镜、讲者），在「{picture_review.HEADING}」里写「不用」；再从字幕推测哪\
里屏幕上应该有图而附图里没有（讲者在念一串数字、描述图表或曲线、逐条读文件或条文、说「看这里」「如图」），在那里写「补\
截」和推测的时间段。
- 照模板的各节写，需要时最后加「{CORRECTIONS_HEADING}」「{picture_review.HEADING}」两节；整篇放进一个 ````markdown 代码块。"""

# A chat AI cannot look at the video (user request, 2026-10-29: delete the frames that are no use, add the ones that
# are missing, over several rounds as an Agent would): it says which pictures it does not need and where one is missing.
PICTURES_SECTION = f"""## {picture_review.HEADING}（网页 AI 写在总结最后）

你看不到视频，只看得到附上的画面，附上的也不一定齐。所以写完后要做两件事，结果写在总结最后这一节，每行一条：

- 附上的画面里用不上的（和内容无关的素材、空镜、讲者特写、黑屏），写「不用」。
- 从字幕推测哪里屏幕上应该有图而附图里没有：讲者在念一串数字、描述图表或曲线的走势、逐条读文件或条文、讲解一张图里的\
结构，或者说「看这里」「如图」，而那段时间附上的图里没有对应的画面，就推测那时屏幕上有图，写「补截」和推测的时间段。\
拿不准也可以要，多要几处没关系。

导入时程序会照它处理，再把这一节从总结里去掉：用不上的画面以后不再给你；要补的，程序在那段时间里截几张不同的候选，下一轮\
发给你挑。两件事都没有的就不写这一节。

```markdown
## {picture_review.HEADING}

- 不用：<画面的路径>（<为什么用不上>）
- 补截：<开始 时:分:秒>–<结束 时:分:秒> <这时应该看到什么>
```"""


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
      PICTURES_SECTION if work_dir is not None else '',
      '---',
      (asset / 'summary-context.md').read_text(encoding='utf-8'),
      '---',
      REMINDER,
    )
    if part
  )
  return text, entries


def follow_up(video, workspace, *, work_dir=None, max_files=None):
  """The next round for a chat AI whose summary asked for pictures in a 画面调整 section: the candidates taken, and
  the summary as it was saved (with the transcript corrections applied), to rewrite. Returns (text, entries) as
  `material` does: with `max_files`, numbered pictures; with only `work_dir`, the pictures at their paths in the
  video's folder; without either, none, and the text names the files by their own names."""
  video, _, asset, _ = processed(video, workspace)
  state = picture_review.load(asset)
  draft = asset / state['draft'] if state.get('draft') else None
  if not draft or not draft.is_file():
    raise SummaryError(f'no summary with a {picture_review.HEADING} section has been imported for {video.name}')
  requests = state.get('requests') or []
  if not requests:
    raise SummaryError(f'the summary imported last for {video.name} asked for no pictures; there is no next round')
  taken = [relative for request in requests for relative in request['candidates']]
  if max_files:
    taken = taken[: max_files - 1]
  names = {}
  for number, relative in enumerate(taken, 1):
    if max_files:
      names[relative] = f'{number:03d}-补截-{Path(relative).stem.removeprefix("frame-")}.jpg'
    else:
      names[relative] = relative if work_dir is not None else Path(relative).name
  lines = []
  for request in requests:
    span = f'{clock(request["start_s"])}–{clock(request["end_s"])} {request["what"]}'.rstrip()
    shown = [relative for relative in request['candidates'] if relative in names]
    if shown:
      lines.append(f'- {span}：' + ''.join(f'\n  - {names[relative]}：{relative}' for relative in shown))
    else:
      lines.append(f'- {span}：没有截到（时间超出视频，或者图片太多没有附上）')
  same = all(names[relative] == relative for relative in names)
  where = (
    '下表列出每张图的路径。'
    if same
    else '附件的文件名不是总结里要用的路径：下表左边是文件名，右边是它的路径，链接时写右边的路径。'
  )
  text = '\n\n'.join(
    (
      (
        f'我照你上一稿最后的「{picture_review.HEADING}」截好了图，附上 {len(names)} 张候选。{where}请看过这些图，改写整篇'
        f'总结：\n\n- 候选里有合适的，就链接到总结里讲到它的地方，并把图里的内容读出来写进总结；都不合适就不链接，也可以'
        f'换个时间段再要。\n- 写过「不用」的画面已经去掉，不要再链接。\n- 还要调整就照样在最后写「{picture_review.HEADING}」，'
        f'不用调整就不写这一节。\n\n{OUTPUT_FENCE}'
      ),
      '\n'.join(lines),
      '上一稿（导入后的样子，字幕改正已经照办）：',
      draft.read_text(encoding='utf-8').strip(),
      '---',
      REMINDER,
    )
  )
  return text, [(names[relative], asset / relative) for relative in names] if work_dir is not None else []


def pack(video, workspace, target, *, request='', max_images=40, template=None, follow=False):
  """Writes a zip with 提示词.md, the screen pages, frames and contact sheets, for chat AIs that take files; with
  `follow`, the next round's prompt and candidates (`follow_up`). Returns the zip and the number of pictures in it."""
  target = Path(target)
  target.parent.mkdir(parents=True, exist_ok=True)
  temporary = files.temporary_beside(target)
  try:
    with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
      if follow:
        text, entries = follow_up(video, workspace, work_dir=work_dir)
      else:
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


def pack_folder(video, workspace, parent, *, request='', max_files=50, template=None, follow=False):
  """Writes a new folder in `parent` with 提示词.md and numbered pictures, `max_files` files in all, for chat AIs that
  take files one by one up to a limit and no zip; with `follow`, the next round's (`follow_up`). Returns the folder and
  the number of pictures in it."""
  if max_files < 2:
    raise SummaryError('a folder for a chat AI needs room for the prompt and at least one picture')
  parent = Path(parent)
  name = f'{video_name(Path(video))}-{"下一轮" if follow else ""}材料'
  target = parent / name
  number = 2
  while target.exists():
    target = parent / f'{name} ({number})'
    number += 1
  with tempfile.TemporaryDirectory(prefix='video-agent-') as work_dir:
    if follow:
      text, entries = follow_up(video, workspace, work_dir=work_dir, max_files=max_files)
    else:
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
