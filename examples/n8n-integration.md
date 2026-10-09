# n8n → AI Spend Hub 接入说明

## MVP 流程（手工触发验证）

1. `Manual Trigger`：先手动验证是否可达。
2. `Edit Fields / Set`：构造一笔**真实已付款**的账单信息：日期、供应商、金额、币种、支付类别、source 和稳定的 externalId。
3. `HTTP Request`：`POST http://<NAS_PRIVATE_IP>:8765/api/transactions/import`；body JSON `{"transactions": [ {{$json}} ]}`（以 n8n 版本对应的表达式编辑器生成正确 JSON）。通过 n8n 的 Header Auth/Bearer Auth 凭据注入密钥；不要在节点导出的明文 JSON 中放访问令牌。
4. `IF`：解析 `imported` / `skipped` / 非 200 响应；只对确认写入成功的账单标注已同步。
5. `Error Trigger` 或工作流错误分支：记录解析失败项，等待人工复核。API 不承诺识别内容真实性。

## 接入邮箱时必须注意

- 只有在**用户主动授权**且明确指定检索范围后，才读取账单邮件。
- 不能只按主题含“invoice”就当作付款成功；检查金额、币种、账单号、退款、付款状态。
- 同一张账单在 Gmail 与银行流水均出现时，要统一 `source + externalId`，或增加跨源对账层，否则可能重复计入。
- 自动导入仅用于 **现金支付**。API 用量和充值积分消耗需要单独的使用量视图，不得与已支付充值混加。
- 不采集邮箱登录密码、信用卡号、API 密钥；日志需脱敏。

## 从其他 Compose 网络调用

优先让 n8n 与 AI Spend Hub 加入同一个 Docker bridge 网络，由 n8n 请求 `http://ai-spend-hub:8765`；或在受信任内网通过 `http://NAS_PRIVATE_IP:8765`。不要在公网上开放 8765 明文 HTTP。
