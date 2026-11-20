# Antigravity

> 给谁看：要改 Antigravity 路线（`gui/src/antigravity.js`）或 `agy` 预设的人和 AI。回答：Antigravity 桌面版和命令行实际怎么用、接口在哪。
> 证据级别：桌面版的 `agentapi` 和本地服务没有公开文档，都是实测（带日期、版本）；`agy` 的部分来自它的文档和实测。

## 桌面版（实测 2026-11-16，44.9.1）

- 自带 `language_server.exe agentapi`，子命令 `new-conversation [--model] [--title] <prompt>`、`send-message`、`get-conversation-metadata`。`new-conversation` 立刻返回对话 id。
- 它要运行中的服务的地址和 CSRF 令牌（环境变量 `ANTIGRAVITY_LS_ADDRESS`、`ANTIGRAVITY_CSRF_TOKEN`）；服务把它们写在 `~/.gemini/antigravity/daemon/hub_<端口>.json`，取进程还活着的最新一个。
- 同一个服务的 Connect JSON 调用：`GetCascadeTrajectory`（步骤，以及 Agent 做完时变成 IDLE 的运行状态）、`GetCascadeModelConfigData`（模型列表）、`ForceStopCascadeTree`（带 `conversationId`，停止）。
- 在测试视频上：Agent 读了 skill、写了草稿、用 `summarize --import` 保存，约两分半，没有提问；停止几秒内生效。
- `agentapi` 不接受文件夹参数，不能限制 Agent 读哪些文件。
- 有每周额度，用完任务会中断，到恢复日期才能再用。
- 应用自己会装更新并重启（例如 2026-11-20 更新到 2.33.0），运行中的任务随之中断；日志在 `%APPDATA%\Antigravity\logs\main.log`。

## 命令行 `agy`（实测 2026-11-16，1.5.9）

- `winget install Google.AntigravityCLI` 安装；用桌面版的登录，`agy models` 不用另外登录就列出模型。
- `-p` 运行一个提示词后带状态退出；这个模式下任何需要询问的操作都被拒绝（它的无人值守文档），所以要 `--dangerously-skip-permissions`。
- `--model` 指定模型，思考强度含在模型名里。
- skill 文件夹 `~/.gemini/antigravity-cli/skills`（它的文档）；桌面版不读这个文件夹。
