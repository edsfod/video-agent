<!--
类别：状态 · 决策层。读者：想知道「为什么不用另一种做法」的人和 AI。
决策被推翻时原地改写本文，被推翻的方案和失败的依据写进「备选方案」。不写状态和日期：仓库里的 ADR 都是当前有效的，时间看 git。
-->

# ADR-0007: 安装包不做代码签名，更新用 Ed25519 签名的 `latest.yml` 验证

## 背景

- 只接受签名有效的更新（`INS-06`）；更新可能来自不可信的镜像（`INS-05`）。
- 安装包没有代码签名时，electron-updater 只核对 `latest.yml` 里的 sha512，而镜像可能给出别的 `latest.yml`。

## 决策

1. 安装包不做代码签名。
2. 发布流程用 Ed25519 私钥（仓库机密 `UPDATE_SIGNING_KEY`）签 `latest.yml`；程序只接受 `latest.yml.sig` 用 `gui/src/update-signature.js` 里的公钥验证通过的 `latest.yml`。

## 备选方案

1. **SignPath Foundation**（免费给符合条件的开源项目签名，发布者显示为 SignPath Foundation）：申请表 signpath.org/apply 打不开。
2. **Azure Artifact Signing**：只接受美国和加拿大的个人。
3. **EV 证书**：从 2024 年起不再跳过 SmartScreen 的信誉检查。

## 影响

- 不可信的镜像也能用作更新源。
- 私钥丢了，旧版程序就验证不了后续版本，用户要手动装下一版；维护者本机另有私钥的备份。
- ARCHITECTURE.md 不变量 `C5`。
