# AUTOLINK Google 抓取与首页性能修复完成报告

**状态：已上线，存在待验证事项。** 2026 年 10 月 12 日生产切换后，Google Inspection Tool smartphone 已显示完整首页，而 Search Console 对根 Sitemap 仍显示 `Sitemap could not be read`。本报告区分公网 HTTP、Google 实时抓取、Google 已索引状态和 Sitemap 处理状态；时间除注明外为 UTC。

## 1. 发布范围与故障结论

- 本轮发布源码为 `52c693475359cf7595164f30ee64a6d78757a6f1`，候选目录 `/opt/autolink-releases/52c6934-round11-20261012`，入口为未合并的 [PR #11](https://github.com/wuoo6327-dot/autolink-platform/pull/11)。基线为当时实际生产品牌版本 `d996b6907c82ac21ee1baf1c09ba93f770a18694`，没有合并无关 PR，也没有改动会员、报价、支付或车型资料。
- 原首页的品牌介绍、搜索和入口依赖单个主脚本完成渲染。Search Console 曾记录该脚本 `Other error`，当时手机渲染截图为 `Unable to load. Please reload.`。这解释了为何非关键脚本失败会使核心首页不可见；**`Other error` 的底层网络或执行原因尚未确定**，不能称该脚本已经修好或损坏。
- 现由 Caddy 对九个语言 URL 直接返回可读的首页 HTML，包括品牌定位、车型搜索、品牌/车型/车源/About 链接和极氪主视觉；浏览器继续加载原有应用作为增强。阻断主脚本的真实浏览器测试仍显示完整公开首页，没有全屏错误。没有开放私有 API。
- 原根 Sitemap 引用两个零 URL 子地图。现只列出有内容的 `static-1.xml`、`brands-1.xml`、`models-1.xml`。这消除了可确认的兼容风险，**但尚无证据证明空子地图就是 Search Console 错误的根因**；Google 后台仍报错，因此此项未完成最终验收。
- 语言切换时由首页语言加载器与业务 SEO 模块同步 `html lang`、方向、Title、Description、Canonical、hreflang、Open Graph、Twitter 标签，处理连续切换和浏览器历史。英语、中文保持原有审核索引规则，其他七种首页语言继续 `noindex`。

主要变更文件为 `Caddyfile`、`auth/trade_service.py`、`site/index.html` 及八个语言首页 HTML、`site/assets/business-language-loader.mjs`、`site/assets/business-seo.js`、`site/assets/home-public-fallback.css`、`scripts/build_round11_home_html.py`、`scripts/round11_cutover.py` 和对应隔离/浏览器测试脚本。原首页主 JavaScript 和业务后端权限规则未被重写。

## 2. 真实生产数据与技术 SEO

切换前后的生产 SQLite 均为 **270 条车型、60 条品牌记录**，公开目录为 **244 个车型、53 个品牌**；没有用历史目录或种子数据覆盖。索引资格保持 **50 个英文车型、177 个中文车型、10 个英文品牌**。根 Sitemap 公网返回 HTTP 200、`application/xml`，含 3 个子地图；子地图分别有 58、10、227 个 URL，共 295 个 URL 条目。HTTP 检查还确认 `robots.txt` 200、Geely Monjaro 和 BYD Han 英文初始 HTML 200、失效车型 404。具备索引资格及出现在 Sitemap 不等于 Google 已索引。

生产首页初始 HTML 为英语并有独立 Title、Canonical 和可抓取链接。九语言各自的初始 HTML 与浏览器动态切换经过检查；阿拉伯语为 RTL、独立 Canonical 且保持 `noindex`。公开品牌/车型 SEO 正文和审核逻辑沿用已上线版本。

## 3. Google Search Console 实际结果

使用已授权的 `autolinkglobal.com` 域名资源完成真实 URL Inspection Live Test，不使用伪造 User-Agent：

| 页面 | Google 手机实时检查 | 观察 |
| --- | --- | --- |
| 首页 `/` | 2026-10-12 19:56（曼谷）`URL is available to Google`、可索引 | Google 渲染截图可见 AUTOLINK 导航、极氪主视觉、`Source China. Drive Global.`，没有全屏错误；HTML 可见英语 Title、介绍、搜索、内部链接及 self Canonical。 |
| Geely Monjaro 英文车型 | 19:44（曼谷）实时抓取成功、可索引 | 测试 HTML 有 2026 年车型英文介绍、2845 mm 轴距与 4770 mm 长度、self Canonical；Google 索引面板显示此前已在 Google。 |
| BYD Han 英文车型 | 19:47（曼谷）实时抓取成功、可索引 | Google 索引面板显示此前已在 Google。 |
| 阿拉伯语首页 `/?lang=ar` | 19:51（曼谷）抓取成功，`Excluded by ‘noindex’ tag` | Google 读取到 `noindex` 与 `https://autolinkglobal.com/?lang=ar` Canonical；没有申请索引。 |

首页实时检查仍显示 **2/26 个资源未加载**：原主脚本为 `Other error`；匿名 `/autolink/me` 被 robots 拦截，这一私有接口限制应继续保留。Google JavaScript Console 面板无消息。核心页面虽已可靠展示，主脚本错误仍是后续独立调查项。

截图证据保存在本地 `release-evidence/gsc/`：`20261012-home-live-render.png`、`20261012-home-live-html.png`、`20261012-home-live-resource-errors.png`、`20261012-arabic-noindex-live.png`。这些带有 Search Console 账户界面的截图不提交到公开仓库。

30 分钟生产监控完成后刷新复查，根 Sitemap 的 Search Console 详情仍为 **`Sitemap could not be read`、Last read 10/12/26、Discovered pages 0**；[最终状态截图](../release-evidence/gsc/20261012-sitemap-after-monitor-still-error.png)留存本地。公网 HTTP/2 请求为 200、`application/xml`、354 字节、无重定向，三个子地图均可解析。更进一步，20:01（曼谷）的 **Google URL Inspection Live Test 对根 XML 显示 `Crawl allowed: Yes`、`Page fetch: Successful`，Google 实际读取到的源码正是三个非空子地图**；本地证据为 `20261012-sitemap-live-fetch-success.png` 与 `20261012-sitemap-live-source.png`。URL Inspection 的抓取成功与 Sitemap 处理器成功是两个不同结论，不能据此把 `Couldn't fetch` 标记为已解决。[Google 官方文档](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)也说明提交 Sitemap 不保证 Google 立即下载或使用。此前已经提交过根 Sitemap，本轮没有进行高频重复提交；需要后续结合 Google 实际抓取日志或后台状态再定因。

## 4. 性能前后对比

Mac Chrome 154、Lighthouse CLI 13.5.0，真实公网同一测试脚本与配置；手机和电脑各三次冷启动，以下为中位数。原始 12 份 JSON 位于本地 `tests/results/round11/lighthouse-public-before/` 和 `tests/results/round11/lighthouse-public-after/`。

| 首页 | Performance | LCP | TBT | CLS |
| --- | ---: | ---: | ---: | ---: |
| 发布前手机 | 34 | 8,189 ms | 3,003 ms | 0.100 |
| 发布后手机 | 62 | 1,787 ms | 2,333 ms | <0.001 |
| 发布前电脑 | 34 | 4,566 ms | 553 ms | 0.061 |
| 发布后电脑 | 49 | 4,685 ms | 282 ms | 0.062 |

手机 LCP 达到 2.5 秒目标，CLS ≤0.1；**手机 TBT 仍远高于 200 ms 目标**，电脑 LCP 略退步。4 倍 CPU、1.6 Mbps 的独立 trace 中，发布前主脚本约 2.29 MB 解码、460 KB 传输，传输耗时约 4.15 秒，记录多个 50 ms 以上长任务；发布后 8 秒内先由静态首页和极氪图片完成展示，最长任务约 132 ms，但原 React 应用及其脚本在较慢首访中仍会较晚接管。一次 25 秒公网手机浏览器检查确认原应用最终加载、现有功能保留。没有为追分删除内容或重做 UI。

## 5. 隔离测试、安全与发布身份

- 本地后端共运行 227 项测试，222 项通过、5 项跳过；阿里云 **linux/amd64** 隔离环境同样运行 227 项、跳过 5 项，耗时 168.497 秒。最终候选在隔离环境完成候选→旧版→候选回滚演练，比较 244 个公开车型和 53 个品牌的 HTML 指纹、227 个车型及 10 个品牌 Sitemap URL，结果 `ISOLATED_ROUND11_QA_OK`；证据 `/opt/autolink-releases/52c6934-round11-20261012/isolated-qa-ok.json`。
- 正式公网阻断主脚本测试通过；九语言初始 HTML、英语→中文→英语及其他语言动态 SEO、阿拉伯语 RTL、桌面及手机导航/登录入口的 Playwright 集成测试通过。测试脚本最初因隐私弹窗晚于 12 秒出现而超时，调整等待顺序后复测 `ROUND11_HOME_INTEGRATION_OK`，这是测试等待条件问题，不是网站入口被弹窗永久遮挡。
- 公网手机浏览器只读检查 `/buyer/login` 与 `/merchant/login` 均返回 200，并在客户端加载后显示各自登录表单；没有使用真实客户账号提交表单。匿名 `/autolink/me` 继续返回 401，Google 对该私有 API 的 robots 限制保持有效。
- macOS Safari 公网访问从中文首页切换到英语，无刷新更新了 URL、页面标题、正文、极氪素材及导航；本地 Safari 的阿拉伯语 RTL 切换此前通过。此项为 Safari 桌面浏览器核对，不冒充 iPhone Safari 测量。
- PR #11 发布源码提交的两项 `source-security` GitHub Actions 均实际运行并成功。固定 Auth AMD64 归档的 Trivy 结果为 0 个漏洞条目；Gitleaks 检查未发现发布阻断泄露。生产 Cookie、CSRF、私有 API、匿名权限与旧业务隔离保留。
- 新 Auth 实际 Docker Image ID 为 `sha256:5dfea447ad82555952ec7cb037b3e877bf361cf162267f7b82e16822f8736049`；Web Image ID 为 `sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb`。Auth 完整不可变归档 `/opt/autolink-releases/52c6934-round11-20261012/images/auth-amd64.tar`，SHA-256 `0e28722ff8584cf749b1ae711d3d1ae2c91a09823873cfd0269ff100a0d7c1b3`，架构 AMD64。**Image ID 不是远程 Registry Manifest Digest**；本次沿用同主机固定镜像归档、加载镜像校验及禁止部署时重新构建/拉取的交付方式。

## 6. 最新备份、恢复与上线监控

切换前最新一致性备份清单：`/opt/autolink-backups/round11-20261012/final-20261012T123639Z/release-backup-manifest.json`。真实数据库来源由运行容器挂载确认，为 `/var/lib/docker/volumes/autolink-demo_auth_data/_data/autolink-auth.sqlite3`；一致性备份为同目录 `autolink-auth-20261012T123639Z.sqlite3`，SHA-256 `ec04bd0080d99adc7e2faac841aa986b4132da42981c2af4fac74811b39e8317`。清单记录 SQLite、上传文件、Caddy 配置和证书卷、旧源码、旧镜像、当时公开目录；隔离恢复验证 `isolatedRestoreVerified=true`。切换没有清空或覆盖数据库、持久卷。

生产脚本在服务器 tmux `round11-cutover` 执行，先 Auth 后 Web，固定镜像、不拉取、不重建。正式切换于 **12:38 UTC** 开始，12:38:31 UTC 完成 Auth/Web 健康及核心探针。状态和完整日志位于 `/opt/autolink-release-state/round11-20261012/52c6934-round11-20261012/`；每分钟检查页面、索引规则、容器与固定镜像，连续失败自动回滚，连接断开不影响脚本。

**30 分钟监控通过。** 脚本于 **13:09:57 UTC** 写入 `completed`，日志有 30 次 `STATE monitoring`、**0 次 `MONITOR_FAILURE`**，没有触发回滚。最终状态固定运行中的 Auth/Web Image ID 与发布锁一致；两容器均为 `healthy`、重启次数 **0**。每轮检查 HTTPS、首页与公开车型/品牌、九语言和 Sitemap；每五轮检查生产 SQLite `quick_check`、CPU、内存和磁盘。第 26 轮 Auth 约 83.38 MiB、Web 约 51.89 MiB，磁盘可用约 17.8 GB。完整原始日志为上述 `cutover.log`，本地截图 `release-evidence/round11-30-minute-completed.png`；切换过程未超过五分钟中断上限。

## 7. 尚未解决的问题

1. Search Console 仍未成功读取根 Sitemap；目前只能确认修正了两个空子地图且公网 XML 正常。不能把 295 条 URL、HTTP 200 或过去的提交回执当作 Google 已发现或已索引。
2. Google 实时检查仍将旧首页主脚本标为 `Other error`；渐进增强已避免核心内容空白，但底层失败机制尚未定位，手机 TBT 仍高。
3. 电脑 LCP 在同条件测试中略退步；首页性能应在不改动已审核 SEO 内容的独立性能任务中继续处理。
