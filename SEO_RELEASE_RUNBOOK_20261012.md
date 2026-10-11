# AUTOLINK 244 车型 SEO 候选发布与回滚

状态：仅供审批；未经本轮单独批准，不执行生产切换、main 合并、Sitemap 提交或索引请求。固定信息见 `docs/SEO_RELEASE_LOCK_20261012.json`。PR #4 的修改已在本分支祖先提交中，旧 `release-lock.json` 属 234 车型历史候选。

## 发布前核验

1. 在阿里云同一 AMD64 主机确认现行 auth/web 镜像、健康、只读文件系统、非 root 用户、cap_drop ALL、no-new-privileges、TLS/证书卷及数据库卷位置。确认当前生产公开目录仍是 244 车型、53 品牌，并重新执行 `scripts/verify_live_catalog_release.py`。若有新车型或资料变化，停止使用本锁，重新审核资料、镜像及 Sitemap。
2. 校验两个镜像归档的 SHA256、auth 本地镜像 ID 和 web manifest digest。auth 暂无注册表 digest；跨主机部署前须把**同一镜像**推送到受控仓库、记录 manifest digest 并重新核验，不得把本地镜像 ID 冒充 registry digest。
3. 从**当前生产**只读复制公开 site、Caddyfile 和运行配置到新发布目录。用 `scripts/build_seo_release_site.py` 从该副本生成 `release-public/site`；仅覆盖受控 SEO 文件及 245 个已校验的车型 WebP/manifest，不删除或覆盖其他线上文件。检查生成的 `release-public/overlay-manifest.json` 和其他文件哈希相等断言。
4. 对当前生产 SQLite 使用一致性备份 API 创建服务器本地快照，验证 `integrity_check`、`foreign_key_check`、记录数量及恢复副本。记录上传资料与证书卷快照/校验，不复制私有资料进 Git。备份未验证则不切换。
5. 在独立网络、独立 127.0.0.1 端口、独立测试库和只读容器运行 `scripts/amd64_seo_release_rollback_qa.sh`；候选、回滚和再次恢复应均保持至少全部现行车型与品牌，候选和恢复的 Sitemap 应为当前审核数量。这个步骤只测试隔离副本。

## 批准后的切换顺序

1. 新建不可变发布目录，放置批准的 Git 提交、固定 auth 镜像归档、现行固定 Caddy 镜像、`release-public/site`、候选 Caddyfile 和 Compose 配置。Compose 继续使用现有项目名、现有数据库及上传/证书卷，保留现有登录、Cookie、CSRF、权限和容器保护；绝不以测试库替换生产库。
2. 先切换 auth 并等待健康；检查公开 244/53 基线、新增线上记录仍在、私有 API 拒绝匿名、车型 HTML 正文、404 与 Sitemap。再切换 web 配置。任何异常立即按下节回滚。
3. 从外网核对 HTTPS、robots、Canonical、hreflang、中英文样页、`noindex` 样页、图片、首页、登录和权限。监控健康、5xx、资源与数据库至少 30 分钟；记录真实生产结果。

## 回滚

1. 保持**当前最新**生产数据库、上传资料和证书卷；恢复原生产 site、Caddyfile 和固定安全镜像。旧 auth 镜像内置历史目录，直接启动会把 26 个旧车型和 7 个品牌补入共享库。因此旧镜像必须额外只读挂载本轮已核验的 `auth/catalog.json` 到 `/app/catalog.json:ro`；隔离回滚已证实这样可以保持 244/53。若生产目录在切换后又变化，须先核对并生成相应当前目录文件，不可盲用旧快照。
2. 先恢复 auth 并检查健康、权限、当前真实目录及数据库记录；再恢复 web。若回滚异常，以已核验的生产备份和恢复预案处理，禁止直接覆盖新产生的数据、删除卷或运行 `docker compose down -v`。
3. 记录回滚触发条件、起止时间、最终镜像 ID、数据完整性和公开页面状态。隔离回滚成功不能替代生产回滚结果。

## Search Console

生产切换后另获授权，再对代表性中英车型、资料不足车型和品牌页执行 Search Console **实时 URL 检查**，记录 Google 实际抓取正文、资源、Canonical 和可索引性；只有另获提交授权才提交 Sitemap 或索引请求。真实收录、曝光、点击和询盘分别统计。
