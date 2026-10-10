# Project status — AI Spend Hub v0.3.3-dev

- **Stage**: PR #1, #2, #3 已合并到 `main`（基线 `cd9a297`）。本轮仅在 `feat/cross-source-invoice-warnings` 实现 P0 只读跨来源疑似重复提示，待 PR 复核。
- **Completed**: 保留 v0.2 的订阅/现金流/钱包/SQLite/n8n API；新增候选队列、审核/拒绝 API、来源编号防冲突、审核日志、独立审核 UI、升级初始化和文档。
- **Verification**: 纯合成数据的新增跨来源 HTTP 边界测试 8/8 PASS；与本地完全匹配 GitHub 原始 SHA 的 `app.py`、`tests/test_app.py` (6) 和 `tests/test_review.py` (7) 联跑，共 21/21 PASS；`app.py` py_compile 和两页 JS 语法 PASS。PR #2 快照测试 4 项及 PR #3 子进程 E2E 1 项未在本轮本地重新运行，**不能称 26/26 完整 main 回归**。既有 SQLite ResourceWarning 仍存在。浏览器、Docker、Synology 未验收。
- **Data protection**: 原账本表不删除；候选审核表独立，避免未经审核入账；没有连接用户 Gmail、银行卡、供应商平台。
- **Known gaps**: 跨来源只按保守规则提示（相同标准化供应商、日期、类型、原币金额、币种，来源不同）；不支持供应商别名与宽松日期匹配、不能证明同一付款；同一付款仍可能人工重复批准。网页 JSON 备份不含审核候选；NAS 实机未验收。
- **This iteration**: `GET /api/invoices` 为待审候选返回只读 `possibleDuplicates`（最多五条），`/review` 页面显示警示并在人工决定前再次提示；完全不更改候选决策、自动入账、去重强制策略、账本金额或数据库模式。合成测试覆盖不同供应商不误报、跨来源候选、已入账匹配、拒绝后不再提示、同来源忽略、日期/类型/币种/金额差异、人工最终决定与旧幂等。
- **Next**: PR 审核后再另行规划供应商别名/离线 EML/CSV；真实浏览器到 HTTP 服务 E2E、NAS/Docker 部署和旧 SQLite 连接关闭警告仍是独立待办。未读取账号、凭证或真实账单，不部署、不消费。
- **Repository**: https://github.com/wangbingquan1991/AI-Spend-Hub
