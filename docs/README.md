# 文档地图

> 给谁看：要了解、修改这个项目的人和 AI。给用户看的介绍和安装说明在仓库根目录的 [README.md](../README.md)。

## 各篇回答什么

| 文档 | 回答什么 |
|---|---|
| [ARCHITECTURE.md](../ARCHITECTURE.md) | 代码在哪、什么不能破坏、改一处要连带改哪里 |
| [requirements.md](requirements.md) | 目标、范围、场景，以及每条需求（`SRC`、`FRM`、`SUM`、`MGT`、`APP`、`INS`、`PRV`）怎样算做到 |
| [summary-requirements.md](summary-requirements.md) | 总结提示词要让模型做到的每一件事（`PRM-`），各写在提示词的哪里 |
| [design.md](design.md) | 数据怎么流、命令行和桌面程序之间的契约、磁盘上的文件、并发；各子系统设计的索引 |
| [processing-design.md](processing-design.md) | 下载和网站账号、字幕、画面布局和屏幕页、课件、代表画面、补截、压缩 |
| [summary-design.md](summary-design.md) | 总结的规则和模板、主线与单元、版本和谱系、画面集、导入时做什么和查什么 |
| [routes-design.md](routes-design.md) | 几种写总结的方式：Agent、分阶段（agy）、模型 API、网页 AI 和 DeepSeek 网页版 |
| [staged-design.md](staged-design.md) | 分阶段写总结：步骤、状态文件、程序检查、画面、agy 通道、代价 |
| [app-design.md](app-design.md) | 桌面程序：技术、任务队列和并发、自动处理、界面、终端、日志、托盘 |
| [collections-design.md](collections-design.md) | 合集、跟随播放列表、合集总结和学习提纲 |
| [distribution-design.md](distribution-design.md) | 安装包、自带的 FFmpeg、许可和隐私说明、更新签名 |
| [adr/](adr/) | 为什么选了现在的方案：跨模块的取舍，以及试过、否决的做法 |
| [roadmap.md](roadmap.md) | 还没排期的方向和它们的前提 |
| [reference/deepseek-web.md](reference/deepseek-web.md)、[reference/antigravity.md](reference/antigravity.md) | 外部系统的实测事实：DeepSeek 网页版、agy |
| [cli.md](cli.md)、[commands.md](commands.md) | 给用户：命令行怎么用、每个命令和选项 |
| [development.md](development.md) | 测试、构建、发布、已知问题 |
| [conventions.md](conventions.md) | 文档、代码、提交怎么做 |
| [writing.md](writing.md) | 仓库里的文字怎么写，为什么 AI 爱写成过程记录、怎么防 |
| [releases/](releases/) | 每一版的发布说明（公开），只追加 |
| [release-log.md](release-log.md) | 每次发布过了哪些检查，只追加 |
| `user-notes/` | 用户亲手写的原始材料，不进 git |

必须遵守的硬要求在 `.claude/rules/hard-requirements.md`，每次会话自动加载。

## 文档怎么分、怎么更新

| 部分 | 怎么更新 |
|---|---|
| 需求、设计、参考、运行、约定、ADR | 原地改写，只保留当前版本；跨模块的取舍写成 ADR，只影响一篇的决定写在那篇里；推翻时直接改，被推翻的做法和原因写进 ADR 的「备选方案」 |
| 讨论过程、试错经过 | 不进文档，留在 git 历史和对话里；试过的做法只写结论 |
| 发布说明、发布检查记录 | 只追加 |
| 用户的原始材料 | 原样保存，只追加 |
| 归档 | 冻结；只当查漏的材料，内容并入新文档后可以删 |

每篇开头写两行：给谁看、回答什么。回答不了这个问题的内容不属于这一篇。不设交接文档和单独的决策日志。
