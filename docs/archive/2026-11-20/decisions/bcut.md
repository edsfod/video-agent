# BCut client — user decision (2026-10-28)

The BCut (必剪) client came, through yanhe-agent, from windlandneko/yanhekit's code. Using BCut for subtitles and packaging summaries as an Agent plugin are common ideas (SocialSisterYi/bcut-asr since 2022, VideoCaptioner, BiliNote and others), so the user had the client written anew for this project rather than credit an origin of ideas it did not have (`src/video_agent/providers/bcut.py`, written from the protocol, not from either earlier client). The aim was the best fit, not a restructuring:

- The parts BCut asks for go up four at a time: 37 MB (a 98-minute lecture) took 4.0 and 5.2 s against 11.4 and 11.2 s one part after another (same audio, alternating runs, 2026-10-28).
- The result is polled from 1 s, slowing to every 10 s, so a short clip is done in seconds; progress names the queue, recognition and the line count instead of a line every 10 s.
- The wait follows the audio's length (its full length plus ten minutes; `extract_audio` writes 48 kb/s, so the size gives the length) rather than a fixed two hours.
- Connection failures and 5xx answers are retried quickly; Bilibili's throttling (412 or 429) waits 30, 60, 120 and 240 s, said in the progress. The first draft of the rewrite left 412 to fail at once; the user's question whether the new client was better found it.
- Empty utterances are dropped; `tests/test_bcut.py` runs the whole protocol against a local server (parallel parts, states, failure, deadline, throttling), which the old client never had.
- Checked against BCut itself: a 90-second clip in 5 s (50 lines) and the 98-minute lecture in 8 parts (2707 lines, ending at 01:38:22).
