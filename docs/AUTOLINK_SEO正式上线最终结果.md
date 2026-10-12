# AUTOLINK SEO 正式上线最终结果

**最终状态：已上线，存在待验证事项。** 生产核心验收和连续 30 分钟监控通过；Google Search Console 已接收根 Sitemap 提交，但截至本报告完成时仍显示 `Couldn't fetch`，尚不能认定其已处理 URL。本报告仅记录 2026 年 10 月 12 日实际执行的生产切换、隔离恢复、公网验收和 Google Search Console 结果。时间除特别注明外均为 UTC。

## 1. 发布范围与版本

- 发布入口为 [PR #9](https://github.com/wuoo6327-dot/autolink-platform/pull/9)，发布脚本 HEAD 为 `224bdb522db154eec67a0c0d1d887dc373e91378`，仍为草稿 PR，未合并 `main`。PR #6 → #7 → #8 为其祖先链；未重新合并 PR #4。仓库维持 Public，未调整可见性。
- 正式候选目录为 `/opt/autolink-releases/5725b8b-seo-20261012`，站点文件对应 Git 提交 `5725b8b3e25e5d80172e8a4df920b58b0bf29ccd`。上线内容限于英文车型/品牌 SEO、车型和品牌 SSR、英文采购指南、robots、Sitemap、Canonical、hreflang、404/noindex、必要静态资源及旧接口兼容。保留当前首页、移动端设计、登录与业务功能；未纳入未经独立验收的重型首页性能改造。
- 当前 Auth 应用镜像源码构建基点 `129c08e09efb3b6a9c99b10fb6aa8885d8b160b6`。发布时**不重新构建、不拉取镜像**，只使用同一阿里云主机已加载且经过归档验证的固定镜像。

## 2. 真实数据、索引资格与公网页面

- 生产 SQLite 实际有 **270 条车型、60 条品牌记录**；公开目录有 **244 个车型、53 个品牌**。没有用旧目录种子覆盖数据库。备份前、切换前和切换后的目录计数一致。
- 生产 Sitemap 为 **50 个英文车型、177 个中文车型、10 个英文品牌 URL**；模型 Sitemap 共 227 条，品牌 Sitemap 10 条。其余车型及尚未审核的语言可访问但暂缓索引。具备技术索引资格不等于 Google 已收录。
- 从外部公网逐页检查 244 个英文车型页和 53 个英文品牌页，初始 HTML、H1、英文 `lang`、Canonical 与 index/noindex 均通过，失败 0；177 个中文车型 Sitemap URL 均通过；50 个可索引英文车型的主图请求全部返回图片，失败 0。抽查阿拉伯语、俄语、法语保持独立 Canonical 与 `noindex`，已审核英中页面只互相声明 hreflang。
- 公网抽查：首页、英文车型/品牌、robots、根 Sitemap、车型/品牌 Sitemap、登录均为 200；不存在车型为 404，匿名后台接口为 401，私有样例图片为 404。浏览器中英文切换、244 车型目录、搜索 “Monjaro” 与进入详情均正常。Geely Monjaro 初始详情显示真实年份、版本、8 项参数、相关车型和“暂无已审核车源”。

## 3. 镜像身份与安全

| 镜像 | 实际 Docker Image ID / 同主机本地清单摘要 | 完整归档 SHA-256 |
| --- | --- | --- |
| 新 Auth | `sha256:0fcb1f1c73a0d6b7b23c81355a9d48ca1e82e514705011d26c63a7cd5aaff815` | `4362de3c243ec679282da29f3d577ce68fd612d8c1cec00970921029da23f4bf` |
| Web / Caddy | `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb` | `ddf2c2f6544eea709258695c53da57bc42b27850a52e2af5a27c61875e59927e` |

上述清单摘要来自本机 containerd 的 `moby` 命名空间，不是远程 Registry Manifest Digest；本轮经所有者允许，采用同主机不可变归档交付。`scripts/verify_local_release_image.py` 核验完整归档 SHA、配置、压缩及解压层、AMD64 架构、已加载 Image ID 和本地清单；Auth 的 21 个应用文件逐一匹配构建源码。发布 Compose 固定两个 Image ID 且关闭 pull/build。证据在远端 `auth-local-image-evidence-v2.json`、`web-local-image-evidence.json`。

PR #9 最新提交的两项 `source-security` GitHub Actions 实际运行并通过：[运行一](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38224173078/job/114727486299)、[运行二](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38224179198/job/114727506596)。Gitleaks/Trivy 未发现阻断性的 CRITICAL/HIGH；Web 的既有 UNKNOWN 漏洞条目仍需跟踪。HTTPS 证书主体 `autolinkglobal.com`，公网校验通过，有效期至 2027-01-01 14:41:18 UTC。

## 4. 最新备份、隔离恢复与回滚

- 最终切换前备份清单：`/opt/autolink-backups/seo-cutover-20261012/final-20261012T083247Z/release-backup-manifest.json`，创建于 2026-10-12 08:33:18 UTC。真实数据库源路径从运行中 Auth 容器的 `/data` 挂载读取，为 `/var/lib/docker/volumes/autolink-demo_auth_data/_data/autolink-auth.sqlite3`。
- 最新 SQLite 一致性备份：同目录 `autolink-auth-20261012T083247Z.sqlite3`，SHA-256 `ec04bd0080d99adc7e2faac841aa986b4132da42981c2af4fac74811b39e8317`；`integrity_check=ok`、外键违规 0、270/60 条记录，隔离复制恢复及哈希校验通过。
- 同一私有目录还保存用户上传与 Auth 非数据库文件、Caddy 证书及配置卷、旧源码和运行配置、旧 Auth/Web 镜像、当时公开目录。压缩包均隔离解压并逐文件比较，归档摘要由备份清单固定。生产数据库和持久卷未执行清空、覆盖、`down -v` 或无关迁移。
- 第一轮切换在 08:29:57 UTC 启动。Web 重建后即时 TLS 探针遇到 curl 35，脚本恢复旧 Auth 和旧 Web；回滚末端过早探针同样报错，状态文件保留 `rollback_failed` 原始记录。随后人工只读核查旧镜像、两个健康容器、HTTPS 200、244/53 目录及匿名权限均通过。修复了 Web Docker 健康和公网 TLS 就绪等待，用新状态目录、新备份重新预检。
- 第二轮于 08:34:24 UTC 启动，08:34:51 UTC 完成新 Auth、Web 与生产核心探针；第一轮日志不覆盖。单次状态分别留在 `/opt/autolink-release-state/seo-20261012/` 与 `/opt/autolink-release-state/seo-20261012-attempt2/`，切换由服务器端 tmux 运行，Workbench 页面切换不会终止。失败时脚本在限定时间内先恢复旧 Auth 再恢复旧 Web，并保留最新数据库与上传卷。

## 5. Google 实际验收与提交

- 使用已授权的 `autolinkglobal.com` 域名 Search Console，真实 **URL Inspection Live Test**（Google Inspection Tool smartphone），不是伪装 User-Agent：Geely Monjaro、Zeekr 9X、BYD Han 及 Geely 英文品牌页面均显示“URL is available to Google”、抓取成功、允许索引、用户声明 Canonical 与英语 URL 一致；Google 渲染截图可见车型英文正文与图片或品牌介绍。
- BYD Song PLUS 当前尚未通过内容资格，真实 Live Test 显示 “Excluded by ‘noindex’ tag”；没有对它申请索引。Geely Monjaro、Zeekr 9X、BYD Han 在本次提交前均为 Google 尚未知的 URL，不得记作已收录。
- Search Console 页面索引报告截至 2026-10-09 为 **1 个已索引 URL、1 个因重定向未索引 URL**。搜索表现的最近 7 日（10 月 3–9 日）为 **1 次点击、56 次曝光**，主要查询为品牌相关词；这些是上线前历史数据，不是本轮 SEO 成效。
- 连续 30 分钟生产监控完成后，向域名资源提交 `https://autolinkglobal.com/sitemap.xml`，Google 两次返回 **“Sitemap submitted successfully”**；但报告中的该条记录仍为 **`Couldn't fetch`、Type `Unknown`、Discovered pages 0、Last read 空白**。不能把表单提交成功写成地图读取成功。直接公网 GET 为 HTTPS 200，根 XML 与五个子 XML 均可解析；Google 对根 XML 的真实 Live Test 显示 `Crawl allowed: Yes`、`Page fetch: Successful`；Search Console 手动处置报告为 `No issues detected`。已按 Google 指引完成一次有限重试，处理状态仍需后续复查；若持续失败，应检查 Google 抓取日志及 Search Console 错误详情再决定修复，不能反复无依据提交。
- 对 **Geely Monjaro、Zeekr 9X、BYD Han** 三个已通过实时检查的英文车型分别申请索引，三次均收到 **“Indexing requested”** 回执，进入 Google 优先抓取队列。未对 BYD Song PLUS 等 `noindex` 页面申请索引。申请成功、Sitemap 提交及技术索引资格都不等于 Google 已收录；Google-selected Canonical 需待实际索引后才能确定。
- 网站地图提交后的 Search Console 表格截图保存在本地 `release-evidence/gsc-sitemap-status-20261012.jpg`，原始公网 Lighthouse JSON 保存在同目录；这些运行证据不加入公开仓库。

## 6. 公网性能与功能

Lighthouse CLI 13.5.0、Mac Chrome 154、真实公网 URL，手机默认配置与桌面预设各做三次独立冷测；以下为中位数，原始 12 份 JSON 在本地 `release-evidence/public-lighthouse-20261012/`。该环境与此前阿里云 AMD64 隔离报告不同，分数不能直接作为同条件前后增益。

| 页面 | 设备 | Performance | LCP | TBT | CLS |
| --- | --- | ---: | ---: | ---: | ---: |
| 首页 | 手机 | 28 | 8,111 ms | 2,631 ms | 0 |
| 首页 | 电脑 | 37 | 3,607 ms | 586 ms | 0 |
| Geely Monjaro 详情 | 手机 | 99 | 1,844 ms | 0 ms | 0 |
| Geely Monjaro 详情 | 电脑 | 100 | 434 ms | 0 ms | 0 |

手机首页仍未达到 2.5 秒 LCP / 200 ms TBT 目标，且桌面首页 TBT 也高；本轮未为追分删除正文、极氪素材或功能。车型详情 CLS ≤0.1。生产浏览器中首页英文切换、车型目录搜索、详情进入及语言链接通过；独立 AMD64 隔离环境此前还完成了 225 项后端/权限测试（220 通过、5 跳过）及全部 2,673 个九语言详情检查。公网运行一次基于 Node 的浏览器回归时，服务器没有 Node 可执行文件，该命令未运行；以实际浏览器交互、Google 手机渲染和公网 Lighthouse 作为本轮浏览器证据，不将未执行测试写为通过。

## 7. 上线监控与剩余事项

第二轮切换的 30 分钟监控于 **09:05:50 UTC** 完成，状态 `completed`、发布进程退出码 **0**、关键探针失败 **0**；两个实际运行容器分别使用上表锁定的 Auth/Web Image ID，均为 `healthy` 且重启次数 **0**。脚本每分钟检查固定镜像、健康、HTTPS、车型/品牌正文、Sitemap、404/noindex 和匿名后台；每五分钟检查数据库 `quick_check`、CPU、内存和磁盘。第 26 分钟实测 Auth 约 89 MiB、Web 约 21 MiB，空闲磁盘约 21 GB。第二轮未触发回滚；第一轮发生并已记录自动恢复旧版。发布状态与完整日志在 `/opt/autolink-release-state/seo-20261012-attempt2/`。

后续单独处理首页手机 LCP/TBT；继续审核尚未合格的英文车型与 43 个未开放索引的英文品牌，再按真实本地化质量开放其他语言。跟踪 Search Console 的实际索引、英文车型曝光和自然点击，并以有效注册和询盘衡量采购效果。不得把目录页数或 Sitemap 数量当成采购线索、Google 收录或排名。
