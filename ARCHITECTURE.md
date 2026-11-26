<!--
类别：状态 · 实现层。读者：要改代码的人和 AI。
装：全局概览、代码地图、不变量、横切关注点（含跨模块改动清单）。
不装：机制细节、文件格式和接口字段（→ docs/design.md 与各篇 docs/*-design.md）、需求（→ docs/requirements.md）、
      决策论证（→ docs/adr/）、测试和发布的步骤（→ docs/development.md）。
模块用文字描述并点出关键名字供搜索；只写很少变化的东西。
-->

# Architecture

## 全局概览

Video Agent 把一段视频变成可以读的总结：先整理出字幕和当时屏幕上的画面，再由模型照模板写总结。要解决的问题见 [docs/requirements.md](docs/requirements.md)。

结构是一个核心、三个前端。处理媒体、写总结、保存总结的逻辑都在 Python 命令行工具里；桌面程序、Agent skill 和终端都把它当程序运行，读它的文字或 `--json` 输出。

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

数据怎么流、磁盘上有哪些文件、命令行和桌面程序之间的契约见 [docs/design.md](docs/design.md)。

## 代码地图

### `src/video_agent/`：命令行

- **入口和契约**：`cli.py` 每个命令一个函数，输出文字，加 `--json` 输出 JSON；`contract.py` 定义 `--json` 输出、`manifest.json` 和 `collection.json` 的类型；`settings.py` 管设置和 API key（Windows 凭据管理器）；`files.py` 管每个视频文件夹的锁（`video_lock`）和原子写（`write_text`、`replace`）。
- **视频和字幕**：`download.py` 运行 yt-dlp；`transcript.py` 读、挑、写带时间的字幕；`providers/bcut.py` 是必剪语音识别；`corrections.py` 是字幕改正（`fix`）。见 [processing-design.md](docs/processing-design.md)。
- **画面**：`media.py` 运行 FFmpeg 和 ffprobe；`layout.py` 找屏幕区域和摄像头区域；`page_rules.py` 决定留哪些屏幕页，是纯函数，不运行 FFmpeg，用合成的图测试；`slide_extractor.py` 接 AutoSlides Extractor 和导入的课件；`compress.py` 原地重编码成 AV1。见 [processing-design.md](docs/processing-design.md)。
- **处理**：`processor.py` 实现 `process`，建视频文件夹、`manifest.json` 和 `summary-context.md`；`evidence.py` 读处理过的文件夹和清单。
- **写总结的方式**：`summarize.py` 加 `model_api.py`（模型 API）；`staged.py`、`staged_agy.py`、`staged_prompts.py`（分阶段，经 agy）；`packing.py`（给网页 AI 的材料）；`importer.py`（`summarize --import`：Agent、分阶段、网页 AI 和用户自己的文字都经它保存）。见 [routes-design.md](docs/routes-design.md)、[staged-design.md](docs/staged-design.md)。
- **总结的加工和保存**：`forest.py` 排「主线与单元」、给「要点」加链接和画面；`summary_review.py` 是导入时的检查和网页 AI 的多轮复查；`picture_review.py`、`pictures.py` 管画面调整和画面集；`versions.py` 管版本和谱系；`templates.py` 和 `prompts/` 是模板。见 [summary-design.md](docs/summary-design.md)。
- **合集和删除**：`collection.py`、`collection_summary.py`、`removal.py`。见 [collections-design.md](docs/collections-design.md)。

### `gui/`：桌面程序

Electron。不含处理媒体或写总结的逻辑，只运行命令行和 Agent。见 [app-design.md](docs/app-design.md)。

- **主进程**（`gui/src/`）：
  - 启动和共用：`main.js` 启动其余模块和程序；`shared.js` 放各模块共用的窗口、托盘、日志、更新器、任务队列、运行中的任务和终端；`settings.js` 是窗口的设置；`window.js` 管窗口和托盘；`logs.js` 管程序日志和每个任务一份的日志。
  - 页面和主进程之间：`ipc.js` 是页面能调用的全部处理函数；`preload.js` 提供 `window.va`，类型在 `va.d.ts`；`cli-types.d.ts` 是命令行 JSON 的类型，由 `scripts/cli_types.py` 生成。
  - 任务：`tasks.js` 是队列规则和哪些任务能同时跑，不依赖 Electron；`jobs.js` 拼每种任务的命令行、Agent 路线、下载用的 cookie 和后续任务；`programs.js` 找到并运行命令行、Claude Code、Codex 和其他 Agent、终端，以及插件和许可文件；`models.js` 列出每种写总结的方式提供哪些模型和思考强度。
  - 外部的程序和网站：`chat-rounds.js`、`deepseek.js` 是 DeepSeek 网页版路线；`accounts.js` 管网站登录和下载用的 cookie；`plugins.js` 安装 Agent 插件、复制 skill；`extractor.js` 把 AutoSlides Extractor 的免安装版下载到数据文件夹，`childEnv` 让命令行用它。
  - 更新：`updater.js` 管更新源，`update-plan.js` 管差量下载，`update-signature.js` 验证 `latest.yml` 的签名。
- **页面**（`gui/src/renderer/`）：ES 模块，从 `file://` 加载，没有构建步骤。`app.js` 启动，`state.js` 放状态和共用函数，每个视图一个模块。
- **安装器**（`gui/installer/`）：NSIS 的补充，PATH 页面和脚本。见 [distribution-design.md](docs/distribution-design.md)。

### `skills/` 和插件清单

`skills/video-agent/SKILL.md` 是给 Agent 的命令行用法；`.claude-plugin/`、`plugin.json` 让 Claude Code 和 Codex 能安装它。桌面程序把它复制到其他 Agent 的 skill 文件夹。

### `packaging/`、`scripts/`、`.github/`

- `packaging/build_cli.py` 用 PyInstaller 冻结命令行；`packaging/ffmpeg/build.sh`、`fetch.sh` 编译和取回 LGPL FFmpeg；`packaging/notices.py` 写第三方声明。见 [distribution-design.md](docs/distribution-design.md)。
- `scripts/bump_version.py` 改版本号；`scripts/cli_types.py` 生成 `cli-types.d.ts`；`scripts/lint_writing.py` 查文字写法；`scripts/githooks/` 是 git 钩子。
- `.github/workflows/test.yml` 按改动挑任务测试，`release.yml` 在标签上构建和建草稿；`.github/scripts/changed-jobs.sh` 决定跑哪些任务；`.github/actions/ffmpeg` 提供 FFmpeg。见 [docs/development.md](docs/development.md)。

## 不变量

**架构不变量**：

| 编号 | 不变量 | 违反后果 | 守护位置 |
|---|---|---|---|
| `A1` | 处理媒体、写总结、保存总结的逻辑只在命令行里；桌面程序和 skill 只运行命令行、读它的输出 | 三个前端的行为不一致，改一处漏别处 | 无自动检查 |
| `A2` | `--json` 输出、`manifest.json`、`collection.json` 的形状只在 `contract.py` 定义；`gui/src/cli-types.d.ts` 由 `scripts/cli_types.py` 生成，不手改 | 桌面程序读错或读不到字段 | mypy；`tests/conftest.py` 的 `checked_json`；`test_the_apps_types_are_written_from_the_contract` |
| `A3` | `contract.JSON_VERSION` 只在去掉字段或字段改变含义时加一；`gui/src/renderer/state.js` 的 `CLI_JSON_VERSION` 和它相同 | 桌面程序配着不兼容的命令行运行而不提示 | `test_the_window_reads_the_json_version_the_cli_prints` |
| `A4` | `collection.json` 带 `schema_version`；比 `contract.COLLECTION_VERSION` 新的拒绝读并说明 | 旧程序读错新格式的合集 | `test_collection_json_carries_its_version_and_a_newer_one_is_refused` |
| `A5` | 页面在沙箱里运行（`contextIsolation`、`sandbox`、CSP），只经 `window.va` 找主进程 | 页面能直接读写任意文件 | `gui/src/window.js` 的 `webPreferences`；`preload.js` 由 `npm run typecheck` 对照 `va.d.ts` 检查 |
| `A6` | 版本号在各处一致，只用 `scripts/bump_version.py` 改 | 安装包、wheel、插件和 README 的版本对不上 | `test_versions_match`、`test_bump_version_changes_every_file_or_none` |
| `A7` | 视频文件夹和文件的名字（含 `总结.md` 等中文名）被桌面程序、skill 和总结里的链接读取；桌面程序和 skill 写的名字与命令行的常量（`evidence.SUMMARY_NAME`、`collection.OVERVIEW`、`collection.GUIDE`、`cli.DOWNLOADS`）一致；改名必须带迁移 | 桌面程序和 skill 找不到文件；已有工作区里的总结和链接失效 | `tests/test_names.py`（名字一致）；迁移无自动检查 |

**数据安全约束**（违反会丢失或弄坏用户的数据，或让用户装上不可信的程序）：

| 编号 | 约束 | 违反后果 | 守护位置 |
|---|---|---|---|
| `C1` | `process`、`summarize`、`fix` 写视频文件夹时持有它的 `.lock`；`files.LOCK_WAIT_S` 内拿不到锁就报错退出，不排队 | 两个写的人互相覆盖 | `files.video_lock`；`test_a_running_writer_blocks_process_and_summarize_but_not_frame`、`test_video_lock_is_released_when_its_process_is_killed` |
| `C2` | 共享文件（`transcript.*`、`summary-context.md`、`manifest.json`、`总结.md`）先写到同一文件夹里的临时文件再改名 | 读的人看到写了一半的文件 | `files.write_text`、`files.replace` |
| `C3` | 导入的新文字只在还没有总结或明确要求时成为 `总结.md`，否则存成一个版本 | 用户的总结被覆盖 | `test_imports_never_lose_a_summary_and_versions_can_be_chosen` |
| `C4` | 删除视频时，视频文件只在是本程序下载的时才删 | 删掉用户自己的视频 | `removal.py`；`test_a_downloaded_video_goes_whole_and_a_local_one_keeps_its_file`、`test_a_followed_collections_download_folder_counts_as_downloaded` |
| `C5` | 更新器只接受 `latest.yml.sig` 用内置公钥验证通过的 `latest.yml` | 镜像能让用户装上别的程序 | `gui/src/update-signature.js`；`gui/test/update-signature.test.js` |
| `C6` | 安装包里的 FFmpeg 是 LGPL 构建，不开 `--enable-gpl` | 分发 GPL 程序却不附源码 | `packaging/ffmpeg/build.sh`（`ffmpeg -L` 不是 LGPL 时失败）；`fetch.sh --verify` |

## 横切关注点

- **数据位置**：视频的文件夹和合集都在工作区里；命令行的设置在 `%APPDATA%\video-agent\`，桌面程序的在 `%APPDATA%\Video Agent\`。各文件用途见 [docs/design.md](docs/design.md)。
- **外部工具**：yt-dlp、FFmpeg、AutoSlides Extractor 作为程序运行，不复制代码；`PATH` 上的优先，再找自带的。
- **文本文件**：仓库统一用 LF（`.gitattributes`）；Python 写文本文件时传 `newline='\n'`。
- **隐私**：音频只在加了 `--allow-remote-asr` 时发给必剪；传 API key 用标准输入，不写进日志；脚本输出里 DeepSeek 的请求和响应要过滤，因为里面带登录令牌。
- **测试分层**：命令行用 pytest 和 mypy，真实 FFmpeg 处理生成的短片，必剪对着本机假服务器；桌面程序用 `npm run typecheck` 和 `node --test`，开窗口的端到端测试和改真实安装的测试只在 GitHub 上跑。见 [docs/development.md](docs/development.md)。
- **文字**：文档、注释、提交信息的写法由 `scripts/lint_writing.py` 检查。见 [docs/writing.md](docs/writing.md)。

### 跨模块改动清单

| 改动 | 需要同时修改 | 检查 |
|---|---|---|
| 改 `--json` 输出或 `manifest.json`、`collection.json` 的字段 | `contract.py` 和生成它的代码；`uv run scripts/cli_types.py` 重写 `cli-types.d.ts`；去掉字段或改含义时 `JSON_VERSION` 和 `CLI_JSON_VERSION` 一起加一；[docs/commands.md](docs/commands.md) | `uv run pytest`、`npm run typecheck` |
| 改 `collection.json` 的格式，旧程序读不了 | `contract.COLLECTION_VERSION`；`collection.py` 的读写 | `uv run pytest tests/test_contract.py` |
| 页面要主进程做一件新的事 | `ipc.js` 的处理函数、`preload.js`、`va.d.ts` | `npm run typecheck` |
| 加或改命令、选项 | `cli.py`；[docs/commands.md](docs/commands.md)、[docs/cli.md](docs/cli.md)；Agent 要用的写进 `SKILL.md`；窗口要用的改 `jobs.js` | `uv run pytest` |
| 改总结模板要模型做的事 | `prompts/summary.md`；[docs/summary-requirements.md](docs/summary-requirements.md)；`packing.py`、`summary_review.py` 里对应的部分 | `uv run pytest tests/test_summarize.py` |
| 改视频文件夹或文件的名字 | 命令行的常量和迁移代码；`gui/`；`SKILL.md`；`tests/test_names.py` 的表；[docs/design.md](docs/design.md) 的磁盘文件 | `uv run pytest tests/test_names.py`；端到端测试 |
| 改版本号 | 只运行 `uv run scripts/bump_version.py <版本>` | `test_versions_match` |
| 改 `packaging/ffmpeg/build.sh` 的版本或编译命令 | 换预编译包，步骤见 [docs/development.md](docs/development.md)「构建」 | `bash packaging/ffmpeg/fetch.sh --verify` |
| 移动或改名文档 | 代码注释里的 `docs/` 路径 | `rg "docs/" src gui packaging scripts .github` |
