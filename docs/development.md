# 测试、构建和发布

> 给谁看：要改代码、跑测试或发布的人和 AI。回答：测试有哪些、在哪里跑、怎么构建安装包、怎么发布、已知问题。

## 测试

- 命令行：`tests/`，pytest 加 mypy。用真实的 FFmpeg 处理生成的短片；必剪对着本机的假服务器；有一项测试保证 `pyproject.toml`、插件清单、`gui/package.json`、skill 和 README 里的版本号一致。
- 桌面程序：`gui/test/`，`node --test`。队列规则、更新器的单元测试，和用 Playwright 驱动真实窗口的端到端测试（`gui/test/e2e.test.js`）。先跑 `npm run typecheck`：TypeScript 借 JSDoc 检查 JavaScript，不编译。
  - 设了 `VA_E2E_BACKGROUND`（测试会设）时，窗口开在屏幕外、没有任务栏按钮、不抢焦点，用户可以照常工作。
  - 每个测试结束都关掉打开的对话框、恢复替换掉的文件对话框，一个失败不连累后面的。
  - 端到端测试平时从源码跑；对着解包后的安装包只重跑打包会影响到的那部分和更新测试，其余用 `devTest` 声明。
  - `gui/test/agents.test.js` 只在设了 `VA_E2E_AGENTS` 时调用真的 Agent。
- 测试等状态，不等时间。
- 界面改动除跑测试外，也在本地打开开发窗口实查（用户 2026-10-28 定）。

## 在哪里跑

- 本机：`pre-push` 钩子（`scripts/githooks/pre-push`）按这次推送改了什么挑检查（规则和 GitHub 一样，见 `.github/scripts/changed-jobs.sh`）：只改文档什么都不跑；改了命令行跑 ruff、mypy、pytest 和入口；改了窗口代码跑 GUI 的类型检查和单元测试；改了打包相关的文件，再打包一次命令行工具并跑它的冒烟测试。开窗口的端到端测试不在本机跑（用户 2026-10-30 定：太慢，GitHub 上也会跑），`update` 也是开窗口的；会安装程序、改真实 PATH 或已安装程序的测试（`update-install`、`installer-path`）只在 GitHub 上跑，用临时目录、临时注册表项隔离的（如 `user-path`）可以在本机跑（用户 2026-11-21 定）。推送的提交都已在远端时跳过。
- GitHub（`.github/workflows/test.yml`，只在 Windows 上）：按改动挑任务。cli 任务跑命令行的检查；gui 任务跑端到端测试（约 2.5 分钟）；installer 任务（构建、PATH 选项、静默安装、更新安装，约 5 分钟）只在依赖、打包、安装器、图标、更新器改了时跑。只改版本号的提交（`.github/scripts/version_only.py`）只跑版本号检查。同一分支上被新推送取代的运行会取消；每个任务都有时限。
- git 钩子：`sh scripts/githooks/install.sh` 把 `scripts/githooks/` 下的 pre-commit（写法检查）、commit-msg（AI 署名、写法检查）和 pre-push 装进 `.git/hooks/`，见 [writing.md](writing.md)。
- 本机跑端到端测试：在 `gui/` 下 `node --test --test-concurrency=1 test/e2e.test.js`，用临时的 APPDATA 和 `--user-data`。

## 构建

- 命令行：`packaging/build_cli.py` 用 PyInstaller 冻结，带上 yt-dlp 和 `packaging/ffmpeg/build.sh` 编译的 LGPL FFmpeg（源码随每次发布附上）。
- 安装包：electron-builder 打成未签名的 NSIS 安装包，安装时先显示 `PRIVACY.md`，并把命令行工具加进用户的 `PATH`。
- LGPL FFmpeg 的预编译包（[design/distribution.md](design/distribution.md) 第三节）：`build.sh` 的版本或编译命令改了以后，CI 每个用到它的任务都要重新编译，本机 pre-push 也跳过打包冒烟测试，直到换上新的预编译包：
  1. 等 installer 任务编完，删掉本机的 `build/ffmpeg`，`gh run download <运行号> -n ffmpeg-lgpl -D build/ffmpeg`，再跑 `bash packaging/ffmpeg/fetch.sh --verify`，要通过。
  2. `tar -czf ffmpeg-lgpl-<哈希>.tar.gz -C build/ffmpeg .`，哈希是 `bash packaging/ffmpeg/fetch.sh --hash` 的输出；`gh release upload v0.9.0 ffmpeg-lgpl-<哈希>.tar.gz`。
  3. 把 `packaging/ffmpeg/fetch.sh` 里的 `PREBUILT_BUILD_HASH` 改成这个哈希，`PREBUILT_ARCHIVE_SHA256` 改成压缩包的 SHA-256，提交。
- `build.sh` 的注释只写整行：`fetch.sh --hash` 只略过整行注释，行尾注释改了也算改动。
- 本机编：在仓库根目录用 MSYS2 的 UCRT64 终端跑 `bash packaging/ffmpeg/build.sh`，要装的包和 `.github/actions/ffmpeg/action.yml` 里的一样（装了 ccache，再编时只重编改到的部分）。编好的 dav1d、SVT-AV1 留在 `build/ffmpeg-deps`，解开的 FFmpeg 源码留在 `build/ffmpeg-work`，下次直接用；要全部重来就删掉这两个文件夹。从 Git Bash 里要经 MSYS2 安装目录下的 `msys2_shell.cmd -ucrt64 -defterm -no-start -here -c 'bash packaging/ffmpeg/build.sh'` 启动：直接运行 MSYS2 的 `bash.exe`，环境变量只传过去 `PATH`、`HOME` 等几个，ccache 因为没有 `USERPROFILE` 会退出。
- 本机手动跑过 `build.sh` 后，再跑 `bash packaging/ffmpeg/fetch.sh --mark`：它校验 `build/ffmpeg` 并写下 `BUILD-HASH`，`fetch.sh` 和 pre-push 才会用这份。

## 发布

1. 用户说发布后：`uv run scripts/bump_version.py <版本>`，手写 `docs/releases/v<版本>.md`，打标签推送。
2. 标签触发 `.github/workflows/release.yml`：构建、测试打包后的程序、用 Ed25519 签名 `latest.yml`、建草稿并附上 FFmpeg 源码。发布流程在标签上独立构建、不复用分支 CI 的安装包产物，既能和 CI 并行、也保留标签自己的构建记录。
3. 检查，全过就发布草稿，不等审阅：
   - 签名的 `latest.yml` 校验通过，里面的大小和安装包一致（`gui/src/update-signature.js` 的 `verify`）；
   - FFmpeg、dav1d、SVT-AV1 源码包的摘要和 `packaging/ffmpeg/build.sh` 里固定的值一致；
   - 打包后的测试通过；
   - 这次提交在 GitHub 上的测试通过。
4. 发布后查三个更新源（github.com、gh-proxy.com、ghfast.top）都给出新版本，把结果记进 `docs/release-log.md`。

## 截图

README 的截图在 `docs/images/`，由 `gui/` 下的 `npm run screenshots -- <工作区> <视频>`（`gui/scripts/screenshots.js`）生成，每张左右拼合浅色和深色主题。当前素材是南京大学《生成式软件工程》第 1 讲「欢迎来到未来」（蒋炎岩，B 站公开课）和它的导入总结，复制在不含本机个人路径的中性文件夹里生成，README 末尾附讲者署名和 AI 输出免责说明。

## 已知问题

- 本机的端到端测试时好时坏：一次窗口在「添加本地视频」时关掉（node-pty 报 `AttachConsole failed`），一次 DeepSeek 网页任务慢到超时；原因没查。
- 维护者机器上 0.2.0 的前两次静默安装把 PATH 选项存成了 0（不加入），之后同一安装包和 CI 都存成 1；没查明。
