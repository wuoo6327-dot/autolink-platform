# AUTOLINK Stripe 双入口隔离候选报告

日期：2026-10-17。状态：**仅隔离候选；生产支付未启用，也未部署本候选。**

## 范围与基线

- 从 `2797d12`（`codex/supplier-brand-auth-on-seo-20261014`）建立独立分支 `codex/stripe-buyer-supplier-20261017`。保留此前生产安全、SEO、询盘和商家审核流程；没有合并旧支付 PR，也没有修改真实生产数据。
- Stripe 为买家会员和供应商上架服务的共同收款商户，分别使用独立的订单、Checkout 和 Webhook 路由。Airwallex 仅保留关闭的接口名称，不参与付款；没有自动续费。
- 生产 Auth 容器只读检查：运行镜像 ID `sha256:e56bb2c05766aeda08db14db4a6931e6ba19f117926a9f24927b7edaccf3be2c`，Auth、Web 均健康；生产容器中的 `PAYMENTS_ENV`、两个支付开关、`STRIPE_LIVE_RELEASE_READY` 与 Stripe 密钥均未配置。线上真实扣款仍为关闭状态。

## 已完成的隔离开发

- 买家会员后端固定 USD 首购／续费价格：月度 1.99／19.90，季度 9.99／29.99，年度 39.99／99.99。每个账户的首购资格只可用一次。只有已签名且身份、金额、币种匹配的 Stripe 付款确认才开通会员；重复回调幂等。买家页面保留现有布局，并仅在后端开放时显示 Stripe 按钮。
- 供应商上架服务使用独立订单表，固定 USD 40／140／200 每 SKC 每季度的现有价格。只有已核准企业的所有者、已审核车源可创建付款单。Stripe 回调核实商户、环境、订单、金额、支付身份和签名；记录退款与争议，且付款不自动改变车源审核或公开状态。供应商可查看自己的付款记录。
- 两入口分别有关闭开关和 Webhook 签名密钥。生产模式另需显式 `STRIPE_LIVE_RELEASE_READY=true`。前端不能提交实际支付金额或凭返回页面开通服务。两个只供操作员使用的订单对账命令可检查和恢复不确定的 Checkout 结果。
- 实际修改：`auth/app.py`、`auth/buyer_service.py`、`auth/Dockerfile`、`auth/membership_payments.py`、`auth/supplier_listing_payments.py`、`auth/reconcile_membership.py`、`auth/reconcile_supplier_listing.py`、`auth/test_membership_payments.py`、`auth/test_supplier_listing_payments.py`、`compose.yaml`、`.gitleaks.toml`、`site/index.html`、`site/assets/membership-checkout.js`、`site/assets/membership-checkout.css`、`site/assets/supplier-stripe-checkout.js`、`site/assets/supplier-program.js`、`site/buyer/app.js`、`site/supplier/app.js`、`site/supplier/index.html`。

## 已验证的事实

| 检查 | 实际结果 |
| --- | --- |
| Stripe Test Mode API | 与服务器隔离环境中配置的商户账户一致；创建并取回 USD 1.99 会员及 USD 40 供应商测试 Checkout。会员沙盒订单 `70330cd7-b5fc-41f7-91a1-4e627cd17e2b` 已用 Stripe 官方测试卡完成付款；Stripe API 返回 `livemode=false`、`status=complete`、`payment_status=paid`、`amount_total=199`、`currency=usd`。供应商测试卡付款尚未完成。 |
| 本机完整后端测试 | 共运行 264 项，其中 259 项通过、5 项跳过。支付专项 25 项通过；包含权限、金额、首购、重复回调、退款和不确定订单恢复。 |
| 阿里云原生 AMD64 支付专项 | 先在现有镜像中只读挂载候选代码运行 25 项，通过；之后将固定候选镜像加载到阿里云，以只读测试文件挂载、无外网、无生产卷运行镜像内代码，25 项再次通过。 |
| 静态及配置检查 | 修改过的 JavaScript `node --check` 通过；使用非生产占位变量的 `docker compose config --quiet` 通过；`git diff --check` 通过。 |
| 安全扫描 | Gitleaks 对候选目录扫描 308.34 MB，未发现泄露；Trivy 文件系统与最终候选镜像扫描均报告 0 项 HIGH/CRITICAL 漏洞。 |

候选镜像以 `linux/amd64` 构建并保存在本机，标签 `autolink-stripe-both:qa-20261017`；本地 OCI manifest list 身份为 `sha256:252202c7962de23d46d594a7408ecedd6e12880379bc12682c80076d35e1cb22`，不冒充远程 Registry Manifest Digest。压缩归档位于 `/Users/oo/Documents/ChatGPT/Space Auto/deployment/artifacts/stripe-both-20261017/autolink-stripe-both-qa-amd64.tar.gz`，SHA256 为 `5d03da09a0da83da84d405e78acf1cfd689c51b4531c2b18ff78d2c396036c79`。阿里云加载后读取的镜像身份、架构与本机一致；镜像内 `app.py` 和两项支付模块的 SHA256 与提交源文件逐项一致。它只作为隔离验收镜像，未接入生产 Compose。

为控制阿里云磁盘使用，原生 AMD64 验收完成后仅删除本次隔离 QA 镜像标签；本机固定归档保留，运行中的生产 Auth 和 Web 容器继续保持健康。

## 尚未达到真实收款上线门槛

1. 会员法律页面仍标注“预览稿／企业资料待确认”；候选草稿已与确认的年度首购 USD 39.99／续费 USD 99.99 及跨套餐仅一次首购优惠保持一致，联系入口改为已存在的 `/support?type=Membership` 站内表单。运营主体及退款、取消条款仍须由所有者审定。不能以 Stripe 实名审核代替服务条款审定。
2. 已有一笔真实 Stripe Test Mode 测试卡成功付款。2026-10-17 17:55（Asia/Bangkok）前后，阿里云隔离数据库对账结果为 `PAID`，重复对账返回 `alreadyProcessed`；隔离库恰有 1 个有效会员期、1 条已付记录和 1 次首购使用记录。尚无失败付款、实际 Webhook 投递、退款和争议的端到端记录；当前 Webhook 成功事件测试仍为模拟签名事件。供应商入口还需独立的 Webhook 端点及签名密钥验证。
3. 供应商付款记录不会自动打开或关闭公开车源。现有车源从 `APPROVED` 到 `ONLINE` 的业务规则并未绑定付费状态；必须明确上架服务的权益启动、退款和停用规则，之后单独验收，才能收取真实上架费。
4. 阿里云主机剩余空间约 2.3 GB（96% 已用）。本轮仅加载隔离候选镜像并运行测试，没有在生产主机构建、清理镜像或替换运行容器。正式发布前仍需最新生产备份、恢复与回滚演练。
5. 本候选未做真实生产部署、真实扣款、生产数据迁移或线上浏览器端到端付款测试。九语言新文案已写入，但仍需业务语言审核。

## 下一步

先审定会员和供应商付费条款、支持联系方式以及供应商付费后的服务规则。随后在隔离环境完成两个 Stripe Webhook 端点的实际测试投递与卡支付、退款、争议测试，并验证数据库备份与回滚。以上门槛通过后，才可按安全 Runbook 讨论生产切换；两个真实支付开关继续保持关闭。
