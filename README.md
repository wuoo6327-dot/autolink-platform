# AUTOLINK 隔离开发与审查源码

本目录用于 AUTOLINK 第一轮隔离修复。候选代码基于 Python、Caddy、SQLite 和现有前端；生产网站为 [AUTOLINK](https://autolinkglobal.com/)。**目录中的修改与扫描配置不代表已经上线。** 不运行生产 Docker、不修改线上数据、不上传 production `.env`；部署属于独立验收流程。

`auth/` 是账号与业务服务，`site/` 是现有界面和语言资源，Caddyfile / compose.yaml 是候选配置。先阅读 [开发与回滚规范](docs/DEVELOPMENT.md) 与 [源码安全扫描](docs/SECURITY_SCANNING.md)，按备份恢复 → 源码秘密 → Git / 工具 → 安全 → 业务 → SEO 的顺序验收。

安装指定官方工具后，运行当前源码检查：

```sh
python3 scripts/security_scan.py --tool all
```

仅在当前目录已是独立 Git 仓库且完整历史可用时运行：

```sh
python3 scripts/security_scan.py --tool gitleaks --history
```

脚本仅保存脱敏报告，区分通过、发现问题和未完成，不升级依赖、修复代码或部署。工具固定为 Gitleaks 8.30.1、Trivy 0.75.0；私有 GitHub CI 已在修复分支启用，实际运行结果以 Actions 记录为准。Lighthouse 留后续性能 / SEO 阶段。
