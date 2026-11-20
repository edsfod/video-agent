# 分发：安装包、FFmpeg、许可、更新

> 给谁看：要改打包、安装、许可说明或更新的人和 AI。回答：三种装法怎么做到装完就能用、自带的 FFmpeg 怎么编译、许可和隐私怎么给用户看、更新怎么下载和验证。
> 构建和发布的步骤见 [development.md](../development.md)。

## 一、三种装法

- **安装包**自带一切（用户 2026-10-27 定）：`packaging/build_cli.py` 用 PyInstaller 冻结命令行（Python、yt-dlp 和自己编译的 FFmpeg），electron-builder 打成未签名的 NSIS 安装包，插件文件放在 `resources/plugin`；node-pty 用它的 N-API 预编译版（`npmRebuild: false`）。桌面程序先找设置里指定的命令行，再找自带的，再找 `PATH` 上的 `video-agent`；它启动的任务和终端把自带的文件夹放在 `PATH` 最前。
- **命令行用 uv 安装**，不需要 git：README、skill 和桌面程序最后的退路 `uvx` 都用 GitHub 发布页附的 wheel，不用 `git+` 链接。FFmpeg 来自 PyPI 的 `imageio-ffmpeg`，yt-dlp 来自 PyPI；`PATH` 上已有的优先。`imageio-ffmpeg` 没有 ffprobe，`media.probe` 从 ffmpeg 的输出里读需要的信息（流、编码、语言、时长），测试保证两种读法结果一样。`download` 传 `--ffmpeg-location`，让 yt-dlp 用同一个 ffmpeg 合并音视频。
- **Agent 插件**：`claude`、`codex plugin marketplace add edsfod/video-agent` 从 GitHub 安装要 git，所以桌面程序有从本机副本安装的按钮。新版本第一次启动时，已装插件的 Claude Code 或 Codex 会照安装按钮的步骤刷新插件。

## 二、PATH 和快捷方式

- 安装程序把 `resources\cli` 追加到用户的 `PATH`，卸载时去掉（`gui/installer/`）。选文件夹之后有一页说明这件事，带一个默认勾上的选项；选择记在 `HKCU\Software\Video Agent`，更新和静默安装照用，CI 两种都检查。追加而不是放在最前：用户自己装的命令行在终端里优先。
- 修改 `HKCU\Environment` 用注册表接口并带 `DoNotExpandEnvironmentNames`、保留值的类型：`[Environment]::GetEnvironmentVariable` 返回展开后的文字，写回去会把 `%USERPROFILE%\bin` 这类条目变成固定路径。静默安装再卸载后 `PATH` 一字节不差（实测 2026-10-27）。
- electron-builder 把安装包（约 160 MB）复制到 `%LOCALAPPDATA%\video-agent-gui-updater`，更新用它做差量下载；卸载时删掉这个文件夹（electron-builder 自己的卸载程序会留下它）。桌面和开始菜单的快捷方式用 electron-builder 的默认。

## 三、自带的 FFmpeg

- 安装包里的 FFmpeg 按 LGPL 自己编译（用户 2026-10-28 定）：原来带的 imageio-ffmpeg 版本是 GPLv3（含 x264、x265），却没附源码。`packaging/ffmpeg/build.sh` 在 MSYS2 UCRT64 里用 GCC 静态编译 FFmpeg 9.0.2，带 dav1d 1.5.4（AV1 解码）、SVT-AV1 4.2.0（压缩用）和 MSYS2 的 zlib；不开 `--enable-gpl`、自动检测的库、网络、设备、硬件加速；所有原生的解码器、封装、滤镜都保留。三个源码包都按 SHA-256 固定。`ffmpeg -L` 不是 LGPL、或缺了用到的滤镜和编码器时，脚本失败。
- 为此换掉了两处只有 GPL 才有的用法：找屏幕页从 `mpdecimate` 换成 `freezedetect`；给 AutoSlides Extractor 的裁剪视频从 x264 换成 FFmpeg 自己的 MPEG-4 编码器（`-q:v 2`）。
- CI（`.github/actions/ffmpeg`，`test.yml` 和 `release.yml` 共用）：以 `packaging/ffmpeg/build.sh` 去掉注释和空行后的 SHA-256 为键（`packaging/ffmpeg/fetch.sh --hash`）。先从 Actions 缓存恢复；缓存未命中（7 天过期、打新标签或新分支）时，从 GitHub 发布页下载对应哈希的预编译包（`ffmpeg-lgpl-<hash>.tar.gz`）并校验压缩包 SHA-256、三个源码包 SHA-256、许可证文件、LGPL 声明及所需的滤镜、解码器和编码器（用户 2026-11-20 定）；只有 `build.sh` 的版本或编译命令真正改动时才在 MSYS2 里重新编译。cli、gui 任务也用同一份，所以测试跑在安装包带的 FFmpeg 上。
- 冻结时去掉 imageio-ffmpeg，把 `build/ffmpeg/bin` 放进命令行的 `ffmpeg/`；`media.tool` 先找 `PATH`，再找这份，pip 和 uv 安装的再找 imageio-ffmpeg 的。冻结后在 `PATH` 只剩 `System32` 的情况下处理并打包一段生成的视频，缺滤镜就在构建时失败，不留给用户。
- 每次发布附上 FFmpeg、dav1d、SVT-AV1 的源码包和 `FFmpeg-BUILD.txt`（版本、校验和、配置命令）。

## 四、许可和隐私

- 许可证 AGPL-3.0-or-later。`packaging/notices.py` 把 `THIRD-PARTY-NOTICES.txt` 写进命令行文件夹和安装文件夹：FFmpeg、dav1d、SVT-AV1、zlib，Python（它的 `LICENSE.txt` 覆盖 CPython 自带的库），每个冻结进去的 Python 包和它自己的许可文件，PyInstaller 的引导程序（GPL 加引导程序例外），AutoSlides 的配色（Apache 2.0）。Electron、Chromium 和 JavaScript 包自带它们的。pip 和 uv 用户的 FFmpeg 由他们自己从 PyPI 取得，本项目不再分发。
- 隐私说明和使用条款在 `PRIVACY.md`（用户 2026-10-29 定），README 链接它；它还有一段许可证摘要，指向全文。安装程序第一页显示它（`notices.py` 写成带 BOM、CRLF 的 `build/PRIVACY.txt`：NSIS 只有看到 BOM 才按 UTF-8 读），也留在安装文件夹；更新和静默安装跳过这一页。这一页有 electron-builder 的「我同意」按钮：AGPL 不需要同意，但使用条款要。
- 设置 → 关于显示版本和许可证，在对话框里打开 PRIVACY.md，用默认编辑器打开许可证和第三方声明。

## 五、更新

- 打包后的程序启动约 8 秒后检查一次（设置，默认开），也可以点「检查更新」；从不自己下载或安装。有新版本时设置按钮出现小点，对话框显示发布说明；「下载并更新」显示进度，「重启并安装」退出（有任务在跑时先问）、静默安装、重新启动。设置里写明上次检查的时间、来源和结果，重启后保留。
- electron-updater 负责下载、sha512 校验、对照缓存的安装包做差量下载和静默重装。差量下载的改动（`gui/src/update-plan.js`）：每个请求只要一个字节范围（github.com 和 ghfast.top 对一个请求多个范围回 501，electron-updater 会退回整包下载）；相距不到 1 MB 的改动块合成一个范围；四个范围同时下载。
- 来源依次试（`gui/src/updater.js`）：github.com（`releases/latest/download/latest.yml`，再到带版本号的文件夹找旧的 blockmap）；GitHub REST API（只能整包下载）；设置里填的镜像；内置镜像 gh-proxy.com、ghfast.top。元数据请求 15 秒超时，下载 60 秒没进度换下一个；`HTTPS_PROXY`、`HTTP_PROXY` 应用到 electron-updater 的会话上。下载 15 秒后，平均不到约 300 KB/s 且按这个速度还要一分钟以上的来源，换到下一个能差量下载的来源（跳过只能整包的 API）；最后一个来源不因慢被换掉，因慢被换掉的在其他都失败后最后再试一次，所以只是慢不会导致更新不了。
- 签名：安装包没有代码签名，electron-updater 只核对 `latest.yml` 里的 sha512，镜像可能给出别的 `latest.yml`。所以发布流程用 Ed25519 私钥（仓库机密 `UPDATE_SIGNING_KEY`）签 `latest.yml`，程序只接受 `latest.yml.sig` 用 `gui/src/update-signature.js` 里的公钥验证通过的。这让不可信的镜像也能用。私钥丢了，用户就得手动装下一版。
- 测试版：`0.9.2-beta` 这样的版本是标签、发布文件夹和各个包的版本，Python 写成 `0.9.2b0`。发布流程把它的草稿标成预发布；GitHub 的 `releases/latest` 跳过预发布，所以正式版用户收不到测试版，README 留着上一个正式版的链接。设置 → 接收测试版：先经 API 读发布列表，最新的是预发布时，各来源都从那个版本的文件夹读 `latest.yml`。`detectUpdateChannel: false` 让测试版也用 `latest.yml`。
- 更新只下载变化的部分；设置和工作区保留。

## 六、待定

- 代码签名暂缓（用户 2026-10-27 定）：signpath.org/apply 的申请表对用户打不开。SignPath Foundation 免费给符合条件的开源项目签名（发布者显示为 SignPath Foundation）；Azure Artifact Signing 只接受美国和加拿大的个人；EV 证书从 2024 年起不再跳过 SmartScreen 的信誉检查。更新的签名不依赖它。
- 维护者机器上 0.2.0 的前两次静默安装把 PATH 选项存成了 0，没查明（[development.md](../development.md)）。
