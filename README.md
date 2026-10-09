# AUTOLINK 独立安全候选（未部署）

仓库维持私有，分支 `codex/security-release-candidate` 从 main `96f1f34` 拆出。

此分支仅加入账号关闭保护、私有车图授权、Cookie 关闭入口与依赖/安全检查。没有合并 main 或部署生产；没有添加真实库存或修改真实业务记录。现有源代码包含邮箱/密码、交易和会员状态功能，但真实第三方验收、收费闭环以及正式法律资料仍不能由此判定完成。

- 范围和测试边界：`docs/SECURITY_RELEASE_SCOPE.md`。
- 实际镜像风险：`docs/ROUND2_IMAGE_FINDINGS.md`。源码扫描通过不能替代镜像 HIGH 风险评审。
- 自动安全检查：`docs/SECURITY_SCANNING.md`。
- 完整业务与 SEO 候选在原 `codex/repair-round1` 和追加分支 `codex/preflight-round2`，不在此安全分支。

真实供应商协议仍为草稿，不能据此开放正式自助入驻。合并和部署须由平台所有者审阅固定提交、测试、法律范围与回滚方案后决定。

生产配置、SQLite、私有文件和备份不在仓库内。维护生产时保留数据库及上传卷；不要执行删除卷或用旧数据库覆盖运行中的记录。
