# AUTOLINK 全球 SEO 自动化优化与性能验收报告

**候选日期：**2026-10-12（Asia/Bangkok）  
**仓库：**`wuoo6327-dot/autolink-platform`  
**隔离开发分支：**`codex/global-seo-20261012`  
**状态：**候选代码与隔离测试；未合并、未部署、未提交生产 Sitemap 或索引请求。

## 1. 已解决的问题与边界

- 车型及品牌公开详情改为服务端直接返回真实 HTML。初始响应包含名称、已证实年份、来源介绍/配置、参数表、同品牌车型链接、询盘入口；不存在的或停用的记录返回 404。车型页不再依赖前端请求公开 API 后才能出现核心正文。
- 公开抓取所需的车型、品牌与配置 API 获得精确的 robots 允许规则；账户、企业资料、证件、报价、询盘和后台接口仍由原权限机制保护。robots 从未被当作访问控制。
- 同一服务端索引规则决定 HTML robots、Canonical、hreflang、`x-default` 与 Sitemap。可索引语言自指 Canonical；未审核语言自指 Canonical、`noindex, follow`，不假称已有译文。九语言访问功能保留。
- 车型及品牌页只展示通过现有审核门槛的公开车源；无车源明确提示。没有生成 FOB 价格、厂家授权或虚构供应商。当前公开目录中通过审核的车源数量为 **0**。
- 直接访问详情页时保留服务端正文，避免前端替换引起的桌面 CLS；车型图设置尺寸并提供经源图 SHA-256 对照的 640px WebP 手机图。首页仅加载当前语言资源，非关键脚本失败后主内容仍可显示；静态图片与字体缓存规则得到修订，现有 UI 与功能保留。

## 2. 基线、PR #4 与实际代码

基于当前生产安全候选和已有 PR #4 的 SEO 工作继续开发。PR #4 仍为草稿、未合并，其历史种子为 **234** 车型；2026-10-12 重新读取生产公开目录后为 **244** 车型、**53** 品牌。相对 PR #4 的车型集合，当前公开目录新增 36 个、旧集合中有 26 个已不在公开目录。新鲜数据库种子与隔离验收使用当日 244 条；`INSERT OR IGNORE` 不覆盖已有生产数据库的运营编辑，也没有触碰生产数据库。现有生产前端移动首页与采购指南素材已同步到候选代码。

主要代码与证据路径：

| 部分 | 修改/新增文件 |
| --- | --- |
| 服务端目录、SEO、Sitemap | `auth/catalog.json`、`auth/catalog_service.py`、`auth/seo_service.py`、`auth/trade_service.py`、`auth/app.py`、`auth/test_current_catalog_seo.py`、`auth/test_seo.py`、`auth/test_seo_quality.py`、`auth/test_trade.py` |
| 抓取与页面交付 | `Caddyfile`、`site/robots.txt`、`site/trade/app.js`、`site/index.html`、`site/assets/business-page-bootstrap.mjs`、首页语言与移动资源、`site/guide/*` |
| 英文与图片 | `site/locales/seo-model-en-reviewed.json`、`site/model-reference/*` 中新增的当日公开车型、`site/images/catalog-update-20261011/*`、`site/images/seo-heroes/*`、`scripts/build_seo_hero_images.py` |
| 验收工具与规则 | `SEO_INDEX_POLICY.md`、`scripts/amd64_isolated_qa.sh`、`scripts/amd64_scan_images.sh`、`scripts/browser_public_qa.js`、`scripts/lighthouse_public_qa.py`、`tests/fixtures/production-public-catalog-20261012.json`、`tests/fixtures/production-catalog-image-hashes-20261012.json` |

完整改动清单以候选分支相对 PR #4 的 Git diff 为准。36 张新增目录图片及 244 张手机派生图均为公开素材；图像清单保留源路径及校验值。

## 3. 目录、索引资格及暂缓原因

隔离快照中有 **244 车型 × 9 语言 + 53 品牌 × 9 语言 = 2,673** 个可访问详情 URL。达到本候选技术索引门槛的车型 URL 为 **199**（英文 **22**、中文 **177**）；品牌 URL 为 **0**。其余 **2,474** 个详情 URL 可访问但暂缓索引。这些数字不是 Google 已收录量，也不能直接外推到上线时可能已变化的生产数据库。

| 暂缓组 | URL 数 | 原因 |
| --- | ---: | --- |
| 其他车型英文页 | 222 | 未完成逐车型英语内容审核，或车型资料本身不合格 |
| 其他车型中文页 | 67 | 29 个缺有效年份/资料待审，35 个仍为配置参考状态，3 个目录 2026 年与来源仅证实的 2025 年不一致 |
| 车型其余七语言 | 1,708 | 可靠本地化与逐页审核未完成 |
| 品牌九语言 | 477 | 稳定公开页和车型列表已存在，但品牌介绍/语言内容尚未通过索引审核 |

年份冲突的三个车型为 `byd-song-plus-2026`、`byd-sealion-7-2026`、`gac-gs8-2026`。页面显示来源证实的 2025 年并保留 `noindex`；不得以目录 2026 标签宣传来源没有证实的配置。内容、发布状态、参考文件或审核指纹变化时，服务端重新计算资格并从 Sitemap 移除失格页。

## 4. 首批 22 个英文重点车型

下列英文页有独立车型描述、来源绑定的配置版本、准确数值与单位；选定配置不被泛化为整个车系，也不代表可出口库存：

| 品牌 | 车型及公开 URL |
| --- | --- |
| Geely | [Monjaro / Xingyue L](https://autolinkglobal.com/trade/models/geely-monjaro-2026)、[Boyue L](https://autolinkglobal.com/trade/models/geely-catalog-2) |
| Galaxy | [E5](https://autolinkglobal.com/trade/models/galaxy-catalog-1)、[L7](https://autolinkglobal.com/trade/models/galaxy-catalog-4)、[M9](https://autolinkglobal.com/trade/models/geely-galaxy-m9-2026) |
| Zeekr | [001](https://autolinkglobal.com/trade/models/zeekr-catalog-1)、[007](https://autolinkglobal.com/trade/models/zeekr-catalog-2)、[7X](https://autolinkglobal.com/trade/models/zeekr-7x-2026)、[9X](https://autolinkglobal.com/trade/models/zeekr-9x-2026) |
| BYD | [Han](https://autolinkglobal.com/trade/models/byd-han-2026)、[Yuan PLUS / ATTO 3](https://autolinkglobal.com/trade/models/byd-catalog-5) |
| Denza | [D9](https://autolinkglobal.com/trade/models/denza-d9-2026)、[N7](https://autolinkglobal.com/trade/models/denza-catalog-2) |
| Changan | [CS75 PLUS](https://autolinkglobal.com/trade/models/changan-catalog-1)、[CS55 PLUS](https://autolinkglobal.com/trade/models/changan-catalog-2) |
| Deepal | [S05](https://autolinkglobal.com/trade/models/deepal-catalog-1)、[S07](https://autolinkglobal.com/trade/models/deepal-s07-2026)、[G318](https://autolinkglobal.com/trade/models/deepal-catalog-3) |
| GAC Trumpchi | [M8](https://autolinkglobal.com/trade/models/trumpchi-m8-ice-2026) |
| 中国生产 Volkswagen | [FAW-VW Golf](https://autolinkglobal.com/trade/models/faw-volkswagen-catalog-3)、[SAIC-VW Passat](https://autolinkglobal.com/trade/models/saic-volkswagen-catalog-2)、[SAIC-VW Tiguan L](https://autolinkglobal.com/trade/models/saic-volkswagen-catalog-3) |

表中 URL 是候选上线后的目标地址；截至本报告时，线上仍运行旧版本，不能将这些链接视为已部署的英文页。另有 BYD Song PLUS、BYD Sealion 7、GAC GS8 三个英文草稿因上述年份冲突未获索引资格。术语检查限定每个已批准页面使用选定配置里的数值、单位及受控的动力术语；带中文或无法证实的英译不能通过审核门槛。

## 5. 手机与电脑性能前后对比

使用同一 Lighthouse/Chrome、相同视口与节流配置，各页面各设备冷启动 **3 次取中位数**。生产基线为线上 HTTPS；候选为本机 Caddy + 隔离公开快照 HTTP。网络与部署环境不同，因此这些是**实验室对比**，不是正式上线后的真实用户性能提升或 Core Web Vitals 结论。

| 页面/设备 | 生产分数 | 候选分数 | 生产 LCP | 候选 LCP | 生产 TBT | 候选 TBT | 生产 CLS | 候选 CLS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 首页·手机 | 38 | 42 | 9,318 ms | 7,933 ms | 1,031 ms | 894 ms | ≈0 | ≈0 |
| 首页·电脑 | 75 | 76 | 1,523 ms | 1,787 ms | 234 ms | 194 ms | ≈0 | ≈0 |
| Zeekr 9X·手机 | 74 | 97 | 7,561 ms | 2,633 ms | 0 ms | 0 ms | 0.001 | 0 |
| Zeekr 9X·电脑 | 72 | 94 | 1,352 ms | 1,643 ms | 0 ms | 0 ms | 0.980 | 0 |

首页手机候选仍有 **7.9 秒 LCP**，尚不算快；电脑端 LCP 在实验室反而增加约 264 ms。首个手机首页样本的传输量由约 1.78 MB 降至 1.29 MB（约少 27%）。移除未经验证有益的图片 preload 后，首页三次手机中位数比保留 preload 时更好。车型详情改善主要来自服务端正文、稳定布局与实际手机图，正式上线后仍需同网络重新测量。

## 6. Google Search Console 真实状态

已有授权的 **只读** Google Search Console 数据（基线审查时读取）：索引报告 2026-10-04 更新，已索引 **1** 页（首页）、未索引 **1** 页（`Page with redirect`）；已提交 Sitemap **0**；2026-10-03 至 10-09 Web 搜索 **56** 次曝光、**1** 次点击。可见查询尚不能证明车型关键词已有曝光；手机和电脑 Core Web Vitals 均无足够真实数据。基线 Zeekr 9X 的 Google Inspection Tool 手机在线测试发现页面 `noindex`、公开资源被 robots 阻挡、渲染正文不是车型资料。该在线测试针对**仍在生产运行的旧版**。

本候选通过浏览器普通用户与 Googlebot Smartphone **模拟 UA** 的初始 HTML 一致性检查；这只能证明服务端响应与本地浏览器行为。候选尚未部署，故**没有**候选版本的真实 Google 实时抓取、Google 选定 Canonical、收录或排名证据。只有另获生产上线授权并完成部署，才能执行实时 URL 检查、提交 Sitemap 或请求索引。

## 7. 完整测试与安全验收

| 范围 | 结果 |
| --- | --- |
| 全部当前车型及品牌页 | 244 车型、53 品牌的九语言共 2,673 次服务端页面检查；索引资格/Sitemap 199 URL，无重复，未知或停用 404 |
| 本机后端与安全权限回归 | 221 项通过，5 项按原条件跳过；包含账户/角色、Cookie、CSRF、发布审核、私有字段、报价与不公开车源测试 |
| 本机真实浏览器 | 首页非关键脚本失败仍渲染；手机 WebP 命中；英/中 SSR 正文、Canonical、robots 与 Googlebot UA 模拟一致，检查通过 |
| Caddy 与公开 HTTP | Caddy 配置校验通过；公开目录、详情、robots、Sitemap、指南正常，未知详情 404、后台未认证 401；AMD64 隔离结果见下文 |
| 英文内容 | 22 页来源指纹、选定配置、数值与单位一致性检查通过；3 页年份不一致被拒绝索引 |
| Lighthouse | 线上基线与候选每类每设备 3 次，原始 JSON 保存在本地 `tests/results/`；表中为中位数 |
| Docker 镜像漏洞扫描 | 固定 Trivy 镜像、完整不抑制的 UNKNOWN/LOW/MEDIUM/HIGH/CRITICAL 扫描完成；认证镜像五级均为 0，Web 镜像 UNKNOWN 1、其余级别 0 |

隔离 AMD64 主机为阿里云 Ubuntu 24.04 `x86_64`，候选目录 `/home/admin/autolink-global-seo-qa-20261012`。测试用独立网络、独立 127.0.0.1 端口、公开快照 SQLite、只读容器与单独数据目录；没有挂载生产数据库或变更生产容器。最终镜像在该主机运行 **221 项后端测试通过、5 项跳过，耗时 152.109 秒**；隔离 HTTP 验收退出码 0，确认 244 车型、53 品牌、199 个 Sitemap 车型 URL、未知车型 404、后台未认证 401、公开指南 200。启动就绪轮询遇到一次连接重置，随后的健康与全部断言成功。生产 auth/web 容器在检查时仍正常运行。隔离机器的构建、后端、HTTP 与镜像扫描日志在该目录保留。部分原有测试跳过属于运行条件；不得写成全部执行。

扫描对象为最终 auth 镜像归档与现有固定 Caddy 镜像归档，使用 `aquasec/trivy@sha256:9db099105405c648166e6b94155eb32f8da12673cf1f455207f7385cc9a77283`，不挂 Docker socket，未配置漏洞忽略。认证镜像 **CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN = 0/0/0/0/0**；Web 镜像 **0/0/0/0/1**。唯一遗留为 `GO-2026-5932`（`golang.org/x/crypto`，扫描器评为 UNKNOWN）；正式上线前应继续跟进其评级或固定 Web 镜像的更新，不把 UNKNOWN 写成零风险。

## 8. 新车型自动 SEO 机制

运营新增或更新车型仍按现有发布流程写数据库。服务端读取当前有效品牌、车型及参考配置，在每次请求计算资料完整度、发布状态、年份一致性与英语审核指纹，产生正文和索引规则；Sitemap 同源重算。尚未完成资料或翻译审核的车型仍可供买家查看，但不会因目录中出现、模板生成或某品牌有页面就被加入索引。停用车型返回 404。后续新增车型如需英文索引，应补充可核对来源的独立文案、配置译名与数值，核对市场与年份，完成审核并锁定来源指纹；来源变化会撤销旧审核。

## 9. Git、固定镜像与 PR

候选代码提交：`bc0649a`（主 SEO/目录）、`63abd25`（AMD64 HTTP 验收）、`2151831`（固定扫描器）、`128abd5`（244 车型新鲜种子与年份审核）。最终文档与镜像锁定清单见 `docs/SEO_RELEASE_LOCK_20261012.json`。阿里云本机构建认证镜像 `autolink-global-seo-auth:128abd5` 的不可变**本地镜像 ID**为 `sha256:4f828c7c39f2545a6501ce2276cdc6732a2fb8f78ba9d4623a82e16f1891ac12`；这不是尚未推送的注册表 manifest digest。隔离 Web 测试使用现有固定 `autolink-round3-caddy@sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`。上线前如需跨主机拉取 auth 镜像，须先发布到受控仓库并记录其 registry digest，再对完全相同镜像复核。PR 以 PR #4 为基底创建**草稿**，不自动合并 main。

## 10. 部署、回滚与 Search Console 操作方案

**当前只提供操作方案，不执行生产变更。** 获得单独批准后，先确认 PR #4 与当前生产安全提交的最终合并顺序，固定镜像 digest，备份并核对数据库，使用预发布配置验证 244 车型及新增加的真实记录仍存在。先将新版本部署到生产，立即检查代表性中英车型页的原始 HTML、HTTP 状态、robots、Canonical、hreflang、图片、权限与首页脚本失败恢复，再重跑线上手机/电脑 Lighthouse。异常时回滚到当前生产固定镜像和 Caddy 配置；数据库采用向后兼容迁移，不用历史 234 条种子覆盖现有数据。

生产通过后再在已授权 Search Console 用 URL Inspection 的**实时测试**检查至少 Geely Monjaro、Zeekr 9X、一个暂无公开车源车型、一个 `noindex` 年份冲突车型及一个品牌页，记录 Google 实际正文、资源、可索引性和 Google 选定 Canonical。另获 Sitemap/索引请求授权后才提交 `/sitemap.xml` 或请求代表 URL 索引。持续分别跟踪已索引车型数、车型查询曝光、自然搜索点击、自然进入详情的会话、自然搜索注册与有效询盘；访问量不可当作采购询盘。

## 11. 验收结论

候选实现了当前目录驱动的真实 HTML、受控英文索引、九语言访问、公开/私有边界及隔离性能修复。**生产抓取结果、真实 CWV 和自然搜索转化尚未产生。** 全部隔离测试完成后停在草稿 PR，等待生产上线批准。
