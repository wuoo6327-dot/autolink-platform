# 第五轮候选发布方案（历史记录，已被第七轮替代）

> 第七轮已按第六轮实际 OCI 归档修正历史 digest。本文件仅作历史说明，不能用于当前候选发布。当前版本、八个 site 覆盖文件及切换步骤以 `release-lock.json` 和 `ROUND7_RELEASE_RUNBOOK.md` 为准。

本分支基于已上线 a38664fc9bf2be639cbcb65dce4b57ef5b94170c。只整合旧接口兼容和公开车型 SEO；不合并 PR #1/#3 的角色、协议、入驻和报价业务改造。

## main 同步方案（仅方案，不执行）

先由所有者审核并将 PR #2 的准确部署提交正常合并到 main，保留提交历史；再将本轮以 PR #2 分支为基准的 PR 改为 main 并核对差异。禁止强推 main，禁止用 PR #1/#3 整包替换。生产发布以候选固定提交、运行文件哈希及镜像 digest 为准，不能只根据分支名称发布。

## 批准后必须重新预检、备份

1. 只读核对两台容器仍是第四轮安全 digest，生产数据库 quick_check 为 ok；核对磁盘、内存、实际源代码、公开静态文件、卷名称和健康状态。记录用户、车源、询盘、报价和会员数量，不导出隐私到 GitHub。
2. 将线上源码、Compose、Caddyfile、环境文件、上传目录、证书卷和运行镜像备份到本机服务器专用 0700 目录；SQLite 用备份 API 做一致性快照。验证归档可读、数据库完整性、恢复到独立 QA 卷可启动。备份不得外传。
3. 再核对本报告的候选 archive SHA256、manifest digest、AMD64 架构、UID10001、只读根文件系统、cap_drop ALL 和 no-new-privileges。未审核镜像禁止替代。
4. 新建版本目录；公开 site 从当前生产完整复制，再只覆盖本轮批准的静态文件。不能使用整个 Git site 覆盖生产，不能覆盖正式法律文件和现有 CSS。Caddyfile 使用本轮版本；auth 新增同一 site 的 /srv:ro 挂载。
5. 用 release-lock.json 的完整 auth digest 设置 AUTOLINK_AUTH_IMAGE；保持原生产 .env 的 Google、邮件和所有者参数。Compose 项目仍为 autolink-demo，三个原有卷名称不变。不能使用 QA Compose、QA 证书、QA 数据或 QA 凭据。

## 切换与回滚

维护窗口另行批准。建议中断上限 5 分钟。先更新 auth 并验证健康，再更新 web 配置；Caddy 镜像保持第四轮已验证 digest，证书卷 UID10001 权限已具备，不需要重新 chown。每个镜像必须与 release-lock.json 一致。

任何私有数据泄露、权限异常、数据库完整性异常、核心页面持续失败、认证不可用、证书读取失败或容器连续重启立即停止并回滚。保留最新生产数据库和上传资料，仅恢复第四轮安全版本的代码、镜像、Compose、公开 site 和 Caddy 配置。不允许用旧数据库覆盖新记录；不回退到第四轮之前的漏洞镜像。

禁止 docker compose down -v、volume prune、删除证书、删除或重建数据库。上线后复核首页、目录、234 个车型九语言、私有图片、账号关闭保护、Cookie/会话、HTTPS/HTTP2、真实公开供应商、旧接口、Sitemap/robots 与私有页 noindex；没有授权测试邮箱时 Google/邮件实测继续待验证。至少监控 30 分钟后交付真实生产结果。

## 本轮资料限制

已有 234 个目录保持不变；39 个未提供详细配置参考、38 个没有可确认年份，页面只展示已有品牌/能源/车身等参数和“年份未提供”，不得补造。Google 实际抓取和索引只能上线后核实，隔离技术测试不等于 Google 收录。


## 供下一轮批准后执行的明确命令顺序

以下是准备好的操作说明，本轮没有在生产执行。`ROUND5_RELEASE` 必须是批准提交的新版本目录，`ROUND5_ENV` 是原生产环境文件的服务器本地副本，均在核对 SHA256 后填写。不能从 Git、QA 或本地测试环境生成正式密钥。

1. 核验 `release-lock.json`。对服务器上的 `auth-image.tar`、`caddy-image.tar` 执行 `sha256sum`；用归档 `index.json` 和 manifest/config/layer 内容分别核验 SHA256、AMD64 和 UID10001。不得把 Docker 的 image ID 当作 config digest。若镜像不在本机，`docker load --input` 只加载这两个已验收归档，禁止重新构建代替。
2. 重新制作服务器本地备份：新建 `/home/admin/autolink-round5-release-<批准时刻>/private-backup`（0700）。SQLite 用 `sqlite3.Connection.backup`，不能直接复制正在写入的 SQLite 主文件；核对 `integrity_check`、表及主键数量。归档当前源码/Compose/.env、auth_data 中的上传文件、`autolink-demo_caddy_data` 与 `autolink-demo_caddy_config`。旧安全镜像也保存并核验 digest。恢复演练只使用独立 QA 数据及证书卷，网络隔离、邮件关闭。新备份没有通过演练就不能切换。
3. 从当前生产目录复制完整公开 site 到新版本目录；只覆盖 release-lock 中五个 site 文件，再逐个核验哈希。除本轮五个覆盖/新增目标外，其余生产公开文件必须与当前生产相同。禁止覆盖法律文件、CSS、车型配置参考库。新 Compose 挂载新公开 site `/srv:ro`，三个卷仍为现有 autolink-demo 卷。
4. 设置镜像变量并只做配置验证：

```sh
export AUTOLINK_AUTH_IMAGE='autolink-round5-auth-candidate@sha256:07e7cbe0475265901922dcb3dbb52a5afaab070c4489cf9c6f2b03b504dda578'
docker compose --project-name autolink-demo --env-file "$ROUND5_ENV" -f "$ROUND5_RELEASE/compose.yaml" config --quiet
```

5. 候选 Caddyfile 的配置校验采用已固定的 Caddy 镜像，单独运行 `caddy validate`；验证时只挂载新公开配置，不使用生产证书卷。确认 UID10001 已能读取现有指定证书卷，本轮不再执行 root→UID10001 权限调整。
6. 在批准的维护窗口中先切换 auth：

```sh
docker compose --project-name autolink-demo --env-file "$ROUND5_ENV" -f "$ROUND5_RELEASE/compose.yaml" up -d --no-deps auth
```

等待 auth healthy，核对实际 manifest、21 个应用文件哈希、数据库 `quick_check`、公开 API 和匿名权限；未通过就回滚，不能继续 web。然后：

```sh
docker compose --project-name autolink-demo --env-file "$ROUND5_ENV" -f "$ROUND5_RELEASE/compose.yaml" up -d --no-deps web
```

7. 外网复核 HTTPS、HTTP/2、HTTP→HTTPS、首页及主要入口、两个旧接口、初始车型 HTML、Sitemap/robots、私有页 noindex。线上权限检查以不改真实数据的方式进行；账号关闭等破坏性检查沿用已通过的隔离测试。核对最新数据库与上传文件没有被覆盖，连续监控至少 30 分钟。
8. 若触发回滚，使用 `/opt/autolink-releases/a38664fc9bf2be639cbcb65dce4b57ef5b94170c/compose.yaml`、原环境文件、原公开 site 与原 Caddyfile；先恢复旧安全 auth 并健康检查，再恢复 web。项目名仍为 autolink-demo。原 Compose 已固定旧安全镜像，不使用候选镜像变量替换。数据库、上传目录和两个证书卷继续使用当前卷；不能恢复部署前旧数据库覆盖新数据。

上述命令包含生产动作，只有下一轮明确部署批准、重新预检和备份恢复演练通过后才能执行。本轮固定镜像归档保留在 AMD64 服务器，无须在本机 ARM64 重建。
