# AUTOLINK Sitemap 与首页 JavaScript 性能最终优化报告

> 记录时间：2026-10-12（UTC）。最终状态：**已上线，存在待验证事项**。生产代码与 30 分钟监控通过；Google Search Console 的 Sitemap 后台仍显示 `Couldn't fetch`，不能宣称该项已修复。

## 1. 结论与范围

本轮最终候选代码为 `40d685b726b762a12a292045ebbd975a6803ea0d`，GitHub [PR #12](https://github.com/wuoo6327-dot/autolink-platform/pull/12)，基于第十一轮分支。生产切换前读取到的实际运行目录是 `/opt/autolink-releases/52c6934-round11-20261012`；本轮没有使用旧车型种子覆盖生产数据。镜像固定归档、隔离验收和上线状态见第 8—10 节。

本轮仅改变静态 Sitemap 的索引资格、首页语言词典热路径和首屏资源交付；车型、品牌正文与已有审核状态保持原样。没有改会员收费、供应商规则、支付或客户数据。

## 2. Sitemap 调查与修复

Search Console 域名资源 `sc-domain:autolinkglobal.com` 在切换前将根 `https://autolinkglobal.com/sitemap.xml` 显示为 `Couldn't fetch`／`Sitemap could not be read`，发现网址数 0，未给出更细的失败原因。真实 Google URL Inspection 的实时抓取曾成功读取根 XML，但这不能证明 Sitemap 后台处理成功。

公网审计读取了根索引及全部三个子地图，合计 295 个唯一 URL：静态 58、英文品牌 10、车型 227。根与子地图均返回 HTTP 200 和 XML Content-Type；295 个 URL 的页面、索引标记和 Canonical 被逐一检查。发现 18 个静态条目属于 `/membership` 与 `/support` 的九语言客户端壳页面，其 Canonical 与条目 URL 不一致；其中 16 个非英文页面的 HTML `lang` 也不一致。没有发现空子地图、重复 URL、无效车型 URL 或批量 HTTP 错误。HTTP/1.1 与 HTTP/2、IPv4、TLS、gzip 均能正常取得 XML；当前域名未公布 AAAA 记录。服务器日志只保留 Caddy 内部代理地址，无法据此验证某条请求的 Googlebot 来源。

候选版为 `/membership`、`/support` 增加响应头 `X-Robots-Tag: noindex, follow`，并从静态 Sitemap 排除其 18 个多语言壳页面。候选根地图仍只列 `static-1.xml`、`brands-1.xml`、`models-1.xml` 三个非空子地图；静态条目降至 40 个，总计 277 个唯一 URL。车型 227 条（英语 50、中文 177）、英语品牌 10 条未改变。AMD64 隔离及正式公网审计 277 个 URL 的结构与页面规则，结果均为 `issues={}`、`structureIssues=[]`。上述问题值得修复，但不能断言它就是 Google 后台 `Couldn't fetch` 的唯一原因；最终判断要看 Search Console 重新处理后的真实状态。

## 3. 首页 JavaScript 依赖及实际改动

生产主脚本 `index-autolink-membership-apply-pricing.js` 解码体积 2,289,575 B，候选版为 2,290,007 B。它是编译后的 React／路由／首页交互／会员页面共享脚本，没有可信 source map 可把每个内部模块按字节精确归属。本轮没有把整段会员业务代码从编译产物中冒险抽离。

Performance trace 定位的关键瓶颈是该脚本中的翻译词典搜索函数 `ba`：生产版单次中文首页跟踪中，其 self time 为 2,062.7 ms，形成约 1,184 ms、1,136 ms 两个长任务。实际页面还从它动态加载了 `business-resources.js` 全九语言字典（2,801,007 B 解码，516,327 B 传输），同时按需加载英语与中文语言块。生产首页对主脚本使用不同查询版本的 preload 与实际 script URL，导致同一 2.29 MB 主脚本在首访中下载两次。

候选版仅对经过原生产文件 SHA256 校验的编译脚本执行可复现的窄范围补丁：删除首页热路径对完整九语言字典的导入，使用当前语言块并缓存小写键索引；九语言界面仍保留。九个首页 HTML 的主脚本 preload 与执行 URL 统一为同一版本；手机版极氪图像 URL 一致；桌面首屏使用同一极氪素材生成的 188,736 B WebP 与对应 preload。主脚本仍约 2.29 MB；本轮真正减少的是多余的 2.8 MB 字典解析和重复请求。生产与候选脚本对照的精确转换验证已通过。

首次切换的覆盖清单遗漏了 `business-page-bootstrap.mjs`：真实生产仍按旧查询版本执行主脚本，因而重复下载；浏览器完整交互出现较晚，而早期 Lighthouse 低 TBT 无法代表完整体验。该次发布在第 6 分钟主动触发已验证的自动回滚，UTC 14:47:07 恢复第十一轮安全版本。最终提交将启动器加入不可变覆盖清单，把九个首页对启动器的 URL 更新为新版本，并给隔离探针及浏览器测试增加运行时版本和单次加载断言。第二次公网浏览器验证中，手机和电脑各只记录到一次 `?v=20261012-home-fast` 主脚本请求，登录和车型入口正常。

在相同本地 Caddy、同一 Chrome 与网络模拟下，首访 JS 条目从 18 减至 16、JS 传输总量从 1,644,612 B 减至 668,512 B、解码总量从 8,145,949 B 减至 3,055,799 B。候选中文 trace 中词典搜索函数 self time 降至约 5.5 ms，最长长任务约 160 ms；这组 trace 是瓶颈定位证据，不代替三次 Lighthouse 中位数。

## 4. 可比较的隔离 Lighthouse 结果

下表取同一机器、同一本地 Caddy 与 Lighthouse 设置各三次冷启动的中位数。基线加载**真实生产主脚本**和第十一轮首页；候选加载最终第十二轮固定文件。原始 JSON 位于本地 `tests/results/round12/lighthouse-local-production-bundle-before/`、`lighthouse-local-candidate-v4/`；trace JSON 位于同一目录下 `trace-local-*`。

| 页面 | 版本 | Performance | LCP | TBT | CLS |
|---|---|---:|---:|---:|---:|
| 中文首页，手机 | 生产文件基线 | 42 | 8,598 ms | 794 ms | 0.0018 |
| 中文首页，手机 | 最终候选 | 68 | 5,856 ms | 15 ms | <0.001 |
| 英文首页，手机 | 生产文件基线 | 49 | 6,007 ms | 798 ms | 0.0018 |
| 英文首页，手机 | 最终候选 | 69 | 5,866 ms | 18 ms | 0.0018 |
| 中文首页，电脑 | 生产文件基线 | 71 | 2,404 ms | 171 ms | 0.070 |
| 中文首页，电脑 | 最终候选 | 87 | 1,207 ms | 0 ms | 0.062 |
| 英文首页，电脑 | 生产文件基线 | 71 | 2,444 ms | 166 ms | 0.070 |
| 英文首页，电脑 | 最终候选 | 87 | 1,567 ms | 0 ms | 0.070 |

中文手机 TBT 与电脑 LCP 达到本轮努力目标。英文手机 LCP 中位数为 5,866 ms，仍未达 2.5 秒；基线三次为 6,007、8,600、6,005 ms，波动较大，因此不能用这个小样本推断真实用户的整体 LCP。不同环境数据不与下表混算。

公网正式地址在切换前后使用同一台测试机、同一 Lighthouse 配置各做三次冷启动；下表只对两组都测试过的中文首页作直接比较。原始 18 份 JSON 保存在 `tests/results/round12/lighthouse-public-before/` 和 `lighthouse-public-v2-after-clean/`。

| 公网中文首页 | Performance 中位数 | LCP 中位数 | TBT 中位数 | CLS 中位数 |
|---|---:|---:|---:|---:|
| 手机，切换前 | 31 | 9,197 ms | 2,362 ms | <0.001 |
| 手机，最终切换后 | 91 | 1,894 ms | 48 ms | <0.001 |
| 电脑，切换前 | 71 | 1,505 ms | 334 ms | 0.062 |
| 电脑，最终切换后 | 69 | 2,383 ms | 0 ms | 0.062 |

切换后英文首页单独三次冷测：手机 Performance 91、LCP 1,869 ms、TBT 36 ms、CLS 0.0018；电脑 Performance 85、LCP 1,266 ms、TBT 0 ms、CLS 0.061。公网中文电脑 LCP 较这组基线**变慢约 878 ms**，虽仍低于 2.5 秒目标，不能把本地受控环境的进步写成公网全面进步；公网三次的 LCP 为 2,383、1,776、2,817 ms，仍有明显波动。图片已从 1.15 MB JPEG 换成 189 KB WebP，LCP 波动尚不能归因于图片大小。移动设备的 Lighthouse 使用其模拟网络／CPU 设置，不能代表某个海外国家的真实用户现场测量。

部分公网 Lighthouse SEO 审计在 robots.txt 请求上报超时；单独 10 次 HTTPS 请求均返回 200，耗时 0.10—0.40 秒。英文根首页的 Lighthouse `finalDisplayedUrl` 变成 `/?lang=zh`，部分运行因而把初始英文 Canonical 判为另一个 hreflang。诊断浏览器在 `en-US` 环境中加载完成后仍是根 URL、英文正文和根 Canonical；在 `zh-CN` 环境中加载完成后则是 `/?lang=zh`、中文正文和中文 Canonical。该审计差异符合初始 HTML 与语言切换期间采样时点不同的表现，但不能仅凭此解释所有 SEO 分数波动；保留原始低分样本。

## 5. 功能、SEO 与权限回归

- 本地后端完整自动测试：227 项运行，222 项通过、5 项按原条件跳过；AMD64 容器挂载完整源码复测同样为 `Ran 227 tests ... OK (skipped=5)`。
- Playwright 首页集成检查通过九语言、阿拉伯语 RTL、Canonical／noindex、主脚本失败的静态首页回退、手机导航与登录入口。Puppeteer 最终候选检查通过九语言、手机和电脑内容链接、车型与登录导航，并断言首页主脚本只请求一次。第二次公网核心浏览器测试也通过手机、电脑、买家登录与车型目录导航以及单次加载断言。正式切换后再用公网浏览器主动阻断主脚本，390 px 和 1,440 px 视口均保留完整英文 H1、介绍、车型／品牌／About 入口，未出现全屏加载错误。
- 隔离环境使用最新生产一致性备份核对 244 个公开车型及 53 个公开品牌 SSR 页面，完成候选版→旧版→候选版的回滚演练；车型、品牌 HTML 哈希与 Sitemap URL 在演练中保持一致。无效车型返回 404；未审核车型仍 noindex；私有管理员接口仍返回 401。
- 上线后的只读业务入口抽查：`/buyer/login`、`/supplier`、`/admin` 均返回 200 并展示原登录／权限界面；`/membership` 在主脚本接管后展示原会员方案与“付款暂未开放”提示，主脚本只请求一次。未登录状态下的 401 请求属于既有权限响应。本轮未发起真实付款、询盘或修改会员规则。
- 原有一个 `browser_public_qa.js` 在 `DOMContentLoaded` 立即采样，命中了 React 接管过程的短暂文本状态，产生失败；在生产基线与候选版等待稳定状态并阻断非关键请求的针对性复测中，首页均能显示完整静态内容及车型／品牌入口。该旧脚本的采样时机需后续修订，不能把其失败算成页面永久错误。

## 6. GitHub 与安全扫描

最终候选提交 `40d685b726b762a12a292045ebbd975a6803ea0d` 位于分支 `codex/round12-sitemap-js-20261012`，PR #12 仍为开放状态，基分支是第十一轮候选。两个最新 GitHub Actions `source-security` 检查实际运行并成功（运行号 38265737425、38265744759）。未合并 `main`，未更改仓库可见性。固定 Auth 归档的 Trivy 镜像扫描结果见第 8 节。

## 7. 变更文件

代码提交涉及 `Caddyfile`、`auth/trade_service.py`、`auth/test_trade.py`、九个 `site/index*.html`、`site/assets/index-autolink-membership-apply-pricing.js`、`site/assets/business-page-bootstrap.mjs`（该文件在上一轮源码中已是正确版本，本轮把它纳入实际发布覆盖）、`site/images/zeekr9x-villa.webp`，以及候选构建、来源验证、Sitemap 审计、备份、隔离测试、性能 trace、镜像锁和自动回滚脚本。完整代码差异以 `git diff 52c6934..40d685b` 与发布覆盖清单为准；测试原始数据和生产备份没有加入 Git。

## 8. AMD64 镜像、备份与发布

第二次发布目录为 `/opt/autolink-releases/40d685b-round12-20261012`，来源 Git commit 为 `40d685b726b762a12a292045ebbd975a6803ea0d`。实际复用的 Auth Image ID 为 `sha256:3d989c05558c56eef533f15d369e1978e0f08cfb728c407f99d091efe18c15a3`，Web Image ID 为 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`。Auth 完整 Docker 归档为发布目录下 `images/auth-amd64.tar`，SHA256 为 `9eee0468c43bc4e54627fa0027b9710f972cee702d51f416203b03d618c040ce`，架构经 Docker inspect 验证为 `linux/amd64`。这两个值分别是**本地 Image ID**和**归档 SHA256**，不是远程 Registry Manifest Digest；本次同机固定镜像发布不依赖远程仓库，也没有在切换时重新构建或拉取。

Trivy 0.75.0 使用 2026-10-12 当天更新的漏洞库对该精确归档执行漏洞和密钥扫描，报告 0 个漏洞、0 个密钥发现，原始 JSON 存在本地 `release-evidence/round12/auth-image-trivy.json`。Auth 源码与镜像内 `trade_service.py` 哈希一致；第二次提交只改首页 HTML 与发布／测试脚本，Auth 镜像字节未变化，故复用同一已扫描镜像。

最终切换前备份清单：`/opt/autolink-backups/round12-20261012/final-20261012T145210Z/release-backup-manifest.json`。该次备份包含 SQLite 一致性快照、公开目录、上传文件、旧源码／配置、Caddy 数据与证书卷、旧镜像；独立恢复验证为 `isolatedRestoreVerified=true`。备份时数据库实际有 270 条车型、60 个品牌，公开 API 有 244 个车型、53 个品牌，数量和实体逐一对照，未将数据库总数误当作公开目录。

最终候选的隔离发布验收核对了全部 297 个公开车型／品牌页面及 277 个 Sitemap URL，并完成候选→旧版→候选回滚演练。切换前预检于 UTC 14:53:28 通过；按 Auth 健康→Web 健康顺序切换，核心生产探针于 UTC 14:54:33 通过。首次发布在 UTC 14:39:30 通过核心探针，但浏览器回归发现重复脚本后于 UTC 14:47:07 主动安全回滚；最终候选为新的锁和新的发布目录，没有复用已尝试的发布状态文件。

## 9. Google Search Console 与公网验收

UTC 14:43，使用已授权的 Search Console 向域名资源重新提交根 `https://autolinkglobal.com/sitemap.xml`，界面明确显示 `Sitemap submitted successfully`。随后真实 URL Inspection Live Test 显示该 XML `URL is available to Google`，Google 获取的 SOURCE 含三个正确子地图，MORE INFO 显示 `application/xml` 与 `HTTP Response 200 OK`。这证明实时抓取与提交动作成功，**不代表 Sitemap 后台已处理成功**；提交后表格仍暂时显示原有 `Couldn't fetch`、发现 0 URL，应在监控结束和后续 24—72 小时复查。

最终候选切换后，UTC 15:05 的**真实首页 URL Inspection Live Test**再次显示 `URL is available to Google`；Google 抓取的 HTML 含英语 `lang`、英语 Canonical、品牌导航、车型入口、英语 H1、英语介绍和极氪图片，Google 手机渲染截图显示完整首屏，而非全屏加载错误。MORE INFO 为 `HTTP Response 200 OK`、`text/html`。该次 26 个资源中 2 个未加载：主脚本 `index-autolink-membership-apply-pricing.js?v=20261012-home-fast` 标为 `Other error`，私有 `/autolink/me` XHR 按 robots 被阻拦。主脚本在普通公网浏览器及直接 HTTPS 请求均可 200 加载，但 Google 实时资源列表仍未消除该错误；静态首页确保抓取正文不依赖它。不能声称所有 Google JavaScript 错误已修复。

同一最终候选运行期间，`/trade/models/geely-monjaro-2026`、`/trade/models/byd-han-2026` 和 `/about` 的真实 Live Test 均显示 `URL is available to Google`；前两款车型和 About 的 Google Index 既有记录显示 `URL is on Google`，**不是本轮新提交后即时收录**。Geely 的 Google 抓取源代码显示英语说明、2026 2.0TD DCT 配置、2,845 mm 轴距、正确 Canonical 和 `index, follow`；手机渲染截图含车型名称、介绍、真实图片与参数入口。BYD Han 的抓取源代码显示 2026 电动版、CLTC 705 km、69.07 kWh、2,920 mm 轴距及正确 Canonical。Geely 的 18 个资源有 1 个 `/buyer/buyer.css` 因现有 robots 私有路径规则被拦截；主车型内容和图片仍正常渲染。该共用 CSS 的公开抓取资格需后续单独修正，不能为了它放开整个 `/buyer/`。

未审核阿拉伯语首页 `/?lang=ar` 的 Live Test 显示 `URL is not available to Google`，理由为 `Excluded by 'noindex' tag`；Google Inspection Tool smartphone 抓取成功，明确读取 `robots` meta 的 `noindex`，用户声明 Canonical 为本语言 URL。该 URL 当前未被 Google 收录，且 Sitemap 没有列它。

UTC 15:11 再次打开域名资源的 Sitemap 表格，根地图提交日期为 Oct 12，但状态**仍为 `Couldn't fetch`、类型 `Unknown`、发现 0 URL、Last read 空白**。随后分别对三个子地图进行真实 URL Inspection Live Test：`models-1.xml`、`static-1.xml`、`brands-1.xml` 均显示 `URL is available to Google`，MORE INFO 均为 `application/xml` 和 `HTTP Response 200 OK`；Google SOURCE 可读到 XML 及品牌条目。它们的 Google Index 页面仍显示 URL 未知，这对 XML 子地图不等于业务页面未收录。根与三个子地图的实时抓取成功，仍**不等于** Search Console Sitemap 后台处理成功。未重复提交子地图或制造“已收录 277 个”的说法。后续 24—72 小时复查同一条记录；若仍不成功，需取得 Google 侧更细的抓取日志／错误说明或官方支持反馈后再改网站。

## 10. 上线监控及剩余风险

最终发布的核心探针在 UTC 14:54:33 通过，自动监控于 UTC 15:26:07 将状态写入 `completed`，覆盖 30 次间隔约一分钟的探针，日志中 `MONITOR_FAILURE` 为 0。监控持续验证 Auth／Web 健康、公开 HTTPS、9 个语言首页、公开目录 244／53、关键车型／品牌、Sitemap 及其三个子地图、空子地图 404、登录与管理权限；每 5 次检查生产 SQLite `PRAGMA quick_check`、Docker 资源和磁盘空间。最后可见资源记录中 Auth 为约 0.01% CPU／91.15 MiB、Web 为约 0.13% CPU／21.06 MiB，磁盘可用 15,171,293,184 B。此为监控采样值，不是峰值或长期负载结论。

监控完成后再次 Docker inspect：Auth 容器实际 Image ID 为 `sha256:3d989c05558c56eef533f15d369e1978e0f08cfb728c407f99d091efe18c15a3`，Web 为 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`；两容器均 `healthy`，重启次数均为 0，与发布锁一致。第二次切换未回滚。第一次因启动器覆盖遗漏造成的重复脚本加载已在 UTC 14:47:07 安全回滚，详细经过见第 3、8 节。生产监控证据保存在服务器 `/opt/autolink-release-state/round12-20261012/40d685b-round12-20261012/status.json` 和 `cutover.log`，只读公网审计与 Lighthouse JSON 保存在本地 `tests/results/round12/`。

若后续出现关键回归，已验证的回滚目标是 `/opt/autolink-releases/52c6934-round11-20261012` 与其固定旧 Auth 镜像。Runbook 按 Auth 健康后切 Web，使用 `--pull never --no-build`，保留当前 SQLite、上传文件及全部持久卷；切换前应先另做当时最新的一致性备份。隔离环境已完成候选→旧版→候选版回滚演练，正式生产**未**在这次最终切换后做额外故障注入。

已知未解决项：Search Console 后台未给出 `Couldn't fetch` 的具体原因；修正了网站侧 18 个不合资格静态条目后仍需等待 Google 重新处理。公网中文电脑 LCP 这组样本较基线变慢；受控本地手机 LCP 仍约 5.86 秒，而公网这组三次为约 1.89 秒，环境差异需要长期真实用户数据判断。Google 实时检查仍把首页主脚本标为 `Other error`，车型共用的 `/buyer/buyer.css` 被 robots 拦截；现有共享主脚本仍约 2.29 MB。后续应取得可维护的源码／source map 后实施路由级拆分，单独修正共用 CSS 的抓取规则，并验证 Safari 和不同海外网络。
