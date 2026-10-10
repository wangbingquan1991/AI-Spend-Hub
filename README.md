# AI Spend Hub v0.3-dev · AI 消费总账

适合个人 / 家庭内网使用的 AI 账单管理服务，兼容 v0.1 HTML JSON 备份。**0 运行依赖**：Python 标准库 + SQLite，附 Docker Compose。默认无外部网络请求。

## GitHub 源码

```bash
git clone https://github.com/wangbingquan1991/AI-Spend-Hub.git
cd AI-Spend-Hub
```

Git 开发与敏感信息保护规则见 [`docs/GIT_WORKFLOW.md`](docs/GIT_WORKFLOW.md)，版本更新见 [`CHANGELOG.md`](CHANGELOG.md)。

## 功能

- ChatGPT、Claude、Cursor、Higgsfield、OpenAI API、火山方舟等任意平台订阅管理；周/月/季度/年付，下一次扣费、月均承诺成本和未来 30 天续费预测。
- 实际现金流流水：`subscription` 订阅扣款、`api` 已出账的 API 费用、`topup` 积分/预付充值、`oneoff` 一次性支付、`refund` 退款（用正金额录入、报表自动扣减）。
- 剩余积分/余额快照 **不再计费**，以免与已购充值重复统计；模型 tokens 的使用量也不会直接算成现金支出。
- 原币记录 + 手动设置币种汇率；每笔历史汇率固化以防汇率变化导致历史账单漂移。汇率仅估算，非结算凭证。
- 支出趋势、分类、预算、订阅编辑与流水编辑、CSV/JSON 导入导出。
- SQLite 持久化、乐观并发修订号（避免静默覆盖）；授权 API 批量导入带 `source + externalId` 去重，适合 n8n / OpenClaw 发送已核实账单。
- v0.3-dev 新增独立候选账单审核队列（审批、拒绝、事件记录、重复单号冲突保护），通过 `/review` 在浏览器审核后才真正入账。见 [`docs/REVIEW_API.md`](docs/REVIEW_API.md)。
- **不包含**：直接读取 Google/Gmail、银行卡、支付宝、微信、第三方 AI 供应商数据；不连接这些账号就无法自动发现它们的费用。

## 快速启动 · 群晖 DSM / NAS

```bash
git clone https://github.com/wangbingquan1991/AI-Spend-Hub.git
cd AI-Spend-Hub
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(36))'
# 把输出粘贴进 .env 的 AI_SPEND_ACCESS_TOKEN=...，不要使用示例值。
docker compose up -d --build
```

默认只监听宿主机 `127.0.0.1:8765`，通过本机 `http://127.0.0.1:8765` 打开，输入刚设置的访问令牌。如果你从内网电脑访问群晖，在 `.env` 将 `AI_SPEND_BIND_IP` 改为 NAS 的 **内网 IP**（例如 192.168.1.20），再运行 `docker compose up -d`，访问 `http://192.168.1.20:8765`。Windows/macOS 上直接运行 `python3 app.py` 也可（见下）。

**网络安全**：应用只适合受信任的内网 / VPN。访问令牌通过 HTTP 明文传输，跨设备访问建议配套 HTTPS 反向代理或 Tailscale。切勿端口转发至互联网。`.env` 保密；请勿上传 GitHub。`compose.yaml` 默认只将端口绑定到回环地址。

数据保存在 Docker 命名卷 `ai_spend_data` 的 `/data/spend.sqlite3`。不要直接删除卷或执行 `docker compose down -v`。如需群晖文件夹挂载，请改 Compose 映射为 `/volume1/docker/ai-spend-hub/data:/data`，并确保容器 UID 10001 对目录有写权限。NAS 需安装 Container Manager / Docker Compose。

备份：网页「导出备份」仅备份主账本 JSON，**不会包含审核候选和事件**。全库请使用 `tools/ledger_snapshot.py` 创建 SQLite 在线快照、校验和恢复到新文件演练，详情见 [`docs/BACKUP_RESTORE.md`](docs/BACKUP_RESTORE.md)。Docker 镜像已包含该工具，可在容器内运行，务必将备份从 Docker 卷复制到受限的安全位置。

原先的手工 SQLite Online Backup 命令仍可参考（没有自动校验和覆盖防护，优先使用上述工具）。如在容器中执行，请确认文件路径位于持久化挂载目录：

```bash
docker compose exec -T ai-spend-hub python -c "import sqlite3; src=sqlite3.connect('/data/spend.sqlite3'); dst=sqlite3.connect('/data/spend-backup.sqlite3'); src.backup(dst); dst.close(); src.close()"
```

用 Docker 工具从命名卷另行复制备份文件，或优先采用 UI JSON 导出。生产部署建议另配定时备份、权限控制及 HTTPS。

## 本地开发（不需要 pip install）

```bash
export AI_SPEND_ACCESS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(36))')"
export AI_SPEND_DB="$PWD/data/spend.sqlite3"
python3 app.py --host 127.0.0.1 --port 8765
```

到 `http://127.0.0.1:8765` 输入终端环境变量对应的访问令牌。纯 HTML 模式也可以打开 `web/index.html`，此时数据仍存浏览器，不涉及服务器同步。**两种模式不是同一个账本**。

## 把 v0.1 数据迁移到 NAS

1. 在旧版 `ai-spend-hub.html` 页面点「导出备份」，保存 JSON。
2. 打开新版 NAS `http://NAS_IP:8765` 并输入访问令牌。
3. 在新版点「导入数据」，选旧版 JSON，确认 **覆盖服务器现有账本**。建议先备份 NAS 的现有账本。
4. 核对流水笔数、历史金额及订阅续费日。不要直接拷贝浏览器 LocalStorage 到服务器。

## n8n 自动导入接口

所有 `/api/*` 均需要请求头：`Authorization: Bearer <AI_SPEND_ACCESS_TOKEN>`。用户界面令牌仅储存于浏览器 `sessionStorage`，刷新同标签保持，关闭标签会话结束；不会写入导出的账本。

- `GET /healthz`：探活（无认证，无敏感信息）
- `GET /api/state`：取得 `{revision, state}`；页面与 JSON 导入使用它
- `PUT /api/state`：提交 `{revision, state}`，旧修订号返回 **409**；有并发写入时 UI 会重新载入（当前输入需重做）
- `GET /api/summary?month=2026-10`：汇总，按人民币折算，不含积分余额快照
- `POST /api/transactions/import`：导入 `{"transactions":[...]}`，**全部先验证再写入**；返回 imported、skipped、revision；按 `(source, externalId)` 幂等去重

```bash
curl -sS http://127.0.0.1:8765/api/summary \
  -H "Authorization: Bearer $AI_SPEND_ACCESS_TOKEN"

curl -sS http://127.0.0.1:8765/api/transactions/import \
  -H "Authorization: Bearer $AI_SPEND_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @examples/import.json
```

**导入必填**：`date`(YYYY-MM-DD)、`provider`、`type`、`amount`(非负的原币数值)、`currency`(CNY/USD/JPY/EUR/HKD)、`source`(如 `gmail-receipt`)、`externalId`(上游账单或消息稳定且唯一的编号)。`rateToCNY` 可选，缺省时用当前手动汇率；已入库后不会改变。`notes` 可选。接口仅接收 **确定发生的付款 / 退款**，不要把“模型 tokens 用量”、Higgsfield credits 用量当成真实付款导入。存在已手工录入的同一账单时，先人工核对，防止重复。

n8n：用邮件触发或 CSV 解析节点把 **核验过的账单** 转成上述 JSON；HTTP Request 节点调用 NAS 的 `POST /api/transactions/import`，设置 Bearer 身份认证（建议通过 n8n 凭据管理，不写死在工作流 JSON），Content-Type application/json。n8n 容器与服务需网络可达；如果走独立 Compose 网络，使用 NAS 内网地址或加入同一 Docker 自定义网络。详情见 `examples/n8n-integration.md`。

## 后续里程碑

详见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。当前 v0.3a 为审核队列，可由 n8n 发送结构化候选账单，尚未连接 Gmail 或其他供应商。将来 Gmail/EML/CSV 收据解析（v0.3b）需要用户主动授权。

## v0.3 候选账单审核（NAS 模式）

- `POST /api/invoices/propose`：接收结构化候选；同源票据去重，冲突返回 409，数据不会直接计入支出。
- `GET /api/invoices?status=pending`：查询待审核候选。
- `POST /api/invoices/decision`：人工批准或拒绝；批准才生成真实交易，审批事件可查询。
- `GET /api/invoices/events`：审核事件历史。
- `GET /review`：人工审核网页（仅 NAS 服务端模式）。

示例候选：[`examples/review-candidates.json`](examples/review-candidates.json)。API 细节：[`docs/REVIEW_API.md`](docs/REVIEW_API.md)。

**重要备份区别**：网页 JSON 导出目前只备份主账本，不含独立 SQLite 审核表；需要完整保留待审核队列和事件历史时，必须用上文的 SQLite Online Backup 备份整个数据库。

## 测试

### 离线 HTTP 审核队列 E2E（真实服务进程、合成数据）

```bash
python3 -m unittest discover -s tests -p 'test_http_review_e2e.py' -v
# 完整回归（包含此测试与历史测试）：
python3 -m unittest discover -s tests -v
```

新增测试会在随机 `127.0.0.1` 端口启动独立 `app.py` 子进程，使用一次性模拟访问令牌及操作系统临时目录内 SQLite；通过真实 HTTP 请求完成候选账单入队、批准、拒绝、重复票据幂等、审核日志和服务重启核对。测试结束清理进程和临时数据库；**不访问 Gmail、银行、AI 厂商接口或任何真实付款账号**，不需要配置任何实际凭证。

这是 HTTP 服务进程级 E2E，**不是浏览器界面 E2E，也不是 Docker/Synology 部署验收**。该测试使用固定合成汇率 `1 USD = 7 CNY`，例如模拟付款 12.50 USD 的已批准账单计为 87.50 CNY；待审核和拒绝的账单都不计现金支出。

```bash
python3 -m unittest discover -s tests -v
node -e "const fs=require('fs'),vm=require('vm');new vm.Script(fs.readFileSync('web/index.html','utf8').match(/<script>([\\s\\S]*?)<\\/script>/)[1]);console.log('JS syntax OK')"
```

目前是单用户内网 MVP；不是财务审计系统。并发状态编辑冲突会阻止覆盖，但账单服务依旧需要备份与访问管理。

## 注意：账单幂等与测试边界

UI 的 CSV 导出带有 `source,externalId` 字段。CSV 再次导入时，如二者都存在，可跳过重复引用；对没有唯一票据编号的 CSV，系统**无法可靠识别**同额重复扣款，请先检查。n8n API 导入强制携带稳定外部编号以便去重。

浏览器模拟测试（需开发环境安装 Playwright 与 Chromium）可执行 `python3 tests/browser_offline_check.py` 和 `python3 tests/browser_server_mock_check.py`。当前测试环境的 Chromium 企业策略阻止访问本地 HTTP URL，因此无法在此环境做浏览器对真实服务的网络端到端测试；服务端 HTTP API 与浏览器交互分别已经测试。Docker 镜像在本环境未执行实际构建和群晖部署验收。
