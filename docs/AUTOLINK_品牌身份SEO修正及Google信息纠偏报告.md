# AUTOLINK 品牌身份 SEO 修正及 Google 信息纠偏报告

**发布状态：已上线，存在待验证事项。** 品牌身份页面和元数据已在生产生效，核心 HTTP、目录和权限探针通过。Google Search Console 接收了网站地图提交，但其处理表仍显示 `Couldn't fetch`；Google 首页手机实时渲染还出现一项旧首页脚本资源加载异常。这两项不能写成已经解决。时间均为 UTC，除非另有说明。

## 1. 范围、基线与代码

- 以 2026-10-12 已运行的 SEO 安全生产版本 `/opt/autolink-releases/5725b8b-seo-20261012` 为基线，叠加品牌身份修正。生产数据库没有被覆盖或迁移，首页现有 UI、车型资料、商家入驻、会员收费、支付及法律协议没有改动。
- 发布代码提交为 `d996b6907c82ac21ee1baf1c09ba93f770a18694`；候选位于[草稿 PR #10](https://github.com/wuoo6327-dot/autolink-platform/pull/10)，基于既有 SEO 发布分支，未合并 `main`。生产发布目录为 `/opt/autolink-releases/d996b69-brand-20261012`。
- 实际网站变更为 `site/index.html`、`site/assets/business-seo.js`、新增 `site/about.html`、`Caddyfile` 及 `auth/trade_service.py` 中的静态 Sitemap 项。与上一生产站点比较，站点文件只变化 `index.html`、`assets/business-seo.js`、`about.html` 三项；其他 5,422 个站点文件的哈希未变。其余提交文件是测试和带状态、自动回滚的发布脚本。

## 2. 首页品牌信息：修改前后

| 项目 | 修改前生产值 | 修改后生产值 |
| --- | --- | --- |
| 英文 Title | `AUTOLINK — Source China. Drive Global.` | `AUTOLINK \| Chinese Vehicle Sourcing & B2B Supplier Platform` |
| Meta Description | `Source Chinese vehicles for the Middle East, Central Asia, East Asia and Africa. AUTOLINK connects international vehicle buyers with Chinese automotive suppliers.` | `AUTOLINK connects international vehicle buyers with Chinese automotive suppliers. Explore vehicle specifications, browse approved supplier listings, and submit sourcing inquiries.` |
| Canonical | `https://autolinkglobal.com/` | `https://autolinkglobal.com/` |
| 首页底部入口 | 无独立 About 链接 | 可见的 `About AUTOLINK` 链接，目标 `/about` |

新元数据直接出现在服务器初始 HTML。公网检查首页为 HTTPS 200、`index, follow`、唯一 Canonical、唯一身份 JSON-LD；英语页面完整加载后的浏览器标题也为新标题。已有中文界面可继续访问，车型和品牌 SEO 的 Title、Canonical、hreflang、404/noindex 规则保持原有审核机制。

## 3. Organization、WebSite 与 About

- 首页仅有一个 `application/ld+json` 图，包含 `Organization`（`https://autolinkglobal.com/#organization`）和 `WebSite`（`https://autolinkglobal.com/#website`）。名称为 AUTOLINK；`Organization.description` 明确写为中国供应商与国际买家连接的 B2B 车辆采购信息平台；Logo 使用实际可访问的本站 `/favicon.svg`；联系入口指向已公开 `/support`。`WebSite.publisher` 引用该 Organization，站内搜索动作指向既有车型/车源搜索入口。
- 未填写尚未经核实的 `legalName`、公司注册地址、社交账号 `sameAs`；没有把 `autolinkua.com` 认作本站或官方关联域名；没有增加 ShippingService、DeliveryService、物流担保或虚构 Offer。
- 新页面 [About AUTOLINK](https://autolinkglobal.com/about) 为独立英文 HTML，初始响应已有完整 H1、业务范围、交易边界和四项 FAQ。它说明平台展示车型和经审核供应信息、支持采购询盘及会员信息服务，同时明确平台不直接销售车型参考中的车辆、不代收车款或定金、不托管交易资金、不直接办理国际运输或报关、也不担保第三方交易。车型资料不等于现货，最终条件由交易双方或独立服务商确认。
- `/about` 返回 200、Canonical 指向自身、允许索引；`/about.html` 以 308 指向 `/about`。英文静态 Sitemap 只收录一次 `/about`。Google 手机渲染的 About 页面可见完整正文，普通浏览器的桌面和 390px 手机视口检查也能读取导航、正文与 FAQ。

## 4. 错误物流描述排查

检查了首页公开文案、About、元数据、JSON-LD、页脚、车型/品牌详情、英语采购指南、会员说明与既有条款中有关 `shipping`、`logistics`、`customs clearance`、`Ro-Ro`、`freight forwarding` 等词的上下文。既有法律条款将运输、报关归于交易当事人或第三方；采购指南讨论贸易条件，不构成 AUTOLINK 自营运输承诺。首页原有英文主文案是采购平台表述，没有发现需要删除的直接自营物流承诺。本轮补充了首页品牌识别信息和 About 的正面解释与明确边界；没有机械删去贸易知识中的运输术语，也没有改动车型参数、库存或报价。

Google 搜索 `byd han china export autolink` 的 AI Mode 与 AI Overview 曾将 AUTOLINK 描述成滚装、铁路、海运和报关服务商，并出现另一域名 `autolinkua.com`。已通过两处页面的“不准确”反馈入口提交纠正说明；页面显示 “Thanks for letting us know”。这只证明反馈被界面接收，**不证明 Google 已更正 AI 回答**。两个域名的服务来源不能混为一谈，AI 误述的具体成因尚未证实。

## 5. 安全、数据与发布证据

- 生产 SQLite 为 **270 条车型、60 条品牌数据库记录**，公开目录为 **244 个车型、53 个品牌**。二者含义不同；切换前后公开目录和实际数据库计数一致。旧有 50 个可索引英文车型、177 个中文车型及 10 个英文品牌的审核规则未放宽。
- Linux/AMD64 隔离环境完成 227 项后端和权限测试（222 通过、5 跳过），并检查全部 244 个公开车型和 53 个公开品牌、站点路由及回滚演练。Gitleaks 未发现泄露；准确发布的 Auth 镜像归档用 Trivy 0.75.0 扫描 HIGH/CRITICAL 为 0；[PR #10](https://github.com/wuoo6327-dot/autolink-platform/pull/10) 的两个 `source-security` GitHub Actions 均实际运行且通过。上述安全扫描范围不表示所有潜在漏洞均不存在。
- 发布前新鲜完整备份清单：`/opt/autolink-backups/brand-identity-20261012/final-20261012T102517Z/release-backup-manifest.json`；真实 SQLite 源由运行中的 Auth `/data` 挂载识别，快照文件 `autolink-auth-20261012T102517Z.sqlite3`，SHA-256 `ec04bd0080d99adc7e2faac841aa986b4132da42981c2af4fac74811b39e8317`。SQLite 一致性检查、隔离复制恢复和哈希校验通过；用户上传、Caddy 证书/配置、旧源码与运行配置、旧 Auth/Web 镜像都已归档并逐项隔离恢复验证。备份目录为私有目录，不提交公开仓库。
- 新 Auth 固定 Docker Image ID 为 `sha256:742d1f3e28b9f9adca7159f3f2c22afb4b540dd25900e7bf36186be05ee217cb`，完整归档 SHA-256 为 `62de1e19426ab58c45aed39a4bf89ee9a84ad8936926dfddceeb9376cf929bd0`；Web 固定 Image ID 为 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`。新镜像为 `linux/amd64`，加载后的 Image ID 与发布锁一致。这里的本地 Image ID / OCI 摘要**不是远程 Registry Manifest Digest**；此同主机发布按不可变归档和固定 Image ID 交付，没有部署时重建或自动拉取。
- 服务器端 tmux 执行有状态发布，先切 Auth 且确认健康，再切 Web 并等待 HTTPS；切换超时或持续探针失败会自动恢复旧版本，同时保留最新数据库和上传卷。核心页面在 `2026-10-12 10:27:40 UTC` 验证通过。该轮没有执行数据库迁移、`down -v`、删除卷或强推 `main`。

## 6. 生产功能与 Google 验收

- 公网抽查：首页、About、Geely Monjaro 英文车型、Geely 英文品牌、robots、根和静态 Sitemap 均返回 200；不存在车型返回 404，未审核车型仍为 `noindex, follow`，匿名管理员接口返回 401，买家登录与商家/管理员入口可达。车型/品牌 SSR 仍包含真实名称、介绍和已审核参数；私有接口没有因 robots 调整而公开。
- Google Search Console 对首页和 About 做了真实 **URL Inspection Live Test**。两页均显示 “URL is available to Google”、“Page can be indexed”，HTTP 200；Google 抓取的首页 HTML 含新标题、描述、Canonical 和唯一身份 JSON-LD，About 抓取的 HTML 含完整业务边界及 FAQ。首页和 About 的重新索引请求均收到 “Indexing requested” 回执；这不是已收录证明。
- 新建浏览器访问英语首页并完成加载后，Title、Description 和 Canonical 保持新值；既有九语言切换入口和页面正文可用。不过，浏览器内不刷新页面地在中文与英文之间切换时，观察到 DOM 的 `lang` 已变化而 Title/Canonical 一度保留上一个语言状态。直接刷新英语 URL 后恢复正确英语值，Google 的英语 Live Test 也读取到正确初始元数据。这是现有客户端语言切换与 SEO 元数据同步的剩余缺陷，不能记作九语言动态元数据全部通过；修复需单独验证，不在本次已锁定镜像和站点文件上热改。
- About 的 Google 手机渲染截图显示正文。首页的 Google 手机渲染截图则显示 “Unable to load. Please reload.”，但静态品牌说明和 About 链接仍可见；资源详情有一项约 2.29 MB 的既有首页脚本 `index-autolink-membership-apply-pricing.js` 报 “Other error”，以及私有 `/autolink/me` 因 robots 拦截（后者符合私有访问要求）。该旧脚本公网直接请求为 200，Google 渲染失败的根因仍需单独定位，不应把其归咎于本次三处站点文件改动，也不能宣称首页完整渲染通过。
- 根 [Sitemap](https://autolinkglobal.com/sitemap.xml) 及五个子 Sitemap 由公网可正常读取并解析；复查时静态子地图 65 条 URL（含新 About）、品牌 10 条、车型 227 条，供应商和公开车源子地图当前各 0 条。本次在 Search Console 提交根 Sitemap 后显示 “Sitemap submitted successfully”。然而刷新后的提交记录仍为 **Type `Unknown`、`Couldn't fetch`、发现页面 0、Last read 空白**。需要等待 Google 后台处理并调查持续失败的真实抓取原因；不能将表单接收视为地图读取或 URL 收录。
- 运行证据截图、Trivy JSON 和公网 HTTP JSON 留在本机 `release-evidence/brand-identity/`，不上传到公开仓库。真实 Google Live Test 截图包括 `gsc-home-live-html.png`、`gsc-home-live-render.png`、`gsc-about-live-html-boundary.png`、`gsc-about-live-render.png`，网站地图提交截图为 `gsc-sitemap-submitted.png`。

## 7. 持续监控、回滚与未解决问题

服务器端连续监控于 **2026-10-12 10:58:35 UTC** 结束，状态文件为 `completed`。完整日志有 **32 次 `CORE_PROBE_OK`、0 次 `rolling_back`、1 次 `completed`**；监控中记录的关键探针失败数均为 0。最终 Auth/Web 容器都是 `running`、`healthy`、重启次数 0，Image ID 与发布锁一致；抽查 CPU 均低于 0.1%，Auth 约 86.7 MiB、Web 约 24.3 MiB，根分区仍有约 19 GiB 可用。切换后至完成超过 30 分钟，本轮未发生回滚。10:59:38 UTC 再从公网抽查首页、About、车型、品牌、robots、Sitemap、404、noindex 和匿名后台 401，九项均符合预期，原始结果在本机 `release-evidence/brand-identity/public-final-20261012.json`。

状态与完整日志位于 `/opt/autolink-release-state/brand-identity-20261012/d996b69-brand-20261012/`。发布脚本按分钟检查固定镜像、容器健康、HTTPS、244/53 公开目录、车型/品牌正文、About、Sitemap、404/noindex 与匿名权限，并定期检查 SQLite 和可用磁盘；连续关键失败会触发自动回滚。回滚使用已归档旧 Auth 镜像和旧发布目录，先 Auth 后 Web，保留现有数据库及上传数据。

仍需单独处理：Search Console 的 Sitemap `Couldn't fetch`；Google 手机首页旧脚本加载失败的原因；首页不刷新时切换语言后的 Title/Canonical 同步；AI Overview 与 AI Mode 是否采用纠正信息，以及实际搜索标题、摘要与收录变化。此前独立公网 Lighthouse 测试的首页手机中位数为 Performance 28、LCP 8,111 ms、TBT 2,631 ms，尚未达目标；本轮未调整重型首页性能代码，也未重跑可比较的 Lighthouse，不声称性能改善。品牌身份修正不能保证 Google AI 立即更正或带来排名和流量增长。
