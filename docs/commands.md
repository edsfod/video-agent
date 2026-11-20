# 命令参考

> 给谁看：用命令行工具的用户和 Agent。回答：每个命令、每个选项是什么、默认是什么。它是命令行解析器的权威说明；从头到尾怎么用见 [cli.md](cli.md)。

## 调用

按 [README](../README.md) 安装后：

```powershell
video-agent --help
video-agent <命令> --help
```

在源码目录里，`uv run video-agent <命令>` 运行同样的命令；在装好的环境里也可以用 `python -m video_agent`。

根命令和每个子命令都有 `-h`、`--help`，打印帮助后以状态 0 退出。没有交互式外壳。

## 命令

### `download`

把 yt-dlp 支持的一个或多个链接下载到本地文件夹。返回保存的路径，不启动 `process`。

```text
video-agent download URL... [选项]
```

| 参数或选项 | 默认 | 含义 |
|---|---|---|
| `URL...` | 必填 | yt-dlp 接受的一个或多个链接 |
| `-o`, `--output PATH` | 当前目录下的 `video-agent-downloads` | 存放下载完成的文件 |
| `--format SELECTOR` | `bv*+ba/b` | yt-dlp 的格式选择：音视频分开时取最好的视频加最好的音频，否则取最好的合并格式 |
| `--playlist` | 关 | 允许下载播放列表。不加时先检查链接，只代表播放列表的拒绝，含有某个视频和播放列表的链接加 `--no-playlist` 只下那个视频 |
| `--yt-dlp PATH` | 自动查找 | 程序路径。查找顺序：这个选项、`YT_DLP_EXECUTABLE`、`PATH` 上的 `yt-dlp`/`yt-dlp.exe`、用户 AppData 里 Media Downloader 管理的那份（Windows）、随 Video Agent 安装的 yt-dlp |
| `--yt-dlp-config PATH` | 无 | 加载这个明确指定的 yt-dlp 配置文件；其他配置文件都不读 |
| `--no-subs` | 关 | 不把网站的字幕存在视频旁边（默认存；弹幕和直播聊天从不存） |
| `--cookies FILE` | 无 | 传给 yt-dlp 的 Netscape 格式 cookie 文件。B 站只对登录的账号列出字幕（含 AI 字幕） |
| `--json` | 关 | 每个保存的文件打印一个 JSON 对象；进度写到标准错误 |
| `--collection NAME` | 无 | 把保存的文件按顺序加进 `--workspace` 里的这个合集（没有就新建）；用于播放列表和连载 |
| `--workspace PATH` | `video-agent-output` | `--collection` 所在的工作区 |
| `--follow` | 关 | 和 `--playlist`、`--collection` 一起用：记住这个列表，以后 `collection update` 下载它的新视频 |
| `--auto` | 关 | 和 `--follow` 一起用：让桌面程序开着时自己检查这个列表 |

不加 `--playlist` 时，命令先只取元数据检查链接，代表播放列表的就拒绝，免得意外下载一大批。用 yt-dlp 的 `--print after_move:filepath` 取得合并、后处理之后的最终路径；正常的进度显示在终端里。开了播放列表时，每下完一个打印一个路径。打印出的路径再分别交给 `process`。

```powershell
video-agent download "https://example.com/video" --output "D:\Video-Downloads"
video-agent process "D:\Video-Downloads\downloaded-video.mp4"
```

有意下载播放列表时加 `--playlist`，每下完一个打印一个本地路径，把要处理的路径作为多个参数交给 `process`：

```powershell
video-agent download "https://example.com/playlist" --playlist --output "D:\Video-Downloads"
video-agent process "D:\Video-Downloads\video-one.mp4" "D:\Video-Downloads\video-two.mp4"
```

下载是可选的。Video Agent 把 yt-dlp 作为依赖安装，桌面安装包也自带，所以 `download` 不用另外装。`PATH` 上的 yt-dlp 或 Media Downloader 放在 `%APPDATA%\media-downloader\bin` 下的那份优先，因为它们可能更新。yt-dlp 会被告知 Video Agent 的 FFmpeg 在哪，所以分开的音视频能合并。找不到程序也找不到模块时，`download` 说明缺什么并以状态 1 退出。下载器只处理 yt-dlp 支持的链接；用别的办法存下的视频直接交给 `process`。

`process` 使用存在视频旁边的字幕；有几份时，人工字幕优先，中文先于其他语言，AI 字幕最后。浏览器开着时 yt-dlp 读不了它的 cookie，新版 Edge 和 Chrome 加密的也读不了，所以桌面程序在自己的窗口里登录，从那里传 cookie。

下载前去掉分享跟踪参数：B 站的 `vd_source`、`spm_id_from`、`from_spmid` 和 `share_*`，YouTube 的 `si` 和 `feature`，以及 `utm_*`。选内容的参数保留，例如多 P 视频的 `?p=2` 和 `?t=90`。

### `inspect`

用 ffprobe 读一个本地视频，打印 JSON：解析后的路径、以秒计的时长、各个流。不写任何文件。

```powershell
video-agent inspect "D:\Videos\lecture.mp4"
```

| 参数 | 必填 | 含义 |
|---|---:|---|
| `VIDEO` | 是 | 本地视频文件的路径，不接受文件夹 |

### `process`

为一个或多个本地视频准备字幕和画面材料。不下载，也不写总结。

```powershell
video-agent process VIDEO... [选项]
```

| 参数或选项 | 默认 | 含义 |
|---|---|---|
| `VIDEO...` | 必填 | 一个或多个本地视频文件的路径，不接受文件夹 |
| `-o`, `--output PATH` | 当前目录下的 `video-agent-output` | 各视频工作文件夹的上级目录 |
| `--frame-interval SECONDS` | `60` | 按间隔抽样的秒数，正数 |
| `--scene-threshold VALUE` | `0.35` | FFmpeg 的场景变化阈值，大于 0、不超过 1 |
| `--max-frames N` | 视频有多少就多少，最多 500 | 每个视频最多写多少张代表画面 |
| `--screen-region X,Y,W,H` | 自动识别 | 布局识别错了时，画面里屏幕部分的像素区域（见这次抽帧文件夹里的 `layout.jpg`） |
| `--json` | 关 | 每个视频打印一个 JSON 对象；进度写到标准错误 |
| `--extract-slides`, `--no-extract-slides` | 装了 AutoSlides Extractor 且视频有屏幕区域时开 | 用 AutoSlides Extractor 找屏幕页：它的幻灯片（同一页的几步合成一页）代替屏幕页。`--no-extract-slides`（或 `AUTOSLIDES_EXTRACTOR=none`）用本程序自己的找法；`--extract-slides` 在判成摄像头画面的视频上也运行它 |
| `--slide-extractor PATH` | 自动查找 | AutoSlides Extractor 的程序路径。查找顺序：这个选项、`AUTOSLIDES_EXTRACTOR`、`PATH` 上的 `SlidesExtractor` 或 `AutoSlidesExtractor`、常见的 Windows 安装目录 |
| `--asr {none,bcut}` | `none` | 没有旁边的字幕、也没有内嵌字幕时用的语音识别 |
| `--allow-remote-asr` | 关 | 明确允许把提取的音频发给 B 站必剪；只能和 `--asr bcut` 一起用 |
| `--force` | 关 | 重新处理处理过的视频。不加时，用同样的抽帧设置处理过的视频直接用上次的结果（每次抽帧的结果不同），除非这次要求更多：缺的字幕（`--asr`）、课件、屏幕区域、字幕文件或 `--overwrite-transcript`。桌面程序总是加它 |
| `--overwrite-transcript` | 关 | 已有 `transcript.srt` 也重新取字幕；取失败时保留原来的，这次标为不完整 |
| `--subtitles FILE` | 无 | 用这个任意名字的 SRT 或 WebVTT 文件当字幕，替换已有的；只能一个视频 |
| `--slides FOLDER` | 无 | 使用这个文件夹里的课件图片（PNG、JPEG）：有 AutoSlides 的 `timeline.json` 就按它的时间，否则按和哪张屏幕页像来对时间。`screen_<名字>` 视频不加这个选项也会用 AutoSlides 放在旁边的 `slides_<名字>` 文件夹。只能一个视频 |

#### 布局检查和静止画面

五分钟以上、有摄像头、屏幕页不到两页的视频，`process` 提示布局可能判断错了，指出 `layout.jpg`（屏幕区域用绿框标出），建议用 `--screen-region`；`summary-context.md` 里也有同样的「Layout check」一行。

布局是这几种之一：`screen`（整个画面）、`split`（屏幕旁边是摄像头画面，讲者挡住部分边界也算）、`inset`（屏幕里嵌着摄像头画面，有没有边框都行，找页时涂黑）、`projected`（摄像机拍的投影或显示器：在那块屏幕里用本程序自己的办法找页）、`camera`。只判成摄像头画面的视频，整个画面停住 2 秒以上的画面（素材之间的图表、截图）就是它的屏幕页；被拍的屏幕找不到两页时也这样。

#### 字幕和上传

先找同名的 `.srt`、`.vtt`，再找内嵌字幕轨。有能用的带时间文字就写 `transcript.srt` 和 `transcript.txt`，不上传音频。

有声音却没有本地字幕时，默认的 `--asr none` 让字幕保持缺失。要选必剪并允许上传，两个选项都要加：

```powershell
video-agent process "D:\Videos\lecture.mp4" --asr bcut --allow-remote-asr
```

这个许可每次调用都要给。没有声音也没有字幕的视频，写一份空字幕，照样准备画面材料。

#### AutoSlides Extractor

装了它时由它找屏幕页：以 JSON 命令行模式在屏幕区域上运行（旁边或里面有摄像头画面时先裁出来），用明确指定的设置，每次一个新的输出文件夹；同一页逐步出现的几步合成一页（只是在上一页上加东西的并入上一页，保留最早的时间和更完整的画面）。它多留的页（幻灯片里在放视频）交给写总结的去掉。它没装或失败时用本程序自己的找法。它的命令行只存幻灯片图片和 `timeline.json`，不生成可编辑的 `.pptx` 或 PDF；导出 PDF 要在它的图形界面里做。

```powershell
video-agent process "D:\Videos\lecture.mp4" --extract-slides
```

它在 `PATH`、`AUTOSLIDES_EXTRACTOR` 和常见的 Windows 安装目录里找；需要时指定程序路径：

```powershell
video-agent process "D:\Videos\lecture.mp4" `
  --extract-slides --slide-extractor "C:\Program Files (x86)\AutoSlides Extractor\AutoSlidesExtractor.exe"
```

### `models`

```powershell
video-agent models [--provider anthropic|openai] [--base-url URL] [--json]
```

从服务商的模型列表（`GET …/models`）列出模型 ID，不花 token；桌面程序用它填模型 API 的「模型」下拉框。`summarize --effort low|medium|high` 设定模型想多深：OpenAI 兼容接口传 `reasoning_effort`，Anthropic 设扩展思考的预算；不给就不传。

### `compress`

```powershell
video-agent compress VIDEO... [--json] [--check]
```

把每个视频原地用 SVT-AV1（CRF 40）按原分辨率重新编码；几乎不动的画面（屏幕录像）降到每秒 10 帧。96 kbps 以内的 AAC 音频直接复制，其他转成 64 kbps 的 AAC；字幕和元数据保留。新文件只在时长差一秒以内、且确实更小时才替换旧文件。已经是 AV1、HEVC、VP9 的视频，和这个命令压缩过的（文件里有标记），都不动。需要带 `libsvtav1` 的 FFmpeg，桌面安装包里的就带。

`--json` 每个视频打印一个 JSON 对象，进度写到标准错误。`--check` 什么都不压缩，只说明每个视频的状态：`compressed`、`efficient`（已经是 AV1、HEVC 或 VP9）、`not-smaller`（试过，副本更大）或 `null`（值得压缩）。状态按路径、大小、修改时间存在设置旁边的 `compression.json`，所以 `show` 的 `compression` 和 `collection list` 里每集的状态都从这个文件读，不用打开视频。

### `frame`

按选定的时间截单张画面，存进视频的工作文件夹，用来看清代表画面漏掉的图表、幻灯片或屏幕上的字。写 1280 像素宽的 JPEG，打印每个路径。

```text
video-agent frame VIDEO TIME... [-o WORKSPACE]
```

| 参数或选项 | 默认 | 含义 |
|---|---|---|
| `VIDEO` | 必填 | 本地视频文件 |
| `TIME...` | 必填 | 一个或多个时间：秒（`70`）、`MM:SS`（`1:10`）或 `HH:MM:SS`（`00:01:10`） |
| `-o`, `--output PATH` | 当前目录下的 `video-agent-output` | 处理这个视频时用的工作区。画面存到 `<工作区>/<视频文件夹>/frames/extra/frame-HH-MM-SS.jpg`，同一秒已有的会被替换 |

到达或超过视频结尾的时间会被报出并跳过，命令以状态 1 退出。

```powershell
video-agent frame "D:\Videos\lecture.mp4" 1:10 00:41:20 --output "D:\Video-Work"
```

### `summarize`

可选。用模型 API 给处理过的视频写 `总结.md`，代替 Agent skill。先用同样的 `--output` 运行 `process`。模型收到 `summary-context.md` 和代表画面（含 `frames/extra/` 里的），照 `template` 打印的规则和模板写。开着工具调用时，模型可以要补截：`summarize` 把每张存进 `frames/extra/` 并把图发回去，最多 `--max-extra-frames` 张。

```text
video-agent summarize VIDEO [-o WORKSPACE] [--provider anthropic|openai] [--model NAME] [--base-url URL]
                      [--request TEXT] [--template NAME] [--effort low|medium|high] [--max-images N]
                      [--max-extra-frames N] [--no-tools] [--make-current] [--import [FILE] [--source S] [--note N]]
video-agent summarize --collection NAME [--guide] [-o WORKSPACE] [...]
```

| 选项 | 默认 | 含义 |
|---|---|---|
| `-o`, `--output PATH` | `video-agent-output` | 处理时用的工作区 |
| `--provider` | 用 `config` 设的（起初是 `anthropic`） | `anthropic` 用 Messages API；`openai` 用任何 OpenAI 兼容的 Chat Completions API |
| `--model NAME` | 用 `config` 设的；Anthropic 是 `claude-sonnet-5-5` | 必须能看图。`openai` 没有默认模型 |
| `--base-url URL` | 用 `config` 设的，否则服务商的官方地址 | 例如 Ollama 的 `http://127.0.0.1:11434/v1` |
| `--request TEXT` | 无 | 用户的要求，例如深度或侧重，交给模型 |
| `--max-images N` | 60 | 第一次请求附的图数；屏幕页和画面拼成总图来放下，3×3 也放不下时才均匀去掉 |
| `--max-extra-frames N` | 8 | 模型通过工具调用能要的补截数；`0` 不许要 |
| `--no-tools` | 关 | 不发工具定义，给不支持工具调用的模型 |
| `--template NAME` | 选定的那个 | 这次总结用的模板（见 `template --list`） |
| `--effort low\|medium\|high` | 不传 | 模型想多深（见 `models`） |
| `--make-current`, `--overwrite` | 关 | 新文字成为当前的 `总结.md`，被替换的存成版本。不加时，已有总结旁边的新文字存成版本（见 `versions`） |
| `--collection NAME` | 无 | 不是给视频，而是从合集各集的总结写合集总结（`合集总结.md`） |
| `--guide` | 关 | 和 `--collection` 一起用：改写学习提纲（`学习提纲.md`） |
| `--source TEXT` | `导入` | 和 `--import` 一起用：是谁写的，例如 `网页 AI`、`Claude Code`，记在版本里 |
| `--note TEXT` | 无 | 和 `--import` 一起用：记在版本里的备注，例如模型 |
| `--import [FILE]` | 无 | 不调用模型，保存别处写的总结：一个文件，`-` 表示标准输入，不给值就读总结旁边的草稿（视频文件夹里的 `总结.draft.md`；合集文件夹里的 `合集总结.draft.md` 或 `学习提纲.draft.md`），存好后删掉草稿 |

用自带模板时，不管哪种方式写的（导入，或 `summarize` 用模型 API），「主线与单元」都由程序排：详细内容里有关系的命题（`← P1`、`反驳 P4`、`步骤 P39`）连成一棵棵树，放在根所在那一段的标题下；主线是带 `接上：` 那一行的命题和它从各单元接过来的条目；每个条目只展开一次，每个编号链接到它在正文里的那一条；写的人写的这一节被替换，其中标 `` `拓展` `` 的单元保留。自己的模板，「主线与单元」里没有模板的标记时，交给写的人。

网页 AI 写的总结最后可以有两节，导入时取出。`## 字幕改正` 列出反复听错的写法（`错的写法 → 正确写法`），套进改正后的字幕。`## 画面调整` 列出它不需要的图（`不用：frames/…` 或课件页的路径），导入时从在用的画面集里去掉（见 `pictures`）；以及它缺图的时间段（`补截：00:02:20–00:02:30 应该看到什么`），导入时在那段时间里截最多四张互不相同的候选到 `frames/extra/`，优先取停在屏幕上的画面。

从文件或标准输入导入的回答算网页 AI 的，走多轮复查。只用 `--import` 导入的草稿算 Agent 的：检查一次 Agent 能改的问题（模板的各节、没覆盖的长时间讲话、要点没指到的段、时间点不在所在段的命题、「主线与单元」排不出来的地方、超出结尾的时间）；查出问题时草稿先存下，导入说明要改什么，再运行同一条命令会覆盖刚存的那份，不另加版本。改一次之后还剩的问题照样说明，文字就这样留下。

导入检查程序看得出的问题：模板的各节（`--template`，默认选定的那个）；`画面调整` 一节（没有要改的写「无」）；两分钟以上有讲话、却没有哪一段的时间范围覆盖的时间段（只提一次，再略过就不再提）；要点一条都没指到的段（按段里的时间或命题编号）；时间点不在所在段范围里的命题；「主线与单元」排不出来的地方（关系用了不存在的编号，接到主结论的条目在 `接上：` 里没写来源）；超出视频结尾的时间点。

从第二轮起，请网页 AI 做复查：对照字幕把稿子过一遍，补上值得记的、删去不值得的，检查要点没有漏掉重要的，结尾写 `## 复查`，列出补上的（`补上：`）、改正的（`改正：`）、删去的（`删去：`）、故意删掉的节（`删掉的节：`）、要点不收的段（`要点不收：<段> 为什么`，检查随之接受），以及每张链接的图上有什么字幕里没有的（`画面：frames/… 内容`）；写「无」的链接被去掉，那张图不再发；没写这一行的图下一轮点名。

第一稿之后，或复查补上、改正了什么，或检查查出了问题，或要了画面，导入会说明原因和还有下一轮；`pack VIDEO --follow-up`（单独、`--zip` 或 `--folder`）给出下一轮：复查要求、查出的问题、候选和保存的稿子，让它改写。复查的补上、改正、删去只在稿子和上一稿不同时才算（不计空行和空格）。之后每一轮的回答（带复查的）覆盖上一轮：不管上一轮成了当前总结还是旁边的版本，只要那份文字还和轮次写的时候一样、且是同一个模板；其他的（第一稿、收敛之后的回答、手改过的稿子、换了模板的、别的方式写的）都是并列的新文字。备注说明轮次进行到哪：给的备注，加上还要下一轮时的 `未收敛` 或 `已收敛`。中途断掉的保留最后一轮，`pack --folder --resume` 从它接着跑。轮次之间的状态在视频文件夹里的 `summary-review.json` 和 `picture-review.json`。

API key 来自 Windows 凭据管理器（用 `config --set-key` 保存），否则 `ANTHROPIC_API_KEY` 或 `OPENAI_API_KEY`。不需要 key 的 OpenAI 兼容服务（例如 Ollama）不用 key 也能用。总结和画面会发给配置的服务商。

### `config`

查看或修改 `summarize` 的设置。不带选项时打印当前的服务商、模型、地址、key 从哪来，以及设置文件（`%APPDATA%\video-agent\settings.json`）。key 从不写进这个文件。

```powershell
video-agent config --provider anthropic --set-key
video-agent config --provider openai --model qwen2.5vl:7b --base-url http://127.0.0.1:11434/v1
video-agent config --delete-key
```

`--provider` 同时把这个服务商设为默认；`--json` 以 JSON 打印设置结果。`--set-key` 读 key 时不回显（不在终端里运行时从标准输入读一行）；`--delete-key` 删掉它。

### `template`

```powershell
video-agent template [NAME] [--list | --use | --default | --edit | --copy NEW | --reset | --accept | --info]
```

打印 Agent skill、`summarize` 和 `pack` 遵循的总结规则和 Markdown 模板：选定的那个，或指名的那个。几个模板并存：自带的「标准」（把说法拆成编号的命题，标出事实、观点、推断或引用；要点不漏重要的；自成一体的单元和它们连成的主线；总结者加的以拓展和核对标出），以及用户在 `%APPDATA%\video-agent\templates` 里自己的模板。从没改过的「标准」副本在自带模板更新后让位给新版。`summarize` 和 `pack` 可以用 `--template NAME` 只指定这一次。

- `--list`：以 JSON 列出所有模板，选定的标 `current`。
- `--use`：以后的总结都用指名的模板。
- `--default`：打印自带模板出厂时的样子，不是用户的副本。
- `--edit`：建立自带模板的用户副本（只建一次），以 JSON 打印路径；更新从不改它。
- `--copy NEW`：从指名的模板建一个名叫 `NEW` 的用户模板。
- `--reset`：删掉自带模板的用户副本，或用户自己的模板。
- `--accept`、`--info`：标记副本已经合并了自带模板的更新；打印它在哪、是否过时。

### `tools`

```powershell
video-agent tools [--json]
```

打印要用的外部程序在哪：FFmpeg、ffprobe、yt-dlp 和 AutoSlides Extractor，各自按 `process` 和 `download` 的查找方法找；找不到的是 `null`（或 `none`）。什么都不改。

### `show`

```powershell
video-agent show VIDEO [-o WORKSPACE]
```

以 JSON 打印一个视频的处理文件夹的情况，什么都不改：时长、是否处理过、清单、总结、材料和字幕的路径、字幕改正、补截的画面、视频旁边找到的字幕文件、压缩状态，以及是不是本程序下载的（`downloaded`）。桌面程序读它。

### `delete`

```powershell
video-agent delete VIDEO... [-o WORKSPACE] [--json]
```

从工作区删掉视频：每个视频的处理文件夹（路径指向它的，以及清单里写着它的），连同字幕、画面和所有版本的总结，以及它在各合集里的位置。视频文件和旁边同名的字幕、信息文件只在本程序下载的时候才删，也就是在工作区的 `下载` 文件夹或跟随的合集的下载文件夹里；从别处添加的视频保留文件。正在运行的任务持有的文件夹不删。`--json` 对每个视频打印删掉了什么（`folders`、`collections`、`files`）和文件是否保留（`video_kept`）。

### `versions`

```text
video-agent versions VIDEO [-o WORKSPACE] [--use FILE | --delete FILE | --note FILE TEXT | --keep SOURCE | --settle] [--json]
video-agent versions --collection NAME [--guide] [...]
```

再写一次总结不会替换当前的，除非要求（`--make-current`）：新文字存成旁边的一个版本 `总结 (<日期 时间>).md`，谁写的和备注记在 `总结.versions.json`，还有它的来历：从头写（`从头写`），或改自更早的某一版（`改自 <文件>`）；导入时，新稿至少五分之一的行（不算模板的行）和某一版一字不差，就算改自那一版。2026-11-16 以前存的文字两样都不显示。文字改名后 id 不变。不带选项时列出各版本。

- `--use FILE`：把这一版设为当前，当前的变成一个版本。
- `--delete FILE`：删掉一个版本（从不删当前的）。
- `--note FILE TEXT`：设置一个版本的备注（`FILE` 可以是 `总结.md`）。
- `--keep SOURCE`：在别的东西改写文件之前，把当前文字另存为一个版本。
- `--settle`：`--keep` 为之准备的事做完之后：别的文件已有同样的文字，这份副本删掉；当前文字被直接改写了，记为来自 SOURCE。
- `--collection NAME`、`--guide`：合集总结或学习提纲，而不是视频的总结。

每个版本记下它写的时候用的画面集（`--json` 里的 `pictures`，见 `pictures`）。

### `pictures`

```text
video-agent pictures VIDEO [-o WORKSPACE] [--use SET] [--drop PATH... | --restore PATH...] [--from SET] [--json]
```

一个视频的哪些图交给总结，组织成一棵画面集树。集 `0` 是处理得到的全部图片，加上在网页 AI 轮次之外补截的；其他每一集由父集去掉、加上一些图得到。有一集在用：每种写总结的方式、打包和材料都用它。网页 AI 的一轮从它长出一个新集（去掉 `画面调整` 里说不用的、复查说没东西的、发过去却没链接的，加上稿子链接的每一张），所以便宜的 AI 可以先筛图，好的 AI 再从剩下的写。图片是视频文件夹里的文件，一集只记它们的名字。重新处理会开一棵新树。不带选项时列出各集，`*` 标出在用的。

- `--use SET`：以后的总结用这一集。
- `--drop PATH...`、`--restore PATH...`：从在用的集或 `--from SET` 做一个去掉或加回这些图的新集（路径同 `--json`，相对视频文件夹），并设为在用。
- `--json`：每一集和它的图（`members`），以及这个视频的其他图（`dropped`）。

### `pack`

```text
video-agent pack VIDEO [-o WORKSPACE] [--request TEXT] [--template NAME] [--follow-up [--new-chat] | --resume]
                 [--zip FILE | --folder PARENT [--max-files N]] [--max-images N]
video-agent pack --collection NAME [--guide] [...]
```

给不能运行命令的网页 AI 的总结提示词：规则、模板和材料，要求把回答放进一个 Markdown 代码块。单独用时打印提示词；`--zip FILE` 把 `提示词.md` 和图片写进 zip，画面保留相对路径，导入后总结里的链接能用；`--folder PARENT` 把 `提示词.md` 和编号的图片写进一个新文件夹，给不收 zip、文件数有限的网页 AI：超过 `--max-files`（默认 50，含提示词）时，屏幕页和整幅画面拼成总图放下，屏幕页放得更大。每张图左下角印着编号和时间。`--max-images`（默认 40）限制屏幕页之外另放的整幅画面数。

`--follow-up` 在导入的回答需要下一轮时（见 `summarize`）给出下一轮：保存的稿子的复查要求、检查查出的问题、为要的画面截的候选，让它改写。回答用 `summarize --import` 存回。桌面程序的「DeepSeek 网页」方式在 DeepSeek 窗口里自己跑这些轮次。

`--new-chat` 和 `--follow-up`、`--folder` 一起用：给出新对话用的这一轮，规则、字幕和在用的画面集在前，然后是这一轮本身；不带以前的回答。

`--resume` 和 `--folder` 一起用、不带 `--follow-up`，用于一次运行的第一轮：同一模板的上一次轮次没收敛就停了（断网、限流、手动停止），且它的稿子还和它写的时候一样，就给出那份稿子在新对话里的下一轮，并在标准错误上说 `接着上次没有收敛的第 N 轮稿子复查`；否则给出第一轮。

### `fix`

```powershell
video-agent fix VIDEO [-o WORKSPACE] [--replace WRONG RIGHT]... [--remove WRONG] [--reset] [--json]
```

改正反复听错的名字和术语。原字幕不动，改正后的写成 `transcript.clean.srt` 和 `.txt`，以后的总结都用它。拉丁字母的词只按整词匹配，中文按写法匹配，也匹配长词里的部分，所以只给在哪里出现都是错的写法。`--remove WRONG` 撤回一条，`--reset` 撤回全部并删掉改正后的字幕；不带选项时列出改正。`--json` 打印改正和改了的行。

```powershell
video-agent fix "D:\Videos\lecture.mp4" -o D:\Video-Work --replace 延和课堂 延河课堂 --replace react ReAct
```

### `collection`

把相关的视频（一门课、一个系列、一个播放列表）编成组，写合集总结和学习提纲。合集是工作区里的一个文件夹；视频自己的文件夹和总结留在原处。每个子命令都接受 `-o WORKSPACE`。

| 子命令 | 含义 |
|---|---|
| `create NAME [VIDEO...]` | 建一个合集，可以同时加视频 |
| `add NAME VIDEO... [--at N]` | 加到最后，或第 N 个之前 |
| `remove NAME VIDEO...` | 移出视频 |
| `show NAME` | 每个视频和它的状态：处理过没有、有没有总结、时长、讲话占比、可能是空的、是否略过 |
| `list` | 工作区里的合集 |
| `delete NAME` | 删掉合集自己的文件夹 |
| `skip NAME VIDEO --reason TEXT` | 把几乎没内容的视频标为略过，原因写进合集总结；原因为空就撤回 |
| `terms NAME [--replace WRONG RIGHT] [--remove WRONG]` | 所有视频共用的改正，套进每个视频改正后的字幕 |
| `follow NAME [URL] [--folder DIR] [--auto\|--no-auto]` | 记住视频来自的列表（新视频存进 `<工作区>/下载`，除非给 `--folder`），或只开关桌面程序自己的检查 |
| `unfollow NAME` | 忘掉列表；视频保留 |
| `update NAME [--cookies FILE] [--no-subs] [--json] ...` | 下载跟随的列表里的新视频，按顺序加到最后；下载过的记在合集的 `downloaded.txt` |

每个视频都有总结后，`summarize --collection NAME` 写合集总结（需留意、各集一览、主线），`--guide` 写学习提纲（重点、按主题的要点、带答案的自测题）。

```powershell
video-agent collection create "机器学习" D:\Videos\ml-01.mp4 D:\Videos\ml-02.mp4 -o D:\Video-Work
video-agent collection terms "机器学习" --replace 剃度下降 梯度下降 -o D:\Video-Work
video-agent summarize --collection "机器学习" -o D:\Video-Work
video-agent summarize --collection "机器学习" --guide -o D:\Video-Work
video-agent download "https://space.bilibili.com/.../lists/...?type=season" --playlist --follow -o D:\Videos --collection "连载" --workspace D:\Video-Work
video-agent collection update "连载" -o D:\Video-Work
```

## 输出的文件

```text
<output>/<视频名>-<路径哈希>/
  manifest.json
  transcript.srt
  transcript.txt
  summary-context.md
  frames/<run-id>/frame-*.jpg
  frames/<run-id>/screen/page-*.jpg
  frames/extra/frame-HH-MM-SS.jpg
  总结.md
  slide-extraction/<run-id>/
    slide-*.jpg
    timeline.json
```

取到能用的字幕时才有字幕文件。没声音也没字幕的视频得到空的字幕文件；有讲话却没有识别服务的，没有字幕文件，这次标为不完整。`summary-context.md` 有字幕文字和代表画面、幻灯片的相对路径，是 `skills/video-agent/` 里的 Agent skill 或 `summarize` 命令的材料，二者都把 `总结.md` 写在它旁边。源视频不移动、不修改。以前的抽帧和幻灯片结果保留。完整的文件清单见 [design/architecture.md](design/architecture.md)。

## 退出状态

- `0`：命令完成；没声音也没字幕的视频可以只带画面材料完成。
- `1`：`download` 的某个链接失败，`frame` 的时间超过了结尾，或至少一个 `process` 的输入失败或缺字幕、缺幻灯片的输出。已经生成的部分材料保留。
- `2`：参数无效，逐个视频处理之前出错（含 `inspect` 失败），或 `summarize`、`config` 失败，例如缺 key 或 API 出错。
- `130`：被 Ctrl+C 中断。

## 没有的命令

命令行没有 `slides` 子命令，也没有图形界面命令。AutoSlides Extractor 装了就由 `process` 使用（`--no-extract-slides` 关掉）。
