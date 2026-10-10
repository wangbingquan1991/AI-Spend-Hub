# Project status — AI Spend Hub v0.3.2-dev

- **Stage**: PR #1（审核队列）与 PR #2（SQLite 快照与恢复演练）均已合并到 main；第 6 轮新增独立进程 HTTP 审核队列 E2E 测试，放在独立待审分支。
- **Completed**: 保留 v0.2 的订阅/现金流/钱包/SQLite/n8n API；新增候选队列、审核/拒绝 API、来源编号防冲突、审核日志、独立审核 UI、升级初始化和文档。
- **Verification**: 本轮本机执行 `python3 -m unittest discover -s tests -v`：18/18 PASS（原 17 项 + 独立进程 HTTP E2E 1 项）；单独 E2E 连续执行 3 次均 PASS；新增测试 `py_compile` PASS。Python 3.13 的旧测试出现部分 SQLite `ResourceWarning`，未改变本轮业务代码。真实浏览器→HTTP 交互、Synology/Docker 实机仍未验收。
- **Data protection**: 原账本表不删除；候选审核表独立，避免未经审核入账；没有连接用户 Gmail、银行卡、供应商平台。
- **Known gaps**: 不支持跨来源的同一付款语义去重；网页 JSON 备份不包含候选审核队列；目前无多用户权限角色；NAS 实际环境未验收。
- **This iteration**: 新增 `tests/test_http_review_e2e.py`，以子进程启动真实 `app.py` 服务，仅监听 `127.0.0.1` 随机端口并使用临时合成 SQLite：验证候选入队不计费、批准入账一次、拒绝不入账、同票据重复/冲突、审核事件及服务重启持久化。未修改业务代码、不连接任何外部账号、不读真实账单、不部署。
- **Next**: Review PR for this test-only increment; keep browser-to-server E2E and Synology/Docker live integration as untested. Future independent P0: EML/CSV offline invoice parsing and supplier aliases (opt-in integrations only after approval).
- **Repository**: https://github.com/wangbingquan1991/AI-Spend-Hub
