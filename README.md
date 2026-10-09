# AI Spend Hub v0.2 · AI 消费总账

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
- **不包含**：直接读取 Google/Gmail、银行卡、支付宝、微信、第三方 AI 供应商数据；不连接这些账号就无法自动发现它们的费用。

## 快速启动 · 群晖 DSM / NAS

```bash
unzip ai-spend-hub-v0.2.zip
cd ai-spend-hub-v0.2
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(36))'
# 把输出粘贴进 .env 的 AI_SPEND_ACCESS_TOKEN=...，不要使用示例值。
docker compose up -d --build
```

默认只监听宿主机 `127.0.0.1:8765`，通过本机 `http://127.0.0.1:8765` 打开，输入刚设置的访问令牌。如果你从内网电脑访问群晖，在 `.env` 将 `AI_SPEND_BIND_IP` 改为 NAS 的 **内网 IP**（例如 192.168.1.20），再运行 `docker compose up -d`，访问 `http://192.168.1.20:8765`。Windows/macOS 上直接运行 `python3 app.py` 也可（见下）。

**网络安全**：应用只适合受信任的内网 / VPN。访问令牌通过 HTTP 明文传输，跨设备访问建议配套 HTTPS 反向代理或 Tailscale。切勿端口转发至互联网。`.env` 保密；请勿上传 GitHub。`compose.yaml` 默认只将端口绑定到回环地址。

数据保存在 Docker 命名卷 `ai_spend_data` 的 `/data/spend.sqlite3`。不要直接删除卷或执行 `docker compose down -v`。如需群晖文件夹挂载，请改 Compose 映射为 `/volume1/docker/ai-spend-hub/data:/data`，并确保容器 UID 10001 对目录有写权限。NAS 需安装 Container Manager / Docker Compose。

备份：在网页「导出备份」保存 JSON（可重新导入）；系统级备份可通过 SQLite backup API 创建一致性备份，而不是运行时直接复制 `.sqlite3`。可在容器中执行：

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

## 未来阶段建议

- v0.3：经用户明确授权的 Gmail 账单检索/解析、发票审核队列、预付/积分对应关系、真正的到账对账。
- v0.4：按供应商官方 API 或下载账单对账、异常提醒、真实历史汇率、账单源统一 dedupe 策略。
- v0.5：用户管理、审计日志、细粒度权限、完全生产级 TLS 接入。

## 测试

```bash
python3 -m unittest discover -s tests -v
node -e "const fs=require('fs'),vm=require('vm');new vm.Script(fs.readFileSync('web/index.html','utf8').match(/<script>([\\s\\S]*?)<\\/script>/)[1]);console.log('JS syntax OK')"
```

目前是单用户内网 MVP；不是财务审计系统。并发状态编辑冲突会阻止覆盖，但账单服务依旧需要备份与访问管理。

## 注意：账单幂等与测试边界

UI 的 CSV 导出带有 `source,externalId` 字段。CSV 再次导入时，如二者都存在，可跳过重复引用；对没有唯一票据编号的 CSV，系统**无法可靠识别**同额重复扣款，请先检查。n8n API 导入强制携带稳定外部编号以便去重。

浏览器模拟测试（需开发环境安装 Playwright 与 Chromium）可执行 `python3 tests/browser_offline_check.py` 和 `python3 tests/browser_server_mock_check.py`。当前测试环境的 Chromium 企业策略阻止访问本地 HTTP URL，因此无法在此环境做浏览器对真实服务的网络端到端测试；服务端 HTTP API 与浏览器交互分别已经测试。Docker 镜像在本环境未执行实际构建和群晖部署验收。