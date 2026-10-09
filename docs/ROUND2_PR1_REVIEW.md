# PR #1：59 个候选文件复核记录

基线 `96f1f34` → 原候选 `5e4c41d`，PR #1 仍为草稿且保持 59 个文件。复核采取源差异、关键权限/状态调用链、对应自动测试及实际本地容器检查；不是外部渗透测试或逐屏全站商业验收。

发现并修正公开车源页遗留角色门槛；Requests 升级和实际镜像风险另见第二轮报告。下表按文件说明覆盖边界，不能解释为每一行代码、每种浏览器或线上全部场景都已通过。

| 文件 | 类别 | 复核证据 | 结论/限制 |
|---|---|---|---|
| .github/workflows/security-review.yml | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| BUSINESS_REPAIR_VERIFICATION.md | 文档 | 与本轮原始测试和边界交叉核对 | 历史 216/221 仍为第一轮结果；不能代表生产验收 |
| Caddyfile | SEO 路由 | 实际 Caddy+auth 23 项 HTTP；九语言适配器 | 初始正文/canonical/hreflang/Sitemap 已验证；Google实际收录不能由此推定 |
| README.md | 文档 | 与本轮原始测试和边界交叉核对 | 历史 216/221 仍为第一轮结果；不能代表生产验收 |
| ROUND1_CHANGED_FILES.md | 文档 | 与本轮原始测试和边界交叉核对 | 历史 216/221 仍为第一轮结果；不能代表生产验收 |
| SUPPLIER_AGREEMENT_RELEASE.md | 文档 | 与本轮原始测试和边界交叉核对 | 历史 216/221 仍为第一轮结果；不能代表生产验收 |
| auth/Dockerfile | 容器配置 | 实际构建、非 root 启动/健康状态、镜像扫描 | HEALTHCHECK 已补；基础镜像依赖 HIGH 待处置 |
| auth/app.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/business_mail.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/buyer_service.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/email_auth.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/image_service.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/platform_service.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/seo_service.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/supplier_agreement_service.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/team_service.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| auth/test_account_capabilities.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_account_http.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_business_readonly_activation.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_buying_requests.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_pagination.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_platform.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_publication_readiness.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_seo.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_supplier_agreement.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_supplier_login_roles.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_supplier_overview.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_supplier_verification.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_team.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/test_trade.py | 测试 | Linux Docker 全套 222 项；新增真实依赖本地证书互通测试 | 覆盖权限/只读/协议门槛；第三方真实服务待验证 |
| auth/trade_service.py | 后端 | 差异、权限调用链及 Linux Docker 回归 | 暂未发现本轮新增阻断；待生产架构预发布复验 |
| compose.yaml | 容器配置 | 实际构建、非 root 启动/健康状态、镜像扫描 | HEALTHCHECK 已补；基础镜像依赖 HIGH 待处置 |
| docs/DEVELOPMENT.md | 文档 | 与本轮原始测试和边界交叉核对 | 历史 216/221 仍为第一轮结果；不能代表生产验收 |
| docs/LEGAL_DETAILS_REQUIRED.md | 文档 | 与本轮原始测试和边界交叉核对 | 历史 216/221 仍为第一轮结果；不能代表生产验收 |
| docs/SECURITY_SCANNING.md | 文档 | 与本轮原始测试和边界交叉核对 | 历史 216/221 仍为第一轮结果；不能代表生产验收 |
| scripts/dev_round1.py | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| scripts/install_security_tools_ci.py | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| scripts/security_scan.py | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| scripts/tests/public_seo.mjs | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| scripts/tests/supplier_inquiry_actions.mjs | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| scripts/tests/test_security_reports.py | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| security/gitleaks.toml | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| security/test-results/auth-discover-summary.json | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| security/tool-versions.json | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| security/trivy.yaml | 安全检查/证据 | Gitleaks/Trivy 执行；报表脱敏测试 | 源码检查通过；不能替代本轮新增实际镜像扫描 |
| site/assets/account-header.js | 前端业务 | 源差异及对应后端/前端回归 | 商家与买家切换有回归覆盖；完整九语与移动端逐屏未全部验收 |
| site/assets/business-seo.js | SEO 路由 | 实际 Caddy+auth 23 项 HTTP；九语言适配器 | 初始正文/canonical/hreflang/Sitemap 已验证；Google实际收录不能由此推定 |
| site/assets/email-ui.js | 前端业务 | 源差异及对应后端/前端回归 | 商家与买家切换有回归覆盖；完整九语与移动端逐屏未全部验收 |
| site/assets/index-autolink-membership-apply-pricing.js | 编译入口 | 按共同前后缀核对唯一差异；node --check | 仅改商家能力门槛；仍为既有编译文件，真实 Google UI 待验证 |
| site/buyer/app.js | 前端业务 | 源差异及对应后端/前端回归 | 商家与买家切换有回归覆盖；完整九语与移动端逐屏未全部验收 |
| site/legal/account-deletion.html | 法律入口 | 源文案/授权门槛；法律相关 VM 27 项 | 技术描述已核对；不代表主体/正式条款完成 |
| site/legal/cookies.html | 法律入口 | 源文案/授权门槛；法律相关 VM 27 项 | 技术描述已核对；不代表主体/正式条款完成 |
| site/legal/legal.js | 法律入口 | 源文案/授权门槛；法律相关 VM 27 项 | 技术描述已核对；不代表主体/正式条款完成 |
| site/legal/privacy.html | 法律入口 | 源文案/授权门槛；法律相关 VM 27 项 | 技术描述已核对；不代表主体/正式条款完成 |
| site/legal/supplier-agreement.js | 法律入口 | 源文案/授权门槛；法律相关 VM 27 项 | 技术描述已核对；不代表主体/正式条款完成 |
| site/robots.txt | SEO 路由 | 实际 Caddy+auth 23 项 HTTP；九语言适配器 | 初始正文/canonical/hreflang/Sitemap 已验证；Google实际收录不能由此推定 |
| site/supplier/app.js | 前端业务 | 源差异及对应后端/前端回归 | 商家与买家切换有回归覆盖；完整九语与移动端逐屏未全部验收 |
| site/trade/app.js | 公开交易入口 | 实际 click/submit 的隔离 VM | 发现商家收藏/询盘仍受 BUYER 限制；第二轮已修正（修复前 6/8 失败，后 8/8 通过） |
| tests/test-legal-account.mjs | 前端测试 | Node VM 实际监听器；全组 38 项 | 均通过；HTTP与外部服务范围分别列出 |
