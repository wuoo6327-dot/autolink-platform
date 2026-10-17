# AUTOLINK Stripe 双入口隔离候选报告

日期：2026-10-17。状态：**仅隔离候选；生产支付未启用，也未部署本候选。**

发布准备分支 `codex/stripe-buyer-supplier-20261017`，草稿 PR [#21](https://github.com/wuoo6327-dot/autolink-platform/pull/21)。最终支付代码提交 `187aff32757976827548134ec5914c4c3725f74f`；后续报告文字提交不改变镜像内应用文件。生产 Auth 镜像仍为 `sha256:e56bb2c05766aeda08db14db4a6931e6ba19f117926a9f24927b7edaccf3be2c`，Auth/Web 均健康，`PAYMENTS_ENV`、买家和供应商真实收款开关均未设置。阿里云根分区可用空间约 2.3 GB（使用率 96%）。

## 范围与基线

- 从 `2797d12`（`codex/supplier-brand-auth-on-seo-20261014`）建立独立分支 `codex/stripe-buyer-supplier-20261017`。保留此前生产安全、SEO、询盘和商家审核流程；没有合并旧支付 PR，也没有修改真实生产数据。
- Stripe 为买家会员和供应商上架服务的共同收款商户，分别使用独立的订单、Checkout 和 Webhook 路由。Airwallex 仅保留关闭的接口名称，不参与付款；没有自动续费。
- 生产 Auth 容器只读检查：运行镜像 ID `sha256:e56bb2c05766aeda08db14db4a6931e6ba19f117926a9f24927b7edaccf3be2c`，Auth、Web 均健康；生产容器中的 `PAYMENTS_ENV`、两个支付开关、`STRIPE_LIVE_RELEASE_READY` 与 Stripe 密钥均未配置。线上真实扣款仍为关闭状态。

## 已完成的隔离开发

- 买家会员后端固定 USD 首购／续费价格：月度 1.99／19.90，季度 9.99／29.99，年度 39.99／99.99。每个账户的首购资格只可用一次。只有已签名且身份、金额、币种匹配的 Stripe 付款确认才开通会员；重复回调幂等。买家页面保留现有布局，并仅在后端开放时显示 Stripe 按钮。
- 供应商上架服务使用独立订单表，固定 USD 40／140／200 每 SKC 每季度的现有价格。只有已核准企业的所有者、已审核且具备当前实拍图、有效资料的车源可创建付款单。结账前须主动确认三个月服务规则，后端保存同意版本和时间。Stripe 已验证的付款将未变更且符合条件的车源当天置为公开；一个 SKC 覆盖同一供应商的同车型同年款配置。到期时公开查询立即隐藏该 SKC；全额退款且无其他有效付费期时，相关车源转为 OFFLINE。部分退款及争议保留人工处理。供应商可查看自己的付款记录。
- 两入口分别有关闭开关和 Webhook 签名密钥。生产模式另需显式 `STRIPE_LIVE_RELEASE_READY=true`。前端不能提交实际支付金额或凭返回页面开通服务。两个只供操作员使用的订单对账命令可检查和恢复不确定的 Checkout 结果。
- 实际修改：`auth/app.py`、`auth/buyer_service.py`、`auth/Dockerfile`、`auth/membership_payments.py`、`auth/supplier_listing_payments.py`、`auth/reconcile_membership.py`、`auth/reconcile_supplier_listing.py`、`auth/test_membership_payments.py`、`auth/test_supplier_listing_payments.py`、`compose.yaml`、`.gitleaks.toml`、`site/index.html`、`site/assets/membership-checkout.js`、`site/assets/membership-checkout.css`、`site/assets/supplier-stripe-checkout.js`、`site/assets/supplier-program.js`、`site/buyer/app.js`、`site/supplier/app.js`、`site/supplier/index.html`。

## 已验证的事实

| 检查 | 实际结果 |
| --- | --- |
| Stripe Test Mode API | 与服务器隔离环境中配置的商户账户一致；创建并取回 USD 1.99 会员及 USD 40 供应商测试 Checkout。会员沙盒订单 `70330cd7-b5fc-41f7-91a1-4e627cd17e2b` 已用 Stripe 官方测试卡完成付款；Stripe API 返回 `livemode=false`、`status=complete`、`payment_status=paid`、`amount_total=199`、`currency=usd`。供应商测试卡付款尚未完成。 |
| 本机完整后端测试 | 本轮最终源码共运行 267 项，其中 262 项通过、5 项跳过；包含权限、金额、首购、重复回调、退款、付费上架及不确定订单恢复。 |
| AMD64 支付与车源专项 | 本轮最终镜像在 Mac Docker 的 `linux/amd64` 隔离容器内，以无外网、无生产卷方式运行 28 项支付专项，通过。阿里云原生 AMD64 以候选源码只读挂载、无外网、无生产数据库方式运行支付／车源／公开权限 43 项，通过；公开 SEO 用例读取现有生产站点素材的只读挂载。第一次未挂站点素材时，Sitemap 用例因缺少资料失败，补全隔离依赖后重跑通过。 |
| 静态及配置检查 | 修改过的 JavaScript `node --check` 通过；使用非生产占位变量的 `docker compose config --quiet` 通过；`git diff --check` 通过。 |
| 安全扫描 | 本轮 Gitleaks 对候选目录扫描约 308.37 MB，未发现泄露；Trivy 文件系统与最终候选镜像均报告 0 项 HIGH/CRITICAL 漏洞。 |

GitHub Actions 在最终支付代码提交 `187aff3` 上实际运行两次 `source-security`，运行编号 `39027901352` 与 `39027904598` 均通过；包含当前源码、历史记录和依赖扫描。上述结果属于候选代码验收，不代表生产支付已启用。

最终候选镜像以 `linux/amd64` 构建并保存在本机，标签 `autolink-stripe-both:qa-20261017-r4`；本地 OCI manifest list 身份为 `sha256:36d3e93c408757b8ef82f59a4c4ba4457c39cee6a037088d466b636a67851a4e`，不冒充远程 Registry Manifest Digest。压缩归档位于 `/Users/oo/Documents/ChatGPT/Space Auto/deployment/artifacts/stripe-both-20261017/autolink-stripe-both-qa-r4-amd64.tar.gz`，SHA256 为 `bd7786b3adc1b1fc7d52400d8c51042216001b9d9bf44c9f783f4925613faeb4`。镜像内 `app.py`、`supplier_listing_payments.py`、`trade_service.py` 哈希与对应源文件相符。本轮最终镜像已经在本机 Docker AMD64 容器运行支付专项；阿里云原生 AMD64 验证使用同源候选源码只读挂载至旧 QA 基础镜像，尚未将最终镜像归档加载到阿里云。候选未接入生产 Compose。

为控制阿里云磁盘使用，本轮没有向阿里云加载新镜像；本机固定归档保留，运行中的生产 Auth 和 Web 容器继续保持健康。

## 尚未达到真实收款上线门槛

1. 所有者提供香港公司注册证明书与商业登记证的图片。证明书显示法定名称 `ZING HEI INTERNATIONAL TRADING LIMITED / 正汽國際貿易有限公司`、编号 `80964737`，签发日 2026-08-04；商业登记证显示同一公司名称、营业地址 `FLAT/RM 917A BLK A 9/F NEW MANDARIN PLAZA NO 14 SCIENCE MUSEUM RD TSIM SHA TSUI HONG KONG`，有效期至 2027-08-03。候选法律页已填入该主体及明确标为“商业登记证所载营业地址”的地址，没有将其冒称为已核实的注册办事处地址。两张图片未单独证明最新注册办事处地址。会员页仍标“预览稿”；已批准的退款规则和价格保留。完整法律页与供应商付费服务条款尚未定稿，不能以 Stripe 实名审核或这些证书代替服务条款审定。证件图片不纳入公开代码库。
2. 已有一笔真实 Stripe Test Mode 测试卡成功付款。2026-10-17 17:55（Asia/Bangkok）前后，阿里云隔离数据库对账结果为 `PAID`，重复对账返回 `alreadyProcessed`；隔离库恰有 1 个有效会员期、1 条已付记录和 1 次首购使用记录。尚无失败付款、实际 Webhook 投递、退款和争议的端到端记录；当前 Webhook 成功事件测试仍为模拟签名事件。供应商入口还需独立的 Webhook 端点及签名密钥验证。
3. 所有者已批准“企业和车源审核后付款、Stripe 确认付款后当天上线、服务三个月、到期或全额退款后下线、部分退款和争议人工处理”。本轮已在候选代码实现，并以模拟已签名事件及阿里云原生 AMD64 隔离测试验证；真实 Stripe Test Mode 供应商付款与 Webhook 投递仍未完成。到期后公开查询会立即隐藏车源，数据库原始状态可暂留 `ONLINE`，商家界面按公开可见性显示暂停；全额退款会写入 `OFFLINE`。正式收款前还需确认服务条款与运营处理流程。
4. 阿里云主机剩余空间约 2.3 GB（96% 已用）。本轮仅加载隔离候选镜像并运行测试，没有在生产主机构建、清理镜像或替换运行容器。正式发布前仍需最新生产备份、恢复与回滚演练。
5. 本候选未做真实生产部署、真实扣款、生产数据迁移或线上浏览器端到端付款测试。九语言新文案已写入，但仍需业务语言审核。

## 下一步

核实最新注册办事处地址并审定完整法律页与供应商付费条款。此次法律 HTML 更新发生在上一版候选镜像归档之后；发布前必须重新构建并验证镜像文件哈希，不能把旧归档称为包含最新条款。在阿里云原生 AMD64 隔离环境复测新镜像与真实 Stripe Test Mode 供应商付款、两个 Webhook 端点的投递及退款争议流程，并验证数据库备份与回滚。以上门槛通过后，才可按安全 Runbook 讨论生产切换；两个真实支付开关继续保持关闭。
