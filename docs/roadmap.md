# 远期方向

> 给谁看：要决定下一步做什么的人和 AI。回答：还没排期的方向、做之前要先满足什么。这里不是承诺；决定要做时写成 [requirements.md](requirements.md) 里的需求。

## 分阶段接 claude、codex 命令行

- 这两个命令行都有自定义 agent、限制工具、接续对话的开关，满足 [ADR-0010](adr/0010-staged-through-agy.md) 对通道的要求。接之前先在 10 分钟片段上量外壳和质量。
- 接上以后，Agent 应用经 skill 进来时调用 `summarize --staged`，可以用那个应用自己的模型（`SUM-02`）。

## 翻页规则的样本视频

一组标好翻页时间的样本视频，用来衡量翻页规则。前提：要用户的视频。

## 代码签名

安装包暂不做代码签名（[ADR-0007](adr/0007-signed-update-feed.md)）。前提：能申请到一种签名途径，例如 SignPath Foundation 的申请表能打开。
