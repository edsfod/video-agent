# Antigravity

> 给谁看：要改分阶段写总结的 agy 通道（`staged_agy.py`）或 `agy` 预设的人和 AI。回答：Antigravity 命令行实际怎么用。
> 证据级别：来自它的文档和实测（带日期、版本）。

## 命令行 `agy`（实测 2026-11-16，1.5.9）

- `winget install Google.AntigravityCLI` 安装；用桌面版的登录，`agy models` 不用另外登录就列出模型。
- `-p` 运行一个提示词后带状态退出；这个模式下任何需要询问的操作都被拒绝（它的无人值守文档），所以要 `--dangerously-skip-permissions`。
- `--model` 指定模型，思考强度含在模型名里。
- skill 文件夹 `~/.gemini/antigravity-cli/skills`（它的文档）；桌面版不读这个文件夹。

## 分阶段用到的（实测 2026-11-23 至 2026-11-25，1.5.14）

- `--input-format stream-json` 从标准输入收 `{"event":"user","message":{"content":…}}`，提示长度不受命令行限制；`--output-format stream-json` 逐行出事件：`step_update`（`agent_response` 带这次调用的 `usage`：`input_tokens`、`cache_read_tokens`、`output_tokens`、`thinking_tokens`；`tool` 带 `tool_name`）和最后的 `result`（`status`、`response`、`conversation_id`、`denied_actions`）。
- `--conversation <id>` 接着原对话，每次一个新进程；这时 `result.usage` 是整个对话的累计，不是这一轮的。
- 一次调用可能以 ERROR 结束，agy 自己再调一次；ERROR 的那次也读了、想了，用量照算。错误事件里不写原因（2026-11-23 那几次是网络中断）。
- `--agent <名字>` 用工作区 `.agents/agents/<名字>.md` 里的自定义 agent（`tools:` 列出能用的工具）；但模型发出的未声明工具 agy 照样执行（实测有 `run_command`）。工作区 `.agents/hooks.json` 的 PreToolUse 钩子能拒绝它们，拒绝时给的理由会交给模型，模型接着作答。
- 无头模式读工作区外的文件要权限，没法申请，读取被拒，整轮回答为空。
- `--effort low` 配 `gemini-3.8-flash-high` 时用量全是 0；思考档位用模型名换（`-low`、`-medium`、`-high`）。
- 后端偶尔回「empty conversation id」；同时启动十几个进程时，偶尔有进程在读入标准输入前就退出（写管道报 `OSError: [Errno 22]`）。两种都重试就好。
