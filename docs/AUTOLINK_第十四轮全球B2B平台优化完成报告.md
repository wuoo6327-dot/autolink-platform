# AUTOLINK 第十四轮全球 B2B 平台优化完成报告

**状态：第十四轮主体于 2026-10-13 13:25:35 UTC 上线，公共 CSS 的 robots 精确修复于 14:00:12 UTC 上线；两次各 30 分钟的生产监控均完成，核心验收通过，未发生回滚。** 本轮没有启用 Stripe、Airwallex、真实扣款，也没有修改会员价格或权益、合并支付 PR #13/#14。以下分别标明隔离验收与真实生产结果。

## 1. 基线与真实目录

- 从 `origin/codex/round12-sitemap-js-20261012` 的 `fda95d7` 建立 `codex/b2b-round14-20261013`。该分支承接已上线 SEO 与首页脚本修复；支付实现提交 `d6844ee` 不是候选祖先。`main` 未被覆盖或强推。
- 2026-10-13 对生产公开 API 与 SQLite 一致性快照只读核对：**244 个公开车型、53 个公开品牌**，数据库总数为 **270 个车型、60 个品牌**；公开目录 ID 与隔离候选完全一致。第二次上线后再次只读核对，数据库仍为 270/60，用户 7、买家需求 0、商家草稿车源 1，`quick_check=ok`。两种车型统计口径不混用。
- 同次只读检查中，公开供应商和已审核公开车源均为 **0**。切换前快照有 1 条已批准的商家申请、1 条草稿车源、7 个用户、0 条真实买家采购需求；这些私有记录未作为公开供应展示。车型页面继续明确标为车型参考，不把它们写成现货或厂家授权。
- 发布站点从当时真实生产目录复制，仅覆盖审查通过的 11 个业务前端文件；另一个小版本仅覆盖 `robots.txt`。生产特有车型图片等资源继续保留，没有使用旧种子覆盖 SQLite 或重新生成 244 个公开车型。

## 2. 本轮实际改动

| 模块 | 变更 |
| --- | --- |
| 车型详情到采购需求 | 服务端初始 HTML 和交互页均增加车型直达采购需求的入口，携带真实车型 ID 与语言；供应商车源入口单独保留。 |
| 买家登录与表单 | 未登录时保存 `returnTo`；从登录切换到注册继续保留所选车型。选中车型后从当前公开目录带入品牌、年份和动力；加入目的港、配置等输入。草稿在同一浏览器会话中按账号暂存 24 小时，成功提交及退出登录时清除；共享同意不暂存。 |
| 需求提交与跟踪 | 后端固定车型的目录事实并保存所需配置；同一车型的重复请求受现有防重规则拦截，不同车型不会误判。成功显示真实 `REQ-` 编号，买家中心可查；状态操作防连续点击并提示结果。 |
| 车型查找 | 车型参考目录加入品牌、年份、能源类型筛选；支持已审核英文名称匹配，组合动力可按单个类型筛选。买家目录分别提供采购需求与已审核车源入口，空结果保持明确提示。 |
| 管理员跟进 | 复用既有后台、询盘表及审计表，增加真实采购需求和供应商询盘列表、买家关联与内部跟进备注。后台每次读取/写入均复核管理员身份；备注不自动通知买家，也不改变询盘状态。 |
| 商家与车源 | 没有修改商家准入、审核或公开规则。隔离浏览器检查商家申请页可显示草稿状态、待补资料和公开条件；未审核车源仍不进入公开列表。 |

主要代码：`auth/app.py`、`auth/buyer_service.py`、`auth/trade_service.py`、`auth/seo_service.py`、`site/buyer/app.js`、`site/trade/app.js`、`site/trade/model-directory.mjs`、`site/trade/directory-locales.js`、`site/trade/model-reference.css`、`site/admin/app.js`、`site/robots.txt` 及对应静态入口版本号。发布工具新增 `scripts/round14_cutover.py`；新增/扩展测试为 `auth/test_buying_requests.py`、`auth/test_current_catalog_seo.py`、`tests/test_model_directory.mjs`、`tests/round14_browser_qa.cjs`。首页主脚本、首页视觉、会员及支付实现没有修改。

## 3. 隔离测试与安全结果

| 验收项 | 实际结果 |
| --- | --- |
| 后端全套（本机源码） | **运行 232 项，5 项跳过，其余通过**；包括买家、商家、管理员权限和 SEO 回归。 |
| 买家采购链路 | Chrome 与 Playwright WebKit 的 390px 手机、1440px 桌面均通过：匿名跳登录及注册返回、车型和英语保留、填写后刷新保留、真实编号、买家中心查找、关闭状态提示；页面 JS 错误 0，横向溢出 0。测试仅用隔离库和合成账号。WebKit 测试不能等同于真实 Safari 设备测试。 |
| 管理员和商家 | Chrome/WebKit 隔离浏览器可查看管理员真实需求、写入内部备注；普通买家请求后台接口返回 403。商家申请页可见草稿、缺失资料及待审核提示。HTTP 测试中匿名 401、买家 403、恶意 Origin 403、管理员 200。 |
| 九语言及首页 | 既有首页九语言、Canonical、noindex、手机菜单、导航和关键脚本失败回退测试通过；买家需求页九语言均能打开并保留所选车型，HTML `lang` 与需求页标题正确。正式公网再次通过九语言首页与非关键脚本失败恢复，WebKit 手机菜单的买家/商家入口可见且 JS 错误 0。首页代码、静态首页文件哈希及 Web 镜像本轮未改变。 |
| SEO 资格 | 当前目录隔离测试维持 **227 个可索引车型 URL**（50 英文、177 中文）和 10 个英文品牌 URL；其余语言继续按原有审核规则 noindex。全部 244 车型、53 品牌的既有 SSR、Canonical 与索引政策测试通过。 |
| 公网只读 SEO 探针 | `robots.txt`、根 Sitemap、三个子 Sitemap、Geely Monjaro 初始 HTML、公共车型 CSS 均返回 200；根 Sitemap 为 3 个子文件，车型子文件 227 URL、品牌子文件 10 URL。Google Search Console 的 “Couldn’t fetch” 与首页主脚本 “Other error” **未在本轮获得后台状态验证**，公开 HTTP 200 不能代替 Google 抓取结论。 |
| 源码安全 | Gitleaks 当前目录与全部本地 Git refs 均为 0 发现；Trivy 文件系统为 0 阻断发现。历史支付报告的 Docker 镜像标签被精确限定为单文件误报例外，未允许任何凭据前缀或支付实现进入本分支。 |
| 候选镜像安全 | 阿里云原生 AMD64 构建的 Auth 镜像 ID 为 `sha256:87e19b1892d25bd79ccfce83f98e2658f20c9ad258db870f1224cd8434494afd`，完整归档 SHA-256 为 `61685e09133dfd0d45487f28cf2a0a0ddf3ce466cfd848027e05b8e4d6451c91`；Trivy HIGH/CRITICAL 漏洞 0、密钥 0。此为本地镜像 ID，不是 Registry Manifest Digest。 |
| 原生 AMD64 后端与回滚 | 阿里云主机内 **运行 232 项，5 项跳过，其余通过**；真实生产 SQLite 副本上的候选→旧版→候选回滚演练三阶段均为 270/60 总记录、244/53 公开目录，`integrity_check=ok`。最初一次测试因隔离挂载遗漏失败，修复 QA 挂载后完整重跑通过，原始日志保留。 |
| GitHub 安全 CI | 当前 PR #15 提交 `12c4891` 的两项 `source-security` 作业均实际成功：[运行 38406530960](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38406530960)、[运行 38406524195](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38406524195)。当前源码、Git 历史、依赖与 Dockerfile 扫描步骤均成功；仅公开仓库中的私有报告上传步骤按设计跳过。 |
| 正式公网只读验收 | 全部 244 个车型与 53 个品牌英文 URL 的 HTTP、Title、Description、H1、Canonical 和 index/noindex 规则匹配当前审核字段；50 个英文车型和 10 个英文品牌具备技术索引资格，未知车型与品牌均返回 404。244 个中文车型页中 177 个保持 index。Chrome 和 WebKit 在手机 390px、电脑 1440px 上通过英文别名搜索、品牌/年份/能源筛选、无结果提示、车型→登录→注册返回链路，横向溢出及页面 JS 错误均为 0。匿名私有接口 401，恶意来源 POST 403。 |
| 生产备份与恢复 | 切换前 SQLite 在线一致性备份及认证卷其他文件、证书、配置、旧 Auth/Web 镜像归档均保存；隔离恢复后 `integrity_check=ok`、外键违规 0，全部表计数一致。未执行生产真实客户修改、删除或密码测试。 |

原始隔离日志和浏览器 JSON 位于本地忽略目录 `tests/results/round14/`，原生 AMD64 日志与发布锁位于阿里云 `/home/admin/autolink-round14-qa-20261013/`、`/opt/autolink-releases/ecee142-round14-20261013/round14-evidence/`。生产 SQLite 与持久卷在切换时沿用原卷，没有以测试记录覆盖真实数据；生产浏览器验收只读，没有创建模拟客户询盘。

## 4. 正式发布、备份与实时状态

代码镜像来自 `ecee142`，发布工具已提交到草稿 [PR #15](https://github.com/wuoo6327-dot/autolink-platform/pull/15)，未合并 `main`。阿里云 `Ubuntu-fkag` 经用户授权，以无重启方式仅追加本机 `codex.pem` 对应公钥到 `admin` 的 `authorized_keys`，原文件另有备份；私钥未发送或上传。SSH + tmux 代替了易受浏览器切换影响的 Workbench。

切换前从实际数据库路径 `/var/lib/docker/volumes/autolink-demo_auth_data/_data/autolink-auth.sqlite3` 备份到 `/opt/autolink-backups/round14-20261013T132136Z/`：SQLite 一致性快照 SHA-256 `996f520c9d20df17ffb9c70199f1e9e5a6d09d163fb6b9295b0629de1d5fdd6e`，同时保存认证卷的其他文件、Caddy 证书与配置卷、原发布目录及旧 Auth/Web 镜像。全部归档校验通过；隔离解压与 SQLite `integrity_check`、`foreign_key_check`、全部表记录数核对通过。发布锁为 `/opt/autolink-releases/ecee142-round14-20261013/round14-release-lock.json`；正式切换未重新构建、拉取镜像或替换数据库/持久卷。

UTC 13:25:08 开始切换，13:25:35 核心公网探针通过；按 Auth 健康→Web 健康执行，实际运行 Auth 镜像 ID 为 `sha256:87e19b1892d25bd79ccfce83f98e2658f20c9ad258db870f1224cd8434494afd`，Web 仍为 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`。第一段自动监控于 **13:56:47 UTC** 返回 `completed`、退出码 0、探针失败 0、容器重启 0，证据在 `/opt/autolink-release-state/round14-20261013/ecee142-round14-20261013/`。

公网只读验收已检查全部 244 个车型和 53 个品牌页面、50 个英文车型与 10 个英文品牌的 index 状态、未知页 404、匿名权限 401/恶意 Origin 403，以及 Chrome/WebKit 的手机和桌面找车入口；没有在生产提交模拟客户询盘。九语言首页、非关键脚本失败回退、车型样式和 Sitemap HTTP 也通过。Google Search Console 后台的 `Couldn't fetch` 与首页脚本 `Other error` 在本轮仍未取得后台实时结果，不能把 HTTP 200 写成 Google 已接受或收录。

发现 `/buyer/buyer.css` 被 robots 的 `/buyer/` 规则覆盖后，另建仅增加 `Allow: /buyer/buyer.css` 的小版本 `e7c48f2`。原生隔离环境验证公共 CSS 可抓取、私有路径仍拒绝、候选→当前版→候选版回滚成功。第一段监控完成后，重新从当时生产制作 `/opt/autolink-backups/round14-robots-20261013T135742Z/`，SQLite SHA-256 为 `285ad37845e84fea7cad29c8fc42897def517a3e6e978fdb2d051386bdc0bdb9`；归档与隔离恢复通过。14:00:12 UTC 第二次切换通过公网核心探针，Auth/Web 镜像 ID 均与第一版相同，发布锁 SHA-256 `0a3cc2118b5facb6be8cf2fb6401725b1e03fd5b2ac1ceaa538f66510adddc76`。真实公网再次验证 CSS 200 且 Googlebot 规则允许、私有接口 401，全部 244/53 页面及 Chrome/WebKit 手机电脑公开流程通过。第二段自动监控于 **14:31:27 UTC** 写入 `completed`，运行器退出码 0、探针失败 0、容器重启 0、未触发回滚；证据位于 `/opt/autolink-release-state/round14-robots-20261013/e7c48f2-round14-robots-20261013/`。

第二段结束后的最终只读复核：正式 Auth/Web 容器均为 healthy、重启数 0，运行镜像 ID 与发布锁一致；生产 SQLite `quick_check=ok`、外键违规 0，总目录仍为 270/60，用户 7、买家需求 0、商家草稿车源 1。公网首页、`robots.txt`、根 Sitemap、公共车型 CSS 和 Geely Monjaro 英文详情均返回 HTTPS 200。隔离 QA 容器和合成测试令牌已清理；生产数据库与持久卷没有被替换。

回滚目标为当前稳定的 `/opt/autolink-releases/ecee142-round14-20261013/`；若主体版自身发生关键故障，上一安全版本为 `/opt/autolink-releases/40d685b-round12-20261012/`。发布脚本只用本地固定镜像，先恢复 Auth 并等健康，再恢复 Web；**沿用切换时最新的数据库与上传文件**，不执行 `down -v`、清库或以旧快照覆盖新客户数据。两次隔离回滚演练均通过；目前实际生产回滚次数为 0。

公网英文首页使用同一台 Mac、同一 Lighthouse CLI 在 robots 小版本切换前后各做手机与电脑 **3 次冷启动**，原始 JSON 位于本地 `tests/results/round14/production-lighthouse/` 与 `production-lighthouse-robots-final/`。手机 Performance 中位数均为 **65**，LCP 中位数 **6540→6394 ms**、TBT **31→26 ms**；电脑 Performance 中位数均为 **90**，LCP **542→539 ms**、CLS 均约 **0.070**。手机 LCP 六次中五次超过 2.5 秒，目标**未达成**，且样本波动明显；这些小样本不能代表海外真实用户。首页文件 SHA-256 在旧版、主体版和 robots 小版本三者完全一致，Web 镜像也未更换。性能问题留作独立优化，不修改真实车型资料或隐藏功能。

## 5. 未完成事项与下一阶段

- Google Search Console 的 Sitemap `Couldn't fetch`、首页主脚本 `Other error` 和 Google 实际收录情况尚无本轮后台实时验收证据。公网可访问及技术索引资格不等于 Google 已抓取或已收录。
- 手机英文首页三次冷启动的 LCP 中位数为 6394 ms，未达到 2.5 秒目标；本轮没有为了追分重做首页。服务器最终检查时系统盘使用率约 82%，后续应按既有保留策略管理归档空间。
- 生产真实买家需求目前为 0，公开已审核车源为 0；询盘提交、管理员跟进及商家审核链路通过隔离合成数据验证，但不能据此宣称已有真实海外采购转化。

下一阶段运营重点是完善真实已审核供应资源和买家询盘响应时效，持续在 Search Console 观察英文车型曝光与已收录数量，并区分访问、注册和有效采购询盘；支付开发继续独立搁置。

## 6. 后续账号权限与商家资料表单修复（2026-10-13）

原第十四轮上线后，用户报告一个买家账号被错误地保留为商家身份并进入供应商中心。只读检查确认该账号仍为 `MERCHANT`，仅有未提交的企业草稿和 3 份私有审核文件，没有公开车源或交易。用户明确要求该账号只作买家，且同一邮箱不能同时拥有买家与商家权限。

补充候选 [PR #16](https://github.com/wuoo6327-dot/autolink-platform/pull/16) 在密码、邮箱验证码和 Google 登录入口执行同一身份约束，拒绝从商家入口静默升级买家身份；供应商 API 再次校验服务器端角色。管理员可对未提交、未公开、无交易的商家草稿执行“清除供应商权限”，并撤销全部会话。另增加有严格业务记录阻断条件的“永久清除个人资料”管理员操作；此操作**没有**对任何生产账号执行。买家端恢复入口和商家端的身份提示同步完善。

用户随后指出企业资料页“主营品牌／主要市场”多选面板过长，且点击“添加”后不会收起。补充提交 `b8502a8` 将电脑端面板改为浮层、手机端改为底部选择区，已选项以紧凑摘要保留在按钮中；“完成”、添加自定义项、空自定义项的“添加”、Escape 和点击外部均可收起。保留原有隐藏字段及保存接口，不改变企业资料审核规则。源码改动为 `site/supplier/company-fields.js`、`site/supplier/console.css`、`site/supplier/bootstrap.mjs`、`site/supplier/index.html`。发布与回滚工具补充于 `41927bd`。

补充验收实际结果：阿里云原生 linux/amd64 后端运行 235 项、5 项跳过，其余通过；复制生产数据库上的买家身份纠正、会话撤销、私有文件保留和合成账号资料清除通过。隔离回滚演练依次通过候选版、旧安全版、恢复候选版，三阶段数据库完整性为 `ok`，总目录 270/60、公开目录 244/53。Chrome 与 Playwright WebKit 的手机、电脑视口均通过真实隔离商家申请页的多选、收起、Escape、无横向溢出及无表单位移检查。GitHub PR #16 最新两项 `source-security` 作业实际通过；候选 Auth 镜像 Trivy HIGH/CRITICAL 0、密钥 0。旧版已有的 7 项法律页头部测试失败在未改动基线可复现，与本次权限和多选修复无关。

2026-10-13 **15:59:47 UTC**，补充版完成生产核心切换，Auth 镜像 ID 为 `sha256:8c14559850ac1ebe5d778415adb6e1b5777e75b5424fe8677ae402ada81242e0`，Web 镜像 ID 仍为 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`。运行代码提交为 `b8502a8`，完整 Auth 归档 SHA-256 为 `63a428cd1ef3988a191affc37ec37da5c15486e5093f807facedb7df64437bf0`；它们是本地镜像 ID 和归档哈希，并非 Registry Manifest Digest。发布锁位于 `/opt/autolink-releases/7fefb90-account-role-20261013/account-role-release-lock.json`。切换前最新全量备份位于 `/opt/autolink-backups/account-role-20261013/final-20261013T155735Z/`，SQLite 快照 SHA-256 为 `2e9787528857222709f8a9a929871947ee5dcff7e7aa870123dde501ae7cb27c`，上传文件、Caddy 证书／配置、旧发布目录及旧镜像均已隔离恢复校验。用户指定账号纠正前另做 SQLite 一致性备份 `/opt/autolink-backups/account-role-20261013/pre-target-role-20261013T1600Z/`，恢复验证通过。

生产纠正通过与隔离演练相同的受保护服务方法执行一次：账号变为 `BUYER`，旧会话数 0，原 3 份私有审核文件保留，审计记录 1 条。生产数据库未被替换，纠正后总目录仍为 270/60，用户 8，买家采购需求 0，商家车源草稿 1，`quick_check=ok`、外键违规 0。上线后只读检查了全部 244 个车型和 53 个品牌英文页面：297 页 HTTP 200、Title/H1/Canonical 齐全，未知车型 404。Chrome 与 WebKit 的手机、电脑视口均通过买家登录、商家登录和代表车型详情的公网匿名访问，未在生产创建测试账号或询盘。

30 分钟自动监控于 **16:30:45 UTC** 写入 `completed`，运行器退出码 0，全程 `MONITOR_FAILURE` 0、核心探针通过 32 次、资源检查 6 次，**未发生回滚**。最终只读复核确认 Auth/Web 镜像 ID 与锁定值一致、均为 healthy、重启数均为 0；SQLite `quick_check=ok`、外键违规 0。生产匿名请求私有证件、管理员用户列表和商家申请接口均返回 401。公网 Chrome 与 WebKit 的 390px 手机、1440px 电脑在买家登录、商家登录及代表车型页共 12 次访问中均为 HTTP 200、横向溢出 0；这不是目标买家账号的真实密码登录测试。全量页面只读结果位于 `/opt/autolink-releases/7fefb90-account-role-20261013/post-release-public-pages.json`，自动监控状态与日志位于 `/opt/autolink-release-state/account-role-20261013/7fefb90-account-role-20261013/`。PR #16 在发布工具提交 `41927bd` 后的两项 `source-security` 实际通过：[运行 38426223354](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38426223354)、[运行 38426230936](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38426230936)。回滚目标为 `/opt/autolink-releases/e7c48f2-round14-robots-20261013/`，回滚只恢复代码和固定镜像，保留最新数据库、上传文件和证书卷。此补充没有启用支付，没有修改会员收费，也没有合并 `main`。
