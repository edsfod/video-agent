# 文档地图

> 给谁看：要了解、修改这个项目的人和 AI。给用户看的介绍和安装说明在仓库根目录的 [README.md](../README.md)。
> 现状（2026-11-20）：文档正在按这张表重构，标「待写」的还没写，对应内容暂时在 `archive/2026-11-20/` 里。

## 各篇回答什么

| 文档 | 回答什么 | 状态 |
|---|---|---|
| [requirements.md](requirements.md) | 要解决什么、怎样算做成、范围和约束 | |
| [summary-requirements.md](summary-requirements.md) | 总结提示词要让模型做到的每一件事，各写在提示词的哪里 | 待改：去掉重写前的「旧位置」 |
| [design/architecture.md](design/architecture.md) | 由哪些部分组成、数据怎么流、磁盘上的文件、部分之间的边界 | |
| design/processing.md | 字幕、画面布局和屏幕页、课件、代表画面、补截、压缩 | 待写 |
| design/summary.md | 总结的规则和模板、主线与单元、版本、画面集、检查和多轮复查 | 待写 |
| design/routes.md | 几种写总结的方式：Agent、Antigravity、模型 API、网页 AI 和 DeepSeek 网页版 | 待写 |
| design/app.md | 桌面程序：界面、任务队列和并发、更新、网站账号 | 待写 |
| design/collections.md | 合集、跟随播放列表、合集总结和学习提纲 | 待写 |
| design/distribution.md | 安装包、自带的 FFmpeg、许可和隐私说明、更新签名 | 待写 |
| design/article-summary.md | 总结文章（计划中） | 待写 |
| reference/ | 外部系统的实测事实：DeepSeek 网页版、Antigravity、必剪、yt-dlp 等 | 待写 |
| [cli.md](cli.md)、[commands.md](commands.md) | 给用户：命令行怎么用、每个命令和选项 | 待译成中文 |
| [development.md](development.md) | 测试、构建、发布、已知问题 | |
| [conventions.md](conventions.md) | 文档、代码、提交怎么做 | |
| [writing.md](writing.md) | 仓库里的文字怎么写，为什么 AI 爱写成过程记录、怎么防 | |
| [releases/](releases/) | 每一版的发布说明（公开），只追加 | |
| [release-log.md](release-log.md) | 每次发布过了哪些检查，只追加 | |
| `user-notes/` | 用户亲手写的原始材料，不进 git | |
| `archive/2026-11-20/` | 重构前的文档，冻结 | |

必须遵守的硬要求在 `.claude/rules/hard-requirements.md`，每次会话自动加载。

## 文档怎么分、怎么更新

| 部分 | 怎么更新 |
|---|---|
| 需求、设计、参考、运行、约定 | 原地改写，只保留当前版本；决定写在所属的那篇里，带日期；推翻时直接改 |
| 讨论过程、试错经过 | 不进文档，留在 git 历史和对话里；试过的做法只写结论 |
| 发布说明、发布检查记录 | 只追加 |
| 用户的原始材料 | 原样保存，只追加 |
| 归档 | 冻结；只当查漏的材料，内容并入新文档后可以删 |

每篇开头写两行：给谁看、回答什么。回答不了这个问题的内容不属于这一篇。不设交接文档和单独的决策日志。
