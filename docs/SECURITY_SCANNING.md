# AUTOLINK 源码安全扫描

本流程只读本地源码及本地 Git 历史，不登录生产、不连接业务数据库、不调用网站接口、不运行生产 Docker、不修改依赖。首次 Trivy 运行要下载漏洞数据库和 Dockerfile 检查规则；它不是完全离线检查，不代表扫描了运行中的服务器。

## 运行

官方工具固定为 Gitleaks **8.30.1** 和 Trivy **0.75.0**。版本、官方 Linux 下载地址和 SHA256 在 `security/tool-versions.json`；工具升级单独评审。CI 不使用远程 `curl | sh`。

```sh
python3 scripts/security_scan.py --tool all
python3 scripts/security_scan.py --tool gitleaks --history
```

第二条仅在当前目录是独立 Git 仓库且完整历史可用时运行，否则会明确拒绝，避免扫描外层无关项目。没有自动忽略基线，不允许通过禁用规则或白名单整个测试目录来通过检查。

## 报告和验收

仅保存 `security-reports/*-sanitized.json`，权限 600。保留规则、文件、行、commit 或依赖版本；不保存凭证、源码片段、匹配原文、作者邮箱或原始 stderr。Gitleaks 同时采用 100% redact，私有临时报告用完删除。

| 状态 / 退出码 | 含义 |
|---|---|
| passed / 0 | 所选扫描真正完成且没有阻断项，不代表网站没有漏洞 |
| blocked / 1 | 任意 secret，或 HIGH / CRITICAL 漏洞与配置风险 |
| incomplete / 2 | 缺工具、版本不匹配、超时、结果无效、数据库下载失败或未覆盖 requirements |

中低风险仍保留在报告里。疑似误报先确认规则和文件，仅为明确非秘密值添加有理由的精确例外。真实秘密进入 Git 后须撤销 / 轮换，删除当前文件无法清除历史泄露。

当前依赖扫描覆盖能识别的 Python requirements，配置扫描覆盖 Dockerfile。**不声称完整审核 Caddy / Compose 语义，不扫描基础镜像内 OS 包，不保证识别无 manifest 的编译前端依赖。** 这些项目另需人工、镜像或软件清单检查。扫描结果不能冒充接口越权、SQL 注入、XSS、CSRF 或线上测试。

## 私有 CI

workflow 只在私有仓库运行，权限只有 `contents: read`，不用生产 SSH、production `.env`、OIDC、写权限或 `pull_request_target`。官方 actions 固定完整 SHA，checkout 不保留凭证，脱敏 artifact 保存 5 天。未上传 / 启用前只有配置文件，**没有真实 GitHub CI 运行结果**。

管理员启用受保护分支，把 `source-security` 设为必需检查并确认评审规则。最终 gate 要求当前源码和历史检查都 completed 且没有阻断项，未运行不算通过。没有自动升级依赖或部署步骤。报告、缓存、数据库、用户文件和备份不进入 Git，`.gitignore` 由安全 Git 基线统一设置。Lighthouse 留后续性能 / SEO 阶段。

官方依据：[Gitleaks](https://github.com/gitleaks/gitleaks)、[Trivy 配置](https://trivy.dev/docs/latest/references/configuration/config-file/)、[Trivy 文件扫描](https://trivy.dev/docs/latest/guide/target/filesystem/)、[GitHub Actions 安全](https://docs.github.com/en/actions/reference/security/secure-use)。
