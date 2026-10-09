# 第一轮业务修复验收与负责文件

状态：**隔离目录代码已实现并通过测试，未部署。** 原目录、生产数据库和生产配置未修改，未发真实邮件。正式协议资料尚缺，新商家正式启用仍被阻挡。

## 最新整套后端测试结果（询盘按钮修复后重跑）

使用内置 Python **3.12.14**，运行全部 `auth` 的 `unittest discover -s auth -p test_*.py`：

| 项目 | 结果 |
| --- | --- |
| 发现并执行统计 | 221 项 |
| 通过 | 216 项 |
| 失败 / 错误 | 0 / 0 |
| 跳过 | 5 项 |
| unittest 耗时 | 40.589 秒 |

5 项跳过均为基线中已有的未部署社交登录草稿测试：`test_app` 的 2 项 legacy social OAuth 测试，以及 `test_social` 因可选依赖未安装跳过的 3 项。**`test_app` 当前 Google 登录的 5 项全部实际运行并通过**，未添加新的跳过来规避失败。

原始日志：`security/test-results/auth-discover.log`。准确数量、跳过测试名称和原因：`security/test-results/auth-discover-summary.json`。

业务专项完整回归先前为 16 套件、152 项通过；`test_business_readonly_activation` 补齐询盘 PUT 后共有 12 项，全部包含在最新 discover 中。所有数据库均为临时 SQLite，协议为明确标记 SYNTHETIC QA 的临时 FINAL 文件，上传目录隔离，邮件使用 Mock 或无操作发送器。默认邮件传输在全套测试时额外禁用。

## 复核补充：询盘已读按钮

复核发现 `site/supplier/app.js` 已显示 `inquiry-viewed` 按钮，但通用 click handler 未接入这个动作。首轮 220 项结果属于后端回归，不能证明该按钮生效。本次已把实际按钮接到现有 **`PUT /autolink/supplier/inquiries/{id}`**，请求体为 **`{"status":"VIEWED"}`**；成功后重新读取当前页面，失败则显示错误并恢复按钮，等待期间不重复提交。

**询盘已读使用 PUT；报价已读使用 POST。** 没有新增 `/inquiries/{id}/viewed` POST 接口，没有改变 GET 的只读行为。

| 补充验证 | 结果 |
| --- | --- |
| 实际 supplier 入口和注册 click handler 的 Node VM 回归 | 3 项全部通过，0 跳过；72.355 毫秒 |
| `test_business_readonly_activation` + `test_team`，Python 3.12.14 | 27 项全部通过，0 跳过；4.869 秒 |
| supplier JavaScript 语法及修改文件空白检查 | 通过 |

前端验证覆盖只读加载、实际点击发送正确 PUT/VIEWED、携带当前公司上下文、成功后刷新、失败后可重试，以及等待期间连续点击只有一次写请求。新增 HTTP 验证覆盖本公司负责人成功、其他账号和跨来源拒绝，以及 GET 前后整库完全不变。

回归命令：`node --test scripts/tests/supplier_inquiry_actions.mjs`；在 `auth` 目录运行 `python3 -m unittest test_business_readonly_activation test_team -q`。日志为 `security/test-results/inquiry-viewed-frontend.log` 和 `security/test-results/inquiry-viewed-backend.log`。此补充仍只使用隔离临时数据和 Mock 响应，没有访问生产。

## 已验证的行为

- 询盘、报价、CRM 详情、商家资料、协议状态、概览及实际 HTTP GET：每次读取前后整库 `iterdump` 相同，不记录 VIEWED，也不写入 EXPIRED。
- 报价过期只计算响应状态。接受、拒绝和显式已读均返回 409，整库及通知、审计不变，不返回假成功。
- 报价已读必须 `POST /autolink/buyer/quotes/{id}/viewed`；仅报价所属买家可操作，跨买家和跨来源被拒绝，重复已读不重复写入审计。
- 询盘已读由按钮主动调用 `PUT /autolink/supplier/inquiries/{id}` 并提交 `status: "VIEWED"`；读取详情不会自动标记已读。
- 只有完整资料、现有必填材料、当前 FINAL 协议确认后的**主动提交**才能自动启用企业。资料保存、协议确认、GET 和重启均不会自动启用。
- 旧 PENDING 申请须主动重新提交，原协议确认及审计历史保留；旧 APPROVED 的读取和重启不迁移原审批状态。暂停公司不能自行恢复。
- 草稿、缺法律字段、有占位、未到生效日期、日期或邮箱格式错误、空协议正文，均不能确认并启用。
- BUYER 公司启用后保留 BUYER 身份，旧 MERCHANT / SUPPLIER 也能使用采购功能。自己公司和公司队员不能向本公司提交询盘或响应本公司采购需求。
- 车源从 DRAFT 开始，提交后仍为 PENDING_REVIEW，不能因商家自动启用直接公开或上线；现有图片、价格及独立审核门槛保留。
- 队员不能确认公司协议、启用公司或邀请队员；撤销后立即失去原工作权限。暂停、删除、未验证及测试账号不能自动启用。
- BUYER 企业负责人可邀请团队，原角色不被改为商家。邀请排队后负责人变为测试账号，邮件任务会取消。
- 与账号分工合并后，买家资料保存不能绕过商家名称锁定，公开买家供应商列表排除测试账号；测试账号保留私人工作台概览。

## 本分工负责修改的代码

| 文件 | 修改 |
| --- | --- |
| auth/trade_service.py | 自动启用、旧申请显式重提、只读 GET、过期状态计算、显式报价已读、采购身份兼容及自公司边界；与 SEO 分工共享文件，Sitemap 段由 SEO 分工负责 |
| auth/supplier_agreement_service.py | FINAL / 法律资料 / 占位 / 生效日期门槛；支持测试临时文档注入，生产仍读取原文件 |
| auth/business_mail.py | BUYER 企业负责人团队邀请资格；测试账号邀请邮件取消 |
| site/buyer/app.js | 双工作台访问、Google 登录保持采购入口、显式报价已读、业务启用标签与说明 |
| site/supplier/app.js | 双工作台导航、协议未就绪说明与禁用按钮、旧 PENDING 主动启用、显式询盘已读 |
| site/trade/app.js | 商家公开标签及说明改为业务账号启用，避免自动启用宣称平台尽调认证；初始 SSR 保留由 SEO 分工负责 |
| site/assets/index-autolink-membership-apply-pricing.js | 仅已定位 Google 商家入口的角色门槛最小替换，允许有商家工作台能力的 BUYER |

账号接口、团队实时身份校验、买家资料锁名及测试账号目录过滤由账号分工负责；本轮最终测试已覆盖其合并结果。

## 本分工负责修改或新增的测试与说明

- `auth/test_trade.py`：共享临时 FINAL fixture；显式报价/询盘已读预期。Sitemap 测试段由 SEO 分工修改。
- `auth/test_supplier_agreement.py`、`auth/test_supplier_verification.py`、`auth/test_publication_readiness.py`：正式测试协议和自动启用预期。
- `auth/test_team.py`：真实撤权角色、只读过期查询、测试账号邀请任务取消。
- `auth/test_buying_requests.py`、`auth/test_platform.py`、`auth/test_supplier_overview.py`：双身份和启用标签、显式已读预期。
- `auth/test_pagination.py`：撤销前创建测试会话，保留撤销后保护检查。
- 新增 `auth/test_business_readonly_activation.py`：原 11 项加本次询盘 PUT 1 项，共 12 项专项隔离回归。
- 新增 `scripts/tests/supplier_inquiry_actions.mjs`：实际入口加载和点击事件 3 项回归。
- 新增 `SUPPLIER_AGREEMENT_RELEASE.md`：8 个 legalDetails 字段、正式新版本规则、阻塞与测试说明。
- 新增本说明及 `security/test-results/auth-discover.log`、`security/test-results/auth-discover-summary.json`。

## 真实协议保持不变

`auth/supplier-agreement.json` 测试前后及 Git 基线 SHA-256 均为：

`07a59126e54405120988cc68e440420e29858e549d9f6b016c719d2f9d390228`

原文件仍为 `REVIEW_DRAFT`，原版本及正文没有改成 FINAL，也没有补写运营资料。正式启用前必须由负责人提供真实运营信息和法律审核后的新版本，不能用 synthetic fixture 发布。

## 剩余事项与限制

- 正式法律资料和协议新版本未提供，因此新的商家入驻仍不能正式启用；属于明确阻塞。
- 本轮未部署，生产环境仍待按后续授权流程发布和验收。
- 法律门槛检查能验证格式、状态及明显占位，不能证明信息真实，也不能代替法律审核。
- 本轮没有使用真实客户数据完成生产写入闭环；通过结果表示隔离代码与接口回归通过。
- 新业务状态说明提供 9 种语言，本轮未进行全站 9 种语言的完整视觉和人工译文验收。
