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

## 3. 跨来源疑似重复提示（P0，纯人工决定）

`GET /api/invoices` 的待审核条目额外包含只读 `possibleDuplicates`。当两个不同 `source` 的记录满足**相同供应商（仅去首尾/重复空格并忽略大小写）、日期、交易类型、原币金额和币种**时返回提示列表（最多 5 项）；会查询仍在待审或已批准的候选，以及已有来源与外部票据编号的入账流水。**已拒绝候选不作为匹配依据**，同来源多张票据不标为跨来源重复。相同金额和日期但供应商不同不会提示。

```json
{"possibleDuplicates":[{"source":"other-source","externalId":"other-001","kind":"candidate","status":"pending"}]}
```

这不是票据真实性证明，也不是强制去重：此字段**不会触发写数据库、驳回、自动批准或改写汇率**。若有人手动批准两笔真实相似票据，账本仍会记录两笔，需人工对账。供应商别名、付款日期窗口、不同币种折算和缺失上游票据编号不在本轮范围。

## 4. 安全注意事项

- 外部 OCR / 邮件 Agent **只允许**先提交候选池；未经用户确认不要走直接导入 API。
- 不要上传完整邮件正文、支付卡号、Cookie、会话 token 或 API 密钥到候选记录；这里只接受必要的交易字段。
- 避免公开 HTTP；生产部署应使用 HTTPS 或可信 VPN。
- 跨来源仅有保守相似性**提示**，没有自动合并或自动拒绝；审核前仍须人工核对。
- 现有网页 JSON 导出不包含审批队列表，建议使用 README 的 SQLite 在线备份指令保全整个数据库。
