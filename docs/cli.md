# 命令行用法

> 给谁看：用命令行工具的用户和 Agent。回答：从下载到总结怎么一步步做。每个命令和选项的完整说明见 [commands.md](commands.md)。

按 [README](../README.md) 安装后运行：

```powershell
video-agent --help
```

下载是可选的；`process` 只接受本地视频文件，从不下载，下载后也不会自动处理。

## 下载（可选）

`download` 只在明确调用时才运行 yt-dlp：把文件存进本地文件夹并打印最终路径，从不接着运行 `process`。把打印出的路径交给单独的 `process` 命令。别处下载的视频直接交给 `process`，不需要 yt-dlp。

```powershell
video-agent download "https://example.com/video" --output "D:\Video-Downloads"
video-agent process "D:\Video-Downloads\downloaded-video.mp4"
```

默认格式选择是 `bv*+ba/b`。只代表播放列表的链接默认拒绝，加 `--playlist` 才下载列表里的全部视频；同时含有某个视频和播放列表的链接，默认只下那个视频。默认不读 yt-dlp 的配置文件，要用就以 `--yt-dlp-config` 明确指定一个。装了 Media Downloader 时，也会找到它放在 `%APPDATA%\media-downloader\bin` 下的 yt-dlp。网站的字幕默认一起下载（`--no-subs` 关掉）；要登录的网站用 `--cookies FILE` 传 Netscape 格式的 cookie 文件。

## 查看和处理

只看媒体流，不写任何东西：

```powershell
video-agent inspect "D:\Videos\lecture.mp4"
```

为总结准备材料：

```powershell
video-agent process "D:\Videos\lecture.mp4" --output "D:\Video-Work"
```

不给 `--output` 时，用当前目录下的 `video-agent-output`。一条 `process` 命令可以给多个视频。

## 处理做了什么

1. 用 ffprobe 查看视频（没有 ffprobe 时从 ffmpeg 的输出里读同样的信息）。
2. 找字幕：同名的 `.srt`、`.vtt`、`视频名.<语言>.srt`，或视频里的字幕轨；`--subtitles FILE` 指定任意名字的字幕文件。
3. 识别画面布局，在屏幕区域里找出每一页（装了 AutoSlides Extractor 时由它找，`--no-extract-slides` 关掉）；`--slides FOLDER` 导入课件图片代替。
4. 按间隔（默认 60 秒）和场景变化抽取代表画面，数量跟着视频走，最多 500 张。
5. 写出清单 `manifest.json` 和 `summary-context.md`（字幕按当时屏幕上的画面分组）；有字幕时还写 `transcript.srt` 和 `transcript.txt`。

场景变化只是候选，按间隔的抽样覆盖长时间不动的镜头；画面是材料，不代表每张都重要。同样的设置处理过的视频直接用上次的结果，`--force` 才重新处理。布局判断错了时看 `layout.jpg`，用 `--screen-region X,Y,W,H` 指定屏幕区域。

## 语音识别和隐私

视频有声音却没有字幕时，`process` 照样保存画面，并说明字幕缺失；默认不上传音频。

要用必剪（B 站的语音识别），两个选项都要加：

```powershell
video-agent process "D:\Videos\lecture.mp4" --asr bcut --allow-remote-asr
```

这会提取音频并上传到 B 站必剪。每条可能上传音频的命令都要带 `--allow-remote-asr`。视频已有能用的字幕时用字幕，不上传音频。

必剪给出的上传地址是 `jssz-boss.biliapi.net` 上的明文 HTTP。Video Agent 和其他程序一样走系统代理；代理规则挡了这个域名时，重试三次（约 12 秒）后失败，报 `audio chunk 1: upload returned HTTP 502` 和空的响应。这时在代理规则里放行这个域名，重试没用。

## 改正字幕、补截

```powershell
video-agent fix "D:\Videos\lecture.mp4" --replace 错的写法 对的写法 -o "D:\Video-Work"
video-agent frame "D:\Videos\lecture.mp4" 12:34 1:02:03 -o "D:\Video-Work"
```

`fix` 另存一份改正后的字幕，原字幕不动，`--remove`、`--reset` 撤回；`frame` 按时间补截画面到 `frames/extra/`。

## 写总结

- Agent：按 skill 写成 `总结.draft.md`，用 `video-agent summarize "<视频>" -o <工作区> --import --source "<名字>"` 保存。
- 模型 API：`video-agent config` 设好服务商、模型和 key 后，`video-agent summarize "<视频>" -o <工作区>`。
- 网页 AI：`video-agent pack "<视频>" -o <工作区>` 打印提示词（`--zip`、`--folder` 连画面一起导出），写好的总结用 `summarize --import <文件>` 存回。

`video-agent template` 打印总结的规则和模板。已有总结时新写的存成一个版本，`video-agent versions` 列出和切换。合集见 `video-agent collection --help`。

## AutoSlides Extractor

装了它时由它找屏幕页；Video Agent 以 JSON 命令行模式运行它，输出存在 `slide-extraction/<run-id>/`。用的是明确指定的 SSIM、降采样、pHash 和机器学习设置，不继承它图形界面里保存的偏好。它的命令行只存幻灯片图片和 `timeline.json`，不生成可编辑的 `.pptx` 或 PDF；导出 PDF 要在它的图形界面里做。

```powershell
video-agent process "D:\Videos\lecture.mp4" `
  --extract-slides --slide-extractor "C:\Program Files (x86)\AutoSlides Extractor\AutoSlidesExtractor.exe"
```
