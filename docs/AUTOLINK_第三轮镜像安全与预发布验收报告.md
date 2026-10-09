# AUTOLINK 第三轮镜像安全与预发布验收报告

日期：2026-10-10（泰国时间）。依据本轮最新 PR #2 源码、生产实际镜像备份和阿里云原生 AMD64 验收，不沿用历史扫描数字。

## 1. 明确结论

**PR #2 的镜像安全与原生架构预发布技术门槛已通过，可以进入正式部署方案审批。现在没有部署生产，也没有合并 main。**

安全候选的 Python 镜像没有扫描发现项；Caddy 没有 HIGH/CRITICAL，保留 1 条 UNKNOWN，详见第 5 节。不能把它写成“所有漏洞都已修复”。实际生产仍运行旧镜像：Python 有 45 条 HIGH，Caddy 有 4 条 HIGH。候选修复只有经单独批准上线后，才能消除线上对应风险。

建议分两步：先审核本次更新后的 PR #2 和发布/回滚方案；批准后在维护窗口发布安全范围，并立即完成外网验收。**不建议将 PR #1、#2、#3 一起合并上线。** 本轮通过也不能代表完整商家入驻、法律协议、SEO、会员收费和真实业务闭环已正式验收。

上线前仍须确认：新鲜备份与恢复、Caddy 旧证书卷拥有者迁移、现有生产环境变量及指定验收账号。真实 Google 登录、真实邮件、公共 ACME 管理/续期和 HTTP/3 实际连通性留到批准后的受控验收；本轮没有冒充通过。

## 2. 实际环境与隔离边界

| 项目 | 本轮核实结果 |
|---|---|
| 阿里云生产主机 | Ubuntu 24.04.2 LTS；x86_64 / linux/amd64；内核 6.8.0-63-generic |
| Docker | Engine 29.1.3，API 1.52，containerd 2.2.1，runc 1.3.4，Compose 2.40.3+ds1 |
| 资源 | 2 CPU，约 3.4 GiB 内存；扫描、测试逐项运行并限制 CPU/内存 |
| 正式服务 | autolink-demo-auth-1、autolink-demo-web-1；本轮前后 ID、镜像、启动时间相同 |
| 隔离预发布目录 | `/home/admin/autolink-round3-stage-native-20261010`，外层权限 0700 |
| 隔离项目 | `autolink-qa-round3-native`；独立网络及 3 个独立数据卷 |
| 暴露端口 | 仅宿主 127.0.0.1 的 19080 / 19443；没有新增外网监听 |
| 数据和邮件 | HTTP 使用保留域名合成账号、合成私有 JPEG 和独立 SQLite；auth 内部网络，邮件提供商/API Key 为空；单元测试无网络 |
| 测试后状态 | 本机模拟和阿里云原生 QA 服务已停止；数据卷、证据、备份保留；未清理生产卷或镜像 |

候选镜像是在本机构建的 **linux/amd64** 交付物，其中 Caddy 使用官方 builder 原生构建后交叉编译 AMD64。相同 archive 按 SHA256 校验后导入阿里云；原生运行检查了 architecture、manifest digest、UID、TLS、代理、后端与实际 HTTP。**本机 ARM64 和模拟执行只作前期排错，最终通过结论来自阿里云 x86_64。**

真实数据库仅用于：从只读连接做一致备份，再在断网容器中初始化副本检查兼容性。没有启动真实资料的 Web 服务或邮件线程，没有把真实数据放入 HTTP 测试、GitHub 或本地报告附件。

## 3. 镜像扫描结果

工具：官方 Trivy 0.75.0，扫描实际 Docker archive 的 OS 和应用库，保留所有严重等级。没有使用 ignore-unfixed、VEX、漏洞白名单或忽略文件隐藏结果；镜像扫描明确使用空忽略文件。扫描容器不挂载 Docker socket、真实数据库或私有上传文件。

| 实际扫描对象 | CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN |
|---|---:|---:|---:|---:|---:|
| 生产 auth 实际镜像 | 0 | 45 | 64 | 62 | 3 |
| 生产 Caddy 实际镜像 | 0 | 4 | 8 | 1 | 7 |
| 最终候选 auth AMD64 | 0 | 0 | 0 | 0 | 0 |
| 最终候选 Caddy AMD64 | 0 | 0 | 0 | 0 | 1 |

45 是“软件包 × 漏洞”的发现条数，对应 9 个不同 HIGH CVE；Caddy 的 4 条对应 3 个不同 HIGH CVE。不是 49 个独立可利用攻击入口。第二轮参考基础镜像的 44 条 HIGH 不代替本轮实际生产扫描。

### 3.1 生产 Python HIGH 逐项确认

生产 Python：3.12.15，Debian 13；不是 Python 解释器版本号本身导致所有 HIGH。下表是基础镜像里的系统软件包。

util-linux 的四项由 Debian 源包映射到 9 个二进制包重复报告：bsdutils、libblkid1、liblastlog2-2、libmount1、libsmartcols1、libuuid1、login、mount、util-linux。基础版本 2.41.5-0+deb13u1（bsdutils/login 有 Debian epoch 或兼容版本前缀，详见原始 JSON）。

| 漏洞及位置 | 触发条件 | 上游修复版本 / 发行版情况 | AUTOLINK 实际使用及处置 |
|---|---|---|---|
| [CVE-2026-76642](https://github.com/util-linux/util-linux/security/advisories/GHSA-m25x-3hj9-m26f)：util-linux 2.41.5，失败的 mount helper 后仍执行特权处理 | SUID mount、允许的 fstab 挂载、X-owner/group/mode 等选项与 helper 失败组合 | util-linux 2.41.6 / 2.42.3；本轮 Debian 稳定包扫描无 fixedVersion | 代码未发现调用 mount；生产容器非 privileged、无额外 SYS_ADMIN。最终 Alpine 不包含这组 Debian mount/helper；不据此宣称旧镜像无风险 |
| [CVE-2026-78408](https://github.com/util-linux/util-linux/security/advisories/GHSA-55fx-f4gg-cfhj)：util-linux nsenter FD 泄漏 | 特权操作者通过 nsenter --join-cgroup 加入攻击者控制的目标进程 | util-linux 2.42.4；旧稳定包无修复条目 | 应用无 nsenter 调用；候选不安装 nsenter。候选保留 libuuid 2.42.3-r1 的 UUID 库，不能把库版本存在等同 nsenter 可执行路径存在 |
| [CVE-2026-78409](https://github.com/util-linux/util-linux/security/advisories/GHSA-8f2p-47x3-43mv)：X-mount.subdir 路径逃逸 | 内核 ≥6.15、受限 SUID/fstab 挂载及符号链接等条件 | util-linux 2.41.6 / 2.42.3；旧稳定包无修复条目 | 当前主机内核 6.8，不满足该内核条件；应用不调用相关挂载。候选不保留受影响 Debian mount |
| [CVE-2026-78410](https://github.com/util-linux/util-linux/security/advisories/GHSA-rh77-686x-2f2m)：受限 bind 源路径检查竞争 | 本地攻击者能控制路径祖先目录，同时执行受限挂载与 root chown/chmod | util-linux 2.41.6 / 2.42.3；旧稳定包无修复条目 | 没有发现业务调用该路径；候选非 root、cap_drop ALL，受影响 Debian工具不进入运行镜像 |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369)：libacl1 2.3.2-2+b1 | 特权 ACL 路径操作遇到攻击者控制的符号链接竞争 | libacl 2.4.0；旧 Debian 稳定包无 fixedVersion | 业务未发现 ACL 路径操作；最终 Alpine 没有 libacl1 |
| [CVE-2025-69720](https://invisible-island.net/ncurses/NEWS.html#index-t20251213)：libncursesw6、libtinfo6、ncurses-base/bin 6.5+20250216-2 | infocmp 分析恶意终端描述输入，栈溢出 | ncurses 6.5-20251213 已修复；旧稳定包无 fixedVersion | 无 infocmp 业务调用；候选终端库升级到 6.6_p20260516-r0，不把正常终端库粗暴删除 |
| [CVE-2026-103111](https://github.com/PCRE2Project/pcre2/security/advisories/GHSA-r9hj-j2rw-4q3m)：libpcre2-8-0 10.46-1~deb13u2 | 恶意正则与特定 PCRE2 JIT 调用组合，越界写 | 上游 10.49；Debian 稳定修复包 10.46-1~deb13u3 | Python re 使用 CPython 正则引擎；没有发现 PCRE2 JIT 业务调用；候选不安装 libpcre2 |
| [CVE-2026-16742](https://github.com/systemd/systemd/security/advisories/GHSA-jm29-p7hh-vjhv)：libsystemd0、libudev1 257.13-1~deb13u1 | 本地 systemd-homed 管理用户及特权组修改路径 | systemd 261.2 / 258.10；旧稳定包无 fixedVersion | 旧容器发现库不代表正在运行 homed 守护进程；候选没有 systemd/udev 这两库 |
| [CVE-2026-9538](https://lists.security.metacpan.org/cve-announce/msg/40396448/)：perl-base 5.40.1-6+deb13u1 | Archive::Tar 处理攻击者声明的巨大 tar 条目导致内存耗尽 | Archive::Tar 3.10；Debian 的修复 Perl 进入 5.42.3-1，旧稳定包无 fixedVersion | 应用不调用 Perl tar 解析；候选不带 Perl |

以上“未发现调用”来自当前源码和运行配置检查，是可达性判断，不是破坏性利用验证。候选仍有 BusyBox 的正常工具，不能写成“容器完全没有 mount 命令”。没有在生产制造挂载竞争、恶意正则或崩溃测试。

### 3.2 Python 的修复办法

采用官方稳定 `python:3.12.15-alpine3.24` 的固定 AMD64 digest，保留 Python 3.12.15；实际运行 Alpine 3.24.2、SQLite 3.53.4、OpenSSL 3.5.9、zlib 1.3.2-r1。musl 与 SQLite 变化通过后端测试、HTTP 和真实 DB 副本兼容检查，不能只依据扫描数字判断可用。

12 个运行库锁定：requests 2.34.2、urllib3 2.8.0、Pillow 12.3.0、cryptography 50.0.2、google-auth 2.50.0、certifi 2026.7.22、cffi 2.1.1、charset-normalizer 3.5.2、idna 3.20、pyasn1 0.6.4、pyasn1-modules 0.4.2、pycparser 3.11。二进制 wheel 安装、pip check 后，将 pip 安装器与其私有 vendor 移出最终运行镜像；采用从官方运行文件系统复制到 scratch 的最终阶段，避免旧 vendor 留在底层镜像层。没有移除应用正在使用的 requests/urllib3。

构建中曾发现并处置 pip vendor 的 HIGH，不隐去失败的中间扫描：

| 构建期发现 | 触发条件与修复版本 | 最终处理 |
|---|---|---|
| [GHSA-6v7p-g79w-8964](https://github.com/msgpack/msgpack-python/security/advisories/GHSA-6v7p-g79w-8964)：msgpack 1.1.2 | 恶意输入引发异常后重用 Unpacker；修复 1.2.1 | 安装器私有 vendor，不是业务依赖；最终层不包含它 |
| [CVE-2025-47273](https://github.com/pypa/setuptools/security/advisories/GHSA-5rjg-fvgr-3xxf)：setuptools 70.3.0 | 从不可信索引下载，路径遍历；修复 78.1.1 | 不在运行时下载/安装包；最终移除安装器 vendor |
| [CVE-2026-97687](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77)：vendor urllib3 2.7.0 | HTTPS proxy 使用自定义 TLS 设置时未正确执行；修复 2.8.0 | 业务 urllib3 锁定 2.8.0；旧 vendor 从最终镜像层移除 |
| [CVE-2026-97689](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw)：vendor urllib3 2.7.0 | 恶意 chunk-size 行导致无界缓冲；修复 2.8.0 | 同上 |

中间镜像另有 setuptools Unicode sdist（CVE-2026-59890，修复 83.0.0）、urllib3 Deflate 循环（CVE-2026-97688，修复 2.8.0）MEDIUM。zlib 的中间基础包风险升级到 1.3.2-r1。最终完整 archive 原生扫描为 0，不靠降低扫描覆盖来通过。

### 3.3 Caddy HIGH 逐项确认

实际生产 Caddy 2.11.6 使用 Go 1.26.8；本轮也先验证了官方稳定 Caddy 2.11.7。**官方 2.11.7 镜像仍有 4 条 HIGH，单纯改标签不能解决。** 所以选用官方 builder 和官方稳定 Caddy v2.11.7 源码重建，采用正式 Go 1.26.9 和 x/net 0.60.0 修复，不采用随机第三方镜像或旧实验二进制。[官方版本来源](https://github.com/caddyserver/caddy/releases/tag/v2.11.7)。

| 漏洞 | 触发条件 / 实际使用 | 上游修复及候选结果 |
|---|---|---|
| [CVE-2026-78669 / GO-2026-6611](https://pkg.go.dev/vuln/GO-2026-6611) | HTTP/2 流、重复 SETTINGS 窗口变化等造成 CPU 拒绝服务；本站对外启用 HTTP/2，相关 | Go 1.26.9 / 1.27.2；x/net 0.60.0。候选 Go 1.26.9、x/net replace 0.60.0，两个包的重复 HIGH 均消除 |
| [CVE-2026-78667 / GO-2026-6609](https://pkg.go.dev/vuln/GO-2026-6609) | ServeContent/ServeFile 多 Range 请求 CPU 消耗；本站有公开静态文件服务，相关 | Go 1.26.9 / 1.27.2；候选已升级 |
| [CVE-2026-97031 / GO-2026-6607](https://pkg.go.dev/vuln/GO-2026-6607) | TLS 的恶意 ECH 扩展处理路径可能造成内存拒绝服务；本站用 TLS，未配置明确 ECH，不进行破坏性触发验证 | Go 1.26.9 / 1.27.2；候选已升级，不能仅凭未显式开 ECH 忽略告警 |

候选运行在官方 Alpine 3.23.6 底座，zlib 1.3.2-r1。实际二进制构建信息确认 Caddy v2.11.7、Go 1.26.9、GOARCH amd64，x/net 的替换目标为 0.60.0；不是仅修改版本说明。非 root UID 10001、移除遗留 file capability，配合 cap_drop ALL、只读根文件系统和 no-new-privileges。

## 4. 最终镜像版本与固定 digest

以下是已经构建、导入阿里云、扫描和测试的交付物。Docker 29 的 manifest digest 与 config digest 不同，不混用。**未发布公共镜像注册表，也没有镜像签名；这些本地固定引用要先加载经过校验的 archive 才可使用。**

| 组件 | 版本 | linux/amd64 manifest digest | config digest |
|---|---|---|---|
| auth / Python | Python 3.12.15、Alpine 3.24.2、12 项依赖锁定 | `sha256:328ad2e7f193a924d8ddc9943c2bde450e26e1b1af7318b26b1e4cb8984d4b80` | `sha256:25736f3ba1098c31cd84e58b73170ae737f83e298c7cad0f66a89ae64012c114` |
| web / Caddy | Caddy 2.11.7 自行修复构建、Go 1.26.9、x/net 0.60.0 | `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb` | `sha256:335a69d3f130d4b91a1729b94e69371e302e3831fb6296054d45b79dd9c1bc6d` |

Compose 使用 `autolink-round3-auth@sha256:…` 与 `autolink-round3-caddy@sha256:…`。archive SHA256：

- auth-image.tar：`f7e329d3be8bb854b846081c73f2a34d3fc97fcb9c7f30c2d99a2b819e61cb9e`
- caddy-image.tar：`ddf2c2f6544eea709258695c53da57bc42b27850a52e2af5a27c61875e59927e`

基础来源固定：

- Python 官方 AMD64 manifest：`sha256:2055081c860db8c842b663415b795b026e7e5cc63b59c5193fcc9997713ea5b8`（3.12.15-alpine3.24）。[官方 Dockerfile](https://github.com/docker-library/python/blob/master/3.12/alpine3.24/Dockerfile)。
- Caddy 官方 builder 多架构 index：`sha256:aa705b1e8e4bce41a7a30de934c1e00f6821667c1d1206424465065c92cb7674`（2.11.7-builder-alpine，构建平台采用本机原生）。
- Caddy 官方 runtime AMD64 manifest：`sha256:173b26306d711395accaeba8b67afcaad2a085ccb1e6bf26010bfe8c095a5229`（2.11.7-alpine）。

候选是明确内容的发布候选，**重新构建产生新 digest 必须重新扫描/验收**，不能沿用这次报告。依赖版本已锁定，镜像内容以 archive 和 digest 为准；包仓库变化和构建元数据可能让重复构建产生不同摘要。

旧生产回滚镜像也已保存：auth `sha256:1c6688cb335a4b6ca375e097e9edf4e0a0a3ece224726f836454477abbb5ec3c`；Caddy `sha256:881bbc60f9986d5ab8e7cfd6cf7e4ef3c9c0439fef2429d035d065577882f028`。回滚可恢复服务，但也会重新带回旧镜像漏洞，必须作为应急处理。

## 5. 保留风险及无法关闭的原因

### 5.1 Caddy 的 1 条 UNKNOWN：GO-2026-5932

扫描包 `golang.org/x/crypto v0.57.0`；风险描述针对已停止维护的 OpenPGP 子包，上游没有修复版本。因此**不能写成已修复，也没有用白名单移除它**。[Go 官方记录](https://pkg.go.dev/vuln/GO-2026-5932)。

补充核实：保留 govulncheck 模块级完整结果；针对实际最终二进制的 ELF/.gopclntab 函数列表检查，62,593 个函数中没有 OpenPGP 函数。被分析二进制和最终镜像中的二进制 SHA256 都是 `9125887a0f88f164ebff4b71e6c7b20502d91d1819d9797cea6e1b6d90a7ec17`。

**判断：当前实际二进制未发现受影响的 OpenPGP 路径，暂不作为安全小版本发布的阻断项；这是依据代码链接结果作出的判断，不是“绝对无法利用”的证明。** x/crypto 仍被其他加密功能使用，不能为了消除模块提示把整个依赖删除。后续有官方版本时重新扫描替换；如果增加 OpenPGP 功能，必须重新评估并改用维护中的实现。

### 5.2 其他明确限制

- 正式生产旧镜像漏洞尚未消除，因为用户禁止本轮部署。
- 公共 ACME 真实签发和未来自动续期没有执行；测试了内部自动 TLS 状态持久化，并用**现有生产证书副本**验证默认公共 CA、HTTP/2 和反向代理，证书有效至 2027-01-01 14:41:18 GMT。这不能证明未来公共续期一定成功。
- HTTP/3 验证了配置、UDP 端口映射与正确的 `h3=":443"` 广告，没有实际 QUIC 客户端连通性验收；不能标记 HTTP/3 完整通过。
- 真实 Google OAuth、验证码投递和真实业务邮件没有在隔离测试中执行。5 个单元测试跳过的原因是未部署的旧社交 OAuth 草稿/可选供应商依赖；不代表 Google 生产登录已验收。
- 九语言检查只证明首页语言路由返回 HTML 200，不是完整翻译、排版、移动端视觉验收；没有新 UI。
- 没有压力攻击、破坏性漏洞利用、宿主 Docker/kernel 完整漏洞扫描或正式渗透测试。本报告的镜像结论不延伸为全主机安全认证。
- 生产备份在同一阿里云主机的私有目录，验证了恢复，但不具备异地灾备能力。上线前应准备受控异地备份，具体目标与敏感数据传输需另行确认。
- 正式法律主体、正式供应商协议、完整商家流程与会员收费不属 PR #2；本轮未修改正式协议或开发收费。

## 6. 实际测试与结果

最终的通过结果均来自阿里云原生 linux/amd64，不把本机模拟结果计为生产同架构验收。

| 测试 | 实际结果 | 证据 |
|---|---|---|
| 全部 PR #2 后端单元/集成测试 | 193 项；188 通过，5 跳过，0 失败；151.636 秒 | backend.log |
| 实际 HTTPS/HTTP 检查 | 45 通过，0 失败；证书校验开启，未用 curl -k | http.json、http.log |
| 平台所有者与最后管理员 | Cookie/H1/H2 下所有者关闭拒绝；其他管理员软关闭；最后活动管理员拒绝关闭 | HTTP 检查第 2–6 项 |
| 登录与权限 | 匿名拒绝、买家不能访问管理员 API、错误密码/停用账号拒绝；实际密码登录写入 Secure/HttpOnly/SameSite Cookie | http.json |
| 私有图片 | 匿名/其他商家/买家拒绝；所属商家与平台所有者允许；私有响应不被公开缓存 | http.json |
| Cookie 关闭与 CSRF | Cookie 单独认证可关闭合成业务账号并清 Cookie；外站/null Origin/cross-site 请求拒绝；被拒绝不影响原会话 | http.json |
| 会话撤销及历史保留 | 关闭后立即撤销会话/图片权限；logout-all 撤销旧和新 Cookie；其他所有者仍可看保留图片；合成业务记录数量未变 | http.json、data-preservation.log |
| TLS 1.2 / TLS 1.3 | 两者均验证证书，ALPN h2 | TLS12.log、TLS13.log |
| 代理、静态页面、语言路由 | 健康接口实际 auth JSON 200；8 个既有页面及 9 个语言路由 HTML 200；HTTP 308 到正式 HTTPS 域名 | http.json、http-redirect.log |
| 重启与 TLS 状态 | 两容器健康、重启后 HTTPS 200/HTTP2；内部自动 TLS 重启前后 CA 字节相同 | restart-https.log、automatic-tls-before/after.log |
| 现有证书兼容与非 root | 从备份恢复的证书副本在 UID10001 加载；默认公共 CA 校验、HTTP2 与 auth 代理通过；只改变副本拥有者 | legacy-tls.json、legacy-tls-https.log |
| 真实 SQLite 副本兼容 | 42 张原有表逐表行内容摘要和数量完全不变；quick_check ok；未启动服务器/邮件线程 | production-copy-compatibility.log |
| 生产外网只读核验 | 默认 CA HTTPS HTTP/2 200；HTTP 308；Caddy/nosniff/referrer 基础响应头存在 | external-https/http.log |
| 原生完整镜像扫描 | 最终 auth 0；Caddy HIGH/CRITICAL 0、UNKNOWN 1；旧镜像结果完整保留 | trivy/summary.json 及 4 份扫描 JSON |
| 最终 Compose | 阿里云 Docker Compose config 通过；两服务 readonly/cap_drop；低端口 sysctl 仅容器命名空间；没有执行生产 up | final-compose-addendum.json |
| 源码与历史安全检查 | 最终源码 Gitleaks/Trivy、Git 历史、GitHub CI 见交付记录 | security-reports 与 PR #2 checks |

5 个跳过项具体为：旧社交草稿的同邮箱跨 provider 合并/回调测试 2 项，以及 Facebook、Instagram、LinkedIn 可选验证测试 3 项。原因已记录，不能将 193 直接当成全部 193 通过。与第一轮 221 项数字不同是候选范围不同，不是把失败测试删除。

“现有业务兼容”包含既有完整 PR #2 后端测试、现有页面/API 路由和真实 DB 副本初始化；**没有使用真实车源、真实询盘或真实会员完成一笔线上交易**。合成测试是明确标注的隔离测试，不冒充真实业务验收。

### 排错过程也保留

1. pip vendor 的中间镜像扫描失败，最终移除不用的安装器 vendor、升级实际运行库并重新扫描。
2. Caddy 遗留 file capability 与 cap_drop 冲突导致启动失败，移除 file capability 后按非 root 验证。
3. 临时高内部端口令 HTTP/3 广告出现 8443，改回容器内部 80/443、隔离宿主端口映射后检查广告为 443。没有修改宿主全局 sysctl。
4. 阿里云私有目录 umask 导致 bind 文件/测试证书不可读，只调整隔离目录的候选公共源码权限及测试证书目录组权限；Linux 测试私钥保持 0640，CA 私钥 0600。
5. 部分公共资产未传齐，哈希检查拒绝继续。补传候选真实公共文件，并仅在生产文件 SHA 与候选一致时只读复制；最终 2,593 个公共文件验证通过，没有添加假库存或价格。
6. 本机模拟第一次测试继承了 QA 的平台管理员环境，引起 100 errors、3 failures；修正测试环境为独立数据库与最小变量。最终阿里云原生结果为 188/5/0。历史失败日志保留，不作为最终通过记录。

## 7. 备份、部署与回滚准备

**已完成、仅只读取生产资料：**

- 本地 Git bundle 校验、PR #2 原源码归档；恢复并核对 2,654 个文件内容。
- 阿里云只读 SQLite 在线 backup，一致快照恢复副本哈希相同，quick_check ok。
- 生产源码/私有配置、上传文件、Caddy 数据与配置卷、旧实际镜像均归档；恢复核对源码 5,128 个文件、上传 1 个文件、Caddy data 7 个、config 1 个。数量为本次真实归档结果，没有补造文件。
- 真实备份、私有环境、证书私钥不进入 GitHub；本地仅取脱敏结果和公共证书。证据导出只删除镜像 JSON 中的 ImageConfig 环境元数据，**没有删除漏洞行**；完整原始扫描仍保留服务器私有目录。

**部署与回滚步骤已经写入 `docs/ROUND3_RELEASE_RUNBOOK.md`，没有执行。**

核心顺序：取得单独批准 → 更新到当前时点的一致备份并恢复核对 → 核对批准提交与两份 archive/digest → 新发布目录、沿用现有私有环境与原数据卷 → 校验配置 → 维护窗口处理旧 Caddy 两卷的 UID10001 拥有者 → 先 auth 后 web → 外网及指定账号验收 → 监控。

回滚：保存上线后的新增数据 → 返回原代码/配置/固定旧镜像 → 按记录恢复 Caddy 权限 → **继续使用当前数据库和上传文件** → 验证服务。禁止直接将旧 DB 快照覆盖上线后新增用户、询盘、车型/车源、会员数据；数据修复需另行批准。禁止 down -v、全局 prune、删除卷。

**重要部署风险：**目前生产 Caddy 以 root 运行，候选是 UID10001。新镜像直接挂老卷可能无法读写证书。已经在副本验证迁移，生产迁移仍须批准、备份、限定两卷并在维护窗口执行。不要把本轮副本 chown 误写成生产已经完成。

## 8. 修改文件与 PR 关系

本轮只改隔离候选。原有账号系统、CRM、数据库结构、页面 UI 未重建；应用业务源码没有在第三轮改写。

| 文件 | 改动 / 修复难度 |
|---|---|
| auth/Dockerfile、auth/requirements.lock | 官方 Alpine 固定基础、依赖锁定、无安装器 vendor 的最终层、UID10001；中等 |
| docker/Caddy.Dockerfile | 官方源码重建 Go/net 补丁、非 root、去 file capability、健康检查；复杂 |
| compose.yaml | 固定候选 digest、readonly/cap_drop/no-new-privileges、tmpfs、容器低端口兼容；中等 |
| Caddyfile | 增加实际 auth /healthz 反向代理；简单 |
| scripts/preflight_seed.py、preflight_http.py、preflight_stage.py | 独立合成数据、真实 HTTPS 权限验收、原生/隔离校验；中等 |
| scripts/preflight_production_readonly.py、preflight_restore_assets.py | 只读备份恢复、真实 DB 副本完整行校验、公共资产哈希；复杂 |
| scripts/preflight_image_scan.py、preflight_legacy_tls.py | 实际镜像扫描、现有证书副本非 root/TLS/H2 测试；中等 |
| docs/ROUND3_RELEASE_RUNBOOK.md、ROUND3_EVIDENCE_SUMMARY.json、本报告 | 摘要、版本、备份/部署/回滚、风险记录 |

- [PR #2](https://github.com/wuoo6327-dot/autolink-platform/pull/2)：base main；继续作为独立安全候选。本轮追加镜像与验收，不加入入驻/SEO/会员业务。
- [PR #1](https://github.com/wuoo6327-dot/autolink-platform/pull/1)：完整第一轮功能，提交 5e4c41d4c4e8，保持不动。
- [PR #3](https://github.com/wuoo6327-dot/autolink-platform/pull/3)：base 为 PR #1 分支，提交 0a193a9bb27d，保持不动；后续整合安全候选时必须解决共同 Docker/Compose/后端文件冲突并重新测试。
- main 保持 `96f1f34c004dd924786cb50c5a0639b879d4dab0`。正式供应商协议仍是原 REVIEW_DRAFT，文件哈希 `07a59126e54405120988cc68e440420e29858e549d9f6b016c719d2f9d390228`，本轮未发布正式版本。

PR #2 的最终提交、检查和源码扫描记录将在交付记录中列出；保持草稿供所有者审查，没有自动合并、部署 workflow 或外部生产发布。

## 9. 下一步优先级

| 优先级 | 待做事项 | 难度 / 发布影响 |
|---|---|---|
| P0 | 审核 PR #2，单独批准安全发布；生产旧镜像的 HIGH 仍存在 | 中等；本轮没有授权发布，不能擅自处理 |
| P1 | 更新备份/恢复证明、确定批准提交和固定镜像；Caddy 旧卷权限迁移和回滚演练操作核对 | 中等；上线前必做 |
| P1 | 受控上线验收真实 Google 登录、邮件、现有证书自动管理/续期配置、外网 H2 和实际 H3/UDP | 中等；未测项保持待验证，不能当成通过 |
| P1 | PR #1/#3 另行完成法律资料、正式协议、业务/SEO 验收 | 复杂；正式商家运营另有门槛，不能靠安全 PR 替代 |
| P2 | 跟踪官方 Caddy 后续已修复二进制、UNKNOWN 变化，减少自维护补丁负担 | 中等；每个新 digest 重新扫描 |
| P2 | 受控镜像注册表、签名/SBOM、异地备份、真实负载和持续扫描 | 中等；不擅自新增账号、费用或敏感数据外传 |

## 10. 原始证据位置

本地私有备份目录：`deployment/autolink-round3-backup-20261010-034752`；原生证据在其中 `native-evidence/`，含完整漏洞行的四份 JSON、193 项后端日志、45 项 HTTP、TLS、数据库兼容、备份及生产不变证明。服务器真实备份只保留在本轮 native 隔离根目录内，不进入网站目录。

下载证据 archive：`000-round3-native-evidence.tar.gz`，SHA256 `2328eee16abb504e24646e7a68d8ea1deef14b040c245e7c9cf3c3b906d38`。最终 Compose 硬化比首次导出多了一次只读校验补充，SHA256 `292b690e637a4639b4f5d0e26a4725e5efead771077e0670b8283700c2edf420`；与实际 QA 已使用的硬化相同，app/Dockerfile/所有首次导出源码哈希除 Compose 外一致。最终配置校验和 QA 停止记录在服务器 evidence 及本地补充记录，没有重建或替换已测试镜像。

**最终建议：进入“安全小版本正式部署审批”阶段；批准前不执行上线。当前旧生产镜像安全风险尚未解除，完整商业运营条件仍需另行满足。**
