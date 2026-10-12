# AUTOLINK 全球 SEO 正式生产上线完成报告

**记录日期：**2026-10-12（Asia/Bangkok）
**结论：正式上线未执行。** 所有者授权在全部门槛通过后直接切换，但发布镜像的独立 manifest 身份尚未核实，且阿里云 Workbench 在最终备份准备时失去连续控制。单实例切换有最长 5 分钟中断限制，因此没有启动生产切换、Search Console 提交或索引请求。本报告区分生产、隔离预发布和 Google 真实抓取。

## 1. 生产基线、提交与范围

- 生产容器仍是 `autolink-demo-auth-1` 与 `autolink-demo-web-1`，最后一次 `docker ps` 均为 healthy。生产认证镜像 ID 为 `sha256:328ad2e7f193d924d8adc9943c2bde450e26e1b1af7318b26b1e4cb8984d4b80`，Web 镜像 ID 为 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`；生产发布目录仍为 `/opt/autolink-releases/a38664fc9bf2be639cbcb65dce4b57ef5b94170c`。
- 真实数据库有 **270 条车型、60 条品牌记录**，当前公开有效目录为 **244 个车型、53 个品牌**。只读核查逐项匹配 244 个车型的参考资料和图片哈希，未把历史种子写入生产。生产挂载的图片文件均匹配；远程主机直连 CDN 的逐张 HTTPS 检查超时，不能据此认定图片缺失。
- [PR #6](https://github.com/wuoo6327-dot/autolink-platform/pull/6) → [PR #7](https://github.com/wuoo6327-dot/autolink-platform/pull/7) → [PR #8](https://github.com/wuoo6327-dot/autolink-platform/pull/8) 为祖先链；[草稿 PR #9](https://github.com/wuoo6327-dot/autolink-platform/pull/9) 基于 #8。没有重复合并 PR #4，也未合并 `main`。当前发布准备分支 `codex/seo-production-release-20261012`、提交 `5725b8b`；认证镜像应用源码构建基点为 `129c08e`，之后的提交调整发布叠加、核验脚本与报告。GitHub 仓库仍为 Public，未更改可见性。
- 未更改生产数据库、账号、会员收费、商家入驻规则、法律协议、CRM 或支付。

## 2. SEO 候选与索引资格

候选目录 `/opt/autolink-releases/5725b8b-seo-20261012` 已准备但**未激活**。从当前生产公开站点复制 5,424 个文件，仅受控覆盖 269 个，其余 5,155 个文件经 SHA-256 校验未变。候选保留车型与品牌 SSR、robots、Sitemap、Canonical、hreflang、x-default、404/noindex、英文内容、采购指南、来源审核和私有接口保护。Web 保留现有首页外观、极氪素材与移动端布局，仅纳入已隔离验证的可选脚本容错和极氪首图资源；较重的 PR #7 首页脚本组合未随本轮 SEO 发布叠加。

隔离候选的**技术索引资格**为 **50 个英文车型 URL、177 个中文车型 URL、10 个英文品牌 URL**；车型 Sitemap 227、品牌 Sitemap 10、静态 Sitemap 64。50 个英文车型和 10 个英文品牌沿用已核查的来源指纹与审核状态。未审核详情及其他语言可访问但 `noindex`，九语言界面保留。上述数字**不是** Google 已收录量。

## 3. AMD64 隔离验收与安全

测试在阿里云 `linux/amd64` 主机的独立网络、`127.0.0.1:18084` 和真实数据库的**备份副本**上完成，未写生产数据库。

| 项目 | 实际结果 |
| --- | --- |
| 后端与权限 | 225 项执行，220 通过、5 项条件跳过、0 失败；涵盖登录、Cookie、CSRF、所有者权限、私有资料、业务隔离和 SEO。 |
| 全量公开页 | 244 车型、53 品牌、九语言详情共 2,673 页的 HTTP、H1、`lang`、Canonical、robots、hreflang、404 和 Sitemap 集合检查零失败。 |
| 浏览器 | Chrome 手机/电脑导航、车型入口、九语言主内容与链接、登录、语言切换、手机菜单通过；手机 Zeekr 9X 初始 HTML 有 39 行参数，电脑 Geely Monjaro 有 8 行。可选脚本失败时首页正文与入口保留。一次桌面链接断言过早采样误报，等待渲染后复测通过，手机/电脑均为 54 个品牌链接。 |
| 爬虫兼容 | 普通 UA 与模拟 Googlebot Smartphone 对四个代表详情的核心响应一致；**不等于真实 Google Live Test**。 |
| 隔离回滚 | 候选 → 旧版 → 候选三阶段通过，始终 244/53、匿名后台 401；候选阶段为 227 个车型及 10 个品牌 Sitemap URL。旧认证镜像回滚必须挂载当前目录 JSON，以免补入历史记录。 |
| GitHub 安全 CI | PR #9 的 `5725b8b` 两次 `source-security` job 均通过：[运行一](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38215440392/job/114698959586)、[运行二](https://github.com/wuoo6327-dot/autolink-platform/actions/runs/38215443923/job/114698970267)。Gitleaks/Trivy 实际运行；Public 仓库按设计不上传私有扫描报告。 |
| 镜像扫描 | Auth 与 Web 均 0 CRITICAL/HIGH。Web 留有一项 UNKNOWN `GO-2026-5932`（`x/crypto` OpenPGP）；此前符号核查未发现 Caddy 二进制使用受影响包，仍需跟踪。 |

原始证据在 `/home/admin/autolink-final-seo-qa-20261012/`：`backend-tests.log`、`rollback-final.log`、`tests/results/overseas-seo-http-final-20261012.json`、`browser-qa-public/tests/results/`、`qa-scan-final/results/` 和 Lighthouse JSON。隔离验收不能写成生产验收。

## 4. 镜像、备份和回滚准备

候选 Auth 镜像 `autolink-final-seo-auth:129c08e` 为 AMD64，本地镜像 ID 是 `sha256:0fcb1f1c73a0d6b7b23c81355a9d48ca1e82e514705011d26c63a7cd5aaff815`；`docker image inspect` 返回同值的本地 `RepoDigests`。候选 Compose 以此摘要引用 Auth，Web 以 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb` 引用，`config -q` 通过。**本地 RepoDigest 与镜像 ID 相同，尚无受控仓库的独立 manifest digest 证明；不能声称仓库清单验证完成。**

Auth 归档 `auth-image-final.tar` SHA-256：`4362de3c243ec679282da29f3d577ce68fd612d8c1cec00970921029da23f4bf`；Web 归档 `web-image-final.tar` SHA-256：`ddf2c2f6544eea709258695c53da57bc42b27850a52e2af5a27c61875e59927e`。旧镜像也已归档，未执行清理。

最近**已验证**的一致性快照为 `/opt/autolink-backups/seo-cutover-20261012/autolink-auth-20261012T072113Z.sqlite3`，SHA-256 `ec04bd0080d99adc7e2faac841aa986b4132da42981c2af4fac74811b39e8317`，679,936 字节；`integrity_check=ok`、外键违规 0、270/60 条记录，SQLite 在线备份 API 的隔离恢复与哈希校验通过。同目录另有仅 root 可读的非数据库认证卷、Caddy 证书与配置卷、运行配置、旧 Auth/Web 镜像归档；`sha256sum -c` 全部通过，四份压缩包隔离解压后逐文件与源哈希一致。`rollback-catalog.json` 固定当前 244/53 目录，旧版 Compose 的只读目录挂载覆盖文件已通过 `config -q`。这些是**预备备份**，不是切换前最新备份。

尝试生成新备份时，第一次手输的数据库路径不正确，脚本在打开源路径前退出，未修改数据库。第二次改为读取已验证 manifest 内的真实源路径时，Workbench 前台切回 Stripe，命令结果无法确认；不能把新快照写为完成。

## 5. 手机与电脑性能

原始 JSON 位于上述隔离目录的 `lighthouse-amd64-final/`、`lighthouse-amd64-baseline/`、`lighthouse-amd64-prodhome-safe/`。生产基线首页手机三次冷测中位数为 **LCP 9,989 ms、TBT 944 ms、评分 38**；本轮保守首页候选三次冷测中位数为 **LCP 9,388 ms、TBT 1,125 ms**。LCP 略降，但 TBT 变差，两者均未达到 2.5 秒/200 ms 目标，不能称手机首页性能达标。完整候选其余路由三次冷测：手机车型详情 LCP 1,435 ms、TBT 0、CLS ≤0.1；品牌目录 2,289 ms/2 ms；车型目录 1,848 ms/16 ms；买家登录 5,109 ms/39 ms。手机与电脑共五类路由的 30 份完整候选 JSON 已保留；这些是实验室结果，不是生产真实用户指标。

## 6. 正式上线、Google 与监控状态

**实际上线时间：无。实际运行 SEO 镜像 digest：无。生产回滚：未发生。上线后 30 分钟监控：未执行。** 原生产容器仍服务网站。没有新版 Google Search Console URL Inspection Live Test、Google 读取的 Canonical、Sitemap 接收状态或索引申请。不能把模拟爬虫、技术索引资格或 Sitemap 数量写成 Google 已收录、排名、自然点击或有效询盘。

当前阻断：

1. 发布镜像仍需可独立核验的 manifest 身份。当前只有本地内容 ID、RepoDigest 和归档 SHA-256，不能冒充受控仓库 manifest 验证。新增仓库权限若必要，属于需报告的授权范围扩展。
2. 阿里云 Workbench 在发布前检查期间多次被切回 Stripe，最近一次发生在最终数据库备份重试时。无法保证单实例切换的 5 分钟中断上限和连续 30 分钟监控，故未启动切换。
3. 手机首页 LCP、TBT 未达理想目标；不得为了分数删除核心内容或放宽安全、数据门槛。

## 7. 继续发布与回滚方案

在终端可连续控制且镜像身份门槛解决后，重新核对当时生产目录、图片、来源指纹和业务数据；若有变化，重新组装候选并隔离验收。用 manifest 内**真实源路径**重新运行 SQLite 在线备份及隔离恢复，并复核上传文件、证书、配置、旧镜像。固定候选提交、站点文件、镜像和归档摘要；确认旧版回滚仍只读挂载当前目录。

依已验证的 Runbook 先切 Auth，待 healthy 后切 Web，保留原数据库和持久卷；不执行 `down -v`、volume prune、清库或历史种子导入。切换时计时，若关键故障或预计超过 5 分钟，立即恢复旧 Auth/Web/站点/Caddy，**保留最新生产数据库与上传文件**。上线后验证 HTTPS、核心路由、登录权限、私有资源、244/53 公开目录、227/10 Sitemap、404/noindex、手机/电脑正文和容器健康，并连续监控至少 30 分钟。

只有新版稳定后，才通过真实 Search Console Live Test 检查 Geely Monjaro、Zeekr 9X、BYD 等合格英文样页及 `noindex` 样页，确认 Google 抓取结果，再提交根 Sitemap 和少量合格 URL 索引请求。分别监控 Google 已收录、英文关键词曝光、自然点击、注册与有效询盘。下一阶段优先审核尚未合格的英文车型和 43 个未完成审核的英文品牌；阿拉伯语、俄语及其他语言需完成真实本地化审核后再开放索引。
