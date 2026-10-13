# AUTOLINK 非洲与中东市场多语言 SEO 扩展报告

更新日期：2026-10-14（Asia/Bangkok）。
基准：切换前生产安全分支 `ce079be`、切换后固定发布提交 `ccf441391bba1783c66fc453b06dbd02798c33dc`、生产数据库只读核对及 Google Search Console 实际界面。下文将技术索引资格、Google 实际收录和发布状态分开记录。

## 1. 当前覆盖与发布口径

生产公开目录为 **244 个车型、53 个品牌**；数据库共有 270 条车型、60 条品牌记录，后者包含不公开或停用记录，不可作为公开 SEO 数量。当前公开车源和供应商各 **1** 个，且车辆审核、企业审核与品牌授权是三个不同事项。

| 语言 | 切换前合格车型／品牌 | 切换后合格车型／品牌 | 本轮其他页面 |
| --- | ---: | ---: | --- |
| 英语 en | 49／9 | **51／11** | 新增 Haval H6、Tank 300 两个车型及 Haval、Tank 两个品牌；英文非洲采购指南 |
| 中文 zh | 177／0 | **177／0** | 现有合格页保留 |
| 阿拉伯语 ar | 0／0 | **0／0** | 中东指南 RTL 草稿仍为 `noindex` |
| 法语 fr、斯瓦希里语 sw | 0／0 | **0／0** | 界面可访问，未审核内容继续 `noindex` |
| 俄语 ru、哈萨克语 kk、乌兹别克语 uz、韩语 ko | 0／0 | **0／0** | 保留九语言界面，本轮不开放新索引 |

旧报告中的 50 个英文车型、10 个英文品牌是历史技术资格口径；切换前线上源资料或审核指纹变化后实际为 49／9。本轮真实生产逐页复核为 **51／11**，是技术索引资格，**不是 Google 已收录数**。中文 177 个不删除。英语车型距“可靠资料车型的 80%”阶段目标仍很远；不通过放松审核凑数。

## 2. 国家市场机会与证据边界

| 市场 | 有用的独立内容方向 | 可核实材料与限制 |
| --- | --- | --- |
| Nigeria / 西非英语市场 | 车型身份、配置、供应商实际车源、进口方需核对的文件 | [U.S. Commercial Service Nigeria 汽车行业概览](https://www.trade.gov/country-commercial-guides/nigeria-automotive-sector)提及中国是新车及零部件的重要来源，同时说明市场数据不完整；不据此声称任一车型获准进口。 |
| Kenya / 东非 | 方向盘、车辆年份、检验、完整车型资料 | [Kenya Revenue Authority 车辆进口指引](https://www.kra.go.ke/component/content/?Itemid=206)涉及右舵及道路适用性检验；须按实际车型与最新规则复核。斯瓦希里语先研究，不开放机器翻译页。 |
| Saudi Arabia / Gulf | SUV 搜索、当地版本与中国版本差异、真实供应资源 | [GWM 官方 Tank 300 沙特发布资料](https://www.gwm-global.com/news/3402203.html)说明当地存在 Tank 品牌营销，不证明本平台的中国配置、库存、准入或授权。 |
| UAE、Oman、Qatar、Kuwait、Egypt | 国家级买家问题和车型别名研究 | 现有 GSC 未提供对应非品牌车型关键词证据；先收集搜索和真实询盘，不批量建立国家入口页。 |
| Morocco、Algeria、Tunisia、Senegal、Côte d’Ivoire、Cameroon | 法语车型术语及当地采购流程 | 尚无经审定的法语车型正文或进口规则内容；暂不将法语页加入 Sitemap。 |

车型是否可能供应，与目的国是否允许进口，必须分别核实。页面不承诺进口税率、认证、方向盘适用性、物流、清关或交付。

## 3. 内容建设清单与实际完成

本轮完成的英文车型：`/trade/models/haval-catalog-1`（Haval H6，中国市场 2026 1.5T 两驱经典版参考配置）和 `/trade/models/tank-catalog-1`（Tank 300，中国市场 2026 2.0T 汽油挑战者版参考配置）。两页使用既有车型参数源文件、车型与资料 SHA256 绑定的英文原创介绍、准确的功率／尺寸等已收录数值、图片、采购提醒和买家询盘入口；没有生成报价、库存或海外认证。车型名称和中东市场背景与[GWM 官方车型资料](https://www.gwm-global.com/news/1155598.html)、[Tank 300 发布资料](https://www.gwm-global.com/news/3402203.html)交叉核对；具体中国配置仍以平台受审的源记录为准。

本轮完成的英文品牌：`/trade/brands/haval` 与 `/trade/brands/tank`。品牌背景根据[GWM 官方品牌车型资料](https://www.gwm-global.com/news/3403821.html)整理；目录、能源和车型链接来自当前数据。品牌页新增统一的“资料仅供参考、与制造商授权无关”说明。供应商页把 `main_brands` 标成供应商自行申报，并声明企业和车源审核不构成制造商授权。

英文区域页：`/guide/african-importers` 有独立的国家差异、车型配置、公开车源核验和询盘内容，并链接上述官方资料和平台真实入口。已有 `/guide/middle-east-importers` 继续保留。本轮只把两篇英文区域页放入静态 Sitemap。

阿语试点：`/guide/middle-east-importers?lang=ar` 提供 `lang=ar`、RTL 和独立阿语正文／标题／自引用 Canonical；目前是待合格阿语审稿的 **`noindex` 草稿**，不出现在 Sitemap 或已审核 hreflang 中。法语和斯瓦希里语本轮仅有建设顺序，没有伪装完成页面。

下一批候选须逐一核实资料和搜索需求。英语可先审核 Haval Dargo/H9、Tank 400/500、Chery Tiggo 8、Geely Monjaro、BYD Song Plus 的当前未合格版本；已有合格版本不重复建页。阿语从已合格英语页筛选 Tank 300、Haval H6、Geely Monjaro、Changan CS75 Plus、BYD Song Plus 的实际对应配置，经阿语汽车术语、图片、原始参数和市场别名审校后再决定开放。法语从相同的源合格集合中研究 Geely Coolray/Binyue、Haval H6、Changan CS75 Plus、BYD Song Plus、Tank 300；不能把这个研究清单视为已翻译或已审定。

## 4. 品牌参考库和供应商授权

**品牌库 ≠ 品牌授权；企业审核 ≠ 品牌授权；车源审核 ≠ 品牌授权。** AUTOLINK 是独立的车型资料及 B2B 供需对接平台。品牌或车型出现在目录，不意味着制造商合作、官方指定销售、经销商授权或平台库存。没有经核验的供应商，不展示“Official Dealer”“Authorized Distributor”“Exclusive Agent”等身份。

生产数据库目前没有独立的供应商品牌授权记录表。现有企业材料和企业审核不能替代授权方、授权链条、品牌、范围、地区、有效期及审核人员的核验。本轮生产 SEO 先消除可被误解的声明；独立授权凭证管理在 [PR #19](https://github.com/wuoo6327-dot/autolink-platform/pull/19) 开发，并以当前 SEO 生产基线整合为单独的[草稿 PR #20](https://github.com/wuoo6327-dot/autolink-platform/pull/20)。该功能**尚未部署**，不会从旧 `main_brands` 字段自动升级授权身份；完整授权文件始终保持私有。整合分支本地完整后端共运行 238 项，**233 通过、5 跳过**，仍需独立 AMD64、数据库备份／恢复及回滚验收。

## 5. 技术索引与询盘链路

模型和品牌沿用服务器初始 HTML、真实 404、审查指纹失效即 `noindex`、自引用 Canonical、仅合格语言 hreflang、当前数据驱动 Sitemap。新的英文非洲指南有英文 Canonical、英语与 `x-default`，未审语言有可访问的 `noindex` 回退；阿语草稿没有伪造的 hreflang。车型详情的询盘入口沿用 `/buyer/requests`，不更改已上线的买家中心、通知、商家后台、价格、会员权益或支付系统。

当前仅有 1 条审核后公开的车源及 1 个对应供应商，其余车型页仍须显示暂无对应公开车源。品牌页列品牌相关的真实资源，绝不推断所有商家都是官方经销商。

## 6. Google Search Console 真实观察

2026-10-14 查看 `sc-domain:autolinkglobal.com`：根 Sitemap `https://autolinkglobal.com/sitemap.xml` 的 **Sitemaps 报表显示 Success**，Google 上次读取为 10 月 13 日，已发现 **50** 个 URL；其中品牌子图成功发现 10 页、静态子图成功发现 40 页。但**车型子图 `/sitemaps/models-1.xml` 仍显示 Couldn't fetch、上次读取 N/A、发现 0 页**。因此根索引可读，车型发现问题尚未解决，50 不能当作全站发现量。公开车型子图实时 HTTP 为 200、`application/xml`、95,627 字节；标准 XML 解析通过且包含 228 个不重复的合格车型 URL（51 英文、177 中文）。这些只能证明当前公网交付正常，不能替代 Google 的子图读取结果。索引总览仍显示已索引 1 页、未索引 1 页（“Page with redirect”，报表最后更新 10 月 9 日）。所选近三个月性能区间此前显示 68 次展示、1 次点击，落在首页及品牌词；尚无新增车型 Google 收录或目标国家有效搜索流量证据。

正式发布后的真实 Google 手机实时检查：

| URL | Google 实际结果 | 索引事实 |
| --- | --- | --- |
| `/trade/models/haval-catalog-1` | 10 月 14 日 02:18，抓取成功、允许索引、自引用 Canonical 正确；“View tested page”的 HTML 中找到 Haval H6 英文介绍；页面资源全部加载、无 JS 控制台消息 | Google Index 仍为“URL is unknown to Google”，未证实收录 |
| `/guide/african-importers` | 02:28，Google 手机抓取成功、允许索引、自引用 Canonical 正确 | 尚未证实收录 |
| `/guide/middle-east-importers?lang=ar` | 02:25，Google 手机抓取成功，明确识别 `robots` meta 的 `noindex`；阿语 URL 自引用 Canonical | 草稿正确暂缓索引；未请求索引 |
| `/sitemap.xml` | 02:24，URL Inspection 实时抓取可用 | Sitemaps 报表根索引 Success，品牌和静态子图成功；车型子图仍 Couldn't fetch |
| `/sitemaps/models-1.xml` | 02:36，Google Inspection Tool smartphone 实时抓取成功、抓取允许、HTTP 页面可用 | Sitemaps 报表仍为 Couldn't fetch，故实时抓取不能代替后台子图处理成功 |

完成 30 分钟生产监控后，在 GSC **单独提交车型子图** `/sitemaps/models-1.xml`。界面明确回显 **“Sitemap submitted successfully”**；随即列表显示提交日期 10 月 14 日，但类型暂为 Unknown、状态仍为 **Couldn't fetch／发现 0**。因此仅确认 Google 接收提交请求，**不能声称已处理成功或车型已发现**；继续等后台读取和错误原因更新。此前根 Sitemap 已提交并显示 Success，本轮没有重复提交根索引。对已审核 Haval H6 英文页和非洲英文指南分别发起少量索引请求；阿语 `noindex` 草稿没有申请。索引请求进入队列不等于页面收录。

截图保存在本机 `tests/results/gsc-haval-live-20261014.png`、`gsc-haval-html-20261014.png`、`gsc-africa-live-20261014.png`、`gsc-arabic-noindex-20261014.png`、`gsc-sitemap-success-20261014.png`、`gsc-model-sitemap-couldnt-fetch-20261014.png`、`gsc-model-sitemap-live-20261014.png`、`gsc-model-sitemap-submitted-20261014.png`、`gsc-haval-index-requested-20261014.png` 和 `gsc-africa-index-requested-20261014.png`；截图未提交公开 GitHub 仓库。

上线后应按语言、国家、页面类型记录 URL Inspection、实际已索引、非品牌展示、自然点击、车型详情进入、注册与有效询盘；“具备技术索引资格”“已入 Sitemap”“Google 已索引”分别统计。

## 7. 测试与发布状态

本地与阿里云原生 `linux/amd64` 验收均使用当前生产目录的**隔离 SQLite 一致性副本**，未向真实客户写入测试记录：

| 验收项 | 真实结果与证据 |
| --- | --- |
| 后端完整测试 | 原生 AMD64 候选镜像共运行 235 项，**230 通过、5 跳过**；`native-container-tests.log` 退出码 0 |
| 全目录索引规则 | 隔离环境及正式公网均遍历 244 个公开车型、53 个公开品牌的 **2673 个语言详情页**；404、私有 API 401、Canonical、hreflang、noindex 和 Sitemap 集合检查通过；公网原始 JSON 为 `tests/results/overseas-seo-public-20261014.json` |
| 回滚演练 | 隔离环境依次启动候选镜像、旧生产镜像、再恢复候选；三个阶段均保留公开目录 244／53，隔离数据库完整性通过；`isolated-qa-run4.log` 退出码 0 |
| 手机／电脑功能 | 公网 Chrome 手机 390×844 与电脑 1440×900 分别检查首页、品牌目录、车型目录、Haval H6、买家登录及非关键脚本失败恢复；12 次页面检查均 200、无页面 JS 错误或横向溢出；`tests/results/afme-public-browser-20261014.json` |
| 安全 | 候选 AMD64 镜像 Trivy 高危／严重漏洞 0、密钥发现 0；本轮 3 个 SEO 提交 Gitleaks 0；[PR #18 安全 CI](https://github.com/wuoo6327-dot/autolink-platform/pull/18) 两次 `source-security` 实际运行并通过。全目录扫描的 371 条命中中 369 条位于被 `.gitignore` 忽略的 Trivy 漏洞数据库缓存，另外 2 条为旧发布锁的 SHA-256；未将其当作本轮源码泄露。 |
| 生产备份 | `/opt/autolink-backups/afme-20261014/final-20261013T191049Z/release-backup-manifest.json`：最新 SQLite 在线备份 SHA-256 `394a202630bc931f457f91bd87aa0be4ea99ab72556cc90caef53d9ee7dfa5d1`，隔离恢复和一致性校验通过，数据库 270／60、公开目录 244／53；上传与非数据库资料、Caddy 证书／配置、旧发布目录、旧镜像均有归档并逐项恢复／哈希验证 |

发布锁 `/opt/autolink-releases/16f65c8-afme-20261014/afme-release-lock.json` 固定了提交 `ccf441391bba1783c66fc453b06dbd02798c33dc`、Auth 镜像 ID `sha256:dd5523c9fe02eab7b7915c90444c95fef1b36a0d99a557b7fda8b0c9f423e148`、Web 镜像 ID `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`。Auth 完整归档 `/opt/autolink-releases/16f65c8-afme-20261014/afme-auth-amd64.tar` 的 SHA-256 为 `f348d18add0f890c2251c3d931811dddf6ee0ef429c8f48153d69195ed48ebfb`。**Docker Image ID 是本机镜像身份，不冒充 Registry Manifest Digest**；切换过程禁止拉取或重新构建。

## 8. 生产切换、监控与回滚

本轮 SEO 代码已完成生产切换，**支付及供应商品牌授权候选均未混入**。阿里云持久 `tmux` 发布会话执行固定脚本 `afme_cutover.py`，不自动拉取或构建、不改写现有 SQLite 和持久卷。2026-10-13 **19:14:18 UTC** 开始切换，先替换 Auth 并确认健康，再替换 Web；**19:14:44 UTC** 完成核心路由与 SEO 探测，约 26 秒，低于 5 分钟中断上限。发布状态文件位于 `/opt/autolink-release-state/afme-20261014/16f65c8-afme-20261014/status.json`，日志为同目录 `cutover.log`，支持断线后查询；脚本设置 110 秒切换期限和自动回滚，回滚镜像已经在隔离环境验证。

核心探测覆盖 HTTPS、首页、买家登录、品牌／车型目录、Geely Monjaro、Haval H6、Tank 300、英文非洲指南、阿语草稿、robots、Sitemap、私有 API 401、不存在车型 404、当前目录数量。公众手机和电脑真实浏览器检查均通过，Haval H6 图片实际解码成功，静态 JS／CSS／图片请求无失败；HTTPS 证书与域名匹配，有效期至 2027-01-01 UTC。生产 Docker Auth 与 Web 均运行锁定的镜像 ID；监控脚本每分钟检查健康与核心路由，每五分钟检查 SQLite `quick_check`、CPU／内存、磁盘，并在连续故障时自动回滚。

2026-10-13 **19:45:48 UTC**，发布脚本记录 `state=completed`，连续 30 分钟监控结束，探测失败 0、容器重启 0，**没有回滚**。最终只读核对显示 Auth 与 Web 均 `healthy`，运行镜像 ID 与发布锁相同；SQLite `PRAGMA quick_check=ok`、车型／品牌数据库记录仍为 270／60。Auth 约 97.58 MiB、Web 约 18.52 MiB，读取时 CPU 均低于 0.02%；磁盘剩余约 3.4 GiB（本轮另建隔离授权候选目录后），后续发布需要持续注意容量。此监控结果证明本次切换稳定，不代表 Google 已收录新增 URL。

## 9. 下一阶段

持续核对 GSC Sitemap “Couldn't fetch”的后台处理与实际读取状态，监测新英文页的 Google 实际收录、非品牌曝光、目标国家访问、注册与有效询盘；实时抓取成功不能当作已收录。根据真实搜索与询盘优先扩展可靠英文车型。阿语稿须汽车术语及区域内容审校，法语和斯瓦希里语须有对应源材料和读者需求后逐页推进。供应商品牌授权按单独的 PR #20 做原生 AMD64、旧数据隔离恢复和独立发布；到期或撤销时仅撤销授权身份，不自动删除合法贸易商及车源。服务器磁盘约 92% 已用，下次发布前应按经批准的保留策略清理旧归档，不能为腾空间直接删除仍需回滚的备份。
