# AUTOLINK 全球海外 SEO 叠加优化报告

**日期：**2026-10-12

**状态：**隔离候选，等待生产审批；未合并 `main`、未部署生产、未向 Google 提交 Sitemap 或索引请求。

**分支：**`codex/global-overseas-seo-20261012`，基于 PR #7 的 `58f34c3`；该提交包含 PR #6 的 `8c6e5e9` 和生产安全候选 `a38664f` 的祖先历史。PR #4 已在既有 SEO 候选历史中，本轮没有重复套用。

## 1. 原有 SEO 与生产目录

2026-10-11 18:50 UTC 对生产公开接口执行只读核对：**244 个车型、53 个品牌**，车型、品牌与本轮隔离快照完全一致；244 个车型参考资料和图片的哈希检查通过。没有写入生产数据库，也没有用历史目录覆盖线上记录。原先通过技术索引资格的 **177 个中文车型 URL、22 个英文车型 URL** 全部保留；九语言界面、服务端初始 HTML、robots、404、Canonical、hreflang 和现有 Sitemap 规则继续沿用 PR #6。首页性能修复沿用 PR #7，未改动首页脚本、极氪素材、布局或业务功能。

生产核对原始记录：`tests/results/live-catalog-overseas-seo-20261012.json`，打包于本报告证据归档。通过技术索引资格、出现在 Sitemap、Google 已收录是三个不同状态；本报告计数只代表前两项在隔离候选中的结果。

## 2. 英文车型内容

本轮在原 22 个英文车型的基础上，**新增 28 个**有独立英文介绍、英文配置名、采购核对说明及来源指纹的车型，隔离候选共 **50 个英文车型 URL**。选定配置的年份、数字和单位由当前生产同源的车型参考 JSON 校验；每页仍展示来源配置链接。本轮为 Codex 的来源对照与英文内容质量检查，生产运营审批前仍应由熟悉目标市场的编辑复核市场称谓。车型介绍不宣称某配置适用于全部市场。实际可公开车源只来自既有供应商发布审核；没有车源时明确显示暂无公开车源。没有新增 FOB 价格、虚构库存、厂家授权或特定国家准入声明。

新增清单：Geely Coolray/Binyue、Emgrand、Haoyue L；Galaxy E8、L6、Starship 7 EM-i、Xingyuan；Zeekr 009、MIX；BYD Qin PLUS、Qin L、Seal 06；Denza N8L、Z9GT；Changan UNI-V、Eado PLUS；Deepal S09、L07；GAC Trumpchi GS3、GS4、M6、Xiangwang M8 PHEV L；SAIC Volkswagen Lavida、Teramont；FAW Volkswagen Sagitar、Magotan、Tayron、Talagon。原有 22 个继续保留，精确 URL、文案与审核来源见 `site/locales/seo-model-en-reviewed.json`。

英文审批并非永久标记：车型名称、年份、图片、描述、参数、活跃状态或参考文件发生变化时，其源指纹不匹配，页面自动转为 `noindex` 并从下次按请求生成的 Sitemap 移除。中文合格页独立判断，不因英文审核失效而删除。还有 **67 个公开车型**未满足中文技术索引资格；除已审核英文的 50 个外，英文页面继续可访问但暂缓索引。数量按当前 244 条记录计算，不代表未来生产目录会固定不变。

## 3. 英文品牌内容

本轮完成 **10 个**有独立英文介绍和来源链接的优先品牌页：Geely、Galaxy、Zeekr、BYD、Denza、Changan、Deepal、GAC Trumpchi、SAIC Volkswagen、FAW Volkswagen。其余 **43 个品牌**仍可访问，但当前没有通过英文内容审核，故不进入品牌 Sitemap。品牌页列出当前数据库中的车型、车身和动力分类，以及经过发布审核的车源入口；品牌出现在目录中不代表 AUTOLINK 获得厂家授权。

背景说明核对了[Geely](https://global.geely.com/en/brand)、[Zeekr Group](https://www.zeekrgroup.com/en/about-zeekr)、[BYD](https://www.byd.com/en/about-byd)、[Denza](https://media.byd.com/section/company/brands/denza/?lang=eng)、[Changan](https://www.globalchangan.com/aboutus.html/)、[Deepal](https://www.globalchangan.com/deepal.html)、[GAC Motor](https://www.gacmotor.com/about)和[Volkswagen Group China](https://www.volkswagen-newsroom.com/en/volkswagen-group-china-4068)的厂商页面；Galaxy 的品牌背景参照[Geely 发布资料](https://global.geely.com/en/news/2026/geely-full-domain-ai-auto-china-2026)。当前品牌车型组合来自 AUTOLINK 目录，不冒充厂商实时在售清单。品牌名称、基础资料或所属车型内容改变时，英文品牌审核指纹自动失效。

## 4. 海外采购关键词与市场页面

[关键词与市场映射](OVERSEAS_SEO_KEYWORD_AND_MARKET_MAP_20261012.md)覆盖 China Car Export、Chinese Car Suppliers、Cars Exported from China、Buy Cars from China、Chinese Cars Wholesale、China Vehicle Exporters、China New Car Suppliers、Geely Monjaro China Export、BYD China Export Supplier、Changan CS75 Plus China 和 China FOB Car Quotation 等采购意图。相近词共享对应的车型、品牌、公开车源或指南页，没有按词批量造重复页面；未采集搜索量或排名，故不声称词库具有实际曝光。

新增一个具备独立内容的[英语指南候选](../site/guide/middle-east-importers.html)，拟上线 URL 为 `/guide/middle-east-importers`，覆盖车型版本、真实车源、目的国审查和报价核对四步。其英文 Canonical 和 `x-default` 指向自身；未审核语言变体返回可读的 `noindex` 提示。非洲、中亚、东南亚目前只有研究规划，没有发布薄内容入口。指南不承诺某车可进口，也不列未经核实的税率、认证或报价。

## 5. 九语言索引状态与自动管理

| 语言 | 合格车型 URL | 合格品牌 URL | 处理 |
| --- | ---: | ---: | --- |
| 英语 `en` | 50 | 10 | P0，已审核页面进入隔离 Sitemap |
| 中文 `zh` | 177 | 0 | 保留原合格车型 |
| 阿拉伯语 `ar`、俄语 `ru` | 0 | 0 | P1，页面可访问，待本地化审核 |
| 哈萨克语 `kk`、乌兹别克语 `uz`、韩语 `ko`、法语 `fr`、斯瓦希里语 `sw` | 0 | 0 | 页面可访问，待本地化审核 |

本轮隔离 Sitemap：**227 个车型详情 URL、10 个品牌详情 URL、64 个既有及新增静态 URL**。其中新增市场指南只有英语 URL 具备进入隔离 Sitemap 的资格。未完成本地化的语言没有被错误指向英文 Canonical，也没有被添加到可索引详情 Sitemap。

管理员后台新增只读 **SEO 管理**页和管理员权限保护的 `/autolink/admin/seo/status`：逐车型和品牌显示英文审核状态、index/noindex 资格、九语言数量、缺失或失效审核、最近目录更新时间、按请求生成的 Sitemap 资格数。目录或来源资料变动时，服务端页面、管理员状态和 Sitemap 下次请求即重新判定；新增车型不会自动获准九语言索引。当前页不提供不具证据的“Google 已收录”数字。

## 6. 测试与安全回归

- 隔离环境：macOS ARM64 本机，当前 244/53 生产公开目录的只读快照、独立临时 SQLite 与合成账号；Caddy `127.0.0.1:18181`、后端 `127.0.0.1:18180`。未访问生产写接口。
- 车型与品牌 **2,673 个语言详情页**逐页检查 HTTP、初始 HTML、H1、`html lang`、Canonical、robots、hreflang；Sitemap 精确集合一致，缺失车型 404、匿名 SEO 后台 401，普通 User-Agent 与 Googlebot Smartphone **模拟**的四个代表页面字节一致。结果通过；模拟不能替代 Search Console 实际抓取。
- 后端全套 **225 项通过、5 项条件跳过**，覆盖目录、登录、Cookie/CSRF、权限、私有资料、供应商发布审核、SEO 和交易流程。`node --check`、Python 编译、Caddy 校验和 `git diff --check` 均通过。
- Trivy 本地源文件扫描：`secret,misconfig` 对检查到的依赖清单和两个 Dockerfile 均为 0 发现；`vuln` 对 `auth/requirements.txt` 为 0 发现。本轮没有构建新 AMD64 镜像；PR #6 原镜像扫描记录不能当作本分支新镜像扫描通过。
- 393×852 浏览器手机视口：新指南无横向溢出，首屏正文与移动菜单可见，菜单中的车型、品牌、车源及采购入口可访问。

原始抓取、后端日志、Trivy JSON 和 Lighthouse JSON 均保存在[证据归档](evidence/autolink-overseas-seo-20261012.tar.gz)（SHA-256 `9a5b99c2fbc1b36a189aa0e9b3979a463d6152590fcdcbfc25af5f73b051b988`）；测试没有调节浏览器节流参数来制造分数。

## 7. 性能影响

Lighthouse 在同一台本机、同一隔离 Caddy 与 CLI 配置下，对首页、新增英文车型、英文品牌及市场指南分别进行手机/电脑各三次独立 Chrome 冷启动。8 组共 **24 份原始 JSON，0 次运行错误**，下表为每组中位数。首页沿用 PR #7 实现；前轮同环境首页手机中位数也是分数 64、LCP 6,905 ms、TBT 17.5 ms、CLS 约 0，故本轮没有声称首页性能改善。

| 页面 / 设备 | Performance | LCP | TBT | CLS |
| --- | ---: | ---: | ---: | ---: |
| 首页 / 手机 | 64 | 6,905 ms | 17.5 ms | 0.000001 |
| 首页 / 电脑 | 84 | 1,596 ms | 0 ms | 0 |
| Geely 英文车型 / 手机 | 95 | 2,861 ms | 0 ms | 0 |
| Geely 英文车型 / 电脑 | 100 | 665 ms | 0 ms | 0 |
| BYD 英文品牌 / 手机 | 96 | 2,784 ms | 0 ms | 0 |
| BYD 英文品牌 / 电脑 | 100 | 668 ms | 0 ms | 0 |
| 中东采购指南 / 手机 | 100 | 901 ms | 0 ms | 0 |
| 中东采购指南 / 电脑 | 100 | 242 ms | 0 ms | 0 |

BYD 品牌页在一组**探索性单次冷测**中，卡片下载原始大图时总传输约 6.11 MB、LCP 5,934 ms；改用同一图片经哈希校验的 640px 衍生图后，该次样本为约 0.42 MB、LCP 2,784 ms。该前后对照只有各一次，不能当作稳定提升幅度；正式优化后结论以上表三次中位数为准。首页手机 LCP **仍未达到 2.5 秒目标**，英文车型与品牌样本也稍高于 2.5 秒；三者 TBT 均低于 200 ms，详情 CLS 符合 0.1 上限。新 SEO 内容不向首页主 JavaScript 或首屏图片再加依赖；它们由服务端 HTML 和独立指南文件交付。隔离实验室分数不能替代生产的真实用户 Core Web Vitals。

## 8. Google 与业务效果数据

本分支未部署，因此没有候选版本的 Search Console 实时抓取、Google 选定 Canonical、已索引 URL、英文词曝光、自然搜索点击或真实采购询盘数据。Search Console 尚未连接到本次隔离后台；自然搜索来源到车型浏览、注册和有效询盘的站内归因也尚未建立。后台以空值和明确的“未连接”状态展示这些指标，不把 237 个可索引详情 URL 当成 Google 已收录数，也不把访问当作有效询盘。

## 9. 实际变更与候选版本

代码：`auth/seo_service.py`、`auth/trade_service.py`、`auth/app.py`、`site/admin/app.js`、`site/admin/bootstrap.js`、`site/admin/index.html`、`Caddyfile`、`site/guide/render.mjs`、三份现有英语指南 HTML；新增市场指南及未审核语言提示。品牌及相关车型卡片改用与原图哈希绑定的 640px 真实图片衍生图，车型详情保留高分辨率原图。内容：`site/locales/seo-model-en-reviewed.json`、`site/locales/seo-brand-en-reviewed.json`。工具/测试：`scripts/extend_overseas_editorial.py`、`scripts/overseas_seo_http_qa.py`、`scripts/lighthouse_public_qa.py`、`scripts/serve_public_snapshot_qa.py` 和相关后端测试。`auth/catalog.json`、生产数据库、会员收费、商家入驻规则及法律协议均未修改。

发布锁：[OVERSEAS_SEO_RELEASE_LOCK_20261012.json](OVERSEAS_SEO_RELEASE_LOCK_20261012.json)。该锁固定生产目录、审核文件哈希与隔离 Sitemap 计数；本分支没有新的 AMD64 固定镜像或 registry digest，不能沿用旧镜像标识冒充本轮候选构建。候选运行代码提交为 `10965677b67dde3ab7aff70f6f6de6d3bb60b9be`，审查入口为[草稿 PR #8](https://github.com/wuoo6327-dot/autolink-platform/pull/8)，其 base 为 PR #7 的分支。

## 10. 生产部署及回滚方案

1. 审批前再只读比对生产目录、参考文件、图片哈希和安全配置；若与 244/53 或锁定指纹不同，先重新审核新增内容与索引资格，再更新候选，不以旧数量覆盖生产。
2. 按 PR #6 → PR #7 → 本分支的祖先顺序形成一个固定发布提交；在阿里云 `linux/amd64` 独立预发布环境构建固定 auth/web 镜像、记录 archive SHA-256 和 registry manifest digest，并对该镜像进行漏洞/密钥扫描、全套后端、页面、安全、性能及回滚演练。审核旧 PR 与线上变更冲突，禁止重复 cherry-pick PR #4。
3. 取得单独生产批准后，先做生产 SQLite、上传卷和证书卷的一致性备份，并在副本验证恢复。发布时只交付已审核的代码和静态内容，保留生产目录、账号和私有资料；以固定 digest 替换镜像，检查健康状态、SEO HTML、robots、Sitemap、权限和首页。
4. 异常时用已验签的上版镜像与**当前生产目录**回滚，不让旧镜像的历史种子覆盖现有车型。先在隔离环境复现回滚，再按生产变更流程执行。
5. 生产稳定后另获授权，才在 Search Console 检查代表性英文/中文/`noindex` 页面、Google 选定 Canonical 与抓取结果；提交 Sitemap 或发起索引请求仍需单独授权。建立自然搜索来源到注册和有效询盘的合规归因后，再报告实际海外采购效果。

## 11. 未解决项

- 43 个品牌英文页及尚未审查的英文车型仍为 `noindex`；阿语、俄语、法语等尚无审核合格的车型/品牌正文。
- 非洲、中亚、东南亚没有合格的独立落地页；不得以换地名的文本凑量。
- 本轮候选缺少 AMD64 镜像归档、digest 与对应隔离回滚验收；旧 PR 的固定镜像只证明旧提交。
- Google 实际收录和站内有效询盘归因尚无连接数据；上线前后必须分别验证。
- 首页手机 LCP 的既有瓶颈仍需按实际性能数据继续处理，不将新增 SEO 页面分数冒充首页达标。
