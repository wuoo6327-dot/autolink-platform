# 商家自动启用与正式协议发布说明

## 当前阻塞

真实 `auth/supplier-agreement.json` 仍为 `REVIEW_DRAFT`。本轮没有修改其版本、正文或任何字节。新商家只能保存资料草稿；协议确认及账号启用会返回 409。不得用测试协议发布线上，也不得把现有草稿标为正式协议。

## 正式新版本要求

由平台负责人提供并审核真实法律信息，使用**新的 version** 发布正式文件。保留历史协议版本及确认记录，不能用旧版本号替换正文、来源哈希或状态。正式文件须有 `status: "FINAL"`、`acceptanceEnabled: true`、`pendingFields: []`，正文和元数据不能含“待补”“待确认”“律师终审后确定”等占位。

`legalDetails` 对象必填以下非空字符串，不能自动代填或用测试内容冒充：

| 字段 | 真实资料要求 |
| --- | --- |
| operatorLegalName | 平台运营主体的法定名称 |
| operatorRegistrationNumber | 运营主体登记号 |
| operatorRegisteredAddress | 法定注册地址 |
| operatorContactAddress | 实际联系地址 |
| supportEmail | 可用客服邮箱，格式必须是邮箱地址 |
| governingLaw | 律师确认的适用法律 |
| disputeJurisdiction | 律师确认的争议管辖 |
| effectiveDate | `YYYY-MM-DD`，合法日期且不晚于当天 |

正文 `bodySha256` 必须与 UTF-8 正文 SHA-256 相符；`sourceSha256` 记录该正式版本来源文件。法律资料和正文应一致。校验只能检查格式、状态及明显占位，不能证明公司信息真实或替代法律审核。

## 启用与车源审核

已验证邮箱的真实业务账号可同时使用买家和商家工作台，不需要改变原 `users.role`。企业负责人填写现有必填资料、上传营业执照和场地/库存照片、确认当前正式协议后，只有**主动提交启用**这一写操作才能启用账号。GET、协议确认或服务重启均不能自动把历史申请转为已启用。

旧 `PENDING` 申请须确认正式协议并主动重新提交；旧 `APPROVED` 记录按原状态保留。暂停账号、暂停企业、测试工作区和销售队员不能自行启用。账号启用不等于平台尽调认证，不保证企业资质、库存或履约。

车源依旧从 DRAFT 开始，独立提交、平台审核（包含现有图片/价格门槛）后才能上线。商家启用不会直接发布任何车源。

## 只读与显式已读

报价和询盘的 GET 不再更新 VIEWED 或 EXPIRED。过期状态仅用于响应计算，数据库历史状态保留。报价已读使用 `POST /autolink/buyer/quotes/{id}/viewed`；询盘已读使用现有 `PUT /autolink/supplier/inquiries/{id}` 的 `status: "VIEWED"`。过期报价的接受、拒绝及已读操作返回 409，不能返回假成功。

## 隔离测试

`auth/test_trade.py` 在每个测试的临时目录创建明确标注 SYNTHETIC QA 的 FINAL 文档，通过构造器参数注入测试服务。版本为 `synthetic-final-v1-isolated-tests`，邮箱使用 `example.com`，有效日期为 `2020-01-01`。数据库、上传目录和邮件传输均为临时或 Mock，不修改实际协议、不接触生产数据、不发真实邮件。
