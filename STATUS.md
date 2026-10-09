# Project status — AI Spend Hub v0.3.0-dev

- **Stage**: v0.3a 候选账单审核功能开发并测试，待 GitHub PR/发布验收。
- **Completed**: 保留 v0.2 的订阅/现金流/钱包/SQLite/n8n API；新增候选队列、审核/拒绝 API、来源编号防冲突、审核日志、独立审核 UI、升级初始化和文档。
- **Verification**: 原 6 项 + 新增 7 项后端 HTTP 测试共 13 项 PASS；两个页面 JS 语法测试通过。真实 Chromium→HTTP 端到端/NAS 容器运行仍未验收。
- **Data protection**: 原账本表不删除；候选审核表独立，避免未经审核入账；没有连接用户 Gmail、银行卡、供应商平台。
- **Known gaps**: 不支持跨来源的同一付款语义去重；网页 JSON 备份不包含候选审核队列；目前无多用户权限角色；NAS 实际环境未验收。
- **Next**: SQLite 整库备份与恢复演练、支持 EML/CSV 离线票据解析、供应商字段别名规则、用户授权的 Gmail 接入、群晖和浏览器 E2E 验收。
- **Repository**: https://github.com/wangbingquan1991/AI-Spend-Hub
