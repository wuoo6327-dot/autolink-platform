# 第二轮实际容器镜像检查（源码扫描之外）

2026-10-10，本机 Docker Linux arm64，Trivy 0.75.0。仅检测包版本，未做漏洞利用或攻击生产。Python 两个候选的镜像均为 Debian 13.7：172 条匹配（HIGH44、MEDIUM63、LOW62、UNKNOWN3），HIGH 涉及 8 个 CVE。Caddy 缓存 v2.11.6 和重新拉取官方当前 v2.11.7 都有 20 条匹配（HIGH4、MEDIUM8、LOW1、UNKNOWN7），HIGH 涉及 3 个 CVE。

“条”是包-CVE 匹配，同一个 CVE 可在多个包重复出现。不是 44 个独立可远程利用的缺陷，也不是已经攻破 AUTOLINK。不能因为源码扫描没有问题就忽略这些项。

实际运行账号 UID10001，未挂 Docker socket；镜像没有 systemd-homed、systemd-homework 或 homectl。systemd 官方公告描述的本地 homed 条件在此镜像未发现，因此 CVE-2026-16742 当前触发面较低；其他 HIGH 仍需独立确认。没有添加扫描忽略规则。

| 镜像 | CVE | 命中的包 | 修复版本 | 状态 |
|---|---|---|---|---|
| full | CVE-2026-76642 | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | 本扫描未列出 | 待判定实际触发条件/选定修复镜像 |
| full | CVE-2026-78408 | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | 本扫描未列出 | 待判定实际触发条件/选定修复镜像 |
| full | CVE-2026-78409 | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | 本扫描未列出 | 待判定实际触发条件/选定修复镜像 |
| full | CVE-2026-78410 | bsdutils, libblkid1, liblastlog2-2, libmount1, libsmartcols1, libuuid1, login, mount, util-linux | 本扫描未列出 | 待判定实际触发条件/选定修复镜像 |
| full | CVE-2026-54369 | libacl1 | 本扫描未列出 | 待判定实际触发条件/选定修复镜像 |
| full | CVE-2025-69720 | libncursesw6, libtinfo6, ncurses-base, ncurses-bin | 本扫描未列出 | 待判定实际触发条件/选定修复镜像 |
| full | CVE-2026-16742 | libsystemd0, libudev1 | 本扫描未列出 | 待判定实际触发条件/选定修复镜像 |
| full | CVE-2026-9538 | perl-base | 本扫描未列出 | 待判定实际触发条件/选定修复镜像 |
| caddy-latest | CVE-2026-78669 | golang.org/x/net, stdlib | 0.60.0 | 待判定实际触发条件/选定修复镜像 |
| caddy-latest | CVE-2026-78667 | stdlib | 1.26.9, 1.27.2 | 待判定实际触发条件/选定修复镜像 |
| caddy-latest | CVE-2026-97031 | stdlib | 1.26.9, 1.27.2 | 待判定实际触发条件/选定修复镜像 |

## 处理方向

- Caddy 的 Go 标准库和 x/net 已有补丁：在官方 Caddy 同版本源码中用已修复 Go 工具链与 x/net 构建，或使用包含修复依赖的官方镜像；必须重新检查 Caddy 路由、Cookie、TLS、证书持久化以及生产服务器架构。
- Python 基础镜像：逐条检查 Debian 官方记录、包是否安装对应可执行组件、是否具备攻击前提；选择更新后的受支持基础镜像，或经评审记录“不受影响/防护措施”，不能自动 blanket 忽略全部 HIGH。
- 本轮范围是候选验收。实际镜像安全发布门槛尚未全部通过，main 和生产保持不变。生产机是否使用同一基础镜像、是否同架构需在正式预发布验证。

官方依据：[Caddy 2.11.7](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)、[HTTP/2 SETTINGS](https://pkg.go.dev/vuln/GO-2026-6611)、[HTTP Range](https://pkg.go.dev/vuln/GO-2026-6609)、[TLS ECH](https://pkg.go.dev/vuln/GO-2026-6607)、[systemd-homed](https://github.com/systemd/systemd/security/advisories/GHSA-jm29-p7hh-vjhv)、[Debian systemd 记录](https://security-tracker.debian.org/tracker/CVE-2026-16742)。
