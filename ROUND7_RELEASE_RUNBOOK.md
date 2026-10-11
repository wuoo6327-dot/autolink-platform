# 第七轮 SEO 发布与回滚手册

> 历史版本：本手册和根目录 `release-lock.json` 对应旧的 234 车型候选，禁止用于当前 244 车型发布。当前候选以 `SEO_RELEASE_RUNBOOK_20261012.md` 和 `docs/SEO_RELEASE_LOCK_20261012.json` 为准。

状态：隔离验收完成，未部署生产。必须取得本轮的单独生产批准后再执行本手册中的生产动作。

## 1. 固定版本及发布范围

- 运行代码提交：`406495bca6a13f72455e0d7b4155757ce6c2e9f8`。后续提交只补充发布锁、证据和文档；发布时另行记录批准的最终 Git HEAD，并确认运行文件与此提交相同。
- 基于第四轮 PR #2 安全版本 `a38664fc9bf2be639cbcb65dce4b57ef5b94170c`，接续 PR #4 原提交 `535dbdd2439d7dda0dcf9421033c5660cbfef3a9`。不混入 PR #1/#3 的其他业务修改，不合并或强推 main。
- auth：`autolink-round7-auth@sha256:9e3bba2af4310b1befbd924cdc1a22ece8f9826e1af2c158713b5f0695664ae2`。
- Caddy：`autolink-round3-caddy@sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`，保持第四轮已验收二进制。
- auth OCI 归档：`/home/admin/autolink-round7-stage-20261010-1515/auth-image.tar`，SHA256 `78fd2da1af3a232ed233756ec30e7196bc3066a23837b040014d45a0df5be0e8`。
- Caddy OCI 归档：`/home/admin/autolink-round5-stage-20261010-1132/caddy-image.tar`，SHA256 `ddf2c2f6544eea709258695c53da57bc42b27850a52e2af5a27c61875e59927e`。
- 配置、源文件、config digest、架构及非 root 用户以 `release-lock.json` 为准。只能加载已验证归档，不得临时重建替代。

## 2. 批准后重新预检与生产备份

建议切换中断上限 5 分钟，维护窗口须在下一轮批准时确认。本轮之前的窗口不自动沿用。

1. 确认阿里云同一 AMD64 主机、Docker/Compose、生产 auth/web 身份和 digest、健康及重启次数，确认没有其他服务占用发布端口。检查磁盘、内存和日志；任何关键异常先停止。
2. 只读核对现有数据库、上传资料、证书和环境文件实际位置。记录数据库完整性、表数量和业务记录数量，不把记录内容导出到报告/GitHub。核实 Compose 项目名 `autolink-demo` 及其三个指定数据卷，不能靠卷名猜测位置。
3. 创建新的服务器本地 0700 备份目录；包含当前源码、公开 site、Compose/Caddyfile、环境文件、现有运行镜像、上传资料、Caddy data/config 卷。一致性 SQLite 快照使用 `sqlite3.Connection.backup`，验证 `integrity_check`、`foreign_key_check`、表与主键数量。不能直接复制写入中的 SQLite 主文件作为一致性备份。
4. 核验备份可读及归档内容，在独立 QA 卷、内部网络、关闭邮件的环境演练恢复；对每个文件核对内容 SHA256、uid/gid/mode，对数据库核对记录及 schema。不得挂载生产卷，不登录恢复副本中的真实用户，不执行真实账号删除测试。新备份未验证就不允许切换。
5. 第六轮生产备份和第七轮隔离备份是现有恢复证据，不能替代发布时的新生产备份。真实备份只留服务器，不传 GitHub、Hostinger 或其他外部服务。

## 3. 准备发布目录及校验

在批准的新版本目录准备文件，以下变量需填入已核实路径：`ROUND7_RELEASE`（新目录），`ROUND7_ENV`（当前生产环境文件的服务器本地副本）。不能使用 QA 凭据、QA 数据库或 QA 证书。

1. 对两个归档执行 SHA256 校验；读取 OCI index、manifest、config 和各层校验摘要，确认 `linux/amd64`、UID/GID `10001:10001`。Docker image ID 与 OCI manifest digest 是不同字段，分别比较，不可混用。
2. 从**当前生产**完整复制公开 site，按发布锁覆盖且只覆盖八个 site 文件：

   - `site/assets/business-page-bootstrap.mjs`
   - `site/assets/business-seo.js`
   - `site/assets/index-autolink-membership-apply-pricing.js`
   - `site/assets/public-directory.js`
   - `site/locales/seo-index-reviews.json`
   - `site/locales/seo-verified-terms.json`
   - `site/robots.txt`
   - `site/trade/model-reference.mjs`

3. 同时准备已验收的 `compose.yaml`、`Caddyfile` 和 `release-lock.json`。逐个核对哈希及静态覆盖包 SHA256，其余生产公开文件必须完全相同。不能拿 Git 中的整套 site 覆盖生产，不改现有法律文件、CSS、车型参考库和真实目录资料。
4. auth 挂载此公开 site 到 `/srv:ro`，web 使用同一目录。保留原数据库及两个 Caddy 卷、只读根文件系统、cap_drop ALL、no-new-privileges 和健康检查。
5. 核对现有指定证书卷 UID10001 权限。第四轮已完成权限兼容，本轮不需要 chown/chmod；出现不匹配先阻断，不批量改变其他卷。
6. 保留原生产 Google、邮件、所有者等环境参数。分别验证 Compose 和 Caddy 配置：

```sh
export AUTOLINK_AUTH_IMAGE='autolink-round7-auth@sha256:9e3bba2af4310b1befbd924cdc1a22ece8f9826e1af2c158713b5f0695664ae2'
docker compose --project-name autolink-demo --env-file "$ROUND7_ENV" -f "$ROUND7_RELEASE/compose.yaml" config --quiet
```

`caddy validate` 使用固定 Caddy 镜像及新公开配置在独立容器中运行；不挂载生产证书卷，不降低证书校验或容器保护。

## 4. 批准后切换顺序

1. 新备份恢复验证通过、版本匹配、资源正常且进入批准窗口后，只切换 auth：

```sh
docker compose --project-name autolink-demo --env-file "$ROUND7_ENV" -f "$ROUND7_RELEASE/compose.yaml" up -d --no-deps auth
```

2. 等待 auth healthy，核对实际镜像及运行文件、数据库完整性、匿名权限和公开 JSON API。任何关键失败立即恢复旧安全 auth，不能继续切换 web。
3. auth 检查通过后切换 web 配置（Caddy 镜像保持不变）：

```sh
docker compose --project-name autolink-demo --env-file "$ROUND7_ENV" -f "$ROUND7_RELEASE/compose.yaml" up -d --no-deps web
```

4. 外网立即检查 HTTPS/TLS、HTTP/2、HTTP→HTTPS、健康检查、主页与后台入口、静态资源及两个旧接口。复核初始 HTML 正文、Canonical、质量门槛及 Sitemap。39 个薄内容车型及全部未审核语言/品牌详情为 `noindex,follow`，robots 必须允许读取这些页面。
5. 在生产只做不改变真实数据的权限检查；账号关闭、CSRF 和跨企业图片等破坏性验证采用本轮已通过的隔离测试。Google 登录/验证码/找回密码若没有单独授权测试账号及邮箱，记录待验证，不能操作真实客户账号或虚构通过。
6. 核对数据库和上传文件未覆盖，至少连续监控 30 分钟：可访问性、5xx、登录及数据库异常、重启、CPU/内存、证书和代理日志。重新扫描实际运行镜像，保留 UNKNOWN，不增加忽略规则。

## 5. 触发条件与回滚

任一条件触发立即停止后续操作并回滚：核心页面持续不可用、认证不能恢复、数据库完整性异常、私有资料暴露、权限异常、证书不可读、关键接口持续错误、容器不断重启或资源耗尽。切换中断超过批准上限也回滚。

- 使用第四轮安全目录 `/opt/autolink-releases/a38664fc9bf2be639cbcb65dce4b57ef5b94170c` 的源码、Compose、Caddyfile、公开 site 和原环境参数。
- auth 恢复为 `autolink-round3-auth@sha256:328ad2e7f193a924d8ddc9943c2bde450e26e1b1af7318b26b1e4cb8984d4b80`；Caddy 保持本手册的已验收 digest。
- 保持 `autolink-demo` 项目名及**当前最新**数据库、上传和证书卷。先恢复 auth 并健康检查，再恢复 web；清除本轮候选镜像变量或显式指定旧安全镜像，避免变量覆盖旧 Compose。
- 不使用部署前的旧数据库替换新产生记录，不删除证书，不重新建库。回滚会撤销本轮 501/SEO 修复，但保留第四轮安全保护。
- 本轮隔离副本已实际执行旧安全版→候选版→旧安全版，记录/schema、文件及权限一致，HTTPS/HTTP2 正常；不是生产回滚演练。

禁止 `docker compose down -v`、`docker volume prune`、未验证迁移及任何真实数据清理。

## 6. 上线后 Google Search Console

1. 使用所有者已授权的 Search Console 属性，核对域名与 HTTPS；不新增未知账户权限。
2. 提交车型 Sitemap 和 Sitemap index，品牌 Sitemap 当前合法为空；不能手工提交 2,106 个车型语言 URL。
3. 对完整中文车型、薄内容车型、未审核外语车型、品牌详情分别抽查“测试实际网址”：HTML 正文、200、Canonical、index/noindex、robots 可读取和 hreflang。
4. 仅为通过质量门槛的中文车型申请索引。对 noindex 页面观察重新抓取后的排除结果，不能用 robots 屏蔽替代 noindex。
5. 监控抓取统计、网页索引、重复/Canonical 与语言问题。Google 是否收录、何时收录和排名以真实 Search Console 结果为准，本轮技术验收不保证收录。
6. 将来补充真实资料或审核翻译后按 `SEO_INDEX_POLICY.md` 验证，再恢复对应页面索引资格。型号、数字、单位、真实年份和配置不得为了 SEO 改写。
