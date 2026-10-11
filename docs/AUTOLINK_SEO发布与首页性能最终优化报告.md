# AUTOLINK SEO 发布与首页性能最终优化报告

**日期：**2026-10-12（Asia/Bangkok）
**状态：**隔离开发与测试完成后提交草稿候选；未合并 `main`、未部署生产、未向 Google 提交 Sitemap 或索引请求。

## 1. SEO 独立发布结论

SEO 已形成可单独审批的[草稿 PR #6](https://github.com/wuoo6327-dot/autolink-platform/pull/6)，基线为生产安全候选 `a38664f`；PR #4 的提交 `8205d5a` 已在祖先历史中，故不应再单独重复应用 PR #4 或 #5。固定发布锁为 `docs/SEO_RELEASE_LOCK_20261012.json`，发布与回滚步骤在 `SEO_RELEASE_RUNBOOK_20261012.md`。这表示**隔离候选达到提交审批的条件**，不表示已经正式上线或被 Google 收录。

2026-10-11 18:21:57 UTC 再次从生产公开 API 核对：**244 个车型、53 个品牌**的 ID 与公开字段均与候选目录一致；244 份车型来源及图片哈希核对通过，未用历史 234 车型集合。当前技术索引资格为 **199 个车型 URL**（中文 177、英文 22），品牌 URL 为 0；其余可访问但按现有资料、年份、翻译审核规则 `noindex`。共有 2,673 个九语言详情 URL，2,474 个暂缓索引。公开车源审核通过数量为 0，候选不会虚构现货、供应商、FOB 价格或厂家授权。

候选保留服务端车型 HTML、正确的 404、robots 精确公开规则、Sitemap、Canonical、hreflang、`x-default` 和 HTML 语言标记。内容审核或目录变动会动态重算索引资格；英文待审核页不因模板生成而开放索引。车型图、配置、年份与源数据保持绑定。已批准的 22 个英文重点车型及 3 个年份冲突排除项详见上一轮报告；本次重新校验了当前所有 244 份来源与图片，未凭旧清单强制发布。

### 生产副本预发布与回滚

在阿里云 Ubuntu 24.04 `linux/amd64` 隔离环境，先只读复制**当前生产公开站点**，再运行 `scripts/build_seo_release_site.py` 只覆盖 254 个 SEO 文件；其他 **5,167** 个生产文件逐一比较 SHA-256 相同。`release-public/overlay-manifest.json` 固定覆盖清单。独立网络、独立测试库、`127.0.0.1:18083` 和只读容器执行候选 → 原生产镜像 → 候选三阶段演练，退出码为 0：

| 阶段 | 车型 | 品牌 | 额外历史车型/品牌 | Sitemap 车型 URL | 私有后台匿名访问 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 候选 | 244 | 53 | 0 / 0 | 199 | 401 |
| 回滚 | 244 | 53 | 0 / 0 | 原版不计算 | 401 |
| 恢复 | 244 | 53 | 0 / 0 | 199 | 401 |

旧 auth 镜像有历史目录种子，回滚时必须把**经核验的当前** `auth/catalog.json` 只读挂载到 `/app/catalog.json`，否则会把 26 个历史车型和 7 个品牌补入共享测试库。安全回滚已验证该挂载；正式回滚不得使用过期目录，也不得覆盖生产数据库。日志留在阿里云隔离目录 `/home/admin/autolink-seo-release-stage-20261012/amd64-seo-rollback-overlay.log`。生产 `autolink-demo-auth-1` 与 `autolink-demo-web-1` 复核时均为 healthy、UID/GID `10001:10001`、只读根文件系统、`cap_drop ALL`、`no-new-privileges`；隔离容器已清理，生产容器未替换。

## 2. 手机首页性能原因与改动

Chrome Performance trace 使用相同的 412×823 手机视口、4 倍 CPU 降速及慢 4G。原首页在每次翻译字符串与属性时重新合并两份语言字典：CPU profile 中 `ba` 自耗时 **2,715 ms**，并伴随 1,184、613、1,089 ms 的长任务。现将字典按语言与来源对象身份缓存，来源替换时重建，`ba` 自耗时降到 **3.5 ms**，最终 trace 只余一个 198 ms 长任务。九语言、导航和页面内容仍通过功能回归检查。

首屏极氪素材继续保留。手机 WebP 从 2,880×1,620、284,182 字节优化为 1,920×1,080、120,504 字节，原有构图和首页布局不变；静态资源查询版本更新，确保首访获取新文件。最终 trace 中主脚本仍约 **460 KB 传输 / 2.29 MB 解码**，约 3.75 秒才完成网络加载；首屏图请求在 4.308 秒才发出，5.935 秒收到，5.948 秒渲染为 LCP。原 trace 分别为 5.320、7.301、7.312 秒。图片加载在主应用创建首屏 DOM 后才开始，仍是 LCP 瓶颈。测试过直接 preload，三次样本反而变慢，故未采用。

当前首页仍预先载入英文与中文两份 business 语言分块，以及包含多语言和多页面逻辑的主 bundle；未发现同一分块重复网络下载，但解析和启动成本仍高。要进一步接近 2.5 秒，需要针对首页拆分或服务端提前输出真实首屏内容，并在不影响九语言及交互的前提下重新验收；本轮没有用占位内容或删功能制造高分。

### 测试环境与前后对比

本机 macOS ARM64、Google Chrome 154.0.8037.98、Lighthouse 13.5.0、同一个本地 Caddy/候选站点、同一 CLI 参数和默认 Lighthouse 手机/电脑节流。每个页面与设备均独立启动 Chrome **3 次冷测**，取中位数；前后不更换机器、视口、节流或站点 API。此为实验室同环境比较，不能外推为生产真实用户 Core Web Vitals。

| 页面 / 设备 | 分数 前→后 | LCP 前→后 | TBT 前→后 | CLS 前→后 |
| --- | ---: | ---: | ---: | ---: |
| 首页 / 手机 | 43→64 | 7,909→6,905 ms | 847.5→17.5 ms | 0.0000→0.0000 |
| 首页 / 电脑 | 78→84 | 1,772→1,597 ms | 173.5→0 ms | 0.0000→0.0000 |
| Zeekr 9X 车型详情 / 手机 | 96→97 | 2,713→2,633 ms | 0→0 ms | 0.0000→0.0000 |
| Zeekr 9X 车型详情 / 电脑 | 94→94 | 1,643→1,643 ms | 0→0 ms | 0.0000→0.0000 |
| 品牌目录 / 手机 | 94→95 | 3,084→2,864 ms | 0→0 ms | 0.0000→0.0000 |
| 品牌目录 / 电脑 | 100→100 | 645→625 ms | 0→0 ms | 0.0000→0.0000 |
| 车型目录 / 手机 | 88→88 | 3,836→3,836 ms | 0→0 ms | 0.0000→0.0000 |
| 车型目录 / 电脑 | 93→93 | 1,729→1,731 ms | 0→0 ms | 0.0000→0.0000 |
| 买家登录 / 手机 | 79→79 | 5,553→5,552 ms | 0→0 ms | 0.0000→0.0000 |
| 买家登录 / 电脑 | 99→99 | 1,042→1,042 ms | 0→0 ms | 0.0000→0.0000 |

**目标判定：**手机首页 TBT <200 ms 已达到，LCP ≤2.5 秒未达到；车型详情 CLS ≤0.1 已达到。其余页面结果只代表本机隔离实验室。买家登录页 `noindex` 是预期隐私设置，其 Lighthouse SEO 项不能用作公开车型 SEO 评分。

## 3. 功能、兼容与安全回归

- **30/30 最终冷测有效**：五类页面 × 手机/电脑 × 三次，所有 Lighthouse 进程退出码 0，`runtimeError` 为空；原始 JSON 和中位数计算脚本保留。
- **九语言与入口**：英文、中文、阿拉伯文、俄文、哈萨克文、乌兹别克文、韩文、法文、斯瓦希里文首页均有主内容、品牌与车型入口；手机语言切换、菜单、买家登录和车型目录导航通过；手机/电脑英文 H1 和核心入口数量一致。证据为 `home-interaction-qa-20261012.json`。
- **非关键脚本失败**：故意阻断 `business-seo.js` 与 `account-header.js` 后，首页仍有原 H1、品牌/车型链接与约 2,153 字正文，未出现全屏错误；正常加载为约 2,141 字。Zeekr 9X 手机 SSR 39 行参数、Geely Monjaro 英文 SSR 8 行参数、Canonical/robots 与 Googlebot UA 模拟一致。证据为 `browser-public-qa-20261012.json`。
- **Chrome 首访/复访**：未节流本地环回手机视口，PerformanceObserver LCP 140→72 ms；极氪图传输 120,804→0 字节、主脚本 460,726→300 字节（复访浏览器缓存/协商）。这与慢 4G Lighthouse 结果不直接比较，也不能代表生产首访。
- **Safari 手机视口**：在无痕窗口的响应式设计模式（iPhone 393×852、DPR 3）核对首访画面及复访刷新，极氪首屏图、H1、搜索和主要入口均可见；切至英文后 H1、搜索及车型入口仍在，手机菜单、买家登录表单和车型目录跳转通过。原始定性记录为 `safari-manual-qa-20261012.json`。未取得 Safari 可与 Chrome 对比的冷载 LCP/TBT 或 Performance trace，故不将 Chrome 分数写作 Safari 结果。

SEO 镜像原先在阿里云 AMD64 运行 221 项后端测试通过、5 项按条件跳过；包括登录、Cookie、CSRF、权限、私有资料、发布审核等。固定 Trivy 扫描：auth 的 CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN 均为 0；web 的 UNKNOWN 为 1（`GO-2026-5932`，`golang.org/x/crypto`），其余为 0。这一 UNKNOWN 仍待跟踪，不写成零风险。本次首页改动仅涉及公开静态资源和测试工具，未修改 auth、账号、会员、协议或生产数据。

Chrome 的 Googlebot Smartphone UA 模拟、普通用户与服务端初始 HTML 一致性已做隔离检查；**候选没有在生产部署，所以没有 Google Search Console 的实际实时抓取、Google 选定 Canonical、已收录量或自然流量增长证据**。上一轮只读 GSC 观察属于旧生产版本，不作为本轮候选抓取通过的证明。

## 4. Git、固定镜像及证据

| 项目 | 固定值 |
| --- | --- |
| SEO 独立候选 | `codex/seo-release-ready-20261012`，提交 `8c6e5e9`，草稿 PR #6 |
| 首页性能候选 | `codex/home-performance-release-20261012`，草稿 PR 提交中 |
| auth AMD64 本地镜像 ID | `sha256:4f828c7c39f2545a6501ce2276cdc6732a2fb8f78ba9d4623a82e16f1891ac12` |
| auth 归档及 SHA-256 | `/home/admin/autolink-global-seo-qa-20261012/auth-image.tar`；`25dabd6f3824a1a8deeca50499b14811c0f5c034500c40c6aad535e2e97e2d57` |
| web 注册表 manifest digest | `autolink-round3-caddy@sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb` |
| web 归档 SHA-256 | `19a86f94d04ee909461dfb3cc32352f83bb315356b9196fe34566e2665b366ef` |
| auth 注册表 manifest digest | 尚无；本地镜像 ID 不冒充 registry digest。跨主机部署前须推送同一归档并固定 digest。 |

本轮实际变更以两个草稿 PR 的 diff 为准。SEO 整合包括 `auth/catalog.json`、`auth/catalog_service.py`、`auth/seo_service.py`、`auth/app.py`、`Caddyfile`、`site/trade/*`、索引审核 JSON、车型图和发布/回滚工具；新增 `scripts/build_seo_release_site.py`、`scripts/verify_live_catalog_release.py`、`scripts/amd64_seo_release_rollback_qa.sh` 及发布锁。首页性能改动为 `site/assets/index-autolink-membership-apply-pricing.js`、`site/assets/home-suv-visuals.js`、`site/assets/business-page-bootstrap.mjs`、`site/index.html`、`site/images/home-mobile/zeekr9x-city-ad.webp`，并新增 trace、交互、缓存和 Lighthouse 汇总工具。

原始 Lighthouse JSON：[60 份 Lighthouse 原始 JSON 与汇总](evidence/autolink-lighthouse-20261012.tar.gz)（SHA-256 `3023e9a29484d642c22df7ade6a3f12bfa0912f081dda2fdd62ee5cd16c03e15`）以及 [Chrome trace、CPU profile 与浏览器回归原始 JSON](evidence/autolink-home-trace-and-browser-20261012.tar.gz)（SHA-256 `8158cf80bb6e972fdae2b113a62ec2341073330b0fb46b1705b44a4f51da92dd`）。后者还包含 Safari 定性核验记录；trace JSON 与 CPU profile 同存档。中位数汇总脚本为 `scripts/summarize_lighthouse_comparison.py`。原始数据保留，未改写分数。

## 5. 获批准后的部署与回滚

1. **审批前**重新读取生产目录与安全配置；若超过 244/53 或资料指纹变化，重新计算索引资格并更新锁，不照旧清单上线。核验镜像归档 SHA、web digest、auth 本地镜像 ID；如跨主机运行，先固定 auth registry digest。对当前生产 SQLite、上传及证书卷创建一致性备份并在副本恢复验证。
2. **SEO 可单独发布**：从部署当时生产公开站点只读复制并应用 254 文件白名单覆盖，按发布锁启动 auth/web，逐项核对公开 244/53 基线及新增记录、199 URL 当前审核数量、HTML 正文、404、robots、Canonical、hreflang、无审核页 `noindex`、登录与私有 API。只在另获生产上线批准后执行；首页性能候选可单独排期，不阻塞 SEO 独立审批。
3. **异常回滚**恢复原 web/site/Caddy 与安全镜像，保留最新生产数据库和上传/证书卷；旧 auth 镜像必须挂载与当时生产目录相符的当前 `catalog.json:ro`，复核车型/品牌数、私有 API 与健康，不运行 `docker compose down -v`。隔离演练不能替代生产回滚观察。
4. **Google 验收**在另获正式部署批准后，用 Search Console 对代表性的中英车型、`noindex` 车型与品牌页执行真实实时 URL 检查；提交 Sitemap 或请求索引还需单独授权。按已索引车型、关键词曝光、点击、自然搜索注册和有效询盘分别统计，访问量不当作询盘。

## 6. 未解决问题

- 首页手机 LCP 仍高于 2.5 秒，首屏 DOM/图片发现依赖主 bundle；Safari 与 Chrome、首访与复访结果见功能回归记录，不将实验室数字写成生产 CWV。
- 英文索引仅 22 个合格车型；其余语言和品牌尚未通过内容审核，继续暂缓索引。
- auth 镜像尚无 registry manifest digest；web 扫描的 UNKNOWN 发现待处理。
- 尚无新版本生产 Google 实时抓取、真实收录与自然搜索转化数据。
