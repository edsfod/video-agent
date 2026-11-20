# Deleting videos — user request (2026-11-16)

The user asked for a way to delete, at one click, a video that was not added from their own disk, with its transcript, pictures and summaries, and agreed to the design: several at once, and a video added from disk keeps its file (Claude's proposal, approved the same day).

- `video-agent delete VIDEO...` does the work (the GUI holds no file logic of its own): every processing folder of the video (the one its path names and any other whose manifest names it: one video had two, the older made under an earlier file name), its place in every collection, and the file with its subtitle and info files only when this program downloaded it. "Downloaded by this program" is read from where the file lies: the workspace's `下载` folder or a followed collection's download folder, the only places downloads go (Claude judgment: no record of each download exists, and the place is what the user sees).
- yt-dlp's download archive of a followed collection keeps the id, so an update does not fetch the deleted video again.
- The window: 删除… on a video's page, and 选择 beside the 视频 list to tick several; one confirmation says how many files go and how many stay. A video with a task queued or running is not deleted; a folder a running job holds is refused by the CLI.
- Product rules: a source video is still never modified or moved, except `compress` and now `delete` of a download.
