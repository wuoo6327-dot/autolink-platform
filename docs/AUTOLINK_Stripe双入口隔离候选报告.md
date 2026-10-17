# AUTOLINK Stripe 双入口隔离候选报告

日期：2026-10-17。状态：**仅隔离候选；生产支付未启用，也未部署本候选。** 2026-10-17 生产服务器上已建立权限为 `0600` 的正式配置文件 `/home/admin/autolink-stripe-live-20261017/private/stripe-live.env`，但正式 Stripe 密钥、账户 ID、支付方式配置及买家／供应商 Webhook 签名密钥仍为空；三个正式收款开关均为 `false`。此文件本身不代表 Stripe 正式凭据已经创建或真实扣款可用。

发布准备分支 `codex/stripe-buyer-supplier-20261017`，草稿 PR [#21](https://github.com/wuoo6327-dot/autolink-platform/pull/21)。Auth 支付代码基准提交 `187aff32757976827548134ec5914c4c3725f74f`；其后增加独立上架服务条款与人工票据申请前端，旧候选镜像只包含此前 Auth 代码，不能充当最终前端发布包。生产 Auth 镜像仍为 `sha256:e56bb2c05766aeda08db14db4a6931e6ba19f117926a9f24927b7edaccf3be2c`，Auth/Web 均健康，`PAYMENTS_ENV`、买家和供应商真实收款开关均未设置。阿里云根分区可用空间约 2.3 GB（使用率 96%）。

## 范围与基线

- 从 `2797d12`（`codex/supplier-brand-auth-on-seo-20261014`）建立独立分支 `codex/stripe-buyer-supplier-20261017`。保留此前生产安全、SEO、询盘和商家审核流程；没有合并旧支付 PR，也没有修改真实生产数据。
- Stripe 为买家会员和供应商上架服务的共同收款商户，分别使用独立的订单、Checkout 和 Webhook 路由。Airwallex 仅保留关闭的接口名称，不参与付款；没有自动续费。
- 生产 Auth 容器只读检查：运行镜像 ID `sha256:e56bb2c05766aeda08db14db4a6931e6ba19f117926a9f24927b7edaccf3be2c`，Auth、Web 均健康；生产容器中的 `PAYMENTS_ENV`、两个支付开关、`STRIPE_LIVE_RELEASE_READY` 与 Stripe 密钥均未配置。线上真实扣款仍为关闭状态。

## 已完成的隔离开发

- 买家会员后端固定 USD 首购／续费价格：月度 1.99／19.90，季度 9.99／29.99，年度 39.99／99.99。每个账户的首购资格只可用一次。只有已签名且身份、金额、币种匹配的 Stripe 付款确认才开通会员；重复回调幂等。买家页面保留现有布局，并仅在后端开放时显示 Stripe 按钮。
- 供应商上架服务使用独立订单表，固定 USD 40／140／200 每 SKC 每季度的现有价格。只有已核准企业的所有者、已审核且具备当前实拍图、有效资料的车源可创建付款单。结账前须主动确认三个月服务规则，后端保存同意版本和时间。Stripe 已验证的付款将未变更且符合条件的车源当天置为公开；一个 SKC 覆盖同一供应商的同车型同年款配置。到期时公开查询立即隐藏该 SKC；全额退款且无其他有效付费期时，相关车源转为 OFFLINE。部分退款及争议保留人工处理。供应商可查看自己的付款记录。
- 两入口分别有关闭开关和 Webhook 签名密钥。生产模式另需显式 `STRIPE_LIVE_RELEASE_READY=true`。前端不能提交实际支付金额或凭返回页面开通服务。两个只供操作员使用的订单对账命令可检查和恢复不确定的 Checkout 结果。
- 实际修改：`auth/app.py`、`auth/buyer_service.py`、`auth/Dockerfile`、`auth/membership_payments.py`、`auth/supplier_listing_payments.py`、`auth/reconcile_membership.py`、`auth/reconcile_supplier_listing.py`、`auth/test_membership_payments.py`、`auth/test_supplier_listing_payments.py`、`compose.yaml`、`.gitleaks.toml`、`site/index.html`、`site/assets/membership-checkout.js`、`site/assets/membership-checkout.css`、`site/assets/supplier-stripe-checkout.js`、`site/assets/supplier-program.js`、`site/buyer/app.js`、`site/supplier/app.js`、`site/supplier/index.html`。后续候选增加 `site/legal/supplier-listing-terms.html`，修改 `Caddyfile`、`site/support/app.js` 和上述供应商脚本，为上架服务提供单独的双语条款与人工核验后开票申请入口；不自动开票，不产生额外收费。

## 已验证的事实

| 检查 | 实际结果 |
| --- | --- |
| Stripe Test Mode API | 与服务器隔离环境中配置的商户账户一致；创建并取回 USD 1.99 会员及 USD 40 供应商测试 Checkout。会员沙盒订单 `70330cd7-b5fc-41f7-91a1-4e627cd17e2b` 已用 Stripe 官方测试卡完成付款；Stripe API 返回 `livemode=false`、`status=complete`、`payment_status=paid`、`amount_total=199`、`currency=usd`。供应商沙盒 USD 40 付款也已由所有者完成，详见下行。 |
| 供应商 Stripe Test Mode 实际回调 | 阿里云原生 AMD64 隔离容器运行候选源码及隔离数据库，未挂载生产数据卷。Stripe CLI 将测试事件 `checkout.session.completed`（`evt_1URYNGD11yCRmchazEXAIAXR`）转发到独立供应商 Webhook，服务返回 HTTP 200。隔离库 `PRAGMA integrity_check=ok`；一笔订单为 `PAID`、金额 4000 美分／USD，一条支付事件，测试车源状态 `ONLINE`，公开查询可见。隔离已付库快照 SHA256 `fe438607f05d077f8f32f05090ab001ebed2b2abd82be93962b05661dec1edc1`。这是沙盒付款，没有真实扣款。 |
| 供应商 Stripe Test Mode 实际全额退款 | 现有受限测试密钥调用退款 API 返回 HTTP 403、`more_permissions_required`。Stripe 沙盒后台的“Charges and Refunds”写权限同时覆盖创建、更新和捕获收款，超过所有者仅增加测试退款权限的授权范围，因此没有扩大密钥权限。改在 Stripe 沙盒交易后台对上述唯一 USD 40 测试订单全额退款；页面显示“已退款”。Stripe CLI 将真实 `charge.refunded` 测试事件 `evt_3URYNFD11yCRmcha0GoYWGuT` 投递到阿里云隔离 Webhook，返回 HTTP 200。隔离库 `refund_status=FULL`、车源 `OFFLINE`、支付事件各一条，`PRAGMA integrity_check=ok`；公开详情返回 HTTP 404。退款后隔离库一致性快照 SHA256 `fef0be8b2376bdca4cf3a0fd674504ac0e921f5911cb9c84c75c85673f6c3292`。没有真实资金往来。 |
| 本机完整后端测试 | 本轮最终源码共运行 267 项，其中 262 项通过、5 项跳过；包含权限、金额、首购、重复回调、退款、付费上架及不确定订单恢复。 |
| AMD64 支付与车源专项 | 本轮最终镜像在 Mac Docker 的 `linux/amd64` 隔离容器内，以无外网、无生产卷方式运行 28 项支付专项，通过。阿里云原生 AMD64 以候选源码只读挂载、无外网、无生产数据库方式运行支付／车源／公开权限 43 项，通过；公开 SEO 用例读取现有生产站点素材的只读挂载。第一次未挂站点素材时，Sitemap 用例因缺少资料失败，补全隔离依赖后重跑通过。 |
| 静态及配置检查 | 修改过的 JavaScript `node --check` 通过；使用非生产占位变量的 `docker compose config --quiet` 通过；`git diff --check` 通过。 |
| 安全扫描 | 本轮 Gitleaks 对候选目录扫描约 308.37 MB，未发现泄露；Trivy 文件系统与最终候选镜像均报告 0 项 HIGH/CRITICAL 漏洞。 |
| 票据入口及新版条款复核 | 新增条款 HTML 结构校验、Caddy 独立路由、修改过的 JavaScript 语法和差异检查通过。2026-10-17 对当前候选目录再次运行 Gitleaks（308.40 MB，0 泄露）与 Trivy 文件系统 HIGH/CRITICAL 扫描（0 项）。隔离 AMD64 完整回归因挂载路径首次漏 `/site`、再次漏 `/tests` 分别出现测试资料找不到的错误；补齐 `/site` 后的 267 项运行中仅 7 项缺 `/tests` 夹具，其余无失败；单独补跑这 7 项，7/7 通过。两次结果合并覆盖全部 267 项（262 通过、5 跳过），不能把其中任何一次失败的运行写成单次全绿。原始日志位于本机 `deployment/artifacts/stripe-both-20261017/`。 |
| 生产只读预备份及隔离恢复 | 完整生产文件归档 SHA256 `8efbb9bf1eb5ed225c445a7428a102bec9b13e04933fd9ea204b2361d09d6d61`，保存在本机私有目录 `/Users/oo/.codex/private/autolink-preflight-20261017/production-files.tar.gz`，权限 0600；`gzip -t` 通过。隔离解包后可读取当前发布锁 `ef551a8e00e69c8a4a0fda02c17a3a9330833de0`、Caddy 数据卷与配置卷，归档内 SQLite `quick_check=ok`、8 个账号。单独的 SQLite 一致性备份 SHA256 `ad9be11ca37a077ee8d75198cada0939720c6271fbf2c6262f34db92c346d65d`，`integrity_check=ok`。这些均是预发布备份；生产切换前仍需重新制作当时最新版本。 |

GitHub Actions 在最终支付代码提交 `187aff3` 上实际运行两次 `source-security`，运行编号 `39027901352` 与 `39027904598` 均通过；包含当前源码、历史记录和依赖扫描。上述结果属于候选代码验收，不代表生产支付已启用。

最终候选镜像以 `linux/amd64` 构建并保存在本机，标签 `autolink-stripe-both:qa-20261017-r4`；本地 OCI manifest list 身份为 `sha256:36d3e93c408757b8ef82f59a4c4ba4457c39cee6a037088d466b636a67851a4e`，不冒充远程 Registry Manifest Digest。压缩归档位于 `/Users/oo/Documents/ChatGPT/Space Auto/deployment/artifacts/stripe-both-20261017/autolink-stripe-both-qa-r4-amd64.tar.gz`，SHA256 为 `bd7786b3adc1b1fc7d52400d8c51042216001b9d9bf44c9f783f4925613faeb4`。镜像内 `app.py`、`supplier_listing_payments.py`、`trade_service.py` 哈希与对应源文件相符。本轮最终镜像已经在本机 Docker AMD64 容器运行支付专项；阿里云原生 AMD64 验证使用同源候选源码只读挂载至旧 QA 基础镜像，尚未将最终镜像归档加载到阿里云。候选未接入生产 Compose。

为控制阿里云磁盘使用，本轮没有向阿里云加载新镜像；本机固定归档保留，运行中的生产 Auth 和 Web 容器继续保持健康。

## 尚未达到真实收款上线门槛

1. 所有者提供香港公司注册证明书与商业登记证的图片。证明书显示法定名称 `ZING HEI INTERNATIONAL TRADING LIMITED / 正汽國際貿易有限公司`、编号 `80964737`，签发日 2026-08-04；商业登记证显示同一公司名称、营业地址 `FLAT/RM 917A BLK A 9/F NEW MANDARIN PLAZA NO 14 SCIENCE MUSEUM RD TSIM SHA TSUI HONG KONG`，有效期至 2027-08-03。候选会员条款、通用条款和隐私政策已填入该主体及明确标为“商业登记证所载营业地址”的地址，没有将其冒称为已核实的注册办事处地址。供应商入驻协议有已签署正文指纹和版本约束，因此本次没有改动该协议；需要另行按签署版本升级流程处理。所有者另提供注册办事处地址中文 `九龍尖沙咀科學館道14號新文華中心A座9樓917A室`、英文 `UNIT 917A, 9/F., TOWER A, NEW MANDARIN PLAZA, NO.14 SCIENCE MUSEUM ROAD, TSIMSHATSUI, KOWLOON, HONG KONG.`，与商证营业地址指向同一单元；候选法律页已分别标注两种地址来源。该注册办事处地址尚未以最新公司资料报告或 NNC1/NR1 独立核验。会员页仍标“预览稿”；已批准的退款规则和价格保留。供应商付费上架规则已整理为 `docs/AUTOLINK_供应商上架付费条款审阅稿.md`，退款资格、供应商违规或资料变更后的处理规则、3 个工作日确认及资料齐全后 10 个工作日给出结果的时限已获所有者批准。生效日、正式中英文页面、票据申请与发放流程仍未定稿，不能以 Stripe 实名审核或这些证书代替服务条款审定。证件图片不纳入公开代码库。
2. 买家会员已有一笔 Stripe Test Mode 测试卡成功付款。2026-10-17 17:55（Asia/Bangkok）前后，阿里云隔离数据库对账结果为 `PAID`，重复对账返回 `alreadyProcessed`；隔离库恰有 1 个有效会员期、1 条已付记录和 1 次首购使用记录。买家 Webhook 成功事件测试目前仍为模拟签名事件。供应商成功付款和全额退款已完成真实 Test Mode 事件投递；两个入口的失败付款、争议端到端记录及买家实际 Webhook 投递仍缺失。
3. 所有者已批准“企业和车源审核后付款、Stripe 确认付款后当天上线、服务三个月、到期或全额退款后下线、部分退款和争议人工处理”。本轮已在候选代码实现，并用 Stripe Test Mode 实际供应商付款及全额退款两类真实测试事件验证上线与下线。到期后公开查询会立即隐藏车源，数据库原始状态可暂留 `ONLINE`，商家界面按公开可见性显示暂停。部分退款和争议仍仅经自动化模拟事件验证；正式收款前还需确认服务条款与运营处理流程。
4. 阿里云主机剩余空间约 2.3 GB（96% 已用）。本轮仅加载隔离候选镜像并运行测试，没有在生产主机构建、清理镜像或替换运行容器。正式发布前仍需最新生产备份、恢复与回滚演练。
5. 本候选未做真实生产部署、真实扣款、生产数据迁移或线上浏览器端到端付款测试。九语言新文案已写入，但仍需业务语言审核。
6. Stripe 测试模式 API 密钥页在本次浏览器核查中直接显示了完整测试密钥，浏览器工具返回内容因此包含测试凭据。没有将其复制到代码、报告正文或其他服务；继续使用前应由账户所有者轮换测试密钥并更新隔离环境。该情况不涉及生产收款密钥，生产支付依旧关闭。
7. 供应商提出企业发票需求。候选已在已付款订单旁加入“申请发票”，通过现有支持单收集订单号、企业抬头、适用登记号、账单地址和接收邮箱，明确由人工核对付款与退款后出具香港公司商业发票。尚无自动发票编号、下载入口或退款后自动更正；香港商业发票不能冒充中国大陆增值税专用发票。Stripe Checkout 的自动生成已付发票是另一个可选方案，香港公开价格当前为交易额的 0.4%，每张封顶 USD 2；**尚未启用，也未计入本候选成本**。需先核对商户实际合同价格、受限密钥权限、收件人字段和财务流程，再决定是否启用；不能静默增加收费功能。
8. 生产法律页 `/terms`、`/membership-terms`、`/privacy` 等仍显示“预览稿／待确认”，其中包含未定稿的生效日、个人资料留存期限及争议条款。新上架服务页不能替代这些通用文件；现有已签署的供应商入驻协议带版本和内容指纹，不得原地改写。正式收款前需完成这些具体条款的审定与版本发布，不能因公司证书已提供而跳过。
9. 最新生产备份正在以只读方式传输；完成压缩归档 SHA256、隔离恢复、旧镜像归档与回滚演练前，不具备生产切换条件。该过程尚未修改生产数据或容器。

## 下一步

以最新公司资料报告或 NNC1/NR1 核实所有者提供的注册办事处地址，并审定完整法律页与供应商付费条款。已提供按订单号申请企业抬头商业发票的人工流程；具体票据必须由财务核对付款、退款及企业信息后出具、更正。此次法律 HTML 更新发生在上一版候选镜像归档之后；发布前必须重新构建并验证镜像文件哈希，不能把旧归档称为包含最新条款。供应商沙盒实际付款、全额退款及 Webhook 已通过；仍须取得正式 Stripe 凭据，并在阿里云原生 AMD64 隔离环境验证最终镜像、买家 Webhook、失败付款及争议流程，完成生产备份、恢复与回滚演练。以上门槛通过后才可执行生产切换；两个真实支付开关继续保持关闭。
