# 第三轮候选发布与回滚说明（未执行生产部署）

本文件只提供后续审批时的操作顺序。执行生产操作必须取得所有者单独批准；本轮仅在 `autolink-qa-round3-native` 项目执行验收。

## 固定交付物

平台 `linux/amd64`，Docker 29 的平台 manifest 与配置 digest 不是同一个值。

| 组件 | 本地 Docker 导入后可用的固定引用 | 配置 digest |
|---|---|---|
| Python | `autolink-round3-auth@sha256:328ad2e7f193a924d8ddc9943c2bde450e26e1b1af7318b26b1e4cb8984d4b80` | `sha256:25736f3ba1098c31cd84e58b73170ae737f83e298c7cad0f66a89ae64012c114` |
| Caddy | `autolink-round3-caddy@sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb` | `sha256:335a69d3f130d4b91a1729b94e69371e302e3831fb6296054d45b79dd9c1bc6d` |

镜像没有发布到公共注册表。先加载经过校验的 Docker archive，核对 `docker image inspect` 的 `Architecture` 和 `Descriptor.digest`，再使用 Compose 中的固定引用；不得将标签相同误认为内容相同。

Archive SHA256：

- auth-image.tar：`f7e329d3be8bb854b846081c73f2a34d3fc97fcb9c7f30c2d99a2b819e61cb9e`
- caddy-image.tar：`ddf2c2f6544eea709258695c53da57bc42b27850a52e2af5a27c61875e59927e`

重新构建可能因上游包索引、构建元数据而产生不同 digest。新 digest 必须重新扫描和验收，不能沿用这两份镜像的通过结论。

## 发布前备份

1. 审核批准 PR #2 的明确提交，记录当前生产容器 ID、启动时间、镜像 digest、Compose project 与数据卷名。
2. 新建独立、权限 0700 的备份目录；用 SQLite 在线 backup API 从只读连接获取一致副本，不直接复制正在写入的单个 SQLite 文件。
3. 备份源码、私有 `.env`、上传文件、Caddy 数据/配置卷，以及实际旧镜像 archive。记录 SHA256；将源码、文件、数据库恢复到另一独立目录，验证文件哈希和 SQLite quick_check。
4. 部署时重新备份，第三轮时间点备份不覆盖随后新增的真实询盘与用户。备份不进入 Git，也不放在可下载的网站目录。

## 审批后才执行的部署顺序

1. 在新 `/opt/autolink-releases/<approved-commit>` 目录准备已审核候选代码和公共 site 文件。逐项验证源码与镜像 archive；保留 `/opt/autolink-demo` 原目录作为回滚版本。
2. 私下沿用当前有效 `.env`，保持真实邮件、Google Client ID、平台所有者、域名配置一致。先检查必填变量，不输出 API Key。不得从 QA 的空邮件配置或合成账号复制生产配置。
3. 加载上述两份固定镜像；执行 Compose config 与 Caddy validate，检查非 root UID 10001、只读根文件系统、权限限制、80/443 TCP 和 443 UDP、原有卷名。
4. **现有 Caddy 卷由旧 root 进程创建，必须先处理拥有者。** 在维护窗口停止旧 web 后，先确认两卷确属 `autolink-demo_caddy_data`、`autolink-demo_caddy_config` 并完成备份；仅将这两卷内部所需文件拥有者改为 10001:10001，保留文件权限、证书内容和路径。禁止对整个 `/var/lib/docker`、auth 数据卷或宿主根目录执行递归修改。本轮只在证书副本验证了该迁移，未修改生产卷。
5. 以项目名 `autolink-demo` 使用候选 Compose，继续挂载 **原有** auth_data、caddy_data、caddy_config；先更新 auth 并等 healthy，再更新 web 并验收。不要使用任何 `down -v`、volume rm、prune 或数据库清空命令。
6. 外网默认 CA 校验 HTTPS、HTTP/2、HTTP→HTTPS 308、健康检查 JSON、匿名权限和页面；仅使用指定验收账号检查登录与业务，不能拿真实用户做关闭测试。
7. 检查 Caddy 自动管理现有证书的加载和续期配置、HTTP/3 实际 UDP 连通性、错误日志和资源使用。公共 ACME 签发/未来续期以及真实 Google 登录、邮件投递没有在本轮隔离测试中执行，必须单独验收。

## 回滚顺序

1. 发现启动失败、代理错误、权限回归或数据异常，立即停止扩大流量；先保存当前新增数据的一致备份。
2. 返回保存的旧 Compose/源码目录，选择备份记录中的 **旧固定镜像**，恢复原环境配置与 Caddy 卷拥有者/权限记录，只重建需要回滚的容器。镜像若被清理，从已校验旧 archive 导入。
3. **优先回滚代码和镜像，继续使用当前数据库及上传文件。** 本轮真实数据库副本初始化验证原有记录未变，不要求把生产数据库恢复到旧时间点。不得直接用旧快照覆盖上线后新增用户、车源、询盘和会员记录。
4. 如确有数据修复需要，先核实差异、保存新数据并制定逐项恢复方案，取得额外批准。禁止无条件数据库回滚。
5. 重验外网 TLS、HTTP/2、代理、旧服务健康、账号权限及业务读取；保留事故日志和所有备份。

## PR 依赖

PR #2 是从 main 提取的独立安全候选，第三轮镜像与验收继续归入该 PR。PR #1 是完整业务/SEO/入驻候选；PR #3 以 PR #1 分支为基线。PR #1/#3 后续整合 PR #2 时需解决共同文件冲突并再次验收，不能一次全部合并或把 PR #3 直接视为独立生产版本。
