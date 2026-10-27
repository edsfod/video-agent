"""summarize against fake Anthropic and OpenAI-compatible servers, including one round of the frame tool."""

import io
import json
import zipfile

import pytest

from video_agent.processor import asset_folder, process_video
from video_agent.summarize import SummaryError, evidence_images, summarize_video, template, video_line

SUMMARY = '# 测试视频\n\n## 概要\n\n一段测试视频，`00:00:03` 展示图表。[画面](frames/extra/frame-00-00-03.jpg)\n'


@pytest.fixture
def processed(sample_video, tmp_path):
  workspace = tmp_path / 'work'
  process_video(sample_video, workspace, interval=2, max_frames=6, status=lambda message: None)
  return sample_video, workspace


def config(provider, url):
  base = url if provider == 'anthropic' else f'{url}/v1'
  return {'provider': provider, 'model': 'test-model', 'base_url': base}


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


def test_no_tools_and_refuses_to_overwrite(processed, fake_model, no_proxy):
  video, workspace = processed
  server = fake_model([{'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': SUMMARY}]}])
  summarize_video(video, workspace, config('anthropic', server.url), 'k', use_tools=False, status=lambda message: None)
  assert 'tools' not in server.requests[0]['body']
  with pytest.raises(SummaryError, match='already exists'):
    summarize_video(video, workspace, config('anthropic', server.url), 'k', status=lambda message: None)


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


def test_import_saves_a_pasted_summary_once(processed, monkeypatch, capsys):
  from video_agent import cli

  video, workspace = processed
  pasted = f'```markdown\n{SUMMARY}```\n'
  monkeypatch.setattr('sys.stdin', io.TextIOWrapper(io.BytesIO(pasted.encode('utf-8'))))
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', '-']) == 0
  target = asset_folder(workspace, video.resolve()) / '总结.md'
  assert target.read_text(encoding='utf-8') == SUMMARY
  again = workspace / 'again.md'
  again.write_text('# 第二版\n\n' + '内容' * 30, encoding='utf-8')
  with pytest.raises(SystemExit) as stopped:
    cli.main(['summarize', str(video), '-o', str(workspace), '--import', str(again)])
  assert stopped.value.code == 2
  assert 'already exists' in capsys.readouterr().err
  assert cli.main(['summarize', str(video), '-o', str(workspace), '--import', str(again), '--overwrite']) == 0
  assert target.read_text(encoding='utf-8').startswith('# 第二版')


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
  assert f'- 总图/总图-001.jpg：00:00:{round(first["time_s"]):02d} {first["path"]}' in prompt
  assert '我的要求：写短一点' in prompt
  assert '「视频」那一行的开头照抄：视频：sample clip [test] · [打开视频]' in prompt
  assert '我们看看这张图表' in prompt and '# Writing a video summary' in prompt

  capsys.readouterr()
  assert cli.main(['pack', str(video), '-o', str(workspace)]) == 0
  assert '这次没有附上画面' in capsys.readouterr().out


def test_screen_pages_go_on_contact_sheets_when_they_exceed_the_budget(tmp_path):
  import subprocess

  from video_agent import media

  screen = tmp_path / 'frames' / 'run' / 'screen'
  screen.mkdir(parents=True)
  subprocess.run(
    [
      media.tool('ffmpeg'),
      '-v',
      'error',
      '-f',
      'lavfi',
      '-i',
      'testsrc=s=320x180:r=1:d=30',
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
