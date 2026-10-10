# 第七轮公开目录索引规则

本轮保留 234 个车型及 53 个品牌的全部九语言页面。规则只控制搜索引擎索引资格，不修改数据库目录、车源、价格、用户和业务数据。

## 当前发布范围

| 页面 | 可索引 | 暂缓索引 |
| --- | ---: | ---: |
| 195 个资料完整车型的中文页 | 195 | 0 |
| 这 195 个车型的其余八语言 | 0 | 1,560 |
| 39 个资料不足车型的九语言 | 0 | 351 |
| 53 个缺少介绍品牌的九语言 | 0 | 477 |
| 合计（仅车型及品牌详情） | 195 | 2,388 |

以上是技术索引资格，不能代表 Google 已收录。品牌/车型目录列表及其他公开页面另算。

## 一个规则用于所有出口

`auth/seo_service.py` 的 `index_policy` 同时用于初始 HTML、公开 API 和 `auth/trade_service.py` 的 Sitemap。前端 `site/assets/business-seo.js` 读取相同 API 元数据，避免 React 加载后把 noindex 改回 index。

- 可索引页：`index, follow`、当前语言自身 Canonical、仅含通过审核语言的 hreflang；英语未通过时 x-default 指向已通过的语言。
- 暂缓页：HTTP 200、`noindex, follow`、当前语言自身 Canonical、不输出 hreflang、不加入车型或品牌建议索引 Sitemap。
- robots 允许抓取车型/品牌页面和必要公开资源，使搜索引擎能够读取 noindex；私有后台继续禁止索引。

## 真实资料补齐后的恢复

车型中文资格自动检查：目录及品牌有效，参考资料关联正确车型，提供来源网站、查询日期、有效年份、版本及参数组；检查展示范围内至少八条实际参数，每个展示版本至少八个实际值。价格不参与补齐参数数目。无效 JSON、无效来源、缺失年份或内容不足均不通过。

其余语言还须完成准确本地化，消除参数正文中的未翻译中文，并在 `site/locales/seo-index-reviews.json` 记录 `sourceFingerprint`、审核人及审核证据。指纹绑定目录内容、参考资料、参数词典和本轮已核验术语；资料或词典改变会使旧审核失效。品牌需真实介绍及关联车型，并完成同样审核。当前审核表为空，未伪造任何审核记录。

## 参数翻译边界

`seo-verified-terms.json` 只加入可准确对应的英语技术术语。原始数字、单位和型号保持不变。仅对完整字段精确匹配；取消在配置名内任意替换汉字的做法，避免“挡”被译成 Block 或营销版型被拼坏。无法确认的配置名、厂家及服务条款保持原文，相关语言继续 noindex。

术语依据包括：[生态环境部 China VI 标准](https://english.mee.gov.cn/Resources/standards/Air_Environment/emission_mobile/201705/t20170524_414680.shtml)、[ZF 自动变速器](https://www.zf.com/products/en/cars/products_64238.html)、[ZF 双离合变速器](https://www.zf.com/products/en/cars/products_64272.html)、[Bosch 永磁同步电机](https://www.bosch-mobility.com/en/solutions/electric-motors/electric-motors-and-active-parts/)。这些来源用于术语核对，不用于替某个车型添加配置或指定供应商。

## 验证

后端质量测试覆盖 234 个车型的 195/39 分组、九语言暂缓规则、品牌规则、JSON 失效保护、真实资料结构校验、翻译数值保持及审核失效。独立 HTTP 检查实际读取 2,583 个初始 HTML、Sitemap 与 robots；前端测试确认页面初始化和异步加载继续遵守相同索引资格。
