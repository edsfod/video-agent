"""summarize against fake Anthropic and OpenAI-compatible servers, including one round of the frame tool."""

import json

import pytest

from video_agent.processor import asset_folder, process_video
from video_agent.summarize import SummaryError, summarize_video, template, video_line

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
