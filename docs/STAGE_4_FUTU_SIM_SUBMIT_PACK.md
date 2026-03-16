# Stage 4 Futu SIM 真 Submit Pack

本輪正式把 Stage 3.5 的 pre-live safety skeleton 接到 **Futu 模擬盤** 真 submit。

## 核心原則

- **只允許 Futu SIM / `paper_trading_mode=1` / `TrdEnv.SIMULATE`**
- **任何非 SIM 路徑直接 fail fast**
- 所有 submit / result / reconciliation payload 都會帶 `sim_only_guard=true`

## 落地內容

### 1. SIM-only broker guard

- `SubmitAttemptService.submit_live_exit_order()` 先檢查：
  - `SystemConfig.is_paper_trading() == true`
  - `SystemConfig.get_trading_mode() == 1`
  - proposal 必須是 `proposal_mode=live`
- guard 不通過時：
  - proposal -> `submit_blocked`
  - reconciliation -> `reconciliation_blocked`
  - 若已有 attempt，attempt -> `failed` + `submit_blocked`
  - result / payload 明確標示 `sim_only_guard=true`
- `paper_trading.get_trade_context()` 也加了第二層 guard：若 `trading_mode != 1` 直接 raise。
- `paper_trading.submit_paper_order()` 也加了 fail fast：若不是 SIM，直接回 `success=false`。

### 2. 真 submit path

- 新主入口：`SubmitAttemptService.submit_live_exit_order(proposal_id)`
- 流程：
  1. reserve / lease
  2. 組裝 stable request payload（symbol / side / qty / correlation）
  3. 呼叫 `paper_trading.submit_paper_order()` 真送到 Futu SIM
  4. 成功後保存：
     - `broker_order_id`
     - `external_order_ref`
     - `broker_request_key`
     - `idempotency_key`
     - `external_correlation_id`
  5. attempt 進到 `reconcile_pending`
  6. proposal 進到 `awaiting_reconciliation`

### 3. Duplicate protection

- `reserve_for_submission()` 會先看 proposal 是否已有 active attempt：
  - `reserved/submitting/submitted/ack_pending/reconcile_pending/reconciled`
  - 有就直接 reuse，不再重送 broker
- submit 成功後若已有 `broker_order_id`，再次呼叫會直接回既有 attempt
- submit repo 現在也會保存：
  - `lease_token`
  - `broker_request_key`
  - `external_order_ref`
  - request / response payload

### 4. Reconciliation coupling

- `run_post_submit_reconciliation()` 改為跑整個 `FutuSyncService.run_once()`
- submit 後 sync 會：
  - upsert `broker_orders`
  - upsert `broker_fills`
  - refresh lifecycle
- `FutuSyncService.refresh_trade_lifecycles()` 已補強：
  - **只要 exit order 已 submitted，即使還沒 fill，也會把 lifecycle 標成 `exit_pending`**
  - 這樣可以形成：
    - submit
    - broker_order record
    - lifecycle exit_pending
    - 後續 fill / close

## 修改檔案

- `execution/submit_attempt_service.py`
- `execution/submit_attempt_repository.py`
- `execution/futu_sync_service.py`
- `paper_trading.py`
- `tests/test_submit_attempt_service.py`
- `tests/test_futu_sync_service_stage4.py`
- `docs/STAGE_4_FUTU_SIM_SUBMIT_PACK.md`

## 驗證重點

- guard 測試：live / real mode 直接 blocked
- submit 測試：成功後 attempt -> `reconcile_pending`
- duplicate 測試：第二次 submit reuse 同一 attempt
- reconciliation 測試：sync 後 lifecycle 可進 `exit_pending`

## 目前邊界 / 風險

- 真 submit 目前透過既有 `paper_trading.submit_paper_order()` 路徑，依賴本地 OpenD / Futu SDK 正常可用
- lifecycle exit order 與 proposal/attempt 的 DB 關聯目前主要靠：
  - symbol + side + time
  - `external_order_ref` / `broker_order_id`
  後續仍可再補更強的 broker->proposal 顯式 foreign-key / raw_payload correlation
- 本輪未新增 migration；沿用 Stage 3.5 schema 即可落地
