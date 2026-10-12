# AUTOLINK Stripe 与 Airwallex 双通道支付系统交付报告

记录日期：2026-10-13（Asia/Bangkok）
状态：**隔离候选完成；真实收款未开放，生产未修改**。

## 1. 商户与渠道状态

所有者确认已有 Stripe 账户，但没有确认香港账户的实际收款审核、Billing 权限、测试/生产密钥及 Webhook 配置。Airwallex 尚未注册并完成审核。Airwallex 香港开户入口已打开：<https://www.airwallex.com/en-hk/business-account>；当前浏览器中直接访问香港注册 URL 显示错误页，须由所有者在可用浏览器完成开户。未输入、读取或保存任何真实商户凭据。

| 渠道 | 单次支付候选 | 自动续费 | 正式开放 |
| --- | --- | --- | --- |
| Stripe 国际银行卡 | 服务端固定价格的 Hosted Checkout 与签名 Webhook 已开发，使用模拟网关隔离测试；真实 Stripe 沙箱未联调 | 关闭，未取得实际 Billing/商户资格验证及主动授权流程 | 关闭 |
| Airwallex 支付宝 | 单次 Hosted Checkout 候选和服务端对账已开发；其 Checkout Sessions API 仍属 early access，未取得账户准入或真实沙箱联调 | 关闭，未确认该钱包的周期扣款资格 | 关闭 |
| Airwallex 微信支付 | 同上，单独的方式开关 | 关闭，未确认微信计划及周期扣款资格 | 关闭 |

Airwallex Checkout Sessions 的 [官方 API 文档](https://www.airwallex.com/docs/api/checkout/checkout_sessions/create)标明 early access。支付宝与微信的周期支付必须分别核实，不能从 Airwallex 提供订阅产品推断钱包可自动扣款。[支付宝周期支付文档](https://www.airwallex.com/docs/payments/payment-methods/apac/alipay-cn/accept-recurring-payments-alipay-cn)、[微信周期支付文档](https://www.airwallex.com/docs/payments/payment-methods/apac/wechat-pay/accept-recurring-payments-wechat-pay)。

## 2. 实现与价格

- 月度首购 USD 1.99，后续 USD 19.90；季度 USD 9.99 / 29.99；年度 USD 39.99 / 99.99。金额以美分在后端固定，客户端只提交套餐与支付方式。首购标记由现有会员及历史账单共同判断，并通过数据库唯一约束防止跨套餐、跨渠道重复使用。
- 新增订单、首购使用和 Webhook 事件表；既有 `buyer_memberships` 继续作为会员权益来源。一个账户只允许一个未完成结算订单。服务端仅在签名、商户身份、金额、币种、方式及订单关联检查通过后开通会员；重复事件不重复延长期限。
- Stripe 走一次性 Checkout，Airwallex 走单次 Checkout Session。付款成功跳转页不授予权益。完整退款撤销对应权益；部分退款与争议记录待人工复核。Airwallex 的“退款已受理”只标为待处理，直至“退款已结算”才撤销权益。
- 所有渠道、真实扣款及自动续费默认关闭。自动续费请求直接拒绝；当前会员页与买家中心说明期满后手动续费。自动续费同意、提醒、取消、失败重试流程尚未上线，不能声称已实现。
- 九语言会员价格、手动续费说明和条件显示的支付方式已加入现有页面；保留现有页面设计。尚未完成九语言人工母语校对。商家规则、法律协议、车型 SEO 和既有权限规则未改动。

## 3. 变更文件与固定候选

代码提交：`d6844ee6d79425ca66eae4fab1d2a38a684e9206`，分支：`codex/membership-dual-payments-20261012`，基于 `fda95d7`。代码文件：`auth/membership_payments.py`、`auth/test_membership_payments.py`、`auth/app.py`、`auth/Dockerfile`、`compose.yaml`、`site/assets/membership-checkout.js`、`site/assets/membership-checkout.css`、`site/assets/index-autolink-membership-apply-pricing.js`、`site/buyer/app.js`、`site/index.html`。

隔离构建 `autolink-auth:payment-candidate`：`linux/amd64`，本地 Docker 镜像 ID `sha256:8864b74d20520c41f42cfd1498d6e470ce243bcf73c67c90762e316d50347e2d`。这是**本地镜像身份**，不是 Registry Manifest Digest，也没有作为正式发布镜像归档。主要应用文件 SHA256：`auth/app.py` 为 `bb218d0cf918b0b7c1e2bdb1404f31bde15ea131bb559f75bb5cbd58dc5970a5`，`auth/membership_payments.py` 为 `678d48988d488aae94850d8df2feb9107160471e22e77bf477a26967ac5f1761`。

## 4. 隔离验收

| 检查 | 实际结果 |
| --- | --- |
| 后端全部自动化测试 | 233 项运行通过，5 项按既有条件跳过 |
| 新支付单测 | 6 项通过：价格/首购唯一性、两渠道重复回调、错误签名/金额/方式/账户拒绝、自动续费关闭、退款状态、HTTP 登录与 Origin 保护 |
| 静态语法与 SEO 兼容 | `node --check` 通过；现有九语言公共 SEO 测试通过 |
| 会员页浏览器检查 | 本地隔离页面实际渲染月/季/年价格与续费说明；未获批时支付按钮不出现 |
| AMD64 容器 | 隔离构建并启动；`/healthz` 返回 200、未登录会员接口返回 401、公开车型目录返回 200 |
| Gitleaks | 本次变更 10 个文件、约 2.48 MB 扫描，未发现泄露 |
| Trivy | 候选源码与 AMD64 镜像的 HIGH/CRITICAL 漏洞及密钥扫描，无发现；低于 HIGH 的级别未作为发布结论 |
| 旧前端专项脚本 | `scripts/tests/legacy_frontend.mjs` 未通过；断言要求旧 bundle 不含轮询/焦点监听，而该问题在本分支的基线 HEAD 已存在。本轮支付改动未触及该逻辑 |

测试使用模拟支付网关及临时数据库；没有向 Stripe/Airwallex 发起真实交易。构建后隔离容器已停止并移除。没有触碰生产数据库、生产配置或真实客户数据，因此本轮未制作新的生产备份，也没有执行生产回滚演练。

## 5. 正式开放前剩余门槛

1. 所有者完成 Airwallex 香港主体开户及收款审核；取得 Checkout Sessions early access 与支付宝/微信各自的支付方式授权。确认实际付款币种和 Airwallex 报价机制，不能写死美元兑人民币汇率。
2. 核对 Stripe 香港商户收款能力、账户 ID、密钥及签名 Webhook；分别完成真实 Stripe 测试模式、Airwallex sandbox 的端到端支付、失败、重复通知、退款、争议和对账测试。真实凭据只存服务端安全环境。
3. 补齐未完成订单的服务端对账和安全关闭机制，处理提供商回调丢失/延迟及部分退款累积；确认通知与到期提醒。自动续费在独立资格、协议和失败重试验收前维持关闭。
4. 进行九语言文案审校、移动端支付入口测试、完整安全与数据回归；制作当时最新生产数据一致性备份和隔离恢复；固定不可变 AMD64 镜像及发布锁，演练回滚后再按既有 Runbook 发布获批的方式。

本轮**未正式开放任何付款方式，也没有启用真实扣款**。Stripe 已有账户只说明开户事实，不等于支付权限或自动续费已获准。
