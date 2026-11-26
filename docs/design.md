<!--
类别：状态 · 实现层（doc-rules.md）。读者：要改代码的人和 AI。
装：跨子系统的机制和契约：数据流、命令行和桌面程序之间的契约、磁盘上的文件、并发。
不装：模块划分和不变量（→ ../ARCHITECTURE.md）、各子系统内部（→ 各篇 *-design.md）、需求（→ requirements.md）、决策论证（→ adr/）。
-->

# 设计

各子系统的设计：

| 文档 | 回答 |
|---|---|
| [processing-design.md](processing-design.md) | 下载和网站账号、字幕、画面布局和屏幕页、课件、代表画面、补截、压缩 |
| [summary-design.md](summary-design.md) | 总结的规则和模板、主线与单元、版本和谱系、画面集、导入时做什么和查什么 |
| [routes-design.md](routes-design.md) | 几种写总结的方式：Agent、分阶段、模型 API、网页 AI 和 DeepSeek 网页版 |
| [staged-design.md](staged-design.md) | 分阶段写总结：步骤、状态文件、程序检查、画面、agy 通道、代价 |
| [app-design.md](app-design.md) | 桌面程序：任务队列和并发、自动处理、界面、终端、日志、托盘 |
| [collections-design.md](collections-design.md) | 合集、跟随播放列表、合集总结和学习提纲 |
| [distribution-design.md](distribution-design.md) | 安装包、自带的 FFmpeg、许可和隐私说明、更新签名 |

## 数据流

1. **下载**（可选）：`download URL` 运行 yt-dlp，把视频和网站字幕存进一个文件夹（桌面程序用 `<工作区>\下载\`）。它不开始处理；桌面程序在开着「下载完自动处理」时随后排一个 `process`。
2. **处理**：`process VIDEO` 读视频，在工作区里写它的文件夹：字幕（旁边或内嵌的字幕，否则加了 `--allow-remote-asr` 用必剪）、画面布局、屏幕区域里的屏幕页、代表画面，以及 `summary-context.md`（字幕和当时屏幕上的画面穿插排列）。
3. **写总结**，都按选定的模板：
   - 模型 API：`summarize` 发出字幕和画面，写下结果；
   - Agent：Claude Code、Codex 或其他 Agent 照 skill 做，写 `总结.draft.md`，用 `summarize --import` 保存；
   - 分阶段：`summarize --staged` 经 agy 命令行，主对话分单元、每个单元一个对话同时写，程序检查、合并、组装，再走同一个导入（[staged-design.md](staged-design.md)）；
   - 网页 AI：`pack` 生成提示词、zip 或文件夹，回答经 `summarize --import` 存回（修好链接）；DeepSeek 网页版由桌面程序一轮轮自动跑；
   - 用户自己的文字，走同一个导入。

   保存时程序照详细内容排出「主线与单元」，并给「要点」加上编号跳转链接和对应画面。新文字只在还没有总结或明确要求时成为 `总结.md`，否则存成一个版本。
4. **合集**：`collection` 把视频编成组；`summarize --collection` 从各集的总结写合集总结或学习提纲。

## 接口契约

### 命令行和桌面程序

- 桌面程序把命令行当子进程运行：`cli:json` 解析 `--json` 输出，`cli:text` 取文字；API key 从标准输入传。
- JSON 的内容由 `src/video_agent/contract.py` 定义：mypy 检查生成它的代码，测试拿命令行输出的每个值对照它，桌面程序的副本 `gui/src/cli-types.d.ts` 由它生成。mypy 只检查标了类型的函数，所以生成 JSON 的函数都标了类型。
- `tools --json` 给出 `json_version`，只在去掉字段或字段改变含义时加一。桌面程序和自己的 `CLI_JSON_VERSION` 比较，设置里指定的命令行版本不同时在合集上方提示。
- `collection.json` 带 `schema_version`，没有的算版本 1；更新的版本拒绝读并说明，免得读错。

### 页面和主进程

- 页面在沙箱里运行，开着上下文隔离和严格的 CSP，只能通过 `window.va`（`preload.js`）找主进程。
- Markdown 用 marked 渲染、DOMPurify 净化；`fs:read` 只读工作区里的文件；`shell:open` 能打开任何路径，因为总结里的链接可能指向任何地方（[ADR-0002](adr/0002-no-allowlist-for-the-page.md)）。

## 持久化

### 磁盘上的文件

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

文件夹和文件名（包括中文的）被桌面程序、skill 和总结里的链接读取，改名要做迁移（不变量 `A7`）。

### 并发

任务是共享文件的独立进程。命令行写一个视频的文件夹时加锁，文件原子写入（不变量 `C1`、`C2`）；桌面程序的队列让每个视频同时只有一个处理或总结任务，并按种类限制数量。哪些任务能同时跑见 [app-design.md](app-design.md)。
