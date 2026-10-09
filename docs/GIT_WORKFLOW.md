# Git 管理规范 / Git workflow

目标仓库：[wangbingquan1991/AI-Spend-Hub](https://github.com/wangbingquan1991/AI-Spend-Hub)

- `main` 为稳定分支。新功能使用 `feat/<description>`，修复使用 `fix/<description>`，推荐通过 PR 合并。
- 提交信息优先遵循 Conventional Commits，例如 `feat: add invoice review queue`、`fix: prevent duplicate charges`、`docs: update NAS guide`。
- 每次改动先运行 `python3 -m unittest discover -s tests -v`，检查 HTML JS 语法；涉及网络、浏览器或容器的变更应补充相应验收。
- 更新 `CHANGELOG.md` 和 `STATUS.md`，注明已完成事项、风险、未验证项与下一步。
- 发布可打标签 `v0.2.0` 等。不要将未经 NAS 实机验收的版本写为生产就绪。
- **绝不上传** `.env`、个人支付信息、真实账单、SQLite 数据库、访问令牌、API 密钥、CSV/JSON 私人备份。发布前检查 `git status`、`git diff --cached` 和 `git ls-files`。
- 私有支付数据只放本地 Docker 卷/指定 NAS 数据目录，并做好异地备份。不要因仓库为公开仓库而放松脱敏要求。
