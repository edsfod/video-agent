# 需求

> 给谁看：要判断系统行为对不对、参与设计和实现的人和 AI。回答：要解决什么、谁在什么情况下用、系统应该做到什么、怎样算做到。
> 怎么做到见 [design.md](design.md) 和各篇 `*-design.md`；模块和不变量见 [ARCHITECTURE.md](../ARCHITECTURE.md)。
> 需求编号只增不改，废弃的不复用，列在末尾「已废弃编号」；代码注释和发布说明引用这些编号。总结提示词的逐条要求在 [summary-requirements.md](summary-requirements.md)，编号前缀 `PRM-`。

## 目标

- **G1 代替看视频的笔记**：看一个视频（课堂录像、讲座、访谈、教程、新闻）很费时间，而且看完记不住。用户要的是一份能代替看视频的笔记：视频讲了什么、要照办的事、日后能用上的内容，每一点能回到视频的时间点，画面上的内容也在里面。

## 范围与不做什么

- **适用**：只支持 Windows（用户定）。
- **许可**：AGPL-3.0-or-later；安装包里的 FFmpeg 按 LGPL，每次发布附上源码。
- **计划中**：总结文章，见 [roadmap.md](roadmap.md)。
- **不做**：
  - 常驻的 MCP 服务；
  - 某个平台专用的逻辑（例如雁课堂的归 AutoSlides）；别的工具的文件夹布局只作为有名字的约定加手动导入支持，不内置；
  - 替用户安装别的工具：缺什么就说缺什么、怎么指定。唯一的例外是用户在设置里点了，才从作者的发布页下载 AutoSlides Extractor 的免安装版。

## 场景

- **S1 桌面程序**：用户在桌面程序里添加本地视频或粘贴链接，程序下载、处理，用户选一种方式写总结，在窗口里读。
- **S2 Agent**：用户在 Claude Code、Codex 或其他 Agent 里让它照 skill 处理视频并写总结。
- **S3 命令行**：用户或脚本用 `video-agent` 命令行批量下载、处理、写总结。
- **S4 合集**：用户把一门课、一个系列或一个播放列表编成合集，写合集总结和学习提纲来复习，合集跟着播放列表收新视频。

## 拿到视频和字幕（`SRC`）

### SRC-01 本地视频和链接

本地视频直接处理；给链接时先下载，下载和处理是分开的两步。

- **服务于**：G1、S1、S2、S3
- **规格**：
  - `process` 接受任何本地视频路径，从不下载；
  - `download` 单独、可选，运行 yt-dlp；
  - 分享链接里的跟踪参数去掉后再下载。
- **验收**：
  - `test_process_uses_sidecar_and_frame_saves_extra` 通过；
  - `test_download_returns_paths_and_refuses_playlists` 通过；
  - `test_share_tracking_is_dropped_from_links` 通过；
  - 端到端测试「process the video from the window」通过。

### SRC-02 网站字幕和网站账号

下载时一起存下网站的字幕；要登录才给的字幕（例如 B 站的 AI 字幕），能在程序里登录网站账号，把登录状态交给 yt-dlp 用。

- **服务于**：G1、S1
- **验收**：
  - `test_download_saves_subtitles_and_passes_cookies` 通过；
  - 端到端测试「a site login is exported as a Netscape cookies file for yt-dlp」通过；
  - 实机：在桌面程序里登录 B 站，下载一个只有 AI 字幕的视频，视频文件夹里有这份字幕。

### SRC-03 先用已有的字幕，再用语音识别

字幕先用已有的，没有时才用语音识别；音频上传到远程识别服务要用户同意。

- **服务于**：G1、S1、S2、S3
- **规格**：
  - 已有的字幕：视频内的字幕轨、旁边同名的字幕文件；名字不同的字幕文件可以手动导入；
  - 语音识别可替换，现在接的是必剪；
  - 命令行里音频只有加了 `--allow-remote-asr` 才上传；
  - 桌面程序里「没有字幕时用必剪转录」默认开，勾选框说明音频会发给 B 站；从本地添加、没有字幕的视频先问（`APP-02`）。
- **验收**：
  - `test_sidecar_prefers_human_chinese_tracks_and_skips_other_videos` 通过；
  - `test_a_chosen_subtitle_file_becomes_the_transcript_whatever_its_name` 通过；
  - `test_process_without_subtitles_asks_for_consent` 通过；
  - `test_allow_remote_asr_needs_bcut` 通过。

### SRC-04 改正字幕

反复听错的名字和术语能改正：改正另存一份，原字幕不动，改正可以撤回；改正后的字幕用于此后的所有总结。

- **服务于**：G1
- **验收**：
  - `test_fix_writes_a_cleaned_transcript_that_the_context_uses` 通过；
  - 端到端测试「a correction gives a cleaned transcript and keeps the original」通过。

## 画面（`FRM`）

### FRM-01 屏幕页

屏幕上出现过的每一页（幻灯片、代码、文档）都截到，用原始分辨率，一页一张，同一页逐步出现的几步合成一页。

- **服务于**：G1
- **规格**：
  - 先识别画面布局；屏幕旁边或里面有摄像头画面时，只在屏幕区域里按原始分辨率找翻页；
  - 装了 AutoSlides Extractor 时由它找（先裁出屏幕区域给它），否则用本程序自己的翻页规则；`--no-extract-slides` 或 `AUTOSLIDES_EXTRACTOR=none` 关掉它。
- **验收**：
  - `test_split_layout_finds_the_screen_and_its_pages` 通过；
  - `test_an_addition_to_a_page_keeps_the_fuller_picture` 通过；
  - `test_merge_keeps_new_pages_and_drops_repeats_and_passing_states` 通过；
  - `test_autoslides_extractor_finds_the_screen_pages_where_installed` 通过。

### FRM-02 其余画面和补截

屏幕页以外的画面按间隔和场景变化抽取；写总结时能按时间补截。

- **服务于**：G1
- **规格**：
  - 代表画面跟着视频走：每个不同的页面和场景都要有，不设固定的少数几张；
  - 不认为编码关键帧和场景变化本身有意义；
  - 数量上限只用来挡住失控（ARCHITECTURE.md「横切关注点」）。
- **验收**：
  - `test_frames_closer_than_a_second_are_merged` 通过；
  - `test_no_scene_changes_is_not_an_error` 通过；
  - `test_process_uses_sidecar_and_frame_saves_extra` 通过（补截存进 `frames/extra/`）。

### FRM-03 导入课件

能导入一个放着课件图片的文件夹，代替截下的屏幕页，按时间表或画面对上时间。

- **服务于**：G1
- **验收**：
  - `test_slides_autoslides_keeps_beside_a_screen_recording_are_taken_with_their_times` 通过；
  - `test_a_chosen_slide_folder_without_times_is_placed_by_the_screen_pages` 通过；
  - 端到端测试「a folder of slide images is taken and placed by the screen pages」通过。

## 总结（`SUM`）

### SUM-01 总结的内容

总结让没看过视频的读者知道视频讲了什么、记住要照办的事、日后能用上视频的内容。

- **服务于**：G1
- **规格**：
  - 分得清哪些是视频说的、哪些是视频引用别人的、哪些是总结者加的；
  - 每一点能回到视频的时间点；
  - 画面上的文字、表格、图表读进总结；
  - 逐条要求见 [summary-requirements.md](summary-requirements.md)（`PRM-*`）。
- **验收**：
  - `PRM-*` 各条在模板或程序里有落点（summary-requirements.md「写在哪里」一列）；
  - `test_the_checks_name_what_a_chat_ais_summary_leaves_out` 通过；
  - `test_the_checks_ask_that_key_points_leave_nothing_out` 通过；
  - 人工评审：办法待定（见「待定」）。上面几条只查格式和覆盖，查不出具体机制被概括成空话这类问题。

### SUM-02 几种写总结的方式写出同一种总结

几种写总结的方式都按用户选的模板写，写出同一种总结。`SUM-06` 的结构先只由分阶段写出，别的方式以后再适配（用户定）。

- **服务于**：G1、S1、S2、S3
- **规格**：
  - Agent 应用（按 skill）；
  - 分阶段（agy 命令行）；
  - 模型 API；
  - 网页 AI：复制材料或导出文件；DeepSeek 网页版全自动。
- **验收**：
  - 端到端测试「summary through the model API, with one frame tool round」通过；
  - 端到端测试「another agent writes a summary from standard input or from a task file」通过；
  - `test_a_whole_run_writes_each_unit_in_its_own_conversation_and_saves_the_tokens` 通过；
  - `test_pack_zips_the_prompt_with_frames_at_their_folder_paths` 通过；
  - 端到端测试「a DeepSeek task waits out a refusal for sending too often and checks what went out」通过。

### SUM-03 模板

自带「标准」模板；用户可以照着它做自己的模板，选哪个模板写。

- **服务于**：G1
- **验收**：
  - `test_template_is_packaged` 通过；
  - `test_several_templates_one_chosen_and_one_named_per_summary` 通过；
  - `test_the_users_copy_of_a_template_is_used_and_knows_when_the_built_in_one_changed` 通过。

### SUM-04 每一版总结都保留

同一个视频的每一版总结都保留，由用户决定用哪一版。

- **服务于**：G1
- **验收**：
  - `test_imports_never_lose_a_summary_and_versions_can_be_chosen` 通过；
  - `test_no_tools_and_a_second_summary_is_kept_beside_the_first` 通过。
- **相关不变量**：`C3`。

### SUM-05 合集

几个相关的视频组成合集，有合集总结和学习提纲；合集可以跟着播放列表下载新视频。

- **服务于**：G1、S4
- **验收**：
  - `test_members_keep_their_order_and_shared_terms_reach_every_transcript` 通过；
  - `test_overview_and_guide_from_the_summaries` 通过；
  - `test_a_followed_list_downloads_only_its_new_videos` 通过；
  - `test_an_existing_collection_can_follow_its_list_later` 通过。

### SUM-06 总结的结构

总结把视频里流式的、信息密度低的内容，整理成由单元组成的结构：读者先看前置部分和提纲，再点开要看的单元。

- **服务于**：G1
- **规格**：
  - 总结分两部分，前置部分在前、知识部分在后（用户定）。按一句话说的是什么来分：
    - 说的是视频这件事本身（谁讲、什么类型、讲了哪些、预设观众知道什么）：元信息、概要；
    - 对这批观众的要求和告知（作业、截止日期、考试）：需留意；讲者为它讲的理由是知识；
    - 说的是视频以外的世界（断言、主张、定义、做法），在别的场合也用得上：知识。
  - 前置部分的顺序：元信息、需留意、概要（用户定）。
  - 概要从视频外描述视频做了什么，写成「讲者论证了 X」这类说法；结论本身在单元里（用户定）。
  - 知识部分由单元组成，单元由条目组成（用户定）。单元平铺，各占一段连续时间，层级只在单元内部（[ADR-0012](adr/0012-flat-units.md)）。
  - 条目沿三条互相独立的轴区分：来源（讲者、讲者引用的人、总结者），标签（讲者怎样呈现：事实、观点、推断……，不判断真假），在单元树里的位置（头、前提、步骤、展开）。视图只用位置。
  - 不存线性的详细内容。读者从提纲进入，点开单元看详情；任一提纲全部点开，拼出全部单元的全部内容（[ADR-0013](adr/0013-outlines-instead-of-a-linear-body.md)）。
  - 主线是一个话题加可以没有的主结论，贯穿一组单元；一个视频可以有几条主线，一条主线可以有几个主结论。有主结论的主线，成员是推进它的单元；没有主结论的，成员是讲这个话题的单元。旁支是和某条主线有关、但不是它的成员的单元，挂在一个单元上、两个单元之间或整条主线上（用户定）。判据和谁来判断见 [ADR-0012](adr/0012-flat-units.md)。
  - 成稿存成程序能按单元、条目、关系读的数据；`总结.md` 由程序从数据生成，给读文字的地方用（用户定，[ADR-0014](adr/0014-structured-summary-data.md)）。
- **验收**：
  - 未实现。
  - 程序检查：每个单元恰好有一个归属，每个条目都挂在单元树上；提纲由程序从数据生成，所以这两条成立时每个提纲都完备（[ADR-0014](adr/0014-structured-summary-data.md)）。
  - 人工评审：办法待定（见「待定」）。

## 管理（`MGT`）

### MGT-01 压缩视频

能压缩视频省空间：重新编码后分辨率不变、看不出画质差别。

- **服务于**：G1
- **规格**：
  - 只用核对过、确实更小的副本替换原文件；
  - 默认只压缩本程序下载的视频；用户从自己硬盘添加的要用户同意，因为会替换原文件。
- **验收**：
  - `test_compress_replaces_the_video_once_and_leaves_efficient_ones` 通过；
  - `test_compress_check_tells_the_state_and_forgets_it_when_the_file_changes` 通过；
  - 实机：同一段压缩前后对照播放，分辨率相同，看不出差别。

### MGT-02 删除视频

能一次删掉选中的视频和它的全部产物（字幕、画面、所有版本的总结、在合集里的位置）。

- **服务于**：G1、S1
- **规格**：
  - 本程序下载的视频文件一起删，用户自己添加的视频文件保留。
- **验收**：
  - `test_a_downloaded_video_goes_whole_and_a_local_one_keeps_its_file` 通过；
  - `test_a_followed_collections_download_folder_counts_as_downloaded` 通过；
  - 端到端测试「chosen videos are deleted together: a downloaded one with its file, a local one keeps its file」通过。
- **相关不变量**：`C4`。

### MGT-03 不动源视频

不修改、不移动源视频；产物都放进工作区。

- **服务于**：G1
- **规格**：
  - 例外只有两个：`compress` 用核对过的更小副本替换（`MGT-01`），`delete` 删除本程序下载的视频（`MGT-02`）。
- **验收**：
  - 实机：`process` 一个本地视频前后，它的大小和修改时间不变，它所在的文件夹里没有多出文件。

## 桌面程序（`APP`）

### APP-01 桌面程序和命令行都能做全部操作

桌面程序能完成以上全部操作；命令行工具也能，供 Agent 和批量处理用。

- **服务于**：S1、S2、S3
- **验收**：
  - 端到端测试（`gui/test/e2e.test.js`）通过；
  - [commands.md](commands.md) 列出的每个命令都能在命令行运行。

### APP-02 下载或添加后自动处理

下载或添加视频后默认自动处理，可以关；没有字幕的本地视频先问是否用语音识别。

- **服务于**：S1
- **验收**：
  - 端到端测试「added local videos are processed at once, and those without subtitles are asked about first」通过；
  - `gui/test/tasks.test.js`「a download follows up only the videos it saved, not those it found saved already」通过。

### APP-03 终端、托盘、任务队列和日志

有内嵌终端、托盘、任务队列和任务日志。

- **服务于**：S1
- **验收**：
  - 端到端测试「embedded terminal runs a command in the video folder」通过；
  - 端到端测试「closing the window keeps the app in the tray」通过；
  - 端到端测试「logs record every job and never the API key」通过；
  - `gui/test/tasks.test.js` 通过。

## 安装和更新（`INS`）

### INS-01 安装包自带一切

安装包装完就能用，不需要另装别的。

- **服务于**：S1
- **规格**：
  - 自带命令行工具、yt-dlp 和自己编译的 LGPL FFmpeg；
  - `PATH` 上已有的优先。
- **验收**：
  - 打包时，冻结的命令行在 `PATH` 只剩 `System32` 的情况下处理并打包一段生成的视频（[distribution-design.md](distribution-design.md)「自带的 FFmpeg」）；
  - `installer-path.test.js` 通过。

### INS-02 命令行用 uv 安装

命令行工具用 uv 安装，不需要 git。

- **服务于**：S2、S3
- **规格**：
  - yt-dlp 和 FFmpeg（`imageio-ffmpeg`）是 Python 依赖；
  - README 和 skill 的安装命令用 GitHub 发布页附的 wheel。
- **验收**：
  - `test_versions_match` 通过（检查 README 和 SKILL.md 里 wheel 的链接）；
  - `test_works_without_ffmpeg_on_path` 通过。

### INS-03 Agent 插件

Agent 插件装进 Claude Code 或 Codex；桌面程序可以从本机的副本安装。

- **服务于**：S2
- **验收**：
  - 端到端测试「the skill is copied into a picked folder, but never over another folder of that name」通过；
  - 实机：在桌面程序里点安装按钮，Claude Code 里出现这个插件。

### INS-04 更新

桌面程序能检查更新、只下载变化的部分、静默重装；设置、工作区和已装的插件跟着保留和更新。

- **服务于**：S1
- **验收**：
  - `update-plan.test.js` 通过；
  - `update-install.test.js`「an update installs silently and the app starts again」通过（只在 GitHub 上跑）。

### INS-05 更新源回退

GitHub 访问不了时改走 GitHub API 或下载镜像。

- **服务于**：S1
- **验收**：
  - `update.test.js`「a signed update is offered with its notes, after skipping the dead source」通过；
  - `update.test.js`「a slow download moves to the next source, which fetches the installer from the versioned folder and checks its sha512」通过。

### INS-06 只接受签名有效的更新

更新器只安装签名验证通过的更新。

- **服务于**：S1
- **验收**：
  - `update.test.js`「the startup check refuses a latest.yml that does not match its signature」通过；
  - `update-signature.test.js` 通过。
- **相关不变量**：`C5`。

## 隐私（`PRV`）

### PRV-01 隐私说明和使用条款

安装时先显示隐私说明和使用条款（`PRIVACY.md`），设置里随时能看。

- **服务于**：S1
- **验收**：
  - 端到端测试「settings show the version, the licence and PRIVACY.md」通过；
  - 实机：运行安装包，第一页是 `PRIVACY.md` 的内容。

### PRV-02 API key

API key 存在 Windows 凭据管理器里，任务日志从不记录 API key。

- **服务于**：S1、S3
- **验收**：
  - `test_config_saves_settings_and_key` 通过；
  - 端到端测试「logs record every job and never the API key」通过。

## 待定

- `SUM-01` 的人工评审办法：怎样判断一份总结能代替看视频。要能对照字幕逐段核查，并在不同的写法、模型之间比较。
- `SUM-06` 还没定的：
  - 单元点开以后按时间显示还是按树显示，或者看从哪个提纲进来。
  - 说的是这份总结本身可不可靠的（需确认、AI 未核对）放在哪：条目本身留在单元里，前置部分是否加一行「关于这份总结」，写模型、用量和需确认、未核对的处数。
  - 「需留意」要不要改名。
  - 标签要不要把非真非假的主张（「应当这样做」）从观点里分出来：核对它时查的是理由够不够，不是真假。
  - 展开的交互：怎么切换视图、怎么展开、跳过去以后怎么跳回；图和视频片段放在哪、放多少，从任意文字点开相关的画面；点时间点直接播放那一段视频。

## 已废弃编号

无。
