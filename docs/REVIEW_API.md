# v0.3 账单审核 API（开发版）

所有接口需要 `Authorization: Bearer <AI_SPEND_ACCESS_TOKEN>`；所有写请求 `Content-Type: application/json`。

## 1. 提交候选账单

`POST /api/invoices/propose`

```json
{
  "candidates": [
    {
      "date": "2026-10-09",
      "provider": "Example AI",
      "type": "subscription",
      "amount": 20,
      "currency": "USD",
      "source": "manual-review",
      "externalId": "sample-20261009-001",
      "notes": "payment confirmation"
    }
  ]
}
```

返回 `{"queued":1,"skipped":0}`。每批最多 500 条；完整验证成功后才写入。候选账单不会修改消费总账或预算数字。

`source + externalId` 必须为**同一个上游票据**提供稳定唯一组合。同组合、相同内容重复提交会跳过；同组合但字段内容不同将返回 HTTP 409，整批回滚，请先核查数据。`rateToCNY` 可选，缺省使用提交时账本的汇率快照。

## 2. 查询与人工审核

- `GET /api/invoices?status=pending&limit=100`：默认查询待审核，可选 `approved`, `rejected`, `duplicate`, `all`；上限 500。
- `POST /api/invoices/decision`：单笔审批。

```json
{"source":"manual-review","externalId":"sample-20261009-001","decision":"approve"}
```

`decision` 可为 `approve` 或 `reject`。批准时同一事务原子写入现金总账并更新候选状态；如果账本已存在该上游编号则标记为 `duplicate` 且不新增账单。拒绝时不改变现金流水；已审核的不同决策返回 HTTP 409，重复提交相同决策返回 `alreadyReviewed:true`。

- `GET /api/invoices/events?limit=100`：只读审核事件记录，不存储凭证详情。
- 可通过 NAS 页面 `http://NAS_IP:8765/review` 打开人工审核页面。

## 3. 安全注意事项

- 外部 OCR / 邮件 Agent **只允许**先提交候选池；未经用户确认不要走直接导入 API。
- 不要上传完整邮件正文、支付卡号、Cookie、会话 token 或 API 密钥到候选记录；这里只接受必要的交易字段。
- 避免公开 HTTP；生产部署应使用 HTTPS 或可信 VPN。
- 相同付款同时出现在不同上游渠道时，当前无法自动进行跨来源合并，审核前须人工核对。
- 现有网页 JSON 导出不包含审批队列表，建议使用 README 的 SQLite 在线备份指令保全整个数据库。
