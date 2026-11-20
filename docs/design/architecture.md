# 整体结构

> 给谁看：要改代码或接手的人和 AI。回答：由哪些部分组成、各管什么、数据怎么流、磁盘上有哪些文件、部分之间的边界。
> 各部分内部见同目录的其他设计文档；测试、构建和发布见 [development.md](../development.md)。

## 一、组成

一个核心，三个前端。处理媒体和写总结的逻辑都在 Python 命令行工具里；其余的把它当子进程启动，读它的输出。

```text
桌面程序（gui/）            Agent skill（skills/）        终端
排队、启动 Agent 和终端      Claude Code、Codex 等照着做    用户自己敲命令
        │                           │                         │
        └───────────────────────────┼─────────────────────────┘
                                    ▼
                     video-agent 命令行（src/video_agent/）
                                    │
     ┌──────────────┬───────────────┼───────────────┬──────────────────────┐
     ▼              ▼               ▼               ▼                      ▼
   yt-dlp     FFmpeg、ffprobe   必剪（HTTP）   模型 API（HTTP）   AutoSlides Extractor
  （程序）       （程序）                                          （程序，可选）
```

### 命令行（`src/video_agent/`）

| 模块 | 管什么 |
|---|---|
| `cli.py` | 命令和选项，每个命令对应一个函数；输出文字，加 `--json` 输出 JSON |
| `download.py` | 运行 yt-dlp：找到它、清理分享链接、存网站字幕、播放列表 |
| `media.py` | 运行 FFmpeg 和 ffprobe：探测、音频、抽帧、屏幕页、总图 |
| `page_rules.py` | 留哪些屏幕页，在缩小的灰度图上比较；纯函数，用合成的图测试 |
| `layout.py` | 找出视频里的屏幕区域和摄像头区域 |
| `transcript.py` | 读、挑、写带时间的字幕 |
| `providers/bcut.py` | 必剪语音识别（HTTP） |
| `corrections.py` | 改正后的字幕（`fix`） |
| `processor.py` | `process`：建视频的文件夹、`manifest.json` 和 `summary-context.md` |
| `slide_extractor.py` | AutoSlides Extractor，和导入的课件 |
| `model_api.py` | 模型 API：Anthropic 和 OpenAI 兼容接口各一个 `Provider`（模型列表、key、带补截工具的一次对话） |
| `evidence.py` | 处理过的视频的文件夹和清单、「视频：」那一行、多少张图放得下 |
| `summarize.py` | 用模型 API 给一个视频写总结 |
| `packing.py` | `pack`：给网页 AI 的提示词，单独、打成 zip 或放进带编号图片的文件夹 |
| `importer.py` | `summarize --import`：把别处写的文字存成总结或合集的文字，修好链接，取出字幕改正和画面调整 |
| `forest.py` | 照详细内容里的关系排出「主线与单元」，并给「要点」加上 `#P<n>` 链接和正文里的画面 |
| `summary_review.py` | 导入时的检查、网页 AI 的多轮复查、哪一稿可以被下一轮覆盖、没跑完的从哪接着跑 |
| `picture_review.py` | 网页 AI 总结里的「画面调整」：不用的画面，和缺图处截的候选 |
| `pictures.py` | 一个视频的画面集树：每种写总结的方式拿哪些图，由网页 AI 的轮次或手动增减 |
| `collection_summary.py` | 合集总结和学习提纲 |
| `templates.py`、`prompts/` | 总结模板：自带的和用户的 |
| `versions.py` | 总结的各个版本，和每一版改自哪一版 |
| `removal.py` | `delete`：视频的文件夹、在合集里的位置、本程序下载的视频文件 |
| `collection.py` | 合集，和跟随播放列表 |
| `compress.py` | `compress`：原地重新编码成 AV1 |
| `files.py` | 每个文件夹的锁，和读的人看不到写了一半的写法 |
| `contract.py` | `--json` 输出、`manifest.json` 和 `collection.json` 的类型 |
| `settings.py` | 命令行的设置和 API key（Windows 凭据管理器） |

### 桌面程序（`gui/`）

| 文件 | 管什么 |
|---|---|
| `src/main.js` | 主进程：启动其余模块和程序 |
| `src/shared.js` | 各模块共用的：窗口、托盘、日志、更新器、任务队列、运行中的任务和终端 |
| `src/settings.js` | 窗口的设置 |
| `src/programs.js` | 找到并运行程序：命令行工具、Claude Code、Codex 和其他 Agent、终端、插件和许可文件 |
| `src/jobs.js` | 运行队列里的任务：每种任务的命令行、Agent 路线、下载用的 cookie、后续任务 |
| `src/antigravity.js` | Antigravity 路线：在运行中的 Antigravity 里新开对话交给它的 Agent，通过它的本地服务跟到结束 |
| `src/chat-rounds.js` | DeepSeek 路线：`pack --folder`、DeepSeek、`summarize --import` 一轮轮跑，直到不再要图；对话太长时换新对话接着跑 |
| `src/deepseek.js` | DeepSeek 网页版，每个对话一个窗口：附文件（失败的逐个重传）、输入、发送（回答没开始就重发）、读回答的代码块；监视页面的请求：发送太频繁的拒绝（所有窗口一起等）和每条消息带了什么 |
| `src/extractor.js` | 从设置里下载 AutoSlides Extractor 的免安装版到数据文件夹；`childEnv` 让命令行用它 |
| `src/plugins.js` | 安装 Agent 插件、复制 skill |
| `src/accounts.js` | 网站登录和下载用的 cookie |
| `src/models.js` | 每种写总结的方式提供哪些模型和思考强度 |
| `src/tasks.js` | 任务队列和哪些任务能同时跑；不依赖 Electron |
| `src/ipc.js` | 页面能调用的所有处理函数 |
| `src/window.js` | 窗口和托盘 |
| `src/updater.js`、`update-plan.js`、`update-signature.js` | 更新：更新源、差量下载、`latest.yml` 的签名 |
| `src/logs.js` | 程序日志，和每个任务一份日志 |
| `src/preload.js` | `window.va`：页面通往主进程的唯一途径 |
| `src/cli-types.d.ts` | 命令行 JSON 的类型，由 `scripts/cli_types.py` 从 `contract.py` 生成 |
| `src/va.d.ts` | `window.va` 的类型，`preload.js` 照它检查，页面照它用 |
| `src/renderer/` | 页面：`index.html`、`style.css` 和 ES 模块。`app.js` 启动，`state.js` 放状态和共用函数，每个视图一个模块（`video-list`、`video-view`、`summary`、`collections`、`lists`、`terminal`、`task-panel`、`site-accounts`、`settings`、`templates`、`updates`、`log-window`） |
| `installer/` | NSIS 的补充：PATH 页面和脚本 |

### Agent skill

`skills/video-agent/SKILL.md` 是给 Agent 的命令行用法；插件清单（`.claude-plugin/`、`plugin.json`）让 Claude Code 和 Codex 能安装它。桌面程序把它复制到其他 Agent 的 skill 文件夹。

## 二、数据流

1. **下载**（可选）：`download URL` 运行 yt-dlp，把视频和网站字幕存进一个文件夹（桌面程序用 `<工作区>\下载\`）。它不开始处理；桌面程序在开着「下载完自动处理」时随后排一个 `process`。
2. **处理**：`process VIDEO` 读视频，在工作区里写它的文件夹：字幕（旁边或内嵌的字幕，否则加了 `--allow-remote-asr` 用必剪）、画面布局、屏幕区域里的屏幕页、代表画面，以及 `summary-context.md`（字幕和当时屏幕上的画面穿插排列）。
3. **写总结**，都按选定的模板：
   - 模型 API：`summarize` 发出字幕和画面，写下结果；
   - Agent：Claude Code、Codex 或其他 Agent 照 skill 做，写 `总结.draft.md`，用 `summarize --import` 保存；
   - Antigravity：桌面程序把同样的任务交给运行中的 Antigravity；
   - 网页 AI：`pack` 生成提示词、zip 或文件夹，回答经 `summarize --import` 存回（修好链接）；DeepSeek 网页版由桌面程序一轮轮自动跑；
   - 用户自己的文字，走同一个导入。

   保存时程序照详细内容排出「主线与单元」，并给「要点」加上编号跳转链接和对应画面。新文字只在还没有总结或明确要求时成为 `总结.md`，否则存成一个版本。
4. **合集**：`collection` 把视频编成组；`summarize --collection` 从各集的总结写合集总结或学习提纲。

## 三、磁盘上的文件

```text
<工作区>\                                     桌面程序默认 Documents\Video Agent；命令行默认 .\video-agent-output
  下载\<标题> [<id>].<扩展名>                   桌面程序下载的视频和它的字幕
  <名字>-<哈希>\                               每个视频一个：名字取自标题，哈希取自视频路径
    manifest.json                             来源、媒体信息、选项、布局、屏幕页、画面（schema_version 1）
    transcript.srt、.txt                      拿到时的原样
    corrections.json                          字幕改正
    transcript.clean.srt、.txt                套用改正后的字幕，有改正时才有
    frames\<run>\                             代表画面、screen\page-NNN-HH-MM-SS.jpg、layout.jpg
    frames\extra\                             后来补截的（frame、网页 AI 的补截）
    slides\、slide-extraction\<run>\          导入的课件、AutoSlides Extractor 找的屏幕页
    summary-context.md                        每种写总结的方式都读的材料
    pictures.json                             画面集树
    picture-review.json、summary-review.json   网页 AI 多轮复查的状态
    总结.md、总结 (<时间>).md、总结.versions.json   当前总结、其他版本和它们的记录
    .lock                                     process、summarize、fix 运行时持有
  合集\<名字>\
    collection.json                           成员顺序、共用的改正、跳过的视频、跟随的来源
    合集总结.md、学习提纲.md（及其版本）
    downloaded.txt                            跟随播放列表时 yt-dlp 的下载记录
%APPDATA%\video-agent\                        命令行：settings.json、templates\、compression.json
%APPDATA%\Video Agent\                        桌面程序：settings.json、logs\、cookies\（临时）、登录分区
```

文件夹和文件名（包括中文的）被桌面程序、skill 和总结里的链接读取，改名要做迁移。

## 四、边界

- **桌面程序和命令行**：桌面程序把命令行当子进程运行（`cli:json` 解析 `--json` 输出，`cli:text` 取文字；API key 从标准输入传）。JSON 的内容由 `src/video_agent/contract.py` 定义：mypy 检查生成它的代码，测试拿命令行输出的每个值对照它，桌面程序的副本 `gui/src/cli-types.d.ts` 由它生成。`tools --json` 给出 `json_version`，只在去掉字段或字段改变含义时加一，桌面程序和自己的 `CLI_JSON_VERSION` 比较，设置里指定的命令行版本不同时在合集上方提示。`collection.json` 带 `schema_version`，没有的算版本 1，更新的版本拒绝读并说明，免得读错。mypy 只检查标了类型的函数，所以生成 JSON 的函数都标了类型。
- **页面和主进程**：页面在沙箱里运行，开着上下文隔离和严格的 CSP，只能通过 `window.va`（`preload.js`）找主进程。Markdown 用 marked 渲染、DOMPurify 净化；`fs:read` 只读工作区里的文件；`shell:open` 能打开任何路径，因为总结里的链接可能指向任何地方（用户定）。
- **并发**：任务是共享文件的独立进程。命令行写一个视频的文件夹时加锁，文件原子写入；桌面程序的队列让每个视频同时只有一个处理或总结任务，并按种类限制数量。见 [app.md](app.md)。
- **外部工具**：yt-dlp、FFmpeg 和 AutoSlides Extractor 作为程序运行，不复制代码；`PATH` 上的优先。
