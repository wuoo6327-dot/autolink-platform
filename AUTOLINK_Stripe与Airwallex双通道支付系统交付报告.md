# AUTOLINK Stripe 与 Airwallex 双通道支付系统交付报告

记录日期：2026-10-13（Asia/Bangkok）

状态：**Stripe 优先的隔离候选已完成；空中云汇供应商上架费收单申请已提交、正在审核；真实收款未开放，生产未修改。**

## 商户与渠道状态

网站所有者确认 Stripe 香港商户账户已获准收款，测试模式 API 密钥及 Webhook 签名密钥存放在服务器安全环境中。本报告此前的 Stripe 候选没有独立核验账户能力或开启真实扣款。2026-10-13，所有者在空中云汇后台提交了 **供应商车源上架数字服务费** 的收单申请；页面显示“您的申请正在审核中”。该申请与买家会员费分开，Stripe 银行卡通道继续保留。

| 支付方式 | 当前实现 | 自动续费 | 正式开放 |
| --- | --- | --- | --- |
| Stripe 国际银行卡 | 后端固定金额的单次 Hosted Checkout、签名 Webhook、退款与争议记录；隔离模拟网关测试通过 | 关闭；尚无主动授权、提醒、取消和真实 Billing 验收 | **关闭** |
| Airwallex 供应商上架费 | 已申请支付宝、微信、PayPal、Visa、Mastercard、银联、Apple Pay、Google Pay；独立订单和沙盘支付链接适配器已写入后续分支，真实商户及单项支付方式均待审核与联调 | 手动续费；自动扣款关闭 | **关闭** |

买家会员 Airwallex 方法名仍为保留值，即使误设会员 Airwallex 环境开关也不可用；会员 Webhook 返回 HTTP 503。供应商上架费使用独立 `/autolink/supplier/...` API 和 Webhook，默认关闭且代码仅允许沙盘模式。前端买家会员只接受 `checkout.stripe.com` 的 HTTPS 收银台地址。空中云汇申请提交不代表上述任一支付方式获批；本轮没有发起任何真实扣款。

## 2026-10-13 空中云汇申请与供应商订单增量

- 申请申报的业务是供应商上架数字服务，**不是买家会员费或车辆货款**。沿用网站既有展示标准：每个 SKC 每季度首季 USD 40、第二季 USD 140、标准 USD 200；同一供应商同品牌、车型、年款为一个 SKC，配置和颜色不重复收费。提交的经营预估为平均 USD 100/笔、最高 USD 200/笔、每月约 100 笔、约 USD 10,000/月、国际付款占比 40%–60%。这些是申请预估，不是实际交易量。
- 申请中的交付说明为企业和车源资料在付款前完成审核，付款后当天开通。现有网站仍无付费上架激活流程；该申报须在正式收款前由真实产品流程和条款落实。
- 新分支 `codex/supplier-airwallex-listing-20261013` 基于 Stripe 候选 `16ce239`，代码提交 `8cccbe783cb2204785a50bd36a40235ae8f89620`，候选为 [GitHub PR #14](https://github.com/wuoo6327-dot/autolink-platform/pull/14)（Draft，目标 PR #13 的分支，不能直接合并主线）。新增 `auth/supplier_listing_payments.py`，在后端创建独立供应商订单，按已付款季度次数计算 USD 40/140/200；前端提交的价格不参与收费。只允许审核通过的企业所有者对已审核车源发起沙盘支付链接。单个 SKC 的未决订单受到唯一约束，避免重复付款。
- 新 Webhook 验证 Airwallex 原始请求体 HMAC、时间戳、账户 ID，并向服务商查询一次性支付链接，复核订单引用、金额、币种和唯一成功 PaymentIntent。重复事件只记录一次。付款仅记录服务期，**不会跳过现有企业、车源及图片审核，也不会自动把车源设为 ONLINE**。
- 新接口为 `GET /autolink/supplier/vehicles/{id}/listing-quote`、`POST /autolink/supplier/vehicles/{id}/listing-checkout`、`GET /autolink/supplier/listing-payments` 和 `POST /autolink/supplier/payments/webhooks/airwallex`。当前 `SUPPLIER_LISTING_PAYMENTS_ENABLED` 默认关闭，代码仅支持 `PAYMENTS_ENV=sandbox`；生产模式始终不可用。网站展示端 `paymentAvailable:false` 不变。
- 隔离测试：后端全套 **249 项运行，5 项跳过，其余通过**；新增供应商支付专项 6 项通过，覆盖默认关闭、审核和所有者限制、服务端价格、重复订单、签名/商户/金额拒绝、HTTP 登录与 Origin 限制。`gitleaks dir auth` 扫描约 2.03 MB，未发现密钥；`trivy fs auth` 的 HIGH/CRITICAL 漏洞与密钥发现均为 0。使用本地临时数据库和模拟网关，**尚未完成真实空中云汇沙盘 API、真实 Webhook、AMD64 预发布及生产验证**。
- GitHub [安全工作流运行 #38380815913](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38380815913) 在提交 `af4723d` 上实际完成并成功：当前源码扫描、Git 历史密钥扫描和阻断发现门槛均通过。仓库当前为 Public，工作流中“保留私有仓库的脱敏报告”步骤按条件跳过；安全扫描本身没有跳过，也未更改仓库可见性。
- 当前仍需补齐供应商收费正式条款、退款及争议流程、真实客服联系方式、付款后激活与到期处理、异常订单对账、空中云汇沙盘凭据和逐项支付方式批准信息。未完成前不得开放真实收款。

## 价格、权益与安全边界

- 后端价格为 USD：月度首购 1.99 / 续费 19.90；季度 9.99 / 29.99；年度 39.99 / 99.99。前端不能指定金额。首购资格由现有会员、既有付款记录及新增唯一使用记录判断，跨套餐只允许一次。
- 默认手动续费。自动续费请求被拒绝；到期前提醒、授权协议、自动扣款及失败重试均未开放。九语言会员价格、续费说明及付款不可用提示已同步，仍需母语内容校对。
- 既有 `buyer_memberships` 仍是权益来源。订单、首购使用与 Webhook 事件另行记录。仅在签名、测试/生产模式、订单、币种、金额与支付状态检查通过后开通会员。重复回调不重复开通；付款成功跳转页本身不授予权益。
- 完整退款会撤销对应会员期；部分退款及争议记录供人工复核。未完成或状态不确定的订单需人工对账，不能因客户端重试再次扣款。
- 原有买家、商家、车型 SEO、登录、Cookie、CSRF、私有数据及会员权益规则未作业务扩展；商家入驻、法律协议和支付以外业务未改动。

## 代码与候选身份

- 新支付代码提交：`d6844ee6d79425ca66eae4fab1d2a38a684e9206`；Stripe 优先收窄提交：`fc9ff1c817fd9cbeb01583497b4d29084d133a2d`。
- 分支：`codex/membership-dual-payments-20261012`；候选：[GitHub PR #13](https://github.com/wuoo6327-dot/autolink-platform/pull/13)，目标为 Round 12 候选分支，**不能把该 PR 当作可直接合并 `main` 的生产发布包**。
- 本轮收窄修改：`auth/membership_payments.py`、`auth/test_membership_payments.py`、`compose.yaml`、`site/assets/membership-checkout.js`、`site/buyer/app.js`。前序支付候选还修改了 `auth/app.py`、`auth/Dockerfile`、会员页面与样式。
- 本地隔离构建：`autolink-auth:stripe-first-candidate`，`linux/amd64`，本地 Docker 镜像 ID `sha256:4c1bb8ff16bffaf986c736e0c54934600c6ccf9fed85568dc4852d90e199f98c`。这是本地镜像身份，不是私有仓库 Manifest Digest，亦非固定生产归档。应用文件 SHA256：`auth/membership_payments.py` 为 `2bac1aeaec91c93f039124de0d315b28888ebc78d3d4a402c41d51f3b4fa03d7`；`auth/app.py` 为 `bb218d0cf918b0b7c1e2bdb1404f31bde15ea131bb559f75bb5cbd58dc5970a5`。

## 实际隔离测试

| 项目 | 结果 |
| --- | --- |
| Stripe 原候选后端全套自动化测试 | 共运行 234 项，其中 229 项通过、5 项依既有条件跳过；新分支最新结果见上节 |
| 支付专项 | 7 项通过：首购与续费价、重复 Webhook、签名/金额/账户/模式拒绝、退款、Stripe 收银台 URL 校验、Airwallex 关闭、HTTP 登录及 Origin 保护 |
| 九语言公共 SEO 测试 | 英、中、阿、俄、哈、乌、韩、法、斯九语言均通过 |
| JavaScript 语法 | 会员收银台和买家中心均通过 `node --check` |
| Compose 配置 | 使用本地占位镜像及站点地址的 `docker compose config --quiet` 通过；默认支付开关为关闭 |
| AMD64 容器基础路由 | 在 Mac Docker 的 `linux/amd64` 隔离容器中，健康 200、公开车型目录 200、未登录会员 401、Airwallex Webhook 503、无签名 Stripe Webhook 400；容器已停止并移除 |
| Gitleaks | `auth` 约 1.98 MB、`site` 约 306.40 MB 扫描，均未发现泄露 |
| Trivy 候选镜像 | HIGH/CRITICAL 漏洞 0，密钥发现 0 |

测试使用临时数据库和模拟 Stripe 网关，没有使用真实 Stripe 测试密钥、创建真实测试模式 Checkout、收取真实款项或验证真实 Webhook 投递。AMD64 容器运行于 Mac Docker，并非阿里云 AMD64 预发布主机。此前的 `legacy_frontend.mjs` 失败源于本候选基线已有的旧轮询断言，本轮没有触及该逻辑。

## 尚未完成的正式开放门槛

1. 在受控服务器环境确认 Stripe 账户 ID、测试/生产密钥与 Webhook 端点，分别完成真实 Stripe 测试模式的支付成功、失败、重复通知、退款、争议及对账测试。不得向前端、报告或 GitHub 输出密钥。
2. 补齐或确认状态不确定订单的安全对账与解锁流程；验证掉回调、延迟回调和部分退款累计行为。自动续费继续关闭。
3. 在真实隔离 AMD64 预发布环境完成完整权限与回归验收，制作生产数据一致性备份并验证隔离恢复，固定镜像归档与发布锁，演练回滚。
4. 独立审校九语言支付文案和移动端结算入口。只有完成以上门槛后，才能按已有安全 Runbook 考虑开放 Stripe 单次付款。Airwallex 现已提交申请，但仍需获得商户及各支付方式批准，补齐供应商正式收费条款、沙盘联调、付款后激活、退款争议和隔离验收。

本次**没有部署生产、没有启用 Stripe 或 Airwallex 真实收款、没有修改生产数据库，也没有执行生产备份或回滚演练**。
