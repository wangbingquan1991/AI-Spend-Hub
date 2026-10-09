# SQLite 全量备份与恢复演练（v0.3b P0）

**范围**：`ledger`（订阅、交易、钱包）、`invoice_reviews`（审核候选）、`review_events`（审核记录）。页面上的 JSON 导出仅包含主账本，不能代替完整 SQLite 备份。

所有操作均为本地文件操作；不会访问 Gmail、支付账号、API，也不会启动或部署服务器。推荐将备份存入 **Git 仓库之外**、仅本人可访问并已加密的目录；不要将实际数据库或备份发送到公共 GitHub。

## 1. 创建在线快照

应用运行时也可以使用 SQLite Online Backup API，它会包含已经提交的 WAL 内容。下面路径仅为示例，先确保目标父目录存在：

```bash
python3 tools/ledger_snapshot.py backup \
  --db /data/spend.sqlite3 \
  --out /private/backups/ai-spend-2026-10-09.sqlite3
```

- `--out` **必须是不存在的新文件**，不会覆盖旧备份、现有数据库或已有符号链接。
- 新文件的 Unix 权限为 `0600`，避免被其他本地用户读取；Windows 权限依赖操作系统 ACL，请自行限制共享权限。
- 命令自动做 SQLite `PRAGMA integrity_check`、三表存在性检查和主账本结构检查，并输出修订号及每张表的**记录数量**，不输出账单或邮件内容。
- 如任何步骤失败，新创建的不完整目标文件会清理；源库不受修改。不要用 `docker compose down -v` 清空生产数据。

### Docker Compose 中运行（仅提供命令，不会自动部署）

Docker 镜像会包含 `/app/tools/ledger_snapshot.py`。容器内 `/data` 是持久化卷，先创建备份子目录：

```bash
docker compose exec -T ai-spend-hub mkdir -p /data/backups
docker compose exec -T ai-spend-hub python tools/ledger_snapshot.py backup \
  --db /data/spend.sqlite3 --out /data/backups/snapshot.sqlite3
```

**注意**：同一 Docker 卷内的快照只是临时副本，并不构成异地备份。应使用 `docker cp` 或受控 NAS 文件备份将副本转移至已加密、受限的卷外位置，再确认恢复演练成功。不要将数据库作为 PR 附件上传。

## 2. 校验已有备份

```bash
python3 tools/ledger_snapshot.py verify \
  --file /private/backups/ai-spend-2026-10-09.sqlite3
```

如果校验失败或缺少审核表，禁止继续恢复；该工具只支持完整的 v0.3 数据库格式。

## 3. 恢复到**新文件**演练

```bash
python3 tools/ledger_snapshot.py restore \
  --file /private/backups/ai-spend-2026-10-09.sqlite3 \
  --out /private/backups/restore-rehearsal.sqlite3
```

恢复目的地必须不存在。此命令**不会**替换当前正在使用的 `/data/spend.sqlite3`，也不会修改容器配置或重启服务。演练完成后分别 `verify` 备份和演练库，检查 revision、三表计数一致；若要真正切换数据，应先停止应用、另行验证和人工执行运维操作（不由此脚本自动执行）。

## 注意事项

- 在线快照只包含备份时已经提交的交易。仍在审核的候选不会影响真实现金支出；恢复后依旧是待审核。
- 账单统计口径是**已实际支付的现金流**：订阅、已支付 API 账单、预充值、一次性支出计入，退款抵减；积分余额、tokens 使用量和审核候选不计入现金流。充值金额与后续积分消耗不可再记一笔现金支出。
- 备份是高度敏感的财务数据；需要最小文件权限、加密的异地副本、定期恢复演练。SQLite 完整性通过不等于业务付款真实性得到确认。
- 该功能只提供可测试的离线工具；尚未在 Synology NAS 或运行中的 Docker 容器上实机验收，**不宣称生产就绪**。
