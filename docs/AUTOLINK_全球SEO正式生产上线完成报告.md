# AUTOLINK 全球 SEO 正式生产上线完成报告

**记录日期：**2026-10-12（Asia/Bangkok）

**结论：正式上线未执行。** 网站所有者已授权在全部发布门槛通过后直接部署，但本轮镜像 manifest 校验门槛未通过；按授权条件停止了生产切换、Search Console 提交与索引请求。以下通过数据均来自隔离预发布，不能写作生产或 Google 验收。

## 1. 生产与候选核对

生产 auth/web 容器仍为 `autolink-demo-auth-1`、`autolink-demo-web-1`，检查时均为 healthy；生产认证镜像本地 ID 为 `sha256:328ad2e7f193d924d8adc9943c2bde450e26e1b1af7318b26b1e4cb8984d4b80`，Web 镜像本地 ID 为 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`。认证发布目录为 `/opt/autolink-releases/a38664fc9bf2be639cbcb65dce4b57ef5b94170c`；公开站点已有部分后续资源，故预发布从**当时生产站点只读副本**生成，未将 Git 历史站点直接覆盖到线上。停止前，生产 HTTPS 首页实测 HTTP 200、证书校验结果 0，原容器仍 healthy。

GitHub PR [#6](https://github.com/wuoo6327-dot/autolink-platform/pull/6) → [#7](https://github.com/wuoo6327-dot/autolink-platform/pull/7) → [#8](https://github.com/wuoo6327-dot/autolink-platform/pull/8) 依次构成祖先链；本轮[草稿 PR #9](https://github.com/wuoo6327-dot/autolink-platform/pull/9) 以 #8 分支为 base。PR #4 已在祖先历史中，没有重复合并。运行候选提交为 `129c08e09efb3b6a9c99b10fb6aa8885d8b160b6`，分支 `codex/seo-production-release-20261012`；未合并 `main`。

生产数据库共有 **270 条车型、60 条品牌记录**，其中当前公开有效目录为 **244 个车型、53 个品牌**。只读校验逐条匹配当前公开目录，244 个车型参考资料与图片哈希全部匹配；没有将旧种子、测试记录或历史数量写入生产。生产认证卷、只读根文件系统、非 root 用户与 `no-new-privileges` 配置保持原状。仓库仍为 **Public**，没有更改可见性。

## 2. 候选内容与索引资格

预发布从生产公开站点复制 **5,424 个文件**，受控覆盖 **269 个文件**，其余 **5,155 个文件**逐一验证 SHA-256 未改变。覆盖包含 PR #6 的车型/品牌 SSR、robots、Sitemap、Canonical、hreflang、404/noindex，PR #7 的首页性能资源，以及 PR #8 的英文车型、品牌和采购指南；对三处与生产不一致的首页/业务资源先核对实际哈希再显式纳入覆盖。没有改动生产数据库、会员收费、商家入驻规则、法律协议或私有资料。

当前隔离候选符合技术索引资格：**50 个英文车型 URL、177 个中文车型 URL、10 个英文品牌 URL**；车型 Sitemap 227、品牌 Sitemap 10、静态 Sitemap 64。50 个英文车型和 10 个英文品牌沿用既有来源指纹与内容审核，未审核车型、品牌及其他语言仍可浏览且 `noindex`。英语是本轮重点；阿拉伯语、俄语及其他未审核语言没有被误列入详情 Sitemap。这里的“技术索引资格”不等于 Google 已收录。

## 3. AMD64 隔离测试与安全

在生产同一阿里云主机的独立 `linux/amd64` 网络、`127.0.0.1:18084` 端口和真实数据库**备份副本**上运行，未挂载生产数据库卷。结果：

| 验收项 | 实际结果 |
| --- | --- |
| 后端及权限回归 | 共运行 225 项，其中 220 项通过、5 项条件跳过；无失败。覆盖登录、Cookie、CSRF、所有者权限、私有资料、供应商审核与 SEO。 |
| 候选 → 旧版 → 候选回滚 | 三阶段均 HTTP 200、公开目录 244/53、匿名后台 401；候选与恢复阶段车型 Sitemap 227、品牌 Sitemap 10；旧版未补入历史车型。 |
| 全部公开详情与语言 | 244 车型、53 品牌 × 9 语言，共 **2,673** 页，HTTP/H1/HTML lang/Canonical/robots/hreflang 检查零失败；不存在车型 404，Sitemap 精确集合一致。 |
| 浏览器功能 | 手机 Zeekr 9X 服务端正文与 39 行参数、桌面 Geely Monjaro 英文正文与 8 行参数通过；非关键脚本失败时首页 H1、品牌/车型入口与完整正文保留；九语言首页、手机菜单、语言切换、登录与车型目录导航通过。 |
| 搜索爬虫模拟 | 四个代表详情的普通 UA 与 Googlebot Smartphone **模拟**响应一致；不等于 Google 实时抓取。 |
| GitHub 安全 CI | PR #9 最终运行提交 `129c08e` 的 `source-security` job **success**，当前源码与全部检出历史的 Gitleaks/Trivy 步骤实际运行通过；Public 仓库的私有制品上传步骤按设计跳过。 |
| 镜像扫描 | 固定 Trivy 扫描：auth CRITICAL/HIGH/MEDIUM/LOW/UNKNOWN 均 0；Web 为 0/0/0/0/1。唯一 UNKNOWN 是 `GO-2026-5932`、`golang.org/x/crypto`。[Go 官方漏洞记录](https://pkg.go.dev/vuln/GO-2026-5932)指出受影响包为 `openpgp`；尚未证明现有 Caddy 二进制使用该包，故保留跟踪，不把 UNKNOWN 算成零风险。 |

原始证据保存在阿里云隔离目录 `/home/admin/autolink-final-seo-qa-20261012/`：`backend-tests.log`、`rollback-final.log`、`tests/results/overseas-seo-http-final-20261012.json`、`browser-qa-public/tests/results/` 两份浏览器 JSON，以及 `qa-scan-final/results/` 两份 Trivy JSON。隔离容器和网络已停止并移除，真实数据库临时副本已清理。

## 4. 备份、镜像与发布阻断

用 SQLite 在线备份 API 建立只读时点备份：`/opt/autolink-backups/seo-final-20261012/autolink-auth-20261011T195016Z.sqlite3`，SHA-256 `ec04bd0080d99adc7e2faac841aa986b4132da42981c2af4fac74811b39e8317`。完整性检查 `ok`、外键违规 0、270/60 条数据库记录、隔离恢复验证通过。另有同目录下 root-only 的非数据库认证卷、Caddy 证书卷、配置卷和运行配置预备归档，四份 `tar.gz` 均已完整读取校验。**这属于预发布备份；由于没有切换，不存在切换前最终备份。**

候选认证镜像 `autolink-final-seo-auth:129c08e` 为 AMD64，本地**镜像 ID** `sha256:0fcb1f1c73a0d6b7b23c81355a9d48ca1e82e514705011d26c63a7cd5aaff815`；归档 `/home/admin/autolink-final-seo-qa-20261012/auth-image-final.tar`，SHA-256 `4362de3c243ec679282da29f3d577ce68fd612d8c1cec00970921029da23f4bf`。固定 Web 归档 `web-image-final.tar`，SHA-256 `ddf2c2f6544eea709258695c53da57bc42b27850a52e2af5a27c61875e59927e`；旧认证镜像回滚归档 `production-auth-image-preflight.tar`，SHA-256 `f7e329d3be8bb854b846081c73f2a34d3fc97fcb9c7f30c2d99a2b819e61cb9e`。

**关键发布阻断：**候选 auth 镜像的 `RepoDigests` 为空，无法提供已推送仓库的 manifest digest。现有 Web 镜像的 `RepoDigests` 字符串与其本地镜像 ID 完全相同，缺少独立的仓库清单验证；不能将它当成已经核实的 registry manifest digest。当前 GitHub 登录令牌仅有 `gist`、`read:org`、`repo`，不具备镜像仓库写权限；服务器 Docker 配置也没有可用仓库凭据。为取得可信 digest 必须使用受控镜像仓库并具备相应权限，这超出本任务已有权限范围。按照“发布镜像验证不通过即停止部署”的指令，本次没有生产切换。运行中的生产镜像仍是旧版，故“实际上线镜像 digest”及上线时间均**无**。

## 5. 性能、Google 与上线后状态

本轮 AMD64 最终组装完成了手机/桌面浏览器功能与脚本失败测试；**未对最终组装版重新运行完整 Lighthouse 冷测**，此项发布门槛也未完成。相同候选链此前 PR #7 的 30 次本机隔离冷测，首页手机中位数为分数 64、LCP **6,905 ms**、TBT **17.5 ms**、CLS 0，电脑首页 LCP 1,597 ms；PR #8 的 24 份隔离冷测中首页手机仍为 LCP 6,905 ms，英文 Geely 车型手机 LCP 2,861 ms、BYD 品牌手机 2,784 ms。它们是**先前候选的实验室结果**，不能冒充本次最终组装版或生产监控。首页手机 LCP 仍未达到 2.5 秒理想目标。

没有生产 SEO 新版，故没有对新版执行 Google Search Console URL Inspection Live Test；**Sitemap 未提交，索引请求未发起**。Google 实际选择的 Canonical、已索引量、关键词曝光、自然点击及有效询盘均无本轮新增证据。没有生产切换，也没有 30 分钟“上线后”监控或生产回滚；隔离回滚演练通过不等于生产回滚。

## 6. 后续发布与回滚步骤

1. 在受控镜像仓库获得现有权限范围内的发布方式，固定并验证 auth 与 Web 的真实 registry manifest digest；如果需要新增仓库/权限，先由所有者处理。重新对**完全相同归档**做摘要和镜像身份验证。不要把本地镜像 ID 写作仓库 digest。
2. 对最终组装版运行要求的手机/电脑 Lighthouse 与性能回归，保留原始 JSON；首页 LCP 未达目标须如实记录。重新校验当时生产车型、图片、来源指纹及安全配置；若目录变化，重算索引资格、重新组装站点并重跑隔离验收。
3. 真正切换前再制作最新 SQLite 一致性备份和上传/证书/配置/旧镜像归档，并实际恢复校验；确认单实例切换可在 5 分钟中断上限内完成。沿经验证的 Runbook，先 auth 后 web，保留现有卷、账号和安全保护；绝不执行 `down -v` 或以测试库替换生产库。
4. 切换后检查 HTTPS、核心路由、手机/电脑正文、权限、Sitemap 与 404，连续监控至少 30 分钟。若故障，先恢复旧 auth/web/site/Caddy，保留**最新**生产数据库及上传文件；旧 auth 必须只读挂载与切换时目录一致的 `auth/catalog.json`，以防旧种子补入历史记录。
5. 仅在正式部署稳定后，通过真实 Search Console Live Test 核对 Geely Monjaro、Zeekr 9X、BYD 等英文样页和 `noindex` 样页；确认 Google 抓到真实正文，再提交根 Sitemap、少量合格 URL 索引请求，并分别监控实际收录、英文曝光、自然点击、注册和有效询盘。

下一阶段英文 SEO 建议继续审核当前未合格车型和 43 个未审核英文品牌，并以海外采购意图完善英语内容；阿拉伯语、俄语待真实本地化审核后再开放索引。不得以中文页面数量、技术资格或 Sitemap 数冒充海外搜索效果。
