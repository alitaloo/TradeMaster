# Stage 3.5 Pre-Live Safety Pack

## Goal

把 Stage 3 已存在的 dry-run proposal，往 future live submit 前再推一層，但**仍然停在 pre-live boundary**：

- 不呼叫 broker / Futu live exit order
- 不直接改 lifecycle closure 主流程
- 先把 reservation / lease、submit attempt state machine、idempotency correlation、reconciliation hook 骨架補齊

## Layering

本輪分層維持：

`detect -> candidate -> proposal -> submit_attempt -> future broker submit -> reconciliation`

Stage 3.5 新增的是：

- `proposal` 上的 lease / submit state / future correlation 欄位
- `submit_attempt` 專屬資料表 `lifecycle_exit_submit_attempts`
- pre-live reconciliation hook payload

## Reservation / Lease

### Proposal lease fields

`lifecycle_exit_action_proposals` 新增：

- `lease_owner`
- `lease_token`
- `leased_at`
- `lease_expires_at`

### Guarantee

`ExitActionProposalRepository.acquire_lease()` 只允許在以下條件下搶 lease：

- proposal `status = proposed`
- `submit_state in (proposed, submit_failed, submit_blocked)`
- lease 已過期，或同 owner 續租

因此同一筆 proposal 不會被多個 worker / cron 同時接手。

## Submit state machine

Stage 3 的 `proposal.status` 仍保留 action evaluation 結果：

- `proposed`
- `blocked`
- `stale`

Stage 3.5 另外新增 `submit_state`，避免把 detect/action 判斷和 submit 流程混在一起：

- `proposed`：proposal 已建立，尚未被 worker 接手
- `leased`：worker 已拿到 lease
- `ready_to_submit`：pre-live submit guard 通過，未來 live path 可從這裡接 broker adapter
- `submit_blocked`：submit guard / state gate 未通過
- `submit_simulated`：本輪 dry-run 模擬送出已記錄，但沒有實際 broker call
- `submit_failed`：未來 live submit 或 pre-live materialization 失敗時可回落到此狀態

## Broker idempotency / external correlation

### Proposal-level fields

- `broker_request_key`
- `external_order_ref`

### Attempt-level fields

`lifecycle_exit_submit_attempts` 保留：

- `broker`
- `broker_request_key` (unique)
- `external_order_ref`
- `attempt_no`
- `request_payload`
- `response_payload`

### Current behavior

目前 request key 用 deterministic 格式：

`exit:{proposal_mode}:{proposal_id}:{candidate_id}`

若再次進入 submit flow，會先用 `broker_request_key` 查 `submit_attempt`：

- 找到既有 attempt → 直接 reuse，避免重複 materialize
- 找不到 → 建立新 attempt

這樣即使現在還沒接 broker，internal proposal -> future broker request key / external order ref 的 mapping 已經先固定。

## Submit attempt table

`lifecycle_exit_submit_attempts` 是 Stage 3.5 的 submit layer。

它用來記錄：

- lease owner / token
- attempt number
- dry-run or live mode
- attempt status
- failure reason
- reconciliation status / hook payload
- future broker correlation data

這讓 detect/candidate/proposal/submit-attempt 仍然清楚分層，不會把 submit side effect 混回 proposal evaluate。

## Post-submit reconciliation hook

新增 `execution/exit_reconciliation_hook.py`：

- 目前只生成 `build_pending_payload()`
- 回傳未來 reconciliation 需要的最小 payload
- `armed = false`
- 明確標註 `Stage 3.5 safety hook only`

目前 proposal / attempt 在 `submit_simulated` 後會被標成：

- `reconciliation_status = awaiting_reconciliation`
- `reconciliation_hook = paper_position_reconciliation`
- `reconciliation_payload = { proposal_id, submit_attempt_id, broker_request_key, external_order_ref, expected_transition, ... }`

也就是說 reconciliation 接點已經有 contract，但還沒有打開 live coupling。

## CLI / observability

### 1) 產生/更新 proposals

```bash
python scripts/lifecycle_exit_action.py --json
```

### 2) 模擬 pre-live submit（會 lease proposal，建立 attempt，但不送 broker）

```bash
python scripts/lifecycle_exit_action.py --submit-dry-run --lease-owner cron-risk-1 --json
```

### 3) 看 proposal 卡在哪個 pre-live state

```bash
python scripts/lifecycle_exit_action.py --inspect-submit-state --json
```

### 4) 看已持久化 submit attempts

```bash
python scripts/lifecycle_exit_action.py --list-attempts --json
```

## Safety boundary in this round

本輪仍然**沒有**做以下事情：

- broker API submit
- lifecycle `exit_pending` / `closed` live mutation
- reconciliation 主流程改寫
- external order polling

所以 Stage 3.5 的定位是：

**future live submit 前的安全骨架已完成，但 execution boundary 仍停在 dry-run / simulated submit。**
