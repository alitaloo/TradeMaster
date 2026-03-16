# Stage 3.5 Pre-Live Safety Pack

本輪只落地 pre-live safety pack，不送 broker / Futu live exit order。

## 已落地

### 1. reservation / lease
- `lifecycle_exit_submit_attempts` 以 `proposal_id` 一筆對一個 submit attempt。
- `reservation_key = proposal:{proposal_id}:mode:{proposal_mode}`。
- `reservation_status = active|released|expired`。
- `lease_owner / lease_acquired_at / lease_expires_at` 形成短租約，避免同 proposal 被多 worker 重複提交。

### 2. submit attempt state machine
- `reserved`
- `submitting`
- `submitted`
- `ack_pending`
- `reconcile_pending`
- `reconciled`
- `cancelled|expired|failed`

目前 `SubmitAttemptService.advance_to_reconcile_pending()` 只做 dry-run 狀態推進，不呼叫 broker。

### 3. broker idempotency / external correlation
- `idempotency_key`：由 proposal/action 穩定欄位 hash 產生。
- `external_correlation_id`：獨立穩定 hash，可預留給未來 broker/clientOrderId 對接。
- DB 上有 unique key，最小落地先把「重試不重複建 attempt」做穩。

### 4. post-submit reconciliation hook
- `run_post_submit_reconciliation()` 會：
  1. `refresh_trade_lifecycles()`
  2. best-effort `reconcile_paper_positions(apply=True)`
  3. attempt 轉 `reconciled`
  4. reservation release

## 邊界
- detect / candidate / proposal / submit-attempt 仍然分層。
- 目前沒有任何 broker submit / live exit order API call。
- lifecycle closure / reconciliation / rebuild self-heal 主流程保持不變。
