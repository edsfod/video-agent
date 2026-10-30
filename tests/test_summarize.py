"""summarize against fake Anthropic and OpenAI-compatible servers, including one round of the frame tool."""

import io
import json
import re
import tempfile
import zipfile
from pathlib import Path

import pytest

from video_agent.evidence import evidence_images, video_line
from video_agent.model_api import SummaryError, list_models
from video_agent.packing import numbered_pictures
from video_agent.processor import asset_folder, process_video
from video_agent.summarize import summarize_video
from video_agent.templates import text as template

SUMMARY = '# 测试视频\n\n## 概要\n\n一段测试视频，`00:00:03` 展示图表。[画面](frames/extra/frame-00-00-03.jpg)\n'


@pytest.fixture
def processed(sample_video, tmp_path):
  workspace = tmp_path / 'work'
  process_video(sample_video, workspace, interval=2, max_frames=6, status=lambda message: None)
  return sample_video, workspace


def config(provider, url):
  base = url if provider == 'anthropic' else f'{url}/v1'
  return {'provider': provider, 'model': 'test-model', 'base_url': base}


def test_the_model_list_costs_no_tokens_and_effort_is_sent_only_when_chosen(processed, fake_model, no_proxy):
  video, workspace = processed
  reply = {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': SUMMARY}]}
  server = fake_model([reply, reply], models=['claude-b', 'claude-a'])
  assert list_models(config('anthropic', server.url), 'secret') == ['claude-a', 'claude-b']
  assert server.requests[0]['path'] == '/v1/models?limit=1000'
  assert server.requests[0]['headers']['x-api-key'] == 'secret'
  summarize_video(video, workspace, config('anthropic', server.url), 'secret', status=lambda message: None)
  plain = server.requests[-1]['body']
  assert 'thinking' not in plain and plain['max_tokens'] == 16000
  chosen = config('anthropic', server.url) | {'effort': 'medium'}
  summarize_video(video, workspace, chosen, 'secret', overwrite=True, status=lambda message: None)
  assert server.requests[-1]['body']['thinking'] == {'type': 'enabled', 'budget_tokens': 8000}
  assert server.requests[-1]['body']['max_tokens'] == 24000

  openai = fake_model([{'choices': [{'message': {'role': 'assistant', 'content': SUMMARY}}]}], models=['m-2', 'm-1'])
  assert list_models(config('openai', openai.url), '') == ['m-1', 'm-2']
  assert openai.requests[0]['path'] == '/v1/models'
  summarize_video(
    video, workspace, config('openai', openai.url) | {'effort': 'high'}, '', overwrite=True, status=lambda m: None
  )
  assert openai.requests[-1]['body']['reasoning_effort'] == 'high'


def test_anthropic_tool_round(processed, fake_model, no_proxy):
  video, workspace = processed
  server = fake_model(
    [
      {
        'stop_reason': 'tool_use',
        'content': [
          {'type': 'text', 'text': 'Let me look.'},
          {'type': 'tool_use', 'id': 'call-1', 'name': 'frame', 'input': {'time': '00:00:03'}},
        ],
      },
      {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': f'```markdown\n{SUMMARY}```'}]},
    ]
  )
  target = summarize_video(video, workspace, config('anthropic', server.url), 'secret', status=lambda message: None)

  assert target.read_text(encoding='utf-8') == SUMMARY
  asset = asset_folder(workspace, video.resolve())
  assert (asset / 'frames' / 'extra' / 'frame-00-00-03.jpg').is_file()
  first, second = (request['body'] for request in server.requests)
  assert server.requests[0]['path'] == '/v1/messages'
  assert server.requests[0]['headers']['x-api-key'] == 'secret'
  assert first['system'] == template()
  assert first['tools'][0]['name'] == 'frame'
  assert sum(block['type'] == 'image' for block in first['messages'][0]['content']) >= 2
  assert '我们看看这张图表' in first['messages'][0]['content'][0]['text']
  result = second['messages'][-1]['content'][0]
  assert result['type'] == 'tool_result' and result['tool_use_id'] == 'call-1' and not result['is_error']
  assert [block['type'] for block in result['content']] == ['text', 'image']


def test_openai_tool_round_sends_image_after_tool_message(processed, fake_model, no_proxy):
  video, workspace = processed
  server = fake_model(
    [
      {
        'choices': [
          {
            'message': {
              'role': 'assistant',
              'content': None,
              'tool_calls': [
                {
                  'id': 'call-9',
                  'type': 'function',
                  'function': {'name': 'frame', 'arguments': json.dumps({'time': '3'})},
                },
              ],
            }
          }
        ]
      },
      {'choices': [{'message': {'role': 'assistant', 'content': SUMMARY}}]},
    ]
  )
  summarize_video(video, workspace, config('openai', server.url), None, status=lambda message: None)

  assert server.requests[0]['path'] == '/v1/chat/completions'
  assert 'Authorization' not in server.requests[0]['headers']
  messages = server.requests[1]['body']['messages']
  assert [message['role'] for message in messages] == ['system', 'user', 'assistant', 'tool', 'user']
  assert messages[3]['tool_call_id'] == 'call-9'
  assert messages[4]['content'][1]['type'] == 'image_url'


def test_frame_limit_and_bad_time_are_reported_to_the_model(processed, fake_model, no_proxy):
  video, workspace = processed
  server = fake_model(
    [
      {
        'stop_reason': 'tool_use',
        'content': [
          {'type': 'tool_use', 'id': 'a', 'name': 'frame', 'input': {'time': '99:00'}},
        ],
      },
      {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': SUMMARY}]},
    ]
  )
  summarize_video(video, workspace, config('anthropic', server.url), 'k', status=lambda message: None)
  result = server.requests[1]['body']['messages'][-1]['content'][0]
  assert result['is_error'] and 'outside the video' in result['content'][0]['text']


def test_no_tools_and_a_second_summary_is_kept_beside_the_first(processed, fake_model, no_proxy):
  video, workspace = processed
  reply = {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': SUMMARY}]}
  server = fake_model([reply, {**reply, 'content': [{'type': 'text', 'text': '# 第二版\n\n' + '内容' * 30}]}])
  first = summarize_video(
    video, workspace, config('anthropic', server.url), 'k', use_tools=False, status=lambda m: None
  )
  assert 'tools' not in server.requests[0]['body']
  second = summarize_video(video, workspace, config('anthropic', server.url), 'k', status=lambda message: None)
  assert first.name == '总结.md' and first.read_text(encoding='utf-8') == SUMMARY, 'the current one stays'
  assert second.name.startswith('总结 (') and second.read_text(encoding='utf-8').startswith('# 第二版')


def test_requires_processing_first(sample_video, tmp_path):
  with pytest.raises(SummaryError, match='run process'):
    summarize_video(
      sample_video, tmp_path / 'empty', config('anthropic', 'http://127.0.0.1:9'), 'k', status=lambda message: None
    )


def test_a_running_writer_blocks_process_and_summarize_but_not_frame(processed, capsys):
  from video_agent import cli, files

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  with files.video_lock(asset, 'test'):
    assert cli.main(['process', str(video), '-o', str(workspace), '--json']) == 1
    assert 'Another Video Agent run is changing' in json.loads(capsys.readouterr().out)['error']
    with pytest.raises(files.BusyError):
      summarize_video(video, workspace, config('openai', 'http://127.0.0.1:9'), None, status=lambda message: None)
    assert cli.main(['frame', str(video), '3', '-o', str(workspace)]) == 0
  assert [path.name for path in (asset / 'frames' / 'extra').iterdir()] == ['frame-00-00-03.jpg']
  assert not list(asset.rglob('*.part*'))


def test_video_line_reads_like_a_title():
  video = 'C:/下载/Agent-native 开发 [08-Raw⧸26生成式软件工程⧸NJU] [BV11LWw6VEHW].mp4'
  assert video_line(video, 5829.4) == (
    '视频：Agent-native 开发 [08-Raw/26生成式软件工程/NJU] [BV11LWw6VEHW] · '
    '[打开视频](<C:/下载/Agent-native 开发 [08-Raw⧸26生成式软件工程⧸NJU] [BV11LWw6VEHW].mp4>) · 时长：1:37:09'
  )
  assert video_line('C:/v/clip.mp4', 65).endswith('时长：1:05')


def test_imports_never_lose_a_summary_and_versions_can_be_chosen(processed, monkeypatch, capsys):
  from video_agent import cli

  video, workspace = processed
  pasted = f'```markdown\n{SUMMARY}```\n'
  monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(pasted.encode('utf-8'))))
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', '-', '--note', 'Gemini']) == 0
  target = asset_folder(workspace, video.resolve()) / '总结.md'
  assert target.read_text(encoding='utf-8') == SUMMARY
  again = workspace / 'again.md'
  again.write_text('# 第二版\n\n' + '内容' * 30, encoding='utf-8')
  capsys.readouterr()
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', str(again), '--source', '网页 AI']) == 0
  assert target.read_text(encoding='utf-8') == SUMMARY, 'a second import does not replace the current summary'
  assert 'make it current with' in capsys.readouterr().err

  def listing():
    assert cli.main(['versions', str(video), '-o', str(workspace), '--json']) == 0
    return json.loads(capsys.readouterr().out)

  found = listing()
  assert (found['current']['note'], found['current']['source']) == ('Gemini', '导入')
  [kept] = found['versions']
  assert kept['source'] == '网页 AI'
  assert cli.main(['versions', str(video), '-o', str(workspace), '--use', kept['file']]) == 0
  capsys.readouterr()
  assert target.read_text(encoding='utf-8').startswith('# 第二版')
  found = listing()
  assert found['current']['source'] == '网页 AI'
  [old] = found['versions']
  assert old['note'] == 'Gemini' and (target.parent / old['file']).read_text(encoding='utf-8') == SUMMARY
  assert cli.main(['versions', str(video), '-o', str(workspace), '--note', old['file'], '第一版']) == 0
  capsys.readouterr()
  assert listing()['versions'][0]['note'] == '第一版'
  assert cli.main(['versions', str(video), '-o', str(workspace), '--delete', old['file']]) == 0
  capsys.readouterr()
  assert listing()['versions'] == [] and not (target.parent / old['file']).exists()


def test_import_repairs_rewritten_links_the_video_line_and_takes_corrections(processed):
  from video_agent import corrections
  from video_agent.importer import import_summary

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  page = next(asset.glob('frames/*/screen/*.jpg')).relative_to(asset).as_posix()
  text = (
    '# 标题\n\n视频：别的名字 · 打开视频 · 时长：0:08 · 字幕：[transcript.txt](https://www.google.com/search?q=transcript.txt)\n\n'
    f'- 一点 [画面](https://www.google.com/search?q={page})，另一点 [画面](sandbox:/mnt/data/material/{page})\n'
    '- 外链 [官网](https://example.com/?q=frames/none.jpg) 不动\n\n'
    '## 字幕改正\n\n- 测试画面 → 测试图像\n- `彩色` -> `彩色的`\n'
  )
  target, pairs = import_summary(video, workspace, text, source='网页 AI')
  saved = target.read_text(encoding='utf-8')
  assert f'[画面]({page})，另一点 [画面]({page})' in saved
  assert '[transcript.txt](transcript.txt)' in saved and 'https://example.com/?q=frames/none.jpg' in saved
  assert '[打开视频](<' in saved and '别的名字' not in saved
  assert '字幕改正' not in saved
  assert pairs == [('测试画面', '测试图像'), ('彩色', '彩色的')]
  assert corrections.load(asset) == pairs
  assert (asset / 'transcript.clean.srt').is_file()


def test_pack_zips_the_prompt_with_frames_at_their_folder_paths(processed, capsys):
  from video_agent import cli

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  assert cli.main(['frame', str(video), '3', '-o', str(workspace)]) == 0
  target = workspace / 'out' / 'material.zip'
  assert cli.main(['pack', str(video), '-o', str(workspace), '--zip', str(target), '--request', '写短一点']) == 0
  with zipfile.ZipFile(target) as archive:
    names = archive.namelist()
    prompt = archive.read('提示词.md').decode('utf-8')
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  pages = [page['path'] for page in manifest['screen_pages']]
  sheets = [name for name in names if name.startswith('总图/')]
  frames = [name for name in names if name != '提示词.md' and name not in sheets]
  assert pages and set(pages) <= set(frames), 'every screen page goes into the zip'
  assert 'frames/extra/frame-00-00-03.jpg' in frames
  assert all((asset / name).is_file() for name in frames), 'zip paths are the folder paths the evidence links'
  assert f'附上了这个视频的 {len(pages)} 张屏幕页' in prompt
  assert sheets == [f'总图/总图-{index:03d}.jpg' for index in range(1, -(-len(pages) // 4) + 1)]
  first = manifest['screen_pages'][0]
  assert f'- 总图/总图-001.jpg：#1 00:00:{round(first["time_s"]):02d} {first["path"]}' in prompt
  assert '左下角印着编号和时间' in prompt, 'each picture carries its number'
  assert '我的要求：写短一点' in prompt
  assert '「视频」那一行的开头照抄：视频：sample clip [test] · [打开视频]' in prompt
  assert '我们看看这张图表' in prompt and '# Writing a video summary' in prompt
  # The 字幕改正 section comes after the template with its form, like the template's own sections (user, 2026-10-28).
  assert prompt.index('# Writing a video summary') < prompt.index('## 字幕改正\n\n- 错的写法 → 正确写法')
  # The points a chat AI missed come once more after the evidence, and the transcript marks the page on screen.
  assert prompt.rstrip().endswith('整篇放进一个 ````markdown 代码块。') and re.search(
    r'▶ (screen page|frame) from 00:00:0\d: frames/', prompt
  )

  capsys.readouterr()
  assert cli.main(['pack', str(video), '-o', str(workspace)]) == 0
  assert '这次没有附上画面' in capsys.readouterr().out


def test_pack_folder_fits_the_prompt_and_numbered_pictures_in_a_file_limit(processed, capsys):
  from video_agent import cli

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  page = manifest['screen_pages'][0]
  out = workspace / 'out'
  for _ in range(2):  # a second export goes into a new folder beside the first
    assert cli.main(['pack', str(video), '-o', str(workspace), '--folder', str(out), '--max-files', '3']) == 0
  first, second = sorted(out.iterdir())
  assert first.name == 'sample clip [test]-材料' and second.name == 'sample clip [test]-材料 (2)'
  names = sorted(path.name for path in first.iterdir())
  # The page alone, every frame on a sheet: none is left out to fit.
  assert len(names) == 3 and names[0].startswith('001-屏幕页-') and names[1].startswith('002-画面总图-')
  assert names[2] == '提示词.md'
  prompt = (first / '提示词.md').read_text(encoding='utf-8')
  assert all(frame['path'] in prompt for frame in manifest['representative_frames'])
  assert '整幅画面，拼在 1 张总图里（每张 2×2 张' in prompt and '没有附上' not in prompt
  assert '分屏、画中画）仍是同一张图' in prompt and '链接打开的是那张图的原图' in prompt
  assert f'- {names[0]}：#1 00:00:{round(page["time_s"]):02d} {page["path"]}' in prompt
  assert '链接右边的路径' in prompt and '我们看看这张图表' in prompt
  with pytest.raises(SystemExit):
    cli.main(['pack', str(video), '-o', str(workspace), '--folder', str(out), '--max-files', '1'])
  assert 'room for the prompt' in capsys.readouterr().err


def test_screen_pages_and_frames_go_on_contact_sheets_when_they_exceed_the_budget(tmp_path):
  import subprocess

  from video_agent import media

  screen = tmp_path / 'frames' / 'run' / 'screen'
  screen.mkdir(parents=True)
  subprocess.run(
    [
      media.tool('ffmpeg'),
      '-v',
      'error',
      '-filter_complex',
      'testsrc=s=320x180:r=1:d=30[v]',
      '-map',
      '[v]',
      str(screen / 'p-%03d.jpg'),
    ],
    check=True,
  )
  pages = [{'time_s': float(index * 10), 'path': f'frames/run/screen/p-{index + 1:03d}.jpg'} for index in range(30)]
  manifest = {'screen_pages': pages, 'representative_frames': []}

  alone, dropped = evidence_images(tmp_path, manifest, 40, tmp_path / 'a')
  assert len(alone) == 30 and dropped == 0 and alone[0][0].startswith('Screen page at 00:00:00')

  sheets, dropped = evidence_images(tmp_path, manifest, 12, tmp_path / 'b')
  assert len(sheets) == 8 and dropped == 0
  assert sheets[0][0].startswith('Screen pages 1-4 on one sheet, 2 per row')
  assert sheets[-1][0].startswith('Screen pages 29-30 on one sheet')

  squeezed, dropped = evidence_images(tmp_path, manifest, 3, tmp_path / 'c')
  assert len(squeezed) == 3 and dropped == 3 and '3 per row' in squeezed[0][0]

  # Frames as well: the pages stay larger than the frames, and none is thinned out while sheets fit.
  frames = [{'time_s': float(index), 'path': f'frames/run/screen/p-{index % 30 + 1:03d}.jpg'} for index in range(40)]
  both, dropped = evidence_images(tmp_path, {**manifest, 'representative_frames': frames}, 13, tmp_path / 'e')
  labels = [label for label, _ in both]
  assert len(both) == 13 and dropped == 0
  assert sum(label.startswith('Screen pages') and '2 per row' in label for label in labels) == 8
  assert sum(label.startswith('Frames') and '3 per row' in label for label in labels) == 5
  assert labels[8].startswith('Frames 1-9 on one sheet') and labels[-1].startswith('Frames 37-40 on one sheet')

  # The same choice with numbered names, for a chat AI that takes few files
  entries, note, _ = numbered_pictures(tmp_path, manifest, 12, tmp_path / 'd')
  assert [name for name, _ in entries][:2] == ['001-屏幕页总图-00-00-00.jpg', '002-屏幕页总图-00-00-40.jpg']
  assert len(entries) == 8 and '30 张屏幕页（幻灯片、代码、文档），拼在 8 张总图里（每张 2×2 页' in note
  assert (
    '- 008-屏幕页总图-00-04-40.jpg：#29 00:04:40 frames/run/screen/p-029.jpg、#30 00:04:50 frames/run/screen/p-030.jpg'
    in note
  )


def test_the_users_copy_of_a_template_is_used_and_knows_when_the_built_in_one_changed(capsys):
  from video_agent import cli, templates

  assert cli.main(['template', '--info']) == 0
  assert json.loads(capsys.readouterr().out)['customized'] is False
  assert cli.main(['template', '--edit']) == 0
  info = json.loads(capsys.readouterr().out)
  copy = Path(info['path'])
  assert info['customized'] and not info['outdated'] and Path(info['default']).is_file()
  copy.write_text(copy.read_text(encoding='utf-8') + '\n- 全部用英文写。\n', encoding='utf-8')
  assert template().endswith('- 全部用英文写。\n') and not template().startswith('<!--')
  assert cli.main(['template']) == 0
  assert capsys.readouterr().out.endswith('- 全部用英文写。\n')

  original = templates.built_in
  templates.built_in = lambda name: original(name) + '\n新规则\n'
  try:
    assert templates.info()['outdated'] is True
    assert cli.main(['template']) == 0
    assert 'older version' in capsys.readouterr().err
    assert templates.accept()['outdated'] is False
    assert template().endswith('- 全部用英文写。\n'), 'accepting keeps the copy as it is'
  finally:
    templates.built_in = original
  assert templates.reset()['customized'] is False
  assert template() == templates.built_in(templates.STANDARD)


def test_several_templates_one_chosen_and_one_named_per_summary(processed, capsys):
  from video_agent import cli, templates

  assert cli.main(['template', '--list']) == 0
  listed = json.loads(capsys.readouterr().out)
  assert [entry['name'] for entry in listed] == ['标准', '命题分析']
  assert [entry['current'] for entry in listed] == [True, False]
  assert '论证结构' in templates.text('命题分析') and '论证结构' not in template()

  assert cli.main(['template', '命题分析', '--copy', '我的']) == 0
  assert json.loads(capsys.readouterr().out)['builtin'] is False
  with pytest.raises(templates.TemplateError):
    templates.copy('标准', '我的')
  with pytest.raises(templates.TemplateError):
    templates.copy('标准', 'a/b')
  assert cli.main(['template', '我的', '--use']) == 0
  capsys.readouterr()
  assert template() == templates.text('命题分析')

  video, workspace = processed
  assert cli.main(['pack', str(video), '-o', str(workspace)]) == 0
  assert '论证结构' in capsys.readouterr().out
  assert cli.main(['pack', str(video), '-o', str(workspace), '--template', '标准']) == 0
  assert '论证结构' not in capsys.readouterr().out
  with pytest.raises(SystemExit):
    cli.main(['pack', str(video), '-o', str(workspace), '--template', '没有这个'])
  assert 'template --list' in capsys.readouterr().err

  assert templates.reset('我的') == {'name': '我的', 'deleted': True}
  assert templates.current() == '标准'


def test_the_one_copy_from_before_moves_into_the_templates(capsys):
  from video_agent import settings, templates

  old = settings.settings_path().parent / 'summary.md'
  old.parent.mkdir(parents=True, exist_ok=True)
  old.write_text('<!-- video-agent default: 0123456789ab -->\r\n' + templates.built_in('命题分析'), encoding='utf-8')
  assert templates.current() == '命题分析' and not old.exists(), 'a copy that is a built-in word for word chooses it'

  old.write_text('<!-- video-agent default: 0123456789ab -->\n# 我自己的规则\n', encoding='utf-8')
  assert templates.text('标准') == '# 我自己的规则\n', 'any other copy becomes the copy of the standard one'
  assert not old.exists() and templates.info('标准')['outdated'] is True


def test_imported_windows_line_endings_stay_single(processed):
  from video_agent.importer import import_summary

  video, workspace = processed
  text = '# 标题\r\n\r\n## 概要\r\n\r\n```\r\n  [Intent]\r\n     |\r\n  [Spec]\r\n```\r\n' + '内容' * 30 + '\r\n'
  target, _ = import_summary(video, workspace, text)
  saved = target.read_bytes()
  assert b'\r' not in saved
  assert b'```\n  [Intent]\n     |\n  [Spec]\n```' in saved
  again, _ = import_summary(video, workspace, saved.decode('utf-8'), overwrite=True)
  assert again.read_bytes() == saved, 'importing a saved summary again changes nothing'


def test_a_draft_beside_the_summary_is_imported_and_removed(processed, capsys):
  from video_agent import cli

  video, workspace = processed
  with pytest.raises(SystemExit):
    cli.main(['summarize', str(video), '-o', str(workspace), '--import'])
  assert 'no draft at' in capsys.readouterr().err
  draft = asset_folder(workspace, video.resolve()) / '总结.draft.md'
  draft.write_text(SUMMARY, encoding='utf-8')
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', '--source', 'Claude Code']) == 0
  assert (draft.parent / '总结.md').read_text(encoding='utf-8') == SUMMARY and not draft.exists()


def test_the_code_block_a_chat_ai_puts_the_summary_in_is_taken_off():
  from video_agent.importer import clean

  inner = '# 标题\n\n```python\nprint(1)\n```\n'
  assert clean(f'````markdown\n{inner}````') == inner  # four backticks, as the material asks (user, 2026-10-28)
  assert clean('```md\n# 标题\n```') == '# 标题\n'
  assert clean(inner) == inner  # a summary that starts and ends otherwise is left as it is


def test_an_old_context_gets_the_picture_marks_without_processing_again(processed, capsys):
  from video_agent import cli

  video, workspace = processed
  context = asset_folder(workspace, video.resolve()) / 'summary-context.md'
  context.write_text(
    '# Video summary context\n\n## Transcript\n\n[00:00:00] 旧的\n', encoding='utf-8'
  )  # as 0.8.3 wrote
  assert cli.main(['pack', str(video), '-o', str(workspace)]) == 0
  assert 'Lines are grouped under the' in context.read_text(encoding='utf-8')
  assert '▶ ' in capsys.readouterr().out


def test_frames_a_chat_ai_asks_for_are_taken_on_import(processed):
  from video_agent.importer import import_summary

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  text = (
    '# 标题\n\n视频：x · 时长：0:08\n\n'
    '- 图表 [画面](补截:00:00:05)，搜索包着的 [画面](https://www.google.com/search?q=补截:0:06)，超出的 [画面](补截:00:09:00)\n'
  )
  said = []
  target, _ = import_summary(video, workspace, text, status=said.append)
  saved = target.read_text(encoding='utf-8')
  assert '[画面](frames/extra/frame-00-00-05.jpg)' in saved and '[画面](frames/extra/frame-00-00-06.jpg)' in saved
  assert (asset / 'frames' / 'extra' / 'frame-00-00-05.jpg').is_file()
  assert '[画面](补截失败:00:09:00)' in saved and any('outside the video' in line for line in said)


def test_the_picture_section_is_read_in_the_forms_chat_ais_write():
  from video_agent import picture_review

  text = (
    '# 标题\n\n正文\n\n## 画面调整\n\n'
    '- 不用：[画面](frames/run/frame-001-00-00-00.jpg)、`frames/run/screen/page-002-00-00-04.jpg`（素材）\n'
    '* 补截：`00:01:10` 至 `00:01:30`，流感阳性率的折线图\n'
    '- 补截：1:02:03 讲者举起的书\n'
    '- 别的话\n\n## 字幕改正\n\n- a → b\n'
  )
  rest, unused, wanted = picture_review.take(text)
  assert rest == '# 标题\n\n正文\n\n## 字幕改正\n\n- a → b\n'
  assert unused == ['frames/run/frame-001-00-00-00.jpg', 'frames/run/screen/page-002-00-00-04.jpg']
  assert wanted == [(70, 90, '流感阳性率的折线图'), (3723, 3733, '讲者举起的书')]
  assert picture_review.take('# 标题\n\n正文\n') == ('# 标题\n\n正文\n', [], [])


def test_a_chat_ai_drops_pictures_and_asks_for_others_over_rounds(processed, capsys):
  from video_agent import cli, picture_review, pictures

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  dropped = manifest['representative_frames'][0]['path']
  linked = manifest['representative_frames'][1]['path']
  answer = workspace / 'answer.md'
  answer.write_text(
    f'# 标题\n\n视频：x · 时长：0:08\n\n- 一点 `00:00:01`，讲了彩条和测试图案各自的用途 [画面]({linked})\n\n'
    f'## 画面调整\n\n- 不用：`{dropped}`（素材画面）\n- 不用：`{linked}`（也链接了）\n'
    '- 补截：00:00:01–00:00:06 彩条\n- 补截：00:09:00 超出的\n',
    encoding='utf-8',
  )
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', str(answer)]) == 0
  told = capsys.readouterr().err
  assert '--follow-up' in told and '下一轮：复查上一稿；2 处补截的候选' in told
  assert '画面调整' not in (asset / '总结.md').read_text(encoding='utf-8')
  state = picture_review.load(asset)
  kept = pictures.members(asset)
  assert dropped not in kept and linked in kept, 'a picture the summary links stays in use'
  wanted, beyond = state['requests']
  assert 1 <= len(wanted['candidates']) <= picture_review.CANDIDATES
  assert all((asset / path).is_file() for path in wanted['candidates']) and beyond['candidates'] == []
  # Dropped pictures are offered to no one again.
  assert dropped not in (asset / 'summary-context.md').read_text(encoding='utf-8')
  first = workspace / 'first.zip'
  assert cli.main(['pack', str(video), '-o', str(workspace), '--zip', str(first)]) == 0
  with zipfile.ZipFile(first) as archive:
    assert dropped not in archive.namelist()

  # The next round: the candidates at their paths and the summary as saved.
  following = workspace / 'next.zip'
  assert cli.main(['pack', str(video), '-o', str(workspace), '--follow-up', '--zip', str(following)]) == 0
  with zipfile.ZipFile(following) as archive:
    names = archive.namelist()
    prompt = archive.read('提示词.md').decode('utf-8')
  assert sorted(names) == sorted(['提示词.md', *wanted['candidates']])
  assert '00:00:01–00:00:06 彩条：\n  - frames/extra/' in prompt and '00:09:00–00:09:10 超出的：没有截到' in prompt
  assert '- 一点 `00:00:01`，讲了' in prompt and prompt.rstrip().endswith('整篇放进一个 ````markdown 代码块。')
  assert '请对照前面的字幕复查上一稿' in prompt and '模板里的「概要」' in prompt
  capsys.readouterr()
  assert cli.main(['pack', str(video), '-o', str(workspace), '--follow-up', '--folder', str(workspace / 'out')]) == 0
  folder = next((workspace / 'out').iterdir())
  assert folder.name == 'sample clip [test]-下一轮材料'
  assert min(path.name for path in folder.iterdir()).startswith('001-补截-00-00-0')

  # A 复查 that still adds something goes round again; one that changes nothing in the draft, with nothing wanted and
  # the checks passed, ends the rounds.
  body = '# 标题\n\n视频：x · 时长：0:08\n\n## 概要\n\n用上了候选，讲了彩条和测试图案各自的用途。\n\n## 详细内容\n\n- 彩条\n\n'
  done = '## 画面调整\n\n无\n\n## 复查\n\n- 删掉的节：要点、时间线、需留意、需确认（测试视频只有 8 秒）\n'
  answer.write_text(body + done + '- 补上：`00:00:03` 测试图案\n', encoding='utf-8')
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', str(answer), '--make-current']) == 0
  told = capsys.readouterr().err
  assert '复查：补上 1 处，改正 0 处，稿子和上一稿相比改了' in told and '--follow-up' in told and '检查' not in told
  # Corrections listed in a draft equal to the one before change nothing (DeepSeek, 2026-10-30): the rounds end.
  answer.write_text(body + done + '- 改正：复核了所有时间点，确认无遗漏\n', encoding='utf-8')
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', str(answer), '--make-current']) == 0
  told = capsys.readouterr().err
  assert '改正 1 处，但稿子和上一稿一样' in told and '--follow-up' not in told
  assert dropped not in pictures.members(asset), 'what was dropped stays dropped'
  # Every picture again from the root of the tree, and the dropped one back by hand.
  assert cli.main(['pictures', str(video), '-o', str(workspace), '--use', '0']) == 0
  assert dropped in (asset / 'summary-context.md').read_text(encoding='utf-8')
  capsys.readouterr()
  with pytest.raises(SystemExit):
    cli.main(['pack', str(video), '-o', str(workspace), '--follow-up'])
  assert 'no next round' in capsys.readouterr().err


def test_a_next_round_in_a_new_conversation_carries_what_it_needs(processed, capsys):
  from video_agent import cli, packing, pictures

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  kept = manifest['representative_frames'][1]['path']
  answer = workspace / 'answer.md'
  answer.write_text(
    f'# 标题\n\n视频：x · 时长：0:08\n\n- 一点 `00:00:01`，上一稿特有的句子，讲了彩条和测试图案 [画面]({kept})\n\n'
    '## 画面调整\n\n- 补截：00:00:01–00:00:06 彩条\n',
    encoding='utf-8',
  )
  with tempfile.TemporaryDirectory() as work_dir:
    packing.material(video, workspace, work_dir=work_dir)  # every picture sent, so the one linked is what stays
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', str(answer)]) == 0
  assert pictures.members(asset)[0] == kept
  with pytest.raises(SystemExit):
    cli.main(['pack', str(video), '-o', str(workspace), '--new-chat'])
  assert '--new-chat goes with' in capsys.readouterr().err
  command = ['pack', str(video), '-o', str(workspace), '--follow-up', '--new-chat', '--folder', str(workspace / 'out')]
  assert cli.main(command) == 0
  folder = next((workspace / 'out').iterdir())
  prompt = (folder / '提示词.md').read_text(encoding='utf-8')
  # The rules, the transcript, the round's request and the draft, in the order the words 「前面的字幕」 need.
  assert prompt.startswith(packing.NEW_CHAT_NOTE)
  assert prompt.index('# Writing a video summary') < prompt.index('请对照前面的字幕复查上一稿') < prompt.index('上一稿特有的句子')
  # The set in use alone, each picture sharp, and the candidates, none of them sharing a printed number.
  names = sorted(path.name for path in folder.iterdir() if path.name != packing.PROMPT_NAME)
  assert sum('补截' in name for name in names) >= 1 and sum('补截' not in name for name in names) == len(pictures.members(asset))
  assert not any('总图' in name for name in names)
  numbers = re.findall(r'#(\d+) \d\d:\d\d:\d\d frames/', prompt)
  assert len(numbers) == len(set(numbers)) == len(names)
  # What is sent now is what the next import judges, not the first round's pictures.
  assert set(json.loads((asset / 'picture-review.json').read_text(encoding='utf-8'))['sent']) == set(pictures.members(asset))


def test_a_chat_ais_later_rounds_overwrite_the_round_before(processed):
  from video_agent import versions
  from video_agent.importer import import_summary

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  import_summary(
    video,
    workspace,
    '# 已有的总结\n\n## 概要\n\n别的路线写的，留着不动，讲了彩条和测试图案各自的用途。\n',
    source='模型 API',
  )
  body = '# 标题\n\n## 概要\n\n第 {} 轮写的测试总结，讲了彩条和测试图案各自的用途，以及怎样看出画面偏色。\n'
  first, _ = import_summary(video, workspace, body.format(1), rounds=True, note='第 1 轮')
  review = '\n## 复查\n\n- 补上：`00:00:03` 测试图案\n'
  second, _ = import_summary(video, workspace, body.format(2) + review, rounds=True, note='第 2 轮')
  third, _ = import_summary(video, workspace, body.format(3) + review, rounds=True, note='第 3 轮')
  listed = versions.listing(asset / '总结.md')
  assert '留着不动' in (asset / '总结.md').read_text(encoding='utf-8'), 'the current summary is not touched'
  assert [version['note'] for version in listed['versions']] == ['第 3 轮'], 'one version, the last round'
  assert all(not path.exists() for path in (first, second) if path != third), 'the earlier rounds are gone'
  assert '第 3 轮写的' in third.read_text(encoding='utf-8')
  # A new first draft, without a 复查, starts a version of its own.
  import_summary(video, workspace, body.format(1), rounds=True, note='第 1 轮')
  assert len(versions.listing(asset / '总结.md')['versions']) == 2


def test_the_pictures_a_summary_is_given_grow_as_a_tree(processed, capsys):
  from video_agent import cli, pictures, versions
  from video_agent.importer import import_summary

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  every = pictures.members(asset)
  first, second, third = every[:3]
  body = '# 标题\n\n## 概要\n\n测试总结，讲了彩条和测试图案各自的用途，以及怎样看出画面偏色。{}\n'
  # A round drops two pictures; the next links one of them again, which brings it back.
  import_summary(
    video,
    workspace,
    body.format('') + f'\n## 画面调整\n\n- 不用：{first}\n- 不用：{second}\n',
    rounds=True,
    note='第 1 轮',
  )
  sorted_once = pictures.current(asset)
  assert sorted_once != pictures.ROOT and first not in pictures.members(asset) and second not in pictures.members(asset)
  current = versions.listing(asset / '总结.md')['current']
  assert current and current['pictures'] == sorted_once, 'the version names the set it was written with'
  linked = body.format(f' [表格：色块]({second})') + '\n## 画面调整\n\n无\n\n## 复查\n\n- 补上：色块\n'
  import_summary(video, workspace, linked + f'- 画面：{second} 色块的顺序\n', rounds=True, note='第 2 轮')
  assert second in pictures.members(asset) and first not in pictures.members(asset)
  assert pictures.listing(asset)['nodes'][-1]['parent'] == sorted_once
  # Later summaries, by any route, are given the current set; an earlier one can be chosen again.
  assert first not in (asset / 'summary-context.md').read_text(encoding='utf-8')
  assert cli.main(['pictures', str(video), '-o', str(workspace), '--use', sorted_once]) == 0
  assert second not in pictures.members(asset)
  capsys.readouterr()
  # By hand: a picture dropped from a chosen set, and one restored, each a new set.
  assert cli.main(['pictures', str(video), '-o', str(workspace), '--from', '0', '--drop', third, '--json']) == 0
  listed = json.loads(capsys.readouterr().out)
  assert listed['nodes'][-1]['source'] == '手动' and listed['nodes'][-1]['parent'] == '0'
  assert third in listed['nodes'][-1]['dropped'] and first in listed['nodes'][-1]['members']
  assert cli.main(['pictures', str(video), '-o', str(workspace), '--restore', third]) == 0
  assert pictures.members(asset) == every
  # What a chat AI was sent and did not link, it saw and found no use for.
  assert cli.main(['pictures', str(video), '-o', str(workspace), '--use', '0']) == 0
  from video_agent.packing import material

  with tempfile.TemporaryDirectory() as work_dir:
    material(video, workspace, work_dir=work_dir)
  import_summary(video, workspace, body.format(f' [表格：色块]({first})'), rounds=True, note='第 1 轮')
  assert pictures.members(asset) == [first] + [path for path in every if path.startswith('frames/extra/')]


def test_the_checks_name_what_a_chat_ais_summary_leaves_out(processed):
  from video_agent import summary_review
  from video_agent.importer import import_summary

  video, workspace = processed
  asset = asset_folder(workspace, video.resolve())
  # The subtitles speak at 0.5-2.5 s and 3-5 s; the detailed part covers only the first.
  text = '# 标题\n\n## 概要\n\n测试。\n\n## 详细内容\n\n### 彩条 `00:00:00`–`00:00:02`\n\n- `00:00:01` 彩条，`00:09:00` 结束\n'
  import_summary(video, workspace, text, rounds=True)
  state = summary_review.load(asset)
  assert state['first'] and state['again']
  missing, pictures, late, gap = state['problems']
  assert '「要点」' in missing and '「时间线」' in missing and '「需确认」' in missing
  assert '画面调整' in pictures and '00:09:00' in late and '00:00:03–00:00:05' in gap
  # Sections and spans left out on purpose, said in the 复查, are not asked for again.
  review = (
    '\n\n## 画面调整\n\n无\n\n## 复查\n\n- 补上：无\n- 删掉的节：要点、时间线、需留意、需确认（太短）\n'
    '- 不写的时间段：00:00:03–00:00:05（片尾）\n'
  )
  import_summary(video, workspace, text.replace('`00:09:00` 结束', '结束') + review, rounds=True)
  state = summary_review.load(asset)
  assert state['problems'] == [] and not state['again'] and state['review']['skipped'] == [[3, 5]]
  # Each linked picture needs a word in the 复查 on what it shows beyond the transcript: a link with none is taken out
  # and the picture not offered again, a picture with no line at all is named.
  from video_agent import pictures

  manifest = json.loads((asset / 'manifest.json').read_text(encoding='utf-8'))
  shown, card, silent = (frame['path'] for frame in manifest['representative_frames'][:3])
  linked = text.replace('彩条，', f'彩条 [表格：色块]({shown}) [截图：彩条]({card})，').replace(
    '## 概要\n\n测试。', f'## 概要\n\n测试。 [画面]({silent})'
  )
  lines = f'- 画面：`{shown}` 七个色块的顺序\n- 画面：{card} 无（字就是字幕）\n'
  target, _ = import_summary(video, workspace, linked.replace('`00:09:00` 结束', '结束') + review + lines, rounds=True)
  saved = target.read_text(encoding='utf-8')
  assert shown in saved and card not in saved and '彩条 [表格：色块]' in saved
  assert card not in pictures.members(asset)
  (problem,) = summary_review.load(asset)['problems']
  assert silent in problem and shown not in problem
  # An Agent's draft has no rounds; what an earlier chat AI's round left is cleared.
  import_summary(video, workspace, text, overwrite=True)
  assert summary_review.load(asset) == {}
